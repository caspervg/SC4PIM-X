"""Procedural "city context" for the Lot Editor 3D preview.

Generates an abstract, architectural-massing-model neighborhood around the
current lot: streets, blocks, parcels, building masses, parks and trees. The
result is deterministic for a lot's TGI, needs no game assets, and is meant to
be generated once per lot and drawn from cached vertex arrays.

Coordinate systems
------------------
* Layout runs on an integer tile grid; 1 tile = 16 x 16 m (TILE_M). The lot
  occupies tiles [0, lot_w) x [0, lot_d); context tiles extend ``margin``
  tiles beyond each side, so tile coordinates may be negative.
* Scene geometry is emitted in metres in the same frame (tile * 16), with
  ``y`` up and the ground at y=0. ``build_context_mesh`` recentres it on the
  lot centre, matching the editor's 3D world (X east, Y up, Z toward the
  viewer's "front" edge; see Draw3D in SC4LotPreview).

Road-edge flags
---------------
Lot exemplar property 0x4A4A88F0 (dec 1246398704, "LotConfig Required
Roads", assets/new_properties.xml) is a Uint8 bitmask of lot sides that
require a road, in lot-local (pre-rotation) tile space:

    bit 0 (1, "Left")   -> road along column tx = -1        (EDGE_XMIN)
    bit 1 (2, "Behind") -> road along row    tz = -1        (EDGE_ZMIN)
    bit 2 (4, "Right")  -> road along column tx = lot_w     (EDGE_XMAX)
    bit 3 (8, "Front")  -> road along row    tz = lot_d     (EDGE_ZMAX)

Bits 0/2/3 match the editor's existing road-edge overlay drawing; bit 1
("Behind") is accepted here even though the current overlay code never drew
it. A flagged side receives a road along its complete border; an unflagged
side never receives an immediately bordering road.

This module is pure Python + numpy (no wx, no OpenGL) so all generation
logic is unit-testable headlessly.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections import deque
from dataclasses import dataclass

import numpy

# Bump when the generator's output changes meaningfully: it feeds the seed,
# so intentional visual evolution is explicit instead of silently reshuffling
# every lot's "stable" context.
CONTEXT_GENERATOR_VERSION = 5

TILE_M = 16.0
ROADWAY_M = 10.0
SIDEWALK_M = 3.0  # per side; SIDEWALK_M + ROADWAY_M + SIDEWALK_M == TILE_M
PARKING_STALL_M = 2.7
PARKING_DEPTH_M = 5.2
PARKING_AISLE_M = 6.0

EDGE_XMIN = "xmin"
EDGE_ZMIN = "zmin"
EDGE_XMAX = "xmax"
EDGE_ZMAX = "zmax"

# (bit value, edge) pairs for property 0x4A4A88F0; see module docstring.
ROAD_FLAG_EDGES = (
    (1, EDGE_XMIN),
    (2, EDGE_ZMIN),
    (4, EDGE_XMAX),
    (8, EDGE_ZMAX),
)

STYLE_URBAN = "urban"
STYLE_SUBURBAN = "suburban"
STYLE_INDUSTRIAL = "industrial"
STYLE_CIVIC = "civic"
STYLE_RURAL = "rural"
STYLE_MIXED = "mixed"

ROAD_STREET = "street"
ROAD_AVENUE = "avenue"
ROAD_BIKE = "bike"
ROAD_PEDESTRIAN = "pedestrian"

SEASON_SPRING = "spring"
SEASON_SUMMER = "summer"
SEASON_AUTUMN = "autumn"
SEASON_WINTER = "winter"

# Deliberate geometry ceilings. Modern hardware can comfortably carry a much
# richer cached backdrop, but every generated family remains bounded so large
# lots cannot create runaway meshes.
MAX_BOXES = 2500
MAX_TREES = 1400
MAX_LIT_WINDOWS = 2400
MAX_DETAIL_BOXES = 3000
MAX_FACADE_QUADS = 6500
MAX_NIGHT_LIGHTS = 800
MAX_CONTEXT_VERTICES = 500_000

_MARGIN_TILES = 18
_MAX_GRID_CELLS = 20_000  # shrink margin (never below 12) for enormous lots

_EMPTY, _LOT, _ROAD = 0, 1, 2


def season_for_month(month):
    """Return the broad visual season used by the procedural context."""
    try:
        month = int(month)
    except (TypeError, ValueError):
        month = 7
    if month in (3, 4, 5):
        return SEASON_SPRING
    if month in (9, 10, 11):
        return SEASON_AUTUMN
    if month in (12, 1, 2):
        return SEASON_WINTER
    return SEASON_SUMMER


def infer_context_style(purpose_types=None, building_purpose=None, *, civic=False, park=False):
    """Infer one broad preset from metadata already loaded for the lot.

    ``purpose_types`` is LotConfigPropertyPurposeTypes (0x88EDC796), while
    ``building_purpose`` is the building exemplar's Purpose (0x27812833).
    Explicit park/civic category membership wins; conflicting or unknown RCI
    metadata deliberately falls back to the neutral mixed preset.
    """
    if park or civic:
        return STYLE_CIVIC

    styles = set()
    for value in purpose_types or ():
        try:
            value = int(value)
        except (TypeError, ValueError):
            continue
        if value == 1:
            styles.add(STYLE_SUBURBAN)
        elif value in (2, 3):
            styles.add(STYLE_URBAN)
        elif value == 5:
            styles.add(STYLE_RURAL)
        elif value in (6, 7, 8):
            styles.add(STYLE_INDUSTRIAL)
    if len(styles) == 1:
        return styles.pop()
    if len(styles) > 1:
        return STYLE_MIXED

    try:
        purpose = int(building_purpose)
    except (TypeError, ValueError):
        return STYLE_MIXED
    if purpose == 1:
        return STYLE_SUBURBAN
    if purpose in (2, 3, 4):
        return STYLE_URBAN
    if purpose == 5:
        return STYLE_RURAL
    if purpose in (6, 7, 8):
        return STYLE_INDUSTRIAL
    return STYLE_MIXED


def road_edges_from_flags(flags):
    """Map the 0x4A4A88F0 bitmask to the set of flagged edges.

    Missing/malformed metadata (None, non-int) degrades to "no bordering
    roads" instead of raising, per the fail-safe requirement.
    """
    try:
        value = int(flags)
    except (TypeError, ValueError):
        return frozenset()
    return frozenset(edge for bit, edge in ROAD_FLAG_EDGES if value & bit)


def default_context_seed(tgi, version=CONTEXT_GENERATOR_VERSION):
    """Stable seed for a lot: full TGI + generator version, via blake2b.

    Python's built-in hash() is process-randomized; a keyed cryptographic
    hash keeps the default context identical across sessions.
    """
    t, g, i = (int(v) & 0xFFFFFFFF for v in tgi)
    digest = hashlib.blake2b(
        b"sc4pimx-city-context:%d:%d:%d:%d" % (int(version), t, g, i),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "little")


def variation_seed(base_seed, nonce):
    """Ephemeral per-session seed for the "Regenerate" action."""
    digest = hashlib.blake2b(
        b"sc4pimx-city-variation:%d:%d" % (int(base_seed), int(nonce)),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "little")


def context_seed(tgi, nonce=None):
    """Default seed, or a session-only variation when ``nonce`` is present."""
    default = default_context_seed(tgi)
    return default if nonce is None else variation_seed(default, nonce)


# ---------------------------------------------------------------------------
# Style presets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StylePreset:
    block_pitch: tuple  # street spacing range, tiles
    first_block: tuple  # depth of first block on unflagged sides, tiles
    parcel_max: int  # split parcels longer than this, tiles
    parcel_min: int  # never split below this, tiles
    front_setback: tuple  # metres from the road corridor edge
    side_gap: tuple  # metres between neighbouring masses
    height: tuple  # wall height range, metres
    corner_boost: float  # height multiplier near intersections
    open_space: float  # probability a parcel becomes park/plaza
    parking: float  # probability a parcel becomes parking
    tree_density: float  # 0..1 street/yard tree probability
    street_tree_spacing: float  # metres between street trees
    pitched_roofs: float  # probability of a pitched roof (small masses)
    archetypes: tuple  # weighted (name, weight) massing choices


STYLE_PRESETS = {
    STYLE_URBAN: StylePreset(
        block_pitch=(4, 6),
        first_block=(2, 3),
        parcel_max=4,
        parcel_min=1,
        front_setback=(0.5, 2.0),
        side_gap=(0.3, 1.0),
        height=(9.0, 34.0),
        corner_boost=1.45,
        open_space=0.10,
        parking=0.06,
        tree_density=0.55,
        street_tree_spacing=10.0,
        pitched_roofs=0.05,
        archetypes=(("row", 4), ("slab", 3), ("lshape", 2), ("podium", 3), ("stepped", 2), ("courtyard", 2)),
    ),
    STYLE_SUBURBAN: StylePreset(
        block_pitch=(5, 8),
        first_block=(2, 4),
        parcel_max=3,
        parcel_min=1,
        front_setback=(3.5, 6.0),
        side_gap=(2.0, 4.0),
        height=(3.5, 8.5),
        corner_boost=1.15,
        open_space=0.12,
        parking=0.03,
        tree_density=0.85,
        street_tree_spacing=8.0,
        pitched_roofs=0.85,
        archetypes=(("detached", 6), ("row", 2), ("lshape", 2)),
    ),
    STYLE_INDUSTRIAL: StylePreset(
        block_pitch=(6, 9),
        first_block=(3, 5),
        parcel_max=6,
        parcel_min=2,
        front_setback=(2.0, 6.0),
        side_gap=(1.5, 4.0),
        height=(5.0, 13.0),
        corner_boost=1.1,
        open_space=0.05,
        parking=0.16,
        tree_density=0.25,
        street_tree_spacing=16.0,
        pitched_roofs=0.30,
        archetypes=(("shed", 6), ("slab", 3), ("lshape", 1), ("stepped", 1)),
    ),
    STYLE_CIVIC: StylePreset(
        block_pitch=(5, 8),
        first_block=(2, 4),
        parcel_max=4,
        parcel_min=1,
        front_setback=(2.5, 5.0),
        side_gap=(1.5, 3.0),
        height=(4.5, 13.0),
        corner_boost=1.2,
        open_space=0.28,
        parking=0.08,
        tree_density=0.75,
        street_tree_spacing=9.0,
        pitched_roofs=0.45,
        archetypes=(("detached", 3), ("slab", 3), ("lshape", 2), ("courtyard", 2), ("row", 1)),
    ),
    STYLE_RURAL: StylePreset(
        block_pitch=(8, 12),
        first_block=(3, 6),
        parcel_max=8,
        parcel_min=2,
        front_setback=(4.0, 8.0),
        side_gap=(3.0, 6.0),
        height=(3.5, 7.5),
        corner_boost=1.0,
        open_space=0.38,
        parking=0.02,
        tree_density=0.55,
        street_tree_spacing=13.0,
        pitched_roofs=0.9,
        archetypes=(("detached", 5), ("shed", 3), ("lshape", 1)),
    ),
    STYLE_MIXED: StylePreset(
        block_pitch=(5, 7),
        first_block=(2, 4),
        parcel_max=4,
        parcel_min=1,
        front_setback=(1.5, 4.0),
        side_gap=(1.0, 3.0),
        height=(5.0, 18.0),
        corner_boost=1.3,
        open_space=0.13,
        parking=0.07,
        tree_density=0.6,
        street_tree_spacing=10.0,
        pitched_roofs=0.35,
        archetypes=(
            ("row", 3),
            ("detached", 2),
            ("slab", 3),
            ("lshape", 2),
            ("podium", 1),
            ("stepped", 1),
            ("courtyard", 1),
        ),
    ),
}


# ---------------------------------------------------------------------------
# Scene primitives (immutable output of generation, input of the mesh build)
# ---------------------------------------------------------------------------

# Materials index into _PALETTE at mesh-build time.
MAT_GROUND = "ground"
MAT_ROAD = "road"
MAT_SIDEWALK = "sidewalk"
MAT_PARK = "park"
MAT_PLAZA = "plaza"
MAT_PARKING = "parking"
MAT_PARKING_AISLE = "parking_aisle"
MAT_YARD = "yard"
MAT_WALL = "wall"
MAT_ROOF = "roof"
MAT_ROOF_PITCHED = "roof_pitched"
MAT_TRUNK = "trunk"
MAT_CANOPY = "canopy"
MAT_MARKING = "marking"
MAT_CONTACT = "contact"
MAT_CURB = "curb"
MAT_WINDOW = "window"
MAT_DOOR = "door"
MAT_STOREFRONT = "storefront"
MAT_AWNING = "awning"
MAT_METAL = "metal"
MAT_DARK_METAL = "dark_metal"
MAT_BRICK = "brick"
MAT_HEDGE = "hedge"
MAT_FIELD = "field"
MAT_VEHICLE_RED = "vehicle_red"
MAT_VEHICLE_BLUE = "vehicle_blue"
MAT_VEHICLE_NEUTRAL = "vehicle_neutral"
MAT_LAMP = "lamp"
MAT_BENCH = "bench"
MAT_WATER = "water"
MAT_HORIZON = "horizon"
MAT_BIKE_LANE = "bike_lane"
MAT_PEDESTRIAN = "pedestrian"
MAT_ISLAND = "island"


@dataclass(frozen=True)
class Rect:
    """Flat ground-plane rectangle at height y (metres, tile frame)."""

    material: str
    x0: float
    z0: float
    x1: float
    z1: float
    y: float


@dataclass(frozen=True)
class Box:
    """Axis-aligned prism; tint scales the material colour per building."""

    material: str
    x0: float
    z0: float
    x1: float
    z1: float
    y0: float
    y1: float
    tint: float = 1.0


@dataclass(frozen=True)
class Roof:
    """Gable roof over [x0,x1]x[z0,z1] with the ridge along ``axis``."""

    x0: float
    z0: float
    x1: float
    z1: float
    eave_y: float
    ridge_y: float
    axis: str  # 'x' or 'z': the direction the ridge line runs
    tint: float = 1.0


@dataclass(frozen=True)
class Tree:
    x: float
    z: float
    base_y: float
    trunk_h: float
    canopy_h: float
    radius: float
    conifer: bool = False
    rotation: float = 0.0
    tint: float = 1.0


@dataclass(frozen=True)
class Quad:
    """An arbitrarily oriented, single-sided detail quad."""

    material: str
    points: tuple
    tint: float = 1.0


@dataclass(frozen=True)
class ContextScene:
    lot_w: int
    lot_d: int
    margin: int
    style: str
    seed: int
    version: int
    road_tiles: tuple  # integer tile coordinates occupied by 16 m corridors
    rects: tuple  # ground / roads / sidewalks / parcel surfaces
    boxes: tuple  # building masses
    roofs: tuple  # pitched roofs
    trees: tuple  # vegetation (detail LOD)
    detail_rects: tuple  # lane markings, parking stalls (detail LOD)
    detail_boxes: tuple  # cars, furniture and rooftop fittings (detail LOD)
    detail_quads: tuple  # facade windows, doors and signs (detail LOD)
    road_profiles: tuple  # (axis, coordinate, kind) corridor classifications
    season: str = SEASON_SUMMER


# Ground-plane stack, all below the lot's own textures at y=0 so the context
# can never z-fight with or cover the editable lot surface.
_Y_GROUND = -0.10
_Y_PARCEL = -0.06
_Y_PARKING_AISLE = -0.055
_Y_CONTACT = -0.05
_Y_ROAD = -0.04
_Y_MARKING = -0.035
_Y_SIDEWALK = -0.02
_Y_BUILDING_BASE = -0.08


def generate_city_context(lot_w, lot_d, road_edges, style, seed, season=SEASON_SUMMER):
    """Generate the neighbourhood layout. Pure; all randomness is local.

    lot_w/lot_d are the lot dimensions in tiles (property 0x88EDC790);
    road_edges is a set of EDGE_* constants (see road_edges_from_flags);
    style is one of the STYLE_* constants (unknown values fall back to
    mixed); seed comes from default_context_seed / variation_seed.
    """
    lot_w = max(1, int(lot_w))
    lot_d = max(1, int(lot_d))
    road_edges = frozenset(road_edges or ())
    preset = STYLE_PRESETS.get(style) or STYLE_PRESETS[STYLE_MIXED]
    if style not in STYLE_PRESETS:
        style = STYLE_MIXED
    if season not in (SEASON_SPRING, SEASON_SUMMER, SEASON_AUTUMN, SEASON_WINTER):
        season = SEASON_SUMMER
    rng = random.Random(seed)

    margin = _MARGIN_TILES
    while margin > 12 and (lot_w + 2 * margin) * (lot_d + 2 * margin) > _MAX_GRID_CELLS:
        margin -= 1

    grid = _Grid(lot_w, lot_d, margin)
    _carve_streets(grid, rng, preset, road_edges)
    road_profiles = _classify_road_profiles(grid, rng, style)

    rects = list(_ground_frame(grid))
    detail_rects = []
    boxes = []
    roofs = []
    trees = []
    detail_boxes = []
    detail_quads = []

    road_tiles = tuple(sorted(grid.road_tiles(), key=lambda tile: (tile[1], tile[0])))
    rects.extend(_road_corridors(grid, detail_rects, road_profiles, style))

    blocks = grid.blocks()
    for block_index, block_cells in enumerate(blocks):
        block_rng = random.Random(rng.getrandbits(64))
        traits = _BlockTraits(
            height_factor=block_rng.uniform(0.85, 1.2),
            front_setback=block_rng.uniform(*preset.front_setback),
            archetype=_weighted_choice(block_rng, preset.archetypes),
        )
        for parcel in _parcels_for_block(block_cells, block_rng, preset):
            _fill_parcel(grid, parcel, block_rng, preset, traits, rects, detail_rects, boxes, roofs, trees)

    _street_trees(grid, rng, preset, trees)
    _decorate_streets(grid, rng, style, detail_rects, detail_boxes, road_profiles)
    _decorate_open_spaces(grid, rng, style, rects, detail_rects, detail_boxes)

    # Deterministic thinning to honour the geometry ceilings.
    if len(trees) > MAX_TREES:
        step = len(trees) / float(MAX_TREES)
        trees = [trees[int(i * step)] for i in range(MAX_TREES)]
    if len(boxes) > MAX_BOXES:
        step = len(boxes) / float(MAX_BOXES)
        boxes = [boxes[int(i * step)] for i in range(MAX_BOXES)]
    # Facade and roof dressing is generated only for masses that survived the
    # primary ceiling, avoiding orphan detail on pathological large scenes.
    _decorate_buildings(grid, rng, style, boxes, roofs, detail_boxes, detail_quads)
    if len(detail_boxes) > MAX_DETAIL_BOXES:
        step = len(detail_boxes) / float(MAX_DETAIL_BOXES)
        detail_boxes = [detail_boxes[int(i * step)] for i in range(MAX_DETAIL_BOXES)]
    if len(detail_quads) > MAX_FACADE_QUADS:
        step = len(detail_quads) / float(MAX_FACADE_QUADS)
        detail_quads = [detail_quads[int(i * step)] for i in range(MAX_FACADE_QUADS)]

    # Small offset footprint pads ground the masses without transparent
    # shadows, sorting, or another draw call. Stacked upper boxes are skipped.
    rects.extend(
        Rect(MAT_CONTACT, box.x0 + 0.2, box.z0 + 0.2, box.x1 + 0.2, box.z1 + 0.2, _Y_CONTACT)
        for box in boxes
        if box.y0 <= _Y_BUILDING_BASE + 0.001
    )
    detail_rects = _merge_adjacent_rects(detail_rects)

    return ContextScene(
        lot_w=lot_w,
        lot_d=lot_d,
        margin=margin,
        style=style,
        seed=seed,
        version=CONTEXT_GENERATOR_VERSION,
        road_tiles=road_tiles,
        rects=tuple(rects),
        boxes=tuple(boxes),
        roofs=tuple(roofs),
        trees=tuple(trees),
        detail_rects=tuple(detail_rects),
        detail_boxes=tuple(detail_boxes),
        detail_quads=tuple(detail_quads),
        road_profiles=road_profiles,
        season=season,
    )


def _merge_adjacent_rects(rects):
    """Coalesce contiguous same-material strips without changing their shape."""

    def merge(items, horizontal):
        groups = {}
        for rect in items:
            key = (rect.material, rect.y, rect.z0, rect.z1) if horizontal else (rect.material, rect.y, rect.x0, rect.x1)
            groups.setdefault(key, []).append(rect)
        merged = []
        for group in groups.values():
            group.sort(key=lambda rect: rect.x0 if horizontal else rect.z0)
            current = group[0]
            for rect in group[1:]:
                end = current.x1 if horizontal else current.z1
                start = rect.x0 if horizontal else rect.z0
                if abs(end - start) < 1.0e-6:
                    current = (
                        Rect(current.material, current.x0, current.z0, rect.x1, current.z1, current.y)
                        if horizontal
                        else Rect(current.material, current.x0, current.z0, current.x1, rect.z1, current.y)
                    )
                else:
                    merged.append(current)
                    current = rect
            merged.append(current)
        return merged

    return merge(merge(rects, True), False)


# ---------------------------------------------------------------------------
# Tile grid + street network
# ---------------------------------------------------------------------------


class _Grid:
    """Occupancy grid in tile coordinates; tx/tz may be negative.

    Internally indexed [tz + margin][tx + margin].
    """

    def __init__(self, lot_w, lot_d, margin):
        self.lot_w = lot_w
        self.lot_d = lot_d
        self.margin = margin
        self.w = lot_w + 2 * margin
        self.h = lot_d + 2 * margin
        self.cells = numpy.zeros((self.h, self.w), dtype=numpy.int8)
        self.cells[margin : margin + lot_d, margin : margin + lot_w] = _LOT
        self.tx_min = -margin
        self.tz_min = -margin
        self.tx_max = lot_w + margin  # exclusive
        self.tz_max = lot_d + margin  # exclusive

    def get(self, tx, tz):
        if not (self.tx_min <= tx < self.tx_max and self.tz_min <= tz < self.tz_max):
            return None
        return int(self.cells[tz + self.margin, tx + self.margin])

    def is_road(self, tx, tz):
        return self.get(tx, tz) == _ROAD

    def set_road(self, tx, tz):
        if self.get(tx, tz) == _EMPTY:
            self.cells[tz + self.margin, tx + self.margin] = _ROAD

    def carve_col(self, tx, tz0, tz1):
        for tz in range(max(tz0, self.tz_min), min(tz1, self.tz_max - 1) + 1):
            self.set_road(tx, tz)

    def carve_row(self, tz, tx0, tx1):
        for tx in range(max(tx0, self.tx_min), min(tx1, self.tx_max - 1) + 1):
            self.set_road(tx, tz)

    def road_tiles(self):
        zs, xs = numpy.nonzero(self.cells == _ROAD)
        return [(int(x) - self.margin, int(z) - self.margin) for z, x in zip(zs, xs)]

    def blocks(self):
        """Connected components of empty cells, in deterministic order."""
        seen = numpy.zeros_like(self.cells, dtype=bool)
        blocks = []
        for gz in range(self.h):
            for gx in range(self.w):
                if seen[gz, gx] or self.cells[gz, gx] != _EMPTY:
                    continue
                cells = []
                queue = deque(((gz, gx),))
                seen[gz, gx] = True
                while queue:
                    cz, cx = queue.popleft()
                    cells.append((cx - self.margin, cz - self.margin))
                    for nz, nx in ((cz - 1, cx), (cz + 1, cx), (cz, cx - 1), (cz, cx + 1)):
                        if 0 <= nz < self.h and 0 <= nx < self.w and not seen[nz, nx] and self.cells[nz, nx] == _EMPTY:
                            seen[nz, nx] = True
                            queue.append((nz, nx))
                cells.sort(key=lambda c: (c[1], c[0]))
                blocks.append(cells)
        return blocks


def _carve_streets(grid, rng, preset, road_edges):
    """Lay the street network: flagged border roads first, then a walked
    grid of secondary streets that never touches an unflagged lot border."""
    lot_w, lot_d = grid.lot_w, grid.lot_d

    road_cols = []
    road_rows = []

    # Mandatory roads along flagged borders run the full grid so they read
    # as through-streets and connect the rest of the network.
    if EDGE_XMIN in road_edges:
        road_cols.append(-1)
    if EDGE_XMAX in road_edges:
        road_cols.append(lot_w)
    if EDGE_ZMIN in road_edges:
        road_rows.append(-1)
    if EDGE_ZMAX in road_edges:
        road_rows.append(lot_d)

    def walk(flagged, border, sign, limit):
        """Street positions marching outward from one side of the lot.

        The first street sits on the border tile when flagged, else one
        first_block-deep block away, keeping unflagged borders road-free.
        """
        positions = []
        if flagged:
            pos = border + sign * (rng.randint(*preset.block_pitch))
        else:
            pos = border + sign * (1 + rng.randint(*preset.first_block))
        while (limit - pos) * sign >= 3:
            positions.append(pos)
            pos += sign * rng.randint(*preset.block_pitch)
        return positions

    road_cols.extend(walk(EDGE_XMIN in road_edges, -1, -1, grid.tx_min))
    road_cols.extend(walk(EDGE_XMAX in road_edges, lot_w, 1, grid.tx_max - 1))
    road_rows.extend(walk(EDGE_ZMIN in road_edges, -1, -1, grid.tz_min))
    road_rows.extend(walk(EDGE_ZMAX in road_edges, lot_d, 1, grid.tz_max - 1))

    for tx in road_cols:
        grid.carve_col(tx, grid.tz_min, grid.tz_max - 1)
    for tz in road_rows:
        grid.carve_row(tz, grid.tx_min, grid.tx_max - 1)

    # Split streets across the bands directly above/below (and left/right of)
    # a wide lot: they run from the grid edge to the first street on that
    # side (T-intersection) and never continue across the lot itself.
    rows_above = [r for r in road_rows if r < 0]
    rows_below = [r for r in road_rows if r >= lot_d]
    cols_left = [c for c in road_cols if c < 0]
    cols_right = [c for c in road_cols if c >= lot_w]

    def interior_positions(span):
        positions = []
        pos = rng.randint(2, max(2, preset.block_pitch[0]))
        while pos <= span - 3:
            positions.append(pos)
            pos += rng.randint(*preset.block_pitch)
        return positions

    if lot_w >= preset.block_pitch[0] + 2:
        for tx in interior_positions(lot_w):
            if rows_above:
                grid.carve_col(tx, grid.tz_min, max(rows_above) - 1)
            if rows_below:
                grid.carve_col(tx, min(rows_below) + 1, grid.tz_max - 1)
    if lot_d >= preset.block_pitch[0] + 2:
        for tz in interior_positions(lot_d):
            if cols_left:
                grid.carve_row(tz, grid.tx_min, max(cols_left) - 1)
            if cols_right:
                grid.carve_row(tz, min(cols_right) + 1, grid.tx_max - 1)


def _profile_maps(road_profiles):
    horizontal, vertical = {}, {}
    for axis, coordinate, kind in road_profiles or ():
        (horizontal if axis == "h" else vertical)[int(coordinate)] = kind
    return horizontal, vertical


def _classify_road_profiles(grid, rng, style):
    """Classify coherent corridors, widening selected avenues to two tiles."""
    road_tiles = set(grid.road_tiles())
    horizontal = sorted({tz for tx, tz in road_tiles if (tx - 1, tz) in road_tiles or (tx + 1, tz) in road_tiles})
    vertical = sorted({tx for tx, tz in road_tiles if (tx, tz - 1) in road_tiles or (tx, tz + 1) in road_tiles})

    avenue_chance = {
        STYLE_URBAN: 0.82,
        STYLE_SUBURBAN: 0.34,
        STYLE_INDUSTRIAL: 0.70,
        STYLE_CIVIC: 0.55,
        STYLE_RURAL: 0.12,
    }.get(style, 0.60)
    bike_chance = {
        STYLE_URBAN: 0.20,
        STYLE_SUBURBAN: 0.18,
        STYLE_INDUSTRIAL: 0.08,
        STYLE_CIVIC: 0.24,
        STYLE_RURAL: 0.04,
    }.get(style, 0.16)
    pedestrian_chance = {
        STYLE_URBAN: 0.09,
        STYLE_SUBURBAN: 0.05,
        STYLE_INDUSTRIAL: 0.02,
        STYLE_CIVIC: 0.15,
        STYLE_RURAL: 0.05,
    }.get(style, 0.08)

    profiles = {}

    def corridor_length(axis, coordinate):
        return sum(1 for tx, tz in road_tiles if (tz == coordinate if axis == "h" else tx == coordinate))

    def choose_avenue(axis, coordinates):
        candidates = [coordinate for coordinate in coordinates if corridor_length(axis, coordinate) >= 8]
        if not candidates or rng.random() >= avenue_chance:
            return None
        longest = max(corridor_length(axis, coordinate) for coordinate in candidates)
        strong = [coordinate for coordinate in candidates if corridor_length(axis, coordinate) >= longest * 0.75]
        return rng.choice(strong)

    avenue_h = choose_avenue("h", horizontal)
    avenue_v = choose_avenue("v", vertical)

    def ordinary_kind(axis, coordinate):
        # A promenade may never replace the immediate road serving the lot.
        borders = {-1, grid.lot_d} if axis == "h" else {-1, grid.lot_w}
        roll = rng.random()
        if coordinate not in borders and roll < pedestrian_chance:
            return ROAD_PEDESTRIAN
        if roll < pedestrian_chance + bike_chance:
            return ROAD_BIKE
        return ROAD_STREET

    for coordinate in horizontal:
        profiles[("h", coordinate)] = ROAD_AVENUE if coordinate == avenue_h else ordinary_kind("h", coordinate)
    for coordinate in vertical:
        profiles[("v", coordinate)] = ROAD_AVENUE if coordinate == avenue_v else ordinary_kind("v", coordinate)

    def widen(axis, coordinate):
        if coordinate is None:
            return
        if axis == "h":
            preferred = coordinate - 1 if coordinate < 0 else coordinate + 1
            alternatives = (preferred, coordinate + 1 if preferred < coordinate else coordinate - 1)
            pair = next(
                (
                    candidate
                    for candidate in alternatives
                    if grid.tz_min <= candidate < grid.tz_max
                    and any(grid.get(tx, candidate) == _EMPTY for tx in range(grid.tx_min, grid.tx_max))
                ),
                None,
            )
            if pair is None:
                return
            for tx in range(grid.tx_min, grid.tx_max):
                if grid.is_road(tx, coordinate):
                    grid.set_road(tx, pair)
            profiles[("h", pair)] = ROAD_AVENUE
        else:
            preferred = coordinate - 1 if coordinate < 0 else coordinate + 1
            alternatives = (preferred, coordinate + 1 if preferred < coordinate else coordinate - 1)
            pair = next(
                (
                    candidate
                    for candidate in alternatives
                    if grid.tx_min <= candidate < grid.tx_max
                    and any(grid.get(candidate, tz) == _EMPTY for tz in range(grid.tz_min, grid.tz_max))
                ),
                None,
            )
            if pair is None:
                return
            for tz in range(grid.tz_min, grid.tz_max):
                if grid.is_road(coordinate, tz):
                    grid.set_road(pair, tz)
            profiles[("v", pair)] = ROAD_AVENUE

    widen("h", avenue_h)
    widen("v", avenue_v)
    return tuple((axis, coordinate, kind) for (axis, coordinate), kind in sorted(profiles.items()))


def _ground_frame(grid):
    """Base ground plane as four rects framing (never covering) the lot."""
    x0, z0 = grid.tx_min * TILE_M, grid.tz_min * TILE_M
    x1, z1 = grid.tx_max * TILE_M, grid.tz_max * TILE_M
    lx0, lz0 = 0.0, 0.0
    lx1, lz1 = grid.lot_w * TILE_M, grid.lot_d * TILE_M
    return (
        Rect(MAT_GROUND, x0, z0, x1, lz0, _Y_GROUND),  # north band
        Rect(MAT_GROUND, x0, lz1, x1, z1, _Y_GROUND),  # south band
        Rect(MAT_GROUND, x0, lz0, lx0, lz1, _Y_GROUND),  # west band
        Rect(MAT_GROUND, lx1, lz0, x1, lz1, _Y_GROUND),  # east band
    )


def _road_corridors(grid, detail_rects, road_profiles=None, style=None):
    """Emit coherent street, avenue, bike-lane and promenade corridors."""
    rects = []
    horizontal_profiles, vertical_profiles = _profile_maps(road_profiles)
    median_material = {
        STYLE_SUBURBAN: MAT_HEDGE,
        STYLE_CIVIC: MAT_HEDGE,
        STYLE_URBAN: MAT_ISLAND,
        STYLE_MIXED: MAT_ISLAND,
        STYLE_INDUSTRIAL: MAT_ISLAND,
    }.get(style)

    # Direct unit-test callers and old serialized scenes have no profile map;
    # infer the legacy one-tile street orientation in that case.
    profiled = bool(road_profiles)
    for tx, tz in grid.road_tiles():
        x, z = tx * TILE_M, tz * TILE_M
        n = grid.is_road(tx, tz - 1)
        s = grid.is_road(tx, tz + 1)
        w = grid.is_road(tx - 1, tz)
        e = grid.is_road(tx + 1, tz)
        hkind = horizontal_profiles.get(tz)
        vkind = vertical_profiles.get(tx)
        horizontal = bool(hkind and (w or e)) if profiled else (w or e or not (n or s))
        vertical = bool(vkind and (n or s)) if profiled else bool(n or s)
        if horizontal and hkind is None:
            hkind = ROAD_STREET
        if vertical and vkind is None:
            vkind = ROAD_STREET

        def horizontal_span(kind):
            if kind == ROAD_AVENUE:
                pair_n = horizontal_profiles.get(tz - 1) == ROAD_AVENUE
                pair_s = horizontal_profiles.get(tz + 1) == ROAD_AVENUE
                return (0.0 if pair_n else 2.0), (TILE_M if pair_s else 14.0), MAT_ROAD
            if kind == ROAD_PEDESTRIAN:
                width = 4.0 if vertical and vkind != ROAD_PEDESTRIAN else 8.0
                return (TILE_M - width) * 0.5, (TILE_M + width) * 0.5, MAT_PEDESTRIAN
            return SIDEWALK_M, SIDEWALK_M + ROADWAY_M, MAT_ROAD

        def vertical_span(kind):
            if kind == ROAD_AVENUE:
                pair_w = vertical_profiles.get(tx - 1) == ROAD_AVENUE
                pair_e = vertical_profiles.get(tx + 1) == ROAD_AVENUE
                return (0.0 if pair_w else 2.0), (TILE_M if pair_e else 14.0), MAT_ROAD
            if kind == ROAD_PEDESTRIAN:
                width = 4.0 if horizontal and hkind != ROAD_PEDESTRIAN else 8.0
                return (TILE_M - width) * 0.5, (TILE_M + width) * 0.5, MAT_PEDESTRIAN
            return SIDEWALK_M, SIDEWALK_M + ROADWAY_M, MAT_ROAD

        hz0, hz1, hmaterial = horizontal_span(hkind) if horizontal else (8.0, 8.0, MAT_ROAD)
        vx0, vx1, vmaterial = vertical_span(vkind) if vertical else (8.0, 8.0, MAT_ROAD)
        if horizontal:
            y = _Y_ROAD + (0.006 if hmaterial == MAT_PEDESTRIAN else 0.0)
            rects.append(Rect(hmaterial, x + (0 if w else vx0), z + hz0, x + (TILE_M if e else vx1), z + hz1, y))
        if vertical:
            y = _Y_ROAD + (0.006 if vmaterial == MAT_PEDESTRIAN else 0.0)
            rects.append(Rect(vmaterial, x + vx0, z + (0 if n else hz0), x + vx1, z + (TILE_M if s else hz1), y))

        # Only exterior edges receive sidewalks. Paired avenue tiles therefore
        # form one uninterrupted 32 m right-of-way with sidewalks outside.
        if horizontal:
            if hz0 > 0.0:
                rects.append(Rect(MAT_SIDEWALK, x, z, x + TILE_M, z + hz0, _Y_SIDEWALK))
            if hz1 < TILE_M:
                rects.append(Rect(MAT_SIDEWALK, x, z + hz1, x + TILE_M, z + TILE_M, _Y_SIDEWALK))
        if vertical:
            if vx0 > 0.0:
                rects.append(Rect(MAT_SIDEWALK, x, z, x + vx0, z + TILE_M, _Y_SIDEWALK))
            if vx1 < TILE_M:
                rects.append(Rect(MAT_SIDEWALK, x + vx1, z, x + TILE_M, z + TILE_M, _Y_SIDEWALK))

        straight_h = horizontal and not vertical
        straight_v = vertical and not horizontal
        if straight_h:
            if hz0 > 0.0:
                detail_rects.append(Rect(MAT_CURB, x, z + hz0 - 0.12, x + TILE_M, z + hz0 + 0.12, _Y_MARKING))
            if hz1 < TILE_M:
                detail_rects.append(Rect(MAT_CURB, x, z + hz1 - 0.12, x + TILE_M, z + hz1 + 0.12, _Y_MARKING))
            if hkind == ROAD_STREET:
                for start in (1.0, 9.0):
                    detail_rects.append(Rect(MAT_MARKING, x + start, z + 7.9, x + start + 4.0, z + 8.1, _Y_MARKING))
            elif hkind == ROAD_BIKE:
                detail_rects.extend(
                    (
                        Rect(MAT_BIKE_LANE, x, z + 3.2, x + TILE_M, z + 4.65, _Y_MARKING),
                        Rect(MAT_BIKE_LANE, x, z + 11.35, x + TILE_M, z + 12.8, _Y_MARKING),
                    )
                )
                for start in (1.0, 9.0):
                    detail_rects.append(Rect(MAT_MARKING, x + start, z + 7.9, x + start + 4.0, z + 8.1, _Y_MARKING))
            elif hkind == ROAD_AVENUE:
                pair_n = horizontal_profiles.get(tz - 1) == ROAD_AVENUE
                pair_s = horizontal_profiles.get(tz + 1) == ROAD_AVENUE
                if pair_s:
                    if median_material:
                        detail_rects.append(Rect(median_material, x, z + 15.4, x + TILE_M, z + 16.0, _Y_SIDEWALK))
                    lane_z = z + (hz0 + 15.4) * 0.5
                elif pair_n:
                    if median_material:
                        detail_rects.append(Rect(median_material, x, z, x + TILE_M, z + 0.6, _Y_SIDEWALK))
                    lane_z = z + (0.6 + hz1) * 0.5
                else:
                    lane_z = z + 8.0
                for start in (1.0, 9.0):
                    detail_rects.append(
                        Rect(MAT_MARKING, x + start, lane_z - 0.1, x + start + 4.0, lane_z + 0.1, _Y_MARKING)
                    )
        elif straight_v:
            if vx0 > 0.0:
                detail_rects.append(Rect(MAT_CURB, x + vx0 - 0.12, z, x + vx0 + 0.12, z + TILE_M, _Y_MARKING))
            if vx1 < TILE_M:
                detail_rects.append(Rect(MAT_CURB, x + vx1 - 0.12, z, x + vx1 + 0.12, z + TILE_M, _Y_MARKING))
            if vkind == ROAD_STREET:
                for start in (1.0, 9.0):
                    detail_rects.append(Rect(MAT_MARKING, x + 7.9, z + start, x + 8.1, z + start + 4.0, _Y_MARKING))
            elif vkind == ROAD_BIKE:
                detail_rects.extend(
                    (
                        Rect(MAT_BIKE_LANE, x + 3.2, z, x + 4.65, z + TILE_M, _Y_MARKING),
                        Rect(MAT_BIKE_LANE, x + 11.35, z, x + 12.8, z + TILE_M, _Y_MARKING),
                    )
                )
                for start in (1.0, 9.0):
                    detail_rects.append(Rect(MAT_MARKING, x + 7.9, z + start, x + 8.1, z + start + 4.0, _Y_MARKING))
            elif vkind == ROAD_AVENUE:
                pair_w = vertical_profiles.get(tx - 1) == ROAD_AVENUE
                pair_e = vertical_profiles.get(tx + 1) == ROAD_AVENUE
                if pair_e:
                    if median_material:
                        detail_rects.append(Rect(median_material, x + 15.4, z, x + 16.0, z + TILE_M, _Y_SIDEWALK))
                    lane_x = x + (vx0 + 15.4) * 0.5
                elif pair_w:
                    if median_material:
                        detail_rects.append(Rect(median_material, x, z, x + 0.6, z + TILE_M, _Y_SIDEWALK))
                    lane_x = x + (0.6 + vx1) * 0.5
                else:
                    lane_x = x + 8.0
                for start in (1.0, 9.0):
                    detail_rects.append(
                        Rect(MAT_MARKING, lane_x - 0.1, z + start, lane_x + 0.1, z + start + 4.0, _Y_MARKING)
                    )
    return rects


# ---------------------------------------------------------------------------
# Blocks, parcels and massing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _BlockTraits:
    """Per-block composition anchors so a block reads as one neighbourhood:
    a shared frontage setback, coherent heights, a favoured archetype."""

    height_factor: float
    front_setback: float
    archetype: str


@dataclass(frozen=True)
class _Parcel:
    tx0: int
    tz0: int
    tx1: int  # exclusive
    tz1: int  # exclusive
    road_sides: tuple  # subset of EDGE_* adjacent to a street
    front: str  # the EDGE_* the massing faces (or '' if landlocked)

    @property
    def w_tiles(self):
        return self.tx1 - self.tx0

    @property
    def d_tiles(self):
        return self.tz1 - self.tz0


def _weighted_choice(rng, weighted):
    total = sum(weight for _name, weight in weighted)
    pick = rng.uniform(0.0, total)
    for name, weight in weighted:
        pick -= weight
        if pick <= 0.0:
            return name
    return weighted[-1][0]


def _rect_decompose(cells):
    """Greedy decomposition of a tile set into rectangles (top-left first)."""
    remaining = set(cells)
    rects = []
    while remaining:
        tz0, tx0 = min((tz, tx) for tx, tz in remaining)
        w = 1
        while (tx0 + w, tz0) in remaining:
            w += 1
        h = 1
        while all((tx, tz0 + h) in remaining for tx in range(tx0, tx0 + w)):
            h += 1
        for tz in range(tz0, tz0 + h):
            for tx in range(tx0, tx0 + w):
                remaining.discard((tx, tz))
        rects.append((tx0, tz0, tx0 + w, tz0 + h))
    return rects


def _split_rect(rect, rng, preset):
    """Recursively split a rectangle into parcel-sized pieces."""
    tx0, tz0, tx1, tz1 = rect
    w, d = tx1 - tx0, tz1 - tz0
    if max(w, d) <= preset.parcel_max:
        return [rect]
    if w >= d:
        if w < 2 * preset.parcel_min:
            return [rect]
        cut = tx0 + rng.randint(preset.parcel_min, w - preset.parcel_min)
        return _split_rect((tx0, tz0, cut, tz1), rng, preset) + _split_rect((cut, tz0, tx1, tz1), rng, preset)
    if d < 2 * preset.parcel_min:
        return [rect]
    cut = tz0 + rng.randint(preset.parcel_min, d - preset.parcel_min)
    return _split_rect((tx0, tz0, tx1, cut), rng, preset) + _split_rect((tx0, cut, tx1, tz1), rng, preset)


def _parcels_for_block(block_cells, rng, preset):
    parcels = []
    for rect in _rect_decompose(block_cells):
        parcels.extend(_split_rect(rect, rng, preset))
    return parcels


def _parcel_road_sides(grid, tx0, tz0, tx1, tz1):
    """Which parcel sides face a street, ordered deterministically."""
    sides = []
    counts = {}
    counts[EDGE_XMIN] = sum(1 for tz in range(tz0, tz1) if grid.is_road(tx0 - 1, tz))
    counts[EDGE_XMAX] = sum(1 for tz in range(tz0, tz1) if grid.is_road(tx1, tz))
    counts[EDGE_ZMIN] = sum(1 for tx in range(tx0, tx1) if grid.is_road(tx, tz0 - 1))
    counts[EDGE_ZMAX] = sum(1 for tx in range(tx0, tx1) if grid.is_road(tx, tz1))
    spans = {EDGE_XMIN: tz1 - tz0, EDGE_XMAX: tz1 - tz0, EDGE_ZMIN: tx1 - tx0, EDGE_ZMAX: tx1 - tx0}
    for edge in (EDGE_ZMAX, EDGE_XMIN, EDGE_XMAX, EDGE_ZMIN):
        if counts[edge] > 0 and counts[edge] >= spans[edge] * 0.5:
            sides.append(edge)
    front = ""
    if sides:
        front = max(sides, key=lambda edge: counts[edge])
    return tuple(sides), front


def _fill_parcel(grid, rect, rng, preset, traits, rects, detail_rects, boxes, roofs, trees):
    tx0, tz0, tx1, tz1 = rect
    road_sides, front = _parcel_road_sides(grid, tx0, tz0, tx1, tz1)
    parcel = _Parcel(tx0, tz0, tx1, tz1, road_sides, front)
    x0, z0 = tx0 * TILE_M, tz0 * TILE_M
    x1, z1 = tx1 * TILE_M, tz1 * TILE_M
    area_tiles = parcel.w_tiles * parcel.d_tiles
    falloff = _parcel_falloff(grid, rect)

    # Landlocked interiors become quiet courtyard green, not blind buildings.
    if not road_sides:
        rects.append(Rect(MAT_PARK, x0, z0, x1, z1, _Y_PARCEL))
        _scatter_trees(rng, x0, z0, x1, z1, max(1, area_tiles // 3), preset.tree_density, trees)
        return

    roll = rng.random()
    if roll < min(0.8, preset.open_space + falloff * 0.22):
        if area_tiles >= 2 and rng.random() < 0.35:
            _make_plaza(rng, x0, z0, x1, z1, rects, trees)
        else:
            _make_park(rng, x0, z0, x1, z1, area_tiles, preset, rects, trees)
        return
    if roll < min(0.9, preset.open_space + falloff * 0.22 + preset.parking):
        _make_parking(x0, z0, x1, z1, parcel, rects, detail_rects)
        return

    _make_building(rng, parcel, preset, traits, falloff, rects, roofs, boxes, trees)


def _parcel_falloff(grid, rect):
    """Smooth 0..1 fade from the lot neighbourhood to the outer frame."""
    tx0, tz0, tx1, tz1 = rect
    x = (tx0 + tx1) * 0.5
    z = (tz0 + tz1) * 0.5
    distance = max(max(0.0, -x, x - grid.lot_w), max(0.0, -z, z - grid.lot_d))
    return min(1.0, max(0.0, (distance / grid.margin - 0.4) / 0.6))


def _tree(rng, x, z, base_y, trunk_h, canopy_h, radius, conifer=False):
    return Tree(
        x,
        z,
        base_y,
        trunk_h,
        canopy_h,
        radius,
        conifer,
        rng.uniform(0.0, math.tau),
        rng.uniform(0.92, 1.06),
    )


def _make_park(rng, x0, z0, x1, z1, area_tiles, preset, rects, trees):
    rects.append(Rect(MAT_PARK, x0, z0, x1, z1, _Y_PARCEL))
    _scatter_trees(rng, x0, z0, x1, z1, max(2, area_tiles), min(1.0, preset.tree_density + 0.2), trees)


def _make_plaza(rng, x0, z0, x1, z1, rects, trees):
    rects.append(Rect(MAT_PLAZA, x0, z0, x1, z1, _Y_PARCEL))
    # Formal tree rows along the two long edges.
    inset = 2.0
    step = 6.0
    n = max(2, int((x1 - x0 - 2 * inset) / step))
    for i in range(n + 1):
        x = x0 + inset + i * (x1 - x0 - 2 * inset) / max(1, n)
        for z in (z0 + inset, z1 - inset):
            trees.append(_tree(rng, x, z, _Y_PARCEL, 1.0, rng.uniform(2.2, 3.0), rng.uniform(1.2, 1.7)))


def _make_parking(x0, z0, x1, z1, parcel, rects, detail_rects):
    rects.append(Rect(MAT_PARKING, x0, z0, x1, z1, _Y_PARCEL))
    along_x = parcel.front in (EDGE_ZMIN, EDGE_ZMAX)
    edge0, edge1 = (x0, x1) if along_x else (z0, z1)
    cross0, cross1 = (z0, z1) if along_x else (x0, x1)
    margin = 1.2
    count = min(40, int(max(0.0, edge1 - edge0 - 2 * margin) / PARKING_STALL_M))
    if count < 2 or cross1 - cross0 < PARKING_DEPTH_M + 2 * margin:
        return

    run = count * PARKING_STALL_M
    start = (edge0 + edge1 - run) * 0.5
    line = 0.12

    def add_row(curb, inner):
        lo, hi = sorted((curb, inner))
        for index in range(count + 1):
            position = start + index * PARKING_STALL_M
            if along_x:
                detail_rects.append(Rect(MAT_MARKING, position - line / 2, lo, position + line / 2, hi, _Y_MARKING))
            else:
                detail_rects.append(Rect(MAT_MARKING, lo, position - line / 2, hi, position + line / 2, _Y_MARKING))
        if along_x:
            detail_rects.append(Rect(MAT_MARKING, start, inner - line / 2, start + run, inner + line / 2, _Y_MARKING))
        else:
            detail_rects.append(Rect(MAT_MARKING, inner - line / 2, start, inner + line / 2, start + run, _Y_MARKING))

    front_low = parcel.front in (EDGE_ZMIN, EDGE_XMIN)
    front_curb = cross0 + margin if front_low else cross1 - margin
    front_inner = front_curb + PARKING_DEPTH_M * (1 if front_low else -1)
    add_row(front_curb, front_inner)

    double_row = cross1 - cross0 >= 2 * margin + 2 * PARKING_DEPTH_M + PARKING_AISLE_M
    if double_row:
        rear_curb = cross1 - margin if front_low else cross0 + margin
        rear_inner = rear_curb - PARKING_DEPTH_M * (1 if front_low else -1)
        add_row(rear_curb, rear_inner)
        aisle0, aisle1 = sorted((front_inner, rear_inner))
    elif front_low:
        aisle0, aisle1 = front_inner, min(front_inner + PARKING_AISLE_M, cross1 - margin)
    else:
        aisle0, aisle1 = max(front_inner - PARKING_AISLE_M, cross0 + margin), front_inner

    if along_x:
        rects.append(Rect(MAT_PARKING_AISLE, start, aisle0, start + run, aisle1, _Y_PARKING_AISLE))
    else:
        rects.append(Rect(MAT_PARKING_AISLE, aisle0, start, aisle1, start + run, _Y_PARKING_AISLE))


def _scatter_trees(rng, x0, z0, x1, z1, count, density, trees):
    inset = 1.5
    if x1 - x0 <= 2 * inset or z1 - z0 <= 2 * inset:
        return
    for _ in range(count):
        if rng.random() > density:
            continue
        trees.append(
            _tree(
                rng,
                rng.uniform(x0 + inset, x1 - inset),
                rng.uniform(z0 + inset, z1 - inset),
                _Y_PARCEL,
                rng.uniform(0.8, 1.6),
                rng.uniform(2.4, 4.2),
                rng.uniform(1.3, 2.2),
                conifer=rng.random() < 0.3,
            )
        )


def _street_trees(grid, rng, preset, trees):
    """Rhythmic trees on the outer sidewalk edges of straight road tiles."""
    spacing = max(6.0, preset.street_tree_spacing)
    per_tile = max(1, int(TILE_M / spacing))
    for tx, tz in grid.road_tiles():
        n = grid.is_road(tx, tz - 1)
        s = grid.is_road(tx, tz + 1)
        w = grid.is_road(tx - 1, tz)
        e = grid.is_road(tx + 1, tz)
        straight_h = (w or e) and not (n or s)
        straight_v = (n or s) and not (w or e)
        if not (straight_h or straight_v):
            continue
        x, z = tx * TILE_M, tz * TILE_M
        for i in range(per_tile):
            if rng.random() > preset.tree_density:
                continue
            offset = (i + 0.5) * TILE_M / per_tile + rng.uniform(-0.8, 0.8)
            height = rng.uniform(2.2, 3.4)
            radius = rng.uniform(1.0, 1.5)
            if straight_h:
                trees.append(_tree(rng, x + offset, z + 1.5, _Y_SIDEWALK, 1.1, height, radius))
                trees.append(_tree(rng, x + offset, z + TILE_M - 1.5, _Y_SIDEWALK, 1.1, height, radius))
            else:
                trees.append(_tree(rng, x + 1.5, z + offset, _Y_SIDEWALK, 1.1, height, radius))
                trees.append(_tree(rng, x + TILE_M - 1.5, z + offset, _Y_SIDEWALK, 1.1, height, radius))


# --- cached close-detail dressing -----------------------------------------


def _tile_distance_to_lot(grid, tx, tz):
    dx = max(0, -tx, tx - grid.lot_w + 1)
    dz = max(0, -tz, tz - grid.lot_d + 1)
    return max(dx, dz)


def _rect_distance_to_lot(grid, rect):
    cx = (rect.x0 + rect.x1) * 0.5 / TILE_M
    cz = (rect.z0 + rect.z1) * 0.5 / TILE_M
    return max(max(0.0, -cx, cx - grid.lot_w), max(0.0, -cz, cz - grid.lot_d))


def _add_car(rng, x, z, along_x, detail_boxes):
    """Add a two-box, SC4-scale parked car."""
    length, width = 4.25, 1.82
    material = rng.choice((MAT_VEHICLE_RED, MAT_VEHICLE_BLUE, MAT_VEHICLE_NEUTRAL, MAT_VEHICLE_NEUTRAL))
    if along_x:
        x0, x1, z0, z1 = x - length / 2, x + length / 2, z - width / 2, z + width / 2
        cx0, cx1, cz0, cz1 = x - 1.25, x + 1.15, z - 0.76, z + 0.76
    else:
        x0, x1, z0, z1 = x - width / 2, x + width / 2, z - length / 2, z + length / 2
        cx0, cx1, cz0, cz1 = x - 0.76, x + 0.76, z - 1.25, z + 1.15
    detail_boxes.append(Box(material, x0, z0, x1, z1, 0.0, 0.62, rng.uniform(0.92, 1.08)))
    detail_boxes.append(Box(MAT_WINDOW, cx0, cz0, cx1, cz1, 0.62, 1.28, 0.72))


def _add_streetlamp(x, z, detail_boxes, height=4.2):
    detail_boxes.append(Box(MAT_DARK_METAL, x - 0.09, z - 0.09, x + 0.09, z + 0.09, 0.0, height, 0.82))
    detail_boxes.append(Box(MAT_LAMP, x - 0.24, z - 0.24, x + 0.24, z + 0.24, height - 0.12, height + 0.28))


def _add_bollard(x, z, detail_boxes):
    detail_boxes.append(Box(MAT_DARK_METAL, x - 0.10, z - 0.10, x + 0.10, z + 0.10, 0.0, 0.92, 0.88))


def _add_bench(x, z, along_x, detail_boxes):
    if along_x:
        detail_boxes.append(Box(MAT_BENCH, x - 1.0, z - 0.25, x + 1.0, z + 0.25, 0.42, 0.62))
        detail_boxes.append(Box(MAT_BENCH, x - 1.0, z + 0.18, x + 1.0, z + 0.30, 0.62, 1.15))
    else:
        detail_boxes.append(Box(MAT_BENCH, x - 0.25, z - 1.0, x + 0.25, z + 1.0, 0.42, 0.62))
        detail_boxes.append(Box(MAT_BENCH, x + 0.18, z - 1.0, x + 0.30, z + 1.0, 0.62, 1.15))


def _decorate_streets(grid, rng, style, detail_rects, detail_boxes, road_profiles=None):
    """Crosswalks, parked cars, lamps and signals around the edited lot."""
    activity = {
        STYLE_URBAN: 0.55,
        STYLE_SUBURBAN: 0.28,
        STYLE_INDUSTRIAL: 0.38,
        STYLE_CIVIC: 0.42,
        STYLE_RURAL: 0.12,
    }.get(style, 0.38)
    horizontal_profiles, vertical_profiles = _profile_maps(road_profiles)
    profiled = bool(road_profiles)
    for tx, tz in grid.road_tiles():
        distance = _tile_distance_to_lot(grid, tx, tz)
        if distance > 11:
            continue
        n, s = grid.is_road(tx, tz - 1), grid.is_road(tx, tz + 1)
        w, e = grid.is_road(tx - 1, tz), grid.is_road(tx + 1, tz)
        hkind = horizontal_profiles.get(tz)
        vkind = vertical_profiles.get(tx)
        if profiled:
            has_h = bool(hkind and (w or e))
            has_v = bool(vkind and (n or s))
            horizontal = has_h and not has_v
            vertical = has_v and not has_h
            intersection = has_h and has_v
        else:
            horizontal = (w or e) and not (n or s)
            vertical = (n or s) and not (w or e)
            intersection = (n or s) and (w or e)
            hkind = ROAD_STREET if horizontal or intersection else None
            vkind = ROAD_STREET if vertical or intersection else None
        x, z = tx * TILE_M, tz * TILE_M

        protected = intersection and {hkind, vkind} == {ROAD_AVENUE, ROAD_PEDESTRIAN}
        if protected and distance <= 8:
            # The promenade itself becomes a raised coloured table across the
            # avenue. Bollards guard both curbs and the centre refuge without
            # blocking the pedestrian desire line.
            if hkind == ROAD_PEDESTRIAN:
                detail_rects.append(Rect(MAT_PEDESTRIAN, x + 1.0, z + 6.2, x + 15.0, z + 9.8, _Y_MARKING + 0.008))
                for bx in (x + 1.8, x + 8.0, x + 14.2):
                    _add_bollard(bx, z + 5.9, detail_boxes)
                    _add_bollard(bx, z + 10.1, detail_boxes)
            else:
                detail_rects.append(Rect(MAT_PEDESTRIAN, x + 6.2, z + 1.0, x + 9.8, z + 15.0, _Y_MARKING + 0.008))
                for bz in (z + 1.8, z + 8.0, z + 14.2):
                    _add_bollard(x + 5.9, bz, detail_boxes)
                    _add_bollard(x + 10.1, bz, detail_boxes)
        elif intersection and distance <= 8:
            # Build one correctly oriented 9.6 m crossing on every connected
            # approach. Bars run in the pedestrian direction; stop bars run
            # across the corresponding traffic lane.
            stripe_w, stripe_step = 0.38, 0.68
            for i in range(4):
                near = 3.25 + i * stripe_step
                far = 12.75 - i * stripe_step - stripe_w
                if n:
                    detail_rects.append(Rect(MAT_MARKING, x + 3.2, z + near, x + 12.8, z + near + stripe_w, _Y_MARKING))
                if s:
                    detail_rects.append(Rect(MAT_MARKING, x + 3.2, z + far, x + 12.8, z + far + stripe_w, _Y_MARKING))
                if w:
                    detail_rects.append(Rect(MAT_MARKING, x + near, z + 3.2, x + near + stripe_w, z + 12.8, _Y_MARKING))
                if e:
                    detail_rects.append(Rect(MAT_MARKING, x + far, z + 3.2, x + far + stripe_w, z + 12.8, _Y_MARKING))
            stop_w = 0.24
            if n:
                detail_rects.append(Rect(MAT_MARKING, x + 3.1, z + 6.05, x + 12.9, z + 6.05 + stop_w, _Y_MARKING))
            if s:
                detail_rects.append(Rect(MAT_MARKING, x + 3.1, z + 9.71, x + 12.9, z + 9.71 + stop_w, _Y_MARKING))
            if w:
                detail_rects.append(Rect(MAT_MARKING, x + 6.05, z + 3.1, x + 6.05 + stop_w, z + 12.9, _Y_MARKING))
            if e:
                detail_rects.append(Rect(MAT_MARKING, x + 9.71, z + 3.1, x + 9.71 + stop_w, z + 12.9, _Y_MARKING))
            # Signals at opposing corners; their dark heads remain visible by
            # day while nearby streetlamps provide the night glow.
            for sx, sz in ((x + 2.25, z + 2.25), (x + 13.75, z + 13.75)):
                detail_boxes.append(Box(MAT_DARK_METAL, sx - 0.11, sz - 0.11, sx + 0.11, sz + 0.11, 0.0, 3.5))
                detail_boxes.append(Box(MAT_DARK_METAL, sx - 0.25, sz - 0.18, sx + 0.25, sz + 0.18, 3.2, 4.0))

        kind = hkind if horizontal else vkind if vertical else None
        motor_road = kind in (ROAD_STREET, ROAD_AVENUE)
        if motor_road and rng.random() < activity * max(0.25, 1.0 - distance / 15.0):
            if horizontal:
                _add_car(rng, x + 8.0 + rng.uniform(-1.0, 1.0), z + rng.choice((4.25, 11.75)), True, detail_boxes)
            else:
                _add_car(rng, x + rng.choice((4.25, 11.75)), z + 8.0 + rng.uniform(-1.0, 1.0), False, detail_boxes)

        if (horizontal or vertical) and (tx + tz) % 2 == 0 and rng.random() < 0.72:
            if horizontal:
                if kind == ROAD_AVENUE and horizontal_profiles.get(tz + 1) == ROAD_AVENUE:
                    lamp_z = z + 1.25
                elif kind == ROAD_AVENUE and horizontal_profiles.get(tz - 1) == ROAD_AVENUE:
                    lamp_z = z + 14.75
                else:
                    lamp_z = z + rng.choice((1.25, 14.75))
                _add_streetlamp(x + 8.0, lamp_z, detail_boxes)
            else:
                if kind == ROAD_AVENUE and vertical_profiles.get(tx + 1) == ROAD_AVENUE:
                    lamp_x = x + 1.25
                elif kind == ROAD_AVENUE and vertical_profiles.get(tx - 1) == ROAD_AVENUE:
                    lamp_x = x + 14.75
                else:
                    lamp_x = x + rng.choice((1.25, 14.75))
                _add_streetlamp(lamp_x, z + 8.0, detail_boxes)

        if kind == ROAD_BIKE and (tx + tz) % 2 == 0:
            if horizontal:
                for bx in (x + 4.0, x + 12.0):
                    _add_bollard(bx, z + 4.85, detail_boxes)
                    _add_bollard(bx, z + 11.15, detail_boxes)
            elif vertical:
                for bz in (z + 4.0, z + 12.0):
                    _add_bollard(x + 4.85, bz, detail_boxes)
                    _add_bollard(x + 11.15, bz, detail_boxes)
        elif kind == ROAD_PEDESTRIAN and (tx + tz) % 3 == 0:
            if horizontal:
                _add_bench(x + 8.0, z + 2.0, True, detail_boxes)
            elif vertical:
                _add_bench(x + 2.0, z + 8.0, False, detail_boxes)
        elif kind == ROAD_AVENUE and style in (STYLE_SUBURBAN, STYLE_CIVIC):
            # One planter per paired tile seam creates a planted median while
            # leaving several metres clear at every junction.
            if horizontal and horizontal_profiles.get(tz + 1) == ROAD_AVENUE:
                detail_boxes.append(Box(MAT_HEDGE, x + 3.0, z + 15.55, x + 13.0, z + 16.45, 0.0, 0.72))
            elif vertical and vertical_profiles.get(tx + 1) == ROAD_AVENUE:
                detail_boxes.append(Box(MAT_HEDGE, x + 15.55, z + 3.0, x + 16.45, z + 13.0, 0.0, 0.72))


def _decorate_open_spaces(grid, rng, style, rects, detail_rects, detail_boxes):
    """Give parks, plazas, yards and rural fields style-specific furniture."""
    candidates = [r for r in rects if r.material in (MAT_PARK, MAT_PLAZA, MAT_YARD, MAT_PARKING)]
    for rect in candidates:
        if _rect_distance_to_lot(grid, rect) > 9:
            continue
        w, d = rect.x1 - rect.x0, rect.z1 - rect.z0
        if min(w, d) < 5.0:
            continue
        cx, cz = (rect.x0 + rect.x1) * 0.5, (rect.z0 + rect.z1) * 0.5

        if rect.material == MAT_PARKING and rng.random() < 0.72:
            along_x = w >= d
            count = min(5, max(1, int((w if along_x else d) / 8.0)))
            for i in range(count):
                offset = (i + 0.5) / count - 0.5
                if along_x:
                    _add_car(rng, cx + offset * w * 0.72, cz - d * 0.22, True, detail_boxes)
                else:
                    _add_car(rng, cx - w * 0.22, cz + offset * d * 0.72, False, detail_boxes)
            continue

        if rect.material in (MAT_PARK, MAT_PLAZA) and rng.random() < 0.55:
            _add_bench(cx, rect.z0 + min(2.0, d * 0.22), w >= d, detail_boxes)
        if style == STYLE_CIVIC and rect.material == MAT_PLAZA and min(w, d) >= 11.0 and rng.random() < 0.55:
            size = min(4.5, min(w, d) * 0.28)
            detail_rects.append(Rect(MAT_WATER, cx - size, cz - size, cx + size, cz + size, _Y_MARKING))
            detail_boxes.append(Box(MAT_BRICK, cx - 0.65, cz - 0.65, cx + 0.65, cz + 0.65, 0.0, 2.8))
            for px, pz in ((cx - size - 1.0, cz), (cx + size + 1.0, cz)):
                detail_boxes.append(Box(MAT_HEDGE, px - 0.65, pz - 0.65, px + 0.65, pz + 0.65, 0.0, 0.8))
        elif style == STYLE_CIVIC and rect.material == MAT_PARK:
            path = min(1.8, min(w, d) * 0.14)
            detail_rects.append(Rect(MAT_PLAZA, rect.x0 + 1.0, cz - path / 2, rect.x1 - 1.0, cz + path / 2, _Y_MARKING))
        elif style == STYLE_RURAL and rect.material in (MAT_PARK, MAT_YARD) and min(w, d) >= 12.0:
            # Alternating crop strips are flat, cheap and immediately turn a
            # generic green parcel into agricultural context.
            count = min(8, max(3, int(min(w, d) / 3.5)))
            if w >= d:
                step = d / count
                for i in range(0, count, 2):
                    detail_rects.append(
                        Rect(
                            MAT_FIELD,
                            rect.x0 + 1.0,
                            rect.z0 + i * step,
                            rect.x1 - 1.0,
                            rect.z0 + (i + 1) * step,
                            _Y_MARKING,
                        )
                    )
            else:
                step = w / count
                for i in range(0, count, 2):
                    detail_rects.append(
                        Rect(
                            MAT_FIELD,
                            rect.x0 + i * step,
                            rect.z0 + 1.0,
                            rect.x0 + (i + 1) * step,
                            rect.z1 - 1.0,
                            _Y_MARKING,
                        )
                    )
        elif style == STYLE_SUBURBAN and rect.material == MAT_YARD and rng.random() < 0.35:
            detail_boxes.append(
                Box(
                    MAT_HEDGE,
                    rect.x0 + 0.5,
                    rect.z0 + 0.5,
                    rect.x1 - 0.5,
                    rect.z0 + 1.0,
                    0.0,
                    0.9,
                    rng.uniform(0.9, 1.08),
                )
            )
        elif style == STYLE_INDUSTRIAL and rect.material == MAT_YARD and min(w, d) >= 14.0 and rng.random() < 0.28:
            # Stacked container-like service blocks stay against the parcel
            # edge, outside the normal building setback.
            length = min(8.0, w - 2.0)
            detail_boxes.append(
                Box(
                    rng.choice((MAT_VEHICLE_RED, MAT_VEHICLE_BLUE, MAT_METAL)),
                    rect.x0 + 1.0,
                    rect.z0 + 0.8,
                    rect.x0 + 1.0 + length,
                    rect.z0 + 3.2,
                    0.0,
                    2.5,
                    0.82,
                )
            )


def _facade_quad(axis, plane, lo, hi, y0, y1, material, tint=1.0, reverse=False):
    if axis == "x":
        points = ((lo, y0, plane), (hi, y0, plane), (hi, y1, plane), (lo, y1, plane))
    else:
        points = ((plane, y0, lo), (plane, y0, hi), (plane, y1, hi), (plane, y1, lo))
    if reverse:
        points = tuple(reversed(points))
    return Quad(material, points, tint)


def _decorate_buildings(grid, rng, style, boxes, roofs, detail_boxes, detail_quads):
    """Bake daytime facades and a style-specific rooftop silhouette kit."""
    pitched = {(round(r.x0, 2), round(r.z0, 2), round(r.x1, 2), round(r.z1, 2)) for r in roofs}
    window_chance = {
        STYLE_URBAN: 0.82,
        STYLE_SUBURBAN: 0.48,
        STYLE_INDUSTRIAL: 0.28,
        STYLE_CIVIC: 0.72,
        STYLE_RURAL: 0.34,
    }.get(style, 0.62)

    for box in boxes:
        tx, tz = ((box.x0 + box.x1) * 0.5 / TILE_M, (box.z0 + box.z1) * 0.5 / TILE_M)
        distance = max(max(0.0, -tx, tx - grid.lot_w), max(0.0, -tz, tz - grid.lot_d))
        if distance > 10.5:
            continue
        base_y = max(0.0, box.y0)
        height = box.y1 - base_y
        if height < 2.8:
            continue
        faces = (
            ("x", box.z0 - 0.04, box.x0, box.x1, True),
            ("x", box.z1 + 0.04, box.x0, box.x1, False),
            ("z", box.x0 - 0.04, box.z0, box.z1, False),
            ("z", box.x1 + 0.04, box.z0, box.z1, True),
        )
        door_face = rng.randrange(4)
        floors = min(14, max(1, int((height - 0.8) / 3.1)))
        for face_index, (axis, plane, lo, hi, reverse) in enumerate(faces):
            span = hi - lo
            columns = min(14, max(1, int(span / (3.0 if style == STYLE_URBAN else 3.8))))
            spacing = span / columns
            width = min(1.35, spacing * 0.48)
            has_storefront = (
                box.y0 <= 0.05
                and style in (STYLE_URBAN, STYLE_MIXED, STYLE_CIVIC)
                and face_index < 2
                and face_index != door_face
                and span >= 8.0
                and rng.random() < 0.58
            )
            for floor in range(floors):
                if floor == 0 and has_storefront:
                    continue
                bottom = base_y + 1.0 + floor * 3.1
                top = min(box.y1 - 0.38, bottom + (1.18 if style == STYLE_CIVIC else 1.02))
                if top <= bottom:
                    continue
                for column in range(columns):
                    if rng.random() > window_chance:
                        continue
                    center = lo + (column + 0.5) * spacing
                    detail_quads.append(
                        _facade_quad(
                            axis,
                            plane,
                            center - width / 2,
                            center + width / 2,
                            bottom,
                            top,
                            MAT_WINDOW,
                            rng.uniform(0.88, 1.05),
                            reverse,
                        )
                    )

            # Doors anchor the otherwise repetitive grid at ground level.
            if box.y0 <= 0.05 and face_index == door_face:
                center = lo + span * rng.uniform(0.35, 0.65)
                detail_quads.append(
                    _facade_quad(
                        axis,
                        plane,
                        center - 0.72,
                        center + 0.72,
                        0.05,
                        min(2.55, box.y1 - 0.1),
                        MAT_DOOR,
                        reverse=reverse,
                    )
                )

            if has_storefront:
                detail_quads.append(
                    _facade_quad(
                        axis,
                        plane,
                        lo + 0.8,
                        hi - 0.8,
                        0.35,
                        min(2.85, box.y1 - 0.15),
                        MAT_STOREFRONT,
                        rng.uniform(0.9, 1.05),
                        reverse,
                    )
                )
                # A thin projecting awning reads strongly in the isometric view.
                mid = (lo + hi) * 0.5
                if axis == "x":
                    z1 = plane + (0.75 if plane > (box.z0 + box.z1) * 0.5 else -0.75)
                    detail_quads.append(
                        Quad(
                            MAT_AWNING,
                            (
                                (mid - 2.0, 2.75, plane),
                                (mid + 2.0, 2.75, plane),
                                (mid + 2.0, 2.55, z1),
                                (mid - 2.0, 2.55, z1),
                            ),
                        )
                    )
                else:
                    x1 = plane + (0.75 if plane > (box.x0 + box.x1) * 0.5 else -0.75)
                    detail_quads.append(
                        Quad(
                            MAT_AWNING,
                            (
                                (plane, 2.75, mid - 2.0),
                                (plane, 2.75, mid + 2.0),
                                (x1, 2.55, mid + 2.0),
                                (x1, 2.55, mid - 2.0),
                            ),
                        )
                    )

        footprint = (round(box.x0, 2), round(box.z0, 2), round(box.x1, 2), round(box.z1, 2))
        flat_roof = footprint not in pitched
        w, d = box.x1 - box.x0, box.z1 - box.z0
        if flat_roof and min(w, d) >= 5.0:
            if style in (STYLE_URBAN, STYLE_CIVIC, STYLE_MIXED) and rng.random() < 0.62:
                p, h = 0.24, 0.5
                detail_boxes.extend(
                    (
                        Box(MAT_BRICK, box.x0, box.z0, box.x1, box.z0 + p, box.y1, box.y1 + h, box.tint),
                        Box(MAT_BRICK, box.x0, box.z1 - p, box.x1, box.z1, box.y1, box.y1 + h, box.tint),
                        Box(MAT_BRICK, box.x0, box.z0 + p, box.x0 + p, box.z1 - p, box.y1, box.y1 + h, box.tint),
                        Box(MAT_BRICK, box.x1 - p, box.z0 + p, box.x1, box.z1 - p, box.y1, box.y1 + h, box.tint),
                    )
                )
            units = 0
            if style == STYLE_INDUSTRIAL:
                units = rng.randint(2, 4)
            elif style in (STYLE_URBAN, STYLE_CIVIC, STYLE_MIXED) and box.y1 >= 7.0:
                units = rng.randint(1, 3)
            for _ in range(units):
                uw = min(rng.uniform(1.0, 2.4), w * 0.28)
                ud = min(rng.uniform(0.9, 2.0), d * 0.28)
                ux = rng.uniform(box.x0 + 0.8, max(box.x0 + 0.8, box.x1 - uw - 0.8))
                uz = rng.uniform(box.z0 + 0.8, max(box.z0 + 0.8, box.z1 - ud - 0.8))
                detail_boxes.append(
                    Box(
                        MAT_METAL,
                        ux,
                        uz,
                        ux + uw,
                        uz + ud,
                        box.y1 + 0.02,
                        box.y1 + rng.uniform(0.65, 1.35),
                        rng.uniform(0.82, 1.05),
                    )
                )
            if style in (STYLE_SUBURBAN, STYLE_RURAL) and rng.random() < 0.45:
                cx = box.x0 + w * rng.uniform(0.22, 0.78)
                cz = box.z0 + d * rng.uniform(0.22, 0.78)
                detail_boxes.append(
                    Box(MAT_BRICK, cx - 0.35, cz - 0.35, cx + 0.35, cz + 0.35, box.y1, box.y1 + 1.8, 0.82)
                )
            if style == STYLE_INDUSTRIAL and rng.random() < 0.42:
                sx, sz = box.x0 + w * 0.72, box.z0 + d * 0.68
                detail_boxes.append(
                    Box(
                        MAT_DARK_METAL,
                        sx - 0.28,
                        sz - 0.28,
                        sx + 0.28,
                        sz + 0.28,
                        box.y1,
                        box.y1 + rng.uniform(3.0, 6.0),
                        0.8,
                    )
                )


# --- massing ---------------------------------------------------------------


def _make_building(rng, parcel, preset, traits, falloff, rects, roofs, boxes, trees):
    x0, z0 = parcel.tx0 * TILE_M, parcel.tz0 * TILE_M
    x1, z1 = parcel.tx1 * TILE_M, parcel.tz1 * TILE_M
    rects.append(Rect(MAT_YARD, x0, z0, x1, z1, _Y_PARCEL))

    front = parcel.front
    setback = traits.front_setback
    side = rng.uniform(*preset.side_gap)
    rear = max(side, setback * rng.uniform(0.8, 1.6))

    # Buildable envelope: front setback toward the street, looser rear.
    margins = {EDGE_XMIN: side, EDGE_XMAX: side, EDGE_ZMIN: side, EDGE_ZMAX: side}
    margins[front] = setback
    margins[_opposite(front)] = rear
    bx0, bz0 = x0 + margins[EDGE_XMIN], z0 + margins[EDGE_ZMIN]
    bx1, bz1 = x1 - margins[EDGE_XMAX], z1 - margins[EDGE_ZMAX]
    if bx1 - bx0 < 4.0 or bz1 - bz0 < 4.0:
        # Residual sliver: landscaping instead of a token box.
        _scatter_trees(rng, x0, z0, x1, z1, 2, preset.tree_density, trees)
        return

    corner = len(parcel.road_sides) >= 2
    height = rng.uniform(*preset.height) * traits.height_factor * (1.0 - falloff * 0.35)
    if corner:
        height = min(height * preset.corner_boost, preset.height[1] * traits.height_factor * preset.corner_boost)
    tint = rng.uniform(0.94, 1.04)

    archetype = traits.archetype if rng.random() < 0.65 else _weighted_choice(rng, preset.archetypes)
    envelope = (bx0, bz0, bx1, bz1)
    if corner and archetype in ("detached", "row", "slab") and min(bx1 - bx0, bz1 - bz0) >= 10.0:
        archetype = "lshape"

    if archetype == "detached":
        _mass_detached(rng, envelope, front, height, tint, preset, boxes, roofs, trees)
    elif archetype == "row":
        _mass_row(rng, envelope, front, height, tint, preset, boxes, roofs)
    elif archetype == "lshape":
        _mass_lshape(rng, envelope, front, height, tint, preset, boxes, roofs)
    elif archetype == "courtyard":
        _mass_courtyard(rng, envelope, height, tint, boxes)
    elif archetype == "podium":
        _mass_podium(rng, envelope, height, tint, boxes)
    elif archetype == "stepped":
        _mass_stepped(rng, envelope, front, height, tint, boxes)
    elif archetype == "shed":
        _mass_shed(rng, envelope, height, tint, preset, boxes, roofs)
    else:
        _mass_slab(rng, envelope, front, height, tint, boxes)


def _opposite(edge):
    return {EDGE_XMIN: EDGE_XMAX, EDGE_XMAX: EDGE_XMIN, EDGE_ZMIN: EDGE_ZMAX, EDGE_ZMAX: EDGE_ZMIN}.get(edge, EDGE_ZMIN)


def _clamp_span(rng, lo, hi, span):
    """A building depth/width within [lo, hi], never exceeding the envelope."""
    if span <= lo:
        return span
    return rng.uniform(lo, min(hi, span))


def _front_slab(envelope, front, depth):
    """Sub-envelope of ``depth`` metres hugging the front edge."""
    bx0, bz0, bx1, bz1 = envelope
    if front == EDGE_ZMIN:
        return bx0, bz0, bx1, min(bz1, bz0 + depth)
    if front == EDGE_ZMAX:
        return bx0, max(bz0, bz1 - depth), bx1, bz1
    if front == EDGE_XMIN:
        return bx0, bz0, min(bx1, bx0 + depth), bz1
    return max(bx0, bx1 - depth), bz0, bx1, bz1


def _maybe_roof(rng, x0, z0, x1, z1, top, tint, preset, boxes, roofs):
    """Pitched roof for small masses, else a flat top (drawn by the box)."""
    w, d = x1 - x0, z1 - z0
    if min(w, d) <= 14.0 and rng.random() < preset.pitched_roofs:
        axis = "x" if w >= d else "z"
        ridge = top + min(w, d) * rng.uniform(0.22, 0.34)
        roofs.append(Roof(x0, z0, x1, z1, top, ridge, axis, tint))
        return True
    return False


def _add_box(boxes, x0, z0, x1, z1, top, tint, y0=_Y_BUILDING_BASE):
    boxes.append(Box(MAT_WALL, x0, z0, x1, z1, y0, top, tint))


def _mass_detached(rng, envelope, front, height, tint, preset, boxes, roofs, trees):
    bx0, bz0, bx1, bz1 = envelope
    w = _clamp_span(rng, 7.0, 14.0, bx1 - bx0)
    d = _clamp_span(rng, 7.0, 12.0, bz1 - bz0)
    # Anchor to the front, centre along it.
    fx0, fz0, fx1, fz1 = _front_slab(envelope, front, d if front in (EDGE_ZMIN, EDGE_ZMAX) else w)
    cx = (fx0 + fx1) / 2.0
    cz = (fz0 + fz1) / 2.0
    x0, x1 = cx - w / 2.0, cx + w / 2.0
    z0, z1 = cz - d / 2.0, cz + d / 2.0
    x0, x1 = max(x0, bx0), min(x1, bx1)
    z0, z1 = max(z0, bz0), min(z1, bz1)
    top = min(height, 9.0)
    _add_box(boxes, x0, z0, x1, z1, top, tint)
    _maybe_roof(rng, x0, z0, x1, z1, top, tint, preset, boxes, roofs)
    # A backyard tree or two.
    if rng.random() < preset.tree_density:
        rx0, rz0, rx1, rz1 = _front_slab((bx0, bz0, bx1, bz1), _opposite(front), 4.0)
        if rx1 - rx0 > 2.0 and rz1 - rz0 > 2.0:
            trees.append(
                _tree(
                    rng,
                    rng.uniform(rx0 + 1, rx1 - 1),
                    rng.uniform(rz0 + 1, rz1 - 1),
                    _Y_PARCEL,
                    rng.uniform(0.8, 1.4),
                    rng.uniform(2.4, 3.8),
                    rng.uniform(1.2, 2.0),
                )
            )


def _mass_row(rng, envelope, front, height, tint, preset, boxes, roofs):
    """Row buildings: rhythmic segments along the frontage, shared walls
    suggested by narrow 0.3 m gaps (avoids coplanar z-fighting)."""
    depth = _clamp_span(rng, 8.0, 12.0, 1e9)
    x0, z0, x1, z1 = _front_slab(envelope, front, depth)
    along_x = front in (EDGE_ZMIN, EDGE_ZMAX)
    length = (x1 - x0) if along_x else (z1 - z0)
    seg = rng.uniform(7.0, 10.0)
    count = max(1, int(length / seg))
    gap = 0.3
    for i in range(count):
        lo = i * length / count
        hi = (i + 1) * length / count - (gap if i < count - 1 else 0.0)
        seg_h = height * rng.uniform(0.85, 1.15)
        seg_tint = tint * rng.uniform(0.97, 1.03)
        if along_x:
            sx0, sx1, sz0, sz1 = x0 + lo, x0 + hi, z0, z1
        else:
            sx0, sx1, sz0, sz1 = x0, x1, z0 + lo, z0 + hi
        _add_box(boxes, sx0, sz0, sx1, sz1, seg_h, seg_tint)
        _maybe_roof(rng, sx0, sz0, sx1, sz1, seg_h, seg_tint, preset, boxes, roofs)


def _mass_slab(rng, envelope, front, height, tint, boxes):
    depth = _clamp_span(rng, 10.0, 18.0, 1e9)
    x0, z0, x1, z1 = _front_slab(envelope, front, depth)
    _add_box(boxes, x0, z0, x1, z1, height, tint)


def _mass_lshape(rng, envelope, front, height, tint, preset, boxes, roofs):
    bx0, bz0, bx1, bz1 = envelope
    wing = rng.uniform(6.0, 10.0)
    # Front bar along the frontage plus a perpendicular wing on one side.
    x0, z0, x1, z1 = _front_slab(envelope, front, wing)
    _add_box(boxes, x0, z0, x1, z1, height, tint)
    _maybe_roof(rng, x0, z0, x1, z1, height, tint, preset, boxes, roofs)
    h2 = height * rng.uniform(0.75, 0.95)
    if front in (EDGE_ZMIN, EDGE_ZMAX):
        wx1 = min(bx0 + wing, bx1)
        wz0, wz1 = (z1, bz1) if front == EDGE_ZMIN else (bz0, z0)
        if wz1 - wz0 > 3.0:
            _add_box(boxes, bx0, wz0, wx1, wz1, h2, tint)
    else:
        wz1 = min(bz0 + wing, bz1)
        wx0, wx1 = (x1, bx1) if front == EDGE_XMIN else (bx0, x0)
        if wx1 - wx0 > 3.0:
            _add_box(boxes, wx0, bz0, wx1, wz1, h2, tint)


def _mass_courtyard(rng, envelope, height, tint, boxes):
    bx0, bz0, bx1, bz1 = envelope
    wing = rng.uniform(6.0, 9.0)
    if bx1 - bx0 < 2.5 * wing or bz1 - bz0 < 2.5 * wing:
        _add_box(boxes, bx0, bz0, bx1, bz1, height, tint)
        return
    h = height
    _add_box(boxes, bx0, bz0, bx1, bz0 + wing, h, tint)  # north bar
    _add_box(boxes, bx0, bz1 - wing, bx1, bz1, h * rng.uniform(0.9, 1.05), tint)  # south bar
    _add_box(boxes, bx0, bz0 + wing, bx0 + wing, bz1 - wing, h * 0.92, tint)  # west bar
    _add_box(boxes, bx1 - wing, bz0 + wing, bx1, bz1 - wing, h * 0.92, tint)  # east bar


def _mass_podium(rng, envelope, height, tint, boxes):
    bx0, bz0, bx1, bz1 = envelope
    podium_h = min(10.0, height * 0.35)
    _add_box(boxes, bx0, bz0, bx1, bz1, podium_h, tint)
    inset_x = (bx1 - bx0) * rng.uniform(0.18, 0.3)
    inset_z = (bz1 - bz0) * rng.uniform(0.18, 0.3)
    _add_box(
        boxes,
        bx0 + inset_x,
        bz0 + inset_z,
        bx1 - inset_x,
        bz1 - inset_z,
        height * rng.uniform(1.1, 1.4),
        tint * 1.02,
        podium_h + 0.02,
    )


def _mass_stepped(rng, envelope, front, height, tint, boxes):
    x0, z0, x1, z1 = _front_slab(envelope, front, _clamp_span(rng, 10.0, 16.0, 1e9))
    _add_box(boxes, x0, z0, x1, z1, height, tint)
    inset = min((x1 - x0), (z1 - z0)) * 0.22
    if inset > 1.5:
        _add_box(
            boxes, x0 + inset, z0 + inset, x1 - inset, z1 - inset, height * rng.uniform(1.25, 1.5), tint, height + 0.02
        )


def _mass_shed(rng, envelope, height, tint, preset, boxes, roofs):
    bx0, bz0, bx1, bz1 = envelope
    h = min(height, rng.uniform(5.0, 9.0))
    _add_box(boxes, bx0, bz0, bx1, bz1, h, tint)
    # Shallow ridge along the long axis.
    w, d = bx1 - bx0, bz1 - bz0
    if rng.random() < preset.pitched_roofs:
        axis = "x" if w >= d else "z"
        roofs.append(Roof(bx0, bz0, bx1, bz1, h, h + min(w, d) * 0.12, axis, tint))


# ---------------------------------------------------------------------------
# Mesh building (pure numpy; consumed by the GL layer as-is)
# ---------------------------------------------------------------------------

# Architectural-model palette (sRGB floats). Opaque throughout: translucency
# would need depth sorting and costs overdraw for no compositional gain.
_PALETTE = {
    MAT_GROUND: (0.75, 0.75, 0.74),
    MAT_ROAD: (0.47, 0.47, 0.48),
    MAT_SIDEWALK: (0.68, 0.675, 0.66),
    MAT_PARK: (0.60, 0.63, 0.58),
    MAT_PLAZA: (0.71, 0.705, 0.69),
    MAT_PARKING: (0.52, 0.52, 0.515),
    MAT_PARKING_AISLE: (0.475, 0.48, 0.485),
    MAT_YARD: (0.68, 0.69, 0.66),
    MAT_WALL: (0.86, 0.86, 0.85),
    MAT_ROOF: (0.68, 0.69, 0.70),
    MAT_ROOF_PITCHED: (0.65, 0.63, 0.62),
    MAT_TRUNK: (0.46, 0.43, 0.40),
    MAT_CANOPY: (0.56, 0.60, 0.54),
    MAT_MARKING: (0.76, 0.76, 0.75),
    MAT_CONTACT: (0.46, 0.46, 0.45),
    MAT_CURB: (0.62, 0.62, 0.61),
    MAT_WINDOW: (0.34, 0.43, 0.48),
    MAT_DOOR: (0.34, 0.31, 0.28),
    MAT_STOREFRONT: (0.39, 0.49, 0.53),
    MAT_AWNING: (0.63, 0.35, 0.30),
    MAT_METAL: (0.59, 0.62, 0.63),
    MAT_DARK_METAL: (0.25, 0.27, 0.28),
    MAT_BRICK: (0.61, 0.53, 0.48),
    MAT_HEDGE: (0.39, 0.49, 0.35),
    MAT_FIELD: (0.62, 0.65, 0.43),
    MAT_VEHICLE_RED: (0.57, 0.25, 0.23),
    MAT_VEHICLE_BLUE: (0.25, 0.37, 0.52),
    MAT_VEHICLE_NEUTRAL: (0.53, 0.54, 0.53),
    MAT_LAMP: (0.83, 0.78, 0.61),
    MAT_BENCH: (0.43, 0.34, 0.27),
    MAT_WATER: (0.39, 0.55, 0.61),
    MAT_HORIZON: (0.38, 0.41, 0.44),
    MAT_BIKE_LANE: (0.34, 0.53, 0.46),
    MAT_PEDESTRIAN: (0.69, 0.65, 0.57),
    MAT_ISLAND: (0.62, 0.61, 0.57),
}

# Restrained per-style accents. Roads and sidewalks remain consistent across
# lots; only the model materials shift enough to communicate character.
_STYLE_PALETTES = {
    STYLE_URBAN: {
        MAT_WALL: (0.87, 0.88, 0.89),
        MAT_ROOF: (0.66, 0.69, 0.72),
        MAT_ROOF_PITCHED: (0.63, 0.65, 0.68),
        MAT_PLAZA: (0.75, 0.74, 0.72),
    },
    STYLE_SUBURBAN: {
        MAT_WALL: (0.90, 0.875, 0.82),
        MAT_ROOF: (0.69, 0.65, 0.61),
        MAT_ROOF_PITCHED: (0.64, 0.57, 0.52),
        MAT_PARK: (0.58, 0.67, 0.53),
        MAT_CANOPY: (0.51, 0.62, 0.47),
    },
    STYLE_INDUSTRIAL: {
        MAT_WALL: (0.81, 0.83, 0.84),
        MAT_ROOF: (0.61, 0.64, 0.66),
        MAT_ROOF_PITCHED: (0.59, 0.61, 0.62),
        MAT_YARD: (0.67, 0.67, 0.64),
        MAT_PARKING: (0.54, 0.55, 0.56),
    },
    STYLE_CIVIC: {
        MAT_WALL: (0.91, 0.90, 0.86),
        MAT_ROOF: (0.70, 0.72, 0.73),
        MAT_PLAZA: (0.79, 0.77, 0.72),
        MAT_PARK: (0.57, 0.67, 0.53),
        MAT_CANOPY: (0.50, 0.61, 0.47),
    },
    STYLE_RURAL: {
        MAT_GROUND: (0.76, 0.76, 0.70),
        MAT_WALL: (0.89, 0.85, 0.78),
        MAT_ROOF: (0.66, 0.61, 0.56),
        MAT_ROOF_PITCHED: (0.61, 0.53, 0.47),
        MAT_PARK: (0.57, 0.66, 0.51),
        MAT_YARD: (0.67, 0.70, 0.60),
        MAT_CANOPY: (0.49, 0.60, 0.45),
    },
}


_SEASON_PALETTES = {
    SEASON_SPRING: {
        MAT_CANOPY: (0.55, 0.68, 0.48),
        MAT_PARK: (0.61, 0.69, 0.54),
        MAT_HEDGE: (0.48, 0.60, 0.41),
    },
    SEASON_AUTUMN: {
        MAT_CANOPY: (0.70, 0.49, 0.28),
        MAT_PARK: (0.63, 0.61, 0.44),
        MAT_HEDGE: (0.54, 0.48, 0.29),
        MAT_FIELD: (0.69, 0.55, 0.31),
    },
    SEASON_WINTER: {
        MAT_CANOPY: (0.48, 0.46, 0.43),
        MAT_PARK: (0.61, 0.61, 0.56),
        MAT_YARD: (0.64, 0.64, 0.59),
        MAT_HEDGE: (0.42, 0.44, 0.38),
        MAT_FIELD: (0.62, 0.60, 0.52),
    },
}


def _palette_for_style(style, season=SEASON_SUMMER):
    palette = dict(_PALETTE)
    palette.update(_STYLE_PALETTES.get(style, ()))
    palette.update(_SEASON_PALETTES.get(season, ()))
    # Retain just enough chroma to distinguish parks and style presets while
    # keeping the editable lot decisively more colourful than its context.
    for material, color in palette.items():
        grey = sum(color) / 3.0
        palette[material] = tuple(grey + (channel - grey) * 0.4 for channel in color)
    return palette


_TRI_ORDER = numpy.asarray((0, 1, 2, 0, 2, 3), dtype=numpy.intp)


@dataclass(frozen=True)
class ContextMesh:
    """Lot-centred, pre-interleaved triangle batches for allocation-free draw."""

    vertices: numpy.ndarray
    detail_vertices: numpy.ndarray
    normals: numpy.ndarray
    detail_normals: numpy.ndarray
    shadow_vertices: numpy.ndarray
    detail_shadow_vertices: numpy.ndarray
    night_vertices: numpy.ndarray

    @property
    def positions(self):
        return self.vertices[:, :3]

    @property
    def colors(self):
        return self.vertices[:, 3:7]

    @property
    def detail_positions(self):
        return self.detail_vertices[:, :3]

    @property
    def detail_colors(self):
        return self.detail_vertices[:, 3:7]

    @property
    def vertex_count(self):
        return len(self.vertices) + len(self.detail_vertices) + len(self.night_vertices)


def scene_stats(scene):
    """Diagnostic counts for logging/tests."""
    return {
        "rects": len(scene.rects) + len(scene.detail_rects),
        "boxes": len(scene.boxes),
        "roofs": len(scene.roofs),
        "trees": len(scene.trees),
        "detail_boxes": len(scene.detail_boxes),
        "facade_quads": len(scene.detail_quads),
        "style": scene.style,
        "season": scene.season,
        "seed": scene.seed,
        "margin": scene.margin,
    }


def _empty_arrays():
    return (
        numpy.zeros((0, 3), dtype=numpy.float32),
        numpy.zeros((0, 4), dtype=numpy.float32),
        numpy.zeros((0, 3), dtype=numpy.float32),
    )


def _rect_arrays(rects, center_x, center_z, palette):
    if not rects:
        return _empty_arrays()
    data = numpy.asarray([(r.x0, r.z0, r.x1, r.z1, r.y) for r in rects], dtype=numpy.float64)
    color = numpy.asarray([palette[r.material] + (1.0,) for r in rects], dtype=numpy.float64)
    x0, z0, x1, z1, y = (data[:, i] for i in range(5))
    corners = numpy.stack(
        [
            numpy.stack([x0, y, z0], axis=1),
            numpy.stack([x1, y, z0], axis=1),
            numpy.stack([x1, y, z1], axis=1),
            numpy.stack([x0, y, z1], axis=1),
        ],
        axis=1,
    )
    positions = corners[:, _TRI_ORDER, :].reshape(-1, 3)
    colors = numpy.repeat(color, 6, axis=0)
    normals = numpy.empty_like(positions)
    normals[:] = (0.0, 1.0, 0.0)
    positions[:, 0] -= center_x
    positions[:, 2] -= center_z
    return positions.astype(numpy.float32), colors.astype(numpy.float32), normals.astype(numpy.float32)


def _quad_arrays(quads, center_x, center_z, palette):
    if not quads:
        return _empty_arrays()
    positions = []
    colors = []
    normals = []
    for quad in quads:
        color = tuple(min(1.0, c * quad.tint) for c in palette[quad.material]) + (1.0,)
        normal = _face_normal(quad.points[0], quad.points[1], quad.points[2])
        for index in _TRI_ORDER:
            positions.append(quad.points[index])
            colors.append(color)
            normals.append(normal)
    positions = numpy.asarray(positions, dtype=numpy.float32)
    positions[:, 0] -= center_x
    positions[:, 2] -= center_z
    return positions, numpy.asarray(colors, dtype=numpy.float32), numpy.asarray(normals, dtype=numpy.float32)


def _box_arrays(boxes, center_x, center_z, palette):
    if not boxes:
        return _empty_arrays()
    data = numpy.asarray([(b.x0, b.z0, b.x1, b.z1, b.y0, b.y1) for b in boxes], dtype=numpy.float64)
    base = numpy.asarray([tuple(c * b.tint for c in palette[b.material]) + (1.0,) for b in boxes], dtype=numpy.float64)
    top_color = numpy.asarray(
        [
            tuple(c * b.tint for c in palette[MAT_ROOF if b.material == MAT_WALL else b.material]) + (1.0,)
            for b in boxes
        ],
        dtype=numpy.float64,
    )
    x0, z0, x1, z1, y0, y1 = (data[:, i] for i in range(6))

    def face(a, b, c, d, color, normal):
        corners = numpy.stack([a, b, c, d], axis=1)
        pos = corners[:, _TRI_ORDER, :].reshape(-1, 3)
        col = numpy.repeat(color, 6, axis=0)
        normals = numpy.empty_like(pos)
        normals[:] = normal
        return pos, col, normals

    def p(x, y, z):
        return numpy.stack([x, y, z], axis=1)

    faces = [
        # Top face uses the roof colour so flat tops read as roofs.
        face(p(x0, y1, z0), p(x1, y1, z0), p(x1, y1, z1), p(x0, y1, z1), top_color, (0, 1, 0)),
        face(p(x0, y0, z1), p(x1, y0, z1), p(x1, y1, z1), p(x0, y1, z1), base, (0, 0, 1)),
        face(p(x1, y0, z0), p(x0, y0, z0), p(x0, y1, z0), p(x1, y1, z0), base, (0, 0, -1)),
        face(p(x1, y0, z1), p(x1, y0, z0), p(x1, y1, z0), p(x1, y1, z1), base, (1, 0, 0)),
        face(p(x0, y0, z0), p(x0, y0, z1), p(x0, y1, z1), p(x0, y1, z0), base, (-1, 0, 0)),
    ]
    positions = numpy.concatenate([f[0] for f in faces])
    colors = numpy.concatenate([f[1] for f in faces])
    normals = numpy.concatenate([f[2] for f in faces])
    positions[:, 0] -= center_x
    positions[:, 2] -= center_z
    return positions.astype(numpy.float32), colors.astype(numpy.float32), normals.astype(numpy.float32)


def _face_normal(a, b, c, outward=None):
    abx, aby, abz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    acx, acy, acz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx = aby * acz - abz * acy
    ny = abz * acx - abx * acz
    nz = abx * acy - aby * acx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length:
        nx, ny, nz = nx / length, ny / length, nz / length
    if outward is not None and nx * outward[0] + ny * outward[1] + nz * outward[2] < 0.0:
        nx, ny, nz = -nx, -ny, -nz
    return nx, ny, nz


def _roof_arrays(roofs, center_x, center_z, palette):
    positions = []
    colors = []
    normals = []
    # Kept below the smallest side gap (0.3 m) so eaves never cross into a
    # neighbouring row-house segment.
    overhang = 0.25
    for roof in roofs:
        color = tuple(c * roof.tint for c in palette[MAT_ROOF_PITCHED]) + (1.0,)
        x0, z0 = roof.x0 - overhang, roof.z0 - overhang
        x1, z1 = roof.x1 + overhang, roof.z1 + overhang
        e, r = roof.eave_y, roof.ridge_y
        if roof.axis == "x":
            mz = (z0 + z1) / 2.0
            quads = (
                ((x0, e, z0), (x1, e, z0), (x1, r, mz), (x0, r, mz)),
                ((x0, r, mz), (x1, r, mz), (x1, e, z1), (x0, e, z1)),
            )
            tris = (
                ((x0, e, z0), (x0, e, z1), (x0, r, mz)),
                ((x1, e, z0), (x1, e, z1), (x1, r, mz)),
            )
        else:
            mx = (x0 + x1) / 2.0
            quads = (
                ((x0, e, z0), (x0, e, z1), (mx, r, z1), (mx, r, z0)),
                ((mx, r, z0), (mx, r, z1), (x1, e, z1), (x1, e, z0)),
            )
            tris = (
                ((x0, e, z0), (x1, e, z0), (mx, r, z0)),
                ((x0, e, z1), (x1, e, z1), (mx, r, z1)),
            )
        for a, b, c, d in quads:
            normal = _face_normal(a, b, c, (0.0, 1.0, 0.0))
            for idx in _TRI_ORDER:
                positions.append((a, b, c, d)[idx])
                colors.append(color)
                normals.append(normal)
        for a, b, c in tris:
            center = tuple((a[i] + b[i] + c[i]) / 3.0 for i in range(3))
            outward = (center[0] - (x0 + x1) / 2.0, 0.0, center[2] - (z0 + z1) / 2.0)
            normal = _face_normal(a, b, c, outward)
            for point in (a, b, c):
                positions.append(point)
                colors.append(color)
                normals.append(normal)
    if not positions:
        return _empty_arrays()
    positions = numpy.asarray(positions, dtype=numpy.float32)
    positions[:, 0] -= center_x
    positions[:, 2] -= center_z
    return positions, numpy.asarray(colors, dtype=numpy.float32), numpy.asarray(normals, dtype=numpy.float32)


def _tree_arrays(trees, center_x, center_z, palette, season=SEASON_SUMMER):
    """Faceted model trees: tapered trunks and six-sided crowns/conifers."""
    positions = []
    colors = []
    normals = []
    trunk = palette[MAT_TRUNK]
    canopy = palette[MAT_CANOPY]

    def add_face(points, color, outward):
        normal = _face_normal(points[0], points[1], points[2], outward)
        indices = _TRI_ORDER if len(points) == 4 else range(3)
        for index in indices:
            positions.append(points[index])
            colors.append(color)
            normals.append(normal)

    for tree in trees:
        x, z, y = tree.x, tree.z, tree.base_y
        th = tree.trunk_h
        trunk_color = trunk + (1.0,)
        canopy_base = (0.47, 0.55, 0.43) if tree.conifer else canopy
        canopy_color = tuple(min(1.0, channel * tree.tint) for channel in canopy_base) + (1.0,)
        bottom = []
        top = []
        for i in range(4):
            angle = tree.rotation + math.tau * i / 4.0
            bottom.append((x + math.cos(angle) * 0.20, y, z + math.sin(angle) * 0.20))
            top.append((x + math.cos(angle) * 0.13, y + th, z + math.sin(angle) * 0.13))
        for i in range(4):
            a, b = bottom[i], bottom[(i + 1) % 4]
            c, d = top[(i + 1) % 4], top[i]
            outward = ((a[0] + b[0]) / 2.0 - x, 0.0, (a[2] + b[2]) / 2.0 - z)
            add_face((a, b, c, d), trunk_color, outward)

        if season == SEASON_WINTER and not tree.conifer:
            # Bare deciduous crowns: six tapered branch planes retain a useful
            # winter silhouette without introducing a separate primitive type.
            branch_color = tuple(channel * 0.92 for channel in trunk) + (1.0,)
            for i in range(6):
                angle = tree.rotation + math.tau * i / 6.0
                tangent = (-math.sin(angle) * 0.10, math.cos(angle) * 0.10)
                start = (x, y + th * 0.72, z)
                end = (
                    x + math.cos(angle) * tree.radius * 0.82,
                    y + th + tree.canopy_h * (0.48 + 0.07 * (i % 3)),
                    z + math.sin(angle) * tree.radius * 0.82,
                )
                add_face(
                    (
                        (start[0] + tangent[0], start[1], start[2] + tangent[1]),
                        (start[0] - tangent[0], start[1], start[2] - tangent[1]),
                        end,
                    ),
                    branch_color,
                    (math.cos(angle), 0.2, math.sin(angle)),
                )
            continue

        seasonal_scale = 0.84 if season == SEASON_SPRING and not tree.conifer else 1.0
        r = tree.radius * seasonal_scale
        base_y = y + th
        top_y = base_y + tree.canopy_h * seasonal_scale
        if tree.conifer:
            tiers = (
                (base_y + tree.canopy_h * 0.05, r, base_y + tree.canopy_h * 0.72),
                (base_y + tree.canopy_h * 0.36, r * 0.72, top_y),
            )
            for ring_y, ring_r, apex_y in tiers:
                ring = [
                    (
                        x + math.cos(tree.rotation + math.tau * i / 6.0) * ring_r,
                        ring_y,
                        z + math.sin(tree.rotation + math.tau * i / 6.0) * ring_r,
                    )
                    for i in range(6)
                ]
                apex = (x, apex_y, z)
                for i in range(6):
                    a, b = ring[i], ring[(i + 1) % 6]
                    outward = ((a[0] + b[0]) / 2.0 - x, 0.25, (a[2] + b[2]) / 2.0 - z)
                    add_face((a, b, apex), canopy_color, outward)
        else:
            mid_y = base_y + tree.canopy_h * 0.48
            ring = []
            for i in range(6):
                angle = tree.rotation + math.tau * i / 6.0
                ring_r = r * (0.92 if i % 2 else 1.04)
                ring.append((x + math.cos(angle) * ring_r, mid_y, z + math.sin(angle) * ring_r))
            lower = (
                x + math.cos(tree.rotation + 0.7) * r * 0.08,
                base_y + tree.canopy_h * 0.04,
                z + math.sin(tree.rotation + 0.7) * r * 0.08,
            )
            upper = (
                x + math.cos(tree.rotation + 1.8) * r * 0.06,
                top_y,
                z + math.sin(tree.rotation + 1.8) * r * 0.06,
            )
            for i in range(6):
                a, b = ring[i], ring[(i + 1) % 6]
                outward = ((a[0] + b[0]) / 2.0 - x, 0.3, (a[2] + b[2]) / 2.0 - z)
                add_face((a, b, upper), canopy_color, outward)
                add_face((b, a, lower), canopy_color, outward)
    if not positions:
        return _empty_arrays()
    positions = numpy.asarray(positions, dtype=numpy.float32)
    positions[:, 0] -= center_x
    positions[:, 2] -= center_z
    return positions, numpy.asarray(colors, dtype=numpy.float32), numpy.asarray(normals, dtype=numpy.float32)


def _window_arrays(scene, center_x, center_z):
    """A bounded deterministic set of emissive façade panes for night mode."""
    rng = random.Random(scene.seed ^ 0x57494E444F5753)
    chance = {
        STYLE_URBAN: 0.34,
        STYLE_SUBURBAN: 0.20,
        STYLE_INDUSTRIAL: 0.12,
        STYLE_CIVIC: 0.26,
        STYLE_RURAL: 0.12,
    }.get(scene.style, 0.25)
    positions = []
    colors = []
    candidates = [quad for quad in scene.detail_quads if quad.material in (MAT_WINDOW, MAT_STOREFRONT)]
    rng.shuffle(candidates)
    for count, quad in enumerate(candidates):
        pane_chance = 0.65 if quad.material == MAT_STOREFRONT else chance
        if rng.random() >= pane_chance:
            continue
        color = rng.choice(((0.94, 0.80, 0.53, 1.0), (0.77, 0.84, 0.82, 1.0)))
        for index in _TRI_ORDER:
            point = quad.points[index]
            positions.append((point[0] - center_x, point[1], point[2] - center_z))
            colors.append(color)
        if len(positions) // 6 >= MAX_LIT_WINDOWS:
            break
    return numpy.asarray(positions, dtype=numpy.float32).reshape(-1, 3), numpy.asarray(
        colors, dtype=numpy.float32
    ).reshape(-1, 4)


def _distance_fade(positions, colors, scene, palette):
    """Blend the outer model board and silhouettes into the 3D backdrop."""
    if not len(positions):
        return colors
    half_w = scene.lot_w * TILE_M * 0.5
    half_d = scene.lot_d * TILE_M * 0.5
    dx = numpy.maximum(0.0, numpy.abs(positions[:, 0]) - half_w)
    dz = numpy.maximum(0.0, numpy.abs(positions[:, 2]) - half_d)
    distance = numpy.maximum(dx, dz) / max(1.0, scene.margin * TILE_M)
    amount = numpy.clip((distance - 0.52) / 0.48, 0.0, 1.0)
    amount = amount * amount * (3.0 - 2.0 * amount)
    faded = colors.copy()
    target = numpy.asarray(palette[MAT_HORIZON], dtype=numpy.float32)
    faded[:, :3] = faded[:, :3] * (1.0 - amount[:, None]) + target * amount[:, None]
    return faded


def _trim_triangles(*arrays, limit):
    """Trim parallel triangle soups to a shared vertex limit."""
    count = min(len(arrays[0]), max(0, int(limit)))
    count -= count % 3
    return tuple(array[:count] for array in arrays)


def build_context_mesh(scene):
    """Convert a scene to lot-centred float32 triangle soups.

    Two batches: ``positions/colors`` always drawn; ``detail_*`` (trees,
    lane markings, parking stalls) skipped at far zoom -- the cheap LOD.
    Arrays are built once here and must not be rebuilt per frame.
    """
    center_x = scene.lot_w * TILE_M / 2.0
    center_z = scene.lot_d * TILE_M / 2.0
    palette = _palette_for_style(scene.style, scene.season)
    rect_pos, rect_col, rect_norm = _rect_arrays(scene.rects, center_x, center_z, palette)
    box_pos, box_col, box_norm = _box_arrays(scene.boxes, center_x, center_z, palette)
    roof_pos, roof_col, roof_norm = _roof_arrays(scene.roofs, center_x, center_z, palette)
    tree_pos, tree_col, tree_norm = _tree_arrays(scene.trees, center_x, center_z, palette, scene.season)
    mark_pos, mark_col, mark_norm = _rect_arrays(scene.detail_rects, center_x, center_z, palette)
    facade_pos, facade_col, facade_norm = _quad_arrays(scene.detail_quads, center_x, center_z, palette)
    fitting_pos, fitting_col, fitting_norm = _box_arrays(scene.detail_boxes, center_x, center_z, palette)
    window_pos, window_col = _window_arrays(scene, center_x, center_z)
    lamp_palette = dict(palette)
    lamp_palette[MAT_LAMP] = (1.0, 0.82, 0.48)
    lamp_pos, lamp_col, _lamp_norm = _box_arrays(
        [box for box in scene.detail_boxes if box.material == MAT_LAMP][:MAX_NIGHT_LIGHTS],
        center_x,
        center_z,
        lamp_palette,
    )

    def interleave(positions, colors):
        vertices = numpy.zeros((len(positions), 9), dtype=numpy.float32)
        vertices[:, :3] = positions
        vertices[:, 3:7] = colors
        vertices.setflags(write=False)
        return vertices

    positions = numpy.concatenate((rect_pos, box_pos, roof_pos))
    colors = numpy.concatenate((rect_col, box_col, roof_col))
    normals = numpy.concatenate((rect_norm, box_norm, roof_norm))
    detail_positions = numpy.concatenate((mark_pos, facade_pos, fitting_pos, tree_pos))
    detail_colors = numpy.concatenate((mark_col, facade_col, fitting_col, tree_col))
    detail_normals = numpy.concatenate((mark_norm, facade_norm, fitting_norm, tree_norm))
    night_positions = numpy.concatenate((window_pos, lamp_pos))
    night_colors = numpy.concatenate((window_col, lamp_col))

    colors = _distance_fade(positions, colors, scene, palette)
    detail_colors = _distance_fade(detail_positions, detail_colors, scene, palette)

    # Base geometry has priority, followed by close detail and then emissive
    # overlays. The trim is a final guard for pathological lot dimensions; all
    # normal scenes remain below the raised budget without touching it.
    positions, colors, normals = _trim_triangles(positions, colors, normals, limit=MAX_CONTEXT_VERTICES)
    remaining = MAX_CONTEXT_VERTICES - len(positions)
    detail_positions, detail_colors, detail_normals = _trim_triangles(
        detail_positions, detail_colors, detail_normals, limit=remaining
    )
    remaining -= len(detail_positions)
    night_positions, night_colors = _trim_triangles(night_positions, night_colors, limit=remaining)
    normals.setflags(write=False)
    detail_normals.setflags(write=False)
    vertices = interleave(positions, colors)
    detail_vertices = interleave(detail_positions, detail_colors)
    night_vertices = interleave(night_positions, night_colors)
    return ContextMesh(
        vertices=vertices,
        detail_vertices=detail_vertices,
        normals=normals,
        detail_normals=detail_normals,
        # Views into the two immutable draw arrays: flat surfaces receive
        # shadows but never cast them, so no duplicate caster mesh is stored.
        shadow_vertices=vertices[len(rect_pos) :],
        detail_shadow_vertices=detail_vertices[min(len(mark_pos) + len(facade_pos), len(detail_vertices)) :],
        night_vertices=night_vertices,
    )


def light_context_vertices(vertices, normals, lighting_state, environment_profile=None):
    """Return one cached-ready vertex batch lit per face normal.

    This mirrors the preview model-light calculation, but can sample bundled
    environment maps per face instead of flattening the context to one ground
    normal. Call only when the lighting state changes, never per frame.
    """
    if not len(vertices):
        return vertices
    state = lighting_state
    profile = environment_profile
    if (
        state.get("use_environment_map")
        and profile is not None
        and profile.environment_pixels
        and profile.environment_width > 0
        and profile.environment_height > 0
    ):
        pixels = numpy.asarray(profile.environment_pixels, dtype=numpy.float32).reshape(
            profile.environment_height, profile.environment_width, 3
        )
        xs = numpy.clip(
            (profile.environment_width * ((normals[:, 0] + 1.0) * 0.5)).astype(numpy.intp),
            0,
            profile.environment_width - 1,
        )
        ys = numpy.clip(
            (profile.environment_height * ((normals[:, 2] + 1.0) * 0.5)).astype(numpy.intp),
            0,
            profile.environment_height - 1,
        )
        base = pixels[ys, xs] / 255.0
    elif state.get("use_environment_map"):
        base = numpy.broadcast_to(
            numpy.asarray(state.get("environment_color", (1.0, 1.0, 1.0)), dtype=numpy.float32),
            (len(vertices), 3),
        )
    else:
        sun = numpy.asarray(state["sun_dir"], dtype=numpy.float32)
        sky = numpy.asarray(state["sky_dir"], dtype=numpy.float32)
        sun /= max(float(numpy.linalg.norm(sun)), 1.0e-6)
        sky /= max(float(numpy.linalg.norm(sky)), 1.0e-6)
        sun_amount = numpy.maximum(normals @ sun, 0.0)[:, None]
        sky_amount = numpy.maximum(normals @ sky, 0.0)[:, None]
        base = (
            numpy.asarray(state["ambient_color"], dtype=numpy.float32)
            + sun_amount * numpy.asarray(state["sun_color"], dtype=numpy.float32)
            + sky_amount * numpy.asarray(state["sky_color"], dtype=numpy.float32)
        )
        numpy.clip(base, 0.0, 1.0, out=base)

    shadow_lift = 1.0 - float(state["terrain_shadow_amount"])
    light = base + (1.0 - base) * shadow_lift
    light *= numpy.asarray(state["global_color"], dtype=numpy.float32)
    tinted = vertices.copy()
    tinted[:, 3:6] *= light
    numpy.clip(tinted[:, 3:6], 0.0, 1.0, out=tinted[:, 3:6])
    tinted.setflags(write=False)
    return tinted
