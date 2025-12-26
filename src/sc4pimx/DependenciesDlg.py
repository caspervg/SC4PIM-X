"""Dependencies dialog for SC4 building lots."""
import wx.html
import wx.lib.sized_controls as sc
import CustomTreeCtrl as CT
import os.path
from translation import *
from SC4DatTools import *
from SC4Data import *
from PIL import Image
import io
offsetGID = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 15, 16, 17, 18, 19, 20, 35]

class MyHtmlListBox(wx.html.HtmlListBox):

    def __init__(self, parent, id=-1, pos=(-1, -1), size=(-1, -1), style=0):
        wx.html.HtmlListBox.__init__(self, parent, id, pos=pos, size=size, style=style)
        self.values = []
        self.SetItemCount(0)
        self.txtClip = ''
        self.bMissing = False

    def Append(self, value):
        v = os.path.split(value)[1]
        if v not in self.values:
            self.values.append(v)
            self.txtClip += '<li><a href="http://www.sc4devotion.com/dependencies.html">' + v + '</a></li></br>\r\n'
            self.SetItemCount(len(self.values))

    def AppendHTML(self, v):
        if v not in self.values:
            self.values.append(v)
            self.SetItemCount(len(self.values))

    def Missing(self, v):
        self.bMissing = True

    def OnGetItem(self, n):
        return self.values[n]


