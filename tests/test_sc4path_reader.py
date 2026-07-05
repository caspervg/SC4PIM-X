import pytest

from sc4pimx.SC4PathReader import (
    SC4PathParseError,
    SC4PathPoint,
    parse_sc4path,
    point_to_lot_2d,
    point_to_lot_3d,
    rotate_local_point,
)


SAMPLE_V11 = """SC4PATHS
1.1
2
3
0
-- Car_3_1
1
0
3
1
2
2.5,-8.0,0.0
2.5,8.0,0.0
-- Sim_3_1
2
0
3
1
2
2.5,-8.0,0.0
2.5,8.0,0.0
-- stopUK_car_1_255
2
1
0
1
255
2.54713,7.26555,0.0
-- stop_car_1_255
1
1
0
1
255
-2.51329,7.24569,0.0
-- stop_sim_a_0_255
1
2
1
0
255
-5.00628,6.41454,0.0
"""


def test_parse_v11_sample_with_names_and_stops():
    path_file = parse_sc4path(SAMPLE_V11)

    assert path_file.version == "1.1"
    assert path_file.terrain_key == 0
    assert len(path_file.paths) == 2
    assert len(path_file.stops) == 3
    assert path_file.paths[0].name == "Car_3_1"
    assert path_file.paths[0].comments == ("Car_3_1",)
    assert path_file.paths[0].transport == 1
    assert path_file.paths[0].entry_side == 3
    assert path_file.paths[0].exit_side == 1
    assert path_file.paths[0].points[0].x_east == pytest.approx(2.5)
    assert path_file.paths[0].points[0].y_north == pytest.approx(-8.0)
    assert path_file.paths[0].points[0].z_height == pytest.approx(0.0)
    assert path_file.stops[0].name == "stopUK_car_1_255"
    assert path_file.stops[0].comments == ("stopUK_car_1_255",)
    assert path_file.stops[0].drive_side == 2
    assert not path_file.warnings


def test_parse_v12_junction_key():
    path_file = parse_sc4path(
        """SC4PATHS
1.2
1
0
1
-- Train_0_1_J
3
0
0
1
1
2
-8.0,0.0,15.0
0.0,8.0,15.5
"""
    )

    assert path_file.version == "1.2"
    assert path_file.terrain_key == 1
    assert path_file.paths[0].junction_key == 1
    assert path_file.paths[0].points[-1].z_height == pytest.approx(15.5)


def test_duplicate_zero_path_warning():
    path_file = parse_sc4path(
        """SC4PATHS
1.0
2
0
-- Car_3_1
1
0
3
1
2
0,-8,0
0,8,0
-- Car_3_1_other
1
0
3
1
2
1,-8,0
1,8,0
"""
    )

    assert any("duplicate zero path number" in warning for warning in path_file.warnings)


def test_entry_exit_edge_warnings():
    path_file = parse_sc4path(
        """SC4PATHS
1.1
1
0
0
-- Car_bad
1
0
3
1
2
0,-7.0,0
0,7.0,0
"""
    )

    assert len(path_file.warnings) == 2
    assert "Entry point does not touch south edge" in path_file.warnings[0]
    assert "Exit point does not touch north edge" in path_file.warnings[1]


def test_invalid_header_raises():
    with pytest.raises(SC4PathParseError):
        parse_sc4path("NOTPATHS\n1.2\n0\n0\n0\n")


def test_point_transforms_and_orientation():
    point = SC4PathPoint(2.0, -8.0, 3.5)

    # Lot frame: +y South. Identity flips y_north; each step is 90 deg CW.
    assert rotate_local_point(point, 0).x_east == pytest.approx(2.0)
    assert rotate_local_point(point, 0).y_north == pytest.approx(8.0)
    assert rotate_local_point(point, 1).x_east == pytest.approx(-8.0)
    assert rotate_local_point(point, 1).y_north == pytest.approx(2.0)
    assert rotate_local_point(point, 2).x_east == pytest.approx(-2.0)
    assert rotate_local_point(point, 2).y_north == pytest.approx(-8.0)
    assert rotate_local_point(point, 3).x_east == pytest.approx(8.0)
    assert rotate_local_point(point, 3).y_north == pytest.approx(-2.0)
    assert point_to_lot_2d(1, 2, 0, point) == pytest.approx((26.0, 48.0))
    assert point_to_lot_3d(1, 2, 0, point) == pytest.approx((26.0, 3.65, 48.0))
