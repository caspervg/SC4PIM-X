import logging
import os
import time
import xml.dom.minidom
from concurrent.futures import ThreadPoolExecutor

import wx

from .dat_cache import DatFileCache, serialize_entries
from .paths import data_file_path, image_db_path
from .SC4DataFunctions import (
    DuplicateProp,
    FinalizeCategory,
    ReadStageVsDensity,
    ReadZoning,
    readCategoryDef,
    readPropertyDef,
)
from .SC4DatTools import BuildSortedFilesList, DatFile, hex2str

logger = logging.getLogger(__name__)


class VirtualDat(object):
    this = None

    def __init__(self, visual_tree):
        self.missing_pictures = None
        VirtualDat.this = self
        self.ilOver = wx.ImageList(64, 64, True)
        self.ilBase = wx.ImageList(64, 64, True)
        self.ilStandardModels = wx.ImageList(64, 64, True)
        self.ilIcon = wx.ImageList(44 * 4, 44, True)
        image = wx.Image(44 * 4, 44)
        self.ilIcon.Add(image.ConvertToBitmap())
        self.baseTexEntries = []
        self.overTexEntries = []
        self.baseTexEntriesDict = {}
        self.overTexEntriesDict = {}
        self.s3dEntries = {}
        self.allTextures = []
        self.allEntries = []
        self.cohorts = []
        self.TGIIndex = {}
        self.tree = visual_tree
        self.properties = {}
        self.categories = {}
        self.standardModels = []
        self.standardModelsDict = {}
        self.otherModels = []
        self.otherModelsDict = {}
        self.atcs = []
        self.atcsDict = {}
        self.rootCategory = None
        self.lotStages = {}
        self.baseTex = {}
        self.zoning = {}
        self.MaxSlopeBeforeLotFoundation = '90'
        self.MaxSlopeAllowed = '90'
        # Pre-stat cache: path -> (mtime_ns, size). Populated during
        # gather_container_files (where os.scandir already has the metadata)
        # so the DBPF parse cache can validate freshness without re-stat'ing
        # every file -- a measurable win on OneDrive/AV-shimmed filesystems
        # where each metadata syscall costs tens of ms.
        self._scan_stat_cache: dict = {}
        self.ReadProperties()
        return

    def ComputeZoning(self, purpose, height):
        x = [v for v in self.zoning.keys() if v[0] == purpose]
        res = [self.zoning[v][0] for v in x if height < v[1]]
        res.sort()
        return res

    def FindBuildingFromID(self, buildingID):
        if buildingID in self.categories:
            bOk = False
            for desc in self.categories[buildingID].descriptors:
                if desc.exemplar.GetProp(16)[0] == 2 and desc.exemplar.entry.tgi[0] == 1697917002:
                    return desc

        possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == buildingID,
                           self.categories[210746197].descriptors)
        for desc in possibles:
            return desc

    def FindBuildingFromLot(self, lotExamplar):
        buildingID = None
        for lcp in range(2297284864, 2297286144):
            values = lotExamplar.GetProp(lcp)
            if values is None:
                return
            if values[0] == 0:
                buildingID = values[12]
                break

        if buildingID is None:
            return
        return self.FindBuildingFromID(buildingID)

    def FindLotFromBuilding(self, buildingExamplar):
        if buildingExamplar.GetProp(662775920) is not None:
            possibles = list(buildingExamplar.GetProp(662775920)) + [buildingExamplar.entry.tgi[2]]
        else:
            possibles = [
                buildingExamplar.entry.tgi[2]]

        def UseThisIID(desc):
            for lcp in range(2297284864, 2297286143):
                values = desc.exemplar.GetProp(lcp)
                if values is None:
                    return False
                if values[0] == 0 and values[12] in possibles:
                    return True

            return False

        descs = list(filter(UseThisIID, self.categories[210091300].descriptors))
        if len(descs) > 0:
            return descs[0]
        return

    def FindAllLotsFromBuilding(self, buildingExamplar):
        if buildingExamplar.GetProp(662775920) is not None:
            possibles = list(buildingExamplar.GetProp(662775920)) + [buildingExamplar.entry.tgi[2]]
        else:
            possibles = [
                buildingExamplar.entry.tgi[2]]

        def UseThisIID(desc):
            for lcp in range(2297284864, 2297286143):
                values = desc.exemplar.GetProp(lcp)
                if values is None:
                    return False
                if values[0] == 0 and values[12] in possibles:
                    return True

            return False

        return list(filter(UseThisIID, self.categories[210091300].descriptors))

    def FindPropFromID(self, propID):
        if propID in self.categories:
            bOk = False
            for desc in self.categories[propID].descriptors:
                if desc.exemplar.GetProp(16)[0] == 30 and desc.exemplar.entry.tgi[0] == 1697917002:
                    return desc

        possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == propID, self.categories[210746660].descriptors)
        for desc in possibles:
            return desc

    def GetAllEntriesFromFile(self, fileName):
        return [entry for entry in self.allEntries if entry.fileName == fileName]

    def ReadProperties(self):
        propertiesXML = xml.dom.minidom.parse(str(data_file_path('new_properties.xml')))
        for node in propertiesXML.documentElement.childNodes:
            if node.nodeType == node.ELEMENT_NODE and node.tagName == 'PROPERTIES':
                for subNode in node.childNodes:
                    if subNode.nodeType == subNode.ELEMENT_NODE and subNode.tagName == 'PROPERTY':
                        prop = readPropertyDef(subNode)
                        self.properties[prop.ID] = prop

            if node.nodeType == node.ELEMENT_NODE and node.tagName == 'CATEGORIES':
                for subNode in node.childNodes:
                    if subNode.nodeType == subNode.ELEMENT_NODE and subNode.tagName == 'CATEGORY':
                        category = readCategoryDef(subNode)
                        if category.parentID != 0:
                            category.parent = self.categories[category.parentID]
                            if category.imgName is None or category.imgName == '':
                                category.imgName = category.parent.imgName
                                category.imgIdx = category.parent.imgIdx
                            self.categories[category.parentID].childs.append(category)
                        else:
                            self.rootCategory = category
                        self.categories[category.ID] = category

            if node.nodeType == node.ELEMENT_NODE and node.tagName == 'LOTCREATION':
                for subNode in node.childNodes:
                    if subNode.nodeType == subNode.ELEMENT_NODE and subNode.tagName == 'STAGEvsDENSITY':
                        stagevsdensity, purpose, wealth, baseTex = ReadStageVsDensity(subNode)
                        self.lotStages[purpose, wealth] = stagevsdensity
                        self.baseTex[purpose, wealth] = baseTex
                    if subNode.nodeType == subNode.ELEMENT_NODE and subNode.tagName == 'MaxSlopeBeforeLotFoundation':
                        self.MaxSlopeBeforeLotFoundation = str(subNode.getAttribute('value'))
                    if subNode.nodeType == subNode.ELEMENT_NODE and subNode.tagName == 'MaxSlopeAllowed':
                        self.MaxSlopeAllowed = str(subNode.getAttribute('value'))
                    if subNode.nodeType == subNode.ELEMENT_NODE and subNode.tagName == 'ZONING':
                        purpose, value, stage, height = ReadZoning(subNode)
                        try:
                            self.zoning[purpose, height].append(value)
                        except KeyError:
                            self.zoning[purpose, height] = [
                                value]

        fProp = self.properties[2297284864]
        for lcp in range(2297284865, 2297286144):
            self.properties[lcp] = DuplicateProp(fProp, lcp)

        return

    def addFolder(self, dlg, folderName, bRecurse=True, bStandard=False):
        logger.debug('Scanning folder %s (recurse=%s, standard=%s)', folderName, bool(bRecurse), bool(bStandard))
        can_report = dlg is not None and hasattr(dlg, 'SetStatus')
        if can_report:
            dlg.SetStatus('Scanning folder: %s' % folderName, 'Building file list...')
        filesName = BuildSortedFilesList(folderName, bRecurse)
        total = len(filesName)
        logger.debug('Found %d candidate files in %s', total, folderName)
        folderLabel = os.path.basename(folderName.rstrip('\\/')) or folderName
        for index, fileName in enumerate(filesName, 1):
            # Skip non-DBPF/SC4 container files early to avoid unnecessary reads.
            if not self._is_sc4_container(fileName):
                continue
            # Refresh the progress text periodically so large scans look alive.
            if can_report and (index % 10 == 0 or index == total):
                dlg.SetStatus('Loading %s  (%d / %d files)' % (folderLabel, index, total),
                              os.path.basename(fileName))
            try:
                self.addFile(dlg, fileName, bStandard)
            except Exception:
                # A single corrupt lot/model must not abort the whole scan.
                logger.warning('Skipping unreadable file %s', fileName, exc_info=True)
                if dlg:
                    dlg.LogError('Skipped unreadable file : %s' % fileName)

    def gather_container_files(self, folderName, bRecurse=True):
        """Return the SC4/DBPF container files under *folderName*, in load order.

        Used by the threaded loader to build a flat work list before parsing
        files in parallel. Safe to call from a background thread (no wx calls).

        Side effect: populates ``self._scan_stat_cache`` with the
        (mtime_ns, size) of every container file seen, taken from the
        ``os.scandir`` ``DirEntry.stat()`` result so the DBPF parse cache
        does not need to re-stat them later. The Windows ``DirEntry`` already
        carries this metadata from the directory enumeration, so capturing
        it here is effectively free; the savings show up at lookup time.
        """
        files = []
        stat_cache = self._scan_stat_cache
        self._scandir_gather(folderName, bRecurse, files, stat_cache)
        return files

    def _scandir_gather(self, folder, recurse, files_out, stat_cache):
        """Recursive scandir walk that captures stats while listing."""
        try:
            it = os.scandir(folder)
        except OSError:
            return
        sub_dirs = []
        sub_files = []
        with it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if recurse:
                            sub_dirs.append(entry.path)
                        continue
                    name_lower = entry.name.lower()
                    if name_lower.endswith(('.dat', '.sc4model',
                                            '.sc4lot', '.sc4desc')):
                        # Known-good extension: skip the header probe.
                        st = entry.stat()
                        path = entry.path
                        sub_files.append(path)
                        stat_cache[os.path.normcase(os.path.abspath(path))] = (
                            st.st_mtime_ns, st.st_size)
                    elif self._is_sc4_container(entry.path):
                        st = entry.stat()
                        path = entry.path
                        sub_files.append(path)
                        stat_cache[os.path.normcase(os.path.abspath(path))] = (
                            st.st_mtime_ns, st.st_size)
                except OSError:
                    continue
        sub_files.sort(key=str.lower)
        files_out.extend(sub_files)
        if recurse:
            sub_dirs.sort(key=str.lower)
            for d in sub_dirs:
                self._scandir_gather(d, True, files_out, stat_cache)

    def load_files_parallel(self, file_list, progress_cb=None):
        """Parse *file_list* in parallel, then merge the results in order.

        *file_list* is an ordered sequence of ``(fileName, bStandard)`` tuples.
        DBPF parsing (file I/O + index decoding) runs in a thread pool; merging
        into the shared entry tables stays single-threaded on the calling
        thread, so load order -- and therefore plugin override order -- is
        preserved (``ThreadPoolExecutor.map`` yields results in input order).

        Must NOT be called on the GUI thread: ``DatFile`` parsing performs no
        wx calls, but this method blocks until every file is parsed.
        """
        file_list = list(file_list)
        total = len(file_list)
        workers = max(2, min(8, (os.cpu_count() or 4)))
        logger.debug('Parsing %d files with %d worker threads', total, workers)

        cache = DatFileCache.open_default(stat_cache=self._scan_stat_cache)

        def _parse(item):
            fileName, bStandard = item
            entries = cache.lookup(fileName)
            if entries is not None:
                return entries, bStandard, fileName, None, None
            try:
                # dlg=None -> no wx calls happen inside the worker thread.
                dat = DatFile(fileName, None, True)
                # Pickle BEFORE returning -- addEntries on the main thread
                # attaches a virtual_dat back-reference that holds wx objects.
                # Doing it here also parallelises the serialization.
                blob = serialize_entries(dat.entries)
                return dat.entries, bStandard, fileName, None, blob
            except Exception as exc:  # noqa: BLE001 - reported per file below
                return None, bStandard, fileName, exc, None

        done = 0
        try:
            with ThreadPoolExecutor(max_workers=workers,
                                    thread_name_prefix='sc4-loader') as pool:
                for entries, bStandard, fileName, exc, blob in pool.map(_parse, file_list):
                    done += 1
                    if entries is None:
                        logger.warning('Skipping unreadable file %s', fileName, exc_info=exc)
                    else:
                        try:
                            self.addEntries(entries, None, bStandard, False)
                        except Exception:
                            logger.warning('Failed to merge entries from %s', fileName,
                                           exc_info=True)
                        else:
                            if blob is not None:
                                cache.queue_store(fileName, blob)
                    if progress_cb is not None:
                        progress_cb(done, total, fileName)
        finally:
            hits, misses, corrupt = cache.stats()
            logger.debug('DBPF parse cache: %d hits, %d misses, %d corrupt',
                         hits, misses, corrupt)
            cache.close()

    def addFile(self, dlg, fileName, bStandard=False, bForceUpdate=False):
        logger.debug('Loading DAT file %s (standard=%s, force_update=%s)',
                     fileName, bool(bStandard), bool(bForceUpdate))
        if not self._is_sc4_container(fileName):
            logger.debug('Skipping non-SC4 container file %s', fileName)
            return
        sc4File = DatFile(fileName, dlg, True)
        logger.debug('Loaded %d entries from %s', len(sc4File.entries), fileName)
        self.addEntries(sc4File.entries, dlg, bStandard, bForceUpdate)

    @staticmethod
    def _is_sc4_container(file_name):
        ext = os.path.splitext(file_name)[1].lower()
        if ext in {'.dat', '.sc4model', '.sc4lot', '.sc4desc'}:
            return True
        # Fall back to a quick header check for non-standard extensions.
        try:
            with open(file_name, 'rb') as handle:
                return handle.read(4) == b'DBPF'
        except OSError:
            return False

    def addEntries(self, entries, dlg, bStandard, bForceUpdate):
        # Hot path: this runs 27k+ times during a full plugins scan, once per
        # DAT file, processing ~500k entries in total. The original loop spent
        # most of its time on attribute lookups and a try/except dedup. The
        # tightened version below local-binds the dict/list/append and tracks
        # the next free index locally so the inner loop is just dict.get +
        # branch. bForceUpdate is hoisted out -- only addFile sets it, and
        # that path isn't part of the bulk scan.
        index = self.TGIIndex
        all_entries = self.allEntries
        append = all_entries.append
        n = len(all_entries)
        before = n
        replaced = 0

        if not bForceUpdate:
            for entry in entries:
                entry.bStandard = bStandard
                entry.virtual_dat = self
                tgi = entry.tgi
                existing = index.get(tgi)
                if existing is None:
                    index[tgi] = n
                    append(entry)
                    n += 1
                else:
                    all_entries[existing] = entry
                    replaced += 1
        else:
            tree = self.tree
            for entry in entries:
                entry.bStandard = bStandard
                entry.virtual_dat = self
                tgi = entry.tgi
                existing = index.get(tgi)
                if existing is None:
                    index[tgi] = n
                    append(entry)
                    n += 1
                else:
                    all_entries[existing] = entry
                    replaced += 1
                tree.UpdateEntry(entry, self, bStandard, dlg)

        logger.debug('Registered %d entries (%d new, %d replaced)',
                     len(entries), n - before, replaced)

    def getEntries(self, t, g, i, tMask=4294967295, gMask=4294967295, iMask=4294967295):
        if t == 87304289 and tMask == 4294967295:
            return filter(lambda entry: entry.tgi[1] & gMask == g and entry.tgi[2] & iMask == i, self.cohorts)
        return filter(
            lambda entry: entry.tgi[0] & tMask == t and entry.tgi[1] & gMask == g and entry.tgi[2] & iMask == i,
            self.allEntries)

    def getEntry(self, t, g, i):
        try:
            return self.allEntries[self.TGIIndex[t, g, i]]
        except KeyError:
            return None

        return None

    def Finalize(self, dlg):
        start = time.time()
        logger.debug('Finalizing virtual DAT with %d entries', len(self.allEntries))
        if dlg is not None and hasattr(dlg, 'SetStatus'):
            dlg.SetStatus('Finalizing data...',
                          '%d entries loaded' % len(self.allEntries))
        self.cohorts = filter(lambda ent: ent.tgi[0] == 87304289, self.allEntries)
        for entry in self.cohorts:
            self.tree.UpdateEntry(entry, self, entry.bStandard, dlg)

        for entry in filter(lambda ent: ent.tgi[0] in {2058686020, 1697917002, 698733036, 1523640343}, self.allEntries):
            self.tree.UpdateEntry(entry, self, entry.bStandard, dlg)

        FinalizeCategory(self.rootCategory)
        self.missing_pictures = []
        for s3d in self.standardModels:
            file_name = str(image_db_path('%s-%s.jpg' % (hex2str(s3d.sc4Model.GID), hex2str(s3d.sc4Model.IID))))
            if not os.path.exists(file_name):
                self.missing_pictures.append((file_name, s3d))
        logger.debug(
            'Finalized virtual DAT in %.3fs: %d standard models, %d other models, %d textures, %d missing pictures',
            time.time() - start,
            len(self.standardModels),
            len(self.otherModels),
            len(self.allTextures),
            len(self.missing_pictures))
