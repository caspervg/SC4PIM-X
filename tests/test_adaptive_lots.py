import pathlib
import struct
from types import SimpleNamespace

import pytest

from sc4pimx.SC4AdaptiveLots import (
    ADAPTIVE_COHORT_GROUP,
    CATEGORY_LOT_CONFIG,
    COHORT_TYPE,
    PROP_ADAPTIVE_TOOLTIP_DESC_KEY,
    PROP_ADAPTIVE_TOOLTIP_KEY,
    PROP_NETWORK_PIECE_MAP,
    WILDCARD_NETWORK,
    AdaptiveRow,
    building_id_for_lot,
    check_rows,
    hidden_building_ids,
    invalidate_adaptive_cache,
    known_piece_ids,
    lot_tooltip_description,
    lot_tooltip_name,
    rows_to_values,
    scan_adaptive_mappings,
    sort_rows,
    values_to_rows,
    variant_indices,
)
from sc4pimx.SC4DataFunctions import LOT_CONFIG_PROPERTY_FIRST
from sc4pimx.SC4DatTools import CreateAProp, DatFile, SC4Entry, SC4Exemplar
from sc4pimx.SC4PIMApp import _new_adaptive_mapping_entry, _write_entries_atomic
from sc4pimx.textutil import encode_sc4_text

ROAD = 0
STREET = 3
PIECE_A = 0x00004B00
PIECE_B = 0x5E54B200
LOT_A = 0x0C9DC024
LOT_B = 0x0C9DC023
BUILDING = 0x0C9DC024


def _row(network=ROAD, piece=PIECE_A, lot=LOT_A):
    return AdaptiveRow(network, piece, lot)


def _codes(problems):
    return {problem.code for problem in problems}


# -- rules ------------------------------------------------------------------


def test_valid_rows_have_no_problems():
    rows = [_row(), _row(lot=LOT_B), _row(STREET, PIECE_B, LOT_B)]
    assert check_rows(BUILDING, rows) == []


def test_zero_building_id_is_fatal():
    assert "no-building" in _codes(check_rows(0, [_row()]))


def test_no_rows_is_fatal():
    assert "empty" in _codes(check_rows(BUILDING, []))


def test_ragged_value_count_is_fatal():
    _rows, problems = values_to_rows([ROAD, PIECE_A, 0])
    assert "ragged" in _codes(problems)


def test_network_type_above_twelve_is_fatal():
    assert "bad-network" in _codes(check_rows(BUILDING, [_row(network=13)]))


def test_wildcard_row_must_have_zero_piece():
    assert "wildcard-piece" in _codes(
        check_rows(BUILDING, [_row(network=WILDCARD_NETWORK, piece=PIECE_A)]))
    assert check_rows(BUILDING, [_row(network=WILDCARD_NETWORK, piece=0)]) == []


def test_normal_row_must_have_non_zero_piece():
    assert "missing-piece" in _codes(check_rows(BUILDING, [_row(piece=0)]))


def test_zero_lot_config_is_fatal():
    assert "no-lot" in _codes(check_rows(BUILDING, [_row(lot=0)]))


def test_repeated_variant_index_in_one_ring_is_fatal():
    values = [ROAD, PIECE_A, 0, LOT_A, ROAD, PIECE_A, 0, LOT_B]
    _rows, problems = values_to_rows(values)
    assert "duplicate-variant" in _codes(problems)


def test_stored_variant_index_sets_the_order_not_the_file_order():
    """The DLL sorts by (network, piece, variant), so file order is not trusted.

    A package may list variant 1 before variant 0. Reading it in file order
    would show the wrong cycle and write a different one back.
    """
    stored = [ROAD, PIECE_A, 2, 0xCCC, ROAD, PIECE_A, 0, LOT_A, ROAD, PIECE_A, 1, LOT_B]
    rows, problems = values_to_rows(stored)

    assert problems == ()
    assert [row.lot_config_id for row in rows] == [LOT_A, LOT_B, 0xCCC]
    assert rows_to_values(rows)[3::4] == (LOT_A, LOT_B, 0xCCC)


def test_a_ring_may_be_interleaved_with_other_rings_in_the_file():
    """RTMT_Resource.dat stores all variant-0 rows first, then all variant-1."""
    stored = [
        ROAD, PIECE_A, 0, LOT_A, STREET, PIECE_B, 0, LOT_A,
        ROAD, PIECE_A, 1, LOT_B, STREET, PIECE_B, 1, LOT_B,
    ]
    rows, problems = values_to_rows(stored)

    assert problems == ()
    assert [row.ring for row in rows] == [
        (ROAD, PIECE_A), (ROAD, PIECE_A), (STREET, PIECE_B), (STREET, PIECE_B),
    ]
    assert [row.lot_config_id for row in rows] == [LOT_A, LOT_B, LOT_A, LOT_B]


