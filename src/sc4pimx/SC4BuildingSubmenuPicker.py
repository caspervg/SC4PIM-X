"""Reusable Building Submenus picker/editor.

Building Submenus are stored as property 0xAA1DD399, a variable-length list of
Uint32 submenu button IDs used by the Submenus DLL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import wx
import wx.lib.agw.ultimatelistctrl as ULC

from .SC4OccupantGroupPicker import _centre_on_top_level, _monospace_font
from .translation import *  # noqa: F401,F403

PROP_BUILDING_SUBMENUS = 0xAA1DD399


_ROOT_LABELS = {
    "SubMenuROOTRCI": "RCI",
    "SubMenuROOTHighway": "Highway",
    "SubMenuROOTRail": "Rail",
    "SubMenuROOTMiscTransit": "Misc Transit",
    "SubMenuROOTWaterTransit": "Water Transit",
    "SubMenuROOTPowerUtility": "Power Utility",
    "SubMenuROOTCivicPolice": "Civic Police",
    "SubMenuROOTCivicEducation": "Civic Education",
    "SubMenuROOTCivicHealth": "Civic Health",
    "SubMenuROOTLandmarks": "Landmarks",
    "SubMenuROOTPark": "Parks",
}


@dataclass(frozen=True)
class BuildingSubmenuItem:
    value: int
    label: str
    root: str
    selected: bool
    unknown: bool

    @property
    def hex(self) -> str:
        return "0x%08X" % self.value

    @property
    def text(self) -> str:
        return ("%s %s %s" % (self.hex, self.root, self.label)).lower()


class BuildingSubmenuListCtrl(ULC.UltimateListCtrl):
    def __init__(self, parent: wx.Window):
        ULC.UltimateListCtrl.__init__(
            self,
            parent,
            -1,
            agwStyle=ULC.ULC_REPORT | ULC.ULC_HRULES | ULC.ULC_SHOW_TOOLTIPS | ULC.ULC_SINGLE_SEL,
        )
        self._mono = _monospace_font(self.GetFont())
        self.Bind(wx.EVT_SIZE, self._on_size)

    def InsertItem(self, index: int, label: str) -> int:
        info = ULC.UltimateListItem()
        info._itemId = index
        info._mask = ULC.ULC_MASK_TEXT | ULC.ULC_MASK_KIND
        info._text = label
        info._kind = 1
        self._mainWin.InsertItem(info)
        return index

    def SetItem(self, index: int, col: int, label: str) -> bool:
        info = ULC.UltimateListItem()
        info._itemId = index
        info._col = col
        info._mask = ULC.ULC_MASK_TEXT
        info._text = label or ""
        if col == 1:
            info.SetFont(self._mono)
            info._mask |= ULC.ULC_MASK_FONT
        self._mainWin.SetItem(info)
        return True

    def CheckItem(self, index: int, checked: bool, send_event: bool = False) -> None:
        item = ULC.CreateListItem(index, 0)
        item = self._mainWin.GetItem(item, 0)
        self._mainWin.CheckItem(item, checked, send_event)

    def SetItemTextColour(self, index: int, colour: wx.Colour) -> None:
        for col in range(self.GetColumnCount()):
            info = ULC.UltimateListItem()
            info._itemId = index
            info._col = col
            info._mask = ULC.ULC_MASK_FONTCOLOUR
            info.SetTextColour(colour)
            self._mainWin.SetItem(info)

    def _on_size(self, event: wx.SizeEvent) -> None:
        event.Skip()
        wx.CallAfter(self.AutoFillLastColumn)

    def AutoFillLastColumn(self) -> None:
        count = self.GetColumnCount()
        if count < 2:
            return
        used = sum(self.GetColumnWidth(c) for c in range(count - 1))
        remaining = self.GetClientSize().width - used - 4
        if remaining > 80:
            self.SetColumnWidth(count - 1, remaining)


class BuildingSubmenuPickerDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        virtual_dat,
        current_submenus: Iterable[int],
        candidates: Optional[Iterable[int]] = None,
        title: Optional[str] = None,
        preserve_unlisted: bool = True,
        allow_manual: bool = True,
    ):
        wx.Dialog.__init__(
            self,
            parent,
            -1,
            title or LEXBuildingSubmenuPickerTitle,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.virtual_dat = virtual_dat
        prop_def = virtual_dat.properties[PROP_BUILDING_SUBMENUS]
        self.options = getattr(prop_def, "Options", {})
        self.option_groups = getattr(prop_def, "OptionGroups", {})
        self.current_submenus = set(int(v) for v in (current_submenus or ()))
        self.preserve_unlisted = preserve_unlisted
        self.allow_manual = allow_manual
        if candidates is None:
            values = set(int(v) for v in self.options.keys()) | self.current_submenus
            self._preserved = set()
        else:
            candidate_values = set(int(v) for v in candidates)
            values = candidate_values | (self.current_submenus & candidate_values)
            self._preserved = self.current_submenus - candidate_values if preserve_unlisted else set()
        self._all_values = sorted(values)
        self._selected = set(self.current_submenus & set(self._all_values))
        self._visible: list[BuildingSubmenuItem] = []
        self._refreshing = False
        self._sort_col = 1
        self._sort_ascending = True

        self.search = wx.SearchCtrl(self, -1, style=wx.TE_PROCESS_ENTER)
        self.filterChoice = wx.Choice(
            self,
            -1,
            choices=[
                LEXBuildingSubmenuFilterAll,
                LEXBuildingSubmenuFilterSelected,
                LEXBuildingSubmenuFilterUnknown,
                LEXBuildingSubmenuFilterRCI,
                LEXBuildingSubmenuFilterTransit,
                LEXBuildingSubmenuFilterRail,
                LEXBuildingSubmenuFilterUtilities,
                LEXBuildingSubmenuFilterCivic,
                LEXBuildingSubmenuFilterParks,
                LEXBuildingSubmenuFilterLandmarks,
            ],
        )
        self.filterChoice.SetSelection(0)
        self.list = BuildingSubmenuListCtrl(self)
        self.list.InsertColumn(0, LEXBuildingSubmenuColSelected, width=76)
        self.list.InsertColumn(1, LEXBuildingSubmenuColHex, width=120)
        self.list.InsertColumn(2, LEXBuildingSubmenuColRoot, width=150)
        self.list.InsertColumn(3, LEXBuildingSubmenuColLabel, width=360)
        self.list.SetMinSize((640, 320))
        self.countText = wx.StaticText(self, -1, "")

        self.okButton = wx.Button(self, wx.ID_OK)
        self.okButton.SetDefault()
        cancelButton = wx.Button(self, wx.ID_CANCEL)

        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(self.search, 1, wx.RIGHT | wx.EXPAND, 6)
        top.Add(self.filterChoice, 0, wx.EXPAND)

        if allow_manual:
            self.hexText = wx.TextCtrl(self, -1, "", style=wx.TE_PROCESS_ENTER)
            if hasattr(self.hexText, "SetHint"):
                self.hexText.SetHint(LEXBuildingSubmenuHexHint)
            self.addButton = wx.Button(self, -1, LEXBuildingSubmenuAddHex)
            add_row = wx.BoxSizer(wx.HORIZONTAL)
            add_row.Add(wx.StaticText(self, -1, LEXBuildingSubmenuManualHex), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
            add_row.Add(self.hexText, 1, wx.RIGHT | wx.EXPAND, 6)
            add_row.Add(self.addButton, 0)

        btns = wx.StdDialogButtonSizer()
        btns.AddButton(self.okButton)
        btns.AddButton(cancelButton)
        btns.Realize()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(top, 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        sizer.Add(self.countText, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        if allow_manual:
            sizer.Add(add_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        sizer.Add(btns, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizerAndFit(sizer)

        self.search.Bind(wx.EVT_TEXT, self._on_filter)
        self.filterChoice.Bind(wx.EVT_CHOICE, self._on_filter)
        self.list.Bind(ULC.EVT_LIST_COL_CLICK, self._on_column_click)
        self.list.Bind(ULC.EVT_LIST_ITEM_CHECKED, self._on_table_checked)
        if allow_manual:
            self.addButton.Bind(wx.EVT_BUTTON, self._on_add_hex)
            self.hexText.Bind(wx.EVT_TEXT_ENTER, self._on_add_hex)

        self._refresh()

    def _label_for(self, value: int) -> str:
        return self.options.get(value, LEXBuildingSubmenuUnknown % ("0x%08X" % value))

    def _root_for(self, value: int) -> str:
        root = self.option_groups.get(value, "")
        return _ROOT_LABELS.get(root, root.replace("SubMenuROOT", "") or LEXBuildingSubmenuNoRoot)

    def _item_for(self, value: int) -> BuildingSubmenuItem:
        return BuildingSubmenuItem(
            value=value,
            label=self._label_for(value),
            root=self._root_for(value),
            selected=value in self._selected,
            unknown=value not in self.options,
        )

    def _passes_quick_filter(self, item: BuildingSubmenuItem) -> bool:
        idx = self.filterChoice.GetSelection()
        root = item.root.lower()
        if idx == 1:
            return item.selected
        if idx == 2:
            return item.unknown
        if idx == 3:
            return root == "rci"
        if idx == 4:
            return "transit" in root or root == "rail"
        if idx == 5:
            return root == "rail"
        if idx == 6:
            return "utility" in root
        if idx == 7:
            return root.startswith("civic")
        if idx == 8:
            return root == "parks"
        if idx == 9:
            return root == "landmarks"
        return True

    def _passes_search(self, item: BuildingSubmenuItem) -> bool:
        raw = self.search.GetValue().strip().lower()
        if not raw:
            return True
        compact_hex = item.hex.lower().replace("0x", "")
        return raw in item.text or raw.replace("0x", "") in compact_hex

    def _sort_key(self, item: BuildingSubmenuItem):
        if self._sort_col == 0:
            return (item.value not in self._selected, item.value)
        if self._sort_col == 1:
            return item.value
        if self._sort_col == 2:
            return (item.root.lower(), item.value)
        return (item.label.lower(), item.value)

    def _refresh(self) -> None:
        self._visible = []
        for value in self._all_values:
            item = self._item_for(value)
            if self._passes_quick_filter(item) and self._passes_search(item):
                self._visible.append(item)
        self._visible.sort(key=self._sort_key, reverse=not self._sort_ascending)
        self._refreshing = True
        try:
            self.list.DeleteAllItems()
            for idx, item in enumerate(self._visible):
                self.list.InsertItem(idx, "")
                self.list.SetItem(idx, 1, item.hex)
                self.list.SetItem(idx, 2, item.root)
                self.list.SetItem(idx, 3, item.label)
                self.list.CheckItem(idx, item.value in self._selected)
                if item.unknown:
                    self.list.SetItemTextColour(idx, wx.Colour(140, 80, 0))
        finally:
            self._refreshing = False
        self._update_count()

    def _update_count(self) -> None:
        self.countText.SetLabel(
            LEXBuildingSubmenuCount
            % (len(self._selected | self._preserved), len(self._visible), len(self._all_values))
        )

    def _on_filter(self, event: wx.Event) -> None:
        self._refresh()
        event.Skip()

    def _on_column_click(self, event: wx.ListEvent) -> None:
        col = event.GetColumn()
        if col == self._sort_col:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_col = col
            self._sort_ascending = True
        self._refresh()
        event.Skip()

    def _on_table_checked(self, event: wx.ListEvent) -> None:
        if not self._refreshing:
            self._on_table_check(event.GetIndex(), self.list.IsItemChecked(event.GetIndex()))
        event.Skip()

    def _on_table_check(self, idx: int, checked: bool) -> None:
        if 0 <= idx < len(self._visible):
            value = self._visible[idx].value
            if checked:
                self._selected.add(value)
            else:
                self._selected.discard(value)
        if self._sort_col == 0 or self.filterChoice.GetSelection() == 1:
            self._refresh()
        else:
            self._update_count()

    def _on_add_hex(self, event: wx.Event) -> None:
        raw = self.hexText.GetValue().strip()
        if not raw:
            return
        try:
            if not raw.lower().startswith("0x") or len(raw) <= 2:
                raise ValueError
            value = int(raw[2:], 16)
            if value < 0 or value > 0xFFFFFFFF:
                raise ValueError
        except ValueError:
            wx.MessageBox(LEXBuildingSubmenuInvalidHex, LEXBuildingSubmenuPickerTitle, wx.OK | wx.ICON_ERROR, self)
            return
        if value not in self._all_values:
            self._all_values.append(value)
            self._all_values.sort()
        self._selected.add(value)
        self.hexText.SetValue("")
        self._refresh()
        event.Skip()

    def GetBuildingSubmenus(self) -> list[int]:
        values = sorted(self._preserved | self._selected)
        return values


def pick_building_submenus(
    parent: wx.Window,
    virtual_dat,
    current_submenus: Iterable[int],
    candidates: Optional[Iterable[int]] = None,
    title: Optional[str] = None,
    preserve_unlisted: bool = True,
    allow_manual: bool = True,
) -> Optional[list[int]]:
    dlg = BuildingSubmenuPickerDialog(
        parent,
        virtual_dat,
        current_submenus,
        candidates=candidates,
        title=title,
        preserve_unlisted=preserve_unlisted,
        allow_manual=allow_manual,
    )
    try:
        _centre_on_top_level(dlg, parent)
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.GetBuildingSubmenus()
        return None
    finally:
        dlg.Destroy()
