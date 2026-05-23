"""Main SC4PIM application with lot editor and data browser."""
import faulthandler
import functools
import logging
import os.path
import re
import sys
import threading
import time
from math import *

import wx.lib.agw.ultimatelistctrl as ULC
import wx.lib.mixins.listctrl as listmix

from .SC4DataFunctions import FinalizeCategory, readCategoryDef

try:
    import win32api
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
import wx.adv

from . import SC4IconMakerDlg, config, treeDnD
from .logsetup import configure_logging
from .ATCViewer import *
from .DependenciesDlg import *
from .paths import asset_path, ensure_user_data_dir, image_db_dir, image_db_path
from .SC4LotPreview import *
from .settings import *
from .textutil import decode_sc4_text, decode_unicode_escape, encode_sc4_text
from .translation import *
from .util import DictWrapper, basic_cmp, clamp_to_tile
from .version import get_version

logger = logging.getLogger(__name__)

offsetGID = [
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 15, 16, 17, 18, 19, 20, 35]
_preload_config_result = None
_faulthandler_file = None


def _env_true(name):
    return os.environ.get(name, '').strip().lower() in ('1', 'true', 'yes', 'on')


def _exit_after(stage):
    target = os.environ.get('SC4PIM_EXIT_AFTER', '').strip()
    if target and target == stage:
        logger.debug('exit after %s', stage)
        sys.exit(0)


def _read_s3d_bbox(mesh):
    """Return an S3D mesh bbox as (width, height, depth), or None if unreadable."""
    if mesh is None or getattr(mesh, 'entry', None) is None:
        return None
    mesh.ReadFile()
    return (mesh.bboxX, mesh.bboxY, mesh.bboxZ)


def _model_occupant_bbox(model):
    """Compute Occupant Size from the best available model mesh."""
    if model is None:
        return None
    candidates = []
    meshes = getattr(model, 's3dMeshes', None)
    if meshes:
        # Standard SC4 models use zoom 5 for the normal best-fit render path.
        if len(meshes) >= 5 and isinstance(meshes[4], list) and meshes[4]:
            candidates.append(meshes[4][0])
        elif len(meshes) >= 5 and not isinstance(meshes[4], list):
            candidates.append(meshes[4])
        for group in meshes:
            if isinstance(group, list):
                candidates.extend(group)
            else:
                candidates.append(group)
    main_mesh = getattr(model, 'mainMesh', None)
    if main_mesh is not None:
        candidates.append(main_mesh)

    seen = set()
    best = None
    best_volume = -1
    for mesh in candidates:
        entry = getattr(mesh, 'entry', None)
        key = getattr(entry, 'tgi', id(mesh))
        if key in seen:
            continue
        seen.add(key)
        try:
            bbox = _read_s3d_bbox(mesh)
        except Exception:
            logger.exception('Failed to read S3D bounds for %r', key)
            continue
        if bbox is None:
            continue
        volume = bbox[0] * bbox[1] * bbox[2]
        if volume > best_volume:
            best = bbox
            best_volume = volume
    return best


def _existing_unique_paths(paths):
    seen = set()
    result = []
    for path in paths:
        if not path or not os.path.isdir(path):
            continue
        normalised = os.path.normcase(os.path.normpath(path))
        if normalised in seen:
            continue
        seen.add(normalised)
        result.append(os.path.normpath(path))
    return result


def _common_sc4_install_folders():
    install_roots = []
    for env_name in ('ProgramFiles(x86)', 'ProgramFiles', 'ProgramW6432'):
        root = os.environ.get(env_name)
        if root:
            install_roots.append(root)

    relative_paths = [
        os.path.join('Maxis', 'SimCity 4'),
        os.path.join('Maxis', 'SimCity 4 Deluxe'),
        'SimCity 4 Deluxe Edition',
        'SimCity 4 Deluxe',
        os.path.join('Steam', 'steamapps', 'common', 'SimCity 4 Deluxe'),
        os.path.join('GOG Galaxy', 'Games', 'SimCity 4 Deluxe Edition'),
        os.path.join('GOG Galaxy', 'Games', 'SimCity 4 Deluxe'),
        os.path.join('GOG Games', 'SimCity 4 Deluxe Edition'),
        os.path.join('GOG Games', 'SimCity 4 Deluxe'),
    ]
    return _existing_unique_paths(os.path.join(root, rel) for root in install_roots for rel in relative_paths)


def _read_sc4_install_folder_from_registry():
    if not HAS_WIN32:
        return ''
    access_modes = [0]
    for flag_name in ('KEY_WOW64_32KEY', 'KEY_WOW64_64KEY'):
        flag = getattr(win32con, flag_name, None)
        if flag is not None:
            access_modes.append(win32con.KEY_READ | flag)

    for access in access_modes:
        try:
            key = win32api.RegOpenKeyEx(win32con.HKEY_LOCAL_MACHINE, 'SOFTWARE\\Maxis\\SimCity 4', 0, access)
            install_folder = str(win32api.RegQueryValueEx(key, 'Install Dir')[0])
            if install_folder and os.path.isdir(install_folder):
                return os.path.normpath(install_folder)
        except Exception:
            pass
    return ''


def _read_user_group_id_from_registry():
    if not HAS_WIN32:
        return None
    access_modes = [0]
    for flag_name in ('KEY_WOW64_32KEY', 'KEY_WOW64_64KEY'):
        flag = getattr(win32con, flag_name, None)
        if flag is not None:
            access_modes.append(win32con.KEY_READ | flag)

    for access in access_modes:
        try:
            key = win32api.RegOpenKeyEx(win32con.HKEY_LOCAL_MACHINE, 'SOFTWARE\\Maxis\\SimCity 4\\Tools', 0, access)
            return win32api.RegQueryValueEx(key, 'User Group ID')[0]
        except Exception:
            pass
    return None


def _enable_faulthandler():
    global _faulthandler_file
    if not _env_true('SC4PIM_FAULTHANDLER'):
        return
    try:
        _faulthandler_file = open(ensure_user_data_dir() / 'faulthandler.log', 'w')
    except OSError:
        _faulthandler_file = None
    if _faulthandler_file is not None:
        faulthandler.enable(file=_faulthandler_file, all_threads=True)
        faulthandler.dump_traceback_later(60, repeat=True, file=_faulthandler_file)
    else:
        faulthandler.enable(all_threads=True)
        faulthandler.dump_traceback_later(60, repeat=True)