def test_same_variant_index_in_different_rings_is_allowed():
    values = [ROAD, PIECE_A, 0, LOT_A, STREET, PIECE_B, 0, LOT_B]
    _rows, problems = values_to_rows(values)
    assert problems == ()


def test_unusable_network_types_warn_but_are_not_fatal():
    problems = check_rows(BUILDING, [_row(network=7)])  # Subway
    assert _codes(problems) == {"unusable-network"}
    assert not any(problem.is_fatal for problem in problems)


# -- ordering and flattening ------------------------------------------------


def test_rows_are_sorted_by_network_then_piece():
    rows = [_row(STREET, PIECE_B), _row(ROAD, PIECE_B), _row(ROAD, PIECE_A)]
    assert [row.ring for row in sort_rows(rows)] == [
        (ROAD, PIECE_A), (ROAD, PIECE_B), (STREET, PIECE_B),
    ]


def test_sort_keeps_the_authored_order_inside_a_ring():
    rows = [_row(lot=LOT_B), _row(lot=LOT_A)]
    assert [row.lot_config_id for row in sort_rows(rows)] == [LOT_B, LOT_A]


def test_each_ring_is_numbered_from_zero():
    rows = [_row(lot=LOT_A), _row(lot=LOT_B), _row(STREET, PIECE_B, LOT_A)]
    assert rows_to_values(rows) == (
        ROAD, PIECE_A, 0, LOT_A,
        ROAD, PIECE_A, 1, LOT_B,
        STREET, PIECE_B, 0, LOT_A,
    )


def test_values_round_trip_through_rows():
    rows = [_row(lot=LOT_A), _row(lot=LOT_B), _row(STREET, PIECE_B, LOT_A)]
    values = rows_to_values(rows)
    back, problems = values_to_rows(values)
    assert problems == ()
    assert rows_to_values(back) == values


def test_wildcard_survives_the_round_trip_unsigned():
    rows = [AdaptiveRow(WILDCARD_NETWORK, 0, LOT_A)]
    values = rows_to_values(rows)
    assert values[0] == 0xFFFFFFFF
    back, _problems = values_to_rows(values)
    assert back[0].network_type == 0xFFFFFFFF


# -- serialization ----------------------------------------------------------


def _property_registry():
    props = {
        0x899AFBAD: SimpleNamespace(ID=0x899AFBAD, Name="Item Name",
                                    Type="String", Count=1),
        PROP_NETWORK_PIECE_MAP: SimpleNamespace(
            ID=PROP_NETWORK_PIECE_MAP, Name="Adaptive Lot Network Piece Map",
            Type="Uint32", Count=-1),
        PROP_ADAPTIVE_TOOLTIP_KEY: SimpleNamespace(
            ID=PROP_ADAPTIVE_TOOLTIP_KEY, Name="Adaptive Lot Tooltip Key",
            Type="Uint32", Count=3),
        PROP_ADAPTIVE_TOOLTIP_DESC_KEY: SimpleNamespace(
            ID=PROP_ADAPTIVE_TOOLTIP_DESC_KEY,
            Name="Adaptive Lot Tooltip Description Key", Type="Uint32", Count=3),
    }
    return SimpleNamespace(properties=props)


def test_mapping_entry_uses_the_adaptive_cohort_tgi(tmp_path):
    package = tmp_path / "adaptive.SC4Desc"
    entry = _new_adaptive_mapping_entry(
        BUILDING, str(package), _property_registry(), [_row()])

    assert entry.tgi == (COHORT_TYPE, ADAPTIVE_COHORT_GROUP, BUILDING)
    _write_entries_atomic(str(package), [entry])
    assert package.is_file()


