"""Dependencies dialog for SC4 building lots."""
from __future__ import annotations

import html as html_std
import os.path
import threading
import webbrowser
from dataclasses import dataclass, field

import wx.adv
import wx.html
import wx.lib.sized_controls as sc
from wx.lib.agw import ultimatelistctrl as ULC

from . import config
from .DependencyCatalog import DependencyCatalogClient
from .SC4Data import *
from .SC4DatTools import *
from .SC4PathReader import SC4PATH_MODEL_GID, SC4PATH_TEXTURE_GID, SC4PATH_TYPE
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

BUILTIN_GAME_FILES = {"cohorts.dat", "ep1.dat", "merged.dat", "simcitylocale.dat", "sound.dat"}


_STATUS_SORT_KEY = {"missing": 0, "found": 1, "ignored": 2}

_FILTER_KEYS = (
    ("all", DepDlgFilterAll),
    ("missing", DepDlgFilterMissing),
    ("catalog", DepDlgFilterCatalog),
    ("found", DepDlgFilterFound),
    ("unmatched", DepDlgFilterUnmatched),
    ("ignored", DepDlgFilterIgnored),
    ("models", DepDlgFilterModels),
    ("textures", DepDlgFilterTextures),
    ("props", DepDlgFilterProps),
    ("buildings", DepDlgFilterBuildings),
)

_KIND_LABELS = {
    "Building": DepDlgKindBuilding,
    "Flora": DepDlgKindFlora,
    "Foundation": DepDlgKindFoundation,
    "Icon": DepDlgKindIcon,
    "LTEXT": DepDlgKindLTEXT,
    "Model": DepDlgKindModel,
    "Prop": DepDlgKindProp,
    "Query": DepDlgKindQuery,
    "SC4Path": DepDlgKindSC4Path,
    "Sound": DepDlgKindSound,
    "Texture": DepDlgKindTexture,
}


def _row_sort_key(row):
    return (
        _STATUS_SORT_KEY.get(row.status, 9),
        (row.kind or "").lower(),
        (row.name or "").lower(),
        row.key or "",
    )


def _hex32(v):
    return "0x%08X" % (int(v) & 0xFFFFFFFF)


def is_builtin_game_file(file_name):
    name = os.path.basename(str(file_name or "")).lower()
    if name in BUILTIN_GAME_FILES:
        return True
    return len(name) == len("simcity_1.dat") and name.startswith("simcity_") and name.endswith(".dat") and name[8] in "12345"


def found_catalog_status(file_name, tgi, catalog_enabled, catalog_base_url):
    if is_builtin_game_file(file_name):
        return "built_in"
    if tgi is not None:
        return "pending" if catalog_enabled and catalog_base_url else "disabled"
    return "not_applicable"


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
    catalog_match_reason: str = ""


@dataclass(frozen=True)
class CatalogJob:
    generation: int
    row_id: int
    tgi: tuple[int, int, int] | None
    iid: int | None
    category: str | None
    allow_iid_fallback: bool = True


@dataclass(frozen=True)
class CatalogResult:
    generation: int
    row_id: int
    status: str
    matches: list[dict]
    match_reason: str = ""


def catalog_match_package(match):
    return str(match.get("Package") or "").strip()


def catalog_match_file_name(match):
    return str(match.get("FileName") or "").strip()


def catalog_match_title(match):
    return catalog_match_package(match) or catalog_match_file_name(match)


def catalog_match_url(match):
    websites = str(match.get("Websites") or "").strip()
    return websites.split(";")[0].strip()


def catalog_match_exemplar(match):
    return str(match.get("ExemplarName") or "").strip()


def catalog_match_instance(match):
    text = str(match.get("TGI") or "").strip()
    if not text:
        return ""
    parts = [p.strip() for p in text.split(",")]
    if not parts:
        return ""
    return parts[-1].upper().replace("0X", "0x")


def catalog_reason_text(reason):
    if reason == "exact_tgi":
        return DepDlgCatalogExactTGI
    if reason == "iid_fallback":
        return DepDlgCatalogIIDFallback
    return DepDlgCatalogMatch


def row_kind_text(row):
    return _KIND_LABELS.get(row.kind, row.kind or "")


def first_catalog_match(row):
    return row.catalog_matches[0] if row.catalog_matches else None


def row_display_label(row):
    if row.name:
        return row.name
    if row.catalog_name:
        return row.catalog_name
    if row.parent_id is None and row.referenced_by:
        return row.referenced_by
    return row.kind or row.key


def row_catalog_title(row):
    match = first_catalog_match(row)
    return catalog_match_title(match) if match else ""


def row_catalog_url(row):
    match = first_catalog_match(row)
    return catalog_match_url(match) if match else ""


def row_catalog_file(row):
    match = first_catalog_match(row)
    return catalog_match_file_name(match) if match else ""


