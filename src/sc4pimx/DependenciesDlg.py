"""Dependencies dialog for SC4 building lots."""
from __future__ import annotations

import html as html_std
import io
import os.path
import threading
import webbrowser
from dataclasses import dataclass, field

import wx.html
import wx.lib.sized_controls as sc
from wx.lib.agw import ultimatelistctrl as ULC
from PIL import Image

from . import config
from .DependencyCatalog import DependencyCatalogClient, format_catalog_match
from .SC4Data import *
from .SC4DatTools import *
from .translation import *

offsetGID = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 15, 16, 17, 18, 19, 20, 35]

SOUND_TYPE_ID = 0x0B8D821A
SOUND_GIDS = (
    0x2A4D1937,  # Disaster, Destruction, Siren, Splash, Low Pitch Ambient
    0x2A4D193D,  # Query Sounds
    0xAA4D1920,  # Activate, Audio Loop, Ambience Decayed, HLS Entries
    0xAA4D1930,  # Fireworks, Construction, Sims, UDI, Alien, Crowds, Animals
    0xCA4D1943,  # UI Button Click & Plop, Wire, Fire, Tools Effects
    0xCA4D1948,  # Occupant Instance Sounds
    0xEA4D192A,  # Fireworks, Riots, Children, Anger, Demo, Crime, Construction, Jet
)


_STATUS_SORT_KEY = {"missing": 0, "catalog": 1, "found": 2, "ignored": 3}


def _row_sort_key(row):
    return (
        _STATUS_SORT_KEY.get(row.status, 9),
        (row.kind or "").lower(),
        (row.name or "").lower(),
        row.key or "",
    )


def _hex32(v):
    return "0x%08X" % (int(v) & 0xFFFFFFFF)


def _monospace_font(base_font):
    try:
        available = set(wx.FontEnumerator.GetFacenames())
    except Exception:
        available = set()
    size = base_font.GetPointSize()
    for name in ('Consolas', 'Cascadia Mono', 'Courier New'):
        if name in available:
            return wx.Font(size, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL,
                           wx.FONTWEIGHT_NORMAL, faceName=name)
    return wx.Font(size, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)


@dataclass
class DependencyRow:
    id: int
    status: str
    kind: str
    name: str
    key: str
    source: str
    referenced_by: str
    parent_id: int | None = None
    tgi: tuple[int, int, int] | None = None
    iid: int | None = None
    catalog_category: str | None = None
    catalog_status: str = "not_applicable"
    catalog_matches: list[dict] = field(default_factory=list)
    catalog_name: str = ""


@dataclass(frozen=True)
class CatalogJob:
    generation: int
    row_id: int
    tgi: tuple[int, int, int] | None
    iid: int | None
    category: str | None


@dataclass(frozen=True)
class CatalogResult:
    generation: int
    row_id: int
    status: str
    matches: list[dict]


def filter_catalog_matches(matches, catalog_category):
    if not catalog_category:
        return matches
    wanted = catalog_category.lower()
    filtered = [
        match for match in matches
        if str(match.get("Category") or "").lower() == wanted
    ]
    return filtered or matches


def lookup_catalog(client, tgi=None, iid=None, catalog_category=None):
    if tgi is not None:
        result = client.search_tgi(tgi)
        if result.matches:
            return result.status, filter_catalog_matches(result.matches, catalog_category)
        if result.status in ("disabled", "error"):
            return result.status, []
    if iid is not None:
        result = client.search_iid(iid)
        return result.status, filter_catalog_matches(result.matches, catalog_category)
    return "disabled", []


def run_catalog_lookups(generation, jobs, catalog_settings, callback):
    client = DependencyCatalogClient(catalog_settings)
    results = []
    for job in jobs:
        status, matches = lookup_catalog(client, job.tgi, job.iid, job.category)
        results.append(CatalogResult(generation, job.row_id, status, matches))
    wx.CallAfter(callback, generation, results)


