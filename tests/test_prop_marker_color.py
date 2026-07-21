import pytest

from sc4pimx.SC4LotPreview import (
    DEFAULT_PROP_MARKER_COLOR,
    LAYER_PROPS,
    OVERLAY_COLOR_DEFAULTS,
    OVERLAY_COLOR_SPECS,
    LotEditorWin,
    format_prop_marker_color,
    parse_overlay_color,
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


def test_overlay_color_parser_uses_the_layer_default_on_invalid_input():
    default = (0.25, 0.5, 0.75)

    assert parse_overlay_color("invalid", default) == default


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
    assert calls == ["save", "invalidate", "draw"]
