import random
from dataclasses import replace
from datetime import date
from itertools import combinations

import numpy
import pytest

from sc4pimx.SC4CityContext import (
    EDGE_XMAX,
    EDGE_XMIN,
    EDGE_ZMAX,
    EDGE_ZMIN,
    MAT_BIKE_LANE,
    MAT_CONTACT,
    MAT_CURB,
    MAT_FIELD,
    MAT_HEDGE,
    MAT_HORIZON,
    MAT_ISLAND,
    MAT_LAMP,
    MAT_MARKING,
    MAT_METAL,
    MAT_PARKING_AISLE,
    MAT_PEDESTRIAN,
    MAT_STOREFRONT,
    MAT_WINDOW,
    MAX_BOXES,
    MAX_CONTEXT_VERTICES,
    MAX_DETAIL_BOXES,
    MAX_FACADE_QUADS,
    MAX_LIT_WINDOWS,
    MAX_NIGHT_LIGHTS,
    MAX_TREES,
    PARKING_AISLE_M,
    PARKING_DEPTH_M,
    PARKING_STALL_M,
    ROAD_AVENUE,
    ROAD_BIKE,
    ROAD_PEDESTRIAN,
    ROAD_STREET,
    ROADWAY_M,
    SEASON_AUTUMN,
    SEASON_SPRING,
    SEASON_SUMMER,
    SEASON_WINTER,
    SIDEWALK_M,
    STYLE_CIVIC,
    STYLE_INDUSTRIAL,
    STYLE_MIXED,
    STYLE_RURAL,
    STYLE_SUBURBAN,
    STYLE_URBAN,
    TILE_M,
    _decorate_open_spaces,
    _decorate_streets,
    _Grid,
    _make_parking,
    _palette_for_style,
    _Parcel,
    _parcel_falloff,
    _road_corridors,
    build_context_ambient_mesh,
    build_context_mesh,
    context_seed,
    default_context_seed,
    generate_city_context,
    infer_context_style,
    light_context_vertices,
    road_edges_from_flags,
    season_for_month,
    variation_seed,
)


