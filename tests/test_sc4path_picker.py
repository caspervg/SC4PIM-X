from sc4pimx import SC4PathPicker
from sc4pimx.SC4PathReader import SC4PathCatalogItem


def test_path_thumb_provider_prioritises_pending_visible_requests(monkeypatch):
    monkeypatch.setattr(SC4PathPicker.wx, "CallAfter", lambda func: None)

    provider = SC4PathPicker._PathThumbProvider()
    callback = lambda _iid, _bitmap: None
    for iid in range(1, 7):
        provider.Get(iid, callback)

    provider.RestrictTo([3, 4])

    assert set(provider._queue) == {1, 2, 3, 4, 5, 6}
    assert set(provider._queue_cb) == {1, 2, 3, 4, 5, 6}
    assert provider._queue[-2:] == [4, 3]


def test_path_thumb_provider_restrict_does_not_create_new_requests(monkeypatch):
    monkeypatch.setattr(SC4PathPicker.wx, "CallAfter", lambda func: None)

    provider = SC4PathPicker._PathThumbProvider()
    provider.RestrictTo([10, 11])

    assert provider._queue == []
    assert provider._queue_cb == {}


def test_transport_filter_rejects_entries_without_transports():
    dialog = SC4PathPicker.SC4PathPickerDialog.__new__(
        SC4PathPicker.SC4PathPickerDialog
    )
    dialog.search = type("Search", (), {"GetValue": lambda self: ""})()
    dialog._active_transports = {1}
    dialog._metadata_table = {0x1234: {"transports": set()}}

    item = SC4PathCatalogItem(
        iid=0x1234,
        gid=0,
        entry=None,
    )

    assert not SC4PathPicker.SC4PathPickerDialog._passes_filters(dialog, item)


def test_transport_filter_accepts_matching_transport():
    dialog = SC4PathPicker.SC4PathPickerDialog.__new__(
        SC4PathPicker.SC4PathPickerDialog
    )
    dialog.search = type("Search", (), {"GetValue": lambda self: ""})()
    dialog._active_transports = {1}
    dialog._metadata_table = {0x1234: {"transports": {1, 3}}}

    item = SC4PathCatalogItem(
        iid=0x1234,
        gid=0,
        entry=None,
    )

    assert SC4PathPicker.SC4PathPickerDialog._passes_filters(dialog, item)
