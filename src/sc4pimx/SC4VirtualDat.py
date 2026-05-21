import logging
import os
import time
import xml.dom.minidom
from concurrent.futures import ThreadPoolExecutor

import wx

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
        """
        files = BuildSortedFilesList(folderName, bRecurse)
        return [f for f in files if self._is_sc4_container(f)]

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

        def _parse(item):
            fileName, bStandard = item
            try:
                # dlg=None -> no wx calls happen inside the worker thread.
                return DatFile(fileName, None, True), bStandard, fileName, None
            except Exception as exc:  # noqa: BLE001 - reported per file below
                return None, bStandard, fileName, exc

        done = 0
        with ThreadPoolExecutor(max_workers=workers,
                                thread_name_prefix='sc4-loader') as pool:
            for datFile, bStandard, fileName, exc in pool.map(_parse, file_list):
                done += 1
                if datFile is None:
                    logger.warning('Skipping unreadable file %s', fileName, exc_info=exc)
                else:
                    try:
                        self.addEntries(datFile.entries, None, bStandard, False)
                    except Exception:
                        logger.warning('Failed to merge entries from %s', fileName,
                                       exc_info=True)
                if progress_cb is not None:
                    progress_cb(done, total, fileName)

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
        before = len(self.allEntries)
        replaced = 0
        for entry in entries:
            entry.bStandard = bStandard
            entry.virtual_dat = self
            try:
                idx = self.TGIIndex[entry.tgi]
                self.allEntries[idx] = entry
                replaced += 1
            except KeyError:
                self.TGIIndex[entry.tgi] = len(self.allEntries)
                self.allEntries.append(entry)

            if bForceUpdate:
                self.tree.UpdateEntry(entry, self, entry.bStandard, dlg)
        logger.debug('Registered %d entries (%d new, %d replaced)', len(entries), len(self.allEntries) - before, replaced)

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