class DependencyResourcePanel(wx.html.HtmlWindow):
    """Bottom panel showing source files and catalog suggestions."""

    def __init__(self, parent):
        wx.html.HtmlWindow.__init__(self, parent, -1, style=wx.html.HW_SCROLLBAR_AUTO | wx.BORDER_THEME)
        self._files = []
        self._catalog = []
        self._files_seen = set()
        self._catalog_seen = set()
        self.bMissing = False
        base = self.GetFont()
        try:
            self.SetStandardFonts(base.GetPointSize(), base.GetFaceName())
        except Exception:
            pass
        self.Render()

    def OnLinkClicked(self, link):
        href = link.GetHref()
        if href:
            webbrowser.open(href)

    def Append(self, value):
        name = os.path.split(value)[1]
        key = name.lower()
        if key in self._files_seen:
            return
        self._files_seen.add(key)
        self._files.append(name)

    def AppendCatalog(self, match):
        package = str(match.get("Package") or "").strip()
        file_name = str(match.get("FileName") or "").strip()
        websites = str(match.get("Websites") or "").strip()
        exemplar = str(match.get("ExemplarName") or "").strip()
        if not package and not file_name:
            return
        key = (package or file_name).lower()
        if key in self._catalog_seen:
            return
        self._catalog_seen.add(key)
        url = websites.split(";")[0].strip()
        self._catalog.append((package, file_name, url, exemplar))

    def Missing(self, v):
        self.bMissing = True

    def Render(self):
        esc = html_std.escape
        out = ['<html><body style="margin:6px">']
        if self._files:
            out.append('<p style="margin:0 0 4px 0"><b>Files contributing to this lot</b></p>')
            out.append('<ul style="margin:0 0 8px 18px">')
            for name in sorted(self._files, key=str.lower):
                out.append('<li>%s</li>' % esc(name))
            out.append('</ul>')
        if self.bMissing:
            out.append(
                '<p style="margin:0 0 4px 0"><font color="#a00000">'
                'Some referenced files are not present in the loaded plugins.'
                '</font></p>'
            )
        if self._catalog:
            out.append('<p style="margin:0 0 4px 0"><b>Suggested from the SC4 Props and Textures Catalog</b></p>')
            out.append('<ul style="margin:0 0 8px 18px">')
            for package, file_name, url, exemplar in self._catalog:
                title = esc(package or file_name)
                if url:
                    title = '<a href="%s">%s</a>' % (esc(url, quote=True), title)
                parts = []
                if exemplar:
                    parts.append('<i>%s</i>' % esc(exemplar))
                if package and file_name:
                    parts.append('<font color="#555555">%s</font>' % esc(file_name))
                tail = (' &mdash; ' + ' &middot; '.join(parts)) if parts else ''
                out.append('<li>%s%s</li>' % (title, tail))
            out.append('</ul>')
        if not self._files and not self._catalog and not self.bMissing:
            out.append('<p><i>No referenced files.</i></p>')
        out.append('</body></html>')
        self.SetPage(''.join(out))


