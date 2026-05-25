"""Float32 response-curve editor for exemplar properties."""

import math

import wx
import wx.lib.plot as wxplot

from .SC4DatTools import format_float_value


def is_curve_property(prop, prop_def):
    """Return whether a property can be represented as x/y Float32 pairs."""
    if prop is None or prop_def is None:
        return False
    if getattr(prop_def, "Type", None) != "Float32":
        return False
    try:
        count = int(getattr(prop_def, "Count", 1))
    except (TypeError, ValueError):
        return False
    if count >= 0 or abs(count) % 2 != 0:
        return False
    values = getattr(prop, "values", ())
    return len(values) >= 2 and len(values) % 2 == 0


def values_to_points(values):
    return [(float(values[i]), float(values[i + 1])) for i in range(0, len(values), 2)]


def points_to_value_text(points):
    values = []
    for x, y in points:
        values.append(format_float_value(float(x)))
        values.append(format_float_value(float(y)))
    return ",".join(values)


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


def padded_axis_ranges(points, padding=0.08):
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]

    def padded_range(values):
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Curve values must be finite numbers.")
        low = min(values)
        high = max(values)
        span = high - low
        if not math.isfinite(span):
            raise ValueError("Curve range is too large to plot.")
        if span == 0:
            pad = abs(low) * padding if low != 0 else 1.0
        else:
            pad = span * padding
        return (low - pad, high + pad)

    return padded_range(xs), padded_range(ys)