def test_rewriting_in_place_keeps_other_cohort_props(tmp_path):
    """The DLL reads tooltip props off the cohort, so an in-place edit must
    not drop them. _new_adaptive_mapping_entry carries extra text lines through
    and the piece map stays owned by the caller."""
    registry = _property_registry()
    extra = (
        '0xa0907c14:{"Adaptive Lot Tooltip Key"}=Uint32:0:(0x2026960b,0x1234,0x5678)',
        '0xa0907c15:{"Adaptive Lot Tooltip Description Key"}=Uint32:0:(0x2026960b,0x1234,0x5679)',
        '0xa0907c13:{"Adaptive Lot Network Piece Map"}=Uint32:0:(0xdeadbeef)',
    )
    entry = _new_adaptive_mapping_entry(
        BUILDING, str(tmp_path / "adaptive.SC4Desc"), registry, [_row()],
        extra_props=extra)

    exemplar = entry.exemplar
    assert exemplar.GetProp(PROP_ADAPTIVE_TOOLTIP_KEY) == [0x2026960B, 0x1234, 0x5678]
    assert exemplar.GetProp(PROP_ADAPTIVE_TOOLTIP_DESC_KEY) == [0x2026960B, 0x1234, 0x5679]
    # The stale piece map in extra_props is ignored; the caller owns it.
    assert exemplar.GetProp(PROP_NETWORK_PIECE_MAP) == [ROAD, PIECE_A, 0, LOT_A]


def test_mapping_entry_is_normalized_to_a_binary_cohort(tmp_path):
    entry = _new_adaptive_mapping_entry(
        BUILDING, str(tmp_path / "adaptive.SC4Desc"), _property_registry(), [_row()])

    assert entry.rawContent.startswith(b"CQZB1###")
    assert entry.exemplar.GetProp(PROP_NETWORK_PIECE_MAP) == [ROAD, PIECE_A, 0, LOT_A]


def test_wildcard_stays_unsigned_through_the_exemplar(tmp_path):
    """0xFFFFFFFF must not come back as -1; see test_signed_property_hex."""
    entry = _new_adaptive_mapping_entry(
        BUILDING, str(tmp_path / "adaptive.SC4Desc"), _property_registry(),
        [AdaptiveRow(WILDCARD_NETWORK, 0, LOT_A)])

    assert entry.exemplar.GetProp(PROP_NETWORK_PIECE_MAP)[0] == 0xFFFFFFFF


# -- scanning ---------------------------------------------------------------


class FakeExemplar:
    def __init__(self, props):
        self.props = dict(props)

    def GetProp(self, key):
        return self.props.get(key)


def _cohort(building_id, values, file_name="plugin.dat", group=ADAPTIVE_COHORT_GROUP,
            props=None):
    entry = SimpleNamespace(tgi=(COHORT_TYPE, group, building_id), fileName=file_name)
    entry.exemplar = FakeExemplar({PROP_NETWORK_PIECE_MAP: list(values), **(props or {})})
    return entry


def _dat(*cohorts):
    return SimpleNamespace(cohorts=list(cohorts), categories={})


def test_scan_reads_a_mapping_cohort():
    dat = _dat(_cohort(BUILDING, [ROAD, PIECE_A, 0, LOT_A]))
    mappings = scan_adaptive_mappings(dat)

    assert list(mappings) == [BUILDING]
    assert mappings[BUILDING].rows == (AdaptiveRow(ROAD, PIECE_A, LOT_A),)
    assert not mappings[BUILDING].is_rejected


def test_scan_ignores_cohorts_in_another_group():
    dat = _dat(_cohort(BUILDING, [ROAD, PIECE_A, 0, LOT_A], group=0xB03697D1))
    assert scan_adaptive_mappings(dat) == {}


def test_scan_marks_a_broken_cohort_as_rejected():
    dat = _dat(_cohort(BUILDING, [ROAD, 0, 0, LOT_A]))
    assert scan_adaptive_mappings(dat)[BUILDING].is_rejected


def test_scan_result_is_cached_until_invalidated():
    dat = _dat(_cohort(BUILDING, [ROAD, PIECE_A, 0, LOT_A]))
    scan_adaptive_mappings(dat)
    dat.cohorts = []
    assert list(scan_adaptive_mappings(dat)) == [BUILDING]

    invalidate_adaptive_cache(dat)
    assert scan_adaptive_mappings(dat) == {}


def test_a_cohort_carrying_an_exemplar_type_is_still_read():
    """SC4DatTools skips binary exemplars whose 0x10 is unknown to it.

    PIM-X writes no 0x10 into a mapping cohort, so its own files always parse.
    A cohort from another tool may carry one; this locks down that the scanner
    reads the property whenever the loader managed to parse it.
    """
    dat = _dat(_cohort(BUILDING, [ROAD, PIECE_A, 0, LOT_A], props={0x10: [0x28]}))
    assert list(scan_adaptive_mappings(dat)) == [BUILDING]


