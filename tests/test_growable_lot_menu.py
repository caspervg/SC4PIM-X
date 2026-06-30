from sc4pimx.SC4PIMApp import (
    _BUILDING_EXEMPLAR_TYPE,
    _GROWABLE_LOT_AGRICULTURAL_FIELD_CATEGORY,
    _GROWABLE_LOT_RCI_CATEGORY,
    _can_create_growable_lot,
)


def category_matcher(*category_ids):
    return set(category_ids).__contains__


def test_agricultural_field_that_also_matches_rci_can_create_one_growable_lot_action():
    matches = category_matcher(
        _GROWABLE_LOT_AGRICULTURAL_FIELD_CATEGORY,
        _GROWABLE_LOT_RCI_CATEGORY,
    )

    assert _can_create_growable_lot(matches, _BUILDING_EXEMPLAR_TYPE)


def test_non_building_exemplar_cannot_create_growable_lot():
    matches = category_matcher(_GROWABLE_LOT_RCI_CATEGORY)

    assert not _can_create_growable_lot(matches, 0x00000000)