class CurveEditorDialog(wx.Dialog):

    def __init__(self, parent, title, prop_name, values):
        wx.Dialog.__init__(
            self,
            parent,
            -1,
            title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._points = values_to_points(values)
        self._value_text = None

        sizer = wx.BoxSizer(wx.VERTICAL)
        body = wx.BoxSizer(wx.HORIZONTAL)

        self.plot = wxplot.PlotCanvas(self)
        self.plot.SetInitialSize((520, 340))
        self.plot.SetEnableZoom(True)
        self.plot.SetEnableGrid(True)
        self.plot.SetUseScientificNotation(False)
        # wx.lib.plot right-click zoom-out can overflow its tick generator on
        # some ranges. Use right-click as a deterministic fit-to-extent reset.
        self.plot.canvas.Unbind(wx.EVT_RIGHT_DOWN)
        self.plot.canvas.Bind(wx.EVT_RIGHT_DOWN, self._on_plot_right_down)
        body.Add(self.plot, 1, wx.EXPAND | wx.ALL, 6)

        side = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(self, -1, prop_name)
        side.Add(label, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 6)

        self.points = wx.ListCtrl(self, -1, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.points.InsertColumn(0, "X", width=112)
        self.points.InsertColumn(1, "Y", width=112)
        self.points.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_edit_point)
        side.Add(self.points, 1, wx.EXPAND | wx.ALL, 6)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        add_btn = wx.Button(self, -1, "Add")
        edit_btn = wx.Button(self, -1, "Edit")
        del_btn = wx.Button(self, -1, "Delete")
        sort_btn = wx.Button(self, -1, "Sort")
        extent_btn = wx.Button(self, -1, "Extent")
        extent_btn.SetToolTip("Zoom to the full curve with padding.")
        add_btn.Bind(wx.EVT_BUTTON, self._on_add)
        edit_btn.Bind(wx.EVT_BUTTON, self._on_edit_point)
        del_btn.Bind(wx.EVT_BUTTON, self._on_delete)
        sort_btn.Bind(wx.EVT_BUTTON, self._on_sort)
        extent_btn.Bind(wx.EVT_BUTTON, self._on_zoom_extent)
        buttons.Add(add_btn, 0, wx.RIGHT, 4)
        buttons.Add(edit_btn, 0, wx.RIGHT, 4)
        buttons.Add(del_btn, 0, wx.RIGHT, 4)
        buttons.Add(sort_btn, 0, wx.RIGHT, 4)
        buttons.Add(extent_btn, 0)
        side.Add(buttons, 0, wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        body.Add(side, 0, wx.EXPAND | wx.ALL, 0)
        sizer.Add(body, 1, wx.EXPAND)

        dialog_buttons = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(self, wx.ID_OK)
        cancel_btn = wx.Button(self, wx.ID_CANCEL)
        ok_btn.SetDefault()
        ok_btn.Bind(wx.EVT_BUTTON, self._on_ok)
        dialog_buttons.AddButton(ok_btn)
        dialog_buttons.AddButton(cancel_btn)
        dialog_buttons.Realize()
        sizer.Add(dialog_buttons, 0, wx.EXPAND | wx.ALL, 6)

        self.SetSizer(sizer)
        self.SetMinSize((760, 420))
        self._load_grid(self._points)
        self._refresh_plot(fit=True)
        self.Fit()

    def GetValueText(self):
        return self._value_text

    def _load_grid(self, points):
        self.points.DeleteAllItems()
        for row, (x, y) in enumerate(points):
            self.points.InsertItem(row, format_float_value(x))
            self.points.SetItem(row, 1, format_float_value(y))

    def _read_grid(self):
        points = []
        for row in range(self.points.GetItemCount()):
            x_text = self.points.GetItemText(row, 0).strip()
            y_text = self.points.GetItemText(row, 1).strip()
            if not x_text and not y_text:
                continue
            x = float(x_text)
            y = float(y_text)
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError("Curve values must be finite numbers.")
            points.append((x, y))
        if not points:
            raise ValueError("Curve must contain at least one point.")
        return points

    def _refresh_plot(self, fit=False):
        try:
            points = self._read_grid()
        except ValueError:
            points = self._points
        objects = []
        if len(points) > 1:
            objects.append(wxplot.PolyLine(points, colour=wx.Colour(42, 99, 181), width=2))
        objects.append(wxplot.PolyMarker(points, colour=wx.Colour(201, 68, 59), marker="circle", size=1.6))
        graphics = wxplot.PlotGraphics(objects, "", "X", "Y")
        if fit:
            try:
                x_axis, y_axis = padded_axis_ranges(points)
            except ValueError:
                self.plot.Draw(graphics)
            else:
                self.plot.Draw(graphics, xAxis=x_axis, yAxis=y_axis)
        else:
            self.plot.Draw(graphics)

    def _on_add(self, _event):
        points = self._read_grid_or_default()
        if points:
            x, y = points[-1]
            points.append((x + 1.0, y))
        else:
            points.append((0.0, 0.0))
        self._load_grid(points)
        self._refresh_plot()

    def _on_delete(self, _event):
        row = self._selected_row()
        if row >= 0:
            self.points.DeleteItem(row)
        self._refresh_plot()

    def _on_sort(self, _event):
        points = sorted(self._read_grid_or_default(), key=lambda point: point[0])
        self._load_grid(points)
        self._refresh_plot()

    def _on_zoom_extent(self, _event):
        self._refresh_plot(fit=True)

    def _on_plot_right_down(self, _event):
        self._refresh_plot(fit=True)

    def _on_ok(self, _event):
        try:
            points = self._read_grid()
        except ValueError as exc:
            wx.MessageBox(str(exc), "Invalid curve", wx.OK | wx.ICON_ERROR, self)
            return
        self._value_text = points_to_value_text(points)
        self.EndModal(wx.ID_OK)

    def _read_grid_or_default(self):
        try:
            return self._read_grid()
        except ValueError:
            return list(self._points)

    def _selected_row(self):
        return self.points.GetNextItem(-1, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)

    def _on_edit_point(self, _event):
        row = self._selected_row()
        if row < 0:
            return
        dlg = PointEditDialog(
            self,
            self.points.GetItemText(row, 0),
            self.points.GetItemText(row, 1),
        )
        try:
            dlg.CentreOnParent()
            if dlg.ShowModal() == wx.ID_OK:
                x, y = dlg.GetPoint()
                self.points.SetItem(row, 0, format_float_value(x))
                self.points.SetItem(row, 1, format_float_value(y))
                self._refresh_plot()
        finally:
            dlg.Destroy()


class PointEditDialog(wx.Dialog):

    def __init__(self, parent, x_value, y_value):
        wx.Dialog.__init__(self, parent, -1, "Edit point")
        self._point = None

        sizer = wx.BoxSizer(wx.VERTICAL)
        form = wx.FlexGridSizer(2, 2, 6, 8)
        form.AddGrowableCol(1)
        form.Add(wx.StaticText(self, -1, "X"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.x_text = wx.TextCtrl(self, -1, x_value)
        form.Add(self.x_text, 1, wx.EXPAND)
        form.Add(wx.StaticText(self, -1, "Y"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.y_text = wx.TextCtrl(self, -1, y_value)
        form.Add(self.y_text, 1, wx.EXPAND)
        sizer.Add(form, 1, wx.EXPAND | wx.ALL, 10)

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

    def GetPoint(self):
        return self._point

    def _on_ok(self, _event):
        try:
            x = float(self.x_text.GetValue())
            y = float(self.y_text.GetValue())
        except ValueError:
            wx.MessageBox("Enter numeric X and Y values.", "Invalid point", wx.OK | wx.ICON_ERROR, self)
            return
        if not math.isfinite(x) or not math.isfinite(y):
            wx.MessageBox("Enter finite numeric X and Y values.", "Invalid point", wx.OK | wx.ICON_ERROR, self)
            return
        self._point = (x, y)
        self.EndModal(wx.ID_OK)


def edit_curve_property(parent, title, prop_name, values):
    dlg = CurveEditorDialog(parent, title, prop_name, values)
    try:
        _centre_on_top_level(dlg, parent)
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.GetValueText()
    finally:
        dlg.Destroy()
    return None
