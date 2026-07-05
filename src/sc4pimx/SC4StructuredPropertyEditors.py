"""Small structured editors for common building/lot property shapes."""

import struct

import wx

from .SC4DatTools import format_float_value, hex2str
from .TablerIcons import icon_button
from .translation import *  # noqa: F401,F403

POLLUTION_VECTOR_IDS = {0x27812851, 0xAA5832F3, 0x68EE9764}
EFFECT_PAIR_IDS = {0x2781284F, 0x27812850, 0xCA5B9305}
DEMAND_PAIR_IDS = {0x27812834, 0x27812840, 0x27812841}

# new_properties.xml exposes a Type *name*; the parsed Prop carries the matching
# numeric typeValue. The single-value editors key off the name for dispatch and
# off the typeValue for round-trip formatting (mirroring Prop.ToStr exactly).
_INTEGER_TYPES = {"Uint32", "Sint32", "Uint8", "Sint64"}
_NUMERIC_TYPES = _INTEGER_TYPES | {"Float32"}

# typeValue -> (min, max) and hex width, matching the clamping in Prop's text
# parser (SC4DatTools.convH) so a chosen/typed value never overflows its type.
_TYPE_BOUNDS = {
    256: (0, 0xFF),  # Uint8
    768: (0, 0xFFFFFFFF),  # Uint32
    1792: (-2147483648, 2147483647),  # Sint32
    2048: (-(2**63), 2**63 - 1),  # Sint64
}
_TYPE_HEX_SIZE = {256: 8, 768: 32, 1792: 32, 2048: 64}


def _monospace_font(base_font):
    """A monospace wx.Font at the base font's size, so hex digits line up."""
    try:
        available = set(wx.FontEnumerator.GetFacenames())
    except Exception:
        available = set()
    size = base_font.GetPointSize()
    for name in ("Consolas", "Cascadia Mono", "Courier New"):
        if name in available:
            return wx.Font(size, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName=name)
    return wx.Font(size, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)


def _has_named_options(prop_def):
    return bool(_option_items(prop_def))


def _has_declared_range(prop_def):
    # readPropertyDef only attaches minVal/maxVal when the XML declares one.
    return getattr(prop_def, "minVal", None) is not None and getattr(prop_def, "maxVal", None) is not None


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
    # Generic editors driven by new_properties.xml metadata and the actual data.
    # A property is edited as a single value when it holds exactly one -- either
    # a fixed scalar (Count == 1) or a variable-length property (Count <= 0) that
    # currently has a lone entry, e.g. Catalog Monthly Cost (Count=-1). Fixed
    # arrays (Count >= 2) use the table; variable-length data with zero or many
    # entries uses the growable table.
    count = getattr(prop_def, "Count", 1)
    n = len(values)
    if n == 1 and count <= 1:
        if prop_type == "Bool":
            return "bool"
        if prop_type in _INTEGER_TYPES and _has_named_options(prop_def):
            return "enum"
        if prop_type in _NUMERIC_TYPES:
            return "scalar"
    if prop_type in _NUMERIC_TYPES:
        if count >= 2:
            return "grid"
        if count <= 0:
            return "list"
    return None


def edit_structured_property(parent, title, prop, prop_def):
    kind = editor_kind(prop, prop_def)
    if kind == "vector":
        return _edit_vector(parent, title, prop, prop_def)
    if kind == "pairs":
        return _edit_pairs(parent, title, prop, prop_def)
    if kind in ("bool", "enum", "scalar"):
        return _edit_single_value(parent, title, prop, prop_def, kind)
    if kind in ("grid", "list"):
        return _edit_table(parent, title, prop, prop_def, variable=(kind == "list"))
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


def _edit_single_value(parent, title, prop, prop_def, kind):
    dlg = SingleValuePropertyDialog(parent, title, prop, prop_def, kind)
    try:
        _centre_on_top_level(dlg, parent)
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.GetValueText()
    finally:
        dlg.Destroy()
    return None


def _edit_table(parent, title, prop, prop_def, variable):
    dlg = TablePropertyDialog(parent, title, prop, prop_def, variable)
    try:
        _centre_on_top_level(dlg, parent)
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.GetValueText()
    finally:
        dlg.Destroy()
    return None