class ProcessDlg(wx.Dialog):

    def __init__(self, parent, title='please wait'):
        wx.Dialog.__init__(self, parent, -1, splashTitle)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.label_g1 = wx.StaticText(self, -1, title, size=Size(500, -1),
                                      style=wx.ST_ELLIPSIZE_MIDDLE)
        sizer.Add(self.label_g1, 0, wx.EXPAND | wx.ALL, 5)
        self.label_detail = wx.StaticText(self, -1, '', size=Size(500, -1),
                                          style=wx.ST_ELLIPSIZE_MIDDLE)
        sizer.Add(self.label_detail, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
        self.g1 = wx.Gauge(self, -1, 32)
        # The following methods no longer exist in modern wxPython versions
        # self.g1.SetBezelFace(3)
        # self.g1.SetShadowWidth(3)
        sizer.Add(self.g1, 0, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(sizer)

        sizer.Fit(self)
        self.Bind(wx.EVT_CLOSE, self.OnCloseWindow)
        self.g1.SetRange(1000)
        self.value = 0
        # The gauge is animated by a main-thread timer so it stays smooth no
        # matter what the background loader thread is doing.
        self._pulse_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_pulse, self._pulse_timer)

    def StartPulse(self):
        """Begin the indeterminate gauge animation (main thread only)."""
        self._pulse_timer.Start(120)

    def StopPulse(self):
        if self._pulse_timer.IsRunning():
            self._pulse_timer.Stop()

    def _on_pulse(self, event):
        self.g1.Pulse()

    def Increment(self):
        # Called only from the GUI thread (Finalize / missing-picture loop).
        # A throttled yield keeps the dialog -- and its pulse timer -- alive
        # while those main-thread phases run.
        self.value += 1
        if self.value % 200 == 0:
            wx.Yield()

    def SetStatus(self, text, detail=''):
        """Update the visible progress text. Safe to call from any thread."""
        if not wx.IsMainThread():
            wx.CallAfter(self.SetStatus, text, detail)
            return
        self.label_g1.SetLabel(text)
        self.label_detail.SetLabel(detail)

    def LogError(self, what):
        pass

    @staticmethod
    def OnCloseWindow(event):
        event.Veto()


class MyTreeCtrl(wx.TreeCtrl):

    def __init__(self, virtual_dat, wx_parent, main_frame, style, size):
        wx.TreeCtrl.__init__(self, wx_parent, -1, style=style | wx.TR_EDIT_LABELS, size=size)
        self.parent = main_frame
        self.virtual_dat = virtual_dat
        self.root = self.AddRoot(treeRootMsg)
        self.resources_item = self.AppendItem(self.root, treeResourceMsg)
        self.standard_models_item = self.AppendItem(self.resources_item, treeStdModelMsg)
        self.SetItemData(self.standard_models_item, virtual_dat.standardModels)
        self.other_models_item = self.AppendItem(self.resources_item, treeOtherModelMsg)
        self.SetItemData(self.other_models_item, virtual_dat.otherModels)
        self.atcs_item = self.AppendItem(self.resources_item, treeAnimMsg)
        self.SetItemData(self.atcs_item, virtual_dat.atcs)
        self.descriptions_item = self.AppendItem(self.root, treeDescMsg)

        def CreateCat(cat, root):
            item = self.AppendItem(root, cat.Name)
            self.SetItemData(item, cat)
            cat.item = item
            for child in cat.childs:
                CreateCat(child, item)

        CreateCat(virtual_dat.rootCategory, self.descriptions_item)
        self.entry2Item = {}
        self.families = {}
        self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
        self.Bind(wx.EVT_TREE_BEGIN_LABEL_EDIT, self.OnBeginEdit)
        self.Bind(wx.EVT_TREE_END_LABEL_EDIT, self.OnEndEdit)

    # ------------------------------------------------------------------
    # Tree navigation helpers: descriptor counts, collapse/expand state
    # persistence and incremental category search.
    # ------------------------------------------------------------------

    def _walk(self, item=None):
        """Yield every tree item in pre-order (parents before children)."""
        if item is None:
            item = self.GetRootItem()
        yield item
        child, cookie = self.GetFirstChild(item)
        while child.IsOk():
            yield from self._walk(child)
            child = self.GetNextSibling(child)

    def _item_key(self, item):
        """A stable string identifier for a tree item, or None if unkeyable.

        Used to persist which categories the user left expanded.
        """
        for fixed, key in ((self.root, 'root'),
                            (self.resources_item, 'res'),
                            (self.standard_models_item, 'std'),
                            (self.other_models_item, 'oth'),
                            (self.atcs_item, 'atc'),
                            (self.descriptions_item, 'desc')):
            if item == fixed:
                return key
        data = self.GetItemData(item)
        if data is not None and hasattr(data, 'ID') and hasattr(data, 'descriptors'):
            return 'cat:%s' % (data.ID,)
        return None

    def RefreshCounts(self):
        """Append a ``(N)`` descriptor count to every category label."""
        self.Freeze()
        try:
            for item, base in ((self.standard_models_item, treeStdModelMsg),
                               (self.other_models_item, treeOtherModelMsg),
                               (self.atcs_item, treeAnimMsg)):
                data = self.GetItemData(item)
                count = len(data) if data is not None else 0
                self.SetItemText(item, '%s (%d)' % (base, count))
            for cat in self.virtual_dat.categories.values():
                cat_item = getattr(cat, 'item', None)
                if cat_item is None or not cat_item.IsOk():
                    continue
                count = len(cat.descriptors)
                if count:
                    self.SetItemText(cat_item, '%s (%d)' % (cat.Name, count))
                else:
                    self.SetItemText(cat_item, cat.Name)
        finally:
            self.Thaw()

    def GetExpandedKeys(self):
        """Identifiers of every currently expanded item, for persistence."""
        keys = []
        for item in self._walk():
            if self.ItemHasChildren(item) and self.IsExpanded(item):
                key = self._item_key(item)
                if key is not None:
                    keys.append(key)
        return keys

    def ApplyExpandedKeys(self, keys):
        """Restore a previously saved expansion state (collapse everything else)."""
        wanted = set(keys or [])
        if not wanted:
            return
        self.Freeze()
        try:
            self.CollapseAll()
            for item in self._walk():
                if self._item_key(item) in wanted:
                    self.Expand(item)
        finally:
            self.Thaw()

    def FindCategory(self, text, after_selection=False):
        """Select the next category whose label contains *text*.

        Returns True on a match. With ``after_selection`` the search starts
        just past the current selection and wraps around, so repeated calls
        cycle through every match.
        """
        needle = (text or '').strip().lower()
        if not needle:
            return False
        items = list(self._walk())
        start = 0
        if after_selection:
            current = self.GetSelection()
            for i, item in enumerate(items):
                if item == current:
                    start = i + 1
                    break
        order = items[start:] + items[:start]
        for item in order:
            if needle in self.GetItemText(item).lower():
                self.EnsureVisible(item)
                self.SelectItem(item)
                return True
        return False

    def OnBeginEdit(self, event):
        item = event.GetItem()
        data = self.GetItemData(item)
        if data is not None and data.__class__ == DictWrapper and data.parentID == 4089087265:
            pass
        else:
            event.Veto()
        return

    def OnEndEdit(self, event):
        if event.IsEditCancelled():
            return
        item = event.GetItem()
        data = self.GetItemData(item)
        file_name_base = 'Family ' + event.GetLabel()
        family = data.ID
        instance_id = family + 268435456 & 4294967295
        buffer = struct.pack('III', 87304289, 1740496652, instance_id)
        buffer += struct.pack('II', 0, 0)
        entry = SC4Entry(buffer, 0, os.path.join(self.parent.rootFolder,
                                                 '%s-0x%08x-0x%08x-0x%08x.SC4Desc' % (file_name_base, 87304289,
                                                                                      1740496652, instance_id)))
        entry.virtualDAT = self.virtual_dat
        props = []
        descs_in_family = self.virtual_dat.categories[family].descriptors
        type_prop = 30
        if descs_in_family:
            for desc in descs_in_family:
                type_prop = desc.exemplar.GetProp(16)[0]
                break

        props.append(CreateAPropFromString(self.virtual_dat.properties[16], '0x%08X' % type_prop))
        props.append(CreateAPropFromString(self.virtual_dat.properties[32], str(event.GetLabel())))
        props.append(CreateAPropFromString(self.virtual_dat.properties[662775920], '0x%08X' % family))

        def prop_sort(x, y):
            return (x[2:2 + 8] > y[2:2 + 8]) - (x[2:2 + 8] < y[2:2 + 8])

        props.sort(key=functools.cmp_to_key(prop_sort))
        buffer = 'CQZT1###\r\n' + 'ParentCohort=Key:{0x00000000,0x00000000,0x00000000}\r\n' + 'PropCount=0x%08x\r\n' % len(
            props)
        buffer += '\r\n'.join(props)
        entry.content = entry.rawContent = buffer
        exemplar = SC4Exemplar(entry, self.virtual_dat)
        exemplar.sig = 'CQZB1###'
        exemplar.entry = entry
        entry.exemplar = exemplar
        descriptor = BuildingDesc(entry)
        self.parent.FillPropList(descriptor, False)
        entry.exemplar.Maj()
        entries = [entry]
        WriteADat(entry.fileName, entries, None, True)
        self.virtual_dat.addEntries(entries, None, False, False)
        self.virtual_dat.cohorts.append(entry)
        self.virtual_dat.categories[family].descriptors.append(descriptor)
        self.Delete(item)
        self.virtual_dat.categories[data.parentID].childs.remove(data)
        data.parentID = 4089086497
        data.parent = self.virtual_dat.categories[data.parentID]
        data.parent.childs.append(data)
        data.Name = event.GetLabel() + ' - [0x%08X]' % family
        item = self.AppendItem(data.parent.item, data.Name)
        self.SetItemData(item, data)
        data.item = item
        self.EnsureVisible(item)
        self.SelectItem(item)
        return

    def OnRightDown(self, event):
        pt = event.GetPosition()
        item, flags = self.HitTest(pt)
        if item:
            self.SelectItem(item)
            data = self.GetItemData(item)
            if data is not None:
                if data.__class__ == DictWrapper:
                    if data.parentID == 4089087265:
                        self.EditLabel(item)
        return

    def Recategorize(self, desc, is_old=True, do_finalize=True):
        if is_old:
            for idCat, category in self.virtual_dat.categories.items():
                try:
                    category.descriptors.remove(desc)
                    continue
                except ValueError:
                    pass

        if not Categorize(self.virtual_dat.rootCategory, desc):
            if desc.exemplar.GetProp(16)[0] == 2:
                self.virtual_dat.categories[3540939231].descriptors.append(desc)
                desc.cats = [3540939231]
            if desc.exemplar.GetProp(16)[0] == 16:
                self.virtual_dat.categories[3379372343].descriptors.append(desc)
                desc.cats = [3379372343]
        prop_families = desc.exemplar.GetProp(662775920)
        if prop_families:
            for family in prop_families:
                if family not in self.virtual_dat.categories:
                    parent_family_cat_id = 4089087265
                    name = '0x%08X' % family
                    is_named_family = False
                    chosen_cohort = self.virtual_dat.getEntry(87304289, 1740496652, family + 268435456 & 4294967295)
                    if chosen_cohort is None:
                        potential_cohorts = []
                        potential_cohorts = self.virtual_dat.getEntries(87304289, 0, family + 268435456 & 4294967295,
                                                                        gMask=0)
                    else:
                        chosen_cohort.cats = [
                            4089082401]
                        potential_cohorts = [chosen_cohort]
                    for cohort in potential_cohorts:
                        if 'exemplar' not in cohort.__dict__:
                            pass
                        else:
                            name = cohort.exemplar.GetProp(32)
                            if name is not None:
                                name = name[0] + ' - [0x%08X]' % family
                                parent_family_cat_id = 4089086497
                                is_named_family = True
                                chosen_cohort = cohort
                                break

                    xml_str = '<?xml version="1.0" encoding="UTF-8"?><temp><CATEGORY Name="%s" ID="%s" ParentID="%s">' % (
                        name, hex2str(family), hex2str(parent_family_cat_id))
                    xml_str += '</CATEGORY></temp>'
                    try:
                        xml_doc = xml.dom.minidom.parseString(xml_str)
                    except Exception:
                        logger.warning('Problem with family %s 0x%08X', name, family)
                        return

                    for subNode in xml_doc.documentElement.childNodes:
                        if subNode.nodeType == subNode.ELEMENT_NODE and subNode.tagName == 'CATEGORY':
                            category = readCategoryDef(subNode)
                            if category.parentID != 0:
                                category.parent = self.virtual_dat.categories[category.parentID]
                                category.imgName = category.parent.imgName
                                category.imgIdx = category.parent.imgIdx
                                self.virtual_dat.categories[category.parentID].childs.append(category)
                            else:
                                self.virtual_dat.rootCategory = category
                            self.virtual_dat.categories[category.ID] = category
                            item = self.AppendItem(category.parent.item, category.Name)
                            self.SetItemData(item, category)
                            category.item = item

                    if chosen_cohort and is_named_family:
                        desc_cohort = BuildingDesc(chosen_cohort)
                        self.virtual_dat.categories[family].descriptors.append(desc_cohort)
                try:
                    self.virtual_dat.categories[family].descriptors.append(desc)
                except Exception:
                    logger.warning('Bizarre problem with family %s 0x%08X in %s',
                                   name, family, desc.exemplar.entry.fileName)

        if do_finalize:
            FinalizeCategory(self.virtual_dat.rootCategory)
            self.parent.RefreshItemsList()
            self.RefreshCounts()
        return

    def UpdateEntry(self, entry, virtual_dat, is_standard, dlg):
        if dlg:
            dlg.Increment()
        if entry.tgi[0] == 2058686020:
            if entry.tgi[1] == 159781726 and entry.tgi[2] & 15 in [3, 8, 13]:
                virtual_dat.allTextures.append(entry)
        if entry.tgi[0] == 1523640343 and entry.tgi[2] & 4095 == 0:
            model = SC4Model(entry.tgi[1], entry.tgi[2], virtual_dat)
            if model.is_valid:
                virtual_dat.standardModelsDict[entry.tgi] = model
                virtual_dat.standardModels.append(StandardModel(entry, model))
            elif entry.tgi[1] == 3134937073 and entry.tgi[2] == 235995136:
                what = SC4ModelMesh(entry.tgi[1], entry.tgi[2], virtual_dat)
                if not what.is_valid:
                    del model
                else:
                    virtual_dat.otherModels.append(StandardModel(entry, what))
                    virtual_dat.otherModelsDict[entry.tgi] = what
            else:
                del model
        if entry.tgi[0] == 698733036:
            atc = ATC(entry, virtual_dat)
            virtual_dat.atcsDict[entry.tgi] = atc
            virtual_dat.atcs.append(ATCProxy(entry, atc))
        if entry.tgi[0] == 87304289:
            if 'exemplar' not in entry.__dict__:
                entry.read_file(None, True, True)
                exemplar = SC4Exemplar(entry, virtual_dat)
                entry.exemplar = exemplar
                entry.rawContent = None
                entry.content = None
            else:
                entry.rawContent = None
                entry.content = None
                exemplar = entry.exemplar
        if not is_standard and entry.tgi[0] == 1697917002:
            if 'exemplar' not in entry.__dict__:
                entry.read_file(None, True, True)
                exemplar = SC4Exemplar(entry, virtual_dat)
                entry.exemplar = exemplar
                entry.rawContent = None
                entry.content = None
            else:
                entry.rawContent = None
                entry.content = None
                exemplar = entry.exemplar
            desc = None
            _0x10 = exemplar.GetProp(16)
            if _0x10 is not None and _0x10[0] == 33:
                desc = PropDesc(entry)
            if _0x10 is not None and _0x10[0] == 30:
                desc = PropDesc(entry)
            if _0x10 is not None and _0x10[0] == 2:
                desc = BuildingDesc(entry)
            if _0x10 is not None and _0x10[0] == 17:
                desc = FoundationDesc(entry)
            if _0x10 is not None and _0x10[0] == 15:
                desc = FloraDesc(entry)
            if _0x10 is not None and _0x10[0] == 16:
                desc = LotDesc(entry)
            if desc is not None:
                self.Recategorize(desc, False, False)
            else:
                del desc
                entry.exemplar.free()
                del entry.exemplar
                del exemplar
        return


class VirtualListCtrl(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin):

    def __init__(self, parent):
        wx.ListCtrl.__init__(self, parent, -1, style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.TAB_TRAVERSAL | wx.LC_SINGLE_SEL)
        listmix.ListCtrlAutoWidthMixin.__init__(self)
        self.SetItemCount(0)
        # all_datas is the full backing list; list_datas is the filtered view
        # that is actually displayed. They are the same object when no filter
        # is active. Row indices everywhere refer to list_datas.
        self.all_datas = []
        self.list_datas = []
        self.filter_text = ''
        self.on_filter_change = None
        # Active column layout; FillItemsList* sets the appropriate keys.
        self.columns = ['name', 'file']
        self.sort_col = -1
        self.sort_ascending = True
        self.attr1 = wx.ItemAttr()
        self.attr1.SetBackgroundColour((255, 228, 181))
        self.attr2 = wx.ItemAttr()
        self.attr2.SetBackgroundColour('light blue')
        # Lazily-loaded row thumbnails. thumb_provider maps a list_datas entry
        # to a JPG path (or None); thumb_index caches path -> image-list index.
        self.thumb_size = 32
        self.thumbs = None
        # A 1x1 image list used when thumbnails are off: wxMSW will not shrink
        # a list's row height back after SetImageList(None), but swapping in a
        # tiny image list does, so non-thumbnail views keep compact rows.
        self.thumbs_empty = None
        self.thumb_index = {}
        self.thumb_provider = None
        self.Bind(wx.EVT_LIST_COL_CLICK, self.OnListHeaderClick)
        return

    def SetThumbnailProvider(self, provider):
        """Show a small thumbnail per row.

        *provider* is a callable mapping a ``list_datas`` entry to a thumbnail
        JPG path, or None to disable thumbnails for the current layout. The
        image list is created on first use and the JPGs are decoded lazily by
        :meth:`OnGetItemImage` -- only rows actually scrolled into view pay the
        decode cost. When disabled the image list is detached so rows without
        thumbnails keep their normal (compact) height.
        """
        self.thumb_provider = provider
        if self.thumbs is None:
            self.thumbs = wx.ImageList(self.thumb_size, self.thumb_size, True)
        if self.thumbs_empty is None:
            self.thumbs_empty = wx.ImageList(1, 1, True)
        self.SetImageList(self.thumbs if provider is not None else self.thumbs_empty,
                          wx.IMAGE_LIST_SMALL)

    def _thumb_index(self, path):
        key = str(path)
        cached = self.thumb_index.get(key)
        if cached is not None:
            return cached
        idx = -1
        try:
            if os.path.exists(key):
                img = wx.Image(key, wx.BITMAP_TYPE_JPEG)
                if img.IsOk():
                    if img.GetWidth() != self.thumb_size or img.GetHeight() != self.thumb_size:
                        img = img.Scale(self.thumb_size, self.thumb_size, wx.IMAGE_QUALITY_HIGH)
                    added = self.thumbs.Add(img.ConvertToBitmap())
                    if added != -1:
                        idx = added
        except Exception:
            logger.exception('Failed to load list thumbnail %s', key)
            idx = -1
        self.thumb_index[key] = idx
        return idx

    def SetData(self, datas):
        """Replace the backing list and re-apply the current filter."""
        self.all_datas = datas if datas is not None else []
        self._refilter()

    def SetFilter(self, text):
        """Restrict the displayed rows to those matching *text* (name or ID)."""
        self.filter_text = (text or '').strip().lower()
        self._refilter()

    def _haystack(self, data):
        """Lower-cased searchable text for a row: its name and any IDs."""
        parts = []
        name = self._column_value(data, 'name')
        if name:
            parts.append(name)
        tgi = self._column_value(data, 'tgi')
        if tgi:
            parts.append(tgi)
        model = getattr(data, 'sc4Model', None)
        if model is not None:
            try:
                parts.append('%08X-%08X' % (model.GID, model.IID))
            except Exception:
                pass
        return ' '.join(parts).lower()

    def _refilter(self):
        if self.filter_text:
            needle = self.filter_text
            self.list_datas = [d for d in self.all_datas if needle in self._haystack(d)]
        else:
            self.list_datas = self.all_datas
        self.DeleteAllItems()
        self.SetItemCount(len(self.list_datas))
        if self.on_filter_change is not None:
            self.on_filter_change()

    def _column_value(self, data, key):
        try:
            if key == 'name':
                return data.name or ''
            if key == 'file':
                return data.fileName or ''
            if key == 'tgi':
                tgi = data.exemplar.entry.tgi
                return '%08X-%08X-%08X' % (tgi[0], tgi[1], tgi[2])
            if key == 'date':
                return time.ctime(data.exemplar.entry.dateUpdated)
        except Exception:
            return ''
        return ''

    def Refresh(self, **kwargs):
        if len(self.list_datas) != self.GetItemCount():
            self.SetItemCount(len(self.list_datas))
        wx.ListCtrl.Refresh(self)

    def OnGetItemText(self, item, col):
        if col >= len(self.columns) or item >= len(self.list_datas):
            return ''
        return self._column_value(self.list_datas[item], self.columns[col])

    def OnListHeaderClick(self, event):
        col = event.GetColumn()
        if not self.all_datas or col >= len(self.columns):
            return
        if self.sort_col == col:
            self.sort_ascending = not self.sort_ascending
        else:
            self.sort_col = col
            self.sort_ascending = True
        key = self.columns[col]

        def sort_key(data):
            if key == 'tgi':
                try:
                    return tuple(data.exemplar.entry.tgi)
                except Exception:
                    return ()
            if key == 'date':
                try:
                    return data.exemplar.entry.dateUpdated
                except Exception:
                    return 0
            return self._column_value(data, key).upper()

        try:
            self.all_datas.sort(key=sort_key, reverse=not self.sort_ascending)
        except Exception:
            logger.exception('Failed to sort resource list')
            return
        self._refilter()

    def OnGetItemImage(self, item):
        if self.thumb_provider is None or item >= len(self.list_datas):
            return -1
        try:
            path = self.thumb_provider(self.list_datas[item])
        except Exception:
            return -1
        if not path:
            return -1
        return self._thumb_index(path)

    def OnGetItemAttr(self, item):
        if item % 2 == 1:
            return self.attr1
        else:
            return self.attr2


class AutoWidthMixinList(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin):

    def __init__(self, parent, identifier, pos=wx.DefaultPosition, size=wx.DefaultSize, style=0):
        wx.ListCtrl.__init__(self, parent, identifier, pos, size, style)
        listmix.ListCtrlAutoWidthMixin.__init__(self)


class MixinList(wx.ListCtrl):

    def __init__(self, parent, identifier, pos=wx.DefaultPosition, size=wx.DefaultSize, style=0):
        wx.ListCtrl.__init__(self, parent, identifier, pos, size, style)


class PropListCtrl(ULC.UltimateListCtrl):
    """The exemplar property table.

    An owner-drawn UltimateListCtrl so individual cells can use their own font:
    the ID column and any hex-valued cell of the Value column are drawn in a
    monospace font so hex digits line up. ``ULC_SHOW_TOOLTIPS`` surfaces the
    full text of any cell too narrow to display it. The ``InsertItem``/
    ``SetItem`` overrides keep the wx.ListCtrl ``(index, col, label)`` calling
    convention so the rest of the code is unchanged.
    """

    def __init__(self, parent):
        ULC.UltimateListCtrl.__init__(
            self, parent, -1,
            agwStyle=ULC.ULC_REPORT | ULC.ULC_HRULES | ULC.ULC_SHOW_TOOLTIPS)
        self._mono = _monospace_font(self.GetFont())
        # The default selection highlight (the system accent blue) is rather
        # loud; blend it toward grey so a selected row reads as selected
        # without dominating the table.
        hl = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        soft = wx.Colour(*(round(c * 0.6 + 128 * 0.4)
                           for c in (hl.Red(), hl.Green(), hl.Blue())))
        self._mainWin._highlightBrush = wx.Brush(soft)
        self.Bind(wx.EVT_SIZE, self._on_size)

    def _apply_text(self, info, label):
        # ULC forbids multiline cell text without ULC_HAS_VARIABLE_ROW_HEIGHT;
        # collapse newlines for display and keep the full text as a tooltip.
        info._mask = ULC.ULC_MASK_TEXT
        label = label or ''
        if '\n' in label or '\r' in label:
            info._text = label.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
            info._tooltip = label
            info._mask |= ULC.ULC_MASK_TOOLTIP
        else:
            info._text = label

    def InsertItem(self, *args):
        # One arg: native UltimateListCtrl call. Two: wx-style (index, label).
        if len(args) == 1:
            return ULC.UltimateListCtrl.InsertItem(self, args[0])
        index, label = args
        info = ULC.UltimateListItem()
        info._itemId = index
        self._apply_text(info, label)
        self._mainWin.InsertItem(info)
        return index

    def SetItem(self, *args):
        # One arg: native UltimateListCtrl call. Three: wx-style cell setter.
        if len(args) == 1:
            return ULC.UltimateListCtrl.SetItem(self, args[0])
        index, col, label = args
        info = ULC.UltimateListItem()
        info._itemId = index
        info._col = col
        self._apply_text(info, label)
        if col == 1 or (col == 4 and _is_hex_value(info._text)):
            info.SetFont(self._mono)
            info._mask |= ULC.ULC_MASK_FONT
        self._mainWin.SetItem(info)
        return True

    def _on_size(self, event):
        event.Skip()
        wx.CallAfter(self.AutoFillLastColumn)

    def AutoFillLastColumn(self):
        """Stretch the last column to consume the remaining client width."""
        if not self:
            return
        count = self.GetColumnCount()
        if count < 2:
            return
        used = sum(self.GetColumnWidth(c) for c in range(count - 1))
        remaining = self.GetClientSize().width - used - 4
        if remaining > 60:
            self.SetColumnWidth(count - 1, remaining)


class EditDialog(sc.SizedDialog):

    def __init__(self, parent, title, txt):
        sc.SizedDialog.__init__(self, parent, -1, title)
        pane = self.GetContentsPane()
        pane.SetSizerType('vertical')
        wx.StaticText(pane, 1, editUnicodeWarning)
        self.editor = wx.TextCtrl(pane, -1, txt, style=wx.TE_MULTILINE, size=Size(400, 100))
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.Fit()
        self.SetMinSize(self.GetSize())

    def GetValue(self):
        return self.editor.GetValue()


# A property value made up solely of 0x.. hex tokens (a lone hex value, a
# comma-separated hex list, or a space-separated TGI triple).
_HEX_VALUE_RE = re.compile(r'^0x[0-9A-Fa-f]+(?:[\s,]+0x[0-9A-Fa-f]+)*$')


def _is_hex_value(text):
    return bool(_HEX_VALUE_RE.match(text.strip())) if text else False


def _monospace_font(base_font):
    """A monospace wx.Font for the property table.

    Consolas is preferred: it was hinted by Microsoft for crisp small-size
    rendering, which matters because UltimateListCtrl draws into a buffer and
    so only gets grayscale (not ClearType) antialiasing -- thinner faces like
    Cascadia Mono look mushy under it.
    """
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


class NoteBookPanel(wx.Panel):

    def __init__(self, parent, descriptor, virtual_dat):
        wx.Panel.__init__(self, parent)
        self.parent = parent
        self.descriptor = descriptor
        self.exemplar = descriptor.exemplar
        self.virtual_dat = virtual_dat
        self.RebuildViewer()
        self.bClose = wx.Button(self, -1, propertyPageClose)
        self.Bind(wx.EVT_BUTTON, self.parent.OnCloseTab, self.bClose)
        self.bSave = wx.Button(self, -1, propertyPageSave)
        self.bSave.Enable(False)
        self.Bind(wx.EVT_BUTTON, self.OnSaveTab, self.bSave)
        self.listProperties = PropListCtrl(self)
        self.listProperties.InsertColumn(0, propertyPageColumnName)
        self.listProperties.InsertColumn(1, propertyPageColumnNameValue)
        self.listProperties.InsertColumn(2, propertyPageColumnDataType)
        self.listProperties.InsertColumn(3, propertyPageColumnRep)
        self.listProperties.InsertColumn(4, propertyPageColumnValue)
        # Column widths live in the main window's session settings so a width
        # the user drags in one tab survives into later tabs and is persisted.
        mw = self.parent.parent._mw_settings
        self.listProperties.SetColumnWidth(0, int(mw['PropColName']))
        self.listProperties.SetColumnWidth(1, int(mw['PropColNameValue']))
        self.listProperties.SetColumnWidth(2, int(mw['PropColType']))
        self.listProperties.SetColumnWidth(3, int(mw['PropColRep']))
        self.Bind(wx.EVT_SET_FOCUS, self.parent.OnFocus, self.listProperties)
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnActivated, self.listProperties)
        self.listProperties.Bind(wx.EVT_LIST_COL_END_DRAG, self.OnPropColResize)
        self.listProperties.DeleteAllItems()
        self.FillTheList()
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(self.listProperties, 1, wx.ALL | wx.GROW, 0)
        horiz = wx.BoxSizer(wx.HORIZONTAL)
        horiz.Add(self.bSave, 0, wx.ALIGN_CENTRE | wx.ALL, 5)
        horiz.Add(self.bClose, 0, wx.ALIGN_CENTRE | wx.ALL, 5)
        box.Add(horiz, 0, wx.ALIGN_CENTRE | wx.ALL, 5)
        self.SetSizer(box)
        self.listProperties.Bind(wx.EVT_RIGHT_DOWN, self.OnRightClick)

    def OnPropColResize(self, event):
        """Capture a user column-drag and re-fill the stretch column."""
        event.Skip()
        wx.CallAfter(self._capture_prop_col_widths)

    def _capture_prop_col_widths(self):
        if self.listProperties.GetColumnCount() < 4:
            return
        self.listProperties.AutoFillLastColumn()
        mw = self.parent.parent._mw_settings
        mw['PropColName'] = int(self.listProperties.GetColumnWidth(0))
        mw['PropColNameValue'] = int(self.listProperties.GetColumnWidth(1))
        mw['PropColType'] = int(self.listProperties.GetColumnWidth(2))
        mw['PropColRep'] = int(self.listProperties.GetColumnWidth(3))

    def RebuildViewer(self):
        rkt0 = self.exemplar.GetProp(662775840)
        rkt1 = self.exemplar.GetProp(662775841)
        rkt3 = self.exemplar.GetProp(662775843)
        rkt4 = self.exemplar.GetProp(662775844)
        rkt5 = self.exemplar.GetProp(662775845)
        view = None
        if rkt0:
            view = ResourceViewer(662775840, rkt0, self.virtual_dat, self.parent.parent, self.exemplar.entry.tgi)
        elif rkt1:
            view = ResourceViewer(662775841, rkt1, self.virtual_dat, self.parent.parent, self.exemplar.entry.tgi)
        elif rkt3:
            view = ResourceViewer(662775843, rkt3, self.virtual_dat, self.parent.parent, self.exemplar.entry.tgi)
        elif rkt4:
            view = ResourceViewer(662775844, rkt4, self.virtual_dat, self.parent.parent, self.exemplar.entry.tgi)
        elif rkt5:
            view = ResourceViewer(662775845, rkt5, self.virtual_dat, self.parent.parent, self.exemplar.entry.tgi)
        self.view = view
        return

    def UndoInCaseModified(self):
        instance_id = self.exemplar.entry.tgi[2]
        tex_entry = VirtualDat.this.getEntry(2238569388, 1782082854, instance_id)
        if tex_entry is not None:
            tex_entry.content = tex_entry.rawContent = None
        if self.exemplar.modified:
            self.exemplar.Reread()
            self.descriptor.name = self.exemplar.GetProp(32)[0]
            self.parent.parent.tree.Recategorize(self.descriptor)
            self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
            self.parent.parent.listItems.Refresh()
            self.listProperties.DeleteAllItems()
            self.FillTheList()
            item = self.parent.parent.tree.GetSelection()
            try:
                data = self.parent.parent.tree.GetItemData(item)
            except Exception:
                data = None

            if data:
                if data.__class__.__name__ == 'list':
                    self.parent.parent.FillItemsListModel(data)
                elif data.__class__.__name__ == 'DictWrapper':
                    self.parent.parent.FillItemsList(data)
        return

    def OnClose(self):
        self.UndoInCaseModified()

    def Change(self, descriptor):
        self.UndoInCaseModified()
        self.listProperties.DeleteAllItems()
        self.descriptor = descriptor
        self.exemplar = descriptor.exemplar
        self.FillTheList()

    def FillTheList(self):
        # Build the rows frozen: the owner-drawn list otherwise repaints on
        # every insert, which is visibly slow for large exemplars.
        self.listProperties.Freeze()
        try:
            self._fill_the_list()
        finally:
            self.listProperties.Thaw()
            self.listProperties.AutoFillLastColumn()

    def _fill_the_list(self):
        idx = self.listProperties.InsertItem(self.listProperties.GetItemCount(), propertyPageFilename)
        self.listProperties.SetItemBackgroundColour(idx, wx.Colour(205, 190, 112))
        self.listProperties.SetItem(idx, 4, '%s' % self.exemplar.entry.fileName)
        idx = self.listProperties.InsertItem(self.listProperties.GetItemCount(), 'TGI')
        self.listProperties.SetItemBackgroundColour(idx, wx.Colour(205, 190, 112))
        self.listProperties.SetItem(idx, 4, '0x%08X 0x%08X 0x%08X' % (self.exemplar.entry.tgi[0],
                                                                            self.exemplar.entry.tgi[1],
                                                                            self.exemplar.entry.tgi[2]))
        idx = self.listProperties.InsertItem(self.listProperties.GetItemCount(), propertyPageParentCohort)
        self.listProperties.SetItemBackgroundColour(idx, wx.Colour(205, 190, 112))
        self.listProperties.SetItem(idx, 4, '0x%08X 0x%08X 0x%08X' % (self.exemplar.parentCohort[0],
                                                                            self.exemplar.parentCohort[1],
                                                                            self.exemplar.parentCohort[2]))
        for prop in self.exemplar.props:
            try:
                name = self.virtual_dat.properties[prop.id].Name
                formatted = ConvertAPropToReadable(prop, self.virtual_dat.properties[prop.id])
            except KeyError:
                name = '0x%08X' % prop.id
                formatted = prop.ToStr()

            idx = self.listProperties.InsertItem(self.listProperties.GetItemCount(), name)
            self.listProperties.SetItem(idx, 1, '0x%08X' % prop.id)
            self.listProperties.SetItem(idx, 2, '%s' % Prop.format2String[prop.typeValue])
            self.listProperties.SetItem(idx, 3, '%d' % len(prop.values))
            self.listProperties.SetItem(idx, 4, '%s' % formatted)
            if prop.id == 138265735:
                if prop.values != [0.0] * 256:
                    self.listProperties.SetItemBackgroundColour(idx, wx.Colour(200, 99, 71))
            if prop.id == 709468037:
                if self.virtual_dat.getEntry(0, 2527069872, prop.values[0]) is None:
                    self.listProperties.SetItemBackgroundColour(idx, wx.Colour(200, 99, 71))
            if prop.id == 2317746872:
                if self.virtual_dat.getEntry(2238569388, 1782082854, prop.values[0]) is None:
                    self.listProperties.SetItemBackgroundColour(idx, wx.Colour(200, 99, 71))
            if prop.id == 3928360329:
                if self.virtual_dat.getEntry(1697917002, 2835075954, prop.values[0]) is None:
                    self.listProperties.SetItemBackgroundColour(idx, wx.Colour(200, 99, 71))

        def FamilyFill(cohort):
            if cohort is not None:
                idx = self.listProperties.InsertItem(self.listProperties.GetItemCount(), propertyPageFamily)
                formatted = '0x%08X 0x%08X 0x%08X' % (cohort.tgi[0], cohort.tgi[1], cohort.tgi[2])
                self.listProperties.SetItem(idx, 4, '%s' % formatted)
                self.listProperties.SetItemBackgroundColour(idx, wx.Colour(160, 190, 220))
                for prop in cohort.exemplar.props:
                    try:
                        name = self.virtual_dat.properties[prop.id].Name
                        formatted = ConvertAPropToReadable(prop, self.virtual_dat.properties[prop.id])
                    except KeyError:
                        name = '0x%08X' % prop.id
                        formatted = prop.ToStr()

                    idx = self.listProperties.InsertItem(self.listProperties.GetItemCount(), name)
                    self.listProperties.SetItem(idx, 1, '0x%08X' % prop.id)
                    self.listProperties.SetItem(idx, 2, '%s' % Prop.format2String[prop.typeValue])
                    self.listProperties.SetItem(idx, 3, '%d' % len(prop.values))
                    self.listProperties.SetItem(idx, 4, '%s' % formatted)
                    self.listProperties.SetItemBackgroundColour(idx, wx.Colour(213, 239, 255))

                RecurseFill(cohort.exemplar.link)
            return

        def RecurseFill(link):
            if link is not None:
                idx = self.listProperties.InsertItem(self.listProperties.GetItemCount(), propertyPageInherited)
                formatted = '0x%08X 0x%08X 0x%08X' % (link.tgi[0], link.tgi[1], link.tgi[2])
                self.listProperties.SetItem(idx, 4, '%s' % formatted)
                self.listProperties.SetItemBackgroundColour(idx, wx.Colour(190, 190, 190))
                for prop in link.exemplar.props:
                    try:
                        name = self.virtual_dat.properties[prop.id].Name
                        formatted = ConvertAPropToReadable(prop, self.virtual_dat.properties[prop.id])
                    except KeyError:
                        name = '0x%08X' % prop.id
                        formatted = prop.ToStr()

                    idx = self.listProperties.InsertItem(self.listProperties.GetItemCount(), name)
                    self.listProperties.SetItem(idx, 1, '0x%08X' % prop.id)
                    self.listProperties.SetItem(idx, 2, '%s' % Prop.format2String[prop.typeValue])
                    self.listProperties.SetItem(idx, 3, '%d' % len(prop.values))
                    self.listProperties.SetItem(idx, 4, '%s' % formatted)
                    self.listProperties.SetItemBackgroundColour(idx, wx.Colour(255, 239, 213))

                RecurseFill(link.exemplar.link)
            return

        RecurseFill(self.exemplar.link)
        UVNK = self.exemplar.GetProp(2319542937)
        IDK = self.exemplar.GetProp(3393284789)
        if UVNK or IDK:
            idx = self.listProperties.InsertItem(self.listProperties.GetItemCount(), propertyPageLTEXT)
            self.listProperties.SetItemBackgroundColour(idx, wx.Colour(113, 255, 139))
            if UVNK:
                try:
                    uvnks = [self.virtual_dat.getEntry(UVNK[0], UVNK[1] + i, UVNK[2]) for i in offsetGID]
                except Exception:
                    uvnks = []

                for i, uvnk in enumerate(uvnks):
                    if uvnk:
                        uvnk.read_file(None, True, True)
                        try:
                            txt = decode_sc4_text(uvnk.content[4:])
                        except UnicodeDecodeError:
                            txt = uvnk.content.decode('utf-8', errors='replace')

                        idx = self.listProperties.InsertItem(self.listProperties.GetItemCount(),
                                                                   self.virtual_dat.properties[2319542937].Name)
                        self.listProperties.SetItem(idx, 4, txt)
                        self.listProperties.SetItem(idx, 1, '0x%08X' % uvnk.tgi[1])
                        self.listProperties.SetItem(idx, 2, namedLang[i])
                        self.listProperties.SetItemData(idx, 805306368 + offsetGID[i])
                        self.listProperties.SetItemBackgroundColour(idx, wx.Colour(213, 255, 239))

            if IDK and IDK != UVNK:
                try:
                    idks = [self.virtual_dat.getEntry(IDK[0], IDK[1] + i, IDK[2]) for i in offsetGID]
                except Exception:
                    idks = []

                for i, idk in enumerate(idks):
                    if idk:
                        idk.read_file(None, True, True)
                        try:
                            txt = decode_sc4_text(idk.content[4:])
                        except UnicodeDecodeError:
                            txt = idk.content.decode('utf-8', errors='replace')

                        idx = self.listProperties.InsertItem(self.listProperties.GetItemCount(),
                                                                   self.virtual_dat.properties[3393284789].Name)
                        self.listProperties.SetItem(idx, 4, txt)
                        self.listProperties.SetItem(idx, 1, '0x%08X' % idk.tgi[1])
                        self.listProperties.SetItem(idx, 2, namedLang[i])
                        self.listProperties.SetItemData(idx, 1073741824 + offsetGID[i])
                        self.listProperties.SetItemBackgroundColour(idx, wx.Colour(213, 255, 239))

        propFamilies = self.exemplar.GetProp(662775920)
        if propFamilies:
            for family in propFamilies:
                choosenCohort = self.virtual_dat.getEntry(87304289, 1740496652, family + 268435456 & 4294967295)
                if choosenCohort is None:
                    potentialCohorts = self.virtual_dat.getEntries(87304289, 0, family + 268435456 & 4294967295, gMask=0)
                else:
                    potentialCohorts = [
                        choosenCohort]
                for cohort in potentialCohorts:
                    if cohort:
                        FamilyFill(cohort)
                        break

        self.RebuildViewer()
        if self.view:
            zoom = self.parent.parent.cbZoom.GetClientData(self.parent.parent.cbZoom.GetSelection())
            rot = self.parent.parent.cbRotation.GetClientData(self.parent.parent.cbRotation.GetSelection())
            try:
                state = self.parent.parent.cbStateChoice.GetClientData(self.parent.parent.cbStateChoice.GetSelection())
            except Exception:
                state = 0

            if zoom == -1:
                nZoom = 0
            else:
                nZoom = zoom
            self.view.draw(self.parent.parent.viewer, self.parent.parent.staticFileName, zoom, rot, state)
            self.parent.parent.currentModel = self.view
        else:
            self.parent.parent.currentModel = None
            self.parent.parent.staticFileName.SetLabel(unknownRK)
        return

    def OnEditLTEXT(self, ltext_entry):
        ltext_entry.read_file(None, True, True)
        try:
            txt = decode_sc4_text(ltext_entry.content[4:])
        except UnicodeDecodeError:
            txt = ltext_entry.content.decode('utf-8', errors='replace')

        dlg = EditDialog(self, editUnicodeTitle, txt)
        if dlg.ShowModal() == wx.ID_OK:
            unicode_text = dlg.GetValue()
            new_val = encode_sc4_text(unicode_text)
            buffer = struct.pack('H', len(unicode_text))
            buffer += struct.pack('H', 4096)
            buffer += new_val
            ltext_entry.content = ltext_entry.rawContent = buffer
            ltext_entry.Maj()
            self.InternalSave(ltext_entry.fileName)
            dlg.Destroy()
            return True
        dlg.Destroy()
        return False

    def OnAddToFamily(self, event):
        title = 'Add to family'
        value = ''
        msg = 'Enter the family ID you want this building/prop to be part of\n\nPlease make sure you get your own family range\nTo get your own range go to \n   http://www.sc4devotion.com\n   http://www.simtropolis.com'
        dlg = wx.TextEntryDialog(self, msg, title, value)
        if dlg.ShowModal() == wx.ID_OK:
            newValue = dlg.GetValue()
            try:
                newPropStr = CreateAPropFromString(self.virtual_dat.properties[662775920], newValue)
                if not self.exemplar.AddTextProp(newPropStr):
                    dlg.Destroy()
                    return
            except Exception:
                dlg.Destroy()
                raise

            self.listProperties.DeleteAllItems()
            self.bSave.Enable(True)
            self.descriptor.name = self.exemplar.GetProp(32)[0]
            self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
            self.parent.parent.listItems.Refresh()
            self.parent.parent.tree.Recategorize(self.descriptor)
            self.FillTheList()
        dlg.Destroy()

    def ChangeCohort(self):
        if bAdvancedUser:
            lst = [
                [
                    resetParentCohortMsg, None]]

            def CohortName(c):
                try:
                    return c.exemplar.GetProp(32)[0]
                except Exception:
                    return hex2str(c.tgi[0]) + '-' + hex2str(c.tgi[1]) + '-' + hex2str(c.tgi[2])

            lst2 = [[CohortName(c), c] for c in self.virtual_dat.cohorts]

            lst2.sort(functools.cmp_to_key(basic_cmp))
            lst = lst + lst2
            dlg = wx.SingleChoiceDialog(self, chooseParentCohortMsg, appTitle, [l[0] for l in lst])
            if dlg.ShowModal() == wx.ID_OK:
                if dlg.GetSelection() == 0:
                    self.exemplar.parentCohort = (0, 0, 0)
                else:
                    self.exemplar.parentCohort = lst[dlg.GetSelection()][1].tgi
                self.exemplar.LinkToParent()
                self.exemplar.modified = True
                self.bSave.Enable(True)
                self.parent.parent.tree.Recategorize(self.descriptor)
                self.listProperties.DeleteAllItems()
                self.FillTheList()
            dlg.Destroy()
        else:
            self.exemplar.parentCohort = (0, 0, 0)
            self.exemplar.LinkToParent()
            self.exemplar.modified = True
            self.bSave.Enable(True)
            self.parent.parent.tree.Recategorize(self.descriptor)
            self.listProperties.DeleteAllItems()
            self.FillTheList()
        return

    def OnActivated(self, event):
        allowedPropEdit = [
            32, 662775824, 2308635565, 2317746857, 2317746872, 1246398704, 1771767972, 2297284498, 3919251084,
            2297284501, 2297284502, 662775920, 662775825]
        listItems = event.GetEventObject()
        idx = event.GetIndex()
        if idx < 3:
            if idx == 2:
                self.ChangeCohort()
            return
        if idx - 3 >= len(self.exemplar.props):
            if listItems.GetItemData(idx) & 805306368 == 805306368:
                offset = listItems.GetItemData(idx) & 255
                UVNK = self.exemplar.GetProp(2319542937)
                uvnk = self.virtual_dat.getEntry(UVNK[0], UVNK[1] + offset, UVNK[2])
                if self.OnEditLTEXT(uvnk):
                    self.listProperties.DeleteAllItems()
                    self.FillTheList()
            elif listItems.GetItemData(idx) & 1073741824 == 1073741824:
                offset = listItems.GetItemData(idx) & 255
                IDK = self.exemplar.GetProp(3393284789)
                idk = self.virtual_dat.getEntry(IDK[0], IDK[1] + offset, IDK[2])
                if self.OnEditLTEXT(idk):
                    self.listProperties.DeleteAllItems()
                    self.FillTheList()
            return
        title = self.exemplar.GetProp(32)[0]
        prop = self.exemplar.props[idx - 3]
        if not bAdvancedUser:
            if prop.id not in allowedPropEdit:
                return
        if prop.id == 662775825:
            self.OnRebuildProperties(1)
            return
        try:
            name = self.virtual_dat.properties[prop.id].Name
        except KeyError:
            name = '0x%08X' % prop.id

        value = prop.ToStr()
        msg = valuePropertyMsg % name
        dlg = wx.TextEntryDialog(self, msg, title, value)
        if dlg.ShowModal() == wx.ID_OK:
            newValue = dlg.GetValue()
            newPropStr = CreateAPropFromString(self.virtual_dat.properties[prop.id], newValue)
            try:
                newProp = Prop(newPropStr, False, self.exemplar)
            except Exception:
                dlg.Destroy()
                raise
                return

            self.exemplar.props[idx - 3] = newProp
            self.exemplar.modified = True
            try:
                name = self.virtual_dat.properties[newProp.id].Name
                formatted = ConvertAPropToReadable(newProp, self.virtual_dat.properties[newProp.id])
            except KeyError:
                name = '0x%08X' % newProp.id
                formatted = newProp.ToStr()

            listItems.SetItem(idx, 0, name)
            listItems.SetItem(idx, 1, '0x%08X' % newProp.id)
            listItems.SetItem(idx, 2, '%s' % Prop.format2String[newProp.typeValue])
            listItems.SetItem(idx, 3, '%d' % len(newProp.values))
            listItems.SetItem(idx, 4, '%s' % formatted)
            self.bSave.Enable(True)
            self.descriptor.name = self.exemplar.GetProp(32)[0]
            self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
            self.parent.parent.listItems.Refresh()
            self.listProperties.DeleteAllItems()
            self.FillTheList()
            item = self.parent.parent.tree.GetSelection()
            try:
                data = self.parent.parent.tree.GetItemData(item)
            except Exception:
                data = None

            if data:
                if data.__class__.__name__ == 'list':
                    self.parent.parent.FillItemsListModel(data)
                elif data.__class__.__name__ == 'DictWrapper':
                    self.parent.parent.FillItemsList(data)
        dlg.Destroy()
        return

    def InternalSave(self, fileName):
        preventFilename = ['simcity_%d.dat' % x for x in range(1, 6)]
        preventFilename += ['ep1.dat', 'sounds.dat', 'intro.dat', 'loteditor.dat']
        preventFilename = [x.upper() for x in preventFilename]
        if os.path.split(fileName)[1].upper() in preventFilename:
            dlg = wx.MessageDialog(self, legacyFileErrorMsg % fileName, legacyFileErrorTitle,
                                   wx.OK | wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
            return
        entries = self.virtual_dat.GetAllEntriesFromFile(fileName)
        nbrOfLots = 0
        lotName = ''
        lotID = 0
        b2Remove = False
        oldFileName = fileName
        for entry in entries:
            entry.read_file(None, True, False)
            if entry.tgi[0] == 1697917002 and entry.tgi[1] == 2835075954:
                nbrOfLots += 1
                lotName = entry.exemplar.GetProp(32)[0]
                lotID = entry.tgi[2]

        if os.path.splitext(fileName)[1] == '.SC4Lot' and nbrOfLots == 1:
            b2Remove = True
            oldFileName = fileName
            fileName = os.path.join(os.path.split(fileName)[0], lotName + '_%08x.SC4Lot' % lotID)
            if oldFileName == fileName:
                b2Remove = False
            for entry in entries:
                entry.fileName = fileName

        WriteADat(fileName, entries, None, False)
        if b2Remove:
            os.remove(oldFileName)
        return

    def OnSaveTab(self, event):
        filename = self.exemplar.entry.fileName
        preventFilename = ['simcity_%d.dat' % x for x in range(1, 6)]
        preventFilename += ['ep1.dat', 'sounds.dat', 'intro.dat', 'loteditor.dat']
        preventFilename = [x.upper() for x in preventFilename]
        if os.path.split(filename)[1].upper() in preventFilename:
            dlg = wx.MessageDialog(self, legacyFileErrorMsg % filename, legacyFileErrorTitle,
                                   wx.OK | wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
            return
        self.exemplar.Maj()
        self.InternalSave(self.exemplar.entry.fileName)
        self.bSave.Enable(False)
        IID = self.exemplar.entry.tgi[2]
        texEntry = self.virtual_dat.getEntry(2238569388, 1782082854, IID)
        if texEntry is not None:
            texEntry.content = texEntry.rawContent = None
        self.descriptor.name = self.exemplar.GetProp(32)[0]
        self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
        self.parent.parent.listItems.Refresh()
        self.listProperties.DeleteAllItems()
        self.FillTheList()
        item = self.parent.parent.tree.GetSelection()
        try:
            data = self.parent.parent.tree.GetItemData(item)
        except Exception:
            data = None

        if data:
            if data.__class__.__name__ == 'list':
                self.parent.parent.FillItemsListModel(data)
            elif data.__class__.__name__ == 'DictWrapper':
                self.parent.parent.FillItemsList(data)
        return

    def OnCloseTab(self, event):
        self.UndoInCaseModified()
        self.parent.OnCloseTab(event)

    def OnRightClick(self, event):
        if not hasattr(self, 'popupID1'):
            self.popupID16 = wx.NewIdRef()
            self.popupID14 = wx.NewIdRef()
            self.popupID15 = wx.NewIdRef()
            self.popupID17 = wx.NewIdRef()
            self.popupID18 = wx.NewIdRef()
            self.popupID19 = wx.NewIdRef()
            self.popupID20 = wx.NewIdRef()
            self.popupID21 = wx.NewIdRef()
            self.popupID22 = wx.NewIdRef()
            self.popupID23 = wx.NewIdRef()
            self.popupID24 = wx.NewIdRef()
            self.popupID25 = wx.NewIdRef()
            self.popupID26 = wx.NewIdRef()
            self.popupID27 = wx.NewIdRef()
            self.popupID28 = wx.NewIdRef()
            self.popupID29 = wx.NewIdRef()
            self.popupID30 = wx.NewIdRef()
            self.popupID31 = wx.NewIdRef()
            self.popupID32 = wx.NewIdRef()
            self.popupID33 = wx.NewIdRef()
            self.popupID34 = wx.NewIdRef()
            self.popupID35 = wx.NewIdRef()
            self.popupID36 = wx.NewIdRef()
            self.popupID37 = wx.NewIdRef()
            self.popupID1 = wx.NewIdRef()
            self.popupID2 = wx.NewIdRef()
            self.popupID3 = wx.NewIdRef()
            self.popupID4 = wx.NewIdRef()
            self.popupID5 = wx.NewIdRef()
            self.popupID6 = wx.NewIdRef()
            self.popupID7 = wx.NewIdRef()
            self.popupID8 = wx.NewIdRef()
            self.popupID9 = wx.NewIdRef()
            self.popupID10 = wx.NewIdRef()
            self.popupID11 = wx.NewIdRef()
            self.popupID12 = wx.NewIdRef()
            self.familyMenuIDs = []
            self.AddLangUVNK_IDs = [wx.NewIdRef() for i in offsetGID]
            for idP in self.AddLangUVNK_IDs:
                self.Bind(wx.EVT_MENU, self.OnAddLangUVNK, id=idP)

            self.AddLangIDK_IDs = [wx.NewIdRef() for i in offsetGID]
            for idP in self.AddLangIDK_IDs:
                self.Bind(wx.EVT_MENU, self.OnAddLangIDK, id=idP)

            self.Bind(wx.EVT_MENU, self.OnCopy, id=self.popupID1)
            self.Bind(wx.EVT_MENU, self.OnPaste, id=self.popupID2)
            self.Bind(wx.EVT_MENU, self.OnDelete, id=self.popupID3)
            self.Bind(wx.EVT_MENU, self.OnAddProperty, id=self.popupID4)
            self.Bind(wx.EVT_MENU, self.OnAddItemName, id=self.popupID5)
            self.Bind(wx.EVT_MENU, self.OnConvertToUVNK, id=self.popupID6)
            self.Bind(wx.EVT_MENU, self.OnAddDescription, id=self.popupID8)
            self.Bind(wx.EVT_MENU, self.OnConvertToIDK, id=self.popupID9)
            self.Bind(wx.EVT_MENU, self.OnRebuildProperties, id=self.popupID14)
            self.Bind(wx.EVT_MENU, self.OnRebuildOccupantSize, id=self.popupID16)
            self.Bind(wx.EVT_MENU, self.OnOpenLotWithBuilding, id=self.popupID17)
            self.Bind(wx.EVT_MENU, self.OnBuildingsFromLot, id=self.popupID18)
            self.Bind(wx.EVT_MENU, self.OnLotInfoDebug, id=self.popupID19)
            self.Bind(wx.EVT_MENU, self.OnAddToFamily, id=self.popupID25)
            self.Bind(wx.EVT_MENU, self.OnConvertToRKT0, id=self.popupID20)
            self.Bind(wx.EVT_MENU, self.OnConvertToRKT1, id=self.popupID21)
            self.Bind(wx.EVT_MENU, self.OnConvertToRKT4, id=self.popupID24)
            self.Bind(wx.EVT_MENU, self.OnConvertReward, id=self.popupID26)
            self.Bind(wx.EVT_MENU, self.OnDependenciesListing, id=self.popupID27)
            self.Bind(wx.EVT_MENU, self.OnCreateLot, id=self.popupID28)
            self.Bind(wx.EVT_MENU, self.OnCreatePlopLot, id=self.popupID29)
            self.Bind(wx.EVT_MENU, self.OnPlop2Grow, id=self.popupID30)
            self.Bind(wx.EVT_MENU, self.OnRecomputeStage, id=self.popupID31)
            self.Bind(wx.EVT_MENU, self.OnRemoveUVNK, id=self.popupID32)
            self.Bind(wx.EVT_MENU, self.OnRemoveUVNKTrans, id=self.popupID33)
            self.Bind(wx.EVT_MENU, self.OnTileset, id=self.popupID34)
            self.Bind(wx.EVT_MENU, self.OnCamStage, id=self.popupID37)
            self.Bind(wx.EVT_MENU, self.OnChangeIcon, id=self.popupID35)
            self.Bind(wx.EVT_MENU, self.OnOpenLotWithProp, id=self.popupID36)
        menu = wx.Menu()
        if bAdvancedUser:
            menu.Append(self.popupID1, popupPropertyMenuItem1)
            menu.Append(self.popupID2, popupPropertyMenuItem2)
            menu.Append(self.popupID3, popupPropertyMenuItem3)
            menu.Append(self.popupID4, popupPropertyMenuItem4)
        else:
            if self.SelectedPropForNonAdvanced():
                menu.Append(self.popupID1, popupPropertyMenuItem1)
            if len(self.parent.clipboard) > 0:
                menu.Append(self.popupID2, popupPropertyMenuItem2)
            if self.SelectedPropForNonAdvanced():
                menu.Append(self.popupID3, popupPropertyMenuItem3)
        bSep = False
        if IsFromCategory(self.virtual_dat.categories[2895100787], self.exemplar) and self.exemplar.GetProp(
                2319542937) is None:
            if not bSep:
                bSep = True
                menu.AppendSeparator()
            menu.Append(self.popupID6, popupPropertyMenuItem6)
        if IsFromCategory(self.virtual_dat.categories[210746660], self.exemplar) and self.exemplar.GetProp(
                2319542937) is None:
            if not bSep:
                bSep = True
                menu.AppendSeparator()
            menu.Append(self.popupID6, popupPropertyMenuItem6)
        if self.exemplar.GetProp(16)[0] == 30:
            bUVNK = True
            if self.exemplar.GetProp(2319542937) is None:
                bUVNK = False
            if self.exemplar.GetProp(2319542937) == [0, 0, 0]:
                bUVNK = False
            if self.exemplar.GetProp(2308635565) is None and not bUVNK:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID5, popupPropertyMenuItem5)
            if not bUVNK:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID6, popupPropertyMenuItem6)
        if self.exemplar.GetProp(2319542937) is not None:
            UVNK = self.exemplar.GetProp(2319542937)
            if UVNK[0] == 539399691:
                uvnks = [self.virtual_dat.getEntry(UVNK[0], UVNK[1] + i, UVNK[2]) for i in offsetGID]
                submenu = wx.Menu()
                bAddSub = False
                for i, uvnk in enumerate(uvnks):
                    if uvnk is None:
                        submenu.Append(self.AddLangUVNK_IDs[i], namedLang[i])
                        bAddSub = True

                if bAddSub:
                    if not bSep:
                        bSep = True
                        menu.AppendSeparator()
                    menu.Append(self.popupID7, popupPropertyMenuItem7, submenu)
        if IsFromCategory(self.virtual_dat.categories[3431971885], self.exemplar) and self.exemplar.GetProp(
                3928360329) and self.exemplar.GetProp(3928360329)[0] != 0:
            if self.exemplar.GetProp(2308635565) is None and self.exemplar.GetProp(2319542937) is None:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID5, popupPropertyMenuItem5)
            if self.exemplar.GetProp(2308635565) is not None and self.exemplar.GetProp(2319542937) is None:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID6, popupPropertyMenuItem6)
            if self.exemplar.GetProp(2317746857) is None and self.exemplar.GetProp(3393284789) is None:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID8, popupPropertyMenuItem8)
            if self.exemplar.GetProp(2317746857) is not None and self.exemplar.GetProp(3393284789) is None:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID9, popupPropertyMenuItem9)
            if self.exemplar.GetProp(3393284789) is not None:
                IDK = self.exemplar.GetProp(3393284789)
                if IDK[0] == 539399691:
                    idks = [self.virtual_dat.getEntry(IDK[0], IDK[1] + i, IDK[2]) for i in offsetGID]
                    submenu = wx.Menu()
                    bAddSub = False
                    for i, idk in enumerate(idks):
                        if idk is None:
                            submenu.Append(self.AddLangIDK_IDs[i], namedLang[i])
                            bAddSub = True

                    if bAddSub:
                        if not bSep:
                            bSep = True
                            menu.AppendSeparator()
                        menu.Append(self.popupID10, popupPropertyMenuItem10, submenu)
        if bAdvancedUser:
            if IsFromCategory(self.virtual_dat.categories[3431971885], self.exemplar):
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID26, popupPropertyMenuItem26)
            else:
                bSep = False
                propFamilies = self.exemplar.GetProp(662775920)
                if propFamilies:
                    if not bSep:
                        bSep = True
                        menu.AppendSeparator()
                    submenu = wx.Menu()
                    self.familyMenuIDs = [wx.NewIdRef() for _ in propFamilies]
                    for i, family in enumerate(propFamilies):
                        submenu.Append(self.familyMenuIDs[i], '0x%08X' % family)
                        self.Bind(wx.EVT_MENU, self.OnOpenFamily, id=self.familyMenuIDs[i])

                    menu.Append(self.popupID12, popupPropertyMenuItem12, submenu)
                if self.exemplar.GetProp(16)[0] == 2 or self.exemplar.GetProp(16)[0] == 30:
                    if self.exemplar.GetProp(662775920) is None:
                        if not bSep:
                            bSep = True
                            menu.AppendSeparator()
                        menu.Append(self.popupID25, popupPropertyMenuItem25)
        if self.exemplar.GetProp(16)[0] == 30:
            if not bSep:
                bSep = True
                menu.AppendSeparator()
            menu.Append(self.popupID36, popupPropertyMenuItem36)
        if self.exemplar.GetProp(16)[0] == 2:
            if not bSep:
                bSep = True
                menu.AppendSeparator()
            menu.Append(self.popupID17, popupPropertyMenuItem17)
            if IsFromCategory(self.virtual_dat.categories[749358634], self.exemplar) and self.exemplar.entry.tgi[
                0] == 1697917002:
                menu.Append(self.popupID28, popupPropertyMenuItem28)
            if IsFromCategory(self.virtual_dat.categories[2895100787], self.exemplar) and self.exemplar.entry.tgi[
                0] == 1697917002:
                menu.Append(self.popupID28, popupPropertyMenuItem28)
            if IsFromCategory(self.virtual_dat.categories[3431971885], self.exemplar) and self.exemplar.entry.tgi[
                0] == 1697917002:
                menu.Append(self.popupID29, popupPropertyMenuItem29)
        if IsFromCategory(self.virtual_dat.categories[2895100787], self.exemplar):
            if not IsFromCategoryDesc(self.virtual_dat.categories[749358634], self.descriptor):
                if not IsFromCategoryDesc(self.virtual_dat.categories[2358230027], self.descriptor):
                    if not bSep:
                        bSep = True
                        menu.AppendSeparator()
                    menu.Append(self.popupID34, popupPropertyMenuItem34)
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID37, 'CAM Stage')
        bSep = False
        if self.exemplar.GetProp(662775824) is not None:
            if not bSep:
                bSep = True
                menu.AppendSeparator()
            menu.Append(self.popupID16, popupPropertyMenuItem16)
        bCategorized, includedCats = GetCategories(self.virtual_dat.rootCategory, self.descriptor)
        if bCategorized and len(includedCats) > 0:
            if not bSep:
                bSep = True
                menu.AppendSeparator()
            menu.Append(self.popupID14, popupPropertyMenuItem14 % includedCats[0][0])
        bSep = False
        if self.exemplar.GetProp(16)[0] != 16:
            if self.exemplar.GetProp(662775840) is None and self.exemplar.GetProp(662775843) is None:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID20, popupPropertyMenuItem20)
            if self.exemplar.GetProp(662775841) is None and self.exemplar.GetProp(662775843) is None:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID21, popupPropertyMenuItem21)
            if self.exemplar.GetProp(662775844) is None and self.exemplar.GetProp(662775843) is None:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID24, popupPropertyMenuItem24)
        bSep = False
        if self.exemplar.GetProp(16)[0] == 16:
            if not bSep:
                bSep = True
                menu.AppendSeparator()
            menu.Append(self.popupID18, popupPropertyMenuItem18)
            menu.Append(self.popupID19, popupPropertyMenuItem19)
            menu.Append(self.popupID27, popupPropertyMenuItem27)
            bSep = False
            desc = self.virtual_dat.FindBuildingFromLot(self.exemplar)
            if desc:
                if desc.exemplar.entry.tgi[0] == 1697917002:
                    if desc in self.virtual_dat.categories[3431971885].descriptors:
                        if not bSep:
                            bSep = True
                            menu.AppendSeparator()
                        menu.Append(self.popupID30, popupPropertyMenuItem30)
                        menu.Append(self.popupID35, popupPropertyMenuItem35)
                    if desc in self.virtual_dat.categories[3540939231].descriptors:
                        if not bSep:
                            bSep = True
                            menu.AppendSeparator()
                        menu.Append(self.popupID30, popupPropertyMenuItem30)
                    if desc in self.virtual_dat.categories[2895100787].descriptors:
                        if not bSep:
                            bSep = True
                            menu.AppendSeparator()
                        menu.Append(self.popupID31, popupPropertyMenuItem31)
        self.PopupMenu(menu)
        menu.Destroy()
        return

    def OnChangeIcon(self, event):
        IID = self.exemplar.entry.tgi[2]
        texEntry = VirtualDat.this.getEntry(2238569388, 1782082854, IID)
        img = None
        if texEntry is not None:
            try:
                if texEntry.content is None:
                    texEntry.read_file(None, True, True)
            except Exception:
                texEntry.read_file(None, True, True)

            cIO = io.BytesIO(texEntry.content)
            try:
                img = Image.open(cIO).convert('RGB')
            except Exception:
                pass

            cIO.close()
        dlg = SC4IconMakerDlg.IconDlg(self, img)
        if dlg.ShowModal() == wx.ID_OK:
            if dlg.image is not None:
                iconImage = dlg.image
                cIO = io.BytesIO()
                iconImage.save(cIO, 'PNG')
                strIcon = cIO.getvalue()
                IID = self.exemplar.entry.tgi[2]
                buffer = struct.pack('III', 2238569388, 1782082854, IID)
                buffer += struct.pack('II', 0, len(strIcon))
                iconEntry = SC4Entry(buffer, 0, self.exemplar.entry.fileName)
                iconEntry.content = iconEntry.rawContent = strIcon[:]
                self.virtual_dat.addEntries([iconEntry], None, False, False)
                cIO.close()
                self.bSave.Enable(True)
        dlg.Destroy()
        return

    def OnTileset(self, event):
        lst = [
            'Chicago', 'New york', 'Houston', 'Euro']
        ogs = [8192, 8193, 8194, 8195]
        dlg = wx.MultiChoiceDialog(self, tilesetSelectorMsg, appTitle, lst)
        currentOgs = self.exemplar.GetProp(2854081430)
        selected = []
        for i, o in enumerate(ogs):
            if o in currentOgs:
                selected.append(i)

        dlg.SetSelections(selected)
        if dlg.ShowModal() == wx.ID_OK:
            nonTilesetOGs = [x for x in currentOgs if x not in ogs]
            selections = dlg.GetSelections()
            tileset = [ogs[x] for x in selections]
            finalOgs = nonTilesetOGs + tileset
            finalOgs.sort()
            prop = CreateAProp(self.virtual_dat.properties[2854081430], tuple(finalOgs))
            self.exemplar.AddTextProp(prop)
            self.listProperties.DeleteAllItems()
            self.FillTheList()
            self.bSave.Enable(True)
            self.descriptor.name = self.exemplar.GetProp(32)[0]
            self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
            self.parent.parent.listItems.Refresh()
        dlg.Destroy()

    def OnCamStage(self, event):
        lots = self.virtual_dat.FindAllLotsFromBuilding(self.exemplar)
        if IsFromCategory(self.virtual_dat.categories[747617173], self.exemplar):
            needed = 3049261992
            lowStage = 9
        if IsFromCategory(self.virtual_dat.categories[1821359013], self.exemplar):
            needed = 3049262000
            lowStage = 9
        if IsFromCategory(self.virtual_dat.categories[210746286], self.exemplar):
            needed = 3049262008
            lowStage = 9
        if IsFromCategory(self.virtual_dat.categories[2358229964], self.exemplar):
            needed = 3049261736
            lowStage = 9
        if IsFromCategory(self.virtual_dat.categories[210746332], self.exemplar):
            needed = 3049261744
            lowStage = 9
        if IsFromCategory(self.virtual_dat.categories[2895100907], self.exemplar):
            needed = 3049261752
            lowStage = 9
        if IsFromCategory(self.virtual_dat.categories[1821359093], self.exemplar):
            needed = 3049261760
            lowStage = 9
        if IsFromCategory(self.virtual_dat.categories[3431971841], self.exemplar):
            needed = 3049261768
            lowStage = 9
        if IsFromCategory(self.virtual_dat.categories[749358378], self.exemplar):
            needed = 3049262112
            lowStage = 1
        if IsFromCategory(self.virtual_dat.categories[747617303], self.exemplar):
            needed = 3049262760
            lowStage = 4
        if IsFromCategory(self.virtual_dat.categories[1820235835], self.exemplar):
            needed = 3049262768
            lowStage = 4
        if IsFromCategory(self.virtual_dat.categories[1821359580], self.exemplar):
            needed = 3049262776
            lowStage = 4
        stage_count = 10 if needed == 3049262112 else 7
        ogs = range(needed + 1, needed + stage_count + 1)
        options = self.virtual_dat.properties[2854081430].Options
        lst = [options.get(x, hex2str(x)) for x in ogs]
        missing_options = [hex2str(x) for x in ogs if x not in options]
        if missing_options:
            logger.debug('Missing occupant group option labels for CAM stage dialog: %s',
                         ', '.join(missing_options))
        dlg = wx.MultiChoiceDialog(self, camStageSelectorMsg, appTitle, lst)
        currentOgs = self.exemplar.GetProp(2854081430)
        selected = []
        for i, o in enumerate(ogs):
            if o in currentOgs:
                selected.append(i)

        for lot in lots:
            stage = lot.exemplar.GetProp(662775863)[0]
            if stage >= lowStage:
                stage -= lowStage
                if stage not in selected:
                    selected.append(stage)

        dlg.SetSelections(selected)
        if dlg.ShowModal() == wx.ID_OK:
            nonTilesetOGs = [x for x in currentOgs if x not in ogs]
            selections = dlg.GetSelections()
            tileset = [ogs[x] for x in selections]
            if needed != 3049262112:
                tileset.append(needed)
            finalOgs = nonTilesetOGs + tileset
            finalOgs.sort()
            prop = CreateAProp(self.virtual_dat.properties[2854081430], tuple(finalOgs))
            self.exemplar.AddTextProp(prop)
            self.listProperties.DeleteAllItems()
            self.FillTheList()
            self.bSave.Enable(True)
            self.descriptor.name = self.exemplar.GetProp(32)[0]
            self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
            self.parent.parent.listItems.Refresh()
        dlg.Destroy()

    def OnRemoveUVNK(self, event):
        pass

    def OnRemoveUVNKTrans(self, event):
        pass

    def OnRecomputeStage(self, event):
        descBuilding = self.virtual_dat.FindBuildingFromLot(self.exemplar)
        dlg = LotCreatorDlg(self, descBuilding.exemplar, self.virtual_dat, True, True, self.exemplar.GetProp(2297284496))
        if dlg.ShowModal() == wx.ID_OK:
            stage = int(dlg.stageCtrl.GetValue())
            newProp = CreateAProp(self.virtual_dat.properties[662775863], (stage,))
            self.exemplar.AddTextProp(newProp)
            purposes = {1: 'R', 2: 'CS', 3: 'CO', 7: 'IM', 6: 'ID', 8: 'IHT', 5: 'IR'}
            purpose = self.exemplar.GetProp(2297284502)[0]
            zoning = self.virtual_dat.ComputeZoning(purposes[purpose], descBuilding.exemplar.GetProp(662775824)[1])
            newProp = CreateAProp(self.virtual_dat.properties[2297284499], tuple(zoning))
            self.exemplar.AddTextProp(newProp)
            self.listProperties.DeleteAllItems()
            self.FillTheList()
            self.bSave.Enable(True)
            self.descriptor.name = self.exemplar.GetProp(32)[0]
            self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
            self.parent.parent.listItems.Refresh()

    def OnPlop2Grow(self, event):
        lst = [
            'R$', 'R$$', 'R$$$', 'CS$', 'CS$$', 'CS$$$', 'CO$$', 'CO$$$', 'IA', 'ID Anchor', 'ID Mech', 'ID Out',
            'IM Anchor', 'IM Mech', 'IM Out', 'IHT Anchor', 'IHT Mech', 'IHT Out']
        name2Cat = {'R$': 747617173, 'R$$': 1821359013, 'R$$$': 210746286, 'CS$': 2358229964, 'CS$$': 210746332,
                    'CS$$$': 2895100907, 'CO$$': 1821359093, 'CO$$$': 3431971841, 'IA': 749358378,
                    'ID Anchor': 747617304, 'ID Mech': 747617305, 'ID Out': 747617306, 'IM Anchor': 1820235836,
                    'IM Mech': 1820235837, 'IM Out': 1820235838, 'IHT Anchor': 1821359581, 'IHT Mech': 1821359582,
                    'IHT Out': 1821359583}
        dlg1 = wx.SingleChoiceDialog(self, plopLotCategoryMsg,
                                     plopLotCategoryTitle, lst, wx.CHOICEDLG_STYLE)
        if dlg1.ShowModal() == wx.ID_OK:
            selected = dlg1.GetStringSelection()
            cat = name2Cat[selected]
            oldBuildingDesc = self.virtual_dat.FindBuildingFromLot(self.exemplar)
            rkt0 = oldBuildingDesc.exemplar.GetProp(662775840)
            rkt1 = oldBuildingDesc.exemplar.GetProp(662775841)
            rkt = rkt0
            if rkt is None:
                rkt = rkt1
            newBuildingDesc = self.parent.parent.CreateAnExamplar(oldBuildingDesc.exemplar.GetProp(32)[0] + '_GROW',
                                                                  rkt, oldBuildingDesc.exemplar.GetProp(662775824),
                                                                  self.virtual_dat.categories[cat],
                                                                  oldBuildingDesc.exemplar.GetProp(662775825))
            lotDimensions = self.exemplar.GetProp(2297284496)
            width = lotDimensions[0]
            depth = lotDimensions[1]
            stage, purpose, wealth = ComputeStagePurposeWealth(newBuildingDesc.exemplar.GetProp(662775860),
                                                               newBuildingDesc.exemplar.GetProp(2854081430),
                                                               lotDimensions[0], lotDimensions[1])
            IID = newBuildingDesc.exemplar.entry.tgi[2]
            fileNameBase = '%s%s%s_%sx%s_%s' % (purpose, '$' * (wealth + 1), stage, width, depth,
                                                newBuildingDesc.exemplar.GetProp(32)[0])
            buffer = struct.pack('III', 1697917002, 2835075954, IID)
            buffer += struct.pack('II', 0, 0)
            entry = SC4Entry(buffer, 0,
                             os.path.join(self.parent.parent.rootFolder, '%s_%08x.SC4Lot' % (fileNameBase, IID)))
            props = []
            purposes = {'R': 1, 'CS': 2, 'CO': 3, 'IM': 7, 'ID': 6, 'IHT': 8, 'IR': 5}

            def CopyPropOrDefault(propID, defaultValue):
                if self.exemplar.GetProp(propID) is None:
                    return defaultValue
                return self.exemplar.GetProp(propID)

            props.append(CreateAProp(self.virtual_dat.properties[16], (16,)))
            props.append(CreateAPropFromString(self.virtual_dat.properties[32], str(fileNameBase)))
            props.append(CreateAProp(self.virtual_dat.properties[662775863], (int(stage),)))
            props.append(CreateAProp(self.virtual_dat.properties[1246398704], CopyPropOrDefault(1246398704, (8,))))
            props.append(CreateAProp(self.virtual_dat.properties[2297284489], (2,)))
            props.append(CreateAProp(self.virtual_dat.properties[2297284496], (int(width), int(depth))))
            zoning = self.virtual_dat.ComputeZoning(purpose, newBuildingDesc.exemplar.GetProp(662775824)[1])
            props.append(CreateAProp(self.virtual_dat.properties[2297284499], tuple(zoning)))
            props.append(CreateAProp(self.virtual_dat.properties[2297284501], (wealth + 1,)))
            props.append(CreateAProp(self.virtual_dat.properties[2297284502], (purposes[purpose],)))
            props.append(CreateAProp(self.virtual_dat.properties[3420603383], (1,)))
            props.append(CreateAProp(self.virtual_dat.properties[1771767972], CopyPropOrDefault(1771767972, (0.0,))))
            props.append(CreateAProp(self.virtual_dat.properties[2297284498], CopyPropOrDefault(2297284498, (90.0,))))
            props.append(
                CreateAProp(self.virtual_dat.properties[2297284504], CopyPropOrDefault(2297284504, (3379372341,))))
            props.append(
                CreateAProp(self.virtual_dat.properties[2298271863], CopyPropOrDefault(2298271863, (2299228948,))))
            props.append(CreateAProp(self.virtual_dat.properties[3919251084], CopyPropOrDefault(3919251084, (90.0,))))
            for lcp in range(2297284864, 2297286143):
                z = self.exemplar.GetProp(lcp)
                if z is None:
                    break
                v = z[:]
                if v[0] == 0:
                    v[12] = IID
                if v[0] == 7:
                    continue
                props.append(CreateAProp(self.virtual_dat.properties[lcp], v))

            props.sort(key=functools.cmp_to_key(lambda x, y: basic_cmp(x[2:2 + 8], y[2:2 + 8])))
            buffer = 'EQZT1###\r\n' + 'ParentCohort=Key:{0x00000000,0x00000000,0x00000000}\r\n' + 'PropCount=0x%08x\r\n' % len(
                props)
            buffer += '\r\n'.join(props)
            entry.content = entry.rawContent = buffer
            exemplar = SC4Exemplar(entry, self.virtual_dat)
            exemplar.entry = entry
            entry.exemplar = exemplar
            lotDescriptor = LotDesc(entry)
            entries = [entry]
            entry.exemplar.Maj()
            WriteADat(entry.fileName, entries, None, True)
            self.virtual_dat.addEntries(entries, None, False, False)
            self.parent.parent.tree.Recategorize(lotDescriptor, False)
            self.parent.AddNewDesc(lotDescriptor, self.virtual_dat, False)
            frame = LotEditorWin(self, -1, 'LotPreview ' + lotDescriptor.name, size=(800,
                                                                                     800))
            frame.Display(entry.exemplar, self.virtual_dat)
            frame.Show()
            frame.Destroy()
        dlg1.Destroy()
        return

    def OnUpdateIcon(self, image):
        iconImage = SC4IconMakerDlg.compose_lot_icon(image)
        cIO = io.BytesIO()
        iconImage.save(cIO, 'PNG')
        strIcon = cIO.getvalue()
        IID = self.exemplar.entry.tgi[2]
        buffer = struct.pack('III', 2238569388, 1782082854, IID)
        buffer += struct.pack('II', 0, len(strIcon))
        iconEntry = SC4Entry(buffer, 0, self.exemplar.entry.fileName)
        iconEntry.content = iconEntry.rawContent = strIcon[:]
        self.virtual_dat.addEntries([iconEntry], None, False, False)
        cIO.close()
        return iconImage

    def OnCreatePlopLot(self, event):
        dlg = LotCreatorDlg(self, self.exemplar, self.virtual_dat, False)
        if dlg.ShowModal() == wx.ID_OK:
            init = datetime.datetime(2005, 5, 5, 21, 24, 15)
            today = datetime.datetime.today()
            dt = today - init
            dt = dt.days * 24 * 3600 + dt.seconds
            first = random.randrange(0, 15)
            IID = first * 268435456 + (dt & 268435455)
            fileNameBase = 'PLOP_%sx%s_%s' % (dlg.widthCtrl.GetValue(), dlg.depthCtrl.GetValue(),
                                              self.exemplar.GetProp(32)[0])
            buffer = struct.pack('III', 1697917002, 2835075954, IID)
            buffer += struct.pack('II', 0, 0)
            entry = SC4Entry(buffer, 0,
                             os.path.join(self.parent.parent.rootFolder, '%s_%08x.SC4Lot' % (fileNameBase, IID)))
            props = []
            props.append(CreateAProp(self.virtual_dat.properties[16], (16,)))
            props.append(CreateAPropFromString(self.virtual_dat.properties[32], str(fileNameBase)))
            if IsFromCategory(self.virtual_dat.categories[3434232095], self.exemplar):
                bFound = False
                for stage in range(1, 16):
                    if IsFromCategory(self.virtual_dat.categories[3434232096 + stage], self.exemplar):
                        props.append(CreateAProp(self.virtual_dat.properties[662775863], (stage,)))
                        bFound = True
                        break

                bFound or props.append(CreateAProp(self.virtual_dat.properties[662775863], (255,)))
        if IsFromCategory(self.virtual_dat.categories[210746672], self.exemplar):
            bFound = False
            for stage in range(1, 16):
                if IsFromCategory(self.virtual_dat.categories[210746672 + stage], self.exemplar):
                    props.append(CreateAProp(self.virtual_dat.properties[662775863], (stage,)))
                    bFound = True
                    break

            if not bFound:
                props.append(CreateAProp(self.virtual_dat.properties[662775863], (255,)))
        else:
            if IsFromCategory(self.virtual_dat.categories[210746652], self.exemplar):
                stages = {210746657: 1, 210746658: 2, 210746659: 3, 210746695: 1, 210746697: 2, 210746700: 3}
                bFound = False
                for catID, stage in stages.items():
                    if IsFromCategory(self.virtual_dat.categories[catID], self.exemplar):
                        props.append(CreateAProp(self.virtual_dat.properties[662775863], (stage,)))
                        bFound = True
                        break

                if not bFound:
                    props.append(CreateAProp(self.virtual_dat.properties[662775863], (255,)))
            else:
                props.append(CreateAProp(self.virtual_dat.properties[662775863], (255,)))
            props.append(CreateAProp(self.virtual_dat.properties[1246398704], (8,)))
            props.append(CreateAProp(self.virtual_dat.properties[2297284489], (2,)))
            props.append(CreateAProp(self.virtual_dat.properties[2297284496],
                                     (int(dlg.widthCtrl.GetValue()), int(dlg.depthCtrl.GetValue()))))
            if IsFromCategory(self.virtual_dat.categories[210746652], self.exemplar):
                props.append(CreateAProp(self.virtual_dat.properties[2297284499], (11,)))
            else:
                if IsFromCategory(self.virtual_dat.categories[3434232095], self.exemplar):
                    props.append(CreateAProp(self.virtual_dat.properties[2297284499], (12,)))
                else:
                    props.append(CreateAProp(self.virtual_dat.properties[2297284499], (15,)))
                props.append(CreateAProp(self.virtual_dat.properties[2297284501], (0,)))
                props.append(CreateAProp(self.virtual_dat.properties[2297284502], (0,)))
                props.append(CreateAProp(self.virtual_dat.properties[3420603383], (1,)))
                currentID = 2297284864
                objID = dt & 16777215
                lotwidth = int(dlg.widthCtrl.GetValue())
                lotdepth = int(dlg.depthCtrl.GetValue())
                buildwidth = (self.exemplar.GetProp(662775824)[0] + 0.3) / 16.0
                builddepth = (self.exemplar.GetProp(662775824)[2] + 0.3) / 16.0
                posX = lotwidth / 2.0
                posY = lotdepth / 2.0
                xmin = posX - buildwidth / 2.0
                ymin = posY - builddepth / 2.0
                xmax = posX + buildwidth / 2.0
                ymax = posY + builddepth / 2.0
                posX = int(posX * 1048576)
                posY = int(posY * 1048576)
                xmin = int(xmin * 1048576)
                ymin = int(ymin * 1048576)
                xmax = int(xmax * 1048576)
                ymax = int(ymax * 1048576)
                families = self.exemplar.GetProp(662775920)
                buildingID = IID
                if families is not None:
                    lst = [
                              lotBuildingChoiceSelf] + ['Family %s' % hex2str(f) for f in families]
                    dlg1 = wx.SingleChoiceDialog(self, lotBuildingChoiceMsg,
                                                 lotCreationTitle, lst, wx.CHOICEDLG_STYLE)
                    if dlg1.ShowModal() == wx.ID_OK:
                        selected = dlg1.GetStringSelection()
                        if selected != lotBuildingChoiceSelf:
                            buildingID = int(selected[7:], 16)
                        dlg1.Destroy()
                    else:
                        return
                v = [
                    0, 0, 2, posX, 0, posY, xmin, ymin, xmax, ymax, 0, objID, buildingID]
                props.append(CreateAProp(self.virtual_dat.properties[currentID], v))
                currentID += 1
                objID += 1
                baseTex = self.virtual_dat.baseTex[('None', 0)]
                for h in range(0, lotdepth):
                    for w in range(0, lotwidth):
                        v = [
                            2, 0, 0, w * 1048576 + 524288, 0, h * 1048576 + 524288, w * 1048576, h * 1048576,
                                     (w + 1) * 1048576, (h + 1) * 1048576, 0, objID, baseTex]
                        props.append(CreateAProp(self.virtual_dat.properties[currentID], v))
                        currentID += 1
                        objID += 1

                LotSizeX = lotwidth
                LotSizeY = lotdepth
                Width = self.exemplar.GetProp(662775824)[0]
                Depth = self.exemplar.GetProp(662775824)[2]
                Height = self.exemplar.GetProp(662775824)[1]
                MaxSlopeBeforeLotFoundation = eval(self.virtual_dat.MaxSlopeBeforeLotFoundation)
                MaxSlopeAllowed = eval(self.virtual_dat.MaxSlopeAllowed)
                if IsFromCategory(self.virtual_dat.categories[3434232095], self.exemplar):
                    MaxSlopeBeforeLotFoundation = 0
            props.append(CreateAProp(self.virtual_dat.properties[1771767972], (0.0,)))
            props.append(CreateAProp(self.virtual_dat.properties[2297284498], (MaxSlopeBeforeLotFoundation,)))
            props.append(CreateAProp(self.virtual_dat.properties[2297284504], (3379372341,)))
            props.append(CreateAProp(self.virtual_dat.properties[2298271863], (2299228948,)))
            props.append(CreateAProp(self.virtual_dat.properties[3919251084], (MaxSlopeAllowed,)))
            props.sort(key=functools.cmp_to_key(lambda x, y: basic_cmp(x[2:2 + 8], y[2:2 + 8])))
            buffer = 'EQZT1###\r\n' + 'ParentCohort=Key:{0x00000000,0x00000000,0x00000000}\r\n' + 'PropCount=0x%08x\r\n' % len(
                props)
            buffer += '\r\n'.join(props)
            entry.content = entry.rawContent = buffer
            exemplar = SC4Exemplar(entry, self.virtual_dat)
            exemplar.entry = entry
            entry.exemplar = exemplar
            descriptor = LotDesc(entry)
            LotID = IID
            copiedExamplarBuffer = self.exemplar.Rep()
            buffer = struct.pack('III', 1697917002, self.exemplar.entry.tgi[1], IID)
            buffer += struct.pack('II', 0, 0)
            descEntry = SC4Entry(buffer, 0,
                                 os.path.join(self.parent.parent.rootFolder, '%s_%08x.SC4Lot' % (fileNameBase, IID)))
            descEntry.content = descEntry.rawContent = copiedExamplarBuffer
            descExamplar = SC4Exemplar(descEntry, self.virtual_dat)
            descExamplar.entry = descEntry
            descEntry.exemplar = descExamplar
            descEntry.exemplar.AddTextProp(CreateAProp(self.virtual_dat.properties[1787239298], (IID,)))
            descEntry.exemplar.AddTextProp(CreateAProp(self.virtual_dat.properties[2317746872], (IID,)))
            descEntry.exemplar.AddTextProp(CreateAProp(self.virtual_dat.properties[3928360329], (IID,)))
            descEntry.exemplar.Maj()
            descDescriptor = BuildingDesc(descEntry)
            self.virtual_dat.addEntries([descEntry], None, False, False)
            self.parent.parent.tree.Recategorize(descDescriptor, False)
            frame = LotEditorWin(self, -1, 'LotPreview ' + descriptor.name, size=(800,
                                                                                  800))
            frame.Display(entry.exemplar, self.virtual_dat, True)
            frame.Show()
            frame.on_draw()
            frame.on_draw()
            image = frame.Save()
            iconImage = SC4IconMakerDlg.compose_lot_icon(image)
            cIO = io.BytesIO()
            iconImage.save(cIO, 'PNG')
            strIcon = cIO.getvalue()
            buffer = struct.pack('III', 2238569388, 1782082854, IID)
            buffer += struct.pack('II', 0, len(strIcon))
            iconEntry = SC4Entry(buffer, 0,
                                 os.path.join(self.parent.parent.rootFolder, '%s_%08x.SC4Lot' % (fileNameBase, IID)))
            iconEntry.content = iconEntry.rawContent = strIcon[:]
            cIO.close()
            entries = [entry, descEntry, iconEntry]
            UVNK = self.exemplar.GetProp(2319542937)
            if UVNK is not None:
                if UVNK[0] == 539399691:
                    descExamplar.AddTextProp(CreateAProp(self.virtual_dat.properties[2319542937],
                                                         (UVNK[0], 1782082854, descExamplar.entry.tgi[2])))
                    uvnks = [self.virtual_dat.getEntry(UVNK[0], UVNK[1] + i, UVNK[2]) for i in offsetGID]
                    for i, uvnk in enumerate(uvnks):
                        if uvnk is not None:
                            uvnk.read_file(None, True, True)
                            try:
                                utxt = decode_sc4_text(uvnk.content[4:])
                            except UnicodeDecodeError:
                                utxt = uvnk.content.decode('utf-8', errors='replace')

                            uvnk.content = uvnk.rawContent = None
                            ltextEnt = self.DuplicateLTEXTEntry(descEntry.exemplar, utxt, 539399691,
                                                                1782082854 + uvnk.tgi[1] - UVNK[1],
                                                                descExamplar.entry.tgi[2])
                            entries.append(ltextEnt)

                IDK = self.exemplar.GetProp(3393284789)
                if IDK is not None:
                    descExamplar.AddTextProp(CreateAProp(self.virtual_dat.properties[3393284789],
                                                         (IDK[0], descExamplar.entry.tgi[1],
                                                          descExamplar.entry.tgi[2])))
                    idks = [self.virtual_dat.getEntry(IDK[0], v[1] + i, IDK[2]) for i in offsetGID]
                    for i, idk in enumerate(idks):
                        if idk is not None:
                            idk.read_file(None, True, True)
                            try:
                                utxt = decode_sc4_text(idk.content[4:])
                            except UnicodeDecodeError:
                                utxt = idk.content.decode('utf-8', errors='replace')

                            idk.content = idk.rawContent = None
                            ltextEnt = self.DuplicateLTEXTEntry(descEntry.exemplar, utxt, 539399691,
                                                                descExamplar.entry.tgi[1] + idk.tgi[1] - IDK[1],
                                                                descExamplar.entry.tgi[2])
                            entries.append(ltextEnt)

                descEntry.exemplar.Maj()
                entry.exemplar.Maj()
                self.virtual_dat.addEntries(entries, None, False, False)
                self.parent.parent.tree.Recategorize(descriptor, False)
                virtualDAT = self.virtual_dat
                parent = self.parent
                dlg.Destroy()
                self.parent.CloseCurrentTab()
                descPage = parent.AddNewDesc(descDescriptor, virtualDAT, False)
                descPage.OnRebuildProperties(None)
                descPage.exemplar.Maj()
                descPage.bSave.Enable(False)
                descEntry.exemplar.Maj()
                entry.exemplar.Maj()
                WriteADat(entry.fileName, entries, None, True)
                parent.AddNewDesc(descriptor, virtualDAT, False)
            dlg.Destroy()
        return

    def OnCreateLot(self, event):
        dlg = LotCreatorDlg(self, self.exemplar, self.virtual_dat, True)
        if dlg.ShowModal() == wx.ID_OK:
            init = datetime.datetime(2005, 5, 5, 21, 24, 15)
            today = datetime.datetime.today()
            dt = today - init
            dt = dt.days * 24 * 3600 + dt.seconds
            first = random.randrange(0, 15)
            IID = first * 268435456 + (dt & 268435455)
            fileNameBase = '%s%s%s_%sx%s_%s' % (dlg.purpose, '$' * (dlg.wealth + 1), dlg.stageCtrl.GetValue(),
                                                dlg.widthCtrl.GetValue(), dlg.depthCtrl.GetValue(),
                                                self.exemplar.GetProp(32)[0])
            buffer = struct.pack('III', 1697917002, 2835075954, IID)
            buffer += struct.pack('II', 0, 0)
            entry = SC4Entry(buffer, 0,
                             os.path.join(self.parent.parent.rootFolder, '%s_%08x.SC4Lot' % (fileNameBase, IID)))
            purposes = {'R': 1, 'CS': 2, 'CO': 3, 'IM': 7, 'ID': 6, 'IHT': 8, 'IR': 5}
            props = []
            props.append(CreateAProp(self.virtual_dat.properties[16], (16,)))
            props.append(CreateAPropFromString(self.virtual_dat.properties[32], str(fileNameBase)))
            props.append(CreateAProp(self.virtual_dat.properties[662775863], (int(dlg.stageCtrl.GetValue()),)))
            props.append(CreateAProp(self.virtual_dat.properties[1246398704], (8,)))
            props.append(CreateAProp(self.virtual_dat.properties[2297284489], (2,)))
            props.append(CreateAProp(self.virtual_dat.properties[2297284496],
                                     (int(dlg.widthCtrl.GetValue()), int(dlg.depthCtrl.GetValue()))))
            zoning = self.virtual_dat.ComputeZoning(dlg.purpose, self.exemplar.GetProp(662775824)[1])
            props.append(CreateAProp(self.virtual_dat.properties[2297284499], tuple(zoning)))
            props.append(CreateAProp(self.virtual_dat.properties[2297284501], (dlg.wealth + 1,)))
            props.append(CreateAProp(self.virtual_dat.properties[2297284502], (purposes[dlg.purpose],)))
            props.append(CreateAProp(self.virtual_dat.properties[3420603383], (1,)))
            currentID = 2297284864
            objID = dt & 16777215
            lotwidth = int(dlg.widthCtrl.GetValue())
            lotdepth = int(dlg.depthCtrl.GetValue())
            buildwidth = self.exemplar.GetProp(662775824)[0] / 16.0
            builddepth = self.exemplar.GetProp(662775824)[2] / 16.0
            posX = lotwidth / 2.0
            posY = lotdepth / 2.0
            xmin = posX - buildwidth / 2.0
            ymin = posY - builddepth / 2.0
            xmax = posX + buildwidth / 2.0
            ymax = posY + builddepth / 2.0
            posX = int(posX * 1048576)
            posY = int(posY * 1048576)
            xmin = int(xmin * 1048576)
            ymin = int(ymin * 1048576)
            xmax = int(xmax * 1048576)
            ymax = int(ymax * 1048576)
            families = self.exemplar.GetProp(662775920)
            buildingID = self.exemplar.entry.tgi[2]
            if families is not None:
                lst = [
                          lotBuildingChoiceSelf] + ['Family %s' % hex2str(f) for f in families]
                dlg1 = wx.SingleChoiceDialog(self, lotBuildingChoiceMsg,
                                             lotCreationTitle, lst, wx.CHOICEDLG_STYLE)
                if dlg1.ShowModal() == wx.ID_OK:
                    selected = dlg1.GetStringSelection()
                    if selected != lotBuildingChoiceSelf:
                        buildingID = int(selected[7:], 16)
                    dlg1.Destroy()
                else:
                    return
            v = [
                0, 0, 2, posX, 0, posY, xmin, ymin, xmax, ymax, 0, objID, buildingID]
            props.append(CreateAProp(self.virtual_dat.properties[currentID], v))
            currentID += 1
            objID += 1
            baseTex = self.virtual_dat.baseTex[dlg.purpose, dlg.wealth]
            for h in range(0, lotdepth):
                for w in range(0, lotwidth):
                    v = [
                        2, 0, 0, w * 1048576 + 524288, 0, h * 1048576 + 524288, w * 1048576, h * 1048576,
                                 (w + 1) * 1048576, (h + 1) * 1048576, 0, objID, baseTex]
                    props.append(CreateAProp(self.virtual_dat.properties[currentID], v))
                    currentID += 1
                    objID += 1

            props.append(CreateAProp(self.virtual_dat.properties[1771767972], (0.0,)))
            LotSizeX = lotwidth
            LotSizeY = lotdepth
            Width = self.exemplar.GetProp(662775824)[0] + 0.3
            Depth = self.exemplar.GetProp(662775824)[2] + 0.3
            Height = self.exemplar.GetProp(662775824)[1]
            MaxSlopeBeforeLotFoundation = eval(self.virtual_dat.MaxSlopeBeforeLotFoundation)
            MaxSlopeAllowed = eval(self.virtual_dat.MaxSlopeAllowed)
            props.append(CreateAProp(self.virtual_dat.properties[2297284498], (MaxSlopeBeforeLotFoundation,)))
            props.append(CreateAProp(self.virtual_dat.properties[2297284504], (3379372341,)))
            props.append(CreateAProp(self.virtual_dat.properties[2298271863], (2299228948,)))
            props.append(CreateAProp(self.virtual_dat.properties[3919251084], (MaxSlopeAllowed,)))
            props.sort(key=functools.cmp_to_key(lambda x, y: basic_cmp(x[2:2 + 8], y[2:2 + 8])))
            buffer = 'EQZT1###\r\n' + 'ParentCohort=Key:{0x00000000,0x00000000,0x00000000}\r\n' + 'PropCount=0x%08x\r\n' % len(
                props)
            buffer += '\r\n'.join(props)
            entry.content = entry.rawContent = buffer
            exemplar = SC4Exemplar(entry, self.virtual_dat)
            exemplar.entry = entry
            entry.exemplar = exemplar
            descriptor = LotDesc(entry)
            entries = [entry]
            entry.exemplar.Maj()
            WriteADat(entry.fileName, entries, None, True)
            self.virtual_dat.addEntries(entries, None, False, False)
            self.parent.parent.tree.Recategorize(descriptor, False)
            self.parent.AddNewDesc(descriptor, self.virtual_dat, False)
            frame = LotEditorWin(self, -1, 'LotPreview ' + descriptor.name, size=(800,
                                                                                  800))
            frame.Display(entry.exemplar, self.virtual_dat)
            frame.Show()
            frame.Destroy()
        dlg.Destroy()
        return

    def OnDependenciesListing(self, event):
        dlg = DependenciesDlg(self.parent.parent, self.exemplar)
        dlg.ShowModal()
        dlg.Destroy()

    def OnLotInfoDebug(self, event):
        self.exemplar.ReindexLotConfig(True)
        frame = LotEditorWin(self, -1, 'LotPreview ' + self.descriptor.name, size=(800,
                                                                                   800))
        frame.Display(self.exemplar, self.virtual_dat)
        frame.Show()
        self.exemplar.modified = True
        self.bSave.Enable(True)

    def OnConvertReward(self, event):
        ogs = list(self.exemplar.GetProp(2854081430))
        ogs.append(5387)
        newOGS = CreateAPropFromString(self.virtual_dat.properties[2854081430], ','.join([hex2str(v) for v in ogs]))
        self.exemplar.AddTextProp(newOGS)
        cityEx = CreateAPropFromString(self.virtual_dat.properties[3928885131], hex2str(self.exemplar.entry.tgi[2]))
        self.exemplar.AddTextProp(cityEx)
        condBuilding = CreateAPropFromString(self.virtual_dat.properties[3929147896], 'True')
        self.exemplar.AddTextProp(condBuilding)
        h = random.randint(0, 15)
        iid = 268435455 & self.exemplar.entry.tgi[2]
        buffer = struct.pack('III', 3395543715, 1247710966, iid)
        newVal = '--#-package:%s# -- package signature'
        newVal = newVal % hex2str(iid)[2:]
        buffer += struct.pack('II', 0, 4 + len(newVal))
        luaEntry = SC4Entry(buffer, 0, self.exemplar.entry.fileName)
        buffer = newVal
        luaEntry.content = buffer
        luaEntry.Maj()
        self.virtual_dat.addEntries([luaEntry], None, False, False)
        self.listProperties.DeleteAllItems()
        self.FillTheList()
        self.bSave.Enable(True)
        self.parent.parent.tree.Recategorize(self.descriptor)
        return

    def OnConvertToRKT4(self, event):
        rkt0 = self.exemplar.GetProp(662775840)
        rkt1 = self.exemplar.GetProp(662775841)
        if rkt0 is not None:
            values = [
                0, 0, 0, 0, 662775840, rkt0[0], rkt0[1], rkt0[2]]
        elif rkt1 is not None:
            values = [
                0, 0, 0, 0, 662775841, rkt1[0], rkt1[1], rkt1[2]]
        else:
            logger.warning('No RKT4 or RKT1 property found')
        newPropStr = CreateAPropFromString(self.virtual_dat.properties[662775844],
                                           ','.join([hex2str(v) for v in values]))
        try:
            self.exemplar.AddTextProp(newPropStr)
            self.exemplar.RemoveProp(662775840)
            self.exemplar.RemoveProp(662775841)
        except Exception:
            raise
            return

        self.listProperties.DeleteAllItems()
        self.FillTheList()
        self.bSave.Enable(True)
        self.descriptor.name = self.exemplar.GetProp(32)[0]
        self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
        self.parent.parent.listItems.Refresh()
        return

    def OnConvertToRKT0(self, event):
        rkt4 = self.exemplar.GetProp(662775844)
        rkt1 = self.exemplar.GetProp(662775841)
        values = []
        if rkt4 is not None:
            values = [
                rkt4[-3], rkt4[-2], rkt4[-1]]
        elif rkt1 is not None:
            values = [
                rkt1[0], rkt1[1], rkt1[2]]
        else:
            logger.warning('No RKT4 or RKT1 property found')
        newPropStr = CreateAPropFromString(self.virtual_dat.properties[662775840],
                                           ','.join([hex2str(v) for v in values]))
        try:
            self.exemplar.AddTextProp(newPropStr)
            self.exemplar.RemoveProp(662775844)
            self.exemplar.RemoveProp(662775841)
        except Exception:
            raise
            return

        self.listProperties.DeleteAllItems()
        self.FillTheList()
        self.bSave.Enable(True)
        self.descriptor.name = self.exemplar.GetProp(32)[0]
        self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
        self.parent.parent.listItems.Refresh()
        return

    def OnConvertToRKT1(self, event):
        rkt0 = self.exemplar.GetProp(662775840)
        rkt4 = self.exemplar.GetProp(662775844)
        values = []
        if rkt4 is not None:
            values = [
                rkt4[-3], rkt4[-2], rkt4[-1]]
        elif rkt0 is not None:
            values = [
                rkt0[0], rkt0[1], rkt0[2]]
        else:
            logger.warning('No RKT4 or RKT0 property found')
        newPropStr = CreateAPropFromString(self.virtual_dat.properties[662775841],
                                           ','.join([hex2str(v) for v in values]))
        try:
            self.exemplar.AddTextProp(newPropStr)
            self.exemplar.RemoveProp(662775840)
            self.exemplar.RemoveProp(662775844)
        except Exception:
            raise
            return

        self.listProperties.DeleteAllItems()
        self.FillTheList()
        self.bSave.Enable(True)
        self.descriptor.name = self.exemplar.GetProp(32)[0]
        self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
        self.parent.parent.listItems.Refresh()
        return

    def OnOpenLotWithBuilding(self, event):
        self.openedLots = []
        wx.BeginBusyCursor()
        if self.exemplar.GetProp(662775920) is not None:
            possibles = list(self.exemplar.GetProp(662775920)) + [self.exemplar.entry.tgi[2]]
        else:
            possibles = [
                self.exemplar.entry.tgi[2]]

        def UseThisIID(desc):
            for lcp in range(2297284864, 2297286143):
                values = desc.exemplar.GetProp(lcp)
                if values is None:
                    return False
                if values[0] == 0:
                    if values[12] in possibles:
                        return True

            return False

        descs = filter(UseThisIID, self.virtual_dat.categories[210091300].descriptors)
        for desc in descs:
            self.openedLots.append(self.parent.AddNewDesc(desc, self.virtual_dat, False))

        wx.EndBusyCursor()
        return

    def OnOpenLotWithProp(self, event):
        self.openedLots = []
        wx.BeginBusyCursor()
        if self.exemplar.GetProp(662775920) is not None:
            possibles = list(self.exemplar.GetProp(662775920)) + [self.exemplar.entry.tgi[2]]
        else:
            possibles = [
                self.exemplar.entry.tgi[2]]

        def UseThisIID(desc):
            for lcp in range(2297284864, 2297286143):
                values = desc.exemplar.GetProp(lcp)
                if values is None:
                    return False
                if values[0] == 1:
                    if values[12] in possibles:
                        return True

            return False

        descs = filter(UseThisIID, self.virtual_dat.categories[210091300].descriptors)
        for desc in descs:
            self.openedLots.append(self.parent.AddNewDesc(desc, self.virtual_dat, False))

        wx.EndBusyCursor()
        return

    def OnBuildingsFromLot(self, event):
        buildingID = None
        for lcp in range(2297284864, 2297286143):
            values = self.exemplar.GetProp(lcp)
            if values is None:
                break
            if values[0] == 0:
                buildingID = values[12]
                break

        if buildingID is None:
            return
        if buildingID in self.virtual_dat.categories:
            bOk = False
            for desc in self.virtual_dat.categories[buildingID].descriptors:
                if desc.exemplar.GetProp(16)[0] == 2:
                    bOk = True
                    self.parent.AddNewDesc(desc, self.virtual_dat, False)

            if bOk:
                return
        possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == buildingID,
                           self.virtual_dat.categories[210746197].descriptors)
        for desc in possibles:
            self.parent.AddNewDesc(desc, self.virtual_dat, False)

        return

    def OnRebuildProperties(self, event):
        bCategorized, includedCats = GetCategories(self.virtual_dat.rootCategory, self.descriptor)
        category = self.virtual_dat.categories[includedCats[0][1]]
        props = []
        IID = self.exemplar.entry.tgi[2]
        Height = height = self.exemplar.GetProp(662775824)[1]
        Width = width = self.exemplar.GetProp(662775824)[0]
        Depth = depth = self.exemplar.GetProp(662775824)[2]
        exemplarName = self.exemplar.GetProp(32)[0]
        try:
            fillingDegree = self.exemplar.GetProp(662775825)[0]
        except Exception:
            fillingDegree = 0.5

        LotSizeX = 1
        LotSizeY = 1
        if IsFromCategory(self.virtual_dat.categories[210746197], self.exemplar):
            if IsFromCategory(self.virtual_dat.categories[3431971885], self.exemplar):
                lotDesc = self.virtual_dat.FindLotFromBuilding(self.exemplar)
                if lotDesc is not None:
                    try:
                        LotSizeX = lotDesc.exemplar.GetProp(2297284496)[0]
                        LotSizeY = lotDesc.exemplar.GetProp(2297284496)[1]
                    except Exception:
                        pass

            if event is not None:
                dlg = wx.TextEntryDialog(self, fillingDegreeMsg, fillingDegreeTitleMsg, str(fillingDegree))
                if dlg.ShowModal() == wx.ID_OK:
                    newValue = dlg.GetValue()
                    newPropStr = CreateAPropFromString(self.virtual_dat.properties[662775825], newValue)
                    self.exemplar.AddTextProp(newPropStr)
                    fillingDegree = self.exemplar.GetProp(662775825)[0]
                    dlg.Destroy()
                else:
                    dlg.Destroy()
                    return
        Volume = volume = Height * Width * Depth * fillingDegree
        cat = category
        variablesName = []
        variables = []
        while 1:
            for variable, what in cat.code:
                if variable not in variablesName:
                    variablesName.append(variable)
                    variables.append((variable, '(' + what + ')'))

            if cat.parent is not None:
                cat = cat.parent
            else:
                break

        del variablesName
        propCreated = []
        while 1:
            for prop2CreatID in category.evalProperties.keys():
                if prop2CreatID == 662775825:
                    pass
                elif prop2CreatID in propCreated:
                    pass
                else:
                    propCreated.append(prop2CreatID)
                    codetxt = category.evalProperties[prop2CreatID]
                    initialCode = codetxt
                    try:
                        while 1:
                            codetxt2 = codetxt
                            for variable, what in variables:
                                codetxt = codetxt.replace(variable, what)

                            if codetxt == codetxt2:
                                break

                        values = eval(codetxt)
                    except Exception:
                        logger.exception(
                            'Error evaluating property %s\n  initial: %s\n  final: %s\n  variables: %s',
                            hex2str(prop2CreatID), initialCode, codetxt, variables)
                        raise

                    prop2CreatValue = []
                    if not isinstance(values, tuple):
                        values = (
                            values,)
                    for v in values:
                        if self.virtual_dat.properties[prop2CreatID].Type == 'Float32':
                            prop2CreatValue.append(str(v))
                        elif self.virtual_dat.properties[prop2CreatID].Type == 'Sint64':
                            prop2CreatValue.append(hex2str(v, 64))
                        elif self.virtual_dat.properties[prop2CreatID].Type[-2:] == '32':
                            prop2CreatValue.append(hex2str(v, 32))
                        else:
                            prop2CreatValue.append(hex2str(v, 8))

                    props.append(
                        CreateAPropFromString(self.virtual_dat.properties[prop2CreatID], ','.join(prop2CreatValue)))

            for prop2CreatID in category.programProperties.keys():
                if prop2CreatID in propCreated:
                    pass
                elif self.exemplar.GetProp(prop2CreatID) is not None:
                    pass
                else:
                    propCreated.append(prop2CreatID)
                    prop2CreatValue = category.programProperties[prop2CreatID]
                    props.append(CreateAPropFromString(self.virtual_dat.properties[prop2CreatID],
                                                       str(prop2CreatValue.replace('IID', '0x%08X' % IID).replace('GID',
                                                                                                                  '0x%08X' % self.parent.parent.GID).replace(
                                                           'exemplarName', exemplarName))))

            for prop2CreatID in category.setProperties.keys():
                if prop2CreatID in propCreated:
                    pass
                elif prop2CreatID == 2317746857 and self.exemplar.GetProp(2319542937):
                    pass
                elif prop2CreatID == 2308635565 and self.exemplar.GetProp(3393284789):
                    pass
                else:
                    propCreated.append(prop2CreatID)
                    prop2CreatValue = category.setProperties[prop2CreatID]
                    props.append(CreateAPropFromString(self.virtual_dat.properties[prop2CreatID], str(prop2CreatValue)))

            for prop2CreatID in category.factorProperties.keys():
                if prop2CreatID in propCreated:
                    pass
                else:
                    propCreated.append(prop2CreatID)
                    factors = category.factorProperties[prop2CreatID]
                    prop2CreatValue = []
                    for factor in factors:
                        v = factor * volume
                        v = Clamp(self.virtual_dat.properties[prop2CreatID], v)
                        if self.virtual_dat.properties[prop2CreatID].Type == 'Float32':
                            prop2CreatValue.append(str(v))
                        elif self.virtual_dat.properties[prop2CreatID].Type == 'Sint64':
                            prop2CreatValue.append(hex2str(v, 64))
                        elif self.virtual_dat.properties[prop2CreatID].Type[:-2] == 32:
                            prop2CreatValue.append(hex2str(v, 32))
                        else:
                            prop2CreatValue.append(hex2str(v, 8))

                    props.append(
                        CreateAPropFromString(self.virtual_dat.properties[prop2CreatID], ','.join(prop2CreatValue)))

            for prop2CreatID in category.pairedFactorProperties.keys():
                if prop2CreatID in propCreated:
                    pass
                else:
                    propCreated.append(prop2CreatID)
                    factors = category.pairedFactorProperties[prop2CreatID]
                    prop2CreatValue = []
                    for factor in factors:
                        v = factor[1] * volume
                        v = Clamp(self.virtual_dat.properties[prop2CreatID], v)
                        if self.virtual_dat.properties[prop2CreatID].Type == 'Float32':
                            prop2CreatValue.append(factor[0])
                            prop2CreatValue.append(str(v))
                        elif self.virtual_dat.properties[prop2CreatID].Type == 'Sint64':
                            prop2CreatValue.append(factor[0])
                            prop2CreatValue.append(hex2str(v, 64))
                        elif self.virtual_dat.properties[prop2CreatID].Type[:-2] == 32:
                            prop2CreatValue.append(factor[0])
                            prop2CreatValue.append(hex2str(v, 32))
                        else:
                            prop2CreatValue.append(factor[0])
                            prop2CreatValue.append(hex2str(v, 8))

                    props.append(
                        CreateAPropFromString(self.virtual_dat.properties[prop2CreatID], ','.join(prop2CreatValue)))

            if category.parent is not None:
                category = category.parent
            else:
                break

        props.sort(key=functools.cmp_to_key(lambda x, y: basic_cmp(x[2:2 + 8], y[2:2 + 8])))
        category = self.virtual_dat.categories[includedCats[0][1]]
        props = [p for p in props if str(p[2:2 + 8].upper()) not in category.removeProperties.values()]
        for prop in category.removeProperties.keys():
            self.exemplar.RemoveProp(prop)

        UVNK = self.exemplar.GetProp(2319542937)
        IDK = self.exemplar.GetProp(3393284789)
        if UVNK is not None:
            props = [p for p in props if str(p[2:2 + 8].upper()) != '899AFBAD']
        if IDK is not None:
            props = [p for p in props if str(p[2:2 + 8].upper()) != '8A2602A9']
        for prop in props:
            self.exemplar.AddTextProp(prop)

        self.listProperties.DeleteAllItems()
        self.FillTheList()
        self.bSave.Enable(True)
        self.descriptor.name = self.exemplar.GetProp(32)[0]
        self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
        self.parent.parent.listItems.Refresh()
        self.OnOpenLotWithBuilding(event)
        if IsFromCategory(self.virtual_dat.categories[2895100787], self.exemplar):
            for p in self.openedLots:
                p.OnRecomputeStage(event)

        return

    def OnRebuildOccupantSize(self, event):
        if self.view:
            try:
                bbox = _model_occupant_bbox(self.view.viewingData[0])
                if bbox is None:
                    raise ValueError('No readable model mesh for Occupant Size rebuild')
                Height = height = round(bbox[1], 4)
                Width = width = round(clamp_to_tile(bbox[0]), 4)
                Depth = depth = round(clamp_to_tile(bbox[2]), 4)
            except Exception:
                logger.exception('Failed to rebuild Occupant Size from model')
                return None

            newPropStr = CreateAPropFromString(self.virtual_dat.properties[662775824],
                                               '%f,%f,%f' % (Width, Height, Depth))
            if not self.exemplar.AddTextProp(newPropStr):
                return None
            self.listProperties.DeleteAllItems()
            self.FillTheList()
            self.bSave.Enable(True)
            self.descriptor.name = self.exemplar.GetProp(32)[0]
            self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
            self.parent.parent.listItems.Refresh()
        return None

    def OnOpenFamily(self, event):
        idMenu = event.GetId()
        familyIdx = self.familyMenuIDs.index(idMenu)
        family = self.exemplar.GetProp(662775920)[familyIdx]
        for desc in self.virtual_dat.categories[family].descriptors:
            self.parent.AddNewDesc(desc, self.virtual_dat, False)

    def DuplicateLTEXTEntry(self, exemplar, utxt, t, g, i):
        newVal = encode_sc4_text(utxt)
        buffer = struct.pack('III', t, g, i)
        buffer += struct.pack('II', 0, 4 + len(newVal))
        ltextEntry = SC4Entry(buffer, 0, exemplar.entry.fileName)
        buffer = struct.pack('H', len(utxt))
        buffer += struct.pack('H', 4096)
        buffer += newVal
        ltextEntry.content = buffer
        ltextEntry.Maj()
        self.virtual_dat.addEntries([ltextEntry], None, False, False)
        return ltextEntry

    def CreateLTEXTEntry(self, utxt, t, g, i, propid2add, propid2remove=0):
        newVal = encode_sc4_text(utxt)
        buffer = struct.pack('III', t, g, i)
        buffer += struct.pack('II', 0, 4 + len(newVal))
        ltextEntry = SC4Entry(buffer, 0, self.exemplar.entry.fileName)
        buffer = struct.pack('H', len(utxt))
        buffer += struct.pack('H', 4096)
        buffer += newVal
        ltextEntry.content = buffer
        ltextEntry.Maj()
        self.InternalSave(ltextEntry.fileName)
        self.virtual_dat.addEntries([ltextEntry], None, False, False)
        self.exemplar.RemoveProp(propid2remove)
        if propid2add:
            newPropStr = CreateAPropFromString(self.virtual_dat.properties[propid2add],
                                               '0x%08X,0x%08X,0x%08X' % (t, g, i))
            self.exemplar.AddTextProp(newPropStr)
        self.listProperties.DeleteAllItems()
        self.FillTheList()
        if propid2add:
            self.bSave.Enable(True)
        self.descriptor.name = self.exemplar.GetProp(32)[0]
        self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
        self.parent.parent.listItems.Refresh()
        return

    def OnAddLangUVNK(self, event):
        idMenu = event.GetId()
        txt = self.exemplar.GetPropObject(32).rawdata
        try:
            utxt = str(txt)
        except Exception:
            try:
                utxt = decode_sc4_text(txt)
            except Exception:
                utxt = txt.decode('utf-8', errors='replace')

        UVNK = self.exemplar.GetProp(2319542937)
        if UVNK:
            uvnks = [self.virtual_dat.getEntry(UVNK[0], UVNK[1] + i, UVNK[2]) for i in offsetGID]
            for i, uvnk in enumerate(uvnks):
                if uvnk:
                    uvnk.read_file(None, True, True)
                    try:
                        utxt = decode_sc4_text(uvnk.content[4:])
                    except UnicodeDecodeError:
                        utxt = uvnk.content.decode('utf-8', errors='replace')

                    break

        idx = self.AddLangUVNK_IDs.index(idMenu)
        self.CreateLTEXTEntry(utxt, 539399691, 1782082854 + offsetGID[idx], self.exemplar.entry.tgi[2], 0)
        return

    def OnConvertToUVNK(self, event):
        try:
            txt = self.exemplar.GetPropObject(2308635565).rawdata
        except Exception:
            txt = self.exemplar.GetPropObject(32).rawdata

        try:
            utxt = str(txt)
        except Exception:
            try:
                utxt = decode_sc4_text(txt)
            except Exception:
                utxt = txt.decode('utf-8', errors='replace')

        if self.exemplar.GetProp(1788208387) and self.exemplar.GetProp(1788208387)[0]:
            newProp = CreateAProp(self.virtual_dat.properties[1788208387], (False,))
            self.exemplar.AddTextProp(newProp)
        self.CreateLTEXTEntry(utxt, 539399691, 1782082854, self.exemplar.entry.tgi[2], 2319542937, 2308635565)

    def OnAddLangIDK(self, event):
        idMenu = event.GetId()
        txt = self.exemplar.GetPropObject(32).rawdata
        try:
            utxt = str(txt)
        except Exception:
            try:
                utxt = decode_sc4_text(txt)
            except Exception:
                utxt = txt.decode('utf-8', errors='replace')

        IDK = self.exemplar.GetProp(3393284789)
        if IDK:
            idks = [self.virtual_dat.getEntry(IDK[0], IDK[1] + i, IDK[2]) for i in offsetGID]
            for i, idk in enumerate(idks):
                if idk:
                    idk.read_file(None, True, True)
                    try:
                        utxt = decode_sc4_text(idk.content[4:])
                    except UnicodeDecodeError:
                        utxt = idk.content.decode('utf-8', errors='replace')

                    break

        idx = self.AddLangIDK_IDs.index(idMenu)
        self.CreateLTEXTEntry(utxt, 539399691, self.exemplar.entry.tgi[1] + offsetGID[idx], self.exemplar.entry.tgi[2],
                              0)
        return

    def OnConvertToIDK(self, event):
        txt = self.exemplar.GetPropObject(2317746857).rawdata
        try:
            utxt = str(txt)
        except Exception:
            try:
                utxt = decode_sc4_text(txt)
            except Exception:
                utxt = txt.decode('utf-8', errors='replace')

        self.CreateLTEXTEntry(utxt, 539399691, self.exemplar.entry.tgi[1], self.exemplar.entry.tgi[2], 3393284789,
                              2317746857)

    def OnAddItemName(self, event):
        newPropStr = CreateAPropFromString(self.virtual_dat.properties[2308635565],
                                           self.exemplar.GetPropObject(32).rawdata)
        if not self.exemplar.AddTextProp(newPropStr):
            return None
        if self.exemplar.GetProp(1788208387) and self.exemplar.GetProp(1788208387)[0]:
            newProp = CreateAProp(self.virtual_dat.properties[1788208387], (False,))
            self.exemplar.AddTextProp(newProp)
        self.listProperties.DeleteAllItems()
        self.FillTheList()
        self.bSave.Enable(True)
        self.descriptor.name = self.exemplar.GetProp(32)[0]
        self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
        self.parent.parent.listItems.Refresh()
        return None

    def OnAddDescription(self, event):
        try:
            txt = self.exemplar.GetPropObject(2308635565).rawdata
        except Exception:
            txt = self.exemplar.GetPropObject(32).rawdata

        newPropStr = CreateAPropFromString(self.virtual_dat.properties[2317746857], txt)
        if not self.exemplar.AddTextProp(newPropStr):
            return None
        self.listProperties.DeleteAllItems()
        self.FillTheList()
        self.bSave.Enable(True)
        self.descriptor.name = self.exemplar.GetProp(32)[0]
        self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
        self.parent.parent.listItems.Refresh()
        return None

    def OnAddProperty(self, event):
        k = self.virtual_dat.properties.keys()
        choices = [self.virtual_dat.properties[idx].Name for idx in k]
        choices.sort(key=str.lower)
        dlg = wx.SingleChoiceDialog(self, addPropertyMsg, addPropertyTitle, choices, wx.CHOICEDLG_STYLE)
        if dlg.ShowModal() == wx.ID_OK:
            choose = dlg.GetStringSelection()
            propChoosen = None
            for id, v in self.virtual_dat.properties.items():
                if v.Name == choose:
                    propChoosen = id
                    break

            if propChoosen:
                msg = valuePropertyMsg % choose
                title = addPropertyTitle
                value = ''
                dlgVal = wx.TextEntryDialog(self, msg, title, value)
                if dlgVal.ShowModal() == wx.ID_OK:
                    newValue = dlgVal.GetValue()
                    newPropStr = CreateAPropFromString(self.virtual_dat.properties[propChoosen], newValue)
                    if not self.exemplar.AddTextProp(newPropStr):
                        dlgVal.Destroy()
                        dlg.Destroy()
                        return
                    self.listProperties.DeleteAllItems()
                    self.FillTheList()
                    self.bSave.Enable(True)
                    self.descriptor.name = self.exemplar.GetProp(32)[0]
                    self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
                    self.parent.parent.tree.Recategorize(self.descriptor)
                    self.parent.parent.listItems.Refresh()
                dlgVal.Destroy()
        dlg.Destroy()
        return

    def SelectedPropForNonAdvanced(self):
        index = self.listProperties.GetFirstSelected()
        if index == -1:
            return False
        while index != -1:
            i = index - 3
            if i >= 0 and i < len(self.exemplar.props):
                prop = self.exemplar.props[i]
                if prop.id >= 2297284864 and prop.id < 2297286144:
                    if prop.values[0] == 0:
                        return False
                else:
                    return False
            index = self.listProperties.GetNextSelected(index)

        return True

    def OnCopy(self, event):
        self.parent.clipboard = []
        index = self.listProperties.GetFirstSelected()
        while index != -1:
            i = index - 3
            if i >= 0 and i < len(self.exemplar.props):
                self.parent.clipboard.append(self.exemplar.props[i].TextRep())
            index = self.listProperties.GetNextSelected(index)

    def OnPaste(self, event):
        prop2Add = []
        for line in self.parent.clipboard:
            id = int(line[2:2 + 8].lower(), 16)
            if id >= 2297284864 and id < 2297286144:
                prop2Add.append(line)
            else:
                self.exemplar.AddTextProp(line)

        if prop2Add != []:
            currentID = 2297284864
            for id in range(2297284864, 2297286144):
                values = self.exemplar.GetProp(id)
                if values is None:
                    currentID = id
                    break

            for prop in prop2Add:
                line = hex2str(currentID) + prop[10:]
                self.exemplar.AddTextProp(line)
                currentID += 1

            self.exemplar.ReindexLotConfig(True)
        if self.parent.clipboard != []:
            self.listProperties.DeleteAllItems()
            self.FillTheList()
            self.bSave.Enable(True)
            self.descriptor.name = self.exemplar.GetProp(32)[0]
            self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
            self.parent.parent.tree.Recategorize(self.descriptor)
            self.parent.parent.listItems.Refresh()
        return

    def OnDelete(self, event):
        index = self.listProperties.GetFirstSelected()
        bRefill = False
        prop2Remove = []
        while index != -1:
            i = index - 3
            if i >= 0 and i < len(self.exemplar.props):
                prop2Remove.append(self.exemplar.props[i].id)
            index = self.listProperties.GetNextSelected(index)

        bNeedReindex = False
        for id in prop2Remove:
            if id >= 2297284864 and id < 2297286144:
                bNeedReindex = True
            self.exemplar.RemoveProp(id)

        if bNeedReindex:
            self.exemplar.ReindexLotConfig()
        if prop2Remove != []:
            self.listProperties.DeleteAllItems()
            self.FillTheList()
            self.bSave.Enable(True)
            self.descriptor.name = self.exemplar.GetProp(32)[0]
            self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
            self.parent.parent.tree.Recategorize(self.descriptor)
            self.parent.parent.listItems.Refresh()