def test_known_piece_ids_skips_wildcards():
    dat = _dat(
        _cohort(BUILDING, [ROAD, PIECE_B, 0, LOT_A]),
        _cohort(LOT_B, [WILDCARD_NETWORK, 0, 0, LOT_A, STREET, PIECE_A, 0, LOT_B]),
    )
    assert known_piece_ids(dat) == [PIECE_A, PIECE_B]


# -- placement tooltip ------------------------------------------------


def _ltext_entry(text):
    """An LTEXT payload like make_ltext_entry builds: 2-byte length, 4096,
    then UTF-16-LE text after the 4-byte TGI header."""
    new_val = encode_sc4_text(text)
    content = struct.pack('H', len(text)) + struct.pack('H', 4096) + new_val
    return SimpleNamespace(content=content)


def _dat_with_lot(
    lot_id=LOT_A, get_prop=None, get_entry=None,
):
    """A virtual_dat where a lot configuration descriptor resolves *lot_id*.

    ``get_prop`` is the fake lot exemplar's GetProp (name/desc overrides);
    ``get_entry`` resolves LTEXT TGIs.
    """
    lot = SimpleNamespace(
        GetProp=get_prop or (lambda _pid: None),
        entry=SimpleNamespace(tgi=(0x6534284A, 0x1234, lot_id)),
    )
    cat = SimpleNamespace(descriptors=[SimpleNamespace(exemplar=lot)])
    dat = _dat()
    dat.categories = {CATEGORY_LOT_CONFIG: cat}
    dat.getEntry = get_entry or (lambda *_args: None)
    return dat, lot


def test_lot_tooltip_name_resolves_the_key():
    """The tooltip title is per replacement lot, read off its exemplar."""
    key = (0x2026960B, 0x1234, 0x5678)
    dat, _lot = _dat_with_lot(
        get_prop=lambda pid: key if pid == PROP_ADAPTIVE_TOOLTIP_KEY else None,
        get_entry=lambda t, g, i: _ltext_entry("  Custom Override Name  ")
        if (t, g, i) == key else None,
    )
    assert lot_tooltip_name(dat, LOT_A) == "Custom Override Name"


def test_lot_tooltip_name_is_none_without_a_key():
    dat, _lot = _dat_with_lot(get_entry=lambda *_a: _ltext_entry("whatever"))
    assert lot_tooltip_name(dat, LOT_A) is None


def test_lot_tooltip_description_is_none_without_a_key():
    dat, _lot = _dat_with_lot(get_entry=lambda *_a: _ltext_entry("whatever"))
    assert lot_tooltip_description(dat, LOT_A) is None


def test_zero_tooltip_key_reads_as_absent():
    """(0,0,0) is the conventional "no key"; the DLL treats it as absent."""
    dat, _lot = _dat_with_lot(
        get_prop=lambda pid: (0, 0, 0) if pid == PROP_ADAPTIVE_TOOLTIP_KEY else None,
    )
    assert lot_tooltip_name(dat, LOT_A) is None


def test_lot_tooltip_resolvers_stay_per_lot():
    """Two lots with different overrides resolve independently."""
    key_a, key_b = (0x2026960B, 0x1234, 0x5678), (0x2026960B, 0x1234, 0x5679)
    lot_a = SimpleNamespace(
        GetProp=lambda pid: key_a if pid == PROP_ADAPTIVE_TOOLTIP_KEY else None,
        entry=SimpleNamespace(tgi=(0x6534284A, 0x1234, LOT_A)),
    )
    lot_b = SimpleNamespace(
        GetProp=lambda pid: key_b if pid == PROP_ADAPTIVE_TOOLTIP_KEY else None,
        entry=SimpleNamespace(tgi=(0x6534284A, 0x1234, LOT_B)),
    )
    dat = _dat()
    dat.categories = {
        CATEGORY_LOT_CONFIG: SimpleNamespace(
            descriptors=[SimpleNamespace(exemplar=lot_a),
                         SimpleNamespace(exemplar=lot_b)]),
    }
    texts = {key_a: "Road A", key_b: "Road B"}
    dat.getEntry = lambda t, g, i: _ltext_entry(texts[(t, g, i)])

    assert lot_tooltip_name(dat, LOT_A) == "Road A"
    assert lot_tooltip_name(dat, LOT_B) == "Road B"


# -- lot to building --------------------------------------------------------