def overlaps_2d(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def test_scale_and_seed_contract():
    tgi = (0x6534284A, 0xA8FBD372, 0x12345678)
    other = (0x6534284A, 0xA8FBD372, 0x12345679)
    default = default_context_seed(tgi)

    assert TILE_M == 16.0
    assert SIDEWALK_M + ROADWAY_M + SIDEWALK_M == TILE_M
    assert default == default_context_seed(tgi)
    assert default != default_context_seed(other)
    assert variation_seed(default, 1) != default
    assert context_seed(tgi, 1) != context_seed(tgi)
    assert context_seed(tgi, None) == default  # reset


def test_road_and_parking_markings_use_real_world_dimensions():
    assert (PARKING_STALL_M, PARKING_DEPTH_M, PARKING_AISLE_M) == (2.7, 5.2, 6.0)

    grid = _Grid(1, 1, 3)
    for tx in (-3, -2, -1):
        grid.set_road(tx, -2)
    road_details = []
    _road_corridors(grid, road_details)
    curbs = [rect for rect in road_details if rect.material == MAT_CURB]
    dashes = [rect for rect in road_details if rect.material == MAT_MARKING]
    assert curbs
    assert dashes
    assert all(sorted((rect.x1 - rect.x0, rect.z1 - rect.z0)) == pytest.approx([0.2, 4.0]) for rect in dashes)

    rects, parking_details = [], []
    parcel = _Parcel(0, 0, 2, 2, (EDGE_ZMIN,), EDGE_ZMIN)
    bays = _make_parking(0.0, 0.0, 32.0, 32.0, parcel, rects, parking_details)
    separators = [
        rect
        for rect in parking_details
        if rect.material == MAT_MARKING and rect.z1 - rect.z0 == pytest.approx(PARKING_DEPTH_M)
    ]
    centers = sorted({round((rect.x0 + rect.x1) * 0.5, 3) for rect in separators})
    assert len(centers) >= 3
    assert all(b - a == pytest.approx(PARKING_STALL_M) for a, b in zip(centers, centers[1:]))
    assert len(bays) == 2 * (len(centers) - 1)
    assert all(not along_x for _x, _z, along_x in bays)
    bay_xs = sorted({round(x, 3) for x, _z, _along_x in bays})
    assert bay_xs == pytest.approx([(a + b) * 0.5 for a, b in zip(centers, centers[1:])])
    assert any(rect.material == MAT_PARKING_AISLE for rect in rects)
    palette = _palette_for_style(STYLE_SUBURBAN)
    architectural = ("ground", "road", "sidewalk", "park", "yard", "wall", "roof")
    assert max(max(palette[name]) - min(palette[name]) for name in architectural) < 0.07
    assert max(max(color) - min(color) for color in palette.values()) < 0.15


def test_parking_cars_use_marked_bay_centers_and_orientation(monkeypatch):
    rects, details = [], []
    parcel = _Parcel(0, 0, 2, 2, (EDGE_ZMIN,), EDGE_ZMIN)
    bays = _make_parking(0.0, 0.0, 32.0, 32.0, parcel, rects, details)
    placed = []
    monkeypatch.setattr(
        "sc4pimx.SC4CityContext._add_car",
        lambda _rng, x, z, along_x, _boxes: placed.append((x, z, along_x)),
    )

    _decorate_open_spaces(_Grid(1, 1, 3), random.Random(1), STYLE_SUBURBAN, rects, details, [], bays)

    assert placed
    assert set(placed) <= set(bays)
    assert all(not along_x for _x, _z, along_x in placed)


def test_crosswalks_are_scaled_and_oriented_per_connected_approach():
    grid = _Grid(1, 1, 4)
    center = (-2, -2)
    for tx, tz in (center, (-2, -3), (-2, -1), (-3, -2), (-1, -2)):
        grid.set_road(tx, tz)
    details, boxes = [], []
    _decorate_streets(grid, random.Random(7), STYLE_URBAN, details, boxes)

    stripes = [
        rect
        for rect in details
        if rect.material == MAT_MARKING and min(rect.x1 - rect.x0, rect.z1 - rect.z0) == pytest.approx(0.50)
    ]
    horizontal = [rect for rect in stripes if rect.x1 - rect.x0 > rect.z1 - rect.z0]
    vertical = [rect for rect in stripes if rect.z1 - rect.z0 > rect.x1 - rect.x0]
    assert len(horizontal) == len(vertical) == 16
    assert all(max(rect.x1 - rect.x0, rect.z1 - rect.z0) == pytest.approx(2.6) for rect in stripes)

    # Every zebra remains on its own approach; perpendicular bars must never
    # overlap into the lattice pattern that previously filled the junction.
    assert all(
        a.x1 <= b.x0 or b.x1 <= a.x0 or a.z1 <= b.z0 or b.z1 <= a.z0
        for a in horizontal
        for b in vertical
    )
    center_x = center[0] * TILE_M + TILE_M / 2
    center_z = center[1] * TILE_M + TILE_M / 2
    assert all(not (rect.x0 < center_x < rect.x1 and rect.z0 < center_z < rect.z1) for rect in stripes)


def test_crosswalks_do_not_decorate_the_internal_seam_of_a_paired_avenue():
    grid = _Grid(1, 1, 4)
    for tz in (-3, -2, -1, 0):
        grid.set_road(-2, tz)
    for tz in (-2, -1):
        grid.set_road(-3, tz)
        grid.set_road(-1, tz)
    profiles = (
        ("h", -2, ROAD_AVENUE),
        ("h", -1, ROAD_AVENUE),
        ("v", -2, ROAD_STREET),
    )
    details, boxes = [], []
    _decorate_streets(grid, random.Random(7), STYLE_URBAN, details, boxes, profiles)

    stripes = [
        rect
        for rect in details
        if rect.material == MAT_MARKING and min(rect.x1 - rect.x0, rect.z1 - rect.z0) == pytest.approx(0.50)
    ]
    seam_z = -TILE_M
    assert stripes
    north_south_bars = [rect for rect in stripes if rect.z1 - rect.z0 > rect.x1 - rect.x0]
    assert north_south_bars
    assert all(rect.z1 <= seam_z - 3.0 or rect.z0 >= seam_z + 3.0 for rect in north_south_bars)


def test_multimodal_corridors_are_coherent_wide_and_protected():
    scene = generate_city_context(4, 4, road_edges_from_flags(8), STYLE_URBAN, 12345)
    profiles = {(axis, coordinate): kind for axis, coordinate, kind in scene.road_profiles}
    avenues = [(axis, coordinate) for (axis, coordinate), kind in profiles.items() if kind == ROAD_AVENUE]
    assert avenues
    assert any((axis, coordinate + 1) in avenues for axis, coordinate in avenues)

    road_tiles = set(scene.road_tiles)
    for axis, coordinate in avenues:
        if (axis, coordinate + 1) not in avenues:
            continue
        if axis == "h":
            assert any((tx, coordinate) in road_tiles and (tx, coordinate + 1) in road_tiles for tx in range(-18, 22))
        else:
            assert any((coordinate, tz) in road_tiles and (coordinate + 1, tz) in road_tiles for tz in range(-18, 22))

    assert ROAD_BIKE in profiles.values()
    assert ROAD_PEDESTRIAN in profiles.values()
    assert any(rect.material == MAT_BIKE_LANE for rect in scene.detail_rects)
    assert any(rect.material == MAT_PEDESTRIAN for rect in scene.rects)
    assert any(rect.material == MAT_PEDESTRIAN for rect in scene.detail_rects)  # protected avenue crossing
    assert any(rect.material == MAT_ISLAND for rect in scene.detail_rects)


@pytest.mark.parametrize("flags", range(16))
def test_immediate_road_tiles_exactly_follow_all_edge_flag_combinations(flags):
    width, depth = 5, 4
    edges = road_edges_from_flags(flags)
    scene = generate_city_context(width, depth, edges, STYLE_MIXED, 99)
    roads = set(scene.road_tiles)
    expected = {
        EDGE_XMIN: {(-1, z) for z in range(depth)},
        EDGE_ZMIN: {(x, -1) for x in range(width)},
        EDGE_XMAX: {(width, z) for z in range(depth)},
        EDGE_ZMAX: {(x, depth) for x in range(width)},
    }
    for edge, border in expected.items():
        assert border.issubset(roads) if edge in edges else roads.isdisjoint(border)


@pytest.mark.parametrize("value", [None, "", "broken", object()])
def test_malformed_road_flags_fail_safe(value):
    assert road_edges_from_flags(value) == frozenset()
    generate_city_context(2, 2, road_edges_from_flags(value), STYLE_MIXED, 1)


@pytest.mark.parametrize(
    ("purpose_types", "building_purpose", "civic", "park", "expected"),
    [
        ((1,), None, False, False, STYLE_SUBURBAN),
        ((2,), None, False, False, STYLE_URBAN),
        ((5,), None, False, False, STYLE_RURAL),
        ((7,), None, False, False, STYLE_INDUSTRIAL),
        ((1, 2), None, False, False, STYLE_MIXED),
        ((), 3, False, False, STYLE_URBAN),
        ((), None, True, False, STYLE_CIVIC),
        (("bad",), None, False, False, STYLE_MIXED),
    ],
)
def test_style_inference_is_small_deterministic_and_safe(purpose_types, building_purpose, civic, park, expected):
    assert (
        infer_context_style(
            purpose_types,
            building_purpose,
            civic=civic,
            park=park,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("width", "depth", "flags", "style"),
    [
        (0, 0, 0, STYLE_MIXED),
        (1, 1, 15, STYLE_SUBURBAN),
        (4, 6, 9, STYLE_URBAN),
        (16, 16, 2, STYLE_INDUSTRIAL),
        (64, 64, 12, STYLE_RURAL),
        (3, 5, None, "ambiguous"),
    ],
)
def test_generation_is_repeatable_bounded_and_clear_of_lot_and_roads(width, depth, flags, style):
    scene = generate_city_context(width, depth, road_edges_from_flags(flags), style, 123456)
    assert scene == generate_city_context(width, depth, road_edges_from_flags(flags), style, 123456)

    lot = (0.0, 0.0, scene.lot_w * TILE_M, scene.lot_d * TILE_M)
    road_rects = [(x * TILE_M, z * TILE_M, (x + 1) * TILE_M, (z + 1) * TILE_M) for x, z in scene.road_tiles]
    bounds = (
        -scene.margin * TILE_M,
        -scene.margin * TILE_M,
        (scene.lot_w + scene.margin) * TILE_M,
        (scene.lot_d + scene.margin) * TILE_M,
    )
    for box in scene.boxes:
        footprint = (box.x0, box.z0, box.x1, box.z1)
        assert not overlaps_2d(footprint, lot)
        assert not any(overlaps_2d(footprint, road) for road in road_rects)
        assert bounds[0] <= box.x0 < box.x1 <= bounds[2]
        assert bounds[1] <= box.z0 < box.z1 <= bounds[3]

    for first, second in combinations(scene.boxes, 2):
        horizontal = overlaps_2d(
            (first.x0, first.z0, first.x1, first.z1),
            (second.x0, second.z0, second.x1, second.z1),
        )
        vertical = min(first.y1, second.y1) > max(first.y0, second.y0)
        assert not (horizontal and vertical)

    assert len(scene.boxes) <= MAX_BOXES
    assert len(scene.trees) <= MAX_TREES


def test_typical_scene_mesh_stays_below_geometry_ceiling_and_is_prebuilt():
    scene = generate_city_context(
        16,
        16,
        road_edges_from_flags(15),
        STYLE_SUBURBAN,
        123,
    )
    mesh = build_context_mesh(scene)

    assert mesh.vertex_count <= MAX_CONTEXT_VERTICES
    assert mesh.vertices.shape[1] == mesh.detail_vertices.shape[1] == 9
    assert mesh.normals.shape == mesh.vertices[:, :3].shape
    assert mesh.detail_normals.shape == mesh.detail_vertices[:, :3].shape
    assert not mesh.vertices.flags.writeable
    assert not mesh.detail_vertices.flags.writeable
    assert not mesh.normals.flags.writeable
    assert not mesh.detail_normals.flags.writeable
    assert not mesh.night_vertices.flags.writeable
    assert len(mesh.night_vertices) <= MAX_LIT_WINDOWS * 6 + MAX_NIGHT_LIGHTS * 30
    assert numpy.shares_memory(mesh.vertices, mesh.shadow_vertices)
    assert numpy.shares_memory(mesh.detail_vertices, mesh.detail_shadow_vertices)
    assert numpy.allclose(numpy.linalg.norm(mesh.normals, axis=1), 1.0, atol=1.0e-5)
    assert numpy.allclose(numpy.linalg.norm(mesh.detail_normals, axis=1), 1.0, atol=1.0e-5)

    large = generate_city_context(64, 64, road_edges_from_flags(12), STYLE_SUBURBAN, 123456)
    assert build_context_mesh(large).vertex_count <= MAX_CONTEXT_VERTICES


def test_fancy_detail_kits_are_deterministic_bounded_and_style_specific():
    scenes = {
        style: generate_city_context(4, 4, road_edges_from_flags(8), style, 12345)
        for style in (STYLE_URBAN, STYLE_SUBURBAN, STYLE_INDUSTRIAL, STYLE_CIVIC, STYLE_RURAL)
    }
    for style, scene in scenes.items():
        assert scene == generate_city_context(4, 4, road_edges_from_flags(8), style, 12345)
        assert scene.detail_boxes
        assert scene.detail_quads
        assert len(scene.detail_boxes) <= MAX_DETAIL_BOXES
        assert len(scene.detail_quads) <= MAX_FACADE_QUADS
        assert any(box.material == MAT_LAMP for box in scene.detail_boxes)
        assert any(quad.material == MAT_WINDOW for quad in scene.detail_quads)

    assert any(quad.material == MAT_STOREFRONT for quad in scenes[STYLE_URBAN].detail_quads)
    assert any(box.material == MAT_HEDGE for box in scenes[STYLE_SUBURBAN].detail_boxes)
    assert any(box.material == MAT_METAL for box in scenes[STYLE_INDUSTRIAL].detail_boxes)
    assert any(rect.material == "water" for rect in scenes[STYLE_CIVIC].detail_rects)
    assert any(rect.material == MAT_FIELD for rect in scenes[STYLE_RURAL].detail_rects)


def test_density_height_and_ambient_activity_are_user_controllable():
    edges = road_edges_from_flags(8)
    low = generate_city_context(4, 4, edges, STYLE_URBAN, 12345, density="low", height="low")
    high = generate_city_context(4, 4, edges, STYLE_URBAN, 12345, density="high", height="high")
    assert len(high.boxes) > len(low.boxes)
    assert max(box.y1 for box in high.boxes) > max(box.y1 for box in low.boxes)

    still = build_context_ambient_mesh(high, 10.0, "off", "off")
    first = build_context_ambient_mesh(high, 10.0, "medium", "medium")
    repeat = build_context_ambient_mesh(high, 10.0, "medium", "medium")
    moved = build_context_ambient_mesh(high, 10.5, "medium", "medium")
    assert len(still.vertices) == 0
    assert len(first.vertices) > 0
    assert numpy.array_equal(first.vertices, repeat.vertices)
    assert not numpy.array_equal(first.vertices, moved.vertices)
    assert first.normals.shape == first.vertices[:, :3].shape


def test_seasons_change_context_vegetation_without_reshuffling_the_city():
    assert season_for_month(4) == SEASON_SPRING
    assert season_for_month(7) == SEASON_SUMMER
    assert season_for_month(10) == SEASON_AUTUMN
    assert season_for_month(1) == SEASON_WINTER

    summer = generate_city_context(5, 4, road_edges_from_flags(8), STYLE_SUBURBAN, 31415, SEASON_SUMMER)
    autumn = generate_city_context(5, 4, road_edges_from_flags(8), STYLE_SUBURBAN, 31415, SEASON_AUTUMN)
    winter = generate_city_context(5, 4, road_edges_from_flags(8), STYLE_SUBURBAN, 31415, SEASON_WINTER)
    assert summer.boxes == autumn.boxes == winter.boxes
    assert summer.road_tiles == autumn.road_tiles == winter.road_tiles
    assert summer.trees == autumn.trees == winter.trees

    summer_mesh = build_context_mesh(summer)
    autumn_mesh = build_context_mesh(autumn)
    winter_mesh = build_context_mesh(winter)
    assert not numpy.array_equal(summer_mesh.detail_colors, autumn_mesh.detail_colors)
    assert len(winter_mesh.detail_vertices) < len(summer_mesh.detail_vertices)


def test_outer_context_colors_converge_on_the_horizon_palette():
    scene = generate_city_context(4, 4, road_edges_from_flags(8), STYLE_MIXED, 2468)
    mesh = build_context_mesh(scene)
    horizon = numpy.asarray(_palette_for_style(scene.style, scene.season)[MAT_HORIZON])
    distance = numpy.maximum(numpy.abs(mesh.positions[:, 0]), numpy.abs(mesh.positions[:, 2]))
    far = mesh.colors[distance >= numpy.percentile(distance, 98), :3]
    near = mesh.colors[distance <= numpy.percentile(distance, 30), :3]
    assert numpy.linalg.norm(far.mean(axis=0) - horizon) < numpy.linalg.norm(near.mean(axis=0) - horizon)


def test_visual_refinements_are_cached_geometry_not_draw_time_work():
    scene = generate_city_context(8, 8, road_edges_from_flags(15), STYLE_MIXED, 444)
    ground_boxes = [box for box in scene.boxes if box.y0 <= -0.079]
    contacts = [rect for rect in scene.rects if rect.material == MAT_CONTACT]
    assert len(contacts) == len(ground_boxes)

    urban = build_context_mesh(replace(scene, style=STYLE_URBAN))
    rural = build_context_mesh(replace(scene, style=STYLE_RURAL))
    assert not numpy.array_equal(urban.colors, rural.colors)

    grid = _Grid(4, 4, 13)
    assert _parcel_falloff(grid, (-1, 0, 0, 1)) == 0.0
    assert _parcel_falloff(grid, (-13, 0, -12, 1)) > 0.9


def test_context_lighting_uses_face_normals_and_returns_immutable_batch():
    vertices = numpy.zeros((2, 9), dtype=numpy.float32)
    vertices[:, 3:7] = (0.8, 0.8, 0.8, 1.0)
    normals = numpy.asarray(((0, 1, 0), (0, -1, 0)), dtype=numpy.float32)
    state = {
        "use_environment_map": False,
        "sun_dir": (0, 1, 0),
        "sky_dir": (1, 0, 0),
        "ambient_color": (0.2, 0.2, 0.2),
        "sun_color": (0.8, 0.8, 0.8),
        "sky_color": (0.0, 0.0, 0.0),
        "terrain_shadow_amount": 1.0,
        "global_color": (1.0, 1.0, 1.0),
    }
    lit = light_context_vertices(vertices, normals, state)

    assert numpy.all(lit[0, 3:6] > lit[1, 3:6])
    assert not lit.flags.writeable
    assert numpy.all(vertices[:, 3:6] == 0.8)


def test_shadow_pass_builds_one_stencil_union_then_composites_once(monkeypatch):
    import sc4pimx.SC4LotPreview as preview

    calls = []

    def record(name):
        return lambda *args: calls.append((name, args))

    for name in (
        "glBlendFunc",
        "glClear",
        "glClearStencil",
        "glColorMask",
        "glDepthFunc",
        "glDepthMask",
        "glDisable",
        "glEnable",
        "glPolygonOffset",
        "glStencilFunc",
        "glStencilMask",
        "glStencilOp",
    ):
        monkeypatch.setattr(preview, name, record(name))

    class Primitives:
        def quad(self, _points, _mvp, **kwargs):
            calls.append(("quad", kwargs["color"]))

    class Dummy:
        glCanvas2D = type(
            "Canvas", (), {"stencil_bits": 8, "renderer": type("Renderer", (), {"primitives": Primitives()})()}
        )()
        lightingProfile = None
        SHADOW_COLOR = (0.08, 0.06, 0.23)
        SHADOW_STRENGTH = 0.4
        SHADOW_DEPTH_BIAS_FACTOR = preview.LotEditorWin.SHADOW_DEPTH_BIAS_FACTOR
        SHADOW_DEPTH_BIAS_UNITS = preview.LotEditorWin.SHADOW_DEPTH_BIAS_UNITS
        _render_context = None

        def _shadow_flatten_matrix(self):
            return numpy.identity(4)

        def _shadow_light_dir(self):
            return (0.5, -1.0, 0.25)

        def DrawCityContextShadows(self, _flatten):
            calls.append(("context", ()))

        def _is_layer_visible(self, _view, _layer):
            return False

        def _flush_shadow_batches(self, _batches):
            return None

    preview.LotEditorWin._draw_shadow_pass(Dummy(), 0, 0, (), 0, 0, 0, 0)

    assert ("glStencilFunc", (preview.GL_ALWAYS, 1, 0xFF)) in calls
    assert ("glStencilFunc", (preview.GL_EQUAL, 1, 0xFF)) in calls
    composites = [color for name, color in calls if name == "quad"]
    assert composites == [pytest.approx((0.632, 0.624, 0.692, 1.0))]
    assert ("glDepthMask", (preview.GL_FALSE,)) in calls
    assert (
        "glPolygonOffset",
        (
            preview.LotEditorWin.SHADOW_DEPTH_BIAS_FACTOR,
            preview.LotEditorWin.SHADOW_DEPTH_BIAS_UNITS,
        ),
    ) in calls


def test_atc_billboards_are_depth_tested_without_writing_depth(monkeypatch):
    import sc4pimx.SC4LotPreview as preview

    atc = preview.ATC(None, None)
    atc.draw_le = lambda *_args: True
    calls = []
    atc.DrawGL = lambda *_args: calls.append(("draw", ()))
    for name in ("glDepthFunc", "glDepthMask", "glDisable", "glEnable"):
        monkeypatch.setattr(preview, name, lambda *args, name=name: calls.append((name, args)))

    class Dummy:
        _render_context = preview.TransformStack()
        s3DTexturesHolder = object()
        glCanvas2D = type("Canvas", (), {"renderer": object()})()

        def _flush_model_batches(self, _batches):
            return None

    preview.LotEditorWin._draw_state_member(Dummy(), atc, (0, 0, 0), 0, 0, 0, 4, None, None, None)

    draw_index = calls.index(("draw", ()))
    assert ("glEnable", (preview.GL_DEPTH_TEST,)) in calls[:draw_index]
    assert ("glDepthFunc", (preview.GL_LEQUAL,)) in calls[:draw_index]
    assert ("glDepthMask", (preview.GL_FALSE,)) in calls[:draw_index]
    assert ("glDepthMask", (preview.GL_TRUE,)) in calls[draw_index + 1 :]
    assert ("glDisable", (preview.GL_BLEND,)) in calls[draw_index + 1 :]
    assert ("glDisable", (preview.GL_DEPTH_TEST,)) not in calls
    assert preview._atc_anchor_depth(numpy.identity(4), 0, 0, 5) > preview._atc_anchor_depth(
        numpy.identity(4), 0, 0, -5
    )


def test_s3d_shadow_projector_includes_sc4_quarter_turn():
    import sc4pimx.SC4LotPreview as preview

    meshes = [object(), object(), object(), object()]
    model = object.__new__(preview.SC4Model)
    model.s3dMeshes = [meshes]
    submitted = {}

    class Dummy:
        SHADOW_PROJECTOR_YAW = preview.LotEditorWin.SHADOW_PROJECTOR_YAW
        _render_context = preview.TransformStack()

        def _shadow_light_dir(self):
            return (0.5, -1.0, 0.25)

        def _submit_s3d_model(self, chosen, _shader, _lighting, _batches, **kwargs):
            submitted["mesh"] = chosen
            submitted["model"] = self._render_context.model.copy()
            submitted["projection"] = kwargs["shadow_projection"]

    dummy = Dummy()
    preview.LotEditorWin._draw_state_member(
        dummy, model, (0.0, 0.0, 0.0), 90.0, 0, 2, 0,
        object(), None, {}, shadow=True, shadow_direction=(0.5, -1.0, 0.25),
    )

    expected_yaw = -180.0  # -lot/view 90, then SC4's fixed -90 projector turn
    expected_direction = (
        preview.SC4Matrix.rotate_y(-expected_yaw)[0:3, 0:3]
        @ numpy.asarray((0.5, -1.0, 0.25))
    )
    assert submitted["mesh"] is meshes[1]
    assert submitted["model"] == pytest.approx(preview.SC4Matrix.rotate_y(expected_yaw))
    assert submitted["projection"][0] == pytest.approx(expected_direction)
    assert submitted["projection"][1] == 0.0


def test_animated_rkt3_shadow_keeps_visible_geometry_position():
    import sc4pimx.SC4LotPreview as preview

    mesh = object()
    model = object.__new__(preview.SC4Model1MeshPerZoom)
    model.s3dMeshes = [mesh]
    camera = preview.SC4Matrix.translate(12.0, 3.0, -7.0)
    submitted = {}

    class Dummy:
        _render_context = preview.TransformStack(model=camera)

        def _shadow_light_dir(self):
            return (0.5, -1.0, 0.25)

        def _submit_s3d_model(self, chosen, _shader, _lighting, _batches, **kwargs):
            submitted["mesh"] = chosen
            submitted["model"] = self._render_context.model.copy()
            submitted["projection"] = kwargs["shadow_projection"]

    preview.LotEditorWin._draw_state_member(
        Dummy(), model, (0.0, 0.0, 0.0), 90.0, 0, 0, 0,
        object(), None, {}, shadow=True, shadow_direction=(0.5, -1.0, 0.25),
    )

    assert submitted["mesh"] is mesh
    assert submitted["model"] == pytest.approx(camera)
    assert submitted["projection"][0] == pytest.approx((0.5, -1.0, 0.25))
    assert submitted["projection"][1] == 0.0


@pytest.mark.parametrize("lot_rotation", range(4))
def test_s3d_shadow_uses_next_prerendered_view_for_each_lot_rotation(lot_rotation):
    import sc4pimx.SC4LotPreview as preview

    meshes = [object(), object(), object(), object()]
    model = object.__new__(preview.SC4Model)
    model.s3dMeshes = [meshes]
    submitted = {}

    class Dummy:
        SHADOW_PROJECTOR_YAW = preview.LotEditorWin.SHADOW_PROJECTOR_YAW
        _render_context = preview.TransformStack()

        def _shadow_light_dir(self):
            return (0.5, -1.0, 0.25)

        def _submit_s3d_model(self, chosen, _shader, _lighting, _batches, **kwargs):
            submitted["mesh"] = chosen

    preview.LotEditorWin._draw_state_member(
        Dummy(), model, (0.0, 0.0, 0.0), lot_rotation * 90.0,
        lot_rotation, 2, 0, object(), None, {}, shadow=True,
        shadow_direction=(0.5, -1.0, 0.25),
    )

    assert submitted["mesh"] is meshes[(lot_rotation + 1) % 4]


@pytest.mark.parametrize("lot_rotation", range(4))
@pytest.mark.parametrize("prop_rotation", range(4))
def test_world_fixed_rkt1_shadow_keeps_rotation_zero_caster(
    lot_rotation, prop_rotation
):
    import sc4pimx.SC4LotPreview as preview

    meshes = [object(), object(), object(), object()]
    model = object.__new__(preview.SC4Model)
    model.s3dMeshes = [meshes]
    submitted = {}
    rot_mapping = [2, 1, 0, 3]
    rot2d = lot_rotation * 90.0
    camera = (
        preview.SC4Matrix.scale(2.0, 2.0, -2.0)
        @ preview.SC4Matrix.rotate_x(30.0)
        @ preview.SC4Matrix.rotate_y(rot2d - 22.5)
    )
    world_light = numpy.asarray((0.5, -1.0, 0.25))

    class Dummy:
        SHADOW_PROJECTOR_YAW = preview.LotEditorWin.SHADOW_PROJECTOR_YAW
        shadowLockToView = False
        _render_context = preview.TransformStack(model=camera)

        def _shadow_light_dir(self):
            return tuple(world_light)

        def _submit_s3d_model(self, chosen, _shader, _lighting, _batches, **kwargs):
            submitted["mesh"] = chosen
            submitted["model"] = self._render_context.model.copy()
            submitted["projection"] = kwargs["shadow_projection"]

    combined_rotation = (lot_rotation + rot_mapping[prop_rotation]) % 4
    preview.LotEditorWin._draw_state_member(
        Dummy(),
        model,
        (0.0, 0.0, 0.0),
        rot2d,
        combined_rotation,
        prop_rotation,
        0,
        object(),
        None,
        {},
        shadow=True,
        shadow_direction=tuple(world_light),
    )

    # With a world-fixed light the caster must not change when only the lot
    # camera rotates. The outer camera still rotates the completed shadow on
    # screen, but the mesh and its local projector stay at their rotation-0
    # values for this prop orientation.
    expected_mesh = meshes[(rot_mapping[prop_rotation] + 1) % 4]
    expected_model = camera @ preview.SC4Matrix.rotate_y(
        preview.LotEditorWin.SHADOW_PROJECTOR_YAW
    )
    expected_direction = (
        preview.SC4Matrix.rotate_y(-preview.LotEditorWin.SHADOW_PROJECTOR_YAW)[0:3, 0:3]
        @ world_light
    )
    assert submitted["mesh"] is expected_mesh
    assert submitted["model"] == pytest.approx(expected_model, abs=1.0e-12)
    assert submitted["projection"][0] == pytest.approx(expected_direction, abs=1.0e-6)
    assert submitted["projection"][1] == 0.0


def test_rkt0_prop_rotation_and_projector_turn_share_one_local_frame():
    import sc4pimx.SC4LotPreview as preview

    mesh = object()
    model = object.__new__(preview.SC4ModelMesh)
    model.mainMesh = mesh
    submitted = {}

    class Dummy:
        SHADOW_PROJECTOR_YAW = preview.LotEditorWin.SHADOW_PROJECTOR_YAW
        _render_context = preview.TransformStack()

        def _shadow_light_dir(self):
            return (0.5, -1.0, 0.25)

        def _submit_s3d_model(self, _mesh, _shader, _lighting, _batches, **kwargs):
            submitted["model"] = self._render_context.model.copy()
            submitted["projection"] = kwargs["shadow_projection"]

    dummy = Dummy()
    # rotFlag 1 applies +90 degrees in the existing RKT0 placement path; the
    # Mac projector's -90-degree turn must cancel it in the same local frame.
    preview.LotEditorWin._draw_state_member(
        dummy, model, (0.0, 0.0, 0.0), 0.0, 0, 1, 0,
        object(), None, {}, shadow=True, shadow_direction=(0.5, -1.0, 0.25),
    )

    assert submitted["model"] == pytest.approx(preview.SC4Matrix.identity(), abs=1.0e-12)
    assert submitted["projection"][0] == pytest.approx((0.5, -1.0, 0.25))


@pytest.mark.parametrize("lot_rotation", range(4))
@pytest.mark.parametrize("prop_rotation", range(4))
def test_rkt0_shadow_matches_north_reference_at_every_lot_rotation(
    lot_rotation, prop_rotation
):
    import sc4pimx.SC4LotPreview as preview

    model = object.__new__(preview.SC4ModelMesh)
    model.mainMesh = object()
    submitted = {}
    rot_mapping = [180, -90, 0, 90]
    rot2d = lot_rotation * 90.0
    camera = (
        preview.SC4Matrix.scale(2.0, 2.0, -2.0)
        @ preview.SC4Matrix.rotate_x(30.0)
        @ preview.SC4Matrix.rotate_y(rot2d - 22.5)
    )

    class Dummy:
        SHADOW_PROJECTOR_YAW = preview.LotEditorWin.SHADOW_PROJECTOR_YAW
        _render_context = preview.TransformStack(model=camera)

        def _shadow_light_dir(self):
            return (0.5, -1.0, 0.25)

        def _submit_s3d_model(self, _mesh, _shader, _lighting, _batches, **kwargs):
            submitted["basis"] = self._render_context.model[0:3, 0:3].copy()
            submitted["projection"] = kwargs["shadow_projection"]

    north_camera_basis = (
        preview.SC4Matrix.scale(2.0, 2.0, -2.0)
        @ preview.SC4Matrix.rotate_x(30.0)
        @ preview.SC4Matrix.rotate_y(-22.5)
    )[0:3, 0:3]
    expected_basis = (
        north_camera_basis
        @ preview.SC4Matrix.rotate_y(-rot_mapping[prop_rotation])[0:3, 0:3]
        @ preview.SC4Matrix.rotate_y(preview.LotEditorWin.SHADOW_PROJECTOR_YAW)[0:3, 0:3]
    )
    north_light = numpy.asarray((0.5, -1.0, 0.25))
    locked_light = (
        preview.SC4Matrix.rotate_y(-rot2d)[0:3, 0:3] @ north_light
    )
    expected_direction = (
        preview.SC4Matrix.rotate_y(
            rot_mapping[prop_rotation] - preview.LotEditorWin.SHADOW_PROJECTOR_YAW
        )[0:3, 0:3]
        @ north_light
    )

    preview.LotEditorWin._draw_state_member(
        Dummy(),
        model,
        (0.0, 0.0, 0.0),
        rot2d,
        lot_rotation,
        prop_rotation,
        0,
        object(),
        None,
        {},
        shadow=True,
        shadow_direction=tuple(locked_light),
    )

    assert submitted["basis"] == pytest.approx(expected_basis, abs=1.0e-12)
    assert submitted["projection"][0] == pytest.approx(expected_direction, abs=1.0e-6)
    assert submitted["projection"][1] == 0.0


def test_context_ui_state_is_3d_only_icon_safe_and_does_not_persist_variation():
    from sc4pimx.SC4LotPreview import (
        LAYER_CITY_CONTEXT,
        LotEditorWin,
    )
    from sc4pimx.SC4OpenGL import MyCanvasBase

    class Dummy:
        _default_visible_layers = LotEditorWin._default_visible_layers

    dummy = Dummy()

    class Button:
        def Enable(self, enabled):
            self.enabled = enabled

    dummy.contextMenuBtn = Button()
    LotEditorWin._update_context_buttons(dummy)
    assert dummy.contextMenuBtn.enabled is False

    layers_2d = LotEditorWin._default_visible_layers(dummy, "2d")
    migrated_3d = LotEditorWin._load_visible_layers(
        dummy,
        {"terrain_background": False},
        "3d",
    )
    assert LAYER_CITY_CONTEXT not in layers_2d
    assert migrated_3d[LAYER_CITY_CONTEXT] is False

    candidates = MyCanvasBase._attribute_candidates()
    assert candidates[0][3] == 8
    assert candidates[-1][3] == 0

    # The icon guard returns before touching GL or even consulting visibility.
    dummy._icon_render = True
    dummy._context_mesh = object()
    LotEditorWin.DrawCityContext(dummy)
    LotEditorWin.DrawCityContextShadows(dummy, None)

    dummy.visibleLayers2D = layers_2d
    dummy.visibleLayers3D = migrated_3d
    dummy.previewDate = date(2026, 7, 13)
    dummy.previewMinutes = 720
    dummy.showInactiveProps = False
    dummy._contextNonce = 42
    state = LotEditorWin._editor_state(dummy)
    assert "_contextNonce" not in state
    assert "ContextNonce" not in state
