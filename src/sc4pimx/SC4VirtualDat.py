import os
import sys
import time
import xml.dom.minidom

import wx

from .paths import package_data_path
from .SC4DataFunctions import (
    DuplicateProp,
    FinalizeCategory,
    ReadStageVsDensity,
    ReadZoning,
    readCategoryDef,
    readPropertyDef,
)
from .SC4DatTools import BuildSortedFilesList, DatFile, hex2str


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

        descs = filter(UseThisIID, self.categories[210091300].descriptors)
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

        descs = filter(UseThisIID, self.categories[210091300].descriptors)
        return descs

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
        propertiesXML = xml.dom.minidom.parse(str(package_data_path('new_properties.xml')))
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
        if os.environ.get('SC4PIM_TRACE', '').strip():
            print('[TRACE] addFolder:%s' % folderName)
            sys.stdout.flush()
        filesName = BuildSortedFilesList(folderName, bRecurse)
        for fileName in filesName:
            # Skip non-DBPF/SC4 container files early to avoid unnecessary reads.
            if not self._is_sc4_container(fileName):
                continue
            self.addFile(dlg, fileName, bStandard)

    def addFile(self, dlg, fileName, bStandard=False, bForceUpdate=False):
        if os.environ.get('SC4PIM_TRACE', '').strip():
            print('[TRACE] addFile:%s' % fileName)
            sys.stdout.flush()
        if not self._is_sc4_container(fileName):
            return
        sc4File = DatFile(fileName, dlg, True)
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
        for entry in entries:
            entry.bStandard = bStandard
            entry.virtual_dat = self
            try:
                idx = self.TGIIndex[entry.tgi]
                self.allEntries[idx] = entry
            except KeyError:
                self.TGIIndex[entry.tgi] = len(self.allEntries)
                self.allEntries.append(entry)

            if bForceUpdate:
                self.tree.UpdateEntry(entry, self, entry.bStandard, dlg)

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
        self.cohorts = filter(lambda ent: ent.tgi[0] == 87304289, self.allEntries)
        for entry in self.cohorts:
            self.tree.UpdateEntry(entry, self, entry.bStandard, dlg)

        for entry in filter(lambda ent: ent.tgi[0] in {2058686020, 1697917002, 698733036, 1523640343}, self.allEntries):
            self.tree.UpdateEntry(entry, self, entry.bStandard, dlg)

        FinalizeCategory(self.rootCategory)
        self.missing_pictures = []
        for s3d in self.standardModels:
            file_name = 'ImageDB/%s-%s.jpg' % (hex2str(s3d.sc4Model.GID), hex2str(s3d.sc4Model.IID))
            if not os.path.exists(file_name):
                self.missing_pictures.append((file_name, s3d))
