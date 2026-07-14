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
    MAT_CONTACT,
    MAT_CURB,
    MAT_MARKING,
    MAT_PARKING_AISLE,
    MAX_BOXES,
    MAX_LIT_WINDOWS,
    MAX_TREES,
    PARKING_AISLE_M,
    PARKING_DEPTH_M,
    PARKING_STALL_M,
    ROADWAY_M,
    SIDEWALK_M,
    STYLE_CIVIC,
    STYLE_INDUSTRIAL,
    STYLE_MIXED,
    STYLE_RURAL,
    STYLE_SUBURBAN,
    STYLE_URBAN,
    TILE_M,
    _Grid,
    _make_parking,
    _palette_for_style,
    _Parcel,
    _parcel_falloff,
    _road_corridors,
    build_context_mesh,
    context_seed,
    default_context_seed,
    generate_city_context,
    infer_context_style,
    light_context_vertices,
    road_edges_from_flags,
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
    _make_parking(0.0, 0.0, 32.0, 32.0, parcel, rects, parking_details)
    separators = [
        rect
        for rect in parking_details
        if rect.material == MAT_MARKING and rect.z1 - rect.z0 == pytest.approx(PARKING_DEPTH_M)
    ]
    centers = sorted({round((rect.x0 + rect.x1) * 0.5, 3) for rect in separators})
    assert len(centers) >= 3
    assert all(b - a == pytest.approx(PARKING_STALL_M) for a, b in zip(centers, centers[1:]))
    assert any(rect.material == MAT_PARKING_AISLE for rect in rects)
    assert max(max(color) - min(color) for color in _palette_for_style(STYLE_SUBURBAN).values()) < 0.07


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

    assert mesh.vertex_count < 100_000
    assert mesh.vertices.shape[1] == mesh.detail_vertices.shape[1] == 9
    assert mesh.normals.shape == mesh.vertices[:, :3].shape
    assert mesh.detail_normals.shape == mesh.detail_vertices[:, :3].shape
    assert not mesh.vertices.flags.writeable
    assert not mesh.detail_vertices.flags.writeable
    assert not mesh.normals.flags.writeable
    assert not mesh.detail_normals.flags.writeable
    assert not mesh.night_vertices.flags.writeable
    assert len(mesh.night_vertices) <= MAX_LIT_WINDOWS * 6
    assert numpy.shares_memory(mesh.vertices, mesh.shadow_vertices)
    assert numpy.shares_memory(mesh.detail_vertices, mesh.detail_shadow_vertices)
    assert numpy.allclose(numpy.linalg.norm(mesh.normals, axis=1), 1.0, atol=1.0e-5)
    assert numpy.allclose(numpy.linalg.norm(mesh.detail_normals, axis=1), 1.0, atol=1.0e-5)

    large = generate_city_context(64, 64, road_edges_from_flags(12), STYLE_SUBURBAN, 123456)
    assert build_context_mesh(large).vertex_count < 100_000


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
        _render_context = None

        def _shadow_flatten_matrix(self):
            return numpy.identity(4)

        def _shadow_silhouette_matrix(self):
            return numpy.identity(4)

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


def test_atc_billboards_are_depth_tested_without_writing_depth(monkeypatch):
    import sc4pimx.SC4LotPreview as preview
    from sc4pimx.ATCReader import ATC
    from sc4pimx.SC4Renderer import TransformStack

    calls = []
    for name in ("glDepthFunc", "glDepthMask", "glDisable", "glEnable"):
        monkeypatch.setattr(preview, name, lambda *args, name=name: calls.append((name, args)))

    atc = ATC(None, None)
    atc.draw_le = lambda *_args: True
    atc.DrawGL = lambda *_args: calls.append(("draw", ()))

    class Dummy:
        _render_context = TransformStack()
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

    mvp = numpy.identity(4)
    assert preview._atc_anchor_depth(mvp, 0, 0, 5) > preview._atc_anchor_depth(mvp, 0, 0, -5)


@pytest.mark.parametrize(
    ("pitch", "yaw"),
    ((30, -22.5), (35, 67.5), (40, 157.5), (45, 247.5)),
)
def test_s3d_shadow_projection_uses_visible_silhouette_not_lod_volume(pitch, yaw):
    import sc4pimx.SC4LotPreview as preview
    from sc4pimx import SC4Matrix

    scene_model = (
        SC4Matrix.scale(0.25, 0.25, -0.25)
        @ SC4Matrix.translate(-20, 0, 8)
        @ SC4Matrix.rotate_x(pitch)
        @ SC4Matrix.rotate_y(yaw)
    )
    light_dir = (0.8, -1.0, 0.6)
    projection = preview._silhouette_shadow_matrix(scene_model, light_dir)

    # One metre of visible height becomes one metre of sun-directed shadow;
    # all source geometry is collapsed onto the lot ground.
    assert projection @ (0, 1, 0, 0) == pytest.approx((0.8, 0.0, 0.6, 0.0))
    assert projection[1] == pytest.approx((0.0, 0.0, 0.0, 0.0))
    assert numpy.linalg.matrix_rank(projection[:3, :3]) == 2

    # Camera pan and zoom must not alter the cached silhouette's proportions.
    other_view = (
        SC4Matrix.scale(2.0, 2.0, -2.0)
        @ SC4Matrix.translate(300, 40, -90)
        @ SC4Matrix.rotate_x(pitch)
        @ SC4Matrix.rotate_y(yaw)
    )
    assert preview._silhouette_shadow_matrix(other_view, light_dir) == pytest.approx(projection)


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

    dummy.contextRegenBtn = Button()
    dummy.contextResetBtn = Button()
    LotEditorWin._update_context_buttons(dummy)
    assert dummy.contextRegenBtn.enabled is False
    assert dummy.contextResetBtn.enabled is False

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
