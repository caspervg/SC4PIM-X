import pytest

from sc4pimx.SC4CurveEditor import (
    is_curve_property,
    padded_axis_ranges,
    points_to_value_text,
    values_to_points,
)


class Prop:
    values = [0.0, 1.0, 0.5, 0.75]


class PropDef:
    Type = "Float32"
    Count = -4


def test_float32_negative_even_count_values_are_curve_editable():
    assert is_curve_property(Prop(), PropDef())


def test_string_count_from_metadata_is_supported():
    prop_def = PropDef()
    prop_def.Count = "-4"

    assert is_curve_property(Prop(), prop_def)


def test_odd_value_count_is_not_curve_editable():
    prop = Prop()
    prop.values = [0.0, 1.0, 0.5]

    assert not is_curve_property(prop, PropDef())


def test_curve_points_round_trip_to_property_value_text():
    points = values_to_points([0.0, 1.0, 0.5, 0.75])

    assert points == [(0.0, 1.0), (0.5, 0.75)]
    assert points_to_value_text(points) == "0.0,1.0,0.5,0.75"


def test_padded_axis_ranges_add_margin_around_data_extent():
    x_axis, y_axis = padded_axis_ranges([(0.0, 10.0), (100.0, 20.0)], padding=0.1)

    assert x_axis == (-10.0, 110.0)
    assert y_axis == (9.0, 21.0)


def test_padded_axis_ranges_handle_flat_data():
    x_axis, y_axis = padded_axis_ranges([(5.0, 0.0), (5.0, 0.0)], padding=0.1)

    assert x_axis == (4.5, 5.5)
    assert y_axis == (-1.0, 1.0)


def test_padded_axis_ranges_reject_non_finite_values():
    with pytest.raises(ValueError):
        padded_axis_ranges([(0.0, 1.0), (float("inf"), 2.0)])