class DependenciesDlg(sc.SizedDialog):

    def __init__(self, parent, exemplar):
        sc.SizedDialog.__init__(self, parent, -1, title=DependenciesDlgTitleMsg, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        pane = self.GetContentsPane()
        pane.SetSizerType('vertical')
        self.exemplar = exemplar
        self.virtualDAT = getattr(parent, 'virtual_dat', None) or getattr(parent, 'virtualDAT')
        self.catalog_settings = config.load_dependency_catalog()
        self.catalog = DependencyCatalogClient(self.catalog_settings)
        self.rows = []
        self.rows_by_id = {}
        self._next_row_id = 1
        self._catalog_generation = 0
        self._alive = True
        self._render_scheduled = False
        self.Bind(wx.EVT_WINDOW_DESTROY, self.OnDestroy)

        filter_panel = wx.Panel(pane, -1)
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)
        filter_sizer.Add(wx.StaticText(filter_panel, -1, "Show:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.filterChoice = wx.Choice(filter_panel, -1, choices=[
            "All", "Missing", "Catalog", "Found", "Ignored",
            "Models", "Textures", "Props", "Buildings",
        ])
        self.filterChoice.SetSelection(0)
        self.filterChoice.Bind(wx.EVT_CHOICE, self.OnFilterChanged)
        filter_sizer.Add(self.filterChoice, 0)
        filter_panel.SetSizer(filter_sizer)
        try:
            filter_panel.SetSizerProps(expand=True)
        except AttributeError:
            pass

        self.list = ULC.UltimateListCtrl(
            pane, -1,
            agwStyle=ULC.ULC_REPORT | ULC.ULC_HRULES | ULC.ULC_VRULES | ULC.ULC_SHOW_TOOLTIPS | ULC.ULC_SINGLE_SEL,
            size=(1050, 360),
        )
        self._mono = _monospace_font(self.list.GetFont())
        self.COL_NAME = 0
        self.COL_STATUS = 1
        self.COL_TYPE = 2
        self.COL_ID = 3
        self.COL_SOURCE = 4
        self.COL_REFBY = 5
        for idx, (label, width) in enumerate((
            ("Name", 230),
            ("Status", 90),
            ("Type", 80),
            ("ID", 230),
            ("Source / Catalog", 280),
            ("Referenced by", 250),
        )):
            self.list.InsertColumn(idx, label, width=width)
        self.list.SetMinSize((950, 240))
        self.list.SetSizerProps(expand=True, proportion=2)

        self.lb = DependencyResourcePanel(pane)
        self.lb.SetMinSize((950, 140))
        self.lb.SetSizerProps(expand=True, proportion=1)

        self.BuildRows()
        self.RenderRows()
        self.lb.Render()
        self.StartCatalogLookups()

        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.Fit()
        self.SetMinSize((1050, 620))

    def AddFileName(self, fileName):
        self.lb.Append(fileName)

    def AddRow(self, status, kind, name, key, source, referenced_by, parent_id=None,
               tgi=None, iid=None, catalog_category=None, catalog_status="not_applicable"):
        row = DependencyRow(
            id=self._next_row_id,
            status=status,
            kind=kind,
            name=name or "",
            key=key or "",
            source=source or "",
            referenced_by=referenced_by or "",
            parent_id=parent_id,
            tgi=tuple(tgi) if tgi is not None else None,
            iid=iid,
            catalog_category=catalog_category,
            catalog_status=catalog_status,
        )
        self._next_row_id += 1
        self.rows.append(row)
        self.rows_by_id[row.id] = row
        return row

    def AddFoundRow(self, kind, name, key, file_name, referenced_by, parent_id=None, tgi=None):
        source = os.path.split(file_name)[1] if file_name else ""
        row = self.AddRow("found", kind, name, key, source, referenced_by,
                          parent_id=parent_id, tgi=tgi)
        if file_name:
            self.lb.Append(file_name)
        return row

    def AddMissingRow(self, kind, name, key, referenced_by, parent_id=None,
                      tgi=None, iid=None, catalog_category=None):
        catalog_status = "not_applicable"
        if tgi is not None or iid is not None:
            catalog_status = "pending" if self.catalog.enabled and self.catalog.base_url else "disabled"
        self.lb.Missing(DepDlgMissing)
        return self.AddRow(
            "missing", kind, name, key, DepDlgNotFound, referenced_by,
            parent_id=parent_id, tgi=tgi, iid=iid,
            catalog_category=catalog_category, catalog_status=catalog_status,
        )

    def AddIgnoredRow(self, kind, name, key, referenced_by, source="ignored", parent_id=None):
        return self.AddRow("ignored", kind, name, key, source, referenced_by,
                           parent_id=parent_id)

    def RowStatusText(self, row):
        if row.status == "found":
            return "Found"
        if row.status == "ignored":
            return "Ignored"
        if row.status == "catalog":
            return "Catalog"
        if row.catalog_status == "pending":
            return "Pending"
        if row.catalog_status == "checked":
            return "Checked"
        if row.catalog_status == "unavailable":
            return "Offline"
        if row.catalog_status == "disabled":
            return "Disabled"
        return "Missing"

    def RowSourceText(self, row):
        if row.catalog_matches:
            match = row.catalog_matches[0]
            package = str(match.get("Package") or "").strip()
            return package or format_catalog_match(match) or row.source
        return row.source

    def RowLabel(self, row):
        if row.name:
            return row.name
        if row.catalog_name:
            return row.catalog_name
        if row.parent_id is None and row.referenced_by:
            return row.referenced_by
        return row.kind or row.key

    def RowMatchesFilter(self, row):
        selected = self.filterChoice.GetStringSelection()
        if selected == "Missing":
            return row.status == "missing"
        if selected == "Catalog":
            return row.status == "catalog"
        if selected == "Found":
            return row.status == "found"
        if selected == "Ignored":
            return row.status == "ignored"
        if selected == "Models":
            return row.kind == "Model"
        if selected == "Textures":
            return row.kind == "Texture"
        if selected == "Props":
            return row.kind == "Prop"
        if selected == "Buildings":
            return row.kind == "Building"
        return True

    def RowStatusColour(self, row):
        if row.status == "found":
            return wx.Colour(0, 110, 0)
        if row.status == "catalog":
            return wx.Colour(160, 95, 0)
        if row.status == "ignored":
            return wx.Colour(120, 120, 120)
        if row.catalog_status == "pending":
            return wx.Colour(80, 80, 160)
        return wx.Colour(170, 0, 0)

    def _SetCell(self, row_idx, col, text, font=None, colour=None):
        info = ULC.UltimateListItem()
        info._itemId = row_idx
        info._col = col
        info._mask = ULC.ULC_MASK_TEXT
        info._text = text or ""
        if font is not None:
            info.SetFont(font)
            info._mask |= ULC.ULC_MASK_FONT
        if colour is not None:
            info.SetTextColour(colour)
            info._mask |= ULC.ULC_MASK_FONTCOLOUR
        self.list.SetItem(info)

    def RenderRows(self):
        if not self._alive or not bool(self.list):
            return
        self.list.Freeze()
        try:
            self.list.DeleteAllItems()
            children_by_parent = {}
            roots = []
            for row in self.rows:
                if row.parent_id is None:
                    roots.append(row)
                else:
                    children_by_parent.setdefault(row.parent_id, []).append(row)
            roots.sort(key=_row_sort_key)
            for kids in children_by_parent.values():
                kids.sort(key=_row_sort_key)
            ordered = []
            for root in roots:
                ordered.append((root, False))
                for child in children_by_parent.get(root.id, []):
                    ordered.append((child, True))
            idx = 0
            for row, is_child in ordered:
                if not self.RowMatchesFilter(row):
                    if is_child:
                        continue
                    if not any(self.RowMatchesFilter(c) for c in children_by_parent.get(row.id, [])):
                        continue
                self.list.InsertStringItem(idx, "")
                display_name = row.name or row.catalog_name or row.kind
                name = ("    " + display_name) if is_child else self.RowLabel(row)
                self._SetCell(idx, self.COL_STATUS, self.RowStatusText(row), colour=self.RowStatusColour(row))
                self._SetCell(idx, self.COL_TYPE, row.kind)
                self._SetCell(idx, self.COL_NAME, name)
                self._SetCell(idx, self.COL_ID, row.key, font=self._mono)
                self._SetCell(idx, self.COL_SOURCE, self.RowSourceText(row))
                self._SetCell(idx, self.COL_REFBY, "" if is_child else row.referenced_by)
                idx += 1
        finally:
            self.list.Thaw()

    def OnFilterChanged(self, event):
        self.RenderRows()

    def ScheduleRender(self):
        if self._render_scheduled or not self._alive:
            return
        self._render_scheduled = True
        wx.CallLater(100, self.FlushRender)

    def FlushRender(self):
        if not self._alive:
            return
        self._render_scheduled = False
        self.RenderRows()
        self.lb.Render()

    def StartCatalogLookups(self):
        jobs = [
            CatalogJob(self._catalog_generation + 1, row.id, row.tgi, row.iid, row.catalog_category)
            for row in self.rows
            if row.status == "missing" and row.catalog_status == "pending"
        ]
        if not jobs:
            return
        self._catalog_generation += 1
        worker = threading.Thread(
            target=run_catalog_lookups,
            args=(self._catalog_generation, jobs, dict(self.catalog_settings), self.ApplyCatalogBatch),
            name="dependency-catalog",
            daemon=True,
        )
        worker.start()

    def ApplyCatalogBatch(self, generation, results):
        if not self._alive or generation != self._catalog_generation:
            return
        changed = False
        for result in results:
            if self.ApplyCatalogResult(result):
                changed = True
        if changed:
            self.RenderRows()
            self.lb.Render()

    def ApplyCatalogResult(self, result):
        if not self._alive or result.generation != self._catalog_generation:
            return False
        row = self.rows_by_id.get(result.row_id)
        if row is None:
            return False
        if result.matches:
            row.status = "catalog"
            row.catalog_status = "checked"
            row.catalog_matches = result.matches
            first_name = str(result.matches[0].get("ExemplarName") or "").strip()
            if first_name:
                row.catalog_name = first_name
            for match in result.matches[:5]:
                self.lb.AppendCatalog(match)
        elif result.status == "ok":
            row.catalog_status = "checked"
        elif result.status == "error":
            row.catalog_status = "unavailable"
        elif result.status == "disabled":
            row.catalog_status = "disabled"
        return True

    def OnDestroy(self, event):
        if event.GetEventObject() is self:
            self._alive = False
            self._catalog_generation += 1
        event.Skip()

    def IsValidRTK(self, rtk):
        if rtk is None:
            return False
        if rtk[0] == 1523640343 and rtk[1] == 3134937073 and rtk[2] == 0:
            return False
        if rtk[0] == 698733036 and rtk[1] == 707025145 and rtk[2] == 0:
            return False
        if rtk[0] == 0 and rtk[1] == 0 and rtk[2] == 0:
            return False
        return True

    def IsValidLTEXTKey(self, tgi):
        if tgi is None:
            return False
        if tgi[0] == 0 and tgi[1] == 0 and tgi[2] == 0:
            return False
        if tgi[0] == 0x2026960B and tgi[1] == 0 and tgi[2] == 0:
            return False
        return True

    def TGIText(self, tgi):
        return "0x%08X-0x%08X-0x%08X" % (tgi[0], tgi[1], tgi[2])

    def EntryTGIText(self, entry):
        try:
            return self.TGIText(entry.tgi)
        except Exception:
            return ""

    def AddBuildingOrProp(self, group, desc):
        referenced_by = "%s: %s" % (group, desc.name)
        if group == DepDlgProps:
            kind = "Prop"
        elif group == DepDlgFlora:
            kind = "Flora"
        elif group == DepDlgBuildingFoundation:
            kind = "Foundation"
        else:
            kind = "Building"
        parent_row = self.AddFoundRow(kind, desc.name, self.EntryTGIText(desc.exemplar.entry),
                                      desc.fileName, referenced_by)
        pid = parent_row.id

        for prop_id in (662775840, 662775841):
            rtk = desc.exemplar.GetProp(prop_id)
            if self.IsValidRTK(rtk):
                entry = self.virtualDAT.getEntry(rtk[0], rtk[1], rtk[2])
                if entry:
                    self.AddFoundRow("Model", "", self.TGIText(rtk), entry.fileName, referenced_by,
                                     parent_id=pid, tgi=rtk)
                else:
                    self.AddMissingRow("Model", "", self.TGIText(rtk), referenced_by,
                                       parent_id=pid, tgi=rtk)

        rtk = desc.exemplar.GetProp(662775844)
        if rtk:
            rkt_data = tuple(rtk)
            for line in range(len(rkt_data) // 8):
                data = rkt_data[line * 8:line * 8 + 8]
                model_tgi = data[5:8]
                if not self.IsValidRTK(model_tgi):
                    continue
                entry = self.virtualDAT.getEntry(model_tgi[0], model_tgi[1], model_tgi[2])
                if entry:
                    self.AddFoundRow("Model", "", self.TGIText(model_tgi), entry.fileName, referenced_by,
                                     parent_id=pid, tgi=model_tgi)
                else:
                    self.AddMissingRow("Model", "", self.TGIText(model_tgi), referenced_by,
                                       parent_id=pid, tgi=model_tgi)

        prop_query = desc.exemplar.GetProp(709468037)
        if prop_query:
            tgi = (0, 2527069872, prop_query[0])
            entry = self.virtualDAT.getEntry(tgi[0], tgi[1], tgi[2])
            if entry:
                self.AddFoundRow("Query", "", self.TGIText(tgi), entry.fileName, referenced_by,
                                 parent_id=pid, tgi=tgi)
            else:
                self.AddMissingRow("Query", "", self.TGIText(tgi), referenced_by, parent_id=pid)

        prop_icon = desc.exemplar.GetProp(2317746872)
        if prop_icon:
            tgi = (2238569388, 1782082854, prop_icon[0])
            entry = self.virtualDAT.getEntry(tgi[0], tgi[1], tgi[2])
            if entry:
                self.AddFoundRow("Icon", "", self.TGIText(tgi), entry.fileName, referenced_by,
                                 parent_id=pid, tgi=tgi)
            else:
                self.AddMissingRow("Icon", "", self.TGIText(tgi), referenced_by, parent_id=pid)

        for prop_id in [2854081431, 1246499630, 172757963, 3384359510, 3390691274]:
            prop_sound = desc.exemplar.GetProp(prop_id)
            if prop_sound:
                iid = prop_sound[0]
                found_entry = None
                found_tgi = None
                for gid in SOUND_GIDS:
                    entry = self.virtualDAT.getEntry(SOUND_TYPE_ID, gid, iid)
                    if entry:
                        found_entry = entry
                        found_tgi = (SOUND_TYPE_ID, gid, iid)
                        break
                if found_entry:
                    self.AddFoundRow("Sound", "", self.TGIText(found_tgi), found_entry.fileName,
                                     referenced_by, parent_id=pid, tgi=found_tgi)
                else:
                    label = "0x%08X-(any sound G)-0x%08X" % (SOUND_TYPE_ID, iid)
                    self.AddMissingRow("Sound", "", label, referenced_by, parent_id=pid,
                                       iid=iid, catalog_category="Sound")

        UVNK = desc.exemplar.GetProp(2319542937)
        if self.IsValidLTEXTKey(UVNK):
            uvnks = [self.virtualDAT.getEntry(UVNK[0], UVNK[1] + i, UVNK[2]) for i in offsetGID]
            found = False
            for entry in uvnks:
                if entry:
                    self.AddFoundRow("LTEXT", "", self.TGIText(entry.tgi), entry.fileName, referenced_by,
                                     parent_id=pid, tgi=entry.tgi)
                    found = True
            if not found:
                self.AddMissingRow("LTEXT", "", self.TGIText(UVNK), referenced_by, parent_id=pid)
        else:
            if UVNK is not None:
                self.AddIgnoredRow("LTEXT", "", self.TGIText(UVNK), referenced_by, "placeholder",
                                   parent_id=pid)

        IDK = desc.exemplar.GetProp(3393284789)
        if self.IsValidLTEXTKey(IDK):
            idks = [self.virtualDAT.getEntry(IDK[0], IDK[1] + i, IDK[2]) for i in offsetGID]
            found = False
            for entry in idks:
                if entry:
                    self.AddFoundRow("LTEXT", "", self.TGIText(entry.tgi), entry.fileName, referenced_by,
                                     parent_id=pid, tgi=entry.tgi)
                    found = True
            if not found:
                self.AddMissingRow("LTEXT", "", self.TGIText(IDK), referenced_by, parent_id=pid)
        else:
            if IDK is not None:
                self.AddIgnoredRow("LTEXT", "", self.TGIText(IDK), referenced_by, "placeholder",
                                   parent_id=pid)

    def BuildRows(self):
        tex_ids = []
        prop_ids = []
        flora_ids = []
        building_foundation = self.exemplar.GetProp(2298271863)
        if building_foundation:
            possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == building_foundation[0],
                               self.virtualDAT.categories[1829068375].descriptors)
            added = False
            for desc in possibles:
                self.AddBuildingOrProp(DepDlgBuildingFoundation, desc)
                added = True
            if not added:
                self.AddMissingRow("Building", "", _hex32(building_foundation[0]), DepDlgBuildingFoundation,
                                   iid=building_foundation[0], catalog_category="Building")

        for lcp in range(2297284864, 2297286144):
            values = self.exemplar.GetProp(lcp)
            if values is None:
                break
            if values[0] == 0:
                added = False
                building_id = values[12]
                if building_id in self.virtualDAT.categories:
                    for desc in self.virtualDAT.categories[building_id].descriptors:
                        if desc.exemplar.GetProp(16)[0] == 2:
                            self.AddBuildingOrProp(DepDlgBuilding, desc)
                            added = True
                else:
                    possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == building_id,
                                       self.virtualDAT.categories[210746197].descriptors)
                    for desc in possibles:
                        self.AddBuildingOrProp(DepDlgBuilding, desc)
                        added = True
                if not added:
                    self.AddMissingRow("Building", "", _hex32(building_id), DepDlgBuilding,
                                       iid=building_id, catalog_category="Building")

            if values[0] == 1:
                prop_id = values[12]
                if prop_id not in prop_ids:
                    prop_ids.append(prop_id)
                    added = False
                    if prop_id in self.virtualDAT.categories:
                        for desc in self.virtualDAT.categories[prop_id].descriptors:
                            if desc.exemplar.GetProp(16)[0] == 30:
                                self.AddBuildingOrProp(DepDlgProps, desc)
                                added = True
                    else:
                        possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == prop_id,
                                           self.virtualDAT.categories[210746660].descriptors)
                        for desc in possibles:
                            self.AddBuildingOrProp(DepDlgProps, desc)
                            added = True
                    if not added:
                        self.AddMissingRow("Prop", "", _hex32(prop_id), DepDlgProps,
                                           iid=prop_id, catalog_category="Prop")

            if values[0] == 2:
                tex_id = values[12]
                if tex_id not in tex_ids:
                    tgi = (2058686020, 159781726, tex_id)
                    tex_entry = self.virtualDAT.getEntry(tgi[0], tgi[1], tgi[2])
                    if tex_entry is None:
                        self.AddMissingRow("Texture", "", _hex32(tex_id), DepDlgTextures,
                                           tgi=tgi, iid=tex_id, catalog_category="Texture")
                    else:
                        self.AddFoundRow("Texture", "", _hex32(tex_id), tex_entry.fileName,
                                         DepDlgTextures, tgi=tgi)
                    tex_ids.append(tex_id)

            if values[0] == 4:
                flora_id = values[12]
                if flora_id not in flora_ids:
                    flora_ids.append(flora_id)
                    added = False
                    possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == flora_id,
                                       self.virtualDAT.categories[1830116951].descriptors)
                    for desc in possibles:
                        self.AddBuildingOrProp(DepDlgFlora, desc)
                        added = True
                    if not added:
                        self.AddMissingRow("Flora", "", _hex32(flora_id), DepDlgFlora,
                                           iid=flora_id, catalog_category="Flora")
