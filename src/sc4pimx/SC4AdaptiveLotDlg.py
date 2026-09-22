"""Adaptive Lots UI: a row editor, a mapping editor and a tree window.

The model is in :mod:`SC4AdaptiveLots`. This module only shows it and calls
the actions that the host frame supplies. Same split as the submenu dialogs.

Two rules govern the editor:

* The user never types a variant index. The position of a row in its ring
  supplies the index. Thus a repeated index, which makes the DLL discard the
  whole mapping, cannot occur.
* Rows always appear in the order the DLL sorts them. Thus the Tab key order
  in the game agrees with the editor.
"""

from __future__ import annotations

import typing

import wx

from .SC4AdaptiveLots import (
    UNUSABLE_NETWORK_TYPES,
    WILDCARD_NETWORK,
    AdaptiveRow,
    building_game_name,
    building_id_for_lot,
    check_rows,
    known_piece_ids,
    lot_config_descriptor,
    lot_game_name,
    lot_tooltip_description,
    lot_tooltip_name,
    scan_adaptive_mappings,
    sort_rows,
    variant_indices,
)
from .SC4OccupantGroupPicker import _centre_on_top_level, _monospace_font
from .SC4TransitLotTools import NETWORK_NAMES, NETWORK_TYPES
from .TablerIcons import dialog_button, icon_bitmap, icon_button, set_button_icon
from .translation import *  # noqa: F401,F403

_SEARCH_LIMIT = 200
_TREE_ICON_SIZE = 16


def network_label(network_type: int) -> str:
    """Menu text for a network type, marking the ones the game never reports."""
    if network_type == WILDCARD_NETWORK:
        return LEXAdaptiveRowWildcard
    name = NETWORK_NAMES.get(network_type, "0x%08X" % (network_type & 0xFFFFFFFF))
    label = "%d - %s" % (network_type, name)
    if network_type in UNUSABLE_NETWORK_TYPES:
        return LEXAdaptiveRowUnusable % label
    return label


def _parse_hex(raw: str) -> typing.Optional[int]:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        value = int(raw, 16)
    except ValueError:
        return None
    return value if 0 <= value <= 0xFFFFFFFF else None


def lot_label(virtual_dat, lot_config_id, descriptor=None):
    """``<exemplar name>  0x<id>  "<game name>"`` for one lot.

    Two names, because they answer different questions: the exemplar name is
    what the author called the lot, the game name is what the player reads in
    the menu. The game name is dropped when it repeats the exemplar name.
    """
    if descriptor is None:
        descriptor = lot_config_descriptor(virtual_dat, lot_config_id)
    parts = []
    if descriptor is not None:
        parts.append(str(descriptor.name))
    parts.append("0x%08X" % lot_config_id)
    game_name = lot_game_name(virtual_dat, lot_config_id)
    if game_name and (descriptor is None or game_name != str(descriptor.name)):
        parts.append('"%s"' % game_name)
    return "   ".join(parts)


def _lot_search_results(virtual_dat, query, limit=_SEARCH_LIMIT):
    """Lot configuration descriptors whose name contains *query*."""
    query = (query or "").strip().lower()
    if not query:
        return []
    from .SC4AdaptiveLots import CATEGORY_LOT_CONFIG

    category = (getattr(virtual_dat, "categories", None) or {}).get(CATEGORY_LOT_CONFIG)
    if category is None:
        return []
    found = []
    for descriptor in getattr(category, "descriptors", ()) or ():
        if query in str(descriptor.name).lower():
            found.append(descriptor)
            if len(found) >= limit:
                break
    return found


