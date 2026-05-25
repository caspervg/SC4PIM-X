"""Small structured editors for common building/lot property shapes."""

import wx

from .SC4DatTools import format_float_value, hex2str


POLLUTION_VECTOR_IDS = {0x27812851, 0xAA5832F3, 0x68EE9764}
EFFECT_PAIR_IDS = {0x2781284F, 0x27812850, 0xCA5B9305}
DEMAND_PAIR_IDS = {0x27812834, 0x27812840, 0x27812841}


def editor_kind(prop, prop_def):
    prop_id = int(getattr(prop, "id", 0))
    values = list(getattr(prop, "values", ()))
    prop_type = getattr(prop_def, "Type", "")
    if prop_id in POLLUTION_VECTOR_IDS and len(values) == 4 and prop_type in ("Sint32", "Float32"):
        return "vector"
    if prop_id in EFFECT_PAIR_IDS and len(values) == 2 and prop_type in ("Sint32", "Float32"):
        return "vector"
    if prop_id in DEMAND_PAIR_IDS and len(values) >= 2 and len(values) % 2 == 0 and prop_type == "Uint32":
        return "pairs"
    return None


def edit_structured_property(parent, title, prop, prop_def):
    kind = editor_kind(prop, prop_def)
    if kind == "vector":
        return _edit_vector(parent, title, prop, prop_def)
    if kind == "pairs":
        return _edit_pairs(parent, title, prop, prop_def)
    return None


def _column_labels(prop_def, count):
    labels = []
    options = getattr(prop_def, "Options", {}) or {}
    for idx in range(count):
        labels.append(options.get("COL:%d" % idx, "Value %d" % (idx + 1)))
    return labels