def row_catalog_match_text(row):
    if not row.catalog_matches:
        return ""
    reason = catalog_reason_text(row.catalog_match_reason)
    if len(row.catalog_matches) > 1:
        return DepDlgCatalogMultipleCandidates % (reason, len(row.catalog_matches))
    return reason


def row_catalog_state_text(row):
    if row.catalog_matches:
        return row_catalog_match_text(row)
    if row.catalog_status == "pending":
        return DepDlgStatusPending
    if row.catalog_status == "checked":
        return DepDlgCatalogNoMatch
    if row.catalog_status == "unavailable":
        return DepDlgStatusOffline
    if row.catalog_status == "disabled":
        return DepDlgStatusDisabled
    if row.catalog_status == "built_in":
        return DepDlgStatusBuiltIn
    return ""


def dependency_package_buckets(rows):
    buckets = {}
    for row in rows:
        match = first_catalog_match(row)
        if not match:
            continue
        title = catalog_match_title(match)
        if not title:
            continue
        key = title.lower()
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {
                "title": title,
                "package": catalog_match_package(match),
                "file_name": catalog_match_file_name(match),
                "url": catalog_match_url(match),
                "found_count": 0,
                "missing_count": 0,
                "rows": [],
                "ids": set(),
                "refs": set(),
                "local_files": set(),
            }
            buckets[key] = bucket
        else:
            if not bucket["package"] and catalog_match_package(match):
                bucket["package"] = catalog_match_package(match)
            if not bucket["file_name"] and catalog_match_file_name(match):
                bucket["file_name"] = catalog_match_file_name(match)
            if not bucket["url"] and catalog_match_url(match):
                bucket["url"] = catalog_match_url(match)
        if row.status == "missing":
            bucket["missing_count"] += 1
        elif row.status == "found":
            bucket["found_count"] += 1
            if row.source and row.source != DepDlgNotFound:
                bucket["local_files"].add(row.source)
        if row.key:
            bucket["ids"].add(row.key)
        if row.referenced_by:
            bucket["refs"].add(row.referenced_by)
        bucket["rows"].append(row)
    return buckets


def _append_report_package(lines, bucket):
    lines.append("- %s" % bucket["title"])
    if bucket["file_name"] and bucket["file_name"] != bucket["title"]:
        lines.append("  %s" % (DepDlgPackageFile % bucket["file_name"]))
    if bucket["url"]:
        lines.append("  %s" % (DepDlgPackageLink % bucket["url"]))
    if bucket["local_files"]:
        lines.append("  %s" % (DepDlgPackageLocalFile % ", ".join(sorted(bucket["local_files"], key=str.lower))))
    if bucket["ids"]:
        lines.append("  %s" % (DepDlgPackageIDs % ", ".join(sorted(bucket["ids"]))))
    if bucket["refs"]:
        refs = sorted(bucket["refs"], key=str.lower)
        lines.append("  %s" % (DepDlgPackageReferencedBy % "; ".join(refs[:6])))
        if len(refs) > 6:
            lines.append("  %s" % (DepDlgPackageReferencedBy % (DepDlgMoreCount % (len(refs) - 6))))


def build_dependency_report(rows):
    buckets = dependency_package_buckets(rows)
    missing_rows = [row for row in rows if row.status == "missing"]
    unmatched_missing = [row for row in missing_rows if not row.catalog_matches]
    installed_unmatched = [
        row for row in rows
        if row.status == "found" and row.catalog_status == "checked" and not row.catalog_matches
    ]
    missing_packages = [
        bucket for bucket in buckets.values()
        if bucket["missing_count"] > 0
    ]
    installed_packages = [
        bucket for bucket in buckets.values()
        if bucket["found_count"] > 0
    ]

    lines = [DepDlgReportTitle, ""]
    lines.append(DepDlgReportSummary)
    lines.append("- %s" % (DepDlgMissingDependenciesCount % len(missing_rows)))
    lines.append("- %s" % (DepDlgCatalogPackagesSuggested % len(missing_packages)))
    lines.append("- %s" % (DepDlgInstalledCatalogPackagesIdentified % len(installed_packages)))
    lines.append("")

    lines.append(DepDlgMissingCatalogHeading)
    if missing_packages:
        for bucket in sorted(missing_packages, key=lambda b: b["title"].lower()):
            _append_report_package(lines, bucket)
    else:
        lines.append("- %s" % DepDlgNone)
    lines.append("")

    lines.append(DepDlgMissingUnknownHeading)
    if unmatched_missing:
        for row in sorted(unmatched_missing, key=_row_sort_key):
            label = row_display_label(row)
            bits = [row_kind_text(row), label, row.key]
            text = " / ".join([bit for bit in bits if bit])
            if row.referenced_by:
                text += " (%s)" % (DepDlgPackageReferencedBy % row.referenced_by)
            lines.append("- %s" % text)
    else:
        lines.append("- %s" % DepDlgNone)
    lines.append("")

    lines.append(DepDlgInstalledCatalogHeading)
    if installed_packages:
        for bucket in sorted(installed_packages, key=lambda b: b["title"].lower()):
            _append_report_package(lines, bucket)
    else:
        lines.append("- %s" % DepDlgNone)

    if installed_unmatched:
        lines.append("")
        lines.append(DepDlgInstalledWithoutCatalogHeading)
        by_file = sorted({row.source for row in installed_unmatched if row.source}, key=str.lower)
        for file_name in by_file[:50]:
            lines.append("- %s" % file_name)
        if len(by_file) > 50:
            lines.append("- %s" % (DepDlgMoreCount % (len(by_file) - 50)))

    return "\n".join(lines).rstrip() + "\n"


