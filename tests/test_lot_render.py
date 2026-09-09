from types import SimpleNamespace

from sc4pimx import SC4PIMApp

# Exemplar-type entry id (tgi[0]) shared by buildings, props and lots.
EXEMPLAR = 1697917002


def _descriptor(tgi, exemplar_type):
    return SimpleNamespace(
        exemplar=SimpleNamespace(
            entry=SimpleNamespace(tgi=tgi),
            GetProp=lambda prop, _t=exemplar_type: [_t] if prop == 16 else None,
        )
    )


def test_human_size_scales_through_units():
    assert SC4PIMApp._human_size(0) == "0.0 B"
    assert SC4PIMApp._human_size(1536) == "1.5 KB"
    assert SC4PIMApp._human_size(150 * 1024) == "150.0 KB"
    assert SC4PIMApp._human_size(int(2.5 * 1024 * 1024)) == "2.5 MB"
    assert SC4PIMApp._human_size(3 * 1024**3) == "3.0 GB"


def test_iter_lot_descriptors_dedups_and_filters_by_type():
    lot_a = _descriptor((EXEMPLAR, 0xA, 0x1), 16)
    lot_b = _descriptor((EXEMPLAR, 0xA, 0x2), 16)
    building = _descriptor((EXEMPLAR, 0xA, 0x3), 2)
    non_exemplar = _descriptor((0xDEADBEEF, 0xA, 0x4), 16)
    virtual_dat = SimpleNamespace(
        categories={
            1: SimpleNamespace(descriptors=[lot_a, building]),
            # lot_a repeated across categories must yield once.
            2: SimpleNamespace(descriptors=[lot_a, lot_b, non_exemplar]),
        }
    )
    tgis = [d.exemplar.entry.tgi for d in SC4PIMApp._iter_lot_descriptors(virtual_dat)]
    assert tgis == [(EXEMPLAR, 0xA, 0x1), (EXEMPLAR, 0xA, 0x2)]


def test_iter_lot_descriptors_skips_unreadable_exemplars():
    def boom(_prop):
        raise ValueError("undecodable")

    bad = SimpleNamespace(exemplar=SimpleNamespace(entry=SimpleNamespace(tgi=(EXEMPLAR, 1, 1)), GetProp=boom))
    virtual_dat = SimpleNamespace(categories={1: SimpleNamespace(descriptors=[bad])})
    assert list(SC4PIMApp._iter_lot_descriptors(virtual_dat)) == []


def test_iter_lot_descriptors_empty_when_no_lots():
    building = _descriptor((EXEMPLAR, 0xA, 0x3), 2)
    virtual_dat = SimpleNamespace(categories={1: SimpleNamespace(descriptors=[building])})
    assert list(SC4PIMApp._iter_lot_descriptors(virtual_dat)) == []