def _lot_exemplar(*rows):
    props = {LOT_CONFIG_PROPERTY_FIRST + index: values for index, values in enumerate(rows)}

    class LotExemplar(FakeExemplar):
        def GetPropRange(self, lo, hi):
            return {key: value for key, value in self.props.items() if lo <= key < hi}

    return LotExemplar(props)


def test_building_id_comes_from_the_type_zero_row():
    lot = _lot_exemplar([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, BUILDING])
    assert building_id_for_lot(lot) == BUILDING


def test_a_lot_without_a_building_row_resolves_to_none():
    lot = _lot_exemplar([7, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, BUILDING])
    assert building_id_for_lot(lot) is None


def test_a_lot_with_two_building_rows_resolves_to_none():
    row = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, BUILDING]
    assert building_id_for_lot(_lot_exemplar(row, list(row))) is None


# -- hidden buildings -------------------------------------------------------


def _mappings(*pairs):
    return {building: SimpleNamespace(rows=rows) for building, rows in pairs}


def test_a_replacement_building_is_hidden():
    mappings = _mappings((BUILDING, [_row(lot=LOT_B)]))
    hidden = hidden_building_ids(mappings, {LOT_B: 0xAAAA0001}.get)
    assert hidden == {0xAAAA0001}


def test_the_root_building_is_not_hidden():
    mappings = _mappings((BUILDING, [_row(lot=LOT_A)]))
    # LOT_A resolves back to the mapping key, so it is the ring's root.
    assert hidden_building_ids(mappings, {LOT_A: BUILDING}.get) == set()


def test_a_building_that_is_also_a_root_elsewhere_is_not_hidden():
    """The DLL builds the whole root set before it hides anything."""
    other = 0xAAAA0002
    mappings = _mappings(
        (BUILDING, [_row(lot=LOT_B)]),
        (other, []),
    )
    assert hidden_building_ids(mappings, {LOT_B: other}.get) == set()


def test_an_unresolvable_lot_hides_nothing():
    mappings = _mappings((BUILDING, [_row(lot=LOT_B)]))
    assert hidden_building_ids(mappings, lambda _lot: None) == set()


def test_a_missing_lot_building_is_not_hidden():
    """The DLL compacts absent lots away before building the hidden set."""
    mappings = _mappings((BUILDING, [_row(lot=LOT_B)]))
    hidden = hidden_building_ids(
        mappings, {LOT_B: 0xAAAA0001}.get, is_available=lambda lot_id: lot_id != LOT_B)
    assert hidden == set()


def test_an_installed_lot_building_is_still_hidden():
    mappings = _mappings((BUILDING, [_row(lot=LOT_B)]))
    hidden = hidden_building_ids(
        mappings, {LOT_B: 0xAAAA0001}.get, is_available=lambda lot_id: lot_id == LOT_B)
    assert hidden == {0xAAAA0001}


# -- tree window lifetime ---------------------------------------------------


class FakeEvent:
    def __init__(self, event_object=None):
        self.event_object = event_object
        self.skipped = False

    def GetEventObject(self):
        return self.event_object

    def Skip(self):
        self.skipped = True


def test_selection_callback_does_not_query_tree_during_rebuild():
    from sc4pimx.SC4AdaptiveLotDlg import AdaptiveLotTreeDialog

    def unexpected_call(*_args):
        raise AssertionError("selection state was queried during tree rebuild")

    dialog = SimpleNamespace(
        _closing=False, _rebuilding=True,
        _selected_data=unexpected_call, _update_details=unexpected_call,
    )
    event = FakeEvent()

    AdaptiveLotTreeDialog._on_selection(dialog, event)

    assert event.skipped


def test_dialog_teardown_unbinds_native_tree_callbacks():
    from sc4pimx.SC4AdaptiveLotDlg import AdaptiveLotTreeDialog

    class FakeTree:
        def __init__(self):
            self.unbound = []

        def Unbind(self, event_type):
            self.unbound.append(event_type)

    tree = FakeTree()
    dialog = SimpleNamespace(_closing=False, tree=tree)

    AdaptiveLotTreeDialog._deactivate_tree_events(dialog)

    assert dialog._closing
    assert len(tree.unbound) == 3


# -- editor variant numbering -----------------------------------------------


def test_each_ring_restarts_the_variant_index_at_zero():
    """The editor shows these numbers and rows_to_values writes them."""
    rows = sort_rows([_row(lot=LOT_A), _row(lot=LOT_B), _row(STREET, PIECE_B, LOT_A)])
    assert variant_indices(rows) == [0, 1, 0]
    assert rows_to_values(rows)[2::4] == (0, 1, 0)