def _grid_labels(prop_def, n):
    """Field labels for a fixed grid: COL options, else TGI for a triple, else Value N."""
    options = getattr(prop_def, "Options", {}) or {}
    cols = [options.get("COL:%d" % i) for i in range(n)]
    if n == 3 and all(c is None for c in cols):
        return [propEditTgiType, propEditTgiGroup, propEditTgiInstance]
    return [cols[i] if cols[i] else propEditValueN % (i + 1) for i in range(n)]


def _scalar_to_text(type_value, value, show_as_hex=True):
    """Format a single value for display/round-trip, honouring ShowAsHex.

    Integers render as 0x-hex or plain decimal per the property's ShowAsHex
    flag; both forms re-parse cleanly through Prop's text parser. Floats and
    bools have a single canonical form.
    """
    if type_value == 2816:  # Bool
        return "True" if value else "False"
    if type_value == 2304:  # Float32
        return "%.08f" % float(value)
    if show_as_hex:
        return hex2str(int(value), _TYPE_HEX_SIZE.get(type_value, 32), upper=True)
    return str(int(value))


def _parse_scalar(type_value, text):
    """Parse user text into a number; raises ValueError on bad input."""
    text = text.strip()
    if type_value == 2304:  # Float32
        return float(text)
    return int(text, 0)  # accepts decimal and 0x-prefixed hex


def _scalar_bounds(type_value, prop_def):
    """Effective (min, max) for a numeric value: the XML range narrows the type range."""
    low, high = _TYPE_BOUNDS.get(type_value, (None, None))
    if _has_declared_range(prop_def):
        decl_low, decl_high = prop_def.minVal, prop_def.maxVal
        low = decl_low if low is None else max(low, decl_low)
        high = decl_high if high is None else min(high, decl_high)
    return low, high


def _conversion_text(type_value, value):
    """A live readout pairing a number with its alternate form.

    Integers show the hex form alongside the signed decimal; floats show their
    raw IEEE-754 32-bit pattern, which is how some SC4 tools display them.
    """
    if type_value == 2304:  # Float32
        bits = struct.unpack("<I", struct.pack("<f", float(value)))[0]
        return propEditFloatRaw % (format_float_value(float(value)), bits)
    return propEditIntConv % (hex2str(int(value), _TYPE_HEX_SIZE.get(type_value, 32), upper=True), int(value))


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
        add_btn = icon_button(self, "plus", "Add")
        edit_btn = icon_button(self, "pencil", "Edit")
        del_btn = icon_button(self, "trash", "Delete")
        up_btn = icon_button(self, "arrow-up", "Up")
        down_btn = icon_button(self, "arrow-down", "Down")
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


