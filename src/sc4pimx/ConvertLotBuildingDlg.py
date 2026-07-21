"""Wizard UI for cloning/converting a paired SC4 lot and building."""

import wx

from .TablerIcons import dialog_button, icon_bitmap, set_button_icon
from .translation import *

MODE_CLONE = 'clone'
MODE_OVERRIDE = 'override'


def suggested_conversion_name(source_name, mode):
    template = (
        convertBuildingSuggestedOverrideName
        if mode == MODE_OVERRIDE
        else convertBuildingSuggestedConvertedName
    )
    return template % source_name


def _tgi_text(tgi):
    return '0x%08X-0x%08X-0x%08X' % tuple(tgi)


class ConvertLotBuildingDialog(wx.Dialog):
    """Three-page category/output/review wizard."""

    def __init__(self, parent, categories, source_lot_name, source_lot_tgi,
                 source_building_name, source_building_tgi, default_name):
        super().__init__(
            parent, title=convertBuildingWizardTitle,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._categories = list(categories)
        self._visible = []
        self._selected = None
        self._source_lot_name = source_lot_name
        self._source_lot_tgi = tuple(source_lot_tgi)
        self._source_building_name = source_building_name
        self._source_building_tgi = tuple(source_building_tgi)
        self._default_base_name = default_name or source_building_name
        self._name_is_custom = False

        root = wx.BoxSizer(wx.VERTICAL)
        self.book = wx.Simplebook(self)
        self.book.AddPage(self._make_category_page(), '')
        self.book.AddPage(self._make_output_page(default_name), '')
        self.book.AddPage(self._make_review_page(), '')
        root.Add(self.book, 1, wx.EXPAND | wx.ALL, 10)

        line = wx.StaticLine(self)
        root.Add(line, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.back = wx.Button(self, label=convertBuildingBack)
        self.next = wx.Button(self, label=convertBuildingNext)
        self.finish = wx.Button(self, wx.ID_OK, convertBuildingFinish)
        self.cancel = dialog_button(self, wx.ID_CANCEL)
        set_button_icon(self.back, 'arrow-back-up')
        set_button_icon(self.next, 'arrow-forward-up')
        set_button_icon(self.finish, 'check')
        set_button_icon(self.cancel, 'x')
        buttons.AddStretchSpacer(1)
        buttons.Add(self.back, 0, wx.RIGHT, 6)
        buttons.Add(self.next, 0, wx.RIGHT, 6)
        buttons.Add(self.finish, 0, wx.RIGHT, 6)
        buttons.Add(self.cancel, 0)
        root.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)

        self.SetSizer(root)
        self.SetMinSize((720, 520))
        self.SetSize((820, 610))
        self.CentreOnParent()

        self.Bind(wx.EVT_BUTTON, self._on_back, self.back)
        self.Bind(wx.EVT_BUTTON, self._on_next, self.next)
        self.Bind(wx.EVT_BUTTON, self._on_finish, self.finish)
        self._show_page(0)

    def _heading(self, parent, title, body):
        sizer = wx.BoxSizer(wx.VERTICAL)
        heading = wx.StaticText(parent, label=title)
        font = heading.GetFont()
        font.SetPointSize(font.GetPointSize() + 2)
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        heading.SetFont(font)
        sizer.Add(heading, 0, wx.BOTTOM, 5)
        explanation = wx.StaticText(parent, label=body)
        explanation.Wrap(730)
        sizer.Add(explanation, 0, wx.BOTTOM, 10)
        return sizer

    def _make_category_page(self):
        page = wx.Panel(self.book)
        root = self._heading(page, convertBuildingCategoryTitle, convertBuildingCategoryHelp)
        self.search = wx.SearchCtrl(page, style=wx.TE_PROCESS_ENTER)
        self.search.ShowCancelButton(True)
        self.search.SetDescriptiveText(convertBuildingCategorySearch)
        root.Add(self.search, 0, wx.EXPAND | wx.BOTTOM, 8)
        self.category_list = wx.ListCtrl(page, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.category_list.InsertColumn(0, convertBuildingCategoryColumnType, width=105)
        self.category_list.InsertColumn(1, convertBuildingCategoryColumnPath, width=550)
        self.category_list.InsertColumn(2, convertBuildingCategoryColumnID, width=110)
        root.Add(self.category_list, 1, wx.EXPAND)
        page.SetSizer(root)
        self.search.Bind(wx.EVT_TEXT, self._on_filter)
        self.category_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_category_selected)
        self.category_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_category_activated)
        self._refresh_categories()
        return page

    def _make_output_page(self, default_name):
        page = wx.Panel(self.book)
        root = self._heading(page, convertBuildingOutputTitle, convertBuildingOutputHelp)
        root.Add(wx.StaticText(page, label=convertBuildingNameLabel), 0, wx.BOTTOM, 3)
        self.name = wx.TextCtrl(
            page,
            value=suggested_conversion_name(self._default_base_name, MODE_CLONE),
        )
        root.Add(self.name, 0, wx.EXPAND | wx.BOTTOM, 12)
        self.mode = wx.RadioBox(
            page, label=convertBuildingModeLabel,
            choices=(convertBuildingModeClone, convertBuildingModeOverride),
            majorDimension=1, style=wx.RA_SPECIFY_ROWS,
        )
        root.Add(self.mode, 0, wx.EXPAND | wx.BOTTOM, 12)
        self.mode_help = wx.StaticText(page, label='')
        self.mode_help.Wrap(730)
        root.Add(self.mode_help, 0, wx.EXPAND)
        page.SetSizer(root)
        self.name.Bind(wx.EVT_TEXT, self._on_name_changed)
        self.mode.Bind(wx.EVT_RADIOBOX, self._on_mode_changed)
        self._on_mode_changed(None)
        return page

    def _make_review_page(self):
        page = wx.Panel(self.book)
        root = self._heading(page, convertBuildingReviewTitle, convertBuildingReviewHelp)
        self.review = wx.StaticText(page, label='')
        self.review.Wrap(730)
        root.Add(self.review, 0, wx.EXPAND | wx.BOTTOM, 12)
        warning_row = wx.BoxSizer(wx.HORIZONTAL)
        self.warning_icon = wx.StaticBitmap(page, bitmap=icon_bitmap('alert-triangle', 20, '#AA2323'))
        warning_row.Add(self.warning_icon, 0, wx.RIGHT | wx.TOP, 7)
        self.review_warning = wx.StaticText(page, label='')
        self.review_warning.SetForegroundColour(wx.Colour(170, 35, 35))
        self.review_warning.Wrap(730)
        warning_row.Add(self.review_warning, 1, wx.EXPAND)
        root.Add(warning_row, 0, wx.EXPAND)
        page.SetSizer(root)
        return page

    def _refresh_categories(self):
        query = self.search.GetValue().strip().casefold()
        selected_category = self._selected.category if self._selected else None
        self.category_list.Freeze()
        try:
            self.category_list.DeleteAllItems()
            self._visible = []
            for item in self._categories:
                path = ' › '.join(item.breadcrumb)
                kind_label = (
                    convertBuildingTypeGrowable
                    if item.target_kind == 'growable'
                    else convertBuildingTypePloppable
                )
                haystack = ('%s %s 0x%08x' % (kind_label, path, item.category.ID)).casefold()
                if query and query not in haystack:
                    continue
                row = self.category_list.InsertItem(self.category_list.GetItemCount(), kind_label)
                self.category_list.SetItem(row, 1, path)
                self.category_list.SetItem(row, 2, '0x%08X' % item.category.ID)
                self._visible.append(item)
                if item.category is selected_category:
                    self.category_list.Select(row)
        finally:
            self.category_list.Thaw()
        if hasattr(self, 'back'):
            self._update_navigation()

    def _on_filter(self, event):
        self._refresh_categories()
        event.Skip()

    def _on_category_selected(self, event):
        index = event.GetIndex()
        if 0 <= index < len(self._visible):
            self._selected = self._visible[index]
        self._update_navigation()

    def _on_category_activated(self, event):
        self._on_category_selected(event)
        if self._selected is not None:
            self._show_page(1)

    def _on_mode_changed(self, event):
        mode = MODE_CLONE if self.mode.GetSelection() == 0 else MODE_OVERRIDE
        if mode == MODE_CLONE:
            self.mode_help.SetLabel(convertBuildingModeCloneHelp)
        else:
            self.mode_help.SetLabel(convertBuildingModeOverrideHelp)
        if not self._name_is_custom:
            # ChangeValue avoids emitting EVT_TEXT, so an automatic suggestion
            # never marks itself as a user customization.
            self.name.ChangeValue(suggested_conversion_name(self._default_base_name, mode))
        self.mode_help.Wrap(730)
        if event is not None:
            event.Skip()

    def _on_name_changed(self, event):
        self._name_is_custom = True
        event.Skip()

    def _update_review(self):
        category_path = ' › '.join(self._selected.breadcrumb)
        mode_label = convertBuildingModeClone if self.mode.GetSelection() == 0 else convertBuildingModeOverride
        te_policy = (
            convertBuildingTEPreserved
            if self._selected.target_kind == 'ploppable'
            else convertBuildingTERemoved
        )
        self.review.SetLabel(convertBuildingReviewTemplate % (
            self._source_lot_name, _tgi_text(self._source_lot_tgi),
            self._source_building_name, _tgi_text(self._source_building_tgi),
            category_path, mode_label, self.name.GetValue().strip(), te_policy,
        ))
        self.review_warning.SetLabel(
            convertBuildingOverrideWarning if self.mode.GetSelection() == 1 else ''
        )
        self.warning_icon.Show(self.mode.GetSelection() == 1)
        self.review.Wrap(730)
        self.review_warning.Wrap(730)

    def _show_page(self, index):
        if index == 2:
            self._update_review()
        self.book.SetSelection(index)
        self._update_navigation()

    def _update_navigation(self):
        page = self.book.GetSelection()
        self.back.Enable(page > 0)
        self.next.Show(page < 2)
        self.finish.Show(page == 2)
        self.next.Enable(page != 0 or self._selected is not None)
        self.Layout()

    def _on_back(self, event):
        self._show_page(max(0, self.book.GetSelection() - 1))

    def _on_next(self, event):
        page = self.book.GetSelection()
        if page == 0 and self._selected is None:
            wx.MessageBox(convertBuildingChooseCategory, convertBuildingWizardTitle,
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        if page == 1 and not self.name.GetValue().strip():
            wx.MessageBox(convertBuildingEnterName, convertBuildingWizardTitle,
                          wx.OK | wx.ICON_INFORMATION, self)
            self.name.SetFocus()
            return
        self._show_page(min(2, page + 1))

    def _on_finish(self, event):
        self.EndModal(wx.ID_OK)

    def GetSelection(self):
        return {
            'category': self._selected.category,
            'target_kind': self._selected.target_kind,
            'name': self.name.GetValue().strip(),
            'mode': MODE_CLONE if self.mode.GetSelection() == 0 else MODE_OVERRIDE,
        }
