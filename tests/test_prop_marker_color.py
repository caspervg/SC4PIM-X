import pytest

from sc4pimx.SC4LotPreview import (
    DEFAULT_PROP_MARKER_COLOR,
    LAYER_PROPS,
    MODE_EDIT_FLORA,
    MODE_EDIT_PROP,
    OVERLAY_COLOR_DEFAULTS,
    OVERLAY_COLOR_SPECS,
    OVERLAY_OPACITY_DEFAULTS,
    OVERLAY_OPACITY_SPECS,
    LotEditorWin,
    format_prop_marker_color,
    marker_detail_alpha,
    marker_overlay_alpha,
    parse_overlay_color,
    parse_overlay_opacity,
    parse_prop_marker_color,
)


def test_prop_marker_color_round_trip():
    color = parse_prop_marker_color("#3366CC")

    assert color == pytest.approx((0.2, 0.4, 0.8))
    assert format_prop_marker_color(color) == "#3366CC"


@pytest.mark.parametrize("value", [None, "", "yellow", "#12", "#GG0000"])
def test_invalid_prop_marker_color_falls_back_to_yellow(value):
    assert parse_prop_marker_color(value) == DEFAULT_PROP_MARKER_COLOR


def test_prop_marker_color_serialization_clamps_channels():
    assert format_prop_marker_color((-0.5, 0.5, 1.5)) == "#0080FF"


def test_each_configurable_overlay_has_one_setting_and_default():
    layer_keys = [layer_key for layer_key, _label, _setting, _default in OVERLAY_COLOR_SPECS]
    setting_keys = [setting for _layer, _label, setting, _default in OVERLAY_COLOR_SPECS]

    assert len(layer_keys) == len(set(layer_keys))
    assert len(setting_keys) == len(set(setting_keys))
    assert set(layer_keys) == set(OVERLAY_COLOR_DEFAULTS)
    assert set(layer_keys) == set(OVERLAY_OPACITY_DEFAULTS)
    assert set(layer_keys) == set(OVERLAY_OPACITY_SPECS)


def test_overlay_color_parser_uses_the_layer_default_on_invalid_input():
    default = (0.25, 0.5, 0.75)

    assert parse_overlay_color("invalid", default) == default


@pytest.mark.parametrize("value", [None, "", "invalid", object()])
def test_overlay_opacity_parser_uses_the_layer_default_on_invalid_input(value):
    assert parse_overlay_opacity(value, 0.65) == 0.65


def test_overlay_opacity_parser_clamps_percentages():
    assert parse_overlay_opacity(-10) == 0.0
    assert parse_overlay_opacity(65) == 0.65
    assert parse_overlay_opacity(120) == 1.0


def test_setting_overlay_color_invalidates_cached_pane_before_drawing():
    calls = []

    class Dummy:
        overlayColors = {LAYER_PROPS: DEFAULT_PROP_MARKER_COLOR}

        def SaveEditorState(self):
            calls.append("save")

        def _invalidate_pane_cache(self):
            calls.append("invalidate")

        def on_draw(self):
            calls.append("draw")

        _persist_overlay_color_change = LotEditorWin._persist_overlay_color_change

    dummy = Dummy()
    LotEditorWin.SetOverlayColor(dummy, LAYER_PROPS, (0.2, 0.4, 0.6))

    assert dummy.overlayColors[LAYER_PROPS] == (0.2, 0.4, 0.6)
    assert calls == ["save", "invalidate", "draw"]


def test_reset_all_overlay_colors_persists_and_redraws_once():
    calls = []

    class Dummy:
        overlayColors = {key: (0.1, 0.2, 0.3) for key in OVERLAY_COLOR_DEFAULTS}
        overlayOpacities = {key: 0.2 for key in OVERLAY_OPACITY_DEFAULTS}

        def SaveEditorState(self):
            calls.append("save")

        def _invalidate_pane_cache(self):
            calls.append("invalidate")

        def on_draw(self):
            calls.append("draw")

        _persist_overlay_color_change = LotEditorWin._persist_overlay_color_change

    dummy = Dummy()
    LotEditorWin.OnResetAllOverlayColors(dummy)

    assert dummy.overlayColors == OVERLAY_COLOR_DEFAULTS
    assert dummy.overlayColors is not OVERLAY_COLOR_DEFAULTS
    assert dummy.overlayOpacities == OVERLAY_OPACITY_DEFAULTS
    assert dummy.overlayOpacities is not OVERLAY_OPACITY_DEFAULTS
    assert calls == ["save", "invalidate", "draw"]


def test_marker_overlays_share_translucent_edit_and_idle_alpha():
    assert marker_overlay_alpha(MODE_EDIT_PROP, MODE_EDIT_PROP) == 0.65
    assert marker_overlay_alpha(MODE_EDIT_FLORA, MODE_EDIT_FLORA) == 0.65
    assert marker_overlay_alpha(0, MODE_EDIT_PROP) == 0.325
    assert marker_overlay_alpha(0, MODE_EDIT_FLORA) == 0.325


def test_marker_details_fade_more_gently_than_the_fill():
    assert marker_detail_alpha(0.0) == 0.0
    assert marker_detail_alpha(0.0625) == 0.5
    assert marker_detail_alpha(0.25) == pytest.approx(0.70710678)
    assert marker_detail_alpha(1.0) == 1.0


def test_setting_overlay_opacity_clamps_and_redraws():
    calls = []

    class Dummy:
        overlayOpacities = {LAYER_PROPS: 0.65}

        def _persist_overlay_color_change(self):
            calls.append("persist")

    dummy = Dummy()
    LotEditorWin.SetOverlayOpacity(dummy, LAYER_PROPS, 1.5)

    assert dummy.overlayOpacities[LAYER_PROPS] == 1.0
    assert calls == ["persist"]
