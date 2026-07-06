from types import SimpleNamespace

from sc4pimx import SC4VirtualDat


def test_finalize_incremental_yields_between_entry_batches(monkeypatch):
    monkeypatch.setattr(SC4VirtualDat, "FinalizeCategory", lambda _root: None)

    updated = []
    virtual_dat = SC4VirtualDat.VirtualDat.__new__(SC4VirtualDat.VirtualDat)
    virtual_dat.allEntries = [
        SimpleNamespace(tgi=(87304289, 0, index), bStandard=False)
        for index in range(5)
    ]
    virtual_dat.tree = SimpleNamespace(
        UpdateEntry=lambda entry, *_args: updated.append(entry)
    )
    virtual_dat.rootCategory = object()
    virtual_dat.standardModels = []
    virtual_dat.otherModels = []
    virtual_dat.atcs = []
    virtual_dat.allTextures = []

    statuses = []
    dialog = SimpleNamespace(
        SetStatus=lambda text, detail="": statuses.append((text, detail))
    )

    yields = list(virtual_dat.FinalizeIncremental(dialog, batch_size=2))

    assert len(yields) == 3
    assert virtual_dat.cohorts == virtual_dat.allEntries
    assert updated == virtual_dat.allEntries
    assert statuses[-1] == ("Building resource index...", "4 / 5 entries")
    assert virtual_dat.missing_pictures == []
    assert virtual_dat.missing_atc_pictures == []