class SC4NoteBook(wx.Notebook):

    def __init__(self, parent, mainFrame):
        wx.Notebook.__init__(self, parent, -1, style=wx.BK_DEFAULT | wx.CLIP_CHILDREN | wx.TAB_TRAVERSAL)
        self.parent = mainFrame
        self.currentPage = None
        self.descriptors = []
        self.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.OnPageChanged)
        self.Bind(wx.EVT_SET_FOCUS, self.OnFocus)
        self.clipboard = []
        return

    def LoadPics(self, virtualDAT):
        if _env_true('SC4PIM_SKIP_NOTEBOOK_PICS'):
            return
        il = wx.ImageList(47, 37)
        for i, cat in virtualDAT.categories.items():
            icon_path = str(asset_path('icons', cat.imgName))
            img = wx.Image(icon_path)
            if not img.IsOk():
                logger.debug('Missing category icon: %s', icon_path)
                img = wx.Image(1, 1)
            cat.imgIdx = il.Add(img.ConvertToBitmap())

        self.AssignImageList(il)

    def OnPageChanged(self, event):
        newPage = event.GetSelection()
        self.RestorePage(newPage)
        event.Skip()

    def OnFocus(self, event):
        if self.currentPage is None:
            return
        self.ChangeSelection(self.currentPage)
        self.RestorePage(self.currentPage)
        event.Skip()
        return

    def RestorePage(self, newPage):
        self.Freeze()
        self.parent.staticFileName.SetLabel(unknownRK)
        self.currentPage = newPage
        if hasattr(self.parent, 'viewer') and hasattr(self.parent.viewer, 's3d_mesh') and self.parent.viewer.s3d_mesh is not None:
            self.parent.viewer.s3d_mesh = None

        if self.parent.viewer.s3d_mesh is not None:
            self.parent.viewer.s3d_mesh.free_3d(self.parent.viewer.s3d_textures_holder)
            self.parent.viewer.s3d_mesh = None
            self.parent.viewer.refresh(False)
        descriptor = self.descriptors[newPage]
        exemplar = descriptor.exemplar
        rkt4 = exemplar.GetProp(662775844)
        if rkt4 is not None:
            choices = []
            for z in range(len(rkt4) // 8):
                choices.append(('Model #%d' % z, z))

            self.parent.SetModelStateChoices(choices)
        else:
            self.parent.SetModelStateChoices([])
        try:
            self.GetPage(newPage).RebuildViewer()
            view = self.GetPage(newPage).view
        except Exception:
            view = None

        if view:
            zoom = self.parent.cbZoom.GetClientData(self.parent.cbZoom.GetSelection())
            rot = self.parent.cbRotation.GetClientData(self.parent.cbRotation.GetSelection())
            try:
                state = self.parent.cbStateChoice.GetClientData(self.parent.cbStateChoice.GetSelection())
            except Exception:
                state = 0

            if zoom == -1:
                nZoom = 0
            else:
                nZoom = zoom
            view.draw(self.parent.viewer, self.parent.staticFileName, zoom, rot, state)
            self.parent.currentModel = view
        else:
            self.parent.currentModel = None
            self.parent.staticFileName.SetLabel(unknownRK)
        self.Thaw()
        return

    def CloseCurrentTab(self):
        if self.GetCurrentPage() is None:
            return
        self.GetCurrentPage().UndoInCaseModified()
        self.GetCurrentPage().OnClose()
        del self.descriptors[self.currentPage]
        oldPage = self.currentPage
        if self.currentPage >= len(self.descriptors):
            self.currentPage = len(self.descriptors) - 1
            if self.currentPage == -1:
                self.currentPage = None
        self.DeletePage(oldPage)
        if self.currentPage is not None:
            self.ChangeSelection(self.currentPage)
            self.RestorePage(self.currentPage)
        self.Refresh(False)
        return

    def OnCloseTab(self, event):
        if self.GetCurrentPage() is None:
            return
        self.GetCurrentPage().UndoInCaseModified()
        self.GetCurrentPage().OnClose()
        del self.descriptors[self.currentPage]
        oldPage = self.currentPage
        if self.currentPage >= len(self.descriptors):
            self.currentPage = len(self.descriptors) - 1
            if self.currentPage == -1:
                self.currentPage = None
        self.DeletePage(oldPage)
        if self.currentPage is not None:
            self.ChangeSelection(self.currentPage)
            self.RestorePage(self.currentPage)
        self.Refresh(False)
        return

    def ReplaceCurrentPage(self, descriptor, virtualDAT):
        if self.parent.viewer.s3d_mesh is not None:
            self.parent.viewer.s3d_mesh.free_3d(self.parent.viewer.s3d_textures_holder)
            self.parent.viewer.s3d_mesh = None
            self.parent.viewer.refresh(False)
        for i, desc in enumerate(self.descriptors):
            if descriptor.exemplar.entry.tgi == desc.exemplar.entry.tgi:
                self.ChangeSelection(i)
                self.RestorePage(i)
                return

        self.Freeze()
        self.descriptors[self.currentPage] = descriptor
        panel = self.GetCurrentPage()
        self.SetPageText(self.currentPage, descriptor.name)
        panel.Change(descriptor)
        self.Thaw()
        return

    def AddNewDesc(self, descriptor, virtualDAT, bAdd):
        try:
            img = virtualDAT.categories[descriptor.cats[0]].imgIdx
        except Exception:
            img = virtualDAT.categories[4089082401].imgIdx

        if bAdd and len(self.descriptors):
            panel = self.GetCurrentPage()
            if not panel.exemplar.modified:
                self.ReplaceCurrentPage(descriptor, virtualDAT)
                self.SetPageImage(self.currentPage, img)
                return self.currentPage
        if self.parent.viewer.s3d_mesh is not None:
            self.parent.viewer.s3d_mesh.free_3d(self.parent.viewer.s3d_textures_holder)
            self.parent.viewer.s3d_mesh = None
            self.parent.viewer.refresh(False)
        for i, desc in enumerate(self.descriptors):
            if descriptor.exemplar.entry.tgi == desc.exemplar.entry.tgi:
                self.ChangeSelection(i)
                self.RestorePage(i)
                self.SetPageImage(i, img)
                return self.GetPage(i)

        self.Freeze()
        page = NoteBookPanel(self, descriptor, virtualDAT)
        self.descriptors.append(descriptor)
        self.AddPage(page, decode_unicode_escape(str(descriptor.name)), True, img)
        self.ChangeSelection(self.GetPageCount() - 1)
        self.Thaw()
        return page


class ConfigureDialog(sc.SizedDialog):

    def __init__(self, parent):
        sc.SizedDialog.__init__(self, parent, -1, configurationDialogTitle,
                                style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.ReadConfig()
        pane = self.GetContentsPane()
        pane.SetSizerType('vertical')
        wx.StaticText(pane, -1, configurationDialogGID % parent.GID)
        self.maxisFolder = parent.maxisFolder
        self.rootFolder = parent.rootFolder
        self.listFolder = []
        rootPane = sc.SizedPanel(pane, -1)
        rootPane.SetSizerType('horizontal')
        wx.StaticText(rootPane, -1, configurationDialogPluginsRoot)
        self.rootFolderCtrl = wx.TextCtrl(rootPane, -1, self.rootFolder, size=Size(520, -1))
        self.rootFolderCtrl.SetSizerProp('expand', True)
        self.rootFolderCtrl.SetSizerProp('proportion', 1)
        self.bBrowseRoot = wx.Button(rootPane, -1, configurationDialogBrowse)
        self.bBrowseRoot.Bind(wx.EVT_BUTTON, self.OnBrowseRoot)
        self.game_folders = _existing_unique_paths([parent.maxisFolder] + getattr(parent, 'gameFolders', []))
        self._build_folder_choices()
        self.lb1 = wx.CheckListBox(pane, -1, choices=self.listFolder, style=wx.LB_SINGLE | wx.LB_HSCROLL, size=Size(700, -1))
        self.lb1.SetSelection(0)
        self.lb1.SetSizerProp('expand', True)
        self.lb1.SetSizerProp('proportion', 1)
        for checked in self.to_check:
            self.lb1.Check(checked)
        buttonPane = sc.SizedPanel(pane, -1)
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.Fit()
        self.SetMinSize(self.GetSize())
        self.Bind(wx.EVT_BUTTON, self.OnOK, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnCancel, id=wx.ID_CANCEL)

    def _build_folder_choices(self):
        self.listFolder = []
        self.to_check = []
        default_folders = []
        for game_folder in self.game_folders:
            default_folders.append((game_folder, False))
            default_folders.append((os.path.join(game_folder, 'Plugins'), True))
            default_folders.append((os.path.join(game_folder, 'plugins'), True))
        default_folders.append((self.rootFolder, True))
        seen_folders = set()
        for folder, recurse_by_default in default_folders:
            if not folder or not os.path.isdir(folder):
                continue
            normalised = self._normalise_path(folder)
            if normalised in seen_folders:
                continue
            seen_folders.add(normalised)
            self.listFolder.append(os.path.normpath(folder))
            if recurse_by_default or normalised in self.pathToScan:
                self.to_check.append(len(self.listFolder) - 1)
        if os.path.isdir(self.rootFolder):
            for root, dirs, files in os.walk(self.rootFolder):
                for folder in dirs:
                    path = os.path.join(self.rootFolder, folder)
                    normalised = self._normalise_path(path)
                    if normalised in seen_folders:
                        continue
                    seen_folders.add(normalised)
                    self.listFolder.append(os.path.normpath(path))
                    if normalised in self.pathToScan:
                        self.to_check.append(len(self.listFolder) - 1)
                break

    def _refresh_folder_list(self):
        previous_checked = set()
        if hasattr(self, 'lb1'):
            for i, path in enumerate(self.listFolder):
                if self.lb1.IsChecked(i):
                    previous_checked.add(self._normalise_path(path))
        self._build_folder_choices()
        self.lb1.Set(self.listFolder)
        for i, path in enumerate(self.listFolder):
            normalised = self._normalise_path(path)
            if normalised in previous_checked or i in self.to_check:
                self.lb1.Check(i)
        if self.listFolder:
            self.lb1.SetSelection(0)

    def OnBrowseRoot(self, event):
        dlg = wx.DirDialog(self, chooseFolderMsg, defaultPath=self.rootFolder, style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.rootFolder = os.path.normpath(dlg.GetPath())
            self.rootFolderCtrl.SetValue(self.rootFolder)
            self._refresh_folder_list()
        dlg.Destroy()

    def OnOK(self, event):
        # Save configuration before closing
        self.OnSave(None)
        self.EndModal(wx.ID_OK)

    def OnCancel(self, event):
        self.EndModal(wx.ID_CANCEL)

    def ReadConfig(self):
        self.pathToScan = [
            self._normalise_path(path) for path, _recurse in config.load_folders()
        ]

    @staticmethod
    def _normalise_path(path):
        return os.path.normcase(os.path.normpath(path))

    def OnSave(self, parent):
        root_folder = self.rootFolderCtrl.GetValue().strip()
        if root_folder:
            new_root = os.path.normpath(root_folder)
            if self._normalise_path(new_root) != self._normalise_path(self.rootFolder):
                self.rootFolder = new_root
                self._refresh_folder_list()
        if parent is not None:
            parent.rootFolder = self.rootFolder
        config.save_user_plugins_root(self.rootFolder)
        folders = []
        maxis_root = self._normalise_path(self.maxisFolder) if self.maxisFolder else ''
        plugins_root = self._normalise_path(self.rootFolder) if self.rootFolder else ''
        for i, path in enumerate(self.listFolder):
            if path and self.lb1.IsChecked(i):
                normalised = self._normalise_path(path)
                recurse = normalised not in (maxis_root, plugins_root)
                folders.append((path, recurse))
        config.save_folders(folders)


class MainFrame(wx.Frame):

    def __init__(self):
        self._mw_settings = config.load_main_window()
        size = Size(int(self._mw_settings['Width']), int(self._mw_settings['Height']))
        wx.Frame.__init__(self, None, title='%s %s' % (appTitle, get_version()), size=size)
        pos_x = int(self._mw_settings['X'])
        pos_y = int(self._mw_settings['Y'])
        if pos_x >= 0 and pos_y >= 0:
            self.SetPosition((pos_x, pos_y))
        # Initialize GID (Group ID) from Windows registry or generate new one.
        self.GID = _read_user_group_id_from_registry()
        if self.GID is None:
            init = datetime.datetime(2005, 5, 5, 21, 24, 15)
            today = datetime.datetime.today()
            dt = today - init
            dt = dt.days * 24 * 3600 + dt.seconds
            first = random.randrange(1, 15, 2)
            self.GID = first * 268435456 + (dt & 268435455)
        # Clamp to 32-bit unsigned: the GID is a 32-bit DBPF group id, and
        # struct 'L' is platform-width (8 bytes on 64-bit Unix).
        self.GID &= 0xFFFFFFFF

        menuBar = wx.MenuBar()
        menu1 = wx.Menu()
        menu1.Append(104, menuItem1_1)
        menuBar.Append(menu1, menuItem1)
        self.SetMenuBar(menuBar)
        self.Bind(wx.EVT_MENU, self.OnQuit, id=104)
        self.Bind(wx.EVT_MENU, self.OnConfigure, id=201)
        splitter = wx.SplitterWindow(self, -1, style=wx.CLIP_CHILDREN | wx.SP_LIVE_UPDATE | wx.SP_3D)
        splitterHoriz = wx.SplitterWindow(splitter, -1, style=wx.CLIP_CHILDREN | wx.SP_LIVE_UPDATE | wx.SP_3D)
        self.splitter = splitter
        self.splitterHoriz = splitterHoriz
        rightUpPanel = wx.Panel(splitterHoriz)
        rightDownPanel = wx.Panel(splitterHoriz)
        leftPanel = wx.Panel(splitter)
        self.currentModel = None
        self.listItemsCat = None
        # The tree node whose contents the list currently shows. Used to tell a
        # genuine navigation (clear the filter) from a transient re-selection
        # such as the one drag-and-drop triggers (keep the filter).
        self._current_list_node = None
        self.virtualDAT = VirtualDat(None)
        self.virtualDAT.getEntry(0, 0, 0)
        self.tree = MyTreeCtrl(self.virtualDAT, leftPanel, self,
                               style=wx.TR_HAS_BUTTONS | wx.TR_ROW_LINES | wx.TAB_TRAVERSAL, size=(400,
                                                                                                   400))
        if not _env_true('SC4PIM_SAFE_MODE'):
            self.tree.ExpandAll()
        self._saved_tree_expanded = self._mw_settings.get('TreeExpanded', [])
        self.treeSearch = wx.SearchCtrl(leftPanel, -1, style=wx.TE_PROCESS_ENTER)
        self.treeSearch.SetDescriptiveText(treeSearchHint)
        self.treeSearch.ShowCancelButton(True)
        self.treeSearch.Bind(wx.EVT_TEXT, self.OnTreeSearch)
        self.treeSearch.Bind(wx.EVT_TEXT_ENTER, self.OnTreeSearchNext)
        self.treeSearch.Bind(wx.EVT_SEARCHCTRL_SEARCH_BTN, self.OnTreeSearchNext)
        self.treeSearch.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self.OnTreeSearchCancel)
        self.bTreeExpand = wx.Button(leftPanel, -1, treeExpandAll, style=wx.BU_EXACTFIT)
        self.bTreeExpand.SetToolTip(treeExpandAllTip)
        self.bTreeExpand.Bind(wx.EVT_BUTTON, lambda evt: self.tree.ExpandAll())
        self.bTreeCollapse = wx.Button(leftPanel, -1, treeCollapseAll, style=wx.BU_EXACTFIT)
        self.bTreeCollapse.SetToolTip(treeCollapseAllTip)
        self.bTreeCollapse.Bind(wx.EVT_BUTTON, self.OnTreeCollapseAll)
        self.virtualDAT.tree = self.tree
        dt = treeDnD.DropTarget(self.tree, self.OnDrop, self.OnDropFile)
        self.tree.SetDropTarget(dt)
        self.Bind(wx.EVT_TREE_SEL_CHANGED, self.OnSelChanged, self.tree)
        if _env_true('SC4PIM_SKIP_VIEWER'):
            logger.info('Skipping viewer (SC4PIM_SKIP_VIEWER)')
            self.glCanvas = wx.Panel(leftPanel)
            self.s3dviewer = None
            self.atcviewer = None
            self.viewer = None
        else:
            self.glCanvas = MyCanvasBase(leftPanel)
            self.s3dviewer = S3DViewer(None, self.glCanvas)
            self.atcviewer = ATCViewer(None, self.glCanvas)
            ATCProxy.viewer = self.atcviewer
            ATC.viewer = self.atcviewer
            StandardModel.viewer = self.s3dviewer
            SC4Model.viewer = self.s3dviewer
            SC4ModelMesh.viewer = self.s3dviewer
            SC4Model1MeshPerZoom.viewer = self.s3dviewer
            self.viewer = self.atcviewer
        self.cbZoom = wx.ComboBox(leftPanel, -1, viewerZoomBest, style=wx.CB_READONLY)
        choices = [(viewerZoomBest, -1), (viewerZoom1, 0), (viewerZoom2, 1), (viewerZoom3, 2), (viewerZoom4, 3),
                   (viewerZoom5, 4)]
        for ch in choices:
            self.cbZoom.Append(ch[0], ch[1])

        self.cbZoom.SetValue(viewerZoomBest)
        self.Bind(wx.EVT_COMBOBOX, self.EvtComboBoxZoom, self.cbZoom)
        self.cbRotation = wx.ComboBox(leftPanel, -1, viewerRotSouth, style=wx.CB_READONLY)
        choices = [(viewerRotSouth, 0), (viewerRotEast, 1), (viewerRotNorth, 2), (viewerRotWest, 3)]
        for ch in choices:
            self.cbRotation.Append(ch[0], ch[1])

        self.cbRotation.SetValue(viewerRotSouth)
        self.Bind(wx.EVT_COMBOBOX, self.EvtComboBoxRotation, self.cbRotation)
        self.cbStateChoice = wx.ComboBox(leftPanel, -1, viewerModel, style=wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX, self.EvtComboBoxState, self.cbStateChoice)
        self.SetModelStateChoices([])
        self.staticFileName = wx.StaticText(leftPanel, -1, '??')
        self.listSearch = wx.SearchCtrl(rightUpPanel, -1, style=wx.TE_PROCESS_ENTER)
        self.listSearch.SetDescriptiveText(listSearchHint)
        self.listSearch.ShowCancelButton(True)
        self.listSearch.Bind(wx.EVT_TEXT, self.OnListSearch)
        self.listSearch.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self.OnListSearchCancel)
        self.listCount = wx.StaticText(rightUpPanel, -1, '')
        self.listItems = VirtualListCtrl(rightUpPanel)
        self.listItems.on_filter_change = self._update_list_count
        self.listItems.InsertColumn(0, itemColumName)
        self.listItems.InsertColumn(1, itemColumFilename)
        self.listItems.SetColumnWidth(0, self._resource_name_col_width())
        self.listItems.Bind(wx.EVT_LIST_BEGIN_DRAG, self.OnBeginDrag)
        self.listItems.Bind(wx.EVT_LIST_COL_END_DRAG, self.OnListColResize)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemListSelected, self.listItems)
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnItemListSelected, self.listItems)
        self.Bind(wx.EVT_LIST_ITEM_FOCUSED, self.OnItemListSelected, self.listItems)
        self.nb = SC4NoteBook(rightDownPanel, self)
        boxLeft = wx.BoxSizer(wx.VERTICAL)
        treeBar = wx.BoxSizer(wx.HORIZONTAL)
        treeBar.Add(self.treeSearch, 1, wx.ALIGN_CENTRE_VERTICAL | wx.RIGHT, 4)
        treeBar.Add(self.bTreeExpand, 0, wx.ALIGN_CENTRE_VERTICAL | wx.RIGHT, 2)
        treeBar.Add(self.bTreeCollapse, 0, wx.ALIGN_CENTRE_VERTICAL, 0)
        boxLeft.Add(treeBar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        boxLeft.Add(self.tree, 1, wx.ALL | wx.EXPAND, 5)
        boxLeft.Add(self.glCanvas, 0, wx.ALL | wx.CENTRE, 5)
        hsizer = wx.BoxSizer(wx.HORIZONTAL)
        hsizer.Add(self.cbZoom, 0, wx.ALL, 5)
        hsizer.Add(self.cbRotation, 0, wx.ALL, 5)
        hsizer.Add(self.cbStateChoice, 0, wx.ALL, 5)
        boxLeft.Add(hsizer, 0, wx.ALL | wx.EXPAND, 5)
        boxLeft.Add(self.staticFileName, 0, wx.ALL, 5)
        leftPanel.SetSizer(boxLeft)
        boxRight = wx.BoxSizer(wx.VERTICAL)
        listBar = wx.BoxSizer(wx.HORIZONTAL)
        listBar.Add(self.listSearch, 1, wx.ALIGN_CENTRE_VERTICAL | wx.RIGHT, 6)
        listBar.Add(self.listCount, 0, wx.ALIGN_CENTRE_VERTICAL)
        boxRight.Add(listBar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        boxRight.Add(self.listItems, 1, wx.ALL | wx.GROW, 5)
        rightUpPanel.SetSizer(boxRight)
        boxRight = wx.BoxSizer(wx.VERTICAL)
        boxRight.Add(self.nb, 1, wx.ALL | wx.EXPAND, 5)
        rightDownPanel.SetSizer(boxRight)
        splitterHoriz.SplitHorizontally(rightUpPanel, rightDownPanel, int(self._mw_settings['ListSash']))
        splitterHoriz.SetMinimumPaneSize(200)
        splitter.SplitVertically(leftPanel, splitterHoriz, int(self._mw_settings['TreeSash']))
        splitter.SetMinimumPaneSize(300)
        if self._mw_settings.get('Maximized'):
            self.Maximize(True)
        if not _env_true('SC4PIM_SAFE_MODE'):
            self.nb.LoadPics(self.virtualDAT)
        self.Bind(wx.EVT_CLOSE, self.OnCloseWindow)
        if self.PreLoadDatas():
            if _env_true('SC4PIM_SKIP_LOAD'):
                self.bLoaded = True
            else:
                self.LoadDatas()
                self.bLoaded = True
        else:
            self.bLoaded = False
        return

    def OnCloseWindow(self, event):
        dlg = wx.MessageDialog(self, quitMsg, appTitle, wx.YES_NO | wx.YES_DEFAULT | wx.ICON_INFORMATION)
        res = dlg.ShowModal()
        dlg.Destroy()
        if res == wx.ID_NO:
            event.Veto()
            return
        self._save_main_window_state()
        self.Destroy()
        sys.exit(0)

    def _save_main_window_state(self):
        """Persist window geometry, sash positions and column widths."""
        try:
            settings = dict(self._mw_settings)
            settings['Maximized'] = bool(self.IsMaximized())
            if not self.IsMaximized():
                width, height = self.GetSize()
                pos_x, pos_y = self.GetPosition()
                settings.update(Width=int(width), Height=int(height),
                                X=int(pos_x), Y=int(pos_y))
            settings['TreeSash'] = int(self.splitter.GetSashPosition())
            settings['TreeExpanded'] = self.tree.GetExpandedKeys()
            settings['ListSash'] = int(self.splitterHoriz.GetSashPosition())
            if self.listItems.GetColumnCount() >= 3:
                settings['ColName'] = int(self.listItems.GetColumnWidth(0))
                settings['ColTGI'] = int(self.listItems.GetColumnWidth(1))
                settings['ColFile'] = int(self.listItems.GetColumnWidth(2))
            page = self.nb.GetCurrentPage() if hasattr(self, 'nb') else None
            prop_list = getattr(page, 'listProperties', None)
            if prop_list is not None and prop_list.GetColumnCount() >= 4:
                settings['PropColName'] = int(prop_list.GetColumnWidth(0))
                settings['PropColNameValue'] = int(prop_list.GetColumnWidth(1))
                settings['PropColType'] = int(prop_list.GetColumnWidth(2))
                settings['PropColRep'] = int(prop_list.GetColumnWidth(3))
            config.save_main_window(settings)
        except Exception:
            logger.exception('Failed to save main window state')

    def OnConfigure(self, event):
        dlg = ConfigureDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            dlg.OnSave(self)
        dlg.Destroy()

    def OnQuit(self, event):
        self.OnCloseWindow(event)

    def OnDrop(self, data, item):
        if data < 0 or data >= len(self.listItems.list_datas):
            return
        what = self.listItems.list_datas[data]
        category = self.tree.GetItemData(item)
        bbox = (8, 1, 8)
        try:
            bbox = _model_occupant_bbox(what.sc4Model) or bbox
        except Exception:
            logger.exception('Failed to read dropped model bounds for %s', getattr(what, 'name', what))

        self.CreateAnExamplar(what.name, (1523640343, what.sc4Model.GID, what.sc4Model.IID), bbox, category)

    def CreateAnExamplar(self, whatName, whatRTK, bbox, category, fd=None):
        fileNameBase = whatName
        dlg = wx.TextEntryDialog(self, descCreationDialogMsg, descCreationDialogTitle, whatName)
        if dlg.ShowModal() == wx.ID_OK:
            fileNameBase = dlg.GetValue()
            dlg.Destroy()
        else:
            dlg.Destroy()
            return
        init = datetime.datetime(2005, 5, 5, 21, 24, 15)
        today = datetime.datetime.today()
        dt = today - init
        dt = dt.days * 24 * 3600 + dt.seconds
        first = random.randrange(1, 15, 2)
        IID = first * 268435456 + (dt & 268435455)
        buffer = struct.pack('III', 1697917002, self.GID, IID)
        buffer += struct.pack('II', 0, 0)
        if IsAChild(category, 3431971885):
            descFileName = '%s-0x%08x-0x%08x-0x%08x._LooseDesc' % (fileNameBase, 1697917002, self.GID, IID)
        else:
            descFileName = '%s-0x%08x-0x%08x-0x%08x.SC4Desc' % (fileNameBase, 1697917002, self.GID, IID)
        entry = SC4Entry(buffer, 0, os.path.join(self.rootFolder, descFileName))
        props = []
        Height = height = round(bbox[1], 4)
        Width = width = round(clamp_to_tile(bbox[0]), 4)
        Depth = depth = round(clamp_to_tile(bbox[2]), 4)
        LotSizeX = 1
        LotSizeY = 1
        if fd is None:
            fillingDegree = 0.5
        else:
            fillingDegree = fd[0]
        Volume = volume = Height * Width * Depth * fillingDegree
        exemplarName = str(fileNameBase)
        props.append(CreateAPropFromString(self.virtualDAT.properties[32], str(fileNameBase)))
        initcat = category
        cat = category
        variablesName = []
        variables = []
        while 1:
            for variable, what in cat.code:
                if variable not in variablesName:
                    variablesName.append(variable)
                    variables.append((variable, '(' + what + ')'))

            if cat.parent is not None:
                cat = cat.parent
            else:
                break

        del variablesName
        propCreated = []
        while 1:
            for prop2CreatID in category.evalProperties.keys():
                if prop2CreatID in propCreated:
                    pass
                else:
                    propCreated.append(prop2CreatID)
                    codetxt = category.evalProperties[prop2CreatID]
                    try:
                        while 1:
                            codetxt2 = codetxt
                            for variable, what in variables:
                                codetxt = codetxt.replace(variable, what)

                            if codetxt == codetxt2:
                                break

                        values = eval(codetxt)
                    except Exception:
                        logger.exception('Error evaluating category formula: %s\n  variables: %s',
                                         codetxt, variables)
                        raise

                    prop2CreatValue = []
                    if not isinstance(values, tuple):
                        values = (
                            values,)
                    for v in values:
                        if self.virtualDAT.properties[prop2CreatID].Type == 'Float32':
                            prop2CreatValue.append(str(v))
                        elif self.virtualDAT.properties[prop2CreatID].Type == 'Sint64':
                            prop2CreatValue.append(hex2str(v, 64))
                        elif self.virtualDAT.properties[prop2CreatID].Type[-2:] == '32':
                            prop2CreatValue.append(hex2str(v, 32))
                        else:
                            prop2CreatValue.append(hex2str(v, 8))

                    props.append(
                        CreateAPropFromString(self.virtualDAT.properties[prop2CreatID], ','.join(prop2CreatValue)))

            for prop2CreatID in category.programProperties.keys():
                if prop2CreatID in propCreated:
                    pass
                else:
                    propCreated.append(prop2CreatID)
                    prop2CreatValue = category.programProperties[prop2CreatID]
                    props.append(CreateAPropFromString(self.virtualDAT.properties[prop2CreatID],
                                                       str(prop2CreatValue.replace('IID', '0x%08X' % IID).replace('GID',
                                                                                                                  '0x%08X' % self.GID).replace(
                                                           'exemplarName', exemplarName))))

            for prop2CreatID in category.setProperties.keys():
                if prop2CreatID in propCreated:
                    pass
                else:
                    propCreated.append(prop2CreatID)
                    prop2CreatValue = category.setProperties[prop2CreatID]
                    props.append(CreateAPropFromString(self.virtualDAT.properties[prop2CreatID], str(prop2CreatValue)))

            for prop2CreatID in category.factorProperties.keys():
                if prop2CreatID in propCreated:
                    pass
                else:
                    propCreated.append(prop2CreatID)
                    factors = category.factorProperties[prop2CreatID]
                    prop2CreatValue = []
                    for factor in factors:
                        v = factor * volume
                        v = Clamp(self.virtualDAT.properties[prop2CreatID], v)
                        if self.virtualDAT.properties[prop2CreatID].Type == 'Float32':
                            prop2CreatValue.append(str(v))
                        elif self.virtualDAT.properties[prop2CreatID].Type == 'Sint64':
                            prop2CreatValue.append(hex2str(v, 64))
                        elif self.virtualDAT.properties[prop2CreatID].Type[:-2] == 32:
                            prop2CreatValue.append(hex2str(v, 32))
                        else:
                            prop2CreatValue.append(hex2str(v, 8))

                    props.append(
                        CreateAPropFromString(self.virtualDAT.properties[prop2CreatID], ','.join(prop2CreatValue)))

            for prop2CreatID in category.pairedFactorProperties.keys():
                if prop2CreatID in propCreated:
                    pass
                else:
                    propCreated.append(prop2CreatID)
                    factors = category.pairedFactorProperties[prop2CreatID]
                    prop2CreatValue = []
                    for factor in factors:
                        v = factor[1] * volume
                        v = Clamp(self.virtualDAT.properties[prop2CreatID], v)
                        if self.virtualDAT.properties[prop2CreatID].Type == 'Float32':
                            prop2CreatValue.append(factor[0])
                            prop2CreatValue.append(str(v))
                        elif self.virtualDAT.properties[prop2CreatID].Type == 'Sint64':
                            prop2CreatValue.append(factor[0])
                            prop2CreatValue.append(hex2str(v, 64))
                        elif self.virtualDAT.properties[prop2CreatID].Type[:-2] == 32:
                            prop2CreatValue.append(factor[0])
                            prop2CreatValue.append(hex2str(v, 32))
                        else:
                            prop2CreatValue.append(factor[0])
                            prop2CreatValue.append(hex2str(v, 8))

                    props.append(
                        CreateAPropFromString(self.virtualDAT.properties[prop2CreatID], ','.join(prop2CreatValue)))

            if category.parent is not None:
                category = category.parent
            else:
                break

        if 662775824 not in propCreated:
            props.append(CreateAProp(self.virtualDAT.properties[662775824], (Width, Height, Depth)))
        try:
            whatRTK = tuple(whatRTK)
        except Exception:
            logger.error('Failed to convert whatRTK: %r', whatRTK)
            raise

        if whatRTK in self.virtualDAT.standardModelsDict:
            if 662775841 not in propCreated:
                props.append(CreateAProp(self.virtualDAT.properties[662775841], whatRTK))
        elif 662775840 not in propCreated:
            props.append(CreateAProp(self.virtualDAT.properties[662775840], whatRTK))
        props.sort(key=functools.cmp_to_key(lambda x, y: basic_cmp(x[2:2 + 8], y[2:2 + 8])))
        props = [p for p in props if str(p[2:2 + 8].upper()) not in initcat.removeProperties.values()]
        buffer = 'EQZT1###\r\n' + 'ParentCohort=Key:{0x00000000,0x00000000,0x00000000}\r\n' + 'PropCount=0x%08x\r\n' % len(
            props)
        buffer += '\r\n'.join(props)
        entry.content = entry.rawContent = buffer
        exemplar = SC4Exemplar(entry, self.virtualDAT)
        exemplar.entry = entry
        entry.exemplar = exemplar
        data = descriptor = BuildingDesc(entry)
        self.FillPropList(data, False)
        entries = [entry]
        if exemplar.GetProp(2319542937) is not None:
            tgi = exemplar.GetProp(2319542937)
            if tgi != [0, 0, 0]:
                txt = u'Name of the building' + exemplarName
                encoded_txt = encode_sc4_text(txt)
                buffer = struct.pack('III', tgi[0], tgi[1], tgi[2])
                buffer += struct.pack('II', 0, 4 + len(encoded_txt))
                entry2 = SC4Entry(buffer, 0, os.path.join(self.rootFolder, descFileName))
                buffer = struct.pack('H', len(txt))
                buffer += struct.pack('H', 4096)
                buffer += encoded_txt
                entry2.content = entry2.rawContent = buffer
                entries.append(entry2)
        if exemplar.GetProp(3393284789) is not None:
            tgi = exemplar.GetProp(3393284789)
            if tgi != [0, 0, 0]:
                txt = u'Description of the building' + v
                encoded_txt = encode_sc4_text(txt)
                buffer = struct.pack('III', tgi[0], tgi[1], tgi[2])
                buffer += struct.pack('II', 0, 4 + len(encoded_txt))
                entry2 = SC4Entry(buffer, 0, os.path.join(self.rootFolder, descFileName))
                buffer = struct.pack('H', len(txt))
                buffer += struct.pack('H', 4096)
                buffer += encoded_txt
                entry2.content = entry2.rawContent = buffer
                entries.append(entry2)
        entry.exemplar.Maj()
        WriteADat(entry.fileName, entries, None, True)
        self.virtualDAT.addEntries(entries, None, False, False)
        Categorize(self.virtualDAT.rootCategory, descriptor)
        desc = descriptor
        return descriptor

    def OnDropFile(self, filenames, item):
        return None

    def OnBeginDrag(self, event):
        idx = event.GetIndex()
        # idx is a row in the (possibly filtered) displayed list; OnDrop
        # resolves it the same way.
        if not isinstance(self.listItemsCat, list) or idx < 0 or idx >= len(self.listItems.list_datas):
            return
        what = self.listItems.list_datas[idx]
        bOk = False
        if what.__class__ == StandardModel:
            bOk = True
        if bOk:
            def DoDragDrop():
                txt = what.name
                dd = treeDnD.DropData()
                dd.setObject(idx)
                comp = wx.DataObjectComposite()
                comp.Add(dd)
                dropSource = wx.DropSource(self)
                dropSource.SetData(comp)
                result = dropSource.DoDragDrop(wx.Drag_AllowMove)

            wx.CallAfter(DoDragDrop)

    def PreLoadDatas(self):
        global _preload_config_result
        if _preload_config_result is not None:
            return _preload_config_result
        logger.debug('Preloading startup configuration')
        self.pathToScan = []
        registry_folder = _read_sc4_install_folder_from_registry()
        self.gameFolders = _existing_unique_paths([registry_folder] + _common_sc4_install_folders())
        self.maxisFolder = self.gameFolders[0] if self.gameFolders else ''
        self.maxisPluginsFolder = os.path.join(self.maxisFolder, 'Plugins') if self.maxisFolder else ''
        self.mydocs = wx.StandardPaths.Get().GetDocumentsDir()
        default_root = os.path.join(self.mydocs, 'SimCity 4', 'Plugins')
        self.rootFolder = os.path.normpath(config.load_user_plugins_root(default_root))
        logger.debug('Showing configuration dialog')
        dlg = ConfigureDialog(parent=self)
        if dlg.ShowModal() == wx.ID_OK:
            dlg.OnSave(self)
            dlg.Destroy()
            _preload_config_result = True
            logger.debug('Startup configuration accepted')
            _exit_after('preload:ok')
            return _preload_config_result
        dlg.Destroy()
        _preload_config_result = False
        logger.debug('Startup configuration cancelled')
        _exit_after('preload:cancel')
        return _preload_config_result

    def LoadDatas(self):
        """Kick off data loading on a background thread and return immediately.

        DBPF files are parsed in parallel by a worker thread pool; the merge,
        finalize and tree-population steps are marshalled back onto the GUI
        thread. The progress dialog stays animated throughout.
        """
        logger.debug('Loading application data')
        safe_mode = _env_true('SC4PIM_SAFE_MODE')
        if safe_mode:
            logger.debug('Safe mode enabled')
        wx.BeginBusyCursor()
        if _env_true('SC4PIM_SKIP_DAT_SCAN'):
            self.pathToScan = []
        try:
            self.pathToScan = config.load_folders()
        except Exception:
            logger.exception('Could not load plugin scan folders from config.toml')
            self.pathToScan = []
        logger.debug('Configured plugin scan folders: %d', len(self.pathToScan))

        # Build the ordered job list on the GUI thread (registry access etc.).
        # Each job is ('file', name, bStandard) or ('folder', name, recurse).
        jobs = [('file', str(asset_path('dbpf', 'cohorts.dat')), True)]
        for path, recurse in self.pathToScan:
            if path == self.maxisFolder:
                logger.debug('Queuing Maxis install data from %s', self.maxisFolder)
                for name in ('simcity_1.dat', 'simcity_2.dat', 'simcity_3.dat',
                             'simcity_4.dat', 'simcity_5.dat', 'ep1.dat'):
                    jobs.append(('file', os.path.join(self.maxisFolder, name), False))
                jobs.append(('file', os.path.join(self.maxisFolder,
                                                  self._maxis_locale_file()), False))
            else:
                normalised = os.path.normcase(os.path.normpath(path))
                plugins_root = os.path.normcase(os.path.normpath(self.rootFolder))
                if normalised == plugins_root:
                    recurse = False
                jobs.append(('folder', path, recurse))

        logger.debug('Showing data loading progress dialog')
        dlg = ProcessDlg(self, loadingDialogMsg)
        dlg.Show()
        dlg.StartPulse()
        start = time.time()
        logger.debug('Starting background loader thread')
        loader = threading.Thread(target=self._load_worker,
                                  args=(dlg, jobs, start, safe_mode),
                                  name='sc4-loader-main', daemon=True)
        loader.start()

    def _maxis_locale_file(self):
        """Return the relative path of the Maxis locale DAT for the OS language."""
        try:
            if HAS_WIN32:
                maxisKey = win32api.RegOpenKeyEx(win32con.HKEY_LOCAL_MACHINE,
                                                 'SOFTWARE\\Maxis\\SimCity 4\\1.0')
                language = win32api.RegQueryValueEx(maxisKey, 'Language')[0]
            else:
                language = 1  # Default to English
        except Exception:
            language = 1  # Default to English if registry read fails
        paths = {1: 'English', 2: 'French', 3: 'German', 4: 'Italian', 5: 'Spanish',
                 6: 'Swedish', 7: 'Finnish', 8: 'Dutch', 9: 'Danish', 10: 'Portgese',
                 11: 'Czech', 12: 'Hebrew', 13: 'Greek', 14: 'Japanese', 15: 'Korean',
                 16: 'Russian', 17: 'SChinese', 18: 'TChinese', 19: 'UKEnglsh',
                 20: 'Polish', 21: 'Thai', 22: 'Norwgian'}
        return os.path.join(paths.get(language, 'English'), 'simcitylocale.dat')

    def _load_worker(self, dlg, jobs, start, safe_mode):
        """Background thread: expand folders, parse DBPF files, merge entries."""
        try:
            file_list = []  # ordered (fileName, bStandard)
            for job in jobs:
                if job[0] == 'file':
                    _, fileName, bStandard = job
                    if os.path.exists(fileName):
                        file_list.append((fileName, bStandard))
                    else:
                        logger.debug('Skipping missing file %s', fileName)
                else:
                    _, folderName, recurse = job
                    dlg.SetStatus('Scanning folder: %s' % folderName,
                                  'Building file list...')
                    try:
                        for f in self.virtualDAT.gather_container_files(folderName, recurse):
                            file_list.append((f, False))
                    except Exception:
                        logger.warning('Could not scan folder %s', folderName, exc_info=True)

            def _progress(done, total, fileName):
                if done % 15 == 0 or done == total:
                    dlg.SetStatus('Loading plugins  (%d / %d files)' % (done, total),
                                  os.path.basename(fileName))

            self.virtualDAT.load_files_parallel(file_list, progress_cb=_progress)
        except Exception:
            logger.exception('Background loader thread failed')
        finally:
            # Hand finalization back to the GUI thread regardless of outcome.
            wx.CallAfter(self._load_finalize, dlg, start, safe_mode)

    def _load_finalize(self, dlg, start, safe_mode):
        """GUI thread: finalize loaded data, build the tree, tear down dialog."""
        try:
            dlg.SetStatus('Finalizing data...', '')
            logger.debug('Finalizing loaded data')
            if not _env_true('SC4PIM_SKIP_FINALIZE'):
                self.virtualDAT.Finalize(dlg)
            else:
                logger.debug('Skipping data finalization')
            logger.debug('Loading texture image lists')
            if not safe_mode and not _env_true('SC4PIM_SKIP_TEXTURE_IMAGES'):
                texLoader = ImageListLoaderTexture(self.virtualDAT)
                texLoader.Start()
            else:
                logger.debug('Skipping texture image loading')
            if self.virtualDAT.missing_pictures and len(self.virtualDAT.missing_pictures) > 0:
                if safe_mode or _env_true('SC4PIM_SKIP_MISSING_PICS'):
                    logger.debug('Skipping missing picture generation')
                else:
                    logger.debug('Generating %d missing model pictures',
                                 len(self.virtualDAT.missing_pictures))
                    dlg2 = ImageDBBuilder(self, -1, imageDbBuilderTitle)
                    dlg2.Show()
                    for data in self.virtualDAT.missing_pictures:
                        dlg2.Draw(data)
                        dlg.Increment()

                    dlg2.Destroy()
            logger.debug('Loading prop image list')
            if not safe_mode and not _env_true('SC4PIM_SKIP_PROP_IMAGES'):
                propLoader = ImageListLoaderProps(self.virtualDAT)
                propLoader.Start()
            else:
                logger.debug('Skipping prop image loading')
            self.tree.RefreshCounts()
            self.tree.ApplyExpandedKeys(self._saved_tree_expanded)
            self.tree.EnsureVisible(self.tree.standard_models_item)
            if not _env_true('SC4PIM_SKIP_TREE_SELECT'):
                wx.CallAfter(self.tree.SelectItem, self.tree.standard_models_item)
            else:
                logger.debug('Skipping initial tree selection')
            self.tree.EnsureVisible(self.tree.root)
            InfoEx()
            if not safe_mode and not _env_true('SC4PIM_SKIP_REFRESH_TIMER'):
                self.t2 = wx.CallLater(500, self.RefreshEvent)
            logger.debug(
                'LoadDatas completed in %.3fs with %d entries, %d standard models, %d textures',
                time.time() - start,
                len(self.virtualDAT.allEntries),
                len(self.virtualDAT.standardModels),
                len(self.virtualDAT.allTextures))
        except Exception:
            logger.exception('Data finalization failed')
        finally:
            dlg.StopPulse()
            wx.EndBusyCursor()
            dlg.Destroy()
            _exit_after('loaddatas:done')

    def RefreshEvent(self):
        if not hasattr(self, 'viewer') or not hasattr(self.viewer, 's3d_mesh'):
            return
        if self.currentModel is not None:
            zoom = self.cbZoom.GetClientData(self.cbZoom.GetSelection())
            rot = self.cbRotation.GetClientData(self.cbRotation.GetSelection())
            if zoom == -1:
                nZoom = 0
            else:
                nZoom = zoom
            if self.currentModel.__class__ == ATC:
                self.currentModel.draw(self.viewer, self.staticFileName, zoom, rot)
            else:
                try:
                    state = self.cbStateChoice.GetClientData(self.cbStateChoice.GetSelection())
                except Exception:
                    state = 0

                self.currentModel.draw(self.viewer, self.staticFileName, zoom, rot, state)
            self.t2.Restart(100)
            return
        self.t2.Restart(500)
        return

    def EvtComboBoxState(self, evt):
        zoom = self.cbZoom.GetClientData(self.cbZoom.GetSelection())
        rot = self.cbRotation.GetClientData(self.cbRotation.GetSelection())
        try:
            state = self.cbStateChoice.GetClientData(self.cbStateChoice.GetSelection())
        except Exception:
            state = 0

        if zoom == -1:
            nZoom = 0
        else:
            nZoom = zoom
        if self.currentModel:
            self.currentModel.draw(self.viewer, self.staticFileName, zoom, rot, state)

    def EvtComboBoxRotation(self, evt):
        zoom = self.cbZoom.GetClientData(self.cbZoom.GetSelection())
        rot = self.cbRotation.GetClientData(self.cbRotation.GetSelection())
        try:
            state = self.cbStateChoice.GetClientData(self.cbStateChoice.GetSelection())
        except Exception:
            state = 0

        if zoom == -1:
            nZoom = 0
        else:
            nZoom = zoom
        if self.currentModel:
            self.currentModel.draw(self.viewer, self.staticFileName, zoom, rot, state)

    def EvtComboBoxZoom(self, evt):
        zoom = self.cbZoom.GetClientData(self.cbZoom.GetSelection())
        rot = self.cbRotation.GetClientData(self.cbRotation.GetSelection())
        try:
            state = self.cbStateChoice.GetClientData(self.cbStateChoice.GetSelection())
        except Exception:
            state = 0

        if zoom == -1:
            nZoom = 0
        else:
            nZoom = zoom
        if self.currentModel:
            self.currentModel.draw(self.viewer, self.staticFileName, zoom, rot, state)

    def RefreshItemsList(self):
        if self.backupCat is not None:
            self.FillItemsList(self.tree.virtual_dat.categories[self.backupCat])
        return

    def _resource_name_col_width(self):
        return max(int(self._mw_settings.get('ColName', 240)), 240)

    def FillItemsList(self, cat):
        self.backupCat = cat.ID
        self.listItemsCat = cat
        if self.listItems.GetColumnCount() == 4:
            self.listItems.DeleteAllItems()
        else:
            self.listItems.ClearAll()
            self.listItems.InsertColumn(0, itemColumName)
            self.listItems.InsertColumn(1, itemColumTGI)
            self.listItems.InsertColumn(2, itemColumFilename)
            self.listItems.InsertColumn(3, itemColumDate)
            self.listItems.SetColumnWidth(0, self._resource_name_col_width())
            self.listItems.SetColumnWidth(1, int(self._mw_settings['ColTGI']))
            self.listItems.SetColumnWidth(2, int(self._mw_settings['ColFile']))
        self.listItems.columns = ['name', 'tgi', 'file', 'date']
        self.listItems.SetThumbnailProvider(None)
        cat.descriptors.sort(key=functools.cmp_to_key(lambda d1, d2: basic_cmp(d2.exemplar.entry.dateUpdated, d1.exemplar.entry.dateUpdated)))
        self.listItems.SetData(cat.descriptors)

    def FillItemsListModel(self, what):
        self.backupCat = None
        self.listItemsCat = what
        if self.listItems.GetColumnCount() == 2:
            self.listItems.DeleteAllItems()
        else:
            self.listItems.ClearAll()
            self.listItems.InsertColumn(0, itemColumName)
            self.listItems.InsertColumn(1, itemColumFilename)
        self.listItems.SetColumnWidth(0, self._resource_name_col_width())
        self.listItems.columns = ['name', 'file']
        # Only the BAT Models section has rendered thumbnails in the image DB;
        # other model lists would just show empty space, so skip thumbnails.
        is_bat_models = what is self.virtualDAT.standardModels
        self.listItems.SetThumbnailProvider(self._model_thumb_path if is_bat_models else None)
        self.listItems.SetData(what)
        return

    def _update_list_count(self):
        """Refresh the '<shown> of <total>' label next to the list filter."""
        shown = len(self.listItems.list_datas)
        total = len(self.listItems.all_datas)
        if shown == total:
            self.listCount.SetLabel(listCountAll % total)
        else:
            self.listCount.SetLabel(listFilterCount % (shown, total))
        sizer = self.listCount.GetContainingSizer()
        if sizer is not None:
            sizer.Layout()

    def OnListColResize(self, event):
        """Capture a user column-drag so it survives a column rebuild + close."""
        event.Skip()
        wx.CallAfter(self._capture_list_col_widths)

    def _capture_list_col_widths(self):
        count = self.listItems.GetColumnCount()
        if count >= 1:
            self._mw_settings['ColName'] = int(self.listItems.GetColumnWidth(0))
        if count >= 3:
            self._mw_settings['ColTGI'] = int(self.listItems.GetColumnWidth(1))
            self._mw_settings['ColFile'] = int(self.listItems.GetColumnWidth(2))

    def OnListSearch(self, event):
        self.listItems.SetFilter(self.listSearch.GetValue())

    def OnListSearchCancel(self, event):
        self.listSearch.SetValue('')
        self.listItems.SetFocus()

    @staticmethod
    def _model_thumb_path(data):
        """Thumbnail JPG path for a model row in the resource list, or None."""
        model = getattr(data, 'sc4Model', None)
        if model is None:
            return None
        try:
            return image_db_path('%s-%s.jpg' % (hex2str(model.GID), hex2str(model.IID)))
        except Exception:
            return None

    def SetModelStateChoices(self, choices):
        self.cbStateChoice.Clear()
        if choices:
            for label, data in choices:
                self.cbStateChoice.Append(label, data)
            self.cbStateChoice.SetSelection(0)
        else:
            self.cbStateChoice.Append(viewerModel, 0)
            self.cbStateChoice.SetSelection(0)
        return

    def FillPropList(self, descriptor, bAdd):
        exemplar = descriptor.exemplar
        rkt4 = exemplar.GetProp(662775844)
        if rkt4 is not None:
            choices = []
            for z in range(len(rkt4) // 8):
                choices.append(('Model #%d' % z, z))

            self.SetModelStateChoices(choices)
        else:
            self.SetModelStateChoices([])
        self.nb.AddNewDesc(descriptor, self.virtualDAT, bAdd)
        return

    def OnItemListSelected(self, event):
        item = event.GetItem()
        idx = event.GetIndex()
        if self.viewer is not None and self.viewer.s3d_mesh is not None:
            self.viewer.s3d_mesh.free_3d(self.viewer.s3d_textures_holder)
            self.viewer.s3d_mesh = None
            self.viewer.refresh(False)
        # The list may be filtered, so resolve the row through the displayed
        # list_datas rather than indexing the (unfiltered) category.
        if idx < 0 or idx >= len(self.listItems.list_datas):
            return
        row = self.listItems.list_datas[idx]
        if self.listItemsCat is not None:
            if self.listItemsCat.__class__.__name__ == 'list':
                self.SetModelStateChoices([])
                data = row.sc4Model
                zoom = self.cbZoom.GetClientData(self.cbZoom.GetSelection())
                rot = self.cbRotation.GetClientData(self.cbRotation.GetSelection())
                self.viewer = data.__class__.viewer
                self.viewer.init_gl()
                self.viewer.s3d_mesh = None
                self.viewer.refresh(False)
                self.staticFileName.SetLabel(row.fileName)
                data.draw(self.viewer, self.staticFileName, zoom, rot)
                self.currentModel = data
            elif self.listItemsCat.__class__.__name__ == 'DictWrapper':
                self.FillPropList(row, not wx.GetKeyState(wx.WXK_CONTROL))
        return

    def OnTreeSearch(self, event):
        self.tree.FindCategory(self.treeSearch.GetValue(), after_selection=False)

    def OnTreeSearchNext(self, event):
        self.tree.FindCategory(self.treeSearch.GetValue(), after_selection=True)

    def OnTreeSearchCancel(self, event):
        self.treeSearch.SetValue('')
        self.tree.SetFocus()

    def OnTreeCollapseAll(self, event):
        self.tree.CollapseAll()
        self.tree.Expand(self.tree.root)

    def OnSelChanged(self, event):
        logger.debug('Tree selection changed: %s', event)
        item = event.GetItem()
        tree = event.GetEventObject()
        try:
            data = tree.GetItemData(item)
        except Exception:
            data = None

        # Navigating to a *different* node starts with a clean (unfiltered)
        # list. A re-selection of the same node -- e.g. the UnselectAll/restore
        # that drag-and-drop performs -- must keep the active filter so the
        # dropped row still resolves to the model the user was dragging.
        if data is not None and data is not self._current_list_node:
            self.listSearch.ChangeValue('')
            self.listItems.filter_text = ''
        if data is not None:
            self._current_list_node = data
        if data:
            if data.__class__.__name__ == 'list':
                self.FillItemsListModel(data)
                if self.viewer is not None and self.viewer.s3d_mesh is not None:
                    self.viewer.s3d_mesh.free_3d(self.viewer.s3d_textures_holder)
                    self.viewer.s3d_mesh = None
                    self.viewer.refresh(False)
            if data.__class__.__name__ == 'DictWrapper':
                self.FillItemsList(data)
                if self.viewer is not None and self.viewer.s3d_mesh is not None:
                    self.viewer.s3d_mesh.free_3d(self.viewer.s3d_textures_holder)
                    self.viewer.s3d_mesh = None
                    self.viewer.refresh(False)
        else:
            self.listItemsCat = None
            self.listItems.SetData([])
            if self.viewer is not None and self.viewer.s3d_mesh is not None:
                self.viewer.s3d_mesh.free_3d(self.viewer.s3d_textures_holder)
                self.viewer.s3d_mesh = None
                self.viewer.refresh(False)
            self.currentModel = None
        return


class SplashScreen(wx.adv.SplashScreen):

    def __init__(self):
        bmp = wx.Image(str(asset_path('other', 'splash.jpg')), wx.BITMAP_TYPE_JPEG).ConvertToBitmap()
        wx.adv.SplashScreen.__init__(self, bmp, wx.adv.SPLASH_CENTRE_ON_SCREEN | wx.adv.SPLASH_TIMEOUT, 500, None, -1)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self._show_main_called = False
        return

    def OnClose(self, evt):
        evt.Skip()
        self.Hide()
        # Build the main window *after* this handler returns. Doing it inline
        # opens a modal dialog whose nested event loop lets wx destroy this
        # splash screen while OnClose is still on the stack -> access violation.
        wx.CallAfter(self.ShowMain)

    def ShowMain(self):
        if self._show_main_called:
            return
        self._show_main_called = True
        frame = MainFrame()
        if frame.bLoaded:
            frame.Show()
        else:
            frame.Destroy()


class App(wx.App):

    def OnInit(self):
        splash = SplashScreen()
        splash.Show()
        return True

    def OnExceptionInMainLoop(self):
        logger.exception('Unhandled exception in wx main loop')
        return True


def main() -> None:
    configure_logging()
    logger.info('SC4PIM-X %s starting', get_version())
    _enable_faulthandler()
    image_db = image_db_dir()
    image_db_large = image_db_dir(large=True)
    image_db.mkdir(parents=True, exist_ok=True)
    image_db_large.mkdir(parents=True, exist_ok=True)

    blank = Image.new('RGB', (64, 64), 8355711)
    blank.save(image_db / '0xbadb57f1-0x00000000.jpg')
    blank.save(image_db / '0x00000000-0x00000000.jpg')
    blank = Image.new('RGB', (128, 128), 8355711)
    blank.save(image_db_large / '0xbadb57f1-0x00000000.jpg')
    blank.save(image_db_large / '0x00000000-0x00000000.jpg')
    prog = App()
    prog.MainLoop()


if __name__ == "__main__":
    main()
