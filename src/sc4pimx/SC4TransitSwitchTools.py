"""Building-exemplar Transit-Switch (TSEC) editor.

The "TSEC" cluster of building-exemplar properties tells the SC4 traffic sim
that walking through this building lets a Sim change travel type:

* ``0xE90E25A1`` Transit Switch Point -- ``Uint8 Count=-4`` array, packed in
  groups of 4 bytes per switch row. Each row is
  ``(art, edges, from_travel, to_travel)``:

  ====== =============================================================
  byte   meaning
  ====== =============================================================
  0      direction flag (Art) -- ``0x81`` Outside→Inside,
         ``0x82`` Inside→Outside
  1      edge mask (4-bit N/W/E/S; S=0x10, E=0x20, N=0x40, W=0x80;
         common combos: 0xF0 all sides, 0xA0 W+E, 0x50 N+S)
  2      from-travel -- 0 Walk, 1 Car, 2 Bus, 3 Train, 4 FreightTruck,
         5 FreightTrain, 6 Subway, 7 ElTrain, 8 Monorail
  3      to-travel -- same enum
  ====== =============================================================

* ``0xE90E25A2`` Transit Switch Entry Cost (``Float32``, seconds per tile).
* ``0xE90E25A3`` Transit Switch Traffic Capacity (``Float32``).

The byte semantics, the 16-combo edge-mask table, the two-direction Art
enum, and the 9 travel types are all ported directly from SC4Tool's
``SwitchGrid.cs`` (see ``.claude/extra-info/SC4Tool/SwitchGrid.cs``); the
edge-mask values are also the OPTION values listed under
``0xe90e25a1`` in ``assets/new_properties.xml`` (lines 9017--9050).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

import wx
import wx.lib.mixins.listctrl as listmix

from .translation import *  # noqa: F401,F403

logger = logging.getLogger(__name__)


# Building-exemplar properties this editor speaks for.
PROP_TRANSIT_SWITCH_POINT = 0xE90E25A1
PROP_TRANSIT_SWITCH_ENTRY_COST = 0xE90E25A2
PROP_TRANSIT_SWITCH_TRAFFIC_CAPACITY = 0xE90E25A3

SWITCH_ROW_SIZE = 4

# Direction flag (byte 0). SC4Tool only ever exposed these two values.
ART_OUTSIDE_TO_INSIDE = 0x81
ART_INSIDE_TO_OUTSIDE = 0x82
SWITCH_ART_LIST: tuple[tuple[int, str], ...] = (
    (ART_OUTSIDE_TO_INSIDE, LEXTransitSwitchArtIn),
    (ART_INSIDE_TO_OUTSIDE, LEXTransitSwitchArtOut),
)
SWITCH_ART_LABELS = {value: label for value, label in SWITCH_ART_LIST}

# Edge-mask bits (byte 1). Matches both new_properties.xml OPTIONs at
# 9017-9046 and SwitchGrid.cs::GetDirectionString lines 704-744.
EDGE_BIT_SOUTH = 0x10
EDGE_BIT_EAST = 0x20
EDGE_BIT_NORTH = 0x40
EDGE_BIT_WEST = 0x80
EDGE_BITS_ALL = EDGE_BIT_NORTH | EDGE_BIT_EAST | EDGE_BIT_SOUTH | EDGE_BIT_WEST

# Travel types (bytes 2 and 3). Names are translation-key indirected.
TRAVEL_WALK = 0
TRAVEL_CAR = 1
TRAVEL_BUS = 2
TRAVEL_TRAIN = 3
TRAVEL_FREIGHT_TRUCK = 4
TRAVEL_FREIGHT_TRAIN = 5
TRAVEL_SUBWAY = 6
TRAVEL_EL_TRAIN = 7
TRAVEL_MONORAIL = 8

SWITCH_TRAVEL_TYPES: tuple[tuple[int, str], ...] = (
    (TRAVEL_WALK, LEXTransitSwitchTravelWalk),
    (TRAVEL_CAR, LEXTransitSwitchTravelCar),
    (TRAVEL_BUS, LEXTransitSwitchTravelBus),
    (TRAVEL_TRAIN, LEXTransitSwitchTravelTrain),
    (TRAVEL_FREIGHT_TRUCK, LEXTransitSwitchTravelFreightTruck),
    (TRAVEL_FREIGHT_TRAIN, LEXTransitSwitchTravelFreightTrain),
    (TRAVEL_SUBWAY, LEXTransitSwitchTravelSubway),
    (TRAVEL_EL_TRAIN, LEXTransitSwitchTravelElTrain),
    (TRAVEL_MONORAIL, LEXTransitSwitchTravelMonorail),
)
SWITCH_TRAVEL_LABELS = {value: label for value, label in SWITCH_TRAVEL_TYPES}

VALID_ART_BYTES = frozenset(value for value, _ in SWITCH_ART_LIST)
VALID_TRAVEL_BYTES = frozenset(value for value, _ in SWITCH_TRAVEL_TYPES)
# Edge mask: any 4-bit value picked from {S=0x10, E=0x20, N=0x40, W=0x80}.
# SC4Tool's GetDirectionString tabulates all 16 combos; we accept the same.
VALID_EDGE_BYTES = frozenset(range(0, 0xF0 + 1, 0x10))


@dataclass
class SwitchRow:
    """One ``(art, edges, from_travel, to_travel)`` switch entry.

    ``expert`` is set when any byte is outside the SC4Tool enum tables; such
    rows are surfaced read-only in the UI but kept faithfully on disk.
    """

    art: int
    edges: int
    frm: int
    to: int
    expert: bool = False
    raw: tuple[int, int, int, int] = field(default=(0, 0, 0, 0))

    def as_bytes(self) -> tuple[int, int, int, int]:
        if self.expert:
            return self.raw
        return (self.art & 0xFF, self.edges & 0xFF, self.frm & 0xFF, self.to & 0xFF)


def decode_switch_array(values: Iterable[int]) -> list[SwitchRow]:
    """Chunk a raw Uint8 list into typed ``SwitchRow`` records.

    Rows whose bytes don't all match the SC4Tool enums are flagged
    ``expert=True`` so the UI can show them read-only (mirrors SC4Tool's
    ``LotTile.m_MustExpert`` fallback).
    """
    rows: list[SwitchRow] = []
    buf = list(int(v) & 0xFF for v in values)
    # Tolerate trailing partial groups by truncating to a row boundary; the
    # alternative (raising) loses data and there's no value in that.
    usable = (len(buf) // SWITCH_ROW_SIZE) * SWITCH_ROW_SIZE
    if usable != len(buf):
        logger.warning(
            "TSEC array length %d is not a multiple of %d; truncating %d trailing byte(s)",
            len(buf),
            SWITCH_ROW_SIZE,
            len(buf) - usable,
        )
    for i in range(0, usable, SWITCH_ROW_SIZE):
        art, edges, frm, to = buf[i : i + SWITCH_ROW_SIZE]
        expert = (
            art not in VALID_ART_BYTES
            or edges not in VALID_EDGE_BYTES
            or frm not in VALID_TRAVEL_BYTES
            or to not in VALID_TRAVEL_BYTES
        )
        rows.append(
            SwitchRow(
                art=art,
                edges=edges,
                frm=frm,
                to=to,
                expert=expert,
                raw=(art, edges, frm, to),
            )
        )
    return rows


def encode_switch_array(rows: Iterable[SwitchRow]) -> list[int]:
    """Pack rows back into a flat Uint8 list ready for ``CreateAPropFromString``."""
    out: list[int] = []
    for row in rows:
        out.extend(row.as_bytes())
    return out


def format_switch_bytes(values: Iterable[int]) -> str:
    """Return Reader-style comma-separated byte hex for copy/paste editing."""
    return ",".join("0x%02X" % (int(value) & 0xFF) for value in values)


def parse_switch_bytes_text(text: str) -> list[int]:
    """Parse Reader-style raw TSEC byte text.

    Accepts commas, whitespace, or semicolons as separators, and accepts both
    prefixed and unprefixed hex bytes. Unknown switch-row byte combinations are
    allowed here; the table will show them as expert rows.
    """
    out: list[int] = []
    for token in re.split(r"[\s,;]+", str(text).strip()):
        if not token:
            continue
        try:
            value = int(token, 16) if not token.lower().startswith("0x") else int(token, 0)
        except ValueError as exc:
            raise ValueError(LEXTransitSwitchRawHexInvalidToken % token) from exc
        if value < 0 or value > 0xFF:
            raise ValueError(LEXTransitSwitchRawHexByteRange % token)
        out.append(value)
    if len(out) % SWITCH_ROW_SIZE:
        raise ValueError(LEXTransitSwitchRawHexCountError % SWITCH_ROW_SIZE)
    return out


def default_switch_row(through_travel: int = TRAVEL_WALK) -> SwitchRow:
    """Seed for the "Add row" button: ``Outside→Inside``, all sides, walk."""
    return SwitchRow(
        art=ART_OUTSIDE_TO_INSIDE,
        edges=EDGE_BITS_ALL,
        frm=TRAVEL_WALK,
        to=int(through_travel),
    )


# --- Display helpers --------------------------------------------------------


def art_label(value: int) -> str:
    return SWITCH_ART_LABELS.get(int(value) & 0xFF, "0x%02X" % (int(value) & 0xFF))


def travel_label(value: int) -> str:
    return SWITCH_TRAVEL_LABELS.get(int(value) & 0xFF, "0x%02X" % (int(value) & 0xFF))


def edge_label(value: int) -> str:
    """Edge-mask mnemonic matching the OPTION labels in
    ``new_properties.xml`` for property ``0xE90E25A1`` (lines 9017-9050):
    ``South``, ``South+East``, ``North+South+East``, ``West+North``,
    ``All Sides``, etc. The XML's join order is W-first when W is set,
    otherwise N-then-S-then-E.
    """
    mask = int(value) & 0xF0
    if mask == 0:
        return "—"
    if mask == EDGE_BITS_ALL:
        return LEXTransitSwitchEdgeAllSides
    parts: list[str] = []
    if mask & EDGE_BIT_WEST:
        parts.append(LEXTransitSwitchEdgeWest)
        if mask & EDGE_BIT_NORTH:
            parts.append(LEXTransitSwitchEdgeNorth)
        if mask & EDGE_BIT_EAST:
            parts.append(LEXTransitSwitchEdgeEast)
        if mask & EDGE_BIT_SOUTH:
            parts.append(LEXTransitSwitchEdgeSouth)
    else:
        if mask & EDGE_BIT_NORTH:
            parts.append(LEXTransitSwitchEdgeNorth)
        if mask & EDGE_BIT_SOUTH:
            parts.append(LEXTransitSwitchEdgeSouth)
        if mask & EDGE_BIT_EAST:
            parts.append(LEXTransitSwitchEdgeEast)
    return "+".join(parts)


class AutoWidthListCtrl(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin):
    """Report-mode ListCtrl whose last column auto-expands to fill width.

    Shared by the TSEC editor table and the preset wizard's preview list so
    both stretch to the dialog's current width.
    """

    def __init__(self, parent: wx.Window, **kwargs):
        wx.ListCtrl.__init__(self, parent, -1, style=wx.LC_REPORT | wx.LC_SINGLE_SEL, **kwargs)
        listmix.ListCtrlAutoWidthMixin.__init__(self)


def row_hex(row: SwitchRow) -> str:
    """Display the four bytes as ``"81 F0 00 02"`` for the Hex column."""
    return " ".join("%02X" % b for b in row.as_bytes())


def edges_from_bools(north: bool, east: bool, south: bool, west: bool) -> int:
    mask = 0
    if north:
        mask |= EDGE_BIT_NORTH
    if east:
        mask |= EDGE_BIT_EAST
    if south:
        mask |= EDGE_BIT_SOUTH
    if west:
        mask |= EDGE_BIT_WEST
    return mask


def bools_from_edges(edges: int) -> tuple[bool, bool, bool, bool]:
    """Return ``(north, east, south, west)`` from a packed edge mask."""
    e = int(edges) & 0xFF
    return (
        bool(e & EDGE_BIT_NORTH),
        bool(e & EDGE_BIT_EAST),
        bool(e & EDGE_BIT_SOUTH),
        bool(e & EDGE_BIT_WEST),
    )


# --- Per-row editor dialog --------------------------------------------------


class TSECRowDialog(wx.Dialog):
    """Port of SC4Tool's ``FormTransitSwitch`` + ``SwitchGrid`` user control.

    Lets the user edit one switch entry via combos + a N/W/E/S checkbox cross.
    Returns a ``SwitchRow`` on OK; ``None`` on Cancel. Validates that at
    least one edge is checked before allowing OK.
    """

    def __init__(self, parent: wx.Window, row: Optional[SwitchRow] = None):
        wx.Dialog.__init__(self, parent, -1, LEXTransitSwitchRowTitle, style=wx.DEFAULT_DIALOG_STYLE)
        seed = row if row is not None else default_switch_row()

        self.artChoice = wx.Choice(self, -1, choices=[label for _value, label in SWITCH_ART_LIST])
        self.fromChoice = wx.Choice(self, -1, choices=[label for _value, label in SWITCH_TRAVEL_TYPES])
        self.toChoice = wx.Choice(self, -1, choices=[label for _value, label in SWITCH_TRAVEL_TYPES])

        # The compass cross matches SC4Tool's PictureBox11 layout: N on top,
        # S on bottom, W on left, E on right.
        self.cbNorth = wx.CheckBox(self, -1, LEXTransitSwitchEdgeNorth)
        self.cbEast = wx.CheckBox(self, -1, LEXTransitSwitchEdgeEast)
        self.cbSouth = wx.CheckBox(self, -1, LEXTransitSwitchEdgeSouth)
        self.cbWest = wx.CheckBox(self, -1, LEXTransitSwitchEdgeWest)

        self.previewText = wx.TextCtrl(self, -1, "", style=wx.TE_READONLY | wx.TE_CENTER)
        self.previewText.SetMinSize((180, -1))

        self.okButton = wx.Button(self, wx.ID_OK)
        self.okButton.SetDefault()
        cancelButton = wx.Button(self, wx.ID_CANCEL)

        # Layout.
        sizer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(0, 2, 4, 8)
        grid.AddGrowableCol(1, 1)
        for label, ctrl in [
            (LEXTransitSwitchArt, self.artChoice),
            (LEXTransitSwitchTravelFrom, self.fromChoice),
            (LEXTransitSwitchTravelTo, self.toChoice),
        ]:
            grid.Add(wx.StaticText(self, -1, label), 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)
        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 8)

        sizer.Add(wx.StaticText(self, -1, LEXTransitSwitchEdgeMask), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        cross = wx.GridSizer(3, 3, 2, 2)
        for cell in (None, self.cbNorth, None, self.cbWest, None, self.cbEast, None, self.cbSouth, None):
            if cell is None:
                cross.Add((0, 0))
            else:
                cross.Add(cell, 0, wx.ALIGN_CENTER)
        sizer.Add(cross, 0, wx.ALIGN_CENTER | wx.ALL, 8)

        preview = wx.BoxSizer(wx.HORIZONTAL)
        preview.Add(wx.StaticText(self, -1, LEXTransitSwitchPreviewLabel), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        preview.Add(self.previewText, 1, wx.EXPAND)
        sizer.Add(preview, 0, wx.EXPAND | wx.ALL, 8)

        self.errorText = wx.StaticText(self, -1, "")
        self.errorText.SetForegroundColour(wx.Colour(160, 0, 0))
        sizer.Add(self.errorText, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        btns = wx.StdDialogButtonSizer()
        btns.AddButton(self.okButton)
        btns.AddButton(cancelButton)
        btns.Realize()
        sizer.Add(btns, 0, wx.EXPAND | wx.ALL, 8)

        self.SetSizerAndFit(sizer)

        # Bindings.
        for ctrl in (self.artChoice, self.fromChoice, self.toChoice):
            ctrl.Bind(wx.EVT_CHOICE, self._on_changed)
        for cb in (self.cbNorth, self.cbEast, self.cbSouth, self.cbWest):
            cb.Bind(wx.EVT_CHECKBOX, self._on_changed)
        self.okButton.Bind(wx.EVT_BUTTON, self._on_ok)

        # Seed.
        self._set_from_row(seed)
        self._refresh_preview()

    # --- internals ---------------------------------------------------------

    def _index_in(self, table: tuple[tuple[int, str], ...], value: int) -> int:
        for idx, (val, _label) in enumerate(table):
            if val == value:
                return idx
        return 0

    def _set_from_row(self, row: SwitchRow) -> None:
        self.artChoice.SetSelection(self._index_in(SWITCH_ART_LIST, row.art))
        self.fromChoice.SetSelection(self._index_in(SWITCH_TRAVEL_TYPES, row.frm))
        self.toChoice.SetSelection(self._index_in(SWITCH_TRAVEL_TYPES, row.to))
        north, east, south, west = bools_from_edges(row.edges)
        self.cbNorth.SetValue(north)
        self.cbEast.SetValue(east)
        self.cbSouth.SetValue(south)
        self.cbWest.SetValue(west)

    def _current_row(self) -> SwitchRow:
        art = SWITCH_ART_LIST[max(0, self.artChoice.GetSelection())][0]
        frm = SWITCH_TRAVEL_TYPES[max(0, self.fromChoice.GetSelection())][0]
        to = SWITCH_TRAVEL_TYPES[max(0, self.toChoice.GetSelection())][0]
        edges = edges_from_bools(
            self.cbNorth.GetValue(),
            self.cbEast.GetValue(),
            self.cbSouth.GetValue(),
            self.cbWest.GetValue(),
        )
        return SwitchRow(art=art, edges=edges, frm=frm, to=to)

    def _refresh_preview(self) -> None:
        row = self._current_row()
        self.previewText.SetValue(row_hex(row))
        # OK is disabled until at least one edge is selected; mirrors SC4Tool's
        # implicit guarantee that GetDirectionString never returns 0x00.
        valid = row.edges != 0
        self.okButton.Enable(valid)
        self.errorText.SetLabel("" if valid else LEXTransitSwitchNoEdgesError)

    def _on_changed(self, event: wx.Event) -> None:
        self._refresh_preview()
        event.Skip()

    def _on_ok(self, event: wx.Event) -> None:
        row = self._current_row()
        if row.edges == 0:
            self.errorText.SetLabel(LEXTransitSwitchNoEdgesError)
            return
        self.result = row
        event.Skip()

    # --- public API --------------------------------------------------------

    def GetRow(self) -> SwitchRow:
        return getattr(self, "result", self._current_row())


# --- Table panel -----------------------------------------------------------


class TSECTablePanel(wx.Panel):
    """The full TSEC editor: row table + cost/capacity numerics + preset hook.

    The panel is intentionally self-contained: ``set_state`` seeds it from
    raw property values, ``get_state`` returns the edited values. Persisting
    them to the exemplar is the caller's job (so this widget is reusable
    from both the right-click menu and the property double-click path).
    """

    def __init__(
        self,
        parent: wx.Window,
        on_apply_preset: Optional[Callable[[], None]] = None,
    ):
        wx.Panel.__init__(self, parent, -1)
        self._on_apply_preset = on_apply_preset
        self._rows: list[SwitchRow] = []

        self.list = AutoWidthListCtrl(self)
        for idx, (label, width) in enumerate(
            [
                (LEXTransitSwitchColHex, 110),
                (LEXTransitSwitchColArt, 150),
                (LEXTransitSwitchColEdges, 150),
                (LEXTransitSwitchColFrom, 110),
                (LEXTransitSwitchColTo, 110),
            ]
        ):
            self.list.InsertColumn(idx, label, width=width)
        self.list.SetMinSize((680, 220))

        self.addBtn = wx.Button(self, -1, LEXTransitSwitchAdd)
        self.editBtn = wx.Button(self, -1, LEXTransitSwitchEdit)
        self.dupBtn = wx.Button(self, -1, LEXTransitSwitchDuplicate)
        self.delBtn = wx.Button(self, -1, LEXTransitSwitchDelete)
        self.presetBtn = wx.Button(self, -1, LEXTransitSwitchApplyPreset)

        self.costText = wx.TextCtrl(self, -1, "", style=wx.TE_PROCESS_ENTER)
        self.capacityText = wx.TextCtrl(self, -1, "", style=wx.TE_PROCESS_ENTER)
        self.rawCheck = wx.CheckBox(self, -1, LEXTransitSwitchRawHexEnable)
        self.rawText = wx.TextCtrl(self, -1, "", style=wx.TE_MULTILINE)
        self.rawText.SetMinSize((680, 70))
        self.rawErrorText = wx.StaticText(self, -1, "")
        self.rawErrorText.SetForegroundColour(wx.Colour(160, 0, 0))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.list, 1, wx.EXPAND | wx.ALL, 6)

        btnRow = wx.BoxSizer(wx.HORIZONTAL)
        btnRow.Add(self.addBtn, 0, wx.RIGHT, 4)
        btnRow.Add(self.editBtn, 0, wx.RIGHT, 4)
        btnRow.Add(self.dupBtn, 0, wx.RIGHT, 4)
        btnRow.Add(self.delBtn, 0, wx.RIGHT, 4)
        btnRow.AddStretchSpacer(1)
        btnRow.Add(self.presetBtn, 0)
        sizer.Add(btnRow, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        sizer.Add(self.rawCheck, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 6)
        sizer.Add(self.rawText, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 6)
        sizer.Add(self.rawErrorText, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 6)

        numericGrid = wx.FlexGridSizer(0, 2, 4, 8)
        numericGrid.AddGrowableCol(1, 1)
        numericGrid.Add(wx.StaticText(self, -1, LEXTransitSwitchCost), 0, wx.ALIGN_CENTER_VERTICAL)
        numericGrid.Add(self.costText, 1, wx.EXPAND)
        numericGrid.Add(wx.StaticText(self, -1, LEXTransitSwitchCapacity), 0, wx.ALIGN_CENTER_VERTICAL)
        numericGrid.Add(self.capacityText, 1, wx.EXPAND)
        sizer.Add(numericGrid, 0, wx.EXPAND | wx.ALL, 6)

        self.SetSizerAndFit(sizer)

        # Bindings.
        self.addBtn.Bind(wx.EVT_BUTTON, self._on_add)
        self.editBtn.Bind(wx.EVT_BUTTON, self._on_edit)
        self.dupBtn.Bind(wx.EVT_BUTTON, self._on_duplicate)
        self.delBtn.Bind(wx.EVT_BUTTON, self._on_delete)
        self.presetBtn.Bind(wx.EVT_BUTTON, self._on_preset)
        self.rawCheck.Bind(wx.EVT_CHECKBOX, self._on_raw_toggle)
        self.rawText.Bind(wx.EVT_TEXT, self._on_raw_text)
        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda evt: self._on_edit(evt))
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_selection_changed)
        self.list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self._on_selection_changed)

        self._sync_raw_text()
        self._refresh_raw_controls()
        self._refresh_buttons()

    # --- public API --------------------------------------------------------

    def set_state(
        self,
        switch_bytes: Iterable[int],
        cost: Optional[float],
        capacity: Optional[float],
    ) -> None:
        self._rows = decode_switch_array(switch_bytes)
        self.costText.SetValue("" if cost is None else _format_float(cost))
        self.capacityText.SetValue("" if capacity is None else _format_float(capacity))
        self._fill_list()
        self._sync_raw_text()
        self._refresh_raw_controls()
        self._refresh_buttons()

    def get_state(self) -> tuple[list[SwitchRow], Optional[float], Optional[float]]:
        if not self.validate():
            raise ValueError(self.rawErrorText.GetLabel())
        return (list(self._rows), _parse_float(self.costText.GetValue()), _parse_float(self.capacityText.GetValue()))

    def get_switch_bytes(self) -> list[int]:
        if self.rawCheck.GetValue():
            self._apply_raw_text()
        return encode_switch_array(self._rows)

    def validate(self) -> bool:
        if self.rawCheck.GetValue():
            return self._apply_raw_text(show_message=True)
        return True

    # --- internals ---------------------------------------------------------

    def _fill_list(self) -> None:
        self.list.DeleteAllItems()
        for row_idx, row in enumerate(self._rows):
            label_art = art_label(row.art)
            if row.expert:
                label_art = "%s %s" % (label_art, LEXTransitSwitchExpertFlag)
            self.list.InsertItem(row_idx, row_hex(row))
            self.list.SetItem(row_idx, 1, label_art)
            self.list.SetItem(row_idx, 2, edge_label(row.edges))
            self.list.SetItem(row_idx, 3, travel_label(row.frm))
            self.list.SetItem(row_idx, 4, travel_label(row.to))
            if row.expert:
                self.list.SetItemTextColour(row_idx, wx.Colour(140, 80, 0))

    def _selected_index(self) -> int:
        return self.list.GetFirstSelected()

    def _refresh_buttons(self) -> None:
        idx = self._selected_index()
        has = idx >= 0
        raw_mode = self.rawCheck.GetValue()
        editable = has and not self._rows[idx].expert
        self.addBtn.Enable(not raw_mode)
        self.editBtn.Enable(not raw_mode and editable)
        self.dupBtn.Enable(not raw_mode and has)
        self.delBtn.Enable(not raw_mode and has)
        self.presetBtn.Enable(self._on_apply_preset is not None)
        self.list.Enable(not raw_mode)

    def _sync_raw_text(self) -> None:
        self.rawText.ChangeValue(format_switch_bytes(encode_switch_array(self._rows)))
        self.rawErrorText.SetLabel("")

    def _refresh_raw_controls(self) -> None:
        raw_mode = self.rawCheck.GetValue()
        self.rawText.Enable(raw_mode)
        self.rawErrorText.Show(raw_mode and bool(self.rawErrorText.GetLabel()))
        self.Layout()

    def _apply_raw_text(self, show_message: bool = False) -> bool:
        try:
            parsed = parse_switch_bytes_text(self.rawText.GetValue())
        except ValueError as exc:
            message = str(exc)
            self.rawErrorText.SetLabel(message)
            self.rawErrorText.Show(True)
            self.Layout()
            if show_message:
                wx.MessageBox(message, LEXTransitSwitchRawHexInvalidTitle, wx.OK | wx.ICON_ERROR, self)
            return False
        self.rawErrorText.SetLabel("")
        self.rawErrorText.Show(False)
        self._rows = decode_switch_array(parsed)
        self._fill_list()
        self._refresh_buttons()
        self.Layout()
        return True

    def _on_selection_changed(self, event: wx.Event) -> None:
        self._refresh_buttons()
        event.Skip()

    def _on_raw_toggle(self, event: wx.Event) -> None:
        if self.rawCheck.GetValue():
            self._sync_raw_text()
        elif not self._apply_raw_text(show_message=True):
            self.rawCheck.SetValue(True)
        else:
            self._sync_raw_text()
        self._refresh_raw_controls()
        self._refresh_buttons()
        event.Skip()

    def _on_raw_text(self, event: wx.Event) -> None:
        if self.rawCheck.GetValue():
            self.rawErrorText.SetLabel("")
            self.rawErrorText.Show(False)
            self.Layout()
        event.Skip()

    def _on_add(self, _event: wx.Event) -> None:
        dlg = TSECRowDialog(self)
        try:
            if dlg.ShowModal() == wx.ID_OK:
                self._rows.append(dlg.GetRow())
                self._fill_list()
                self._sync_raw_text()
                self._select(len(self._rows) - 1)
        finally:
            dlg.Destroy()

    def _on_edit(self, _event: wx.Event) -> None:
        idx = self._selected_index()
        if idx < 0:
            return
        row = self._rows[idx]
        if row.expert:
            wx.MessageBox(LEXTransitSwitchExpertWarning, LEXTransitSwitchExpertFlag, wx.OK | wx.ICON_INFORMATION, self)
            return
        dlg = TSECRowDialog(self, row)
        try:
            if dlg.ShowModal() == wx.ID_OK:
                self._rows[idx] = dlg.GetRow()
                self._fill_list()
                self._sync_raw_text()
                self._select(idx)
        finally:
            dlg.Destroy()

    def _on_duplicate(self, _event: wx.Event) -> None:
        idx = self._selected_index()
        if idx < 0:
            return
        clone = SwitchRow(**vars(self._rows[idx]))
        self._rows.insert(idx + 1, clone)
        self._fill_list()
        self._sync_raw_text()
        self._select(idx + 1)

    def _on_delete(self, _event: wx.Event) -> None:
        idx = self._selected_index()
        if idx < 0:
            return
        del self._rows[idx]
        self._fill_list()
        self._sync_raw_text()
        self._select(min(idx, len(self._rows) - 1))

    def _on_preset(self, _event: wx.Event) -> None:
        if self._on_apply_preset is not None:
            self._on_apply_preset()

    def _select(self, idx: int) -> None:
        if idx < 0 or idx >= self.list.GetItemCount():
            self._refresh_buttons()
            return
        self.list.Select(idx)
        self.list.Focus(idx)
        self._refresh_buttons()


def _format_float(value: float) -> str:
    """Round-trippable float display: keep precision, lose noisy trailing zeros."""
    s = "%.7g" % float(value)
    return s


def _parse_float(text: str) -> Optional[float]:
    text = text.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
