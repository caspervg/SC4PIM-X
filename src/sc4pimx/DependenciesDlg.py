"""Dependencies dialog for SC4 building lots."""
from __future__ import annotations

import html as html_std
import os.path
import threading
import webbrowser
from dataclasses import dataclass, field

import wx.html
import wx.lib.sized_controls as sc
from wx.lib.agw import ultimatelistctrl as ULC

from . import config
from .DependencyCatalog import DependencyCatalogClient
from .SC4Data import *
from .SC4DatTools import *
from .SC4PathReader import SC4PATH_MODEL_GID, SC4PATH_TEXTURE_GID, SC4PATH_TYPE
from .TablerIcons import icon_bitmap, set_button_icon
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
IGNORED_SOUND_IIDS = {0x8A8B7DD1, 0x2A8B7DB4}

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

_KIND_GROUP_LABELS = {
    "Building": DepDlgFilterBuildings,
    "Flora": DepDlgKindFlora,
    "Foundation": DepDlgKindFoundation,
    "Icon": DepDlgKindIcon,
    "LTEXT": DepDlgKindLTEXT,
    "Model": DepDlgFilterModels,
    "Prop": DepDlgFilterProps,
    "Query": DepDlgKindQuery,
    "SC4Path": DepDlgKindSC4Path,
    "Sound": DepDlgKindSound,
    "Texture": DepDlgFilterTextures,
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


def identification_catalog_status(row, catalog_enabled, catalog_base_url):
    if row.status == "ignored" or not row.catalog_lookup:
        return "not_applicable"
    if row.status == "found":
        return found_catalog_status(row.source, row.tgi, catalog_enabled, catalog_base_url)
    if row.status == "missing" and (row.tgi is not None or row.iid is not None):
        return "pending" if catalog_enabled and catalog_base_url else "disabled"
    return "not_applicable"


def is_ignored_sound_iid(iid):
    try:
        return (int(str(iid), 0) & 0xFFFFFFFF) in IGNORED_SOUND_IIDS
    except (TypeError, ValueError):
        return False


def is_placeholder_ltext_key(tgi):
    return tgi is not None and tuple(tgi) == (0, 0, 0)


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
    catalog_lookup: bool = True
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


def row_kind_group_text(row):
    return _KIND_GROUP_LABELS.get(row.kind, row_kind_text(row))


def row_status_text(row):
    if row.status == "found":
        return DepDlgLocalStateFound
    if row.status == "ignored":
        return DepDlgLocalStateIgnored
    return DepDlgLocalStateMissing


def first_catalog_match(row):
    return row.catalog_matches[0] if row.catalog_matches else None


def _normalised_asset_text(value):
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def _is_generic_asset_name(row, value):
    text = _normalised_asset_text(value)
    if not text:
        return True
    kind = _normalised_asset_text(row_kind_text(row))
    group = _normalised_asset_text(row_kind_group_text(row))
    category = _normalised_asset_text(row.catalog_category)
    generic = {v for v in (kind, group, category) if v}
    generic.update({
        "building", "buildings",
        "flora",
        "foundation", "foundations",
        "icon", "icons",
        "ltext",
        "model", "models",
        "prop", "props",
        "query", "queries",
        "sc4path", "sc4paths", "sc4 path", "sc4 paths",
        "sound", "sounds",
        "texture", "textures",
    })
    return text in generic


def row_specific_label(row):
    for value in (row.name, row.catalog_name):
        if value and not _is_generic_asset_name(row, value):
            return str(value).strip()
    if row.key:
        return row.key
    if row.iid is not None:
        return _hex32(row.iid)
    return row_kind_text(row)


def _has_asset_prefix(row, value):
    text = str(value or "").strip().lower()
    prefixes = {
        row_kind_text(row).strip().lower(),
        row_kind_group_text(row).strip().lower(),
        str(row.catalog_category or "").strip().lower(),
    }
    prefixes = {prefix for prefix in prefixes if prefix}
    return any(text.startswith(prefix + ":") for prefix in prefixes)


def row_display_label(row):
    specific = row_specific_label(row)
    group = row_kind_group_text(row)
    if _has_asset_prefix(row, specific):
        return specific
    if group and specific and _normalised_asset_text(specific) != _normalised_asset_text(group):
        return "%s: %s" % (group, specific)
    return specific or group or row.key


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


def package_bucket_display_text(bucket):
    package = bucket["package"] or bucket["title"]
    file_name = bucket["file_name"]
    if file_name and file_name != package:
        return "%s\n%s" % (package, file_name)
    return package


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
    """Panel showing source files and catalog package suggestions."""

    def __init__(self, parent):
        wx.html.HtmlWindow.__init__(self, parent, -1, style=wx.html.HW_SCROLLBAR_AUTO | wx.BORDER_THEME)
        self._files = []
        self._files_seen = set()
        self._rows = []
        self._catalog_requested = False
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

    def Missing(self, v):
        self.bMissing = True

    def _package_item_html(self, bucket, esc):
        package = bucket["package"] or bucket["title"]
        url = bucket["url"]
        text = package_bucket_display_text(bucket)
        title = esc(package)
        if url:
            title = '<a href="%s">%s</a>' % (esc(url, quote=True), title)
        suffix = text[len(package):]
        return title + esc(suffix).replace("\n", "<br>")

    def Render(self, rows=None, catalog_requested=None):
        if rows is not None:
            self._rows = rows
        if catalog_requested is not None:
            self._catalog_requested = catalog_requested
        buckets = dependency_package_buckets(self._rows)
        packages = sorted(buckets.values(), key=lambda b: b["title"].lower())
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
        if not self._catalog_requested:
            out.append('<p><i>%s</i></p>' % esc(DepDlgPackageLookupNotRun))
        if packages:
            out.append('<p style="margin:0 0 4px 0"><b>%s</b></p>' % esc(DepDlgPublishPackagesHeading))
            out.append('<ul style="margin:0 0 8px 18px">')
            for bucket in packages:
                out.append('<li>%s</li>' % self._package_item_html(bucket, esc))
            out.append('</ul>')
        if self._catalog_requested and not self._files and not buckets and not self.bMissing:
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
        self._catalog_requested = False
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

        self.identifyButton = wx.Button(filter_panel, -1, DepDlgIdentifyPackages)
        set_button_icon(self.identifyButton, "packages")
        self.identifyButton.Bind(wx.EVT_BUTTON, self.OnIdentifyPackages)
        filter_sizer.Add(self.identifyButton, 0, wx.ALIGN_CENTER_VERTICAL)
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
            size=(960, 430),
        )
        self.COL_STATUS = 0
        self.COL_NAME = 1
        self.COL_SOURCE = 2
        self.COL_PACKAGE = 3
        for idx, (label, width) in enumerate((
            (DepDlgColStatus, 90),
            (DepDlgColDependency, 360),
            (DepDlgColLocalFile, 220),
            (DepDlgCatalogPackage, 240),
        )):
            self.list.InsertColumn(idx, label, width=width)
        self.list.SetMinSize((940, 360))
        self._status_images = wx.ImageList(16, 16, True)
        self._status_icon_indices = {
            "found": self._status_images.Add(icon_bitmap("circle-check", 16, "#006E00")),
            "missing": self._status_images.Add(icon_bitmap("alert-triangle", 16, "#AA0000")),
            "ignored": self._status_images.Add(icon_bitmap("info-circle", 16, "#787878")),
        }
        self.list.SetImageList(self._status_images, wx.IMAGE_LIST_SMALL)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnRowSelected)
        list_sizer.Add(self.list, 1, wx.EXPAND)
        list_panel.SetSizer(list_sizer)

        details_panel = wx.Panel(self.splitter, -1)
        details_sizer = wx.BoxSizer(wx.VERTICAL)
        self.lb = DependencyResourcePanel(details_panel)
        details_sizer.Add(self.lb, 1, wx.EXPAND)
        details_panel.SetSizer(details_sizer)

        self.splitter.SplitVertically(list_panel, details_panel, 980)
        self.splitter.SetMinimumPaneSize(320)
        try:
            self.splitter.SetSashGravity(0.75)
        except AttributeError:
            pass
        self.splitter.SetMinSize((1280, 430))
        try:
            self.splitter.SetSizerProps(expand=True, proportion=1)
        except AttributeError:
            pass

        self.BuildRows()
        self.RenderRows()
        self.lb.Render(self.rows, self._catalog_requested)

        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.Fit()
        self.SetMinSize((1320, 640))

    def AddFileName(self, fileName):
        self.lb.Append(fileName)

    def AddRow(self, status, kind, name, key, source, referenced_by, parent_id=None,
               tgi=None, iid=None, catalog_category=None, catalog_status="not_applicable",
               catalog_lookup=True):
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
            catalog_lookup=catalog_lookup,
        )
        self._next_row_id += 1
        self.rows.append(row)
        self.rows_by_id[row.id] = row
        return row

    def AddFoundRow(self, kind, name, key, file_name, referenced_by, parent_id=None, tgi=None,
                    catalog_lookup=True):
        source = os.path.split(file_name)[1] if file_name else ""
        row = self.AddRow("found", kind, name, key, source, referenced_by,
                          parent_id=parent_id, tgi=tgi, catalog_lookup=catalog_lookup)
        if file_name:
            self.lb.Append(file_name)
        return row

    def AddMissingRow(self, kind, name, key, referenced_by, parent_id=None,
                      tgi=None, iid=None, catalog_category=None, catalog_lookup=True):
        self.lb.Missing(DepDlgMissing)
        return self.AddRow(
            "missing", kind, name, key, DepDlgNotFound, referenced_by,
            parent_id=parent_id, tgi=tgi, iid=iid,
            catalog_category=catalog_category, catalog_lookup=catalog_lookup,
        )

    def AddIgnoredRow(self, kind, name, key, referenced_by, source="ignored", parent_id=None):
        return self.AddRow("ignored", kind, name, key, source, referenced_by,
                           parent_id=parent_id)

    def RowStatusText(self, row):
        return row_status_text(row)

    def RowSourceText(self, row):
        return row.source

    def RowCatalogText(self, row):
        return row_catalog_title(row) or row_catalog_state_text(row)

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

    def _SetCell(self, row_idx, col, text, font=None, colour=None, image=None):
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
        if image is not None:
            info.SetImage(image)
            info._mask |= ULC.ULC_MASK_IMAGE
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
                display_name = self.RowLabel(row)
                name = ("    " + display_name) if is_child else display_name
                self._SetCell(
                    idx, self.COL_STATUS, self.RowStatusText(row),
                    colour=self.RowStatusColour(row),
                    image=self._status_icon_indices.get(row.status),
                )
                self._SetCell(idx, self.COL_NAME, name)
                self._SetCell(idx, self.COL_SOURCE, self.RowSourceText(row), colour=self.RowStatusColour(row) if row.status != "found" else None)
                self._SetCell(idx, self.COL_PACKAGE, self.RowCatalogText(row), colour=self.RowCatalogColour(row))
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
        event.Skip()

    def OnIdentifyPackages(self, event):
        self._catalog_requested = True
        self._catalog_generation += 1
        for row in self.rows:
            row.catalog_matches = []
            row.catalog_name = ""
            row.catalog_match_reason = ""
            row.catalog_status = identification_catalog_status(
                row,
                self.catalog.enabled,
                self.catalog.base_url,
            )
        self.identifyButton.SetLabel(DepDlgIdentifyPackagesRunning)
        set_button_icon(self.identifyButton, "loader-2")
        self.identifyButton.Enable(False)
        self.ScheduleRender()
        if not self.StartCatalogLookups():
            self.identifyButton.SetLabel(DepDlgIdentifyPackages)
            set_button_icon(self.identifyButton, "packages")
            self.identifyButton.Enable(True)
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
        self.lb.Render(self.rows, self._catalog_requested)

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
            return False
        self._catalog_generation = generation
        worker = threading.Thread(
            target=run_catalog_lookups,
            args=(self._catalog_generation, jobs, dict(self.catalog_settings), self.ApplyCatalogBatch),
            name="dependency-catalog",
            daemon=True,
        )
        worker.start()
        return True

    def ApplyCatalogBatch(self, generation, results):
        if not self._alive or generation != self._catalog_generation:
            return
        changed = False
        for result in results:
            if self.ApplyCatalogResult(result):
                changed = True
        if changed:
            self.ScheduleRender()
        if not any(row.catalog_status == "pending" for row in self.rows):
            self.identifyButton.SetLabel(DepDlgIdentifyPackages)
            set_button_icon(self.identifyButton, "packages")
            self.identifyButton.Enable(True)

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
        model_catalog_lookup = kind != "Prop"

        for prop_id in (662775840, 662775841):
            rtk = desc.exemplar.GetProp(prop_id)
            if self.IsValidRTK(rtk):
                entry = self.virtualDAT.getEntry(rtk[0], rtk[1], rtk[2])
                if entry:
                    self.AddFoundRow("Model", "", self.TGIText(rtk), entry.fileName, referenced_by,
                                     parent_id=pid, tgi=rtk, catalog_lookup=model_catalog_lookup)
                else:
                    self.AddMissingRow("Model", "", self.TGIText(rtk), referenced_by,
                                       parent_id=pid, tgi=rtk, catalog_lookup=model_catalog_lookup)

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
                                     parent_id=pid, tgi=model_tgi, catalog_lookup=model_catalog_lookup)
                else:
                    self.AddMissingRow("Model", "", self.TGIText(model_tgi), referenced_by,
                                       parent_id=pid, tgi=model_tgi, catalog_lookup=model_catalog_lookup)

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
                if is_ignored_sound_iid(iid):
                    continue
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
            if UVNK is not None and not is_placeholder_ltext_key(UVNK):
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
            if IDK is not None and not is_placeholder_ltext_key(IDK):
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