def _centre_on_top_level(dialog, parent):
    top = wx.GetTopLevelParent(parent)
    if top is None:
        dialog.CentreOnParent()
        return
    top_pos = top.GetScreenPosition()
    top_size = top.GetSize()
    dlg_size = dialog.GetSize()
    x = top_pos.x + max(0, (top_size.width - dlg_size.width) // 2)
    y = top_pos.y + max(0, (top_size.height - dlg_size.height) // 2)
    dialog.SetPosition((x, y))


def _format_value(prop_type, value):
    if prop_type == "Float32":
        return format_float_value(float(value))
    return str(int(value))


def _parse_value(prop_type, text):
    if prop_type == "Float32":
        return float(text)
    return int(text, 0)


def _values_to_text(prop_type, values):
    return ",".join(_format_value(prop_type, value) for value in values)


def demand_pairs(values):
    return [(int(values[i]), int(values[i + 1])) for i in range(0, len(values), 2)]


def demand_pairs_to_text(pairs):
    values = []
    for demand_id, amount in pairs:
        values.append(hex2str(demand_id))
        values.append(str(int(amount)))
    return ",".join(values)


def option_label(prop_def, value):
    options = getattr(prop_def, "Options", {}) or {}
    name = options.get(int(value))
    if name:
        return name
    return hex2str(int(value))


def _option_items(prop_def):
    options = getattr(prop_def, "Options", {}) or {}
    items = [(value, name) for value, name in options.items() if isinstance(value, int)]
    items.sort(key=lambda item: item[1].lower())
    return items


def _edit_vector(parent, title, prop, prop_def):
    dlg = VectorEditorDialog(parent, title, getattr(prop_def, "Name", title), prop.values, prop_def)
    try:
        _centre_on_top_level(dlg, parent)
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.GetValueText()
    finally:
        dlg.Destroy()
    return None


def _edit_pairs(parent, title, prop, prop_def):
    dlg = DemandPairEditorDialog(parent, title, getattr(prop_def, "Name", title), prop.values, prop_def)
    try:
        _centre_on_top_level(dlg, parent)
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.GetValueText()
    finally:
        dlg.Destroy()
    return None


class VectorEditorDialog(wx.Dialog):

    def __init__(self, parent, title, prop_name, values, prop_def):
        wx.Dialog.__init__(self, parent, -1, title)
        self._value_text = None
        self._prop_type = getattr(prop_def, "Type", "")
        labels = _column_labels(prop_def, len(values))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, -1, prop_name), 0, wx.EXPAND | wx.ALL, 8)
        form = wx.FlexGridSizer(len(values), 2, 6, 8)
        form.AddGrowableCol(1)
        self.controls = []
        for label, value in zip(labels, values):
            form.Add(wx.StaticText(self, -1, label), 0, wx.ALIGN_CENTER_VERTICAL)
            ctrl = wx.TextCtrl(self, -1, _format_value(self._prop_type, value))
            form.Add(ctrl, 1, wx.EXPAND)
            self.controls.append(ctrl)
        sizer.Add(form, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        buttons = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(self, wx.ID_OK)
        cancel_btn = wx.Button(self, wx.ID_CANCEL)
        ok_btn.SetDefault()
        ok_btn.Bind(wx.EVT_BUTTON, self._on_ok)
        buttons.AddButton(ok_btn)
        buttons.AddButton(cancel_btn)
        buttons.Realize()
        sizer.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.SetSizerAndFit(sizer)

    def GetValueText(self):
        return self._value_text

    def _on_ok(self, _event):
        values = []
        try:
            for ctrl in self.controls:
                values.append(_parse_value(self._prop_type, ctrl.GetValue().strip()))
        except ValueError:
            wx.MessageBox("Enter valid numeric values.", "Invalid values", wx.OK | wx.ICON_ERROR, self)
            return
        self._value_text = _values_to_text(self._prop_type, values)
        self.EndModal(wx.ID_OK)


class DemandPairEditorDialog(wx.Dialog):

    def __init__(self, parent, title, prop_name, values, prop_def):
        wx.Dialog.__init__(self, parent, -1, title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._prop_def = prop_def
        self._value_text = None
        self._pairs = demand_pairs(values)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, -1, prop_name), 0, wx.EXPAND | wx.ALL, 8)
        self.list = wx.ListCtrl(self, -1, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.list.InsertColumn(0, "Type", width=150)
        self.list.InsertColumn(1, "ID", width=95)
        self.list.InsertColumn(2, "Amount", width=85)
        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_edit)
        sizer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        row_buttons = wx.BoxSizer(wx.HORIZONTAL)
        add_btn = wx.Button(self, -1, "Add")
        edit_btn = wx.Button(self, -1, "Edit")
        del_btn = wx.Button(self, -1, "Delete")
        up_btn = wx.Button(self, -1, "Up")
        down_btn = wx.Button(self, -1, "Down")
        add_btn.Bind(wx.EVT_BUTTON, self._on_add)
        edit_btn.Bind(wx.EVT_BUTTON, self._on_edit)
        del_btn.Bind(wx.EVT_BUTTON, self._on_delete)
        up_btn.Bind(wx.EVT_BUTTON, self._on_up)
        down_btn.Bind(wx.EVT_BUTTON, self._on_down)
        for btn in (add_btn, edit_btn, del_btn, up_btn, down_btn):
            row_buttons.Add(btn, 0, wx.RIGHT, 4)
        sizer.Add(row_buttons, 0, wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        buttons = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(self, wx.ID_OK)
        cancel_btn = wx.Button(self, wx.ID_CANCEL)
        ok_btn.SetDefault()
        ok_btn.Bind(wx.EVT_BUTTON, self._on_ok)
        buttons.AddButton(ok_btn)
        buttons.AddButton(cancel_btn)
        buttons.Realize()
        sizer.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.SetMinSize((420, 320))
        self.SetSizer(sizer)
        self._refresh()
        self.Fit()

    def GetValueText(self):
        return self._value_text

    def _refresh(self, selected=None):
        self.list.DeleteAllItems()
        for row, (demand_id, amount) in enumerate(self._pairs):
            self.list.InsertItem(row, option_label(self._prop_def, demand_id))
            self.list.SetItem(row, 1, hex2str(demand_id))
            self.list.SetItem(row, 2, str(amount))
        if selected is not None and 0 <= selected < self.list.GetItemCount():
            self.list.Select(selected)
            self.list.Focus(selected)

    def _selected_row(self):
        return self.list.GetNextItem(-1, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)

    def _on_add(self, _event):
        default_id = _option_items(self._prop_def)[0][0] if _option_items(self._prop_def) else 0
        dlg = DemandPairDialog(self, self._prop_def, default_id, 0)
        try:
            dlg.CentreOnParent()
            if dlg.ShowModal() == wx.ID_OK:
                self._pairs.append(dlg.GetPair())
                self._refresh(len(self._pairs) - 1)
        finally:
            dlg.Destroy()

    def _on_edit(self, _event):
        row = self._selected_row()
        if row < 0:
            return
        demand_id, amount = self._pairs[row]
        dlg = DemandPairDialog(self, self._prop_def, demand_id, amount)
        try:
            dlg.CentreOnParent()
            if dlg.ShowModal() == wx.ID_OK:
                self._pairs[row] = dlg.GetPair()
                self._refresh(row)
        finally:
            dlg.Destroy()

    def _on_delete(self, _event):
        row = self._selected_row()
        if row >= 0:
            del self._pairs[row]
            self._refresh(min(row, len(self._pairs) - 1))

    def _on_up(self, _event):
        row = self._selected_row()
        if row > 0:
            self._pairs[row - 1], self._pairs[row] = self._pairs[row], self._pairs[row - 1]
            self._refresh(row - 1)

    def _on_down(self, _event):
        row = self._selected_row()
        if 0 <= row < len(self._pairs) - 1:
            self._pairs[row + 1], self._pairs[row] = self._pairs[row], self._pairs[row + 1]
            self._refresh(row + 1)

    def _on_ok(self, _event):
        if not self._pairs:
            wx.MessageBox("Add at least one pair.", "Invalid values", wx.OK | wx.ICON_ERROR, self)
            return
        self._value_text = demand_pairs_to_text(self._pairs)
        self.EndModal(wx.ID_OK)


class DemandPairDialog(wx.Dialog):

    def __init__(self, parent, prop_def, demand_id, amount):
        wx.Dialog.__init__(self, parent, -1, "Edit pair")
        self._prop_def = prop_def
        self._pair = None
        self._items = _option_items(prop_def)

        sizer = wx.BoxSizer(wx.VERTICAL)
        form = wx.FlexGridSizer(3, 2, 6, 8)
        form.AddGrowableCol(1)

        form.Add(wx.StaticText(self, -1, "Known type"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.choice = wx.Choice(self, -1, choices=[name for _, name in self._items])
        form.Add(self.choice, 1, wx.EXPAND)

        form.Add(wx.StaticText(self, -1, "ID"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.id_text = wx.TextCtrl(self, -1, hex2str(demand_id))
        form.Add(self.id_text, 1, wx.EXPAND)

        form.Add(wx.StaticText(self, -1, "Amount"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.amount_text = wx.TextCtrl(self, -1, str(int(amount)))
        form.Add(self.amount_text, 1, wx.EXPAND)
        sizer.Add(form, 1, wx.EXPAND | wx.ALL, 10)

        for idx, (value, _) in enumerate(self._items):
            if value == int(demand_id):
                self.choice.SetSelection(idx)
                break
        self.choice.Bind(wx.EVT_CHOICE, self._on_choice)

        buttons = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(self, wx.ID_OK)
        cancel_btn = wx.Button(self, wx.ID_CANCEL)
        ok_btn.SetDefault()
        ok_btn.Bind(wx.EVT_BUTTON, self._on_ok)
        buttons.AddButton(ok_btn)
        buttons.AddButton(cancel_btn)
        buttons.Realize()
        sizer.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.SetSizerAndFit(sizer)

    def GetPair(self):
        return self._pair

    def _on_choice(self, _event):
        selection = self.choice.GetSelection()
        if selection >= 0:
            self.id_text.SetValue(hex2str(self._items[selection][0]))

    def _on_ok(self, _event):
        try:
            demand_id = int(self.id_text.GetValue().strip(), 0)
            amount = int(self.amount_text.GetValue().strip(), 0)
        except ValueError:
            wx.MessageBox("Enter valid integer values.", "Invalid pair", wx.OK | wx.ICON_ERROR, self)
            return
        if demand_id < 0 or demand_id > 0xFFFFFFFF:
            wx.MessageBox("ID must be a 32-bit unsigned value.", "Invalid pair", wx.OK | wx.ICON_ERROR, self)
            return
        if amount < 0 or amount > 0xFFFFFFFF:
            wx.MessageBox("Amount must be a 32-bit unsigned value.", "Invalid pair", wx.OK | wx.ICON_ERROR, self)
            return
        self._pair = (demand_id, amount)
        self.EndModal(wx.ID_OK)