def test_editor_refuses_to_move_a_row_into_another_ring():
    """sort_rows would undo the move, so the buttons must not offer it."""
    from sc4pimx.SC4AdaptiveLotDlg import AdaptiveMappingDialog

    rows = [_row(lot=LOT_A), _row(STREET, PIECE_B, LOT_B)]
    dialog = SimpleNamespace(_rows=list(rows), _selected_index=lambda: 0,
                             _refresh=lambda select=None: None)
    dialog._can_move = lambda index, delta: AdaptiveMappingDialog._can_move(
        dialog, index, delta)

    assert dialog._can_move(0, 1) is False
    AdaptiveMappingDialog._move(dialog, 1)
    assert dialog._rows == rows


def test_editor_can_move_a_row_inside_its_ring():
    from sc4pimx.SC4AdaptiveLotDlg import AdaptiveMappingDialog

    dialog = SimpleNamespace(_rows=[_row(lot=LOT_A), _row(lot=LOT_B)])
    assert AdaptiveMappingDialog._can_move(dialog, 0, 1) is True
    assert AdaptiveMappingDialog._can_move(dialog, 0, -1) is False
    assert AdaptiveMappingDialog._can_move(dialog, None, 1) is False


# -- row status and mapping notice ------------------------------------------


def _notes_dat(monkeypatch, hidden_building=None, in_submenu=(), known_lots=(LOT_A, LOT_B)):
    """A virtual dat stand-in wired for _adaptive_notes."""
    import sc4pimx.SC4AdaptiveLots as model
    import sc4pimx.SC4MenuScanner as menus
    from sc4pimx.SC4MenuScanner import BUILDING_EXEMPLAR_TYPE, MenuMember

    dat = SimpleNamespace(cohorts=[], categories={})
    monkeypatch.setattr(model, "scan_adaptive_mappings", lambda *_a, **_k: {})
    monkeypatch.setattr(model, "hidden_building_ids",
                        lambda *_a, **_k: {hidden_building} if hidden_building else set())
    monkeypatch.setattr(model, "building_id_for_lot_id",
                        lambda _dat, lot_id: hidden_building)
    monkeypatch.setattr(model, "lot_config_descriptor",
                        lambda _dat, lot_id: object() if lot_id in known_lots else None)
    members = [MenuMember(kind="building", name="Tower",
                          tgi=(BUILDING_EXEMPLAR_TYPE, 0x1234, b), via="exemplar")
               for b in in_submenu]
    monkeypatch.setattr(menus, "menu_members", lambda *_a, **_k: {0xAC706063: members})
    return dat


def test_row_status_reports_a_lot_that_is_not_installed(monkeypatch):
    from sc4pimx.SC4PIMApp import _adaptive_notes

    status_for_row, _notice = _adaptive_notes(_notes_dat(monkeypatch, known_lots=()))
    assert status_for_row(_row(lot=LOT_A))


def test_row_status_is_empty_for_an_installed_lot(monkeypatch):
    """A hidden building is the normal case, so it is never a per-row note."""
    from sc4pimx.SC4PIMApp import _adaptive_notes

    dat = _notes_dat(monkeypatch, hidden_building=0xAAAA0001, in_submenu=(0xAAAA0001,))
    status_for_row, _notice = _adaptive_notes(dat)
    assert status_for_row(_row(lot=LOT_A)) == ""


def test_no_notice_when_no_hidden_building_is_in_a_submenu(monkeypatch):
    from sc4pimx.SC4PIMApp import _adaptive_notes

    dat = _notes_dat(monkeypatch, hidden_building=0xAAAA0001, in_submenu=())
    _status, notice_for_mapping = _adaptive_notes(dat)
    assert notice_for_mapping([_row(lot=LOT_A)]) == ""


def test_notice_counts_buildings_once_not_rows(monkeypatch):
    """Many variants share one building; the count must not repeat it."""
    from sc4pimx.SC4PIMApp import _adaptive_notes

    dat = _notes_dat(monkeypatch, hidden_building=0xAAAA0001, in_submenu=(0xAAAA0001,))
    _status, notice_for_mapping = _adaptive_notes(dat)
    text = notice_for_mapping([_row(lot=LOT_A), _row(lot=LOT_B), _row(lot=LOT_A)])
    assert "1" in text


# -- end to end -------------------------------------------------------------


