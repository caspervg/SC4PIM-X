"""Adaptive lot model: which lot a catalog building places on which network.

The Adaptive Lots DLL reads one detached cohort per catalog building:

    type 0x05342861, group 0xA0907C10, instance = catalog building IID

Its property 0xA0907C13 is a flat ``Uint32`` array of quadruples::

    network type, network piece IID, variant index, lot configuration IID

Rows with the same network type and piece IID form a ring. The Tab key cycles
through a ring in the game. The DLL sorts the array by (network, piece,
variant) and renumbers each ring from zero, so the stored variant index sets
the order inside its ring and the file order means nothing. See
``LotMapping::Table::Add``. RTMT_Resource.dat, for example, stores every
variant-0 row first and interleaves the rings.

If one row breaks a rule, the DLL discards the whole cohort, and it gives no
message. ``check_rows`` and ``values_to_rows`` are ports of those rules. Thus
the editor can refuse to write a cohort that the game would discard, and the
tree can mark one that is already on disk.

This module uses no wx, so tests can run it without a display. The dialogs in
``SC4AdaptiveLotDlg`` show it. Same split as ``SC4MenuScanner``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .SC4DataFunctions import lot_building_rows
from .textutil import decode_sc4_text

COHORT_TYPE = 0x05342861
ADAPTIVE_COHORT_GROUP = 0xA0907C10
PROP_NETWORK_PIECE_MAP = 0xA0907C13

# The DLL's placement tooltip can be overridden per replacement lot. The
# props live on the LOT exemplar (not the mapping cohort): 0xA0907C14 is an
# LTEXT key whose text becomes the tooltip title (falling back to the building
# name chain); 0xA0907C15 is an LTEXT key whose text becomes the tooltip body
# (falling back to the lot/building description chain, or hiding it when the
# key is present but blank/missing/invalid). The DLL keys its tooltip cache by
# lot configuration ID, so every variant in a ring can show its own text. See
# AdaptiveLots.cpp::ResolveLotInfo and RingMetadata.cpp.
PROP_ADAPTIVE_TOOLTIP_KEY = 0xA0907C14
PROP_ADAPTIVE_TOOLTIP_DESC_KEY = 0xA0907C15

WILDCARD_NETWORK = 0xFFFFFFFF
MAX_NETWORK_TYPE = 12
LOT_OBJECT_BUILDING_ID_INDEX = 12

CATEGORY_LOT_CONFIG = 210091300
CATEGORY_BUILDING = 210746197

# The DLL accepts these network types, but the game never reports them under
# the cursor. A row that uses one can never match.
UNUSABLE_NETWORK_TYPES = (4, 5, 7)  # Pipe, Powerline, Subway

# Problem codes. Fatal ones mean the DLL discards the whole cohort.
FATAL_CODES = (
    "no-building",
    "empty",
    "ragged",
    "bad-network",
    "wildcard-piece",
    "missing-piece",
    "no-lot",
    "duplicate-variant",
)


@dataclass(frozen=True)
class AdaptiveRow:
    """One variant. The position inside its ring supplies the variant index."""

    network_type: int
    piece_id: int
    lot_config_id: int

    @property
    def ring(self) -> tuple:
        return (self.network_type, self.piece_id)

    @property
    def is_wildcard(self) -> bool:
        return self.network_type == WILDCARD_NETWORK


@dataclass(frozen=True)
class Problem:
    """One reason the DLL rejects a cohort, or one warning about a row."""

    code: str
    text: str
    row_index: Optional[int] = None

    @property
    def is_fatal(self) -> bool:
        return self.code in FATAL_CODES


@dataclass(frozen=True)
class AdaptiveMapping:
    building_id: int
    rows: tuple = ()
    tgi: Optional[tuple] = None
    file_name: Optional[str] = None
    problems: tuple = ()

    @property
    def hex(self) -> str:
        return "0x%08X" % (self.building_id & 0xFFFFFFFF)

    @property
    def is_rejected(self) -> bool:
        return any(problem.is_fatal for problem in self.problems)

    def rings(self) -> dict:
        """{(network, piece): [row]} in the order the DLL cycles them."""
        grouped: dict = {}
        for row in sort_rows(self.rows):
            grouped.setdefault(row.ring, []).append(row)
        return grouped


# -- rules ------------------------------------------------------------------


def sort_rows(rows):
    """Order rows the way ``LotMapping::Table::Add`` does.

    The sort is stable, so the caller's order inside a ring becomes the
    variant order.
    """
    return sorted(rows, key=lambda row: (row.network_type, row.piece_id))


def check_rows(building_id, rows):
    """Return the problems that make the DLL reject this cohort.

    Covers the rules that edited rows can break. A repeated variant index
    cannot occur here, because ``AdaptiveRow`` holds no index. See
    ``values_to_rows`` for data that arrives with its own indices.
    """
    problems = []
    if not int(building_id or 0) & 0xFFFFFFFF:
        problems.append(Problem("no-building", "The catalog building ID is zero."))
    if not rows:
        problems.append(Problem("empty", "The mapping has no variants."))
    for index, row in enumerate(rows):
        if row.network_type != WILDCARD_NETWORK and row.network_type > MAX_NETWORK_TYPE:
            problems.append(Problem(
                "bad-network", "The network type must be 0 to 12, or the wildcard.", index))
        if row.is_wildcard and row.piece_id != 0:
            problems.append(Problem(
                "wildcard-piece", "A wildcard row must have a network piece ID of 0.", index))
        if not row.is_wildcard and row.piece_id == 0:
            problems.append(Problem(
                "missing-piece", "The network piece ID must not be 0.", index))
        if row.lot_config_id == 0:
            problems.append(Problem("no-lot", "The lot configuration ID must not be 0.", index))
        if row.network_type in UNUSABLE_NETWORK_TYPES:
            problems.append(Problem(
                "unusable-network",
                "The game never reports this network type under the cursor.", index))
    return problems


def variant_indices(rows):
    """The variant index of each row, in the given order.

    Rows must already be sorted. Each ring restarts at zero, the way the DLL
    renumbers a cohort it loads. The editor shows these numbers and
    ``rows_to_values`` writes them, so both come from here.
    """
    indices = []
    variant = 0
    previous_ring = None
    for row in rows:
        variant = 0 if row.ring != previous_ring else variant + 1
        previous_ring = row.ring
        indices.append(variant)
    return indices


def rows_to_values(rows):
    """Flatten rows into the quadruple array, numbering each ring from zero."""
    rows = sort_rows(rows)
    values = []
    for row, variant in zip(rows, variant_indices(rows)):
        values.extend((row.network_type, row.piece_id, variant, row.lot_config_id))
    return tuple(value & 0xFFFFFFFF for value in values)


def values_to_rows(values):
    """Read a stored quadruple array. Returns ``(rows, problems)``.

    Applies the two rules that only data from another tool can break: a length
    that is not a multiple of four, and a repeated variant index in one ring.
    The rows come back even after a fatal problem, so the tree can show what
    the file holds and why the game ignores it.
    """
    values = [int(value) & 0xFFFFFFFF for value in (values or ())]
    problems = []
    if not values:
        problems.append(Problem("empty", "The mapping has no variants."))
        return (), tuple(problems)
    if len(values) % 4:
        problems.append(Problem(
            "ragged", "The value count is %d, which is not a multiple of 4." % len(values)))
        values = values[:len(values) - len(values) % 4]

    stored = []
    seen = set()
    for index, offset in enumerate(range(0, len(values), 4)):
        network_type, piece_id, variant, lot_config_id = values[offset:offset + 4]
        key = (network_type, piece_id, variant)
        if key in seen:
            problems.append(Problem(
                "duplicate-variant", "Variant %d of this ring is used twice." % variant, index))
        seen.add(key)
        stored.append((variant, AdaptiveRow(network_type, piece_id, lot_config_id)))

    # The DLL sorts by (network, piece, variant), so the stored index sets the
    # order in a ring. File order must not be trusted: a package may list
    # variant 1 before variant 0, and reading it in file order would show the
    # wrong cycle and write a different one back.
    stored.sort(key=lambda item: (item[1].network_type, item[1].piece_id, item[0]))
    return tuple(row for _variant, row in stored), tuple(problems)


# -- cache ------------------------------------------------------------------


def _cache(virtual_dat) -> dict:
    cache = getattr(virtual_dat, "_adaptive_cache", None)
    if cache is None:
        cache = {}
        try:
            virtual_dat._adaptive_cache = cache
        except AttributeError:  # read-only stand-ins in tests
            return {}
    return cache


def invalidate_adaptive_cache(virtual_dat) -> None:
    """Drop every cached adaptive view.

    Call this after a mapping cohort is written. Then the next editor or tree
    shows it without a rescan.
    """
    try:
        virtual_dat._adaptive_cache = {}
    except AttributeError:
        pass


# -- scanning ---------------------------------------------------------------


def scan_adaptive_mappings(virtual_dat, force=False):
    """{building_id: AdaptiveMapping} for every mapping cohort in the plugins.

    Cached on the virtual_dat instance. Pass ``force=True`` to rescan.
    """
    cache = _cache(virtual_dat)
    cached = cache.get("mappings")
    if cached is not None and not force:
        return cached

    mappings = {}
    for entry in getattr(virtual_dat, "cohorts", ()) or ():
        tgi = tuple(getattr(entry, "tgi", ()) or ())
        if len(tgi) < 3 or (int(tgi[1]) & 0xFFFFFFFF) != ADAPTIVE_COHORT_GROUP:
            continue
        exemplar = getattr(entry, "exemplar", None)
        if exemplar is None:
            continue
        values = exemplar.GetProp(PROP_NETWORK_PIECE_MAP)
        if values is None:
            continue
        building_id = int(tgi[2]) & 0xFFFFFFFF
        rows, problems = values_to_rows(values)
        mappings[building_id] = AdaptiveMapping(
            building_id=building_id, rows=rows, tgi=tgi,
            file_name=getattr(entry, "fileName", None),
            problems=tuple(problems) + tuple(check_rows(building_id, rows)),
        )
    cache["mappings"] = mappings
    return mappings


def _lot_tooltip_text(virtual_dat, lot_config_id, prop_id):
    """The LTEXT text a lot's tooltip override key prop points at, or None.

    The DLL reads the adaptive tooltip key props off the replacement lot
    exemplar and leaves one ``LotInfo`` per lot configuration ID in its cache,
    so the tree shows the name per variant and the row editor edits it per
    lot. A missing, (0,0,0), or unreadable key reads as None.
    """
    descriptor = lot_config_descriptor(virtual_dat, int(lot_config_id) & 0xFFFFFFFF)
    exemplar = getattr(descriptor, "exemplar", None)
    if exemplar is None:
        return None
    key = exemplar.GetProp(prop_id)
    if not key or len(key) < 3:
        return None
    key = tuple(int(value) & 0xFFFFFFFF for value in key[:3])
    if key == (0, 0, 0):
        return None
    entry = virtual_dat.getEntry(*key)
    if entry is None:
        return None
    try:
        if entry.content is None:
            entry.read_file(None, True, True)
        return decode_sc4_text(entry.content[4:]).strip() or None
    except Exception:
        return None


def lot_tooltip_name(virtual_dat, lot_config_id):
    """The tooltip title the game shows for this replacement lot, or None."""
    return _lot_tooltip_text(virtual_dat, lot_config_id, PROP_ADAPTIVE_TOOLTIP_KEY)


def lot_tooltip_description(virtual_dat, lot_config_id):
    """The tooltip description the game shows for this lot, or None."""
    return _lot_tooltip_text(virtual_dat, lot_config_id, PROP_ADAPTIVE_TOOLTIP_DESC_KEY)


def known_piece_ids(virtual_dat, force=False):
    """Network piece IIDs that a mapping already uses, lowest first.

    PIM-X cannot calculate a piece IID from any file it reads. The values that
    other packages use are the only known ones.
    """
    pieces = set()
    for mapping in scan_adaptive_mappings(virtual_dat, force=force).values():
        pieces.update(row.piece_id for row in mapping.rows if not row.is_wildcard)
    return sorted(pieces)


# -- lot and building resolution --------------------------------------------


def _descriptor_index(virtual_dat, category_id, cache_key):
    """{instance: descriptor} over one category, built once.

    The tree and the editor look up one lot and one building per row. A scan of
    the whole category per row is too slow on a large plugins folder, so the
    index is cached like ``SC4MenuScanner._png_icon_index``.
    """
    cache = _cache(virtual_dat)
    index = cache.get(cache_key)
    if index is None:
        index = {}
        categories = getattr(virtual_dat, "categories", None) or {}
        category = categories.get(category_id)
        for descriptor in getattr(category, "descriptors", ()) or ():
            entry = getattr(getattr(descriptor, "exemplar", None), "entry", None)
            if entry is not None:
                index.setdefault(int(entry.tgi[2]) & 0xFFFFFFFF, descriptor)
        cache[cache_key] = index
    return index


def lot_config_descriptor(virtual_dat, iid):
    """The lot configuration descriptor with this instance ID, or None."""
    return _descriptor_index(virtual_dat, CATEGORY_LOT_CONFIG, "lot_configs").get(
        int(iid) & 0xFFFFFFFF)


def building_descriptor(virtual_dat, iid):
    """The building descriptor with this instance ID, or None."""
    return _descriptor_index(virtual_dat, CATEGORY_BUILDING, "buildings").get(
        int(iid) & 0xFFFFFFFF)


def building_game_name(virtual_dat, building_id):
    """The name the game shows for a building, or None.

    The menu draws this name, so the tree shows it next to the raw ID. Uses the
    same resolver as the submenu tree.
    """
    from .SC4MenuScanner import resolve_display_name

    descriptor = building_descriptor(virtual_dat, building_id) if building_id else None
    exemplar = getattr(descriptor, "exemplar", None)
    return resolve_display_name(virtual_dat, exemplar) if exemplar is not None else None


def lot_game_name(virtual_dat, lot_config_id):
    """The name the game shows for the building a lot places, or None."""
    return building_game_name(virtual_dat, building_id_for_lot_id(virtual_dat, lot_config_id))


def building_id_for_lot(exemplar):
    """The building a lot configuration places, or None.

    The DLL resolves a lot only when it places exactly one building. This is
    the same type-0 row rule the lot conversion tools use.
    """
    rows = [values for _prop_id, values in lot_building_rows(exemplar)
            if len(values) > LOT_OBJECT_BUILDING_ID_INDEX]
    if len(rows) != 1:
        return None
    building_id = int(rows[0][LOT_OBJECT_BUILDING_ID_INDEX]) & 0xFFFFFFFF
    return building_id or None


def building_id_for_lot_id(virtual_dat, lot_config_id):
    """``building_id_for_lot`` starting from a lot configuration IID."""
    descriptor = lot_config_descriptor(virtual_dat, lot_config_id)
    exemplar = getattr(descriptor, "exemplar", None)
    return building_id_for_lot(exemplar) if exemplar is not None else None


def hidden_building_ids(mappings, building_of_lot, is_available=None):
    """Buildings the DLL removes from the catalog menus.

    Port of ``RingMetadata::BuildHiddenBuildingSet``. The DLL hides a
    replacement lot's building so one adaptive item stands in for a whole ring,
    but it keeps each ring's root visible. A root is a mapping key, or the
    building of the lot configuration whose IID equals that key.

    ``building_of_lot`` maps a lot configuration IID to a building IID or None,
    which keeps this function independent of the plugin index. Only applies
    while the DLL's ``HideRingLotMenuItems`` setting is on, which is its
    default.

    ``is_available`` tells whether a lot configuration is installed; default is
    "everything is". The DLL compacts rows whose lot configuration is missing
    from the plugins before it builds the hidden set (see
    ``RemoveUnavailableLotConfigurations``), so a missing lot's building is
    never hidden.
    """
    if is_available is None:
        is_available = lambda _lot_config_id: True

    roots = set()
    for building_id in mappings:
        roots.add(building_id)
        root_building = building_of_lot(building_id)
        if root_building:
            roots.add(root_building)

    hidden = set()
    for mapping in mappings.values():
        for row in mapping.rows:
            if not is_available(row.lot_config_id):
                continue
            building_id = building_of_lot(row.lot_config_id)
            if building_id and building_id not in roots:
                hidden.add(building_id)
    return hidden
