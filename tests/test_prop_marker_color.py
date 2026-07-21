import pytest

from sc4pimx.SC4LotPreview import (
    DEFAULT_PROP_MARKER_COLOR,
    format_prop_marker_color,
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