def _match_tgi_group(match, group_id):
    text = str(match.get("TGI") or "")
    parts = [p.strip() for p in text.split(",")]
    if len(parts) < 2:
        return False
    g = parts[1]
    if g == "#":
        return True
    try:
        return int(g, 16) == int(group_id)
    except (ValueError, TypeError):
        return False


def filter_catalog_matches(matches, catalog_category, expected_group=None):
    if expected_group is not None:
        gfiltered = [m for m in matches if _match_tgi_group(m, expected_group)]
        if gfiltered:
            return gfiltered
    if not catalog_category:
        return matches
    wanted = catalog_category.lower()
    return [
        match for match in matches
        if not (match.get("Category") or "")
        or str(match.get("Category") or "").lower() == wanted
    ]


def lookup_catalog(client, tgi=None, iid=None, catalog_category=None, allow_iid_fallback=True):
    expected_group = tgi[1] if tgi is not None else None
    if tgi is not None:
        result = client.search_tgi(tgi)
        if result.matches:
            return result.status, result.matches, "exact_tgi"
        if result.status in ("disabled", "error"):
            return result.status, [], ""
    if allow_iid_fallback and iid is not None:
        result = client.search_iid(iid)
        return result.status, filter_catalog_matches(result.matches, catalog_category, expected_group), "iid_fallback"
    if tgi is not None:
        return "ok", [], ""
    return "disabled", [], ""


def run_catalog_lookups(generation, jobs, catalog_settings, callback):
    client = DependencyCatalogClient(catalog_settings)
    cache = {}
    for job in jobs:
        cache_key = (job.tgi, job.iid if job.allow_iid_fallback else None,
                     job.category if job.allow_iid_fallback else None, job.allow_iid_fallback)
        cached = cache.get(cache_key)
        if cached is None:
            cached = lookup_catalog(
                client, job.tgi, job.iid, job.category,
                allow_iid_fallback=job.allow_iid_fallback,
            )
            cache[cache_key] = cached
        status, matches, reason = cached
        result = CatalogResult(generation, job.row_id, status, matches, reason)
        wx.CallAfter(callback, generation, [result])