class SingleValuePropertyDialog(wx.Dialog):
    """Metadata-driven editor for a single-value property.

    Picks its control from new_properties.xml: a checkbox for Bool, an editable
    combo of named OPTIONs for enumerated integers (raw values stay typeable so
    bitmask-style properties are never trapped), or a range-validated text field
    for numbers that declare Min/MaxValue.
    """

    def __init__(self, parent, title, prop, prop_def, kind):
        wx.Dialog.__init__(self, parent, -1, title)
        self._kind = kind
        self._type_value = int(getattr(prop, "typeValue", 0))
        self._prop_def = prop_def
        self._show_as_hex = bool(getattr(prop_def, "ShowAsHex", True))
        self._value_text = None
        self._items = _option_items(prop_def)
        self._value_by_label = {label: value for value, label in self._items}
        self._mono = _monospace_font(self.GetFont())
        current = prop.values[0]

        sizer = wx.BoxSizer(wx.VERTICAL)
        name = getattr(prop_def, "Name", "") or title
        sizer.Add(wx.StaticText(self, -1, name), 0, wx.EXPAND | wx.ALL, 8)

        self._control = self._build_control(current)
        sizer.Add(self._control, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        hint = self._hint_text()
        if hint:
            label = wx.StaticText(self, -1, hint)
            label.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
            sizer.Add(label, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # Live hex<->decimal (or float raw-bits) readout under numeric controls.
        self._conv_label = None
        if self._kind in ("enum", "scalar"):
            self._conv_label = wx.StaticText(self, -1, "")
            self._conv_label.SetFont(self._mono)
            self._conv_label.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
            sizer.Add(self._conv_label, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
            self._control.Bind(wx.EVT_TEXT, self._on_value_changed)
            self._update_conversion()

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

    def _build_control(self, current):
        if self._kind == "bool":
            ctrl = wx.CheckBox(self, -1, propEditBoolCheckbox)
            ctrl.SetValue(bool(current))
            return ctrl
        if self._kind == "enum":
            labels = [label for _, label in self._items]
            ctrl = wx.ComboBox(self, -1, choices=labels, style=wx.CB_DROPDOWN)
            known = next((label for value, label in self._items if value == int(current)), None)
            ctrl.SetValue(known if known is not None else self._fmt(current))
            return ctrl
        ctrl = wx.TextCtrl(self, -1, self._fmt(current))
        if self._show_as_hex:
            ctrl.SetFont(self._mono)
        return ctrl

    def _fmt(self, value):
        return _scalar_to_text(self._type_value, value, self._show_as_hex)

    def _hint_text(self):
        if self._kind == "enum":
            return propEditEnumHint
        if self._kind == "scalar":
            low, high = _scalar_bounds(self._type_value, self._prop_def)
            if low is not None and high is not None:
                return propEditRangeError % (low, high)
        return ""

    def _resolve_value(self, text):
        """Best-effort numeric value of the current text, or None if unparseable."""
        text = text.strip()
        if self._kind == "enum" and text in self._value_by_label:
            return self._value_by_label[text]
        try:
            return _parse_scalar(self._type_value, text)
        except ValueError:
            return None

    def _on_value_changed(self, event):
        self._update_conversion()
        event.Skip()

    def _update_conversion(self):
        if self._conv_label is None:
            return
        value = self._resolve_value(self._control.GetValue())
        self._conv_label.SetLabel("" if value is None else _conversion_text(self._type_value, value))

    def GetValueText(self):
        return self._value_text

    def _reject(self, message):
        wx.MessageBox(message, propEditInvalidTitle, wx.OK | wx.ICON_ERROR, self)

    def _on_ok(self, _event):
        if self._kind == "bool":
            self._value_text = _scalar_to_text(self._type_value, self._control.GetValue())
            self.EndModal(wx.ID_OK)
            return

        text = self._control.GetValue().strip()
        if self._kind == "enum" and text in self._value_by_label:
            value = self._value_by_label[text]
        else:
            try:
                value = _parse_scalar(self._type_value, text)
            except ValueError:
                self._reject(propEditInvalidNumber)
                return

        low, high = _scalar_bounds(self._type_value, self._prop_def)
        if low is not None and high is not None and not (low <= value <= high):
            self._reject(propEditRangeError % (low, high))
            return

        self._value_text = self._fmt(value)
        self.EndModal(wx.ID_OK)


def _parse_checked(type_value, prop_def, text):
    """Parse one numeric field and range-check it.

    Returns ``(value, None)`` on success or ``(None, message)`` on failure, so
    grid/list/entry editors share identical parsing and bounds rules.
    """
    try:
        value = _parse_scalar(type_value, text)
    except ValueError:
        return None, propEditInvalidNumber
    low, high = _scalar_bounds(type_value, prop_def)
    if low is not None and high is not None and not (low <= value <= high):
        return None, propEditRangeError % (low, high)
    return value, None


class TablePropertyDialog(wx.Dialog):
    """Table editor for multi-value properties, consistent with the other
    list-based dialogs.

    Fixed-count properties show a labelled row per value (TGI triples get
    Type/Group/Instance) and are edited in place; variable-length ones add a
    ``#`` index column and gain add/delete/reorder. Values are uppercase-hex
    and monospace when ShowAsHex is set, and validated against the type/range.
    A ``ListCtrl`` scrolls natively, so even Count=256 arrays stay usable.
    """

    def __init__(self, parent, title, prop, prop_def, variable):
        wx.Dialog.__init__(self, parent, -1, title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._type_value = int(getattr(prop, "typeValue", 0))
        self._prop_def = prop_def
        self._show_as_hex = bool(getattr(prop_def, "ShowAsHex", True))
        self._variable = variable
        self._mono = _monospace_font(self.GetFont())
        self._value_text = None
        if variable:
            self._values = list(prop.values)
            self._labels = None
            self._expected_n = None
        else:
            n = max(int(getattr(prop_def, "Count", len(prop.values))), len(prop.values), 1)
            self._values = [prop.values[i] if i < len(prop.values) else 0 for i in range(n)]
            self._labels = _grid_labels(prop_def, n)
            self._expected_n = n

        sizer = wx.BoxSizer(wx.VERTICAL)
        name = getattr(prop_def, "Name", "") or title
        sizer.Add(wx.StaticText(self, -1, name), 0, wx.EXPAND | wx.ALL, 8)

        self.list = wx.ListCtrl(self, -1, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        if variable:
            self.list.InsertColumn(0, propEditListColIndex, width=48)
        else:
            self.list.InsertColumn(0, propEditListColField, width=130)
        self.list.InsertColumn(1, propEditListColValue, width=220)
        self.list.SetFont(self._mono)
        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_edit)
        sizer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        row_buttons = wx.BoxSizer(wx.HORIZONTAL)
        edit_btn = icon_button(self, "pencil", propEditListEdit)
        edit_btn.Bind(wx.EVT_BUTTON, self._on_edit)
        row_buttons.Add(edit_btn, 0, wx.RIGHT, 4)
        if variable:
            add_btn = icon_button(self, "plus", propEditListAdd)
            del_btn = icon_button(self, "trash", propEditListDelete)
            up_btn = icon_button(self, "arrow-up", propEditListUp)
            down_btn = icon_button(self, "arrow-down", propEditListDown)
            add_btn.Bind(wx.EVT_BUTTON, self._on_add)
            del_btn.Bind(wx.EVT_BUTTON, self._on_delete)
            up_btn.Bind(wx.EVT_BUTTON, self._on_up)
            down_btn.Bind(wx.EVT_BUTTON, self._on_down)
            for btn in (add_btn, del_btn, up_btn, down_btn):
                row_buttons.Add(btn, 0, wx.RIGHT, 4)
        sizer.Add(row_buttons, 0, wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # A raw comma-separated view so the whole value can be copied or pasted
        # in one go; it stays the source of truth on OK, with the table writing
        # into it. Edits here sync back to the table when focus leaves.
        sizer.Add(wx.StaticText(self, -1, propEditRawLabel), 0, wx.LEFT | wx.RIGHT, 8)
        self.raw = wx.TextCtrl(self, -1, "", style=wx.TE_MULTILINE)
        self.raw.SetFont(self._mono)
        self.raw.SetMinSize((-1, 48))
        self.raw.Bind(wx.EVT_KILL_FOCUS, self._on_raw_focus)
        sizer.Add(self.raw, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        buttons = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(self, wx.ID_OK)
        cancel_btn = wx.Button(self, wx.ID_CANCEL)
        ok_btn.SetDefault()
        ok_btn.Bind(wx.EVT_BUTTON, self._on_ok)
        buttons.AddButton(ok_btn)
        buttons.AddButton(cancel_btn)
        buttons.Realize()
        sizer.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.SetMinSize((360, 320))
        self.SetSizer(sizer)
        self._refresh()
        self.Fit()

    def _fmt(self, value):
        return _scalar_to_text(self._type_value, value, self._show_as_hex)

    def _label_for(self, row):
        if self._variable:
            return str(row + 1)
        if row < len(self._labels):
            return self._labels[row]
        return propEditValueN % (row + 1)

    def GetValueText(self):
        return self._value_text

    def _refresh(self, selected=None, sync_raw=True):
        self.list.DeleteAllItems()
        for row, value in enumerate(self._values):
            self.list.InsertItem(row, self._label_for(row))
            self.list.SetItem(row, 1, self._fmt(value))
        if selected is not None and 0 <= selected < self.list.GetItemCount():
            self.list.Select(selected)
            self.list.Focus(selected)
        # Table edits push into the raw field; raw edits set sync_raw=False so
        # the user's in-progress text is not overwritten from under them.
        if sync_raw:
            self.raw.SetValue(",".join(self._fmt(v) for v in self._values))

    def _parse_raw(self):
        """Parse the raw field into a value list; returns (values, error)."""
        text = self.raw.GetValue().strip()
        tokens = [tok.strip() for tok in text.split(",")] if text else []
        values = []
        for tok in tokens:
            value, error = _parse_checked(self._type_value, self._prop_def, tok)
            if error:
                return None, error
            values.append(value)
        return values, None

    def _on_raw_focus(self, event):
        event.Skip()
        values, error = self._parse_raw()
        if error is None and values != self._values:
            self._values = values
            self._refresh(sync_raw=False)

    def _selected_row(self):
        return self.list.GetNextItem(-1, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)

    def _prompt(self, value):
        dlg = NumberEntryDialog(self, self._prop_def, self._type_value, self._show_as_hex, value)
        try:
            dlg.CentreOnParent()
            if dlg.ShowModal() == wx.ID_OK:
                return dlg.GetValue()
        finally:
            dlg.Destroy()
        return None

    def _on_edit(self, _event):
        row = self._selected_row()
        if row < 0:
            return
        value = self._prompt(self._values[row])
        if value is not None:
            self._values[row] = value
            self._refresh(row)

    def _on_add(self, _event):
        value = self._prompt(0)
        if value is not None:
            self._values.append(value)
            self._refresh(len(self._values) - 1)

    def _on_delete(self, _event):
        row = self._selected_row()
        if row >= 0:
            del self._values[row]
            self._refresh(min(row, len(self._values) - 1))

    def _on_up(self, _event):
        row = self._selected_row()
        if row > 0:
            self._values[row - 1], self._values[row] = self._values[row], self._values[row - 1]
            self._refresh(row - 1)

    def _on_down(self, _event):
        row = self._selected_row()
        if 0 <= row < len(self._values) - 1:
            self._values[row + 1], self._values[row] = self._values[row], self._values[row + 1]
            self._refresh(row + 1)

    def _on_ok(self, _event):
        # The raw field is authoritative so a paste or manual edit is honoured
        # even if focus never left it before OK was pressed.
        values, error = self._parse_raw()
        if error:
            wx.MessageBox(error, propEditInvalidTitle, wx.OK | wx.ICON_ERROR, self)
            return
        if self._variable:
            if not values:
                wx.MessageBox(propEditListEmpty, propEditInvalidTitle, wx.OK | wx.ICON_ERROR, self)
                return
        elif len(values) != self._expected_n:
            wx.MessageBox(propEditCountMismatch % self._expected_n, propEditInvalidTitle, wx.OK | wx.ICON_ERROR, self)
            return
        self._value_text = ",".join(self._fmt(v) for v in values)
        self.EndModal(wx.ID_OK)


class NumberEntryDialog(wx.Dialog):
    """One-field numeric entry used by the table editor for add/edit."""

    def __init__(self, parent, prop_def, type_value, show_as_hex, value):
        wx.Dialog.__init__(self, parent, -1, propEditEntryTitle)
        self._prop_def = prop_def
        self._type_value = type_value
        self._value = None

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.text = wx.TextCtrl(self, -1, _scalar_to_text(type_value, value, show_as_hex), style=wx.TE_PROCESS_ENTER)
        if show_as_hex:
            self.text.SetFont(_monospace_font(self.GetFont()))
        self.text.Bind(wx.EVT_TEXT_ENTER, self._on_ok)
        sizer.Add(self.text, 0, wx.EXPAND | wx.ALL, 10)

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
        self.text.SetFocus()
        self.text.SelectAll()

    def GetValue(self):
        return self._value

    def _on_ok(self, _event):
        value, error = _parse_checked(self._type_value, self._prop_def, self.text.GetValue().strip())
        if error:
            wx.MessageBox(error, propEditInvalidTitle, wx.OK | wx.ICON_ERROR, self)
            return
        self._value = value
        self.EndModal(wx.ID_OK)