class AdaptiveRowDialog(wx.Dialog):
    """Collect one variant: a network, a piece ID and a replacement lot."""

    def __init__(self, parent, virtual_dat, row: typing.Optional[AdaptiveRow] = None):
        wx.Dialog.__init__(self, parent, -1, LEXAdaptiveRowDialogTitle,
                           style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.virtual_dat = virtual_dat
        self._lot_id = row.lot_config_id if row is not None else 0
        self._results = []

        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
        grid.AddGrowableCol(1)

        grid.Add(wx.StaticText(self, label=LEXAdaptiveRowNetworkLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        self.networkChoice = wx.Choice(self, -1, choices=[
            network_label(value) for value, _label, _short in NETWORK_TYPES
        ] + [network_label(WILDCARD_NETWORK)])
        self._network_values = [value for value, _label, _short in NETWORK_TYPES] + [WILDCARD_NETWORK]
        grid.Add(self.networkChoice, 1, wx.EXPAND)

        grid.Add(wx.StaticText(self, label=LEXAdaptiveRowPieceLabel), 0, wx.ALIGN_CENTER_VERTICAL)
        self.pieceCombo = wx.ComboBox(self, -1, style=wx.CB_DROPDOWN, choices=[
            "0x%08X" % piece for piece in known_piece_ids(virtual_dat)
        ])
        grid.Add(self.pieceCombo, 1, wx.EXPAND)

        pieceHelp = wx.StaticText(self, -1, LEXAdaptiveRowPieceHelp)
        pieceHelp.Wrap(460)

        lotBox = wx.StaticBoxSizer(wx.StaticBox(self, label=LEXAdaptiveRowLotLabel), wx.VERTICAL)
        host = lotBox.GetStaticBox()
        searchRow = wx.BoxSizer(wx.HORIZONTAL)
        self.searchCtrl = wx.SearchCtrl(host, -1, style=wx.TE_PROCESS_ENTER)
        self.searchCtrl.SetDescriptiveText(LEXAdaptiveRowSearchHint)
        searchRow.Add(self.searchCtrl, 1, wx.RIGHT | wx.EXPAND, 6)
        self.searchButton = wx.Button(host, -1, LEXAdaptiveRowSearch)
        set_button_icon(self.searchButton, "zoom-in")
        searchRow.Add(self.searchButton, 0)
        lotBox.Add(searchRow, 0, wx.EXPAND | wx.ALL, 6)

        self.lotList = wx.ListBox(host, -1, style=wx.LB_SINGLE)
        self.lotList.SetMinSize((440, 160))
        lotBox.Add(self.lotList, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 6)

        self.lotSummary = wx.StaticText(host, -1, "", style=wx.ST_ELLIPSIZE_END)
        self.lotSummary.SetFont(_monospace_font(self.lotSummary.GetFont()))
        lotBox.Add(self.lotSummary, 0, wx.EXPAND | wx.ALL, 6)

        # The DLL's tooltip overrides live on the replacement lot exemplar and
        # are keyed by lot config ID, so every variant (row) can show its own
        # title/description. These fields author that override for this row's
        # lot. Empty means "no override; use the DLL's default text".
        tooltipBox = wx.StaticBoxSizer(
            wx.StaticBox(self, label=LEXAdaptiveRowTooltipLabel), wx.VERTICAL)
        host2 = tooltipBox.GetStaticBox()
        tipGrid = wx.FlexGridSizer(cols=2, vgap=6, hgap=8)
        tipGrid.AddGrowableCol(1)
        tipGrid.Add(wx.StaticText(host2, label=LEXAdaptiveTooltipTitleLabel), 0,
                    wx.ALIGN_CENTER_VERTICAL)
        self.tooltipNameCtrl = wx.TextCtrl(host2, -1, "")
        self.tooltipNameCtrl.SetToolTip(LEXAdaptiveTooltipHelp)
        tipGrid.Add(self.tooltipNameCtrl, 1, wx.EXPAND)
        tipGrid.Add(wx.StaticText(host2, label=LEXAdaptiveTooltipDescriptionLabel), 0,
                    wx.ALIGN_CENTER_VERTICAL)
        self.tooltipDescriptionCtrl = wx.TextCtrl(host2, -1, "")
        self.tooltipDescriptionCtrl.SetToolTip(LEXAdaptiveTooltipHelp)
        tipGrid.Add(self.tooltipDescriptionCtrl, 1, wx.EXPAND)
        tooltipBox.Add(tipGrid, 0, wx.EXPAND | wx.ALL, 6)

        buttons = wx.StdDialogButtonSizer()
        self.okButton = dialog_button(self, wx.ID_OK)
        self.okButton.SetDefault()
        buttons.AddButton(self.okButton)
        buttons.AddButton(dialog_button(self, wx.ID_CANCEL))
        buttons.Realize()
        self.okButton.Bind(wx.EVT_BUTTON, self._on_ok)

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(grid, 0, wx.EXPAND | wx.ALL, 10)
        root.Add(pieceHelp, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        root.Add(lotBox, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        root.Add(tooltipBox, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        root.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizerAndFit(root)
        self.SetMinSize((520, 560))

        self.networkChoice.Bind(wx.EVT_CHOICE, self._on_network_changed)
        self.searchButton.Bind(wx.EVT_BUTTON, self._on_search)
        self.searchCtrl.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.lotList.Bind(wx.EVT_LISTBOX, self._on_lot_selected)

        self._select_network(row.network_type if row is not None else NETWORK_TYPES[0][0])
        if row is not None and row.piece_id:
            self.pieceCombo.SetValue("0x%08X" % row.piece_id)
        self._on_network_changed(None)
        self._update_lot_summary()

    # -- state --------------------------------------------------------------

    def _select_network(self, network_type):
        if network_type in self._network_values:
            self.networkChoice.SetSelection(self._network_values.index(network_type))
        else:
            self.networkChoice.SetSelection(0)

    def _selected_network(self):
        index = self.networkChoice.GetSelection()
        if index == wx.NOT_FOUND:
            return NETWORK_TYPES[0][0]
        return self._network_values[index]

    def _on_network_changed(self, event):
        # A wildcard ring applies where no exact piece matches. The DLL needs
        # its piece ID to be zero.
        wildcard = self._selected_network() == WILDCARD_NETWORK
        if wildcard:
            self.pieceCombo.SetValue("0x00000000")
        self.pieceCombo.Enable(not wildcard)
        if event is not None:
            event.Skip()

    def _on_search(self, event):
        self._results = _lot_search_results(self.virtual_dat, self.searchCtrl.GetValue())
        self.lotList.Set([
            lot_label(self.virtual_dat, d.exemplar.entry.tgi[2], descriptor=d)
            for d in self._results])
        if event is not None:
            event.Skip()

    def _on_lot_selected(self, event):
        index = self.lotList.GetSelection()
        if 0 <= index < len(self._results):
            self._lot_id = int(self._results[index].exemplar.entry.tgi[2]) & 0xFFFFFFFF
        self._update_lot_summary()
        if event is not None:
            event.Skip()

    def _update_lot_summary(self):
        """Show the lot and the building it places.

        The cohort key is a building ID, but the values are lot IDs. For much
        content the two IDs are equal, which hides the difference. Showing both
        keeps it visible.
        """
        if not self._lot_id:
            self.lotSummary.SetLabel(LEXAdaptiveRowNoLot)
            return
        descriptor = lot_config_descriptor(self.virtual_dat, self._lot_id)
        exemplar = getattr(descriptor, "exemplar", None)
        building_id = building_id_for_lot(exemplar) if exemplar is not None else None
        if building_id is None:
            self.lotSummary.SetLabel(LEXAdaptiveRowLotUnresolved)
            return
        self.lotSummary.SetLabel(LEXAdaptiveRowLotSummary % (
            "0x%08X" % self._lot_id, "0x%08X" % building_id))
        self._update_tooltip_fields()

    def _update_tooltip_fields(self):
        """Preload the tooltip overrides of the currently selected lot.

        Disabled (and cleared) when the lot is not installed, because the
        overrides must be written onto the lot exemplar's package.
        """
        descriptor = lot_config_descriptor(self.virtual_dat, self._lot_id) \
            if self._lot_id else None
        editable = descriptor is not None
        self.tooltipNameCtrl.Enable(editable)
        self.tooltipDescriptionCtrl.Enable(editable)
        if not editable:
            self.tooltipNameCtrl.SetValue("")
            self.tooltipDescriptionCtrl.SetValue("")
            return
        self.tooltipNameCtrl.SetValue(
            lot_tooltip_name(self.virtual_dat, self._lot_id) or "")
        self.tooltipDescriptionCtrl.SetValue(
            lot_tooltip_description(self.virtual_dat, self._lot_id) or "")

    # -- commit -------------------------------------------------------------

    def _on_ok(self, event):
        if not self._lot_id:
            wx.MessageBox(LEXAdaptiveRowNoLot, LEXAdaptiveRowDialogTitle, wx.OK | wx.ICON_ERROR, self)
            return
        network_type = self._selected_network()
        piece_id = 0 if network_type == WILDCARD_NETWORK else _parse_hex(self.pieceCombo.GetValue())
        if piece_id is None or (network_type != WILDCARD_NETWORK and piece_id == 0):
            wx.MessageBox(LEXAdaptiveRowBadPiece, LEXAdaptiveRowDialogTitle, wx.OK | wx.ICON_ERROR, self)
            return
        title = self.tooltipNameCtrl.GetValue().strip() if self.tooltipNameCtrl.IsEnabled() else ""
        description = (self.tooltipDescriptionCtrl.GetValue().strip()
                       if self.tooltipDescriptionCtrl.IsEnabled() else "")
        self._result = (AdaptiveRow(network_type, piece_id, self._lot_id), title, description)
        self.EndModal(wx.ID_OK)

    def GetResult(self) -> typing.Optional[tuple]:
        return getattr(self, "_result", None)


def open_adaptive_row_dialog(parent, virtual_dat, row=None):
    dlg = AdaptiveRowDialog(parent, virtual_dat, row=row)
    try:
        _centre_on_top_level(dlg, parent)
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.GetResult()
        return None
    finally:
        dlg.Destroy()


class AdaptiveMappingDialog(wx.Dialog):
    """Edit every variant of one catalog building.

    The DLL's placement tooltip title/description are authored per replacement
    lot through the row editor (see AdaptiveRowDialog); the dialog collects
    those edits and GetResult returns ``(rows, {lot_config_id: (title,
    description)})`` for the caller to apply.
    """

    def __init__(self, parent, virtual_dat, building_id, rows=(), status_for_row=None,
                 notice_for_mapping=None):
        wx.Dialog.__init__(
            self, parent, -1, LEXAdaptiveDialogTitle,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.virtual_dat = virtual_dat
        self.building_id = int(building_id) & 0xFFFFFFFF
        self._rows = list(sort_rows(rows))
        self._status_for_row = status_for_row or (lambda _row: "")
        self._notice_for_mapping = notice_for_mapping or (lambda _rows: "")
        self._tooltip_edits = {}

        name = building_game_name(virtual_dat, self.building_id)
        label = '0x%08X  "%s"' % (self.building_id, name) if name else "0x%08X" % self.building_id
        heading = wx.StaticText(self, -1, LEXAdaptiveDialogHeading % label)
        heading.Wrap(760)

        self.list = wx.ListCtrl(self, -1, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for index, (label, width) in enumerate((
            (LEXAdaptiveColNetwork, 170), (LEXAdaptiveColPiece, 110),
            (LEXAdaptiveColVariant, 70), (LEXAdaptiveColLot, 220),
            (LEXAdaptiveColStatus, 260),
        )):
            self.list.InsertColumn(index, label, width=width)
        self.list.SetMinSize((840, 260))

        self.status = wx.StaticText(self, -1, "", style=wx.ST_ELLIPSIZE_END)

        editRow = wx.BoxSizer(wx.HORIZONTAL)
        self.addButton = wx.Button(self, -1, LEXAdaptiveAdd)
        set_button_icon(self.addButton, "plus")
        self.changeButton = wx.Button(self, -1, LEXAdaptiveChange)
        set_button_icon(self.changeButton, "pencil")
        self.removeButton = wx.Button(self, -1, LEXAdaptiveRemove)
        set_button_icon(self.removeButton, "trash")
        self.upButton = icon_button(self, "fold-up", LEXAdaptiveMoveUp)
        self.downButton = icon_button(self, "fold-down", LEXAdaptiveMoveDown)
        for button in (self.addButton, self.changeButton, self.removeButton,
                       self.upButton, self.downButton):
            editRow.Add(button, 0, wx.RIGHT, 6)

        buttons = wx.StdDialogButtonSizer()
        self.okButton = dialog_button(self, wx.ID_OK)
        self.okButton.SetLabel(LEXAdaptiveSave)
        self.okButton.SetDefault()
        buttons.AddButton(self.okButton)
        buttons.AddButton(dialog_button(self, wx.ID_CANCEL))
        buttons.Realize()
        self.okButton.Bind(wx.EVT_BUTTON, self._on_ok)

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(heading, 0, wx.EXPAND | wx.ALL, 10)
        root.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        root.Add(editRow, 0, wx.EXPAND | wx.ALL, 10)
        root.Add(self.status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        root.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizerAndFit(root)
        self.SetMinSize((880, 560))

        self.addButton.Bind(wx.EVT_BUTTON, self._on_add)
        self.changeButton.Bind(wx.EVT_BUTTON, self._on_change)
        self.removeButton.Bind(wx.EVT_BUTTON, self._on_remove)
        self.upButton.Bind(wx.EVT_BUTTON, lambda _evt: self._move(-1))
        self.downButton.Bind(wx.EVT_BUTTON, lambda _evt: self._move(1))
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_selection)
        self.list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self._on_selection)
        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_change)

        self._refresh()

    # -- rows ---------------------------------------------------------------

    def _selected_index(self):
        index = self.list.GetFirstSelected()
        return index if index != wx.NOT_FOUND else None


    def _refresh(self):
        self._rows = list(sort_rows(self._rows))
        variants = variant_indices(self._rows)
        self.list.Freeze()
        try:
            self.list.DeleteAllItems()
            for index, row in enumerate(self._rows):
                self.list.InsertItem(index, network_label(row.network_type))
                self.list.SetItem(index, 1, "-" if row.is_wildcard else "0x%08X" % row.piece_id)
                self.list.SetItem(index, 2, str(variants[index]))
                self.list.SetItem(index, 3, lot_label(self.virtual_dat, row.lot_config_id))
                self.list.SetItem(index, 4, self._status_for_row(row))
        finally:
            self.list.Thaw()
        self._update_status()

    def _select(self, index):
        if 0 <= index < len(self._rows):
            self.list.Select(index)
            self.list.EnsureVisible(index)

    def _update_status(self):
        problems = check_rows(self.building_id, self._rows)
        fatal = [problem for problem in problems if problem.is_fatal]
        if not self._rows:
            self.status.SetLabel(LEXAdaptiveNoRows)
        elif fatal:
            first = fatal[0]
            text = (LEXAdaptiveProblemRow % (first.row_index + 1, first.text)
                    if first.row_index is not None else first.text)
            self.status.SetLabel("%s  %s" % (text, LEXAdaptiveRejectWarning))
        else:
            notice = self._notice_for_mapping(self._rows)
            self.status.SetLabel(notice or LEXAdaptiveOk)
        self.okButton.Enable(bool(self._rows) and not fatal)
        self._on_selection(None)

    def _can_move(self, index, delta):
        """A row can only move inside its own ring; sort_rows fixes the rest."""
        target = index + delta if index is not None else -1
        if not 0 <= target < len(self._rows):
            return False
        return self._rows[index].ring == self._rows[target].ring

    def _on_selection(self, event):
        index = self._selected_index()
        for button in (self.changeButton, self.removeButton):
            button.Enable(index is not None)
        self.upButton.Enable(self._can_move(index, -1))
        self.downButton.Enable(self._can_move(index, 1))
        if event is not None:
            event.Skip()

    def _on_add(self, event):
        result = open_adaptive_row_dialog(self, self.virtual_dat)
        if result is not None:
            row, title, description = result
            self._rows.append(row)
            self._tooltip_edits[row.lot_config_id] = (title, description)
            self._refresh()  # sorts, so the row's index is only known after
            self._select(self._rows.index(row))
        if event is not None:
            event.Skip()

    def _on_change(self, event):
        index = self._selected_index()
        if index is not None:
            old_row = self._rows[index]
            result = open_adaptive_row_dialog(self, self.virtual_dat, row=old_row)
            if result is not None:
                row, title, description = result
                if old_row.lot_config_id != row.lot_config_id:
                    self._tooltip_edits.pop(old_row.lot_config_id, None)
                self._rows[index] = row
                self._tooltip_edits[row.lot_config_id] = (title, description)
                self._refresh()
                self._select(self._rows.index(row))
        if event is not None:
            event.Skip()

    def _on_remove(self, event):
        index = self._selected_index()
        if index is not None:
            self._tooltip_edits.pop(self._rows[index].lot_config_id, None)
            del self._rows[index]
            self._refresh()
            self._select(min(index, len(self._rows) - 1))
        if event is not None:
            event.Skip()

    def _move(self, delta):
        """Move a row inside its ring. That order is the variant order."""
        index = self._selected_index()
        if not self._can_move(index, delta):
            return
        target = index + delta
        self._rows[index], self._rows[target] = self._rows[target], self._rows[index]
        self._refresh()
        self._select(target)

    # -- commit -------------------------------------------------------------

    def _on_ok(self, event):
        if any(problem.is_fatal for problem in check_rows(self.building_id, self._rows)):
            return
        self._result = (tuple(sort_rows(self._rows)), dict(self._tooltip_edits))
        self.EndModal(wx.ID_OK)

    def GetResult(self):
        return getattr(self, "_result", None)


def open_adaptive_mapping_dialog(parent, virtual_dat, building_id, rows=(),
                                 status_for_row=None, notice_for_mapping=None):
    dlg = AdaptiveMappingDialog(parent, virtual_dat, building_id, rows=rows,
                                status_for_row=status_for_row,
                                notice_for_mapping=notice_for_mapping)
    try:
        _centre_on_top_level(dlg, parent)
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.GetResult()
        return None
    finally:
        dlg.Destroy()


class AdaptiveLotTreeActions:
    """What the host frame lets the tree do, beyond looking at things."""

    def __init__(self, edit_mapping=None, delete_mapping=None, open_lot=None):
        self.edit_mapping = edit_mapping
        self.delete_mapping = delete_mapping
        self.open_lot = open_lot


class AdaptiveLotTreeDialog(wx.Dialog):
    """Every mapping in the plugins: building, then ring, then variant."""

    def __init__(self, parent, virtual_dat, actions=None, status_for_row=None,
                 notice_for_mapping=None, title=None):
        wx.Dialog.__init__(
            self, parent, -1, title or LEXAdaptiveTreeTitle,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.virtual_dat = virtual_dat
        self.actions = actions or AdaptiveLotTreeActions()
        self._status_for_row = status_for_row or (lambda _row: "")
        self._notice_for_mapping = notice_for_mapping or (lambda _rows: "")
        self._mappings = {}
        # Tearing the tree down deletes its items one by one, and each deletion
        # fires EVT_TREE_SEL_CHANGED at a control whose C++ side is already
        # gone. Nothing selection-related may run once this is set.
        self._closing = False
        self._rebuilding = False

        top = wx.BoxSizer(wx.HORIZONTAL)
        self.search = wx.SearchCtrl(self, -1, style=wx.TE_PROCESS_ENTER)
        self.search.SetDescriptiveText(LEXAdaptiveTreeSearchHint)
        self.search.ShowCancelButton(True)
        top.Add(self.search, 1, wx.EXPAND | wx.RIGHT, 6)
        self.bExpand = icon_button(self, "fold-down", LEXAdaptiveTreeExpandAll)
        top.Add(self.bExpand, 0, wx.RIGHT, 2)
        self.bCollapse = icon_button(self, "fold-up", LEXAdaptiveTreeCollapseAll)
        top.Add(self.bCollapse, 0, wx.RIGHT, 6)
        self.refreshButton = wx.Button(self, -1, LEXAdaptiveTreeRefresh)
        set_button_icon(self.refreshButton, "rotate-clockwise-2")
        top.Add(self.refreshButton, 0)

        self.tree = wx.TreeCtrl(
            self, -1,
            style=wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT | wx.TR_LINES_AT_ROOT | wx.TR_ROW_LINES,
        )
        self.tree.SetMinSize((560, 380))

        self.countText = wx.StaticText(self, -1, "")
        self.details = wx.StaticText(self, -1, LEXAdaptiveTreeDetailNone, style=wx.ST_ELLIPSIZE_END)
        self.details.SetFont(_monospace_font(self.details.GetFont()))

        actionsRow = wx.BoxSizer(wx.HORIZONTAL)
        self.editButton = wx.Button(self, -1, LEXAdaptiveTreeEdit)
        set_button_icon(self.editButton, "pencil")
        self.deleteButton = wx.Button(self, -1, LEXAdaptiveTreeDelete)
        set_button_icon(self.deleteButton, "trash")
        self.openButton = wx.Button(self, -1, LEXAdaptiveTreeOpenLot)
        set_button_icon(self.openButton, "folder-open")
        self.copyButton = wx.Button(self, -1, LEXAdaptiveTreeCopyId)
        set_button_icon(self.copyButton, "copy")
        for button in (self.editButton, self.deleteButton, self.openButton, self.copyButton):
            actionsRow.Add(button, 0, wx.RIGHT, 6)
        actionsRow.AddStretchSpacer(1)
        closeButton = wx.Button(self, wx.ID_CLOSE, LEXAdaptiveTreeClose)
        actionsRow.Add(closeButton, 0)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(top, 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(self.tree, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        sizer.Add(self.countText, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)
        sizer.Add(self.details, 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(actionsRow, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.SetSizerAndFit(sizer)
        self.SetMinSize((720, 560))

        self.search.Bind(wx.EVT_TEXT, self._on_filter)
        self.search.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self._on_search_cancel)
        self.bExpand.Bind(wx.EVT_BUTTON, lambda _evt: self.tree.ExpandAll())
        self.bCollapse.Bind(wx.EVT_BUTTON, self._on_collapse_all)
        self.refreshButton.Bind(wx.EVT_BUTTON, self._on_refresh)
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self._on_selection)
        self.tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._on_activated)
        self.tree.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self._on_right_click)
        self.editButton.Bind(wx.EVT_BUTTON, self._on_edit)
        self.deleteButton.Bind(wx.EVT_BUTTON, self._on_delete)
        self.openButton.Bind(wx.EVT_BUTTON, self._on_open_lot)
        self.copyButton.Bind(wx.EVT_BUTTON, self._on_copy_id)
        closeButton.Bind(wx.EVT_BUTTON, lambda _evt: self.Close())
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)

        self.Reload()

    # -- lifetime -----------------------------------------------------------

    def _on_close(self, event):
        self._deactivate_tree_events()
        event.Skip()

    def _on_destroy(self, event):
        if event.GetEventObject() is self:
            self._deactivate_tree_events()
        event.Skip()

    def _deactivate_tree_events(self):
        """Stop native tree callbacks before wx starts deleting its children."""
        if self._closing:
            return
        self._closing = True
        tree = getattr(self, "tree", None)
        if tree is None:
            return
        for event_type in (
            wx.EVT_TREE_SEL_CHANGED,
            wx.EVT_TREE_ITEM_ACTIVATED,
            wx.EVT_TREE_ITEM_RIGHT_CLICK,
        ):
            try:
                tree.Unbind(event_type)
            except RuntimeError:
                break

    # -- data ---------------------------------------------------------------

    def Reload(self, force: bool = False) -> None:
        busy = wx.BusyCursor()
        try:
            self._mappings = scan_adaptive_mappings(self.virtual_dat, force=force)
            self._load_icons()
        finally:
            del busy
        self._rebuild()

    def _load_icons(self):
        images = wx.ImageList(_TREE_ICON_SIZE, _TREE_ICON_SIZE)
        self._icon_building = images.Add(icon_bitmap("building-community", _TREE_ICON_SIZE))
        self._icon_ring = images.Add(icon_bitmap("list", _TREE_ICON_SIZE))
        self._icon_lot = images.Add(icon_bitmap("folder-open", _TREE_ICON_SIZE))
        self.tree.AssignImageList(images)

    def _matches(self, text: str) -> bool:
        needle = self.search.GetValue().strip().lower()
        if not needle:
            return True
        return needle.replace("0x", "") in text.lower().replace("0x", "")

    def _mapping_label(self, mapping):
        # The building ID alone says nothing. The menu name is what the user
        # clicked in the game, so it belongs next to the ID.
        name = building_game_name(self.virtual_dat, mapping.building_id)
        label = "%s  %s  (%d)" % (mapping.hex, name, len(mapping.rows)) if name \
            else "%s  (%d)" % (mapping.hex, len(mapping.rows))
        if mapping.is_rejected:
            label += "  " + LEXAdaptiveTreeRejected
        return label

    def _ring_label(self, ring):
        network_type, piece_id = ring
        if network_type == WILDCARD_NETWORK:
            return LEXAdaptiveTreeWildcardRing
        return LEXAdaptiveTreeRingLabel % (network_label(network_type), "0x%08X" % piece_id)

    def _row_label(self, variant, row):
        label = "%d   %s" % (variant, lot_label(self.virtual_dat, row.lot_config_id))
        tooltip = lot_tooltip_name(self.virtual_dat, row.lot_config_id)
        if tooltip:
            label += '   ·  "%s"' % tooltip
        status = self._status_for_row(row)
        return "%s  [%s]" % (label, status) if status else label

    def _rebuild(self) -> None:
        self._rebuilding = True
        self.tree.Freeze()
        try:
            self.tree.DeleteAllItems()
            root_id = self.tree.AddRoot("")
            self._mapping_count = 0
            self._row_count = 0
            for building_id in sorted(self._mappings):
                self._add_mapping(root_id, self._mappings[building_id])
            if not self.tree.GetChildrenCount(root_id, False):
                self.tree.AppendItem(root_id, LEXAdaptiveTreeEmpty)
            elif self.search.GetValue().strip():
                self.tree.ExpandAll()
            else:
                child, cookie = self.tree.GetFirstChild(root_id)
                while child.IsOk():
                    self.tree.Expand(child)
                    child, cookie = self.tree.GetNextChild(root_id, cookie)
        finally:
            try:
                self.tree.Thaw()
            finally:
                self._rebuilding = False
        if self._closing:
            return
        self.countText.SetLabel(LEXAdaptiveTreeCount % (self._mapping_count, self._row_count))
        self._update_details(None)

    def _add_mapping(self, parent_id, mapping):
        rings = mapping.rings()
        self_match = self._matches(mapping.hex)
        item_id = self.tree.AppendItem(parent_id, self._mapping_label(mapping), self._icon_building)
        self.tree.SetItemData(item_id, ("mapping", mapping))
        self.tree.SetItemBold(item_id, True)
        self._mapping_count += 1

        kept = 0
        for ring, rows in rings.items():
            ring_label = self._ring_label(ring)
            visible = [(index, row) for index, row in enumerate(rows)
                       if self_match or self._matches(ring_label)
                       or self._matches(self._row_label(index, row))]
            if not visible:
                continue
            ring_id = self.tree.AppendItem(item_id, ring_label, self._icon_ring)
            self.tree.SetItemData(ring_id, ("ring", (mapping, ring, rows)))
            for variant, row in visible:
                row_id = self.tree.AppendItem(ring_id, self._row_label(variant, row), self._icon_lot)
                self.tree.SetItemData(row_id, ("row", (mapping, variant, row)))
                self._row_count += 1
            kept += 1

        if kept or self_match:
            return True
        self.tree.Delete(item_id)
        self._mapping_count -= 1
        return False

    # -- selection ----------------------------------------------------------

    def _selected_data(self):
        if self._closing or self._rebuilding:
            return None, None
        # _closing only catches this dialog's own Close()/Destroy() path. On
        # Windows the native tree control can still fire a selection event off
        # a TreeCtrl whose C++ side is already gone (e.g. the owning frame is
        # torn down while this modeless dialog is still open), so the call
        # itself must be guarded too.
        try:
            item = self.tree.GetSelection()
            if not item.IsOk():
                return None, None
            data = self.tree.GetItemData(item)
        except RuntimeError:
            return None, None
        if not data:
            return None, None
        return data

    def _selected_mapping(self):
        """The mapping to act on: the selected one, or a selected row's."""
        kind, payload = self._selected_data()
        if kind == "mapping":
            return payload
        if kind == "ring":
            return payload[0]
        if kind == "row":
            return payload[0]
        return None

    def _selected_row(self):
        kind, payload = self._selected_data()
        return payload[2] if kind == "row" else None

    def _on_selection(self, event):
        if self._closing or self._rebuilding:
            event.Skip()
            return
        kind, payload = self._selected_data()
        self._update_details((kind, payload) if kind else None)
        event.Skip()

    def _detail_text(self, selection) -> str:
        if selection is None:
            return LEXAdaptiveTreeDetailNone
        kind, payload = selection
        if kind == "mapping":
            source = payload.file_name or LEXAdaptiveTreeSourceUnknown
            detail = LEXAdaptiveTreeDetailMapping % (
                payload.hex, len(payload.rings()), len(payload.rows),
                LEXAdaptiveTreeRejected if payload.is_rejected else source,
            )
            notice = self._notice_for_mapping(payload.rows)
            return "%s   ·   %s" % (detail, notice) if notice else detail
        if kind == "ring":
            _mapping, ring, rows = payload
            piece = "-" if ring[0] == WILDCARD_NETWORK else "0x%08X" % ring[1]
            return LEXAdaptiveTreeDetailRing % (network_label(ring[0]), piece, len(rows))
        if kind == "row":
            _mapping, variant, row = payload
            detail = LEXAdaptiveTreeDetailRow % (
                variant, "0x%08X" % row.lot_config_id,
                self._status_for_row(row) or network_label(row.network_type))
            tooltip = lot_tooltip_name(self.virtual_dat, row.lot_config_id)
            if tooltip:
                detail = "%s   ·   tooltip \"%s\"" % (detail, tooltip)
            return detail
        return LEXAdaptiveTreeDetailNone

    def _update_buttons(self) -> None:
        mapping = self._selected_mapping()
        self.editButton.Enable(self.actions.edit_mapping is not None and mapping is not None)
        self.deleteButton.Enable(self.actions.delete_mapping is not None and mapping is not None)
        self.openButton.Enable(self.actions.open_lot is not None and self._selected_row() is not None)
        self.copyButton.Enable(mapping is not None)

    def _update_details(self, selection) -> None:
        self.details.SetLabel(self._detail_text(selection))
        self._update_buttons()

    # -- events -------------------------------------------------------------

    def _on_filter(self, event):
        self._rebuild()
        event.Skip()

    def _on_search_cancel(self, event):
        self.search.SetValue("")
        self._rebuild()
        event.Skip()

    def _on_collapse_all(self, event):
        root_id = self.tree.GetRootItem()
        if root_id.IsOk():
            child, cookie = self.tree.GetFirstChild(root_id)
            while child.IsOk():
                self.tree.CollapseAllChildren(child)
                child, cookie = self.tree.GetNextChild(root_id, cookie)
        event.Skip()

    def _on_refresh(self, event):
        self.Reload(force=True)
        event.Skip()

    def _on_activated(self, event):
        if self._selected_row() is not None:
            self._on_open_lot(event)
        else:
            item = event.GetItem()
            if item.IsOk():
                self.tree.Toggle(item)
        event.Skip()

    def _on_right_click(self, event):
        self.tree.SelectItem(event.GetItem())
        menu = wx.Menu()
        for label, handler, button in (
            (LEXAdaptiveTreeEdit, self._on_edit, self.editButton),
            (LEXAdaptiveTreeDelete, self._on_delete, self.deleteButton),
            (LEXAdaptiveTreeOpenLot, self._on_open_lot, self.openButton),
            (LEXAdaptiveTreeCopyId, self._on_copy_id, self.copyButton),
        ):
            item_id = wx.NewIdRef()
            menu.Append(item_id, label).Enable(button.IsEnabled())
            self.Bind(wx.EVT_MENU, handler, id=item_id)
        self.PopupMenu(menu)
        menu.Destroy()

    def _on_edit(self, event):
        mapping = self._selected_mapping()
        if self.actions.edit_mapping is not None and mapping is not None:
            self.actions.edit_mapping(mapping.building_id)
            self.Reload(force=True)
        if hasattr(event, "Skip"):
            event.Skip()

    def _on_delete(self, event):
        mapping = self._selected_mapping()
        if self.actions.delete_mapping is not None and mapping is not None:
            self.actions.delete_mapping(mapping.building_id)
            self.Reload(force=True)
        if hasattr(event, "Skip"):
            event.Skip()

    def _on_open_lot(self, event):
        row = self._selected_row()
        if self.actions.open_lot is not None and row is not None:
            self.actions.open_lot(row.lot_config_id)
        if hasattr(event, "Skip"):
            event.Skip()

    def _on_copy_id(self, event):
        mapping = self._selected_mapping()
        if mapping is not None and wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(mapping.hex))
            finally:
                wx.TheClipboard.Close()
        if hasattr(event, "Skip"):
            event.Skip()


def open_adaptive_lot_tree(parent, virtual_dat, actions=None, status_for_row=None,
                           notice_for_mapping=None):
    """Show the tree, reusing the window if it is already open on ``parent``."""
    existing = getattr(parent, "_adaptive_tree_dialog", None)
    if existing:
        try:
            existing.Reload(force=True)
            existing.Raise()
            return existing
        except RuntimeError:  # the C++ side is gone
            pass
    dlg = AdaptiveLotTreeDialog(parent, virtual_dat, actions=actions,
                                status_for_row=status_for_row,
                                notice_for_mapping=notice_for_mapping)
    try:
        parent._adaptive_tree_dialog = dlg
    except AttributeError:
        pass

    def _forget(event):
        # Bound after the dialog's own EVT_CLOSE handler, so this one runs
        # first: set the flag here too or the selection events the imminent
        # Destroy() fires would still reach a half-dead tree.
        dlg._deactivate_tree_events()
        try:
            if getattr(parent, "_adaptive_tree_dialog", None) is dlg:
                parent._adaptive_tree_dialog = None
        except AttributeError:
            pass
        event.Skip()
        dlg.Destroy()

    dlg.Bind(wx.EVT_CLOSE, _forget)
    _centre_on_top_level(dlg, parent)
    dlg.Show()
    return dlg