def test_the_property_is_registered_and_a_written_file_reads_back(tmp_path):
    """Write with the real property registry, then read the file back.

    This is the only check that new_properties.xml declares 0xA0907C13. Every
    other test supplies its own registry, so a missing definition would stay
    invisible until a KeyError in the save flow.
    """
    from sc4pimx.SC4VirtualDat import VirtualDat

    # ReadProperties only fills plain attributes, so it runs without the wx.App
    # that a real VirtualDat needs for its image lists.
    virtual_dat = SimpleNamespace(
        properties={}, categories={}, builtin_family_names={},
        lotStages={}, baseTex={}, zoning={}, rootCategory=None,
        MaxSlopeBeforeLotFoundation="90", MaxSlopeAllowed="90",
    )
    VirtualDat.ReadProperties(virtual_dat)
    assert PROP_NETWORK_PIECE_MAP in virtual_dat.properties

    rows = [_row(lot=LOT_A), _row(lot=LOT_B), AdaptiveRow(WILDCARD_NETWORK, 0, LOT_B)]
    package = tmp_path / "AdaptiveLot.SC4Desc"
    entry = _new_adaptive_mapping_entry(BUILDING, str(package), virtual_dat, rows)
    _write_entries_atomic(str(package), [entry])

    written = next(e for e in DatFile(str(package), None, False).entries
                   if tuple(e.tgi) == (COHORT_TYPE, ADAPTIVE_COHORT_GROUP, BUILDING))
    written.read_file(None, True, True)
    exemplar = SC4Exemplar(written, virtual_dat)

    back, problems = values_to_rows(exemplar.GetProp(PROP_NETWORK_PIECE_MAP))
    assert problems == ()
    assert check_rows(BUILDING, back) == []
    assert back == tuple(sort_rows(rows))


# -- tooltip LTEXT planning ------------------------------------------------


def _planning_dat():
    """A virtual_dat stand-in for _plan_tooltip_ltext (no existing LTEXTs)."""
    return SimpleNamespace(
        properties=_property_registry().properties,
        getEntry=lambda *_: None,
    )


def test_plan_creates_a_fresh_ltext_for_new_tooltip_text():
    from sc4pimx.SC4PIMApp import _plan_tooltip_ltext

    key_prop, entries, removed = _plan_tooltip_ltext(
        _planning_dat(), PROP_ADAPTIVE_TOOLTIP_KEY, None, None, "Custom Name",
        "pkg.dat")

    assert key_prop
    assert key_prop.startswith("0xa0907c14")
    assert len(entries) == 1 and entries[0].tgi[0] == 0x2026960B
    assert removed == []


def test_plan_keeps_an_unchanged_existing_key():
    from sc4pimx.SC4PIMApp import _plan_tooltip_ltext

    dat = _planning_dat()
    old_key = (0x2026960B, 0x1234, 0x5678)
    key_prop, entries, removed = _plan_tooltip_ltext(
        dat, PROP_ADAPTIVE_TOOLTIP_KEY, old_key, "Same", "Same", "pkg.dat")

    assert key_prop == CreateAProp(dat.properties[PROP_ADAPTIVE_TOOLTIP_KEY], old_key)
    assert entries == []
    assert removed == []


class _LocalLtextDat:
    """A virtual_dat stand-in: resolves only *key* (as a local LTEXT), so an
    IID allocate can find a free candidate for every other tgi."""
    properties = _property_registry().properties

    def __init__(self, key):
        self._key = key

    def getEntry(self, t, g, i):
        if (t, g, i) == self._key:
            return SimpleNamespace(
                fileName="pkg.dat", entry=SimpleNamespace(tgi=(t, g, i)))
        return None


def test_plan_drops_the_key_and_removes_a_local_ltext_on_clear():
    from sc4pimx.SC4PIMApp import _plan_tooltip_ltext

    key = (0x2026960B, 0x1234, 0x5678)
    key_prop, entries, removed = _plan_tooltip_ltext(
        _LocalLtextDat(key), PROP_ADAPTIVE_TOOLTIP_KEY, key, "Old", "", "pkg.dat")

    assert key_prop is None
    assert entries == []
    assert removed == [key]


def test_plan_replaces_text_and_drops_the_old_local_ltext():
    from sc4pimx.SC4PIMApp import _plan_tooltip_ltext

    key = (0x2026960B, 0x1234, 0x5679)
    key_prop, entries, removed = _plan_tooltip_ltext(
        _LocalLtextDat(key), PROP_ADAPTIVE_TOOLTIP_DESC_KEY, key,
        "Old", "New", "pkg.dat")

    assert key_prop and key_prop.startswith("0xa0907c15")
    assert len(entries) == 1
    assert removed == [key]