class DependenciesDlg(sc.SizedDialog):

    def __init__(self, parent, examplar):
        sc.SizedDialog.__init__(self, parent, -1, title=DependenciesDlgTitleMsg, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        pane = self.GetContentsPane()
        pane.SetSizerType('vertical')
        self.examplar = examplar
        self.virtualDAT = parent.virtual_dat
        self.tree = CT.CustomTreeCtrl(pane, -1, style=wx.SUNKEN_BORDER | CT.TR_HAS_VARIABLE_ROW_HEIGHT | CT.TR_FULL_ROW_HIGHLIGHT | CT.TR_SINGLE, size=(300,
                                                                                                                                                        300))
        self.root = self.tree.AddRoot(examplar.GetProp(32)[0])
        self.tree.SetMinSize((500, 300))
        self.tree.SetIndent(10)
        self.tree.EnableSelectionGradient(True)
        self.tree.SetGradientStyle(False)
        self.tree.SetSizerProps(expand=True)
        self.files = [examplar.entry.fileName]
        self.lb = MyHtmlListBox(pane, -1, style=wx.BORDER_SUNKEN | wx.LB_SINGLE, size=(500,
                                                                                       200))
        self.lb.SetSizerProps(expand=True)
        self.FillTheTree()
        if self.lb.bMissing:
            self.lb.AppendHTML(DepDlgMissing)
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.Fit()
        self.SetMinSize(self.GetSize())
        self.do = wx.TextDataObject()
        self.do.SetText('<ul>\r\n' + self.lb.txtClip + '</ul>\r\n')
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(self.do)
            wx.TheClipboard.Close()

    def AddFileName(self, fileName):
        self.lb.Append(fileName)

    def AddBuildingOrProp(self, rootItem, desc):

        def isValidRTK(rtk):
            if rtk is None:
                return False
            if rtk[0] == 1523640343 and rtk[1] == 3134937073 and rtk[2] == 0:
                return False
            if rtk[0] == 698733036 and rtk[1] == 707025145 and rtk[2] == 0:
                return False
            if rtk[0] == 0 and rtk[1] == 0 and rtk[2] == 0:
                return False
            return True

        thisBuildingItem = self.tree.AppendItem(rootItem, desc.name, ct_type=1, wnd=wx.StaticText(self.tree, -1, os.path.split(desc.fileName)[1]))
        self.lb.Append(desc.fileName)
        self.tree.CheckItem(thisBuildingItem, True)
        rtk = desc.exemplar.GetProp(662775840)
        if isValidRTK(rtk):
            rtkEntry = self.virtualDAT.getEntry(rtk[0], rtk[1], rtk[2])
            if rtkEntry:
                rtkItem = self.tree.AppendItem(thisBuildingItem, 'Model 0x%08X-0x%08X-0x%08X' % (rtk[0], rtk[1], rtk[2]), ct_type=1, wnd=wx.StaticText(self.tree, -1, os.path.split(rtkEntry.fileName)[1]))
                self.lb.Append(rtkEntry.fileName)
                self.tree.CheckItem(rtkItem, True)
            else:
                rtkItem = self.tree.AppendItem(thisBuildingItem, 'Model 0x%08X-0x%08X-0x%08X' % (rtk[0], rtk[1], rtk[2]), ct_type=1, wnd=wx.StaticText(self.tree, -1, DepDlgNotFound))
                self.lb.Missing(DepDlgMissing)
        rtk = desc.exemplar.GetProp(662775841)
        if isValidRTK(rtk):
            rtkEntry = self.virtualDAT.getEntry(rtk[0], rtk[1], rtk[2])
            if rtkEntry:
                rtkItem = self.tree.AppendItem(thisBuildingItem, 'Model 0x%08X-0x%08X-0x%08X' % (rtk[0], rtk[1], rtk[2]), ct_type=1, wnd=wx.StaticText(self.tree, -1, os.path.split(rtkEntry.fileName)[1]))
                self.lb.Append(rtkEntry.fileName)
                self.tree.CheckItem(rtkItem, True)
            else:
                rtkItem = self.tree.AppendItem(thisBuildingItem, 'Model 0x%08X-0x%08X-0x%08X' % (rtk[0], rtk[1], rtk[2]), ct_type=1, wnd=wx.StaticText(self.tree, -1, DepDlgNotFound))
                self.lb.Missing(DepDlgMissing)
        rtk = desc.exemplar.GetProp(662775844)
        if rtk:
            rktData = tuple(rtk)
            for line in range(len(rktData) // 8):
                data = rktData[line * 8:line * 8 + 8]
                entry = self.virtualDAT.getEntry(data[5], data[6], data[7])
                if data[5] == 1523640343 and data[6] == 3134937073 and data[7] == 0:
                    pass
                elif data[5] == 698733036 and data[6] == 707025145 and data[7] == 0:
                    pass
                elif data[5] == 0 and data[6] == 0 and data[7] == 0:
                    pass
                elif entry:
                    rtkItem = self.tree.AppendItem(thisBuildingItem, 'Model 0x%08X-0x%08X-0x%08X' % (data[5], data[6], data[7]), ct_type=1, wnd=wx.StaticText(self.tree, -1, os.path.split(entry.fileName)[1]))
                    self.lb.Append(entry.fileName)
                    self.tree.CheckItem(rtkItem, True)
                else:
                    rtkItem = self.tree.AppendItem(thisBuildingItem, 'Model 0x%08X-0x%08X-0x%08X' % (data[5], data[6], data[7]), ct_type=1, wnd=wx.StaticText(self.tree, -1, DepDlgNotFound))
                    self.lb.Missing(DepDlgMissing)

        propQuery = desc.exemplar.GetProp(709468037)
        if propQuery:
            entry = self.virtualDAT.getEntry(0, 2527069872, propQuery[0])
            if entry:
                item = self.tree.AppendItem(thisBuildingItem, 'Query 0x%08X-0x%08X-0x%08X' % (0, 2527069872, propQuery[0]), ct_type=1, wnd=wx.StaticText(self.tree, -1, os.path.split(entry.fileName)[1]))
                self.lb.Append(entry.fileName)
                self.tree.CheckItem(item, True)
            else:
                item = self.tree.AppendItem(thisBuildingItem, 'Query 0x%08X-0x%08X-0x%08X' % (0, 2527069872, propQuery[0]), ct_type=1, wnd=wx.StaticText(self.tree, -1, DepDlgNotFound))
                self.lb.Missing(DepDlgMissing)
        propIcon = desc.exemplar.GetProp(2317746872)
        if propIcon:
            entry = self.virtualDAT.getEntry(2238569388, 1782082854, propIcon[0])
            if entry:
                item = self.tree.AppendItem(thisBuildingItem, 'Icon 0x%08X-0x%08X-0x%08X' % (2238569388, 1782082854, propIcon[0]), ct_type=1, wnd=wx.StaticText(self.tree, -1, os.path.split(entry.fileName)[1]))
                self.lb.Append(entry.fileName)
                self.tree.CheckItem(item, True)
            else:
                item = self.tree.AppendItem(thisBuildingItem, 'Icon 0x%08X-0x%08X-0x%08X' % (2238569388, 1782082854, propIcon[0]), ct_type=1, wnd=wx.StaticText(self.tree, -1, DepDlgNotFound))
                self.lb.Missing(DepDlgMissing)
        for propId in [2854081431, 1246499630, 172757963, 3384359510, 3390691274]:
            propSound = desc.exemplar.GetProp(propId)
            if propSound:
                entry = self.virtualDAT.getEntry(193823258, 3394050371, propSound[0])
                if entry:
                    item = self.tree.AppendItem(thisBuildingItem, 'Sound 0x%08X-0x%08X-0x%08X' % (193823258, 3394050371, propSound[0]), ct_type=1, wnd=wx.StaticText(self.tree, -1, os.path.split(entry.fileName)[1]))
                    self.lb.Append(entry.fileName)
                    self.tree.CheckItem(item, True)
                else:
                    item = self.tree.AppendItem(thisBuildingItem, 'Sound 0x%08X-0x%08X-0x%08X' % (193823258, 3394050371, propSound[0]), ct_type=1, wnd=wx.StaticText(self.tree, -1, DepDlgNotFound))
                    self.tree.SetItemBackgroundColour(item, wx.Colour(255, 0, 0))
                    self.lb.Missing(DepDlgMissing)

        UVNK = desc.exemplar.GetProp(2319542937)
        if UVNK:
            uvnks = [ self.virtualDAT.getEntry(UVNK[0], UVNK[1] + i, UVNK[2]) for i in offsetGID ]
            bFound = False
            for i, entry in enumerate(uvnks):
                if entry:
                    item = self.tree.AppendItem(thisBuildingItem, 'LTEXT 0x%08X-0x%08X-0x%08X' % (entry.tgi[0], entry.tgi[1], entry.tgi[2]), ct_type=1, wnd=wx.StaticText(self.tree, -1, os.path.split(entry.fileName)[1]))
                    self.lb.Append(entry.fileName)
                    self.tree.CheckItem(item, True)
                    bFound = True

            if not bFound:
                item = self.tree.AppendItem(thisBuildingItem, 'LTEXT 0x%08X-0x%08X-0x%08X' % (UVNK[0], UVNK[1], UVNK[2]), ct_type=1, wnd=wx.StaticText(self.tree, -1, DepDlgNotFound))
                self.tree.SetItemBackgroundColour(item, wx.Colour(255, 0, 0))
                self.lb.Missing(DepDlgMissing)
        IDK = self.examplar.GetProp(3393284789)
        if IDK:
            idks = [ self.virtualDAT.getEntry(IDK[0], IDK[1] + i, IDK[2]) for i in offsetGID ]
            bFound = False
            for i, entry in enumerate(idks):
                if entry:
                    item = self.tree.AppendItem(thisBuildingItem, 'LTEXT 0x%08X-0x%08X-0x%08X' % (entry.tgi[0], entry.tgi[1], entry.tgi[2]), ct_type=1, wnd=wx.StaticText(self.tree, -1, os.path.split(entry.fileName)[1]))
                    self.lb.Append(entry.fileName)
                    self.tree.CheckItem(item, True)
                    bFound = True

            if not bFound:
                item = self.tree.AppendItem(thisBuildingItem, 'LTEXT 0x%08X-0x%08X-0x%08X' % (IDK[0], IDK[1], IDK[2]), ct_type=1, wnd=wx.StaticText(self.tree, -1, DepDlgNotFound))
                self.tree.SetItemBackgroundColour(item, wx.Colour(255, 0, 0))
                self.lb.Missing(DepDlgMissing)
        self.tree.Expand(thisBuildingItem)

    def FillTheTree(self):
        self.texturesItem = None
        self.buildingsItem = None
        self.propsItem = None
        self.florasItem = None
        texIDs = []
        propIDs = []
        floraIDs = []
        buildingFoundation = self.examplar.GetProp(2298271863)
        if buildingFoundation:
            self.buildFound = self.tree.AppendItem(self.root, DepDlgBuildingFoundation)
            self.tree.SetItemBold(self.buildFound)
            possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == buildingFoundation[0], self.virtualDAT.categories[1829068375].descriptors)
            bAdded = False
            for desc in possibles:
                self.AddBuildingOrProp(self.buildFound, desc)
                bAdded = True

            if not bAdded:
                item = self.tree.AppendItem(self.buildFound, hex2str(buildingFoundation[0]), ct_type=1, wnd=wx.StaticText(self.tree, -1, DepDlgNotFound))
                self.lb.Missing(DepDlgMissing)
            self.tree.Expand(self.buildFound)
        for lcp in range(2297284864, 2297286144):
            values = self.examplar.GetProp(lcp)
            if values == None:
                break
            if values[0] == 0:
                bAdded = False
                if self.buildingsItem == None:
                    self.buildingsItem = self.tree.AppendItem(self.root, DepDlgBuilding)
                    self.tree.SetItemBold(self.buildingsItem, True)
                buildingID = values[12]
                if buildingID in self.virtualDAT.categories:
                    for desc in self.virtualDAT.categories[buildingID].descriptors:
                        if desc.exemplar.GetProp(16)[0] == 2:
                            self.AddBuildingOrProp(self.buildingsItem, desc)
                            bAdded = True

                else:
                    possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == buildingID, self.virtualDAT.categories[210746197].descriptors)
                    for desc in possibles:
                        self.AddBuildingOrProp(self.buildingsItem, desc)
                        bAdded = True

                if not bAdded:
                    item = self.tree.AppendItem(self.buildingsItem, hex2str(buildingID), ct_type=1, wnd=wx.StaticText(self.tree, -1, DepDlgNotFound))
                    self.lb.Missing(DepDlgMissing)
            if values[0] == 1:
                if self.propsItem == None:
                    self.propsItem = self.tree.AppendItem(self.root, DepDlgProps)
                    self.tree.SetItemBold(self.propsItem, True)
                propID = values[12]
                if propID not in propIDs:
                    propIDs.append(propID)
                    bAdded = False
                    if propID in self.virtualDAT.categories:
                        for desc in self.virtualDAT.categories[propID].descriptors:
                            if desc.exemplar.GetProp(16)[0] == 30:
                                self.AddBuildingOrProp(self.propsItem, desc)
                                bAdded = True

                    else:
                        possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == propID, self.virtualDAT.categories[210746660].descriptors)
                        for desc in possibles:
                            self.AddBuildingOrProp(self.propsItem, desc)
                            bAdded = True

                    if not bAdded:
                        item = self.tree.AppendItem(self.propsItem, hex2str(propID), ct_type=1, wnd=wx.StaticText(self.tree, -1, DepDlgNotFound))
                        self.lb.Missing(DepDlgMissing)
            if values[0] == 2:
                if self.texturesItem == None:
                    self.texturesItem = self.tree.AppendItem(self.root, DepDlgTextures)
                    self.tree.SetItemBold(self.texturesItem, True)
                texID = values[12]
                if texID not in texIDs:
                    texEntry = self.virtualDAT.getEntry(2058686020, 159781726, texID)
                    if texEntry == None:
                        item = self.tree.AppendItem(self.texturesItem, hex2str(texID), ct_type=1, wnd=wx.StaticText(self.tree, -1, DepDlgNotFound))
                        self.lb.Missing(DepDlgMissing)
                    else:
                        item = self.tree.AppendItem(self.texturesItem, hex2str(texID), ct_type=1, wnd=wx.StaticText(self.tree, -1, os.path.split(texEntry.fileName)[1]))
                        self.AddFileName(texEntry.fileName)
                        self.tree.CheckItem(item, True)
                    texIDs.append(texID)
            if values[0] == 4:
                if self.florasItem == None:
                    self.florasItem = self.tree.AppendItem(self.root, DepDlgFlora)
                    self.tree.SetItemBold(self.florasItem)
                floraID = values[12]
                if floraID not in floraIDs:
                    floraIDs.append(floraID)
                    bAdded = False
                    possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == floraID, self.virtualDAT.categories[1830116951].descriptors)
                    for desc in possibles:
                        self.AddBuildingOrProp(self.florasItem, desc)
                        bAdded = True

                    if not bAdded:
                        item = self.tree.AppendItem(self.florasItem, hex2str(floraID), ct_type=1, wnd=wx.StaticText(self.tree, -1, DepDlgNotFound))
                        self.lb.Missing(DepDlgMissing)

        if self.buildingsItem:
            self.tree.Expand(self.buildingsItem)
        if self.propsItem:
            self.tree.Expand(self.propsItem)
        if self.texturesItem:
            self.tree.Expand(self.texturesItem)
        if self.florasItem:
            self.tree.Expand(self.florasItem)
        self.tree.Expand(self.root)
        return