class DependencyResourcePanel(wx.html.HtmlWindow):
    """Bottom panel showing source files and catalog suggestions."""

    def __init__(self, parent):
        wx.html.HtmlWindow.__init__(self, parent, -1, style=wx.html.HW_SCROLLBAR_AUTO | wx.BORDER_THEME)
        self._files = []
        self._catalog = {}
        self._files_seen = set()
        self._rows = []
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
        tgi_text = str(match.get("TGI") or "").strip()
        category = str(match.get("Category") or "").strip()
        if not package and not file_name:
            return
        url = websites.split(";")[0].strip()
        pkey = (package or file_name).lower()
        bucket = self._catalog.get(pkey)
        if bucket is None:
            bucket = {"package": package, "file_name": file_name, "url": url,
                      "items": [], "seen": set()}
            self._catalog[pkey] = bucket
        else:
            if not bucket["file_name"] and file_name:
                bucket["file_name"] = file_name
            if not bucket["url"] and url:
                bucket["url"] = url
        instance = ""
        if tgi_text:
            parts = [p.strip() for p in tgi_text.split(",")]
            if parts:
                instance = parts[-1].upper().replace("0X", "0x")
        ikey = (instance, exemplar.lower())
        if ikey in bucket["seen"]:
            return
        bucket["seen"].add(ikey)
        bucket["items"].append({"instance": instance, "exemplar": exemplar, "category": category})

    def Missing(self, v):
        self.bMissing = True

    def Render(self, rows=None):
        if rows is not None:
            self._rows = rows
        buckets = dependency_package_buckets(self._rows)
        missing_packages = [
            bucket for bucket in buckets.values()
            if bucket["missing_count"] > 0
        ]
        installed_packages = [
            bucket for bucket in buckets.values()
            if bucket["found_count"] > 0
        ]
        esc = html_std.escape
        out = ['<html><body style="margin:6px">']
        if self._files:
            out.append('<p style="margin:0 0 4px 0"><b>%s</b></p>' % esc(DepDlgFilesHeading))
            out.append('<ul style="margin:0 0 8px 18px">')
            for name in sorted(self._files, key=str.lower):
                out.append('<li>%s</li>' % esc(name))
            out.append('</ul>')
        if self.bMissing:
            out.append(
                '<p style="margin:0 0 4px 0"><font color="#a00000">'
                '%s</font></p>' % esc(DepDlgSomeMissing)
            )
        for heading, packages in (
            (DepDlgMissingCatalogHeading, missing_packages),
            (DepDlgInstalledCatalogHeading, installed_packages),
        ):
            if not packages:
                continue
            out.append('<p style="margin:0 0 4px 0"><b>%s</b></p>' % esc(heading))
            out.append('<ul style="margin:0 0 8px 18px">')
            for bucket in sorted(packages, key=lambda b: b["title"].lower()):
                package = bucket["package"]
                file_name = bucket["file_name"]
                url = bucket["url"]
                title = esc(package or file_name)
                if url:
                    title = '<a href="%s">%s</a>' % (esc(url, quote=True), title)
                header = title
                if package and file_name:
                    header += ' &mdash; <font color="#555555">%s</font>' % esc(file_name)
                out.append('<li>%s' % header)
                ids = sorted(bucket["ids"])
                refs = sorted(bucket["refs"], key=str.lower)
                local_files = sorted(bucket["local_files"], key=str.lower)
                details = []
                if local_files:
                    details.append(DepDlgPackageLocalFile % ", ".join(local_files[:3]))
                if ids:
                    details.append(DepDlgPackageIDs % ", ".join(ids[:5]))
                if refs:
                    details.append(DepDlgPackageReferencedBy % "; ".join(refs[:4]))
                if details:
                    out.append('<ul style="margin:2px 0 4px 18px">')
                    for detail in details:
                        out.append('<li>%s</li>' % esc(detail))
                    out.append('</ul>')
                out.append('</li>')
            out.append('</ul>')
        if not self._files and not buckets and not self.bMissing:
            out.append('<p><i>%s</i></p>' % esc(DepDlgNoReferencedFiles))
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
        self.selected_row_id = None
        self._visible_row_ids = []
        self.Bind(wx.EVT_WINDOW_DESTROY, self.OnDestroy)

        filter_panel = wx.Panel(pane, -1)
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)
        filter_sizer.Add(wx.StaticText(filter_panel, -1, DepDlgShow), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self._filter_keys = [key for key, label in _FILTER_KEYS]
        self.filterChoice = wx.Choice(filter_panel, -1, choices=[label for key, label in _FILTER_KEYS])
        self.filterChoice.SetSelection(0)
        self.filterChoice.Bind(wx.EVT_CHOICE, self.OnFilterChanged)
        filter_sizer.Add(self.filterChoice, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        self.search = wx.SearchCtrl(filter_panel, -1, style=wx.TE_PROCESS_ENTER)
        self.search.SetDescriptiveText(DepDlgSearchHint)
        try:
            self.search.ShowCancelButton(True)
        except AttributeError:
            pass
        self.search.Bind(wx.EVT_TEXT, self.OnFilterChanged)
        try:
            self.search.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self.OnSearchCancel)
        except AttributeError:
            pass
        filter_sizer.Add(self.search, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        self.summaryText = wx.StaticText(filter_panel, -1, "")
        filter_sizer.Add(self.summaryText, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        self.refreshButton = wx.Button(filter_panel, -1, DepDlgCatalogRefresh)
        self.refreshButton.Bind(wx.EVT_BUTTON, self.OnRefreshCatalog)
        filter_sizer.Add(self.refreshButton, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

        self.copyReportButton = wx.Button(filter_panel, -1, DepDlgCopyReport)
        self.copyReportButton.Bind(wx.EVT_BUTTON, self.OnCopyReport)
        filter_sizer.Add(self.copyReportButton, 0, wx.ALIGN_CENTER_VERTICAL)
        filter_panel.SetSizer(filter_sizer)
        try:
            filter_panel.SetSizerProps(expand=True)
        except AttributeError:
            pass

        self.splitter = wx.SplitterWindow(pane, -1, style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH)
        list_panel = wx.Panel(self.splitter, -1)
        list_sizer = wx.BoxSizer(wx.VERTICAL)
        self.list = ULC.UltimateListCtrl(
            list_panel, -1,
            agwStyle=ULC.ULC_REPORT | ULC.ULC_HRULES | ULC.ULC_VRULES | ULC.ULC_SHOW_TOOLTIPS | ULC.ULC_SINGLE_SEL,
            size=(820, 430),
        )
        self._mono = _monospace_font(self.list.GetFont())
        self.COL_NAME = 0
        self.COL_STATUS = 1
        self.COL_TYPE = 2
        self.COL_ID = 3
        self.COL_LOCAL = 4
        self.COL_CATALOG = 5
        self.COL_MATCH = 6
        for idx, (label, width) in enumerate((
            (DepDlgColName, 240),
            (DepDlgColStatus, 90),
            (DepDlgColType, 80),
            (DepDlgColID, 230),
            (DepDlgColLocalFile, 190),
            (DepDlgColCatalog, 240),
            (DepDlgColMatch, 120),
        )):
            self.list.InsertColumn(idx, label, width=width)
        self.list.SetMinSize((780, 360))
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnRowSelected)
        list_sizer.Add(self.list, 1, wx.EXPAND)
        list_panel.SetSizer(list_sizer)

        details_panel = wx.Panel(self.splitter, -1)
        details_sizer = wx.BoxSizer(wx.VERTICAL)
        self.notebook = wx.Notebook(details_panel, -1)
        self.detailPanel = self.CreateDetailPanel(self.notebook)
        self.lb = DependencyResourcePanel(self.notebook)
        self.reportText = wx.TextCtrl(
            self.notebook, -1, "",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP | wx.BORDER_THEME,
        )
        self.notebook.AddPage(self.detailPanel, DepDlgDetailsTab)
        self.notebook.AddPage(self.lb, DepDlgPackageSummaryTab)
        self.notebook.AddPage(self.reportText, DepDlgReportTab)
        details_sizer.Add(self.notebook, 1, wx.EXPAND)
        details_panel.SetSizer(details_sizer)

        self.splitter.SplitVertically(list_panel, details_panel, 850)
        self.splitter.SetMinimumPaneSize(320)
        try:
            self.splitter.SetSashGravity(0.70)
        except AttributeError:
            pass
        self.splitter.SetMinSize((1180, 430))
        try:
            self.splitter.SetSizerProps(expand=True, proportion=1)
        except AttributeError:
            pass

        self.BuildRows()
        self.RenderRows()
        self.lb.Render(self.rows)
        self.UpdateSummary()
        self.UpdateDetails()
        self.UpdateReport()
        self.StartCatalogLookups()

        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.Fit()
        self.SetMinSize((1220, 680))

    def CreateDetailPanel(self, parent):
        panel = wx.Panel(parent, -1)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.detailTitle = wx.StaticText(panel, -1, DepDlgNoSelection)
        title_font = self.detailTitle.GetFont()
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        self.detailTitle.SetFont(title_font)
        sizer.Add(self.detailTitle, 0, wx.EXPAND | wx.ALL, 6)

        grid = wx.FlexGridSizer(cols=2, hgap=6, vgap=5)
        grid.AddGrowableCol(1)
        self.detailFields = {}

        def add_field(key, label):
            grid.Add(wx.StaticText(panel, -1, label), 0, wx.ALIGN_CENTER_VERTICAL)
            ctrl = wx.TextCtrl(panel, -1, "", style=wx.TE_READONLY | wx.BORDER_THEME)
            grid.Add(ctrl, 1, wx.EXPAND)
            self.detailFields[key] = ctrl

        add_field("status", DepDlgColStatus)
        add_field("type", DepDlgColType)
        add_field("id", DepDlgColID)
        add_field("local", DepDlgDetailLocalFile)
        add_field("referenced_by", DepDlgDetailReferencedBy)
        add_field("parent", DepDlgDetailParent)
        add_field("catalog_package", DepDlgCatalogPackage)
        add_field("catalog_file", DepDlgDetailCatalogFile)
        add_field("match", DepDlgColMatch)
        sizer.Add(grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        action_row = wx.BoxSizer(wx.HORIZONTAL)
        self.copyIDButton = wx.Button(panel, -1, DepDlgCopyID)
        self.copyIDButton.Bind(wx.EVT_BUTTON, self.OnCopySelectedID)
        action_row.Add(self.copyIDButton, 0, wx.RIGHT, 4)
        self.copyPackageButton = wx.Button(panel, -1, DepDlgCopyPackage)
        self.copyPackageButton.Bind(wx.EVT_BUTTON, self.OnCopySelectedPackage)
        action_row.Add(self.copyPackageButton, 0)
        sizer.Add(action_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        link_row = wx.BoxSizer(wx.HORIZONTAL)
        link_row.Add(wx.StaticText(panel, -1, DepDlgDetailLink), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.detailLink = wx.adv.HyperlinkCtrl(panel, -1, DepDlgCatalogNoLink, "")
        self.detailLink.Enable(False)
        link_row.Add(self.detailLink, 1, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(link_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        sizer.Add(wx.StaticText(panel, -1, DepDlgDetailCandidates), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.candidateList = wx.ListCtrl(panel, -1, style=wx.LC_REPORT | wx.BORDER_THEME)
        for idx, (label, width) in enumerate((
            (DepDlgCatalogPackage, 150),
            (DepDlgColLocalFile, 165),
            (DepDlgColType, 90),
            (DepDlgColID, 115),
        )):
            self.candidateList.InsertColumn(idx, label, width=width)
        sizer.Add(self.candidateList, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        panel.SetSizer(sizer)
        return panel

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
        catalog_status = found_catalog_status(source, tgi, self.catalog.enabled, self.catalog.base_url)
        row = self.AddRow("found", kind, name, key, source, referenced_by,
                          parent_id=parent_id, tgi=tgi, catalog_status=catalog_status)
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
            return DepDlgLocalStateFound
        if row.status == "ignored":
            return DepDlgLocalStateIgnored
        return DepDlgLocalStateMissing

    def RowSourceText(self, row):
        return row.source

    def RowCatalogText(self, row):
        return row_catalog_title(row)

    def RowLabel(self, row):
        return row_display_label(row)

    def RowMatchesFilter(self, row):
        selection = self.filterChoice.GetSelection()
        selected = self._filter_keys[selection] if 0 <= selection < len(self._filter_keys) else "all"
        if selected == "missing":
            return row.status == "missing"
        if selected == "catalog":
            return bool(row.catalog_matches)
        if selected == "found":
            return row.status == "found"
        if selected == "unmatched":
            return row.catalog_status == "checked" and not row.catalog_matches and row.status != "ignored"
        if selected == "ignored":
            return row.status == "ignored"
        if selected == "models":
            return row.kind == "Model"
        if selected == "textures":
            return row.kind == "Texture"
        if selected == "props":
            return row.kind == "Prop"
        if selected == "buildings":
            return row.kind == "Building"
        return True

    def RowMatchesSearch(self, row):
        text = self.search.GetValue().strip().lower()
        if not text:
            return True
        haystack = [
            row_display_label(row),
            row_kind_text(row),
            row.key,
            row.source,
            row.referenced_by,
            row_catalog_title(row),
            row_catalog_file(row),
            row_catalog_match_text(row),
        ]
        for match in row.catalog_matches:
            haystack.extend([
                catalog_match_package(match),
                catalog_match_file_name(match),
                catalog_match_exemplar(match),
                catalog_match_instance(match),
            ])
        return text in " ".join([value for value in haystack if value]).lower()

    def RowStatusColour(self, row):
        if row.status == "found":
            return wx.Colour(0, 110, 0)
        if row.status == "ignored":
            return wx.Colour(120, 120, 120)
        return wx.Colour(170, 0, 0)

    def RowCatalogColour(self, row):
        if row.catalog_matches:
            return wx.Colour(160, 95, 0) if row.status == "missing" else wx.Colour(0, 100, 120)
        if row.catalog_status == "pending":
            return wx.Colour(80, 80, 160)
        if row.catalog_status == "checked":
            return wx.Colour(110, 110, 110)
        if row.catalog_status == "built_in":
            return wx.Colour(80, 120, 80)
        if row.catalog_status in ("unavailable", "disabled"):
            return wx.Colour(170, 0, 0)
        return wx.Colour(90, 90, 90)

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
        selected_index = None
        self.list.Freeze()
        try:
            self.list.DeleteAllItems()
            self._visible_row_ids = []
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
                if not self.RowMatchesFilter(row) or not self.RowMatchesSearch(row):
                    if is_child:
                        continue
                    if not any(
                        self.RowMatchesFilter(c) and self.RowMatchesSearch(c)
                        for c in children_by_parent.get(row.id, [])
                    ):
                        continue
                self.list.InsertStringItem(idx, "")
                display_name = row.name or row.catalog_name or row_kind_text(row)
                name = ("    " + display_name) if is_child else self.RowLabel(row)
                self._SetCell(idx, self.COL_STATUS, self.RowStatusText(row), colour=self.RowStatusColour(row))
                self._SetCell(idx, self.COL_TYPE, row_kind_text(row))
                self._SetCell(idx, self.COL_NAME, name)
                self._SetCell(idx, self.COL_ID, row.key, font=self._mono)
                self._SetCell(idx, self.COL_LOCAL, self.RowSourceText(row))
                self._SetCell(idx, self.COL_CATALOG, self.RowCatalogText(row))
                self._SetCell(idx, self.COL_MATCH, row_catalog_state_text(row), colour=self.RowCatalogColour(row))
                self._visible_row_ids.append(row.id)
                if row.id == self.selected_row_id:
                    selected_index = idx
                idx += 1
        finally:
            self.list.Thaw()
        if self.selected_row_id is None and self._visible_row_ids:
            self.selected_row_id = self._visible_row_ids[0]
            selected_index = 0
        if selected_index is not None:
            self.list.Select(selected_index)
        elif self.selected_row_id is not None and self.selected_row_id not in self._visible_row_ids:
            self.selected_row_id = None
            self.UpdateDetails()
        self.UpdateSummary()

    def OnFilterChanged(self, event):
        self.RenderRows()
        event.Skip()

    def OnSearchCancel(self, event):
        self.search.ChangeValue("")
        self.RenderRows()
        event.Skip()

    def OnRowSelected(self, event):
        idx = event.GetIndex()
        if 0 <= idx < len(self._visible_row_ids):
            self.selected_row_id = self._visible_row_ids[idx]
            self.UpdateDetails()
        event.Skip()

    def UpdateSummary(self):
        missing = len([row for row in self.rows if row.status == "missing"])
        found = len([row for row in self.rows if row.status == "found"])
        matched = len([row for row in self.rows if row.catalog_matches])
        unmatched = len([
            row for row in self.rows
            if row.catalog_status == "checked" and not row.catalog_matches and row.status != "ignored"
        ])
        self.summaryText.SetLabel(DepDlgSummary % (missing, found, matched, unmatched))

    def UpdateDetails(self):
        row = self.rows_by_id.get(self.selected_row_id)
        if row is None:
            self.detailTitle.SetLabel(DepDlgNoSelection)
            for ctrl in self.detailFields.values():
                ctrl.ChangeValue("")
            self.copyIDButton.Enable(False)
            self.copyPackageButton.Enable(False)
            self.detailLink.SetLabel(DepDlgCatalogNoLink)
            self.detailLink.SetURL("")
            self.detailLink.Enable(False)
            self.candidateList.DeleteAllItems()
            return

        parent = self.rows_by_id.get(row.parent_id) if row.parent_id is not None else None
        self.detailTitle.SetLabel(row_display_label(row))
        values = {
            "status": self.RowStatusText(row),
            "type": row_kind_text(row),
            "id": row.key,
            "local": self.RowSourceText(row),
            "referenced_by": row.referenced_by,
            "parent": row_display_label(parent) if parent is not None else "",
            "catalog_package": row_catalog_title(row),
            "catalog_file": row_catalog_file(row),
            "match": row_catalog_state_text(row),
        }
        for key, ctrl in self.detailFields.items():
            ctrl.ChangeValue(values.get(key, ""))

        self.copyIDButton.Enable(bool(row.key))
        self.copyPackageButton.Enable(bool(row_catalog_title(row)))
        url = row_catalog_url(row)
        self.detailLink.SetLabel(url or DepDlgCatalogNoLink)
        self.detailLink.SetURL(url or "")
        self.detailLink.Enable(bool(url))

        self.candidateList.DeleteAllItems()
        for idx, match in enumerate(row.catalog_matches):
            self.candidateList.InsertItem(idx, catalog_match_title(match))
            self.candidateList.SetItem(idx, 1, catalog_match_file_name(match))
            self.candidateList.SetItem(idx, 2, str(match.get("Category") or ""))
            self.candidateList.SetItem(idx, 3, catalog_match_instance(match))

    def UpdateReport(self):
        self.reportText.ChangeValue(build_dependency_report(self.rows))

    def CopyTextToClipboard(self, text):
        if not text:
            return False
        data = wx.TextDataObject(text)
        if not wx.TheClipboard.Open():
            return False
        try:
            return bool(wx.TheClipboard.SetData(data))
        finally:
            wx.TheClipboard.Close()

    def OnCopySelectedID(self, event):
        row = self.rows_by_id.get(self.selected_row_id)
        if row is not None and self.CopyTextToClipboard(row.key):
            self.summaryText.SetLabel(DepDlgCopyIDDone)
        event.Skip()

    def OnCopySelectedPackage(self, event):
        row = self.rows_by_id.get(self.selected_row_id)
        package = row_catalog_title(row) if row is not None else ""
        if self.CopyTextToClipboard(package):
            self.summaryText.SetLabel(DepDlgCopyPackageDone)
        event.Skip()

    def OnRefreshCatalog(self, event):
        self._catalog_generation += 1
        for row in self.rows:
            row.catalog_matches = []
            row.catalog_name = ""
            row.catalog_match_reason = ""
            if row.status == "ignored":
                row.catalog_status = "not_applicable"
            elif row.status == "found":
                row.catalog_status = found_catalog_status(row.source, row.tgi, self.catalog.enabled, self.catalog.base_url)
            elif row.status == "missing" and (row.tgi is not None or row.iid is not None):
                row.catalog_status = "pending" if self.catalog.enabled and self.catalog.base_url else "disabled"
            else:
                row.catalog_status = "not_applicable"
        self.ScheduleRender()
        self.StartCatalogLookups()
        event.Skip()

    def OnCopyReport(self, event):
        text = build_dependency_report(self.rows)
        copied = self.CopyTextToClipboard(text)
        self.summaryText.SetLabel(DepDlgReportCopied if copied else DepDlgReportCopyFailed)
        event.Skip()

    def ScheduleRender(self):
        if self._render_scheduled or not self._alive:
            return
        self._render_scheduled = True
        wx.CallLater(150, self.FlushRender)

    def FlushRender(self):
        if not self._alive:
            return
        self._render_scheduled = False
        self.RenderRows()
        self.lb.Render(self.rows)
        self.UpdateDetails()
        self.UpdateReport()

    def StartCatalogLookups(self):
        generation = self._catalog_generation + 1
        jobs = []
        for row in self.rows:
            if row.status == "missing" and row.catalog_status == "pending" and row.tgi is not None:
                jobs.append(CatalogJob(generation, row.id, row.tgi, row.iid, row.catalog_category, True))
        for row in self.rows:
            if row.status == "missing" and row.catalog_status == "pending" and row.tgi is None and row.iid is not None:
                jobs.append(CatalogJob(generation, row.id, row.tgi, row.iid, row.catalog_category, True))
        for row in self.rows:
            if row.status == "found" and row.catalog_status == "pending" and row.tgi is not None:
                jobs.append(CatalogJob(generation, row.id, row.tgi, None, row.catalog_category, False))
        if not jobs:
            return
        self._catalog_generation = generation
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
            self.ScheduleRender()

    def ApplyCatalogResult(self, result):
        if not self._alive or result.generation != self._catalog_generation:
            return False
        row = self.rows_by_id.get(result.row_id)
        if row is None:
            return False
        if result.matches:
            row.catalog_status = "checked"
            row.catalog_matches = result.matches
            row.catalog_match_reason = result.match_reason
            first_name = str(result.matches[0].get("ExemplarName") or "").strip()
            if first_name:
                row.catalog_name = first_name
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
        try:
            desc_tgi = tuple(desc.exemplar.entry.tgi)
        except Exception:
            desc_tgi = None
        parent_row = self.AddFoundRow(kind, desc.name, self.EntryTGIText(desc.exemplar.entry),
                                      desc.fileName, referenced_by, tgi=desc_tgi)
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
                self.AddMissingRow("Query", "", self.TGIText(tgi), referenced_by, parent_id=pid,
                                   tgi=tgi, catalog_category="Query")

        prop_icon = desc.exemplar.GetProp(2317746872)
        if prop_icon:
            tgi = (2238569388, 1782082854, prop_icon[0])
            entry = self.virtualDAT.getEntry(tgi[0], tgi[1], tgi[2])
            if entry:
                self.AddFoundRow("Icon", "", self.TGIText(tgi), entry.fileName, referenced_by,
                                 parent_id=pid, tgi=tgi)
            else:
                self.AddMissingRow("Icon", "", self.TGIText(tgi), referenced_by, parent_id=pid,
                                   tgi=tgi, catalog_category="Icon")

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
                self.AddMissingRow("LTEXT", "", self.TGIText(UVNK), referenced_by, parent_id=pid,
                                   tgi=tuple(UVNK), catalog_category="LTEXT")
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
                self.AddMissingRow("LTEXT", "", self.TGIText(IDK), referenced_by, parent_id=pid,
                                   tgi=tuple(IDK), catalog_category="LTEXT")
        else:
            if IDK is not None:
                self.AddIgnoredRow("LTEXT", "", self.TGIText(IDK), referenced_by, "placeholder",
                                   parent_id=pid)

    def BuildRows(self):
        tex_ids = []
        prop_ids = []
        flora_ids = []
        path_ids = []
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

            if values[0] == 7:
                if len(values) <= 15:
                    continue
                sc4path_id = values[15]
                if sc4path_id in path_ids or sc4path_id == 0:
                    continue
                path_ids.append(sc4path_id)
                found_entry = None
                found_tgi = None
                for gid in (SC4PATH_MODEL_GID, SC4PATH_TEXTURE_GID):
                    entry = self.virtualDAT.getEntry(SC4PATH_TYPE, gid, sc4path_id)
                    if entry:
                        found_entry = entry
                        found_tgi = (SC4PATH_TYPE, gid, sc4path_id)
                        break
                if found_entry:
                    self.AddFoundRow("SC4Path", "", self.TGIText(found_tgi), found_entry.fileName,
                                     DepDlgNetwork, tgi=found_tgi)
                else:
                    label_tgi = (SC4PATH_TYPE, SC4PATH_MODEL_GID, sc4path_id)
                    self.AddMissingRow("SC4Path", "", self.TGIText(label_tgi), DepDlgNetwork,
                                       tgi=label_tgi, iid=sc4path_id, catalog_category="SC4Path")