# -- package rewrite --------------------------------------------------------

OTHER_TGI = (0x6534284A, 0x1234, 0x5678)


def _package_with_mapping(tmp_path, virtual_dat, extra_entry=True):
    package = tmp_path / "plugin.dat"
    entry = _new_adaptive_mapping_entry(BUILDING, str(package), virtual_dat, [_row()])
    entries = [entry]
    if extra_entry:
        other = SC4Entry(struct.pack("<IIIII", *OTHER_TGI, 0, 0), 0, str(package))
        other.content = other.rawContent = b"EQZT1###\r\nPropCount=0x00000000\r\n"
        other.Maj()
        entries.append(other)
    _write_entries_atomic(str(package), entries)
    return package, SimpleNamespace(GetAllEntriesFromFile=lambda name: [
        e for e in DatFile(name, None, False).entries])


def test_rewrite_replaces_the_mapping_and_keeps_the_other_entry(tmp_path):
    from sc4pimx.SC4PIMApp import _rewrite_package

    registry = _property_registry()
    package, dat = _package_with_mapping(tmp_path, registry)
    new_entry = _new_adaptive_mapping_entry(
        BUILDING, str(package), registry, [_row(lot=LOT_B)])

    backup = _rewrite_package(dat, str(package), new_entry.tgi, new_entry)

    assert pathlib.Path(backup).is_file()
    tgis = {tuple(e.tgi) for e in DatFile(str(package), None, False).entries}
    assert tgis == {(COHORT_TYPE, ADAPTIVE_COHORT_GROUP, BUILDING), OTHER_TGI}


def test_rewrite_removes_the_mapping_and_keeps_the_other_entry(tmp_path):
    from sc4pimx.SC4PIMApp import _rewrite_package

    package, dat = _package_with_mapping(tmp_path, _property_registry())

    _rewrite_package(dat, str(package), (COHORT_TYPE, ADAPTIVE_COHORT_GROUP, BUILDING))

    tgis = {tuple(e.tgi) for e in DatFile(str(package), None, False).entries}
    assert tgis == {OTHER_TGI}


def test_rewrite_deletes_a_package_that_held_only_the_mapping(tmp_path):
    """An empty DBPF would still load in the game, so the file goes away."""
    from sc4pimx.SC4PIMApp import _rewrite_package

    package, dat = _package_with_mapping(tmp_path, _property_registry(), extra_entry=False)

    backup = _rewrite_package(dat, str(package), (COHORT_TYPE, ADAPTIVE_COHORT_GROUP, BUILDING))

    assert not package.exists()
    assert pathlib.Path(backup).is_file()


OLD_LTEXT_TGI = (0x2026960B, 0x6A386D26, 0x10000001)


def test_rewrite_drops_a_tombstone_ltext_and_adds_a_new_one(tmp_path):
    """_rewrite_package can add and remove entries in the same pass."""
    from sc4pimx.SC4PIMApp import _rewrite_package

    registry = _property_registry()
    package, dat = _package_with_mapping(tmp_path, registry)
    new_entry = _new_adaptive_mapping_entry(
        BUILDING, str(package), registry, [_row(lot=LOT_B)])

    def _ltext(tgi, text):
        entry = SC4Entry(struct.pack("<IIIII", *tgi, 0, 0), 0, str(package))
        entry.content = entry.rawContent = (
            struct.pack("H", len(text)) + struct.pack("H", 4096) + encode_sc4_text(text))
        entry.Maj()
        return entry

    # Add an "old" LTEXT to the existing package without dropping the mapping.
    existing = [e for e in DatFile(str(package), None, False).entries]
    for e in existing:
        e.read_file(None, True, True)
    _write_entries_atomic(str(package), existing + [_ltext(OLD_LTEXT_TGI, "Old")])

    added_ltext = _ltext((0x2026960B, 0x6A386D26, 0x20000002), "New")

    _rewrite_package(dat, str(package), new_entry.tgi, new_entry,
                     additional=[added_ltext], remove_tgis=[OLD_LTEXT_TGI])

    tgis = {tuple(e.tgi) for e in DatFile(str(package), None, False).entries}
    assert tgis == {
        (COHORT_TYPE, ADAPTIVE_COHORT_GROUP, BUILDING),
        OTHER_TGI,
        (0x2026960B, 0x6A386D26, 0x20000002),
    }


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
