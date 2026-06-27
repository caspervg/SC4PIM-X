from types import SimpleNamespace

from sc4pimx.SC4PIMApp import _non_building_lot_object_rows


def prop(prop_id, object_type):
    return SimpleNamespace(id=prop_id, values=[object_type])


def test_non_building_lot_object_rows_selects_all_lot_object_types_except_building():
    props = [
        prop(0x00000010, 1),
        prop(0x88EDC900, 0),
        prop(0x88EDC901, 1),
        prop(0x88EDC902, 2),
        prop(0x88EDC903, 3),
        prop(0x88EDC904, 4),
        prop(0x88EDCE00, 1),
    ]

    assert _non_building_lot_object_rows(props) == [5, 6, 7, 8]


def test_non_building_lot_object_rows_ignores_malformed_empty_values():
    props = [SimpleNamespace(id=0x88EDC901, values=[])]

    assert _non_building_lot_object_rows(props) == []