class ImageListCtrl(wx.ListCtrl):

    def __init__(self, parent):
        wx.ListCtrl.__init__(self, parent, -1, style=wx.LC_ICON | wx.LC_AUTOARRANGE | wx.LC_HRULES | wx.LC_VRULES)
        self.InsertColumn(0, 'Image')
        self.SetColumnWidth(0, 500)
        self.il = wx.ImageList(88, 88, False)
        allIcons = VirtualDat.this.getEntries(2238569388, 1782082854, 0, iMask=0)
        for iconEntry in allIcons:
            iconEntry.read_file(None, True, True)
            c = io.BytesIO(iconEntry.content)
            pil = Image.open(c)
            pilz = pil.crop((3 * 44, 0, 4 * 44, 44)).copy()
            image = wx.EmptyImage(88, 88)
            try:
                pilz = pilz.resize((88, 88), Image.BICUBIC)
                image.SetData(pilz.convert('RGB').tobytes())
            except Exception:
                raise

            idx = self.il.Add(image.ConvertToBitmap())
            self.InsertImageStringItem(self.GetItemCount(), hex2str(iconEntry.tgi[2]), idx)
            iconEntry.rawContent = None
            iconEntry.content = None

        self.SetImageList(self.il, wx.IMAGE_LIST_NORMAL)
        return


class IconsDlg(sc.SizedDialog):

    def __init__(self, parent, examplar):
        sc.SizedDialog.__init__(self, parent, -1, title='Icons', style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        pane = self.GetContentsPane()
        pane.SetSizerType('vertical')
        self.iconsList = ImageListCtrl(pane)
        self.iconsList.SetMinSize((500, 300))
        self.iconsList.SetSizerProps(expand=True)
        self.iconsList.SetSizerProps(proportion=1)
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.Fit()
        self.SetMinSize(self.GetSize())
