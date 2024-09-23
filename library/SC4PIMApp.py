# uncompyle6 version 2.11.5
# Python bytecode 2.4 (62061)
# Decompiled from: Python 2.7.18 (default, Oct 15 2023, 16:43:11) 
# [GCC 11.4.0]
# Embedded file name: SC4PIMApp.pyo
# Compiled at: 2010-01-16 17:56:19
import wx
import sys
import struct
import datetime
import random
import time
import QFS
import math
import os
import dircache
import os.path
from math import *
import wx.lib.hyperlink as hl
import wx.lib.mixins.listctrl as listmix
import wx.lib.sized_controls as sc
import Image
import ImageOps
import ImageDraw
import win32api
import win32con
import StringIO
import SC4IconMakerDlg
from SC4DatTools import *
from SC4Data import *
from S3DReader import *
from ATCReader import *
from ATCViewer import *
from SC4OpenGL import *
from SC4LotPreview import *
from DependenciesDlg import *
import treeDnD
from translation import *
from settings import *
offsetGID = [
 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 15, 16, 17, 18, 19, 20, 35]
oldRound = round

def round(a):
    return int(oldRound(a))


def clamp2Tile(x):
    if fmod(x, 16) < 0.5 and x > 16:
        return int(x - 1) / 16 * 16 + 15.5
    return int(x) / 16 * 16 + min(fmod(x, 16), 15.5)


def Test(condition, valTrue, valFalse):
    if condition:
        return valTrue
    return valFalse


def LessThan(v1, v2):
    return v1 < v2


def GreaterThan(v1, v2):
    return v1 > v2


class ProcessDlg(wx.Dialog):

    def __init__(self, parent, title='please wait'):
        pre = wx.PreDialog()
        pre.Create(parent, -1, 'PIM Extended')
        self.PostCreate(pre)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.labelg1 = wx.StaticText(self, -1, title, size=(500, -1))
        sizer.Add(self.labelg1, 1, wx.EXPAND | wx.ALIGN_CENTRE | wx.ALL, 5)
        self.g1 = wx.Gauge(self, -1, 32)
        self.g1.SetBezelFace(3)
        self.g1.SetShadowWidth(3)
        sizer.Add(self.g1, 0, wx.EXPAND | wx.ALIGN_CENTRE | wx.ALL, 5)
        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Bind(wx.EVT_CLOSE, self.OnCloseWindow)
        self.g1.SetRange(1000)
        self.value = 0

    def Increment(self):
        self.value += 1
        if self.value == 1000:
            self.g1.Pulse()
            self.value = 0
            wx.Yield()

    def LogError(self, what):
        pass

    def OnCloseWindow(self, event):
        event.Veto()


class MyTreeCtrl(wx.TreeCtrl):

    def __init__(self, virtualDAT, parent, mainFrame, style, size):
        wx.TreeCtrl.__init__(self, parent, -1, style=style | wx.TR_EDIT_LABELS, size=size)
        self.parent = mainFrame
        self.virtualDAT = virtualDAT
        self.root = self.AddRoot(treeRootMsg)
        self.ResourcesItem = self.AppendItem(self.root, treeResourceMsg)
        self.StandardModelsItem = self.AppendItem(self.ResourcesItem, treeStdModelMsg)
        self.SetPyData(self.StandardModelsItem, virtualDAT.standardModels)
        self.OtherModelsItem = self.AppendItem(self.ResourcesItem, treeOtherModelMsg)
        self.SetPyData(self.OtherModelsItem, virtualDAT.otherModels)
        self.ATCsItem = self.AppendItem(self.ResourcesItem, treeAnimMsg)
        self.SetPyData(self.ATCsItem, virtualDAT.atcs)
        self.DescItem = self.AppendItem(self.root, treeDescMsg)

        def CreateCat(cat, root):
            item = self.AppendItem(root, cat.Name)
            self.SetPyData(item, cat)
            cat.item = item
            for child in cat.childs:
                CreateCat(child, item)

        CreateCat(virtualDAT.rootCategory, self.DescItem)
        self.entry2Item = {}
        self.families = {}
        self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
        self.Bind(wx.EVT_TREE_BEGIN_LABEL_EDIT, self.OnBeginEdit)
        self.Bind(wx.EVT_TREE_END_LABEL_EDIT, self.OnEndEdit)

    def OnBeginEdit(self, event):
        item = event.GetItem()
        data = self.GetPyData(item)
        if data is not None and data.__class__ == DictWrapper and data.parentID == 4089087265L:
            pass
        else:
            event.Veto()
        return

    def OnEndEdit(self, event):
        if event.IsEditCancelled():
            return
        item = event.GetItem()
        data = self.GetPyData(item)
        fileNameBase = 'Family ' + event.GetLabel()
        family = data.ID
        IID = family + 268435456 & 4294967295L
        buffer = struct.pack('III', 87304289, 1740496652, IID)
        buffer += struct.pack('II', 0, 0)
        entry = SC4Entry(buffer, 0, os.path.join(self.parent.rootFolder, '%s-0x%08x-0x%08x-0x%08x.SC4Desc' % (fileNameBase, 87304289, 1740496652, IID)))
        entry.virtualDAT = self.virtualDAT
        props = []
        descsInFamily = self.virtualDAT.categories[family].descriptors
        typeProp = 30
        if descsInFamily:
            for desc in descsInFamily:
                typeProp = desc.examplar.GetProp(16)[0]
                break

        props.append(CreateAPropFromString(self.virtualDAT.properties[16], '0x%08X' % typeProp))
        props.append(CreateAPropFromString(self.virtualDAT.properties[32], str(event.GetLabel())))
        props.append(CreateAPropFromString(self.virtualDAT.properties[662775920], '0x%08X' % family))
        props.sort(cmp=lambda x, y: cmp(x[2:2 + 8], y[2:2 + 8]))
        buffer = 'CQZT1###\r\n' + 'ParentCohort=Key:{0x00000000,0x00000000,0x00000000}\r\n' + 'PropCount=0x%08x\r\n' % len(props)
        buffer += '\r\n'.join(props)
        entry.content = entry.rawContent = buffer
        examplar = Examplar(entry, self.virtualDAT)
        examplar.sig = 'CQZB1###'
        examplar.entry = entry
        entry.examplar = examplar
        descriptor = BuildingDesc(entry)
        self.parent.FillPropList(descriptor, False)
        entry.examplar.Maj()
        entries = [entry]
        WriteADat(entry.fileName, entries, None, True)
        self.virtualDAT.addEntries(entries, None, False, False)
        self.virtualDAT.cohorts.append(entry)
        self.virtualDAT.categories[family].descriptors.append(descriptor)
        self.Delete(item)
        self.virtualDAT.categories[data.parentID].childs.remove(data)
        data.parentID = 4089086497L
        data.parent = self.virtualDAT.categories[data.parentID]
        data.parent.childs.append(data)
        data.Name = event.GetLabel() + ' - [0x%08X]' % family
        item = self.AppendItem(data.parent.item, data.Name)
        self.SetPyData(item, data)
        data.item = item
        self.EnsureVisible(item)
        self.SelectItem(item)
        return

    def OnRightDown(self, event):
        pt = event.GetPosition()
        item, flags = self.HitTest(pt)
        if item:
            self.SelectItem(item)
            data = self.GetPyData(item)
            if data is not None:
                if data.__class__ == DictWrapper:
                    if data.parentID == 4089087265L:
                        self.EditLabel(item)
        return

    def Recategorize(self, desc, bOld=True, bFinalize=True):
        if bOld:
            for idCat, category in self.virtualDAT.categories.iteritems():
                try:
                    category.descriptors.remove(desc)
                    continue
                except ValueError:
                    pass

        if not Categorize(self.virtualDAT.rootCategory, desc):
            if desc.examplar.GetProp(16)[0] == 2:
                self.virtualDAT.categories[3540939231L].descriptors.append(desc)
                desc.cats = [3540939231L]
            if desc.examplar.GetProp(16)[0] == 16:
                self.virtualDAT.categories[3379372343L].descriptors.append(desc)
                desc.cats = [3379372343L]
        propFamilies = desc.examplar.GetProp(662775920)
        if propFamilies:
            for family in propFamilies:
                if family not in self.virtualDAT.categories:
                    parentFamilyCatID = 4089087265L
                    name = '0x%08X' % family
                    bNamed = False
                    choosenCohort = self.virtualDAT.getEntry(87304289, 1740496652, family + 268435456 & 4294967295L)
                    if choosenCohort == None:
                        potentialCohorts = []
                        potentialCohorts = self.virtualDAT.getEntries(87304289, 0, family + 268435456 & 4294967295L, gMask=0)
                    else:
                        choosenCohort.cats = [
                         4089082401L]
                        potentialCohorts = [choosenCohort]
                    for cohort in potentialCohorts:
                        if 'examplar' not in cohort.__dict__:
                            pass
                        else:
                            name = cohort.examplar.GetProp(32)
                            if name is not None:
                                name = name[0] + ' - [0x%08X]' % family
                                parentFamilyCatID = 4089086497L
                                bNamed = True
                                choosenCohort = cohort
                                break

                    xmlStr = '<?xml version="1.0" encoding="UTF-8"?><temp><CATEGORY Name="%s" ID="%s" ParentID="%s">' % (name, hex2str(family), hex2str(parentFamilyCatID))
                    xmlStr += '</CATEGORY></temp>'
                    try:
                        xmlDoc = xml.dom.minidom.parseString(xmlStr)
                    except:
                        print 'Problem with family %s 0x%08X' % (name, family)
                        return

                    for subNode in xmlDoc.documentElement.childNodes:
                        if subNode.nodeType == subNode.ELEMENT_NODE and subNode.tagName == 'CATEGORY':
                            category = readCategoryDef(subNode)
                            if category.parentID != 0:
                                category.parent = self.virtualDAT.categories[category.parentID]
                                category.imgName = category.parent.imgName
                                category.imgIdx = category.parent.imgIdx
                                self.virtualDAT.categories[category.parentID].childs.append(category)
                            else:
                                self.virtualDAT.rootCategory = category
                            self.virtualDAT.categories[category.ID] = category
                            item = self.AppendItem(category.parent.item, category.Name)
                            self.SetPyData(item, category)
                            category.item = item

                    if choosenCohort and bNamed:
                        descCohort = BuildingDesc(choosenCohort)
                        self.virtualDAT.categories[family].descriptors.append(descCohort)
                try:
                    self.virtualDAT.categories[family].descriptors.append(desc)
                except:
                    print 'Bizarre problem with family %s 0x%08X in %s' % (name, family, desc.examplar.entry.fileName)

        if bFinalize:
            FinalizeCategory(self.virtualDAT.rootCategory)
            self.parent.RefreshItemsList()
        return

    def UpdateEntry(self, entry, virtualDAT, bStandard, dlg):
        if dlg:
            dlg.Increment()
        if entry.tgi[0] == 2058686020:
            if entry.tgi[1] == 159781726 and entry.tgi[2] & 15 in [3, 8, 13]:
                virtualDAT.allTextures.append(entry)
            if entry.tgi[0] == 1523640343 and entry.tgi[2] & 4095 == 0:
                model = SC4Model(entry.tgi[1], entry.tgi[2], virtualDAT)
                if model.bValid:
                    virtualDAT.standardModelsDict[entry.tgi] = model
                    virtualDAT.standardModels.append(StandardModel(entry, model))
                elif entry.tgi[1] == 3134937073L and entry.tgi[2] == 235995136:
                    what = SC4ModelMesh(entry.tgi[1], entry.tgi[2], virtualDAT)
                    if what.bValid == False:
                        del model
                    else:
                        virtualDAT.otherModels.append(StandardModel(entry, what))
                        virtualDAT.otherModelsDict[entry.tgi] = what
                else:
                    del model
            if entry.tgi[0] == 698733036:
                atc = ATC(entry, virtualDAT)
                virtualDAT.atcsDict[entry.tgi] = atc
                virtualDAT.atcs.append(ATCProxy(entry, atc))
            if entry.tgi[0] == 87304289:
                if 'examplar' not in entry.__dict__:
                    entry.ReadFile(None, True, True)
                    examplar = Examplar(entry, virtualDAT)
                    entry.examplar = examplar
                    entry.rawContent = None
                    entry.content = None
                else:
                    entry.rawContent = None
                    entry.content = None
                    examplar = entry.examplar
            if not bStandard and entry.tgi[0] == 1697917002:
                if 'examplar' not in entry.__dict__:
                    entry.ReadFile(None, True, True)
                    examplar = Examplar(entry, virtualDAT)
                    entry.examplar = examplar
                    entry.rawContent = None
                    entry.content = None
                else:
                    entry.rawContent = None
                    entry.content = None
                    examplar = entry.examplar
                desc = None
                _0x10 = examplar.GetProp(16)
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
                entry.examplar.free()
                del entry.examplar
                del examplar
        return


class VirtualListCtrl(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin):

    def __init__(self, parent):
        wx.ListCtrl.__init__(self, parent, -1, style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.TAB_TRAVERSAL | wx.LC_SINGLE_SEL)
        listmix.ListCtrlAutoWidthMixin.__init__(self)
        self.SetItemCount(0)
        self.listdatas = None
        self.attr1 = wx.ListItemAttr()
        self.attr1.SetBackgroundColour((255, 228, 181))
        self.attr2 = wx.ListItemAttr()
        self.attr2.SetBackgroundColour('light blue')
        self.Bind(wx.EVT_LIST_COL_CLICK, self.OnListHeaderClick)
        return

    def Refresh(self):
        if len(self.listdatas) != self.GetItemCount():
            self.SetItemCount(len(self.listdatas))
        wx.ListCtrl.Refresh(self)

    def OnGetItemText(self, item, col):
        if self.listdatas == None:
            return ''
        elif col == 0:
            return self.listdatas[item].name
        elif col == 1:
            return self.listdatas[item].fileName
        elif col == 2:
            return time.ctime(self.listdatas[item].examplar.entry.dateUpdated)
        else:
            return 'Item %d, column %d' % (item, col)
        return

    def OnListHeaderClick(self, event):
        col = event.GetColumn()
        if col == 0:
            self.listdatas.sort(cmp=lambda n1, n2: cmp(n1.name.upper(), n2.name.upper()))
        if col == 1:
            self.listdatas.sort(cmp=lambda n1, n2: cmp(n1.fileName.upper(), n2.fileName.upper()))
        if col == 2:
            self.listdatas.sort(cmp=lambda n1, n2: cmp(n2.examplar.entry.dateUpdated, n1.examplar.entry.dateUpdated))
        self.DeleteAllItems()
        self.SetItemCount(len(self.listdatas))

    def OnGetItemImage(self, item):
        return -1

    def OnGetItemAttr(self, item):
        if item % 2 == 1:
            return self.attr1
        else:
            return self.attr2


class Mixinlist(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin):

    def __init__(self, parent, ID, pos=wx.DefaultPosition, size=wx.DefaultSize, style=0):
        wx.ListCtrl.__init__(self, parent, ID, pos, size, style)
        listmix.ListCtrlAutoWidthMixin.__init__(self)


class Mixinlist(wx.ListCtrl):

    def __init__(self, parent, ID, pos=wx.DefaultPosition, size=wx.DefaultSize, style=0):
        wx.ListCtrl.__init__(self, parent, ID, pos, size, style)


class EditDialog(sc.SizedDialog):

    def __init__(self, parent, title, txt):
        sc.SizedDialog.__init__(self, parent, -1, title)
        pane = self.GetContentsPane()
        pane.SetSizerType('vertical')
        wx.StaticText(pane, 1, editUnicodeWarning)
        self.editor = wx.TextCtrl(pane, -1, txt, style=wx.TE_MULTILINE, size=(400,
                                                                              100))
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.Fit()
        self.SetMinSize(self.GetSize())

    def GetValue(self):
        return self.editor.GetValue()


class NoteBookPanel(wx.Panel):

    def __init__(self, parent, descriptor, virtualDAT):
        wx.Panel.__init__(self, parent)
        self.parent = parent
        self.descriptor = descriptor
        self.examplar = descriptor.examplar
        self.virtualDAT = virtualDAT
        self.RebuildViewer()
        self.bClose = wx.Button(self, -1, propertyPageClose)
        self.Bind(wx.EVT_BUTTON, self.parent.OnCloseTab, self.bClose)
        self.bSave = wx.Button(self, -1, propertyPageSave)
        self.bSave.Enable(False)
        self.Bind(wx.EVT_BUTTON, self.OnSaveTab, self.bSave)
        self.listProperties = Mixinlist(self, -1, style=wx.LC_REPORT | wx.LC_HRULES)
        self.listProperties.InsertColumn(0, propertyPageColumnName)
        self.listProperties.InsertColumn(1, propertyPageColumnNameValue)
        self.listProperties.InsertColumn(2, propertyPageColumnDataType)
        self.listProperties.InsertColumn(3, propertyPageColumnRep)
        self.listProperties.InsertColumn(4, propertyPageColumnValue)
        self.listProperties.SetColumnWidth(4, 400)
        self.Bind(wx.EVT_SET_FOCUS, self.parent.OnFocus, self.listProperties)
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnActivated, self.listProperties)
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

    def RebuildViewer(self):
        rkt0 = self.examplar.GetProp(662775840)
        rkt1 = self.examplar.GetProp(662775841)
        rkt3 = self.examplar.GetProp(662775843)
        rkt4 = self.examplar.GetProp(662775844)
        rkt5 = self.examplar.GetProp(662775845)
        view = None
        if rkt0:
            view = ResourceViewer(662775840, rkt0, self.virtualDAT, self.parent.parent, self.examplar.entry.tgi)
        elif rkt1:
            view = ResourceViewer(662775841, rkt1, self.virtualDAT, self.parent.parent, self.examplar.entry.tgi)
        elif rkt3:
            view = ResourceViewer(662775843, rkt3, self.virtualDAT, self.parent.parent, self.examplar.entry.tgi)
        elif rkt4:
            view = ResourceViewer(662775844, rkt4, self.virtualDAT, self.parent.parent, self.examplar.entry.tgi)
        elif rkt5:
            view = ResourceViewer(662775845, rkt5, self.virtualDAT, self.parent.parent, self.examplar.entry.tgi)
        self.view = view
        return

    def UndoInCaseModified(self):
        IID = self.examplar.entry.tgi[2]
        texEntry = VirtualDat.this.getEntry(2238569388L, 1782082854, IID)
        if texEntry != None:
            texEntry.content = texEntry.rawContent = None
        if self.examplar.modified:
            self.examplar.Reread()
            self.descriptor.name = self.examplar.GetProp(32)[0]
            self.parent.parent.tree.Recategorize(self.descriptor)
            self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
            self.parent.parent.listItems.Refresh()
            self.listProperties.DeleteAllItems()
            self.FillTheList()
            item = self.parent.parent.tree.GetSelection()
            try:
                data = self.parent.parent.tree.GetPyData(item)
            except:
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
        self.examplar = descriptor.examplar
        self.FillTheList()

    def FillTheList(self):
        idx = self.listProperties.InsertStringItem(sys.maxint, propertyPageFilename)
        self.listProperties.SetItemBackgroundColour(idx, wx.Colour(205, 190, 112))
        self.listProperties.SetStringItem(idx, 4, '%s' % self.examplar.entry.fileName)
        idx = self.listProperties.InsertStringItem(sys.maxint, 'TGI')
        self.listProperties.SetItemBackgroundColour(idx, wx.Colour(205, 190, 112))
        self.listProperties.SetStringItem(idx, 4, '0x%08X 0x%08X 0x%08X' % (self.examplar.entry.tgi[0], self.examplar.entry.tgi[1], self.examplar.entry.tgi[2]))
        idx = self.listProperties.InsertStringItem(sys.maxint, propertyPageParentCohort)
        self.listProperties.SetItemBackgroundColour(idx, wx.Colour(205, 190, 112))
        self.listProperties.SetStringItem(idx, 4, '0x%08X 0x%08X 0x%08X' % (self.examplar.parentCohort[0], self.examplar.parentCohort[1], self.examplar.parentCohort[2]))
        for prop in self.examplar.props:
            try:
                name = self.virtualDAT.properties[prop.id].Name
                formatted = ConvertAPropToReadable(prop, self.virtualDAT.properties[prop.id])
            except KeyError:
                name = '0x%08X' % prop.id
                formatted = prop.ToStr()

            idx = self.listProperties.InsertStringItem(sys.maxint, name)
            self.listProperties.SetStringItem(idx, 1, '0x%08X' % prop.id)
            self.listProperties.SetStringItem(idx, 2, '%s' % Prop.format2String[prop.typeValue])
            self.listProperties.SetStringItem(idx, 3, '%d' % len(prop.values))
            self.listProperties.SetStringItem(idx, 4, '%s' % formatted)
            if prop.id == 138265735:
                if prop.values != [0.0] * 256:
                    self.listProperties.SetItemBackgroundColour(idx, wx.Colour(200, 99, 71))
            if prop.id == 709468037:
                if self.virtualDAT.getEntry(0, 2527069872L, prop.values[0]) == None:
                    self.listProperties.SetItemBackgroundColour(idx, wx.Colour(200, 99, 71))
            if prop.id == 2317746872L:
                if self.virtualDAT.getEntry(2238569388L, 1782082854, prop.values[0]) == None:
                    self.listProperties.SetItemBackgroundColour(idx, wx.Colour(200, 99, 71))
            if prop.id == 3928360329L:
                if self.virtualDAT.getEntry(1697917002, 2835075954L, prop.values[0]) == None:
                    self.listProperties.SetItemBackgroundColour(idx, wx.Colour(200, 99, 71))

        def FamilyFill(cohort):
            if cohort != None:
                idx = self.listProperties.InsertStringItem(sys.maxint, propertyPageFamily)
                formatted = '0x%08X 0x%08X 0x%08X' % (cohort.tgi[0], cohort.tgi[1], cohort.tgi[2])
                self.listProperties.SetStringItem(idx, 4, '%s' % formatted)
                self.listProperties.SetItemBackgroundColour(idx, wx.Colour(160, 190, 220))
                for prop in cohort.examplar.props:
                    try:
                        name = self.virtualDAT.properties[prop.id].Name
                        formatted = ConvertAPropToReadable(prop, self.virtualDAT.properties[prop.id])
                    except KeyError:
                        name = '0x%08X' % prop.id
                        formatted = prop.ToStr()

                    idx = self.listProperties.InsertStringItem(sys.maxint, name)
                    self.listProperties.SetStringItem(idx, 1, '0x%08X' % prop.id)
                    self.listProperties.SetStringItem(idx, 2, '%s' % Prop.format2String[prop.typeValue])
                    self.listProperties.SetStringItem(idx, 3, '%d' % len(prop.values))
                    self.listProperties.SetStringItem(idx, 4, '%s' % formatted)
                    self.listProperties.SetItemBackgroundColour(idx, wx.Colour(213, 239, 255))

                RecurseFill(cohort.examplar.link)
            return

        def RecurseFill(link):
            if link != None:
                idx = self.listProperties.InsertStringItem(sys.maxint, propertyPageInherited)
                formatted = '0x%08X 0x%08X 0x%08X' % (link.tgi[0], link.tgi[1], link.tgi[2])
                self.listProperties.SetStringItem(idx, 4, '%s' % formatted)
                self.listProperties.SetItemBackgroundColour(idx, wx.Colour(190, 190, 190))
                for prop in link.examplar.props:
                    try:
                        name = self.virtualDAT.properties[prop.id].Name
                        formatted = ConvertAPropToReadable(prop, self.virtualDAT.properties[prop.id])
                    except KeyError:
                        name = '0x%08X' % prop.id
                        formatted = prop.ToStr()

                    idx = self.listProperties.InsertStringItem(sys.maxint, name)
                    self.listProperties.SetStringItem(idx, 1, '0x%08X' % prop.id)
                    self.listProperties.SetStringItem(idx, 2, '%s' % Prop.format2String[prop.typeValue])
                    self.listProperties.SetStringItem(idx, 3, '%d' % len(prop.values))
                    self.listProperties.SetStringItem(idx, 4, '%s' % formatted)
                    self.listProperties.SetItemBackgroundColour(idx, wx.Colour(255, 239, 213))

                RecurseFill(link.examplar.link)
            return

        RecurseFill(self.examplar.link)
        UVNK = self.examplar.GetProp(2319542937L)
        IDK = self.examplar.GetProp(3393284789L)
        if UVNK or IDK:
            idx = self.listProperties.InsertStringItem(sys.maxint, propertyPageLTEXT)
            self.listProperties.SetItemBackgroundColour(idx, wx.Colour(113, 255, 139))
            if UVNK:
                try:
                    uvnks = [ self.virtualDAT.getEntry(UVNK[0], UVNK[1] + i, UVNK[2]) for i in offsetGID ]
                except:
                    uvnks = []

                for i, uvnk in enumerate(uvnks):
                    if uvnk:
                        uvnk.ReadFile(None, True, True)
                        try:
                            txt = uvnk.content[4:].decode('unicode_internal')
                        except UnicodeDecodeError:
                            txt = uvnk.content.decode('utf8')

                        idx = self.listProperties.InsertStringItem(sys.maxint, self.virtualDAT.properties[2319542937L].Name)
                        self.listProperties.SetStringItem(idx, 4, txt)
                        self.listProperties.SetStringItem(idx, 1, '0x%08X' % uvnk.tgi[1])
                        self.listProperties.SetStringItem(idx, 2, namedLang[i])
                        self.listProperties.SetItemData(idx, 805306368 + offsetGID[i])
                        self.listProperties.SetItemBackgroundColour(idx, wx.Colour(213, 255, 239))

            if IDK and IDK != UVNK:
                try:
                    idks = [ self.virtualDAT.getEntry(IDK[0], IDK[1] + i, IDK[2]) for i in offsetGID ]
                except:
                    idks = []

                for i, idk in enumerate(idks):
                    if idk:
                        idk.ReadFile(None, True, True)
                        try:
                            txt = idk.content[4:].decode('unicode_internal')
                        except UnicodeDecodeError:
                            txt = idk.content.decode('utf8')

                        idx = self.listProperties.InsertStringItem(sys.maxint, self.virtualDAT.properties[3393284789L].Name)
                        self.listProperties.SetStringItem(idx, 4, txt)
                        self.listProperties.SetStringItem(idx, 1, '0x%08X' % idk.tgi[1])
                        self.listProperties.SetStringItem(idx, 2, namedLang[i])
                        self.listProperties.SetItemData(idx, 1073741824 + offsetGID[i])
                        self.listProperties.SetItemBackgroundColour(idx, wx.Colour(213, 255, 239))

        propFamilies = self.examplar.GetProp(662775920)
        if propFamilies:
            for family in propFamilies:
                choosenCohort = self.virtualDAT.getEntry(87304289, 1740496652, family + 268435456 & 4294967295L)
                if choosenCohort == None:
                    potentialCohorts = self.virtualDAT.getEntries(87304289, 0, family + 268435456 & 4294967295L, gMask=0)
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
            except:
                state = 0

            if zoom == -1:
                nZoom = 0
            else:
                nZoom = zoom
            self.view.Draw(self.parent.parent.viewer, self.parent.parent.staticFileName, zoom, rot, state)
            self.parent.parent.currentModel = self.view
        else:
            self.parent.parent.currentModel = None
            self.parent.parent.staticFileName.SetLabel(unknownRK)
        return

    def OnEditLTEXT(self, ltextEntry):
        ltextEntry.ReadFile(None, True, True)
        try:
            txt = ltextEntry.content[4:].decode('unicode_internal')
        except UnicodeDecodeError:
            txt = ltextEntry.content.decode('utf8')

        dlg = EditDialog(self, editUnicodeTitle, txt)
        if dlg.ShowModal() == wx.ID_OK:
            utxt = unicode(dlg.GetValue())
            newVal = utxt.encode('unicode_internal')
            buffer = struct.pack('H', len(utxt))
            buffer += struct.pack('H', 4096)
            buffer += newVal
            ltextEntry.content = ltextEntry.rawContent = buffer
            ltextEntry.Maj()
            self.InternalSave(ltextEntry.fileName)
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
            newValue = dlg.GetValue().encode('utf8')
            try:
                newPropStr = CreateAPropFromString(self.virtualDAT.properties[662775920], newValue)
                if not self.examplar.AddTextProp(newPropStr):
                    dlg.Destroy()
                    return
            except:
                dlg.Destroy()
                raise
                return

            self.listProperties.DeleteAllItems()
            self.bSave.Enable(True)
            self.descriptor.name = self.examplar.GetProp(32)[0]
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
                    return c.examplar.GetProp(32)[0]
                except:
                    return hex2str(c.tgi[0]) + '-' + hex2str(c.tgi[1]) + '-' + hex2str(c.tgi[2])

            lst2 = [ [CohortName(c), c] for c in self.virtualDAT.cohorts ]
            lst2.sort(cmp=lambda x, y: cmp(x[0], y[0]))
            lst = lst + lst2
            dlg = wx.SingleChoiceDialog(self, chooseParentCohortMsg, 'PIMX', [ l[0] for l in lst ])
            if dlg.ShowModal() == wx.ID_OK:
                if dlg.GetSelection() == 0:
                    self.examplar.parentCohort = (0, 0, 0)
                else:
                    self.examplar.parentCohort = lst[dlg.GetSelection()][1].tgi
                self.examplar.LinkToParent()
                self.examplar.modified = True
                self.bSave.Enable(True)
                self.parent.parent.tree.Recategorize(self.descriptor)
                self.listProperties.DeleteAllItems()
                self.FillTheList()
            dlg.Destroy()
        else:
            self.examplar.parentCohort = (0, 0, 0)
            self.examplar.LinkToParent()
            self.examplar.modified = True
            self.bSave.Enable(True)
            self.parent.parent.tree.Recategorize(self.descriptor)
            self.listProperties.DeleteAllItems()
            self.FillTheList()
        return

    def OnActivated(self, event):
        allowedPropEdit = [
         32, 662775824, 2308635565L, 2317746857L, 2317746872L, 1246398704, 1771767972, 2297284498L, 3919251084L, 2297284501L, 2297284502L, 662775920, 662775825]
        listItems = event.GetEventObject()
        idx = event.GetIndex()
        if idx < 3:
            if idx == 2:
                self.ChangeCohort()
            return
        if idx - 3 >= len(self.examplar.props):
            if listItems.GetItemData(idx) & 805306368 == 805306368:
                offset = listItems.GetItemData(idx) & 255
                UVNK = self.examplar.GetProp(2319542937L)
                uvnk = self.virtualDAT.getEntry(UVNK[0], UVNK[1] + offset, UVNK[2])
                if self.OnEditLTEXT(uvnk):
                    self.listProperties.DeleteAllItems()
                    self.FillTheList()
            elif listItems.GetItemData(idx) & 1073741824 == 1073741824:
                offset = listItems.GetItemData(idx) & 255
                IDK = self.examplar.GetProp(3393284789L)
                idk = self.virtualDAT.getEntry(IDK[0], IDK[1] + offset, IDK[2])
                if self.OnEditLTEXT(idk):
                    self.listProperties.DeleteAllItems()
                    self.FillTheList()
            return
        title = self.examplar.GetProp(32)[0]
        prop = self.examplar.props[idx - 3]
        if not bAdvancedUser:
            if prop.id not in allowedPropEdit:
                return
        if prop.id == 662775825:
            self.OnRebuildProperties(1)
            return
        try:
            name = self.virtualDAT.properties[prop.id].Name
        except KeyError:
            name = '0x%08X' % prop.id

        value = prop.ToStr()
        msg = valuePropertyMsg % name
        dlg = wx.TextEntryDialog(self, msg, title, value)
        if dlg.ShowModal() == wx.ID_OK:
            newValue = dlg.GetValue().encode('utf8')
            newPropStr = CreateAPropFromString(self.virtualDAT.properties[prop.id], newValue)
            try:
                newProp = Prop(newPropStr, False, self.examplar)
            except:
                dlg.Destroy()
                raise
                return

            self.examplar.props[idx - 3] = newProp
            self.examplar.modified = True
            try:
                name = self.virtualDAT.properties[newProp.id].Name
                formatted = ConvertAPropToReadable(newProp, self.virtualDAT.properties[newProp.id])
            except KeyError:
                name = '0x%08X' % newProp.id
                formatted = newProp.ToStr()

            listItems.SetStringItem(idx, 0, name)
            listItems.SetStringItem(idx, 1, '0x%08X' % newProp.id)
            listItems.SetStringItem(idx, 2, '%s' % Prop.format2String[newProp.typeValue])
            listItems.SetStringItem(idx, 3, '%d' % len(newProp.values))
            listItems.SetStringItem(idx, 4, '%s' % formatted)
            self.bSave.Enable(True)
            self.descriptor.name = self.examplar.GetProp(32)[0]
            self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
            self.parent.parent.listItems.Refresh()
            self.listProperties.DeleteAllItems()
            self.FillTheList()
            item = self.parent.parent.tree.GetSelection()
            try:
                data = self.parent.parent.tree.GetPyData(item)
            except:
                data = None

            if data:
                if data.__class__.__name__ == 'list':
                    self.parent.parent.FillItemsListModel(data)
                elif data.__class__.__name__ == 'DictWrapper':
                    self.parent.parent.FillItemsList(data)
        dlg.Destroy()
        return

    def InternalSave(self, fileName):
        preventFilename = [ 'simcity_%d.dat' % x for x in xrange(1, 6) ]
        preventFilename += ['ep1.dat', 'sounds.dat', 'intro.dat', 'loteditor.dat']
        preventFilename = [ x.upper() for x in preventFilename ]
        if os.path.split(fileName)[1].upper() in preventFilename:
            dlg = wx.MessageDialog(self, "You can't save %s" % fileName, 'Legacy file error', wx.OK | wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
            return
        entries = self.virtualDAT.GetAllEntriesFromFile(fileName)
        nbrOfLots = 0
        lotName = ''
        lotID = 0
        b2Remove = False
        oldFileName = fileName
        for entry in entries:
            entry.ReadFile(None, True, False)
            if entry.tgi[0] == 1697917002 and entry.tgi[1] == 2835075954L:
                nbrOfLots += 1
                lotName = entry.examplar.GetProp(32)[0]
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
        filename = self.examplar.entry.fileName
        preventFilename = [ 'simcity_%d.dat' % x for x in xrange(1, 6) ]
        preventFilename += ['ep1.dat', 'sounds.dat', 'intro.dat', 'loteditor.dat']
        preventFilename = [ x.upper() for x in preventFilename ]
        if os.path.split(filename)[1].upper() in preventFilename:
            dlg = wx.MessageDialog(self, "You can't save %s" % filename, 'Legacy file error', wx.OK | wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
            return
        self.examplar.Maj()
        self.InternalSave(self.examplar.entry.fileName)
        self.bSave.Enable(False)
        IID = self.examplar.entry.tgi[2]
        texEntry = VirtualDat.this.getEntry(2238569388L, 1782082854, IID)
        if texEntry != None:
            texEntry.content = texEntry.rawContent = None
        self.descriptor.name = self.examplar.GetProp(32)[0]
        self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
        self.parent.parent.listItems.Refresh()
        self.listProperties.DeleteAllItems()
        self.FillTheList()
        item = self.parent.parent.tree.GetSelection()
        try:
            data = self.parent.parent.tree.GetPyData(item)
        except:
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
            self.popupID16 = wx.NewId()
            self.popupID14 = wx.NewId()
            self.popupID15 = wx.NewId()
            self.popupID17 = wx.NewId()
            self.popupID18 = wx.NewId()
            self.popupID19 = wx.NewId()
            self.popupID20 = wx.NewId()
            self.popupID21 = wx.NewId()
            self.popupID22 = wx.NewId()
            self.popupID23 = wx.NewId()
            self.popupID24 = wx.NewId()
            self.popupID25 = wx.NewId()
            self.popupID26 = wx.NewId()
            self.popupID27 = wx.NewId()
            self.popupID28 = wx.NewId()
            self.popupID29 = wx.NewId()
            self.popupID30 = wx.NewId()
            self.popupID31 = wx.NewId()
            self.popupID32 = wx.NewId()
            self.popupID33 = wx.NewId()
            self.popupID34 = wx.NewId()
            self.popupID35 = wx.NewId()
            self.popupID36 = wx.NewId()
            self.popupID37 = wx.NewId()
            self.popupID1 = wx.NewId()
            self.popupID2 = wx.NewId()
            self.popupID3 = wx.NewId()
            self.popupID4 = wx.NewId()
            self.popupID5 = wx.NewId()
            self.popupID6 = wx.NewId()
            self.popupID7 = wx.NewId()
            self.popupID8 = wx.NewId()
            self.popupID9 = wx.NewId()
            self.popupID10 = wx.NewId()
            self.popupID11 = wx.NewId()
            self.popupID12 = wx.NewId()
            self.popupID13 = wx.NewId()
            self.AddLangUVNK_IDs = [ wx.NewId() for i in offsetGID ]
            for idP in self.AddLangUVNK_IDs:
                self.Bind(wx.EVT_MENU, self.OnAddLangUVNK, id=idP)

            self.AddLangIDK_IDs = [ wx.NewId() for i in offsetGID ]
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
        if IsFromCategory(self.virtualDAT.categories[2895100787L], self.examplar) and self.examplar.GetProp(2319542937L) == None:
            if not bSep:
                bSep = True
                menu.AppendSeparator()
            menu.Append(self.popupID6, popupPropertyMenuItem6)
        if IsFromCategory(self.virtualDAT.categories[210746660], self.examplar) and self.examplar.GetProp(2319542937L) == None:
            if not bSep:
                bSep = True
                menu.AppendSeparator()
            menu.Append(self.popupID6, popupPropertyMenuItem6)
        if self.examplar.GetProp(16)[0] == 30:
            bUVNK = True
            if self.examplar.GetProp(2319542937L) == None:
                bUVNK = False
            if self.examplar.GetProp(2319542937L) == [0, 0, 0]:
                bUVNK = False
            if self.examplar.GetProp(2308635565L) == None and not bUVNK:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID5, popupPropertyMenuItem5)
            if not bUVNK:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID6, popupPropertyMenuItem6)
        if self.examplar.GetProp(2319542937L) != None:
            UVNK = self.examplar.GetProp(2319542937L)
            if UVNK[0] == 539399691:
                uvnks = [ self.virtualDAT.getEntry(UVNK[0], UVNK[1] + i, UVNK[2]) for i in offsetGID ]
                submenu = wx.Menu()
                bAddSub = False
                for i, uvnk in enumerate(uvnks):
                    if uvnk == None:
                        submenu.Append(self.AddLangUVNK_IDs[i], namedLang[i])
                        bAddSub = True

                if bAddSub:
                    if not bSep:
                        bSep = True
                        menu.AppendSeparator()
                    menu.AppendMenu(self.popupID7, popupPropertyMenuItem7, submenu)
        if IsFromCategory(self.virtualDAT.categories[3431971885L], self.examplar) and self.examplar.GetProp(3928360329L) and self.examplar.GetProp(3928360329L)[0] != 0:
            if self.examplar.GetProp(2308635565L) == None and self.examplar.GetProp(2319542937L) == None:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID5, popupPropertyMenuItem5)
            if self.examplar.GetProp(2308635565L) != None and self.examplar.GetProp(2319542937L) == None:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID6, popupPropertyMenuItem6)
            if self.examplar.GetProp(2317746857L) == None and self.examplar.GetProp(3393284789L) == None:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID8, popupPropertyMenuItem8)
            if self.examplar.GetProp(2317746857L) != None and self.examplar.GetProp(3393284789L) == None:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID9, popupPropertyMenuItem9)
            if self.examplar.GetProp(3393284789L) != None:
                IDK = self.examplar.GetProp(3393284789L)
                if IDK[0] == 539399691:
                    idks = [ self.virtualDAT.getEntry(IDK[0], IDK[1] + i, IDK[2]) for i in offsetGID ]
                    submenu = wx.Menu()
                    bAddSub = False
                    for i, idk in enumerate(idks):
                        if idk == None:
                            submenu.Append(self.AddLangIDK_IDs[i], namedLang[i])
                            bAddSub = True

                    if bAddSub:
                        if not bSep:
                            bSep = True
                            menu.AppendSeparator()
                        menu.AppendMenu(self.popupID10, popupPropertyMenuItem10, submenu)
        if bAdvancedUser:
            if IsFromCategory(self.virtualDAT.categories[3431971885L], self.examplar):
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID26, popupPropertyMenuItem26)
            else:
                bSep = False
                propFamilies = self.examplar.GetProp(662775920)
                if propFamilies:
                    if not bSep:
                        bSep = True
                        menu.AppendSeparator()
                    submenu = wx.Menu()
                    for i, family in enumerate(propFamilies):
                        submenu.Append(self.popupID13 + i, '0x%08X' % family)
                        self.Bind(wx.EVT_MENU, self.OnOpenFamily, id=self.popupID13 + i)

                    menu.AppendMenu(self.popupID12, popupPropertyMenuItem12, submenu)
                if self.examplar.GetProp(16)[0] == 2 or self.examplar.GetProp(16)[0] == 30:
                    if self.examplar.GetProp(662775920) == None:
                        if not bSep:
                            bSep = True
                            menu.AppendSeparator()
                        menu.Append(self.popupID25, popupPropertyMenuItem25)
        if self.examplar.GetProp(16)[0] == 30:
            if not bSep:
                bSep = True
                menu.AppendSeparator()
            menu.Append(self.popupID36, popupPropertyMenuItem36)
        if self.examplar.GetProp(16)[0] == 2:
            if not bSep:
                bSep = True
                menu.AppendSeparator()
            menu.Append(self.popupID17, popupPropertyMenuItem17)
            if IsFromCategory(self.virtualDAT.categories[749358634], self.examplar) and self.examplar.entry.tgi[0] == 1697917002:
                menu.Append(self.popupID28, popupPropertyMenuItem28)
            if IsFromCategory(self.virtualDAT.categories[2895100787L], self.examplar) and self.examplar.entry.tgi[0] == 1697917002:
                menu.Append(self.popupID28, popupPropertyMenuItem28)
            if IsFromCategory(self.virtualDAT.categories[3431971885L], self.examplar) and self.examplar.entry.tgi[0] == 1697917002:
                menu.Append(self.popupID29, popupPropertyMenuItem29)
        if IsFromCategory(self.virtualDAT.categories[2895100787L], self.examplar):
            if not IsFromCategoryDesc(self.virtualDAT.categories[749358634], self.descriptor):
                if not IsFromCategoryDesc(self.virtualDAT.categories[2358230027L], self.descriptor):
                    if not bSep:
                        bSep = True
                        menu.AppendSeparator()
                    menu.Append(self.popupID34, popupPropertyMenuItem34)
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID37, 'CAM Stage')
        bSep = False
        if self.examplar.GetProp(662775824) != None:
            if not bSep:
                bSep = True
                menu.AppendSeparator()
            menu.Append(self.popupID16, popupPropertyMenuItem16)
        bCategorized, includedCats = GetCategories(self.virtualDAT.rootCategory, self.descriptor)
        if bCategorized and len(includedCats) > 0:
            if not bSep:
                bSep = True
                menu.AppendSeparator()
            menu.Append(self.popupID14, popupPropertyMenuItem14 % includedCats[0][0])
        bSep = False
        if self.examplar.GetProp(16)[0] != 16:
            if self.examplar.GetProp(662775840) == None and self.examplar.GetProp(662775843) == None:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID20, popupPropertyMenuItem20)
            if self.examplar.GetProp(662775841) == None and self.examplar.GetProp(662775843) == None:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID21, popupPropertyMenuItem21)
            if self.examplar.GetProp(662775844) == None and self.examplar.GetProp(662775843) == None:
                if not bSep:
                    bSep = True
                    menu.AppendSeparator()
                menu.Append(self.popupID24, popupPropertyMenuItem24)
        bSep = False
        if self.examplar.GetProp(16)[0] == 16:
            if not bSep:
                bSep = True
                menu.AppendSeparator()
            menu.Append(self.popupID18, popupPropertyMenuItem18)
            menu.Append(self.popupID19, popupPropertyMenuItem19)
            menu.Append(self.popupID27, popupPropertyMenuItem27)
            bSep = False
            desc = self.virtualDAT.FindBuildingFromLot(self.examplar)
            if desc:
                if desc.examplar.entry.tgi[0] == 1697917002:
                    if desc in self.virtualDAT.categories[3431971885L].descriptors:
                        if not bSep:
                            bSep = True
                            menu.AppendSeparator()
                        menu.Append(self.popupID30, popupPropertyMenuItem30)
                        menu.Append(self.popupID35, popupPropertyMenuItem35)
                    if desc in self.virtualDAT.categories[3540939231L].descriptors:
                        if not bSep:
                            bSep = True
                            menu.AppendSeparator()
                        menu.Append(self.popupID30, popupPropertyMenuItem30)
                    if desc in self.virtualDAT.categories[2895100787L].descriptors:
                        if not bSep:
                            bSep = True
                            menu.AppendSeparator()
                        menu.Append(self.popupID31, popupPropertyMenuItem31)
        self.PopupMenu(menu)
        menu.Destroy()
        return

    def OnChangeIcon(self, event):
        IID = self.examplar.entry.tgi[2]
        texEntry = VirtualDat.this.getEntry(2238569388L, 1782082854, IID)
        img = None
        if texEntry != None:
            try:
                if texEntry.content == None:
                    texEntry.ReadFile(None, True, True)
            except:
                texEntry.ReadFile(None, True, True)

            cIO = StringIO(texEntry.content)
            try:
                img = Image.open(cIO).convert('RGB')
            except:
                pass

            cIO.close()
        dlg = SC4IconMakerDlg.IconDlg(self, img)
        if dlg.ShowModal() == wx.ID_OK:
            if dlg.image != None:
                iconImage = dlg.image
                cIO = StringIO()
                iconImage.save(cIO, 'PNG')
                strIcon = cIO.getvalue()
                IID = self.examplar.entry.tgi[2]
                buffer = struct.pack('III', 2238569388L, 1782082854, IID)
                buffer += struct.pack('II', 0, len(strIcon))
                iconEntry = SC4Entry(buffer, 0, self.examplar.entry.fileName)
                iconEntry.content = iconEntry.rawContent = strIcon[:]
                self.virtualDAT.addEntries([iconEntry], None, False, False)
                cIO.close()
                self.bSave.Enable(True)
        dlg.Destroy()
        return

    def OnTileset(self, event):
        lst = [
         'Chicago', 'New york', 'Houston', 'Euro']
        ogs = [8192, 8193, 8194, 8195]
        dlg = wx.MultiChoiceDialog(self, 'Choose tileset', 'PIMX', lst)
        currentOgs = self.examplar.GetProp(2854081430L)
        selected = []
        for i, o in enumerate(ogs):
            if o in currentOgs:
                selected.append(i)

        dlg.SetSelections(selected)
        if dlg.ShowModal() == wx.ID_OK:
            nonTilesetOGs = [ x for x in currentOgs if x not in ogs ]
            selections = dlg.GetSelections()
            tileset = [ ogs[x] for x in selections ]
            finalOgs = nonTilesetOGs + tileset
            finalOgs.sort()
            prop = CreateAProp(self.virtualDAT.properties[2854081430L], tuple(finalOgs))
            self.examplar.AddTextProp(prop)
            self.listProperties.DeleteAllItems()
            self.FillTheList()
            self.bSave.Enable(True)
            self.descriptor.name = self.examplar.GetProp(32)[0]
            self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
            self.parent.parent.listItems.Refresh()
        dlg.Destroy()

    def OnCamStage(self, event):
        lots = self.virtualDAT.FindAllLotsFromBuilding(self.examplar)
        if IsFromCategory(self.virtualDAT.categories[747617173], self.examplar):
            needed = 3049261992L
            lowStage = 9
        if IsFromCategory(self.virtualDAT.categories[1821359013], self.examplar):
            needed = 3049262000L
            lowStage = 9
        if IsFromCategory(self.virtualDAT.categories[210746286], self.examplar):
            needed = 3049262008L
            lowStage = 9
        if IsFromCategory(self.virtualDAT.categories[2358229964L], self.examplar):
            needed = 3049261736L
            lowStage = 9
        if IsFromCategory(self.virtualDAT.categories[210746332], self.examplar):
            needed = 3049261744L
            lowStage = 9
        if IsFromCategory(self.virtualDAT.categories[2895100907L], self.examplar):
            needed = 3049261752L
            lowStage = 9
        if IsFromCategory(self.virtualDAT.categories[1821359093], self.examplar):
            needed = 3049261760L
            lowStage = 9
        if IsFromCategory(self.virtualDAT.categories[3431971841L], self.examplar):
            needed = 3049261768L
            lowStage = 9
        if IsFromCategory(self.virtualDAT.categories[749358378], self.examplar):
            needed = 3049262112L
            lowStage = 1
        if IsFromCategory(self.virtualDAT.categories[747617303], self.examplar):
            needed = 3049262760L
            lowStage = 4
        if IsFromCategory(self.virtualDAT.categories[1820235835], self.examplar):
            needed = 3049262768L
            lowStage = 4
        if IsFromCategory(self.virtualDAT.categories[1821359580], self.examplar):
            needed = 3049262776L
            lowStage = 4
        ogs = range(needed + 1, needed + 8)
        lst = [ self.virtualDAT.properties[2854081430L].Options[x] for x in ogs ]
        dlg = wx.MultiChoiceDialog(self, 'Choose CAM Stage', 'PIMX', lst)
        currentOgs = self.examplar.GetProp(2854081430L)
        selected = []
        for i, o in enumerate(ogs):
            if o in currentOgs:
                selected.append(i)

        for lot in lots:
            stage = lot.examplar.GetProp(662775863)[0]
            if stage >= lowStage:
                stage -= lowStage
                if stage not in selected:
                    selected.append(stage)

        dlg.SetSelections(selected)
        if dlg.ShowModal() == wx.ID_OK:
            nonTilesetOGs = [ x for x in currentOgs if x not in ogs ]
            selections = dlg.GetSelections()
            tileset = [ ogs[x] for x in selections ]
            if needed != 3049262112L:
                tileset.append(needed)
            finalOgs = nonTilesetOGs + tileset
            finalOgs.sort()
            prop = CreateAProp(self.virtualDAT.properties[2854081430L], tuple(finalOgs))
            self.examplar.AddTextProp(prop)
            self.listProperties.DeleteAllItems()
            self.FillTheList()
            self.bSave.Enable(True)
            self.descriptor.name = self.examplar.GetProp(32)[0]
            self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
            self.parent.parent.listItems.Refresh()
        dlg.Destroy()

    def OnRemoveUVNK(self, event):
        pass

    def OnRemoveUVNKTrans(self, event):
        pass

    def OnRecomputeStage(self, event):
        descBuilding = self.virtualDAT.FindBuildingFromLot(self.examplar)
        dlg = LotCreatorDlg(self, descBuilding.examplar, self.virtualDAT, True, True, self.examplar.GetProp(2297284496L))
        if dlg.ShowModal() == wx.ID_OK:
            stage = int(dlg.stageCtrl.GetValue())
            newProp = CreateAProp(self.virtualDAT.properties[662775863], (stage,))
            self.examplar.AddTextProp(newProp)
            purposes = {1: 'R',2: 'CS',3: 'CO',7: 'IM',6: 'ID',8: 'IHT',5: 'IR'}
            purpose = self.examplar.GetProp(2297284502L)[0]
            zoning = self.virtualDAT.ComputeZoning(purposes[purpose], descBuilding.examplar.GetProp(662775824)[1])
            newProp = CreateAProp(self.virtualDAT.properties[2297284499L], tuple(zoning))
            self.examplar.AddTextProp(newProp)
            self.listProperties.DeleteAllItems()
            self.FillTheList()
            self.bSave.Enable(True)
            self.descriptor.name = self.examplar.GetProp(32)[0]
            self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
            self.parent.parent.listItems.Refresh()

    def OnPlop2Grow(self, event):
        lst = [
         'R$', 'R$$', 'R$$$', 'CS$', 'CS$$', 'CS$$$', 'CO$$', 'CO$$$', 'IA', 'ID Anchor', 'ID Mech', 'ID Out', 'IM Anchor', 'IM Mech', 'IM Out', 'IHT Anchor', 'IHT Mech', 'IHT Out']
        name2Cat = {'R$': 747617173,'R$$': 1821359013,'R$$$': 210746286,'CS$': 2358229964L,'CS$$': 210746332,'CS$$$': 2895100907L,'CO$$': 1821359093,'CO$$$': 3431971841L,'IA': 749358378,'ID Anchor': 747617304,'ID Mech': 747617305,'ID Out': 747617306,'IM Anchor': 1820235836,'IM Mech': 1820235837,'IM Out': 1820235838,'IHT Anchor': 1821359581,'IHT Mech': 1821359582,'IHT Out': 1821359583}
        dlg1 = wx.SingleChoiceDialog(self, 'Choose the category you want the new lot to be based on', 'Plop lot creation', lst, wx.CHOICEDLG_STYLE)
        if dlg1.ShowModal() == wx.ID_OK:
            selected = dlg1.GetStringSelection()
            cat = name2Cat[selected]
            oldBuildingDesc = self.virtualDAT.FindBuildingFromLot(self.examplar)
            rkt0 = oldBuildingDesc.examplar.GetProp(662775840)
            rkt1 = oldBuildingDesc.examplar.GetProp(662775841)
            rkt = rkt0
            if rkt == None:
                rkt = rkt1
            newBuildingDesc = self.parent.parent.CreateAnExamplar(oldBuildingDesc.examplar.GetProp(32)[0] + '_GROW', rkt, oldBuildingDesc.examplar.GetProp(662775824), self.virtualDAT.categories[cat], oldBuildingDesc.examplar.GetProp(662775825))
            lotDimensions = self.examplar.GetProp(2297284496L)
            width = lotDimensions[0]
            depth = lotDimensions[1]
            stage, purpose, wealth = ComputeStagePurposeWealth(newBuildingDesc.examplar.GetProp(662775860), newBuildingDesc.examplar.GetProp(2854081430L), lotDimensions[0], lotDimensions[1])
            IID = newBuildingDesc.examplar.entry.tgi[2]
            fileNameBase = '%s%s%s_%sx%s_%s' % (purpose, '$' * (wealth + 1), stage, width, depth, newBuildingDesc.examplar.GetProp(32)[0])
            buffer = struct.pack('III', 1697917002, 2835075954L, IID)
            buffer += struct.pack('II', 0, 0)
            entry = SC4Entry(buffer, 0, os.path.join(self.parent.parent.rootFolder, '%s_%08x.SC4Lot' % (fileNameBase, IID)))
            props = []
            purposes = {'R': 1,'CS': 2,'CO': 3,'IM': 7,'ID': 6,'IHT': 8,'IR': 5}

            def CopyPropOrDefault(propID, defaultValue):
                if self.examplar.GetProp(propID) == None:
                    return defaultValue
                return self.examplar.GetProp(propID)

            props.append(CreateAProp(self.virtualDAT.properties[16], (16, )))
            props.append(CreateAPropFromString(self.virtualDAT.properties[32], str(fileNameBase)))
            props.append(CreateAProp(self.virtualDAT.properties[662775863], (int(stage),)))
            props.append(CreateAProp(self.virtualDAT.properties[1246398704], CopyPropOrDefault(1246398704, (8, ))))
            props.append(CreateAProp(self.virtualDAT.properties[2297284489L], (2, )))
            props.append(CreateAProp(self.virtualDAT.properties[2297284496L], (int(width), int(depth))))
            zoning = self.virtualDAT.ComputeZoning(purpose, newBuildingDesc.examplar.GetProp(662775824)[1])
            props.append(CreateAProp(self.virtualDAT.properties[2297284499L], tuple(zoning)))
            props.append(CreateAProp(self.virtualDAT.properties[2297284501L], (wealth + 1,)))
            props.append(CreateAProp(self.virtualDAT.properties[2297284502L], (purposes[purpose],)))
            props.append(CreateAProp(self.virtualDAT.properties[3420603383L], (1, )))
            props.append(CreateAProp(self.virtualDAT.properties[1771767972], CopyPropOrDefault(1771767972, (0.0, ))))
            props.append(CreateAProp(self.virtualDAT.properties[2297284498L], CopyPropOrDefault(2297284498L, (90.0, ))))
            props.append(CreateAProp(self.virtualDAT.properties[2297284504L], CopyPropOrDefault(2297284504L, (3379372341L, ))))
            props.append(CreateAProp(self.virtualDAT.properties[2298271863L], CopyPropOrDefault(2298271863L, (2299228948L, ))))
            props.append(CreateAProp(self.virtualDAT.properties[3919251084L], CopyPropOrDefault(3919251084L, (90.0, ))))
            for lcp in range(2297284864L, 2297286143L):
                z = self.examplar.GetProp(lcp)
                if z == None:
                    break
                v = z[:]
                if v[0] == 0:
                    v[12] = IID
                if v[0] == 7:
                    continue
                props.append(CreateAProp(self.virtualDAT.properties[lcp], v))

            props.sort(cmp=lambda x, y: cmp(x[2:2 + 8], y[2:2 + 8]))
            buffer = 'EQZT1###\r\n' + 'ParentCohort=Key:{0x00000000,0x00000000,0x00000000}\r\n' + 'PropCount=0x%08x\r\n' % len(props)
            buffer += '\r\n'.join(props)
            entry.content = entry.rawContent = buffer
            examplar = Examplar(entry, self.virtualDAT)
            examplar.entry = entry
            entry.examplar = examplar
            lotDescriptor = LotDesc(entry)
            entries = [entry]
            entry.examplar.Maj()
            WriteADat(entry.fileName, entries, None, True)
            self.virtualDAT.addEntries(entries, None, False, False)
            self.parent.parent.tree.Recategorize(lotDescriptor, False)
            self.parent.AddNewDesc(lotDescriptor, self.virtualDAT, False)
            frame = LotEditorWin(self, -1, 'LotPreview ' + lotDescriptor.name, size=(800,
                                                                                     800))
            frame.Display(entry.examplar, self.virtualDAT)
            frame.Show()
            frame.Destroy()
        dlg1.Destroy()
        return

    def OnUpdateIcon(self, image):
        template = Image.open('IconTpl.png')
        mask = Image.open('IconMaskTpl.png').convert('L')
        iconImage = Image.new('RGBA', (44 * 4, 44))
        iconImage.paste(image, (0, 0))
        iconImage.paste(image, (44, 0))
        iconImage.paste(image, (88, 0))
        iconImage.paste(image, (44 * 3, 0))
        iconImage = Image.composite(iconImage, template, mask)
        cIO = StringIO()
        iconImage.save(cIO, 'PNG')
        strIcon = cIO.getvalue()
        IID = self.examplar.entry.tgi[2]
        buffer = struct.pack('III', 2238569388L, 1782082854, IID)
        buffer += struct.pack('II', 0, len(strIcon))
        iconEntry = SC4Entry(buffer, 0, self.examplar.entry.fileName)
        iconEntry.content = iconEntry.rawContent = strIcon[:]
        self.virtualDAT.addEntries([iconEntry], None, False, False)
        cIO.close()
        return iconImage

    def OnCreatePlopLot(self, event):
        dlg = LotCreatorDlg(self, self.examplar, self.virtualDAT, False)
        if dlg.ShowModal() == wx.ID_OK:
            init = datetime.datetime(2005, 5, 5, 21, 24, 15)
            today = datetime.datetime.today()
            dt = today - init
            dt = dt.days * 24 * 3600 + dt.seconds
            first = random.randrange(0, 15)
            IID = first * 268435456 + (dt & 268435455)
            fileNameBase = 'PLOP_%sx%s_%s' % (dlg.widthCtrl.GetValue(), dlg.depthCtrl.GetValue(), self.examplar.GetProp(32)[0])
            buffer = struct.pack('III', 1697917002, 2835075954L, IID)
            buffer += struct.pack('II', 0, 0)
            entry = SC4Entry(buffer, 0, os.path.join(self.parent.parent.rootFolder, '%s_%08x.SC4Lot' % (fileNameBase, IID)))
            props = []
            props.append(CreateAProp(self.virtualDAT.properties[16], (16, )))
            props.append(CreateAPropFromString(self.virtualDAT.properties[32], str(fileNameBase)))
            if IsFromCategory(self.virtualDAT.categories[3434232095L], self.examplar):
                bFound = False
                for stage in xrange(1, 16):
                    if IsFromCategory(self.virtualDAT.categories[3434232096L + stage], self.examplar):
                        props.append(CreateAProp(self.virtualDAT.properties[662775863], (stage,)))
                        bFound = True
                        break

                bFound or props.append(CreateAProp(self.virtualDAT.properties[662775863], (255, )))
        if IsFromCategory(self.virtualDAT.categories[210746672], self.examplar):
            bFound = False
            for stage in xrange(1, 16):
                if IsFromCategory(self.virtualDAT.categories[210746672 + stage], self.examplar):
                    props.append(CreateAProp(self.virtualDAT.properties[662775863], (stage,)))
                    bFound = True
                    break

            if not bFound:
                props.append(CreateAProp(self.virtualDAT.properties[662775863], (255, )))
        else:
            if IsFromCategory(self.virtualDAT.categories[210746652], self.examplar):
                stages = {210746657: 1,210746658: 2,210746659: 3,210746695: 1,210746697: 2,210746700: 3}
                bFound = False
                for catID, stage in stages.iteritems():
                    if IsFromCategory(self.virtualDAT.categories[catID], self.examplar):
                        props.append(CreateAProp(self.virtualDAT.properties[662775863], (stage,)))
                        bFound = True
                        break

                if not bFound:
                    props.append(CreateAProp(self.virtualDAT.properties[662775863], (255, )))
            else:
                props.append(CreateAProp(self.virtualDAT.properties[662775863], (255, )))
            props.append(CreateAProp(self.virtualDAT.properties[1246398704], (8, )))
            props.append(CreateAProp(self.virtualDAT.properties[2297284489L], (2, )))
            props.append(CreateAProp(self.virtualDAT.properties[2297284496L], (int(dlg.widthCtrl.GetValue()), int(dlg.depthCtrl.GetValue()))))
            if IsFromCategory(self.virtualDAT.categories[210746652], self.examplar):
                props.append(CreateAProp(self.virtualDAT.properties[2297284499L], (11, )))
            else:
                if IsFromCategory(self.virtualDAT.categories[3434232095L], self.examplar):
                    props.append(CreateAProp(self.virtualDAT.properties[2297284499L], (12, )))
                else:
                    props.append(CreateAProp(self.virtualDAT.properties[2297284499L], (15, )))
                props.append(CreateAProp(self.virtualDAT.properties[2297284501L], (0, )))
                props.append(CreateAProp(self.virtualDAT.properties[2297284502L], (0, )))
                props.append(CreateAProp(self.virtualDAT.properties[3420603383L], (1, )))
                currentID = 2297284864L
                objID = dt & 16777215
                lotwidth = int(dlg.widthCtrl.GetValue())
                lotdepth = int(dlg.depthCtrl.GetValue())
                buildwidth = (self.examplar.GetProp(662775824)[0] + 0.3) / 16.0
                builddepth = (self.examplar.GetProp(662775824)[2] + 0.3) / 16.0
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
                families = self.examplar.GetProp(662775920)
                buildingID = IID
                if families != None:
                    lst = [
                     'This building only'] + [ 'Family %s' % hex2str(f) for f in families ]
                    dlg1 = wx.SingleChoiceDialog(self, 'Choose the building or family you want to put on this lot', 'Lot Creation', lst, wx.CHOICEDLG_STYLE)
                    if dlg1.ShowModal() == wx.ID_OK:
                        selected = dlg1.GetStringSelection()
                        if selected != 'This building only':
                            buildingID = int(selected[7:], 16)
                        dlg1.Destroy()
                    else:
                        return
                v = [
                 0, 0, 2, posX, 0, posY, xmin, ymin, xmax, ymax, 0, objID, buildingID]
                props.append(CreateAProp(self.virtualDAT.properties[currentID], v))
                currentID += 1
                objID += 1
                baseTex = self.virtualDAT.baseTex[('None', 0)]
                for h in xrange(0, lotdepth):
                    for w in xrange(0, lotwidth):
                        v = [
                         2, 0, 0, w * 1048576 + 524288, 0, h * 1048576 + 524288, w * 1048576, h * 1048576, (w + 1) * 1048576, (h + 1) * 1048576, 0, objID, baseTex]
                        props.append(CreateAProp(self.virtualDAT.properties[currentID], v))
                        currentID += 1
                        objID += 1

                LotSizeX = lotwidth
                LotSizeY = lotdepth
                Width = self.examplar.GetProp(662775824)[0]
                Depth = self.examplar.GetProp(662775824)[2]
                Height = self.examplar.GetProp(662775824)[1]
                MaxSlopeBeforeLotFoundation = eval(self.virtualDAT.MaxSlopeBeforeLotFoundation)
                MaxSlopeAllowed = eval(self.virtualDAT.MaxSlopeAllowed)
                if IsFromCategory(self.virtualDAT.categories[3434232095L], self.examplar):
                    MaxSlopeBeforeLotFoundation = 0
            props.append(CreateAProp(self.virtualDAT.properties[1771767972], (0.0, )))
            props.append(CreateAProp(self.virtualDAT.properties[2297284498L], (MaxSlopeBeforeLotFoundation,)))
            props.append(CreateAProp(self.virtualDAT.properties[2297284504L], (3379372341L, )))
            props.append(CreateAProp(self.virtualDAT.properties[2298271863L], (2299228948L, )))
            props.append(CreateAProp(self.virtualDAT.properties[3919251084L], (MaxSlopeAllowed,)))
            props.sort(cmp=lambda x, y: cmp(x[2:2 + 8], y[2:2 + 8]))
            buffer = 'EQZT1###\r\n' + 'ParentCohort=Key:{0x00000000,0x00000000,0x00000000}\r\n' + 'PropCount=0x%08x\r\n' % len(props)
            buffer += '\r\n'.join(props)
            entry.content = entry.rawContent = buffer
            examplar = Examplar(entry, self.virtualDAT)
            examplar.entry = entry
            entry.examplar = examplar
            descriptor = LotDesc(entry)
            LotID = IID
            copiedExamplarBuffer = self.examplar.Rep()
            buffer = struct.pack('III', 1697917002, self.examplar.entry.tgi[1], IID)
            buffer += struct.pack('II', 0, 0)
            descEntry = SC4Entry(buffer, 0, os.path.join(self.parent.parent.rootFolder, '%s_%08x.SC4Lot' % (fileNameBase, IID)))
            descEntry.content = descEntry.rawContent = copiedExamplarBuffer
            descExamplar = Examplar(descEntry, self.virtualDAT)
            descExamplar.entry = descEntry
            descEntry.examplar = descExamplar
            descEntry.examplar.AddTextProp(CreateAProp(self.virtualDAT.properties[1787239298], (IID,)))
            descEntry.examplar.AddTextProp(CreateAProp(self.virtualDAT.properties[2317746872L], (IID,)))
            descEntry.examplar.AddTextProp(CreateAProp(self.virtualDAT.properties[3928360329L], (IID,)))
            descEntry.examplar.Maj()
            descDescriptor = BuildingDesc(descEntry)
            self.virtualDAT.addEntries([descEntry], None, False, False)
            self.parent.parent.tree.Recategorize(descDescriptor, False)
            frame = LotEditorWin(self, -1, 'LotPreview ' + descriptor.name, size=(800,
                                                                                  800))
            frame.Display(entry.examplar, self.virtualDAT, True)
            frame.Show()
            frame.OnDraw()
            frame.OnDraw()
            image = frame.Save()
            template = Image.open('IconTpl.png')
            mask = Image.open('IconMaskTpl.png').convert('L')
            iconImage = Image.new('RGBA', (44 * 4, 44))
            iconImage.paste(image, (0, 0))
            iconImage.paste(image, (44, 0))
            iconImage.paste(image, (88, 0))
            iconImage.paste(image, (44 * 3, 0))
            iconImage = Image.composite(iconImage, template, mask)
            cIO = StringIO()
            iconImage.save(cIO, 'PNG')
            strIcon = cIO.getvalue()
            buffer = struct.pack('III', 2238569388L, 1782082854, IID)
            buffer += struct.pack('II', 0, len(strIcon))
            iconEntry = SC4Entry(buffer, 0, os.path.join(self.parent.parent.rootFolder, '%s_%08x.SC4Lot' % (fileNameBase, IID)))
            iconEntry.content = iconEntry.rawContent = strIcon[:]
            cIO.close()
            entries = [entry, descEntry, iconEntry]
            UVNK = self.examplar.GetProp(2319542937L)
            if UVNK != None:
                if UVNK[0] == 539399691:
                    descExamplar.AddTextProp(CreateAProp(self.virtualDAT.properties[2319542937L], (UVNK[0], 1782082854, descExamplar.entry.tgi[2])))
                    uvnks = [ self.virtualDAT.getEntry(UVNK[0], UVNK[1] + i, UVNK[2]) for i in offsetGID ]
                    for i, uvnk in enumerate(uvnks):
                        if uvnk != None:
                            uvnk.ReadFile(None, True, True)
                            try:
                                utxt = uvnk.content[4:].decode('unicode_internal')
                            except UnicodeDecodeError:
                                utxt = uvnk.content.decode('utf8')

                            uvnk.content = uvnk.rawContent = None
                            ltextEnt = self.DuplicateLTEXTEntry(descEntry.examplar, utxt, 539399691, 1782082854 + uvnk.tgi[1] - UVNK[1], descExamplar.entry.tgi[2])
                            entries.append(ltextEnt)

                IDK = self.examplar.GetProp(3393284789L)
                if IDK != None:
                    descExamplar.AddTextProp(CreateAProp(self.virtualDAT.properties[3393284789L], (IDK[0], descExamplar.entry.tgi[1], descExamplar.entry.tgi[2])))
                    idks = [ self.virtualDAT.getEntry(IDK[0], v[1] + i, IDK[2]) for i in offsetGID ]
                    for i, idk in enumerate(idks):
                        if idk != None:
                            idk.ReadFile(None, True, True)
                            try:
                                utxt = idk.content[4:].decode('unicode_internal')
                            except UnicodeDecodeError:
                                utxt = idk.content.decode('utf8')

                            idk.content = idk.rawContent = None
                            ltextEnt = self.DuplicateLTEXTEntry(descEntry.examplar, utxt, 539399691, descExamplar.entry.tgi[1] + idk.tgi[1] - IDK[1], descExamplar.entry.tgi[2])
                            entries.append(ltextEnt)

                descEntry.examplar.Maj()
                entry.examplar.Maj()
                self.virtualDAT.addEntries(entries, None, False, False)
                self.parent.parent.tree.Recategorize(descriptor, False)
                virtualDAT = self.virtualDAT
                parent = self.parent
                dlg.Destroy()
                self.parent.CloseCurrentTab()
                descPage = parent.AddNewDesc(descDescriptor, virtualDAT, False)
                descPage.OnRebuildProperties(None)
                descPage.examplar.Maj()
                descPage.bSave.Enable(False)
                descEntry.examplar.Maj()
                entry.examplar.Maj()
                WriteADat(entry.fileName, entries, None, True)
                parent.AddNewDesc(descriptor, virtualDAT, False)
            dlg.Destroy()
        return

    def OnCreateLot(self, event):
        dlg = LotCreatorDlg(self, self.examplar, self.virtualDAT, True)
        if dlg.ShowModal() == wx.ID_OK:
            init = datetime.datetime(2005, 5, 5, 21, 24, 15)
            today = datetime.datetime.today()
            dt = today - init
            dt = dt.days * 24 * 3600 + dt.seconds
            first = random.randrange(0, 15)
            IID = first * 268435456 + (dt & 268435455)
            fileNameBase = '%s%s%s_%sx%s_%s' % (dlg.purpose, '$' * (dlg.wealth + 1), dlg.stageCtrl.GetValue(), dlg.widthCtrl.GetValue(), dlg.depthCtrl.GetValue(), self.examplar.GetProp(32)[0])
            buffer = struct.pack('III', 1697917002, 2835075954L, IID)
            buffer += struct.pack('II', 0, 0)
            entry = SC4Entry(buffer, 0, os.path.join(self.parent.parent.rootFolder, '%s_%08x.SC4Lot' % (fileNameBase, IID)))
            purposes = {'R': 1,'CS': 2,'CO': 3,'IM': 7,'ID': 6,'IHT': 8,'IR': 5}
            props = []
            props.append(CreateAProp(self.virtualDAT.properties[16], (16, )))
            props.append(CreateAPropFromString(self.virtualDAT.properties[32], str(fileNameBase)))
            props.append(CreateAProp(self.virtualDAT.properties[662775863], (int(dlg.stageCtrl.GetValue()),)))
            props.append(CreateAProp(self.virtualDAT.properties[1246398704], (8, )))
            props.append(CreateAProp(self.virtualDAT.properties[2297284489L], (2, )))
            props.append(CreateAProp(self.virtualDAT.properties[2297284496L], (int(dlg.widthCtrl.GetValue()), int(dlg.depthCtrl.GetValue()))))
            zoning = self.virtualDAT.ComputeZoning(dlg.purpose, self.examplar.GetProp(662775824)[1])
            props.append(CreateAProp(self.virtualDAT.properties[2297284499L], tuple(zoning)))
            props.append(CreateAProp(self.virtualDAT.properties[2297284501L], (dlg.wealth + 1,)))
            props.append(CreateAProp(self.virtualDAT.properties[2297284502L], (purposes[dlg.purpose],)))
            props.append(CreateAProp(self.virtualDAT.properties[3420603383L], (1, )))
            currentID = 2297284864L
            objID = dt & 16777215
            lotwidth = int(dlg.widthCtrl.GetValue())
            lotdepth = int(dlg.depthCtrl.GetValue())
            buildwidth = self.examplar.GetProp(662775824)[0] / 16.0
            builddepth = self.examplar.GetProp(662775824)[2] / 16.0
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
            families = self.examplar.GetProp(662775920)
            buildingID = self.examplar.entry.tgi[2]
            if families != None:
                lst = [
                 'This building only'] + [ 'Family %s' % hex2str(f) for f in families ]
                dlg1 = wx.SingleChoiceDialog(self, 'Choose the building or family you want to put on this lot', 'Lot Creation', lst, wx.CHOICEDLG_STYLE)
                if dlg1.ShowModal() == wx.ID_OK:
                    selected = dlg1.GetStringSelection()
                    if selected != 'This building only':
                        buildingID = int(selected[7:], 16)
                    dlg1.Destroy()
                else:
                    return
            v = [
             0, 0, 2, posX, 0, posY, xmin, ymin, xmax, ymax, 0, objID, buildingID]
            props.append(CreateAProp(self.virtualDAT.properties[currentID], v))
            currentID += 1
            objID += 1
            baseTex = self.virtualDAT.baseTex[dlg.purpose, dlg.wealth]
            for h in xrange(0, lotdepth):
                for w in xrange(0, lotwidth):
                    v = [
                     2, 0, 0, w * 1048576 + 524288, 0, h * 1048576 + 524288, w * 1048576, h * 1048576, (w + 1) * 1048576, (h + 1) * 1048576, 0, objID, baseTex]
                    props.append(CreateAProp(self.virtualDAT.properties[currentID], v))
                    currentID += 1
                    objID += 1

            props.append(CreateAProp(self.virtualDAT.properties[1771767972], (0.0, )))
            LotSizeX = lotwidth
            LotSizeY = lotdepth
            Width = self.examplar.GetProp(662775824)[0] + 0.3
            Depth = self.examplar.GetProp(662775824)[2] + 0.3
            Height = self.examplar.GetProp(662775824)[1]
            MaxSlopeBeforeLotFoundation = eval(self.virtualDAT.MaxSlopeBeforeLotFoundation)
            MaxSlopeAllowed = eval(self.virtualDAT.MaxSlopeAllowed)
            props.append(CreateAProp(self.virtualDAT.properties[2297284498L], (MaxSlopeBeforeLotFoundation,)))
            props.append(CreateAProp(self.virtualDAT.properties[2297284504L], (3379372341L, )))
            props.append(CreateAProp(self.virtualDAT.properties[2298271863L], (2299228948L, )))
            props.append(CreateAProp(self.virtualDAT.properties[3919251084L], (MaxSlopeAllowed,)))
            props.sort(cmp=lambda x, y: cmp(x[2:2 + 8], y[2:2 + 8]))
            buffer = 'EQZT1###\r\n' + 'ParentCohort=Key:{0x00000000,0x00000000,0x00000000}\r\n' + 'PropCount=0x%08x\r\n' % len(props)
            buffer += '\r\n'.join(props)
            entry.content = entry.rawContent = buffer
            examplar = Examplar(entry, self.virtualDAT)
            examplar.entry = entry
            entry.examplar = examplar
            descriptor = LotDesc(entry)
            entries = [entry]
            entry.examplar.Maj()
            WriteADat(entry.fileName, entries, None, True)
            self.virtualDAT.addEntries(entries, None, False, False)
            self.parent.parent.tree.Recategorize(descriptor, False)
            self.parent.AddNewDesc(descriptor, self.virtualDAT, False)
            frame = LotEditorWin(self, -1, 'LotPreview ' + descriptor.name, size=(800,
                                                                                  800))
            frame.Display(entry.examplar, self.virtualDAT)
            frame.Show()
            frame.Destroy()
        dlg.Destroy()
        return

    def OnDependenciesListing(self, event):
        dlg = DependenciesDlg(self.parent.parent, self.examplar)
        dlg.ShowModal()
        dlg.Destroy()

    def OnLotInfoDebug(self, event):
        self.examplar.ReindexLotConfig(True)
        frame = LotEditorWin(self, -1, 'LotPreview ' + self.descriptor.name, size=(800,
                                                                                   800))
        frame.Display(self.examplar, self.virtualDAT)
        frame.Show()
        self.examplar.modified = True
        self.bSave.Enable(True)

    def OnConvertReward(self, event):
        ogs = list(self.examplar.GetProp(2854081430L))
        ogs.append(5387)
        newOGS = CreateAPropFromString(self.virtualDAT.properties[2854081430L], ','.join([ hex2str(v) for v in ogs ]))
        self.examplar.AddTextProp(newOGS)
        cityEx = CreateAPropFromString(self.virtualDAT.properties[3928885131L], hex2str(self.examplar.entry.tgi[2]))
        self.examplar.AddTextProp(cityEx)
        condBuilding = CreateAPropFromString(self.virtualDAT.properties[3929147896L], 'True')
        self.examplar.AddTextProp(condBuilding)
        h = random.randint(0, 15)
        iid = 268435455 & self.examplar.entry.tgi[2]
        buffer = struct.pack('III', 3395543715L, 1247710966, iid)
        newVal = '--#-package:%s# -- package signature'
        newVal = newVal % hex2str(iid)[2:]
        buffer += struct.pack('II', 0, 4 + len(newVal))
        luaEntry = SC4Entry(buffer, 0, self.examplar.entry.fileName)
        buffer = newVal
        luaEntry.content = buffer
        luaEntry.Maj()
        self.virtualDAT.addEntries([luaEntry], None, False, False)
        self.listProperties.DeleteAllItems()
        self.FillTheList()
        self.bSave.Enable(True)
        self.parent.parent.tree.Recategorize(self.descriptor)
        return

    def OnConvertToRKT4(self, event):
        rkt0 = self.examplar.GetProp(662775840)
        rkt1 = self.examplar.GetProp(662775841)
        if rkt0 is not None:
            values = [
             0, 0, 0, 0, 662775840, rkt0[0], rkt0[1], rkt0[2]]
        elif rkt1 is not None:
            values = [
             0, 0, 0, 0, 662775841, rkt1[0], rkt1[1], rkt1[2]]
        else:
            print ' no rkt4 or rkt1'
        newPropStr = CreateAPropFromString(self.virtualDAT.properties[662775844], ','.join([ hex2str(v) for v in values ]))
        try:
            self.examplar.AddTextProp(newPropStr)
            self.examplar.RemoveProp(662775840)
            self.examplar.RemoveProp(662775841)
        except:
            raise
            return

        self.listProperties.DeleteAllItems()
        self.FillTheList()
        self.bSave.Enable(True)
        self.descriptor.name = self.examplar.GetProp(32)[0]
        self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
        self.parent.parent.listItems.Refresh()
        return

    def OnConvertToRKT0(self, event):
        rkt4 = self.examplar.GetProp(662775844)
        rkt1 = self.examplar.GetProp(662775841)
        values = []
        if rkt4 is not None:
            values = [
             rkt4[-3], rkt4[-2], rkt4[-1]]
        elif rkt1 is not None:
            values = [
             rkt1[0], rkt1[1], rkt1[2]]
        else:
            print ' no rkt4 or rkt1'
        newPropStr = CreateAPropFromString(self.virtualDAT.properties[662775840], ','.join([ hex2str(v) for v in values ]))
        try:
            self.examplar.AddTextProp(newPropStr)
            self.examplar.RemoveProp(662775844)
            self.examplar.RemoveProp(662775841)
        except:
            raise
            return

        self.listProperties.DeleteAllItems()
        self.FillTheList()
        self.bSave.Enable(True)
        self.descriptor.name = self.examplar.GetProp(32)[0]
        self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
        self.parent.parent.listItems.Refresh()
        return

    def OnConvertToRKT1(self, event):
        rkt0 = self.examplar.GetProp(662775840)
        rkt4 = self.examplar.GetProp(662775844)
        values = []
        if rkt4 is not None:
            values = [
             rkt4[-3], rkt4[-2], rkt4[-1]]
        elif rkt0 is not None:
            values = [
             rkt0[0], rkt0[1], rkt0[2]]
        else:
            print ' no rkt4 or rkt0'
        newPropStr = CreateAPropFromString(self.virtualDAT.properties[662775841], ','.join([ hex2str(v) for v in values ]))
        try:
            self.examplar.AddTextProp(newPropStr)
            self.examplar.RemoveProp(662775840)
            self.examplar.RemoveProp(662775844)
        except:
            raise
            return

        self.listProperties.DeleteAllItems()
        self.FillTheList()
        self.bSave.Enable(True)
        self.descriptor.name = self.examplar.GetProp(32)[0]
        self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
        self.parent.parent.listItems.Refresh()
        return

    def OnOpenLotWithBuilding(self, event):
        self.openedLots = []
        wx.BeginBusyCursor()
        if self.examplar.GetProp(662775920) != None:
            possibles = list(self.examplar.GetProp(662775920)) + [self.examplar.entry.tgi[2]]
        else:
            possibles = [
             self.examplar.entry.tgi[2]]

        def UseThisIID(desc):
            for lcp in range(2297284864L, 2297286143L):
                values = desc.examplar.GetProp(lcp)
                if values == None:
                    return False
                if values[0] == 0:
                    if values[12] in possibles:
                        return True

            return False

        descs = filter(UseThisIID, self.virtualDAT.categories[210091300].descriptors)
        for desc in descs:
            self.openedLots.append(self.parent.AddNewDesc(desc, self.virtualDAT, False))

        wx.EndBusyCursor()
        return

    def OnOpenLotWithProp(self, event):
        self.openedLots = []
        wx.BeginBusyCursor()
        if self.examplar.GetProp(662775920) != None:
            possibles = list(self.examplar.GetProp(662775920)) + [self.examplar.entry.tgi[2]]
        else:
            possibles = [
             self.examplar.entry.tgi[2]]

        def UseThisIID(desc):
            for lcp in range(2297284864L, 2297286143L):
                values = desc.examplar.GetProp(lcp)
                if values == None:
                    return False
                if values[0] == 1:
                    if values[12] in possibles:
                        return True

            return False

        descs = filter(UseThisIID, self.virtualDAT.categories[210091300].descriptors)
        for desc in descs:
            self.openedLots.append(self.parent.AddNewDesc(desc, self.virtualDAT, False))

        wx.EndBusyCursor()
        return

    def OnBuildingsFromLot(self, event):
        buildingID = None
        for lcp in range(2297284864L, 2297286143L):
            values = self.examplar.GetProp(lcp)
            if values == None:
                break
            if values[0] == 0:
                buildingID = values[12]
                break

        if buildingID == None:
            return
        if buildingID in self.virtualDAT.categories:
            bOk = False
            for desc in self.virtualDAT.categories[buildingID].descriptors:
                if desc.examplar.GetProp(16)[0] == 2:
                    bOk = True
                    self.parent.AddNewDesc(desc, self.virtualDAT, False)

            if bOk:
                return
        possibles = filter(lambda desc: desc.examplar.entry.tgi[2] == buildingID, self.virtualDAT.categories[210746197].descriptors)
        for desc in possibles:
            self.parent.AddNewDesc(desc, self.virtualDAT, False)

        return

    def OnRebuildProperties(self, event):
        bCategorized, includedCats = GetCategories(self.virtualDAT.rootCategory, self.descriptor)
        category = self.virtualDAT.categories[includedCats[0][1]]
        props = []
        IID = self.examplar.entry.tgi[2]
        Height = height = self.examplar.GetProp(662775824)[1]
        Width = width = self.examplar.GetProp(662775824)[0]
        Depth = depth = self.examplar.GetProp(662775824)[2]
        examplarName = self.examplar.GetProp(32)[0]
        try:
            fillingDegree = self.examplar.GetProp(662775825)[0]
        except:
            fillingDegree = 0.5

        LotSizeX = 1
        LotSizeY = 1
        if IsFromCategory(self.virtualDAT.categories[210746197], self.examplar):
            if IsFromCategory(self.virtualDAT.categories[3431971885L], self.examplar):
                lotDesc = self.virtualDAT.FindLotFromBuilding(self.examplar)
                if lotDesc is not None:
                    try:
                        LotSizeX = lotDesc.examplar.GetProp(2297284496L)[0]
                        LotSizeY = lotDesc.examplar.GetProp(2297284496L)[1]
                    except:
                        pass

            if event is not None:
                dlg = wx.TextEntryDialog(self, fillingDegreeMsg, fillingDegreeTitleMsg, str(fillingDegree))
                if dlg.ShowModal() == wx.ID_OK:
                    newValue = dlg.GetValue().encode('utf8')
                    if newValue.__class__ == unicode:
                        pass
                    newPropStr = CreateAPropFromString(self.virtualDAT.properties[662775825], newValue)
                    self.examplar.AddTextProp(newPropStr)
                    fillingDegree = self.examplar.GetProp(662775825)[0]
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

            if cat.parent != None:
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
                    except:
                        print 'Error in eval',
                        print hex2str(prop2CreatID)
                        print initialCode
                        print codetxt
                        print variables
                        raise

                    prop2CreatValue = []
                    if values.__class__ != tuple:
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

                    props.append(CreateAPropFromString(self.virtualDAT.properties[prop2CreatID], ','.join(prop2CreatValue)))

            for prop2CreatID in category.programProperties.keys():
                if prop2CreatID in propCreated:
                    pass
                elif self.examplar.GetProp(prop2CreatID) != None:
                    pass
                else:
                    propCreated.append(prop2CreatID)
                    prop2CreatValue = category.programProperties[prop2CreatID]
                    props.append(CreateAPropFromString(self.virtualDAT.properties[prop2CreatID], str(prop2CreatValue.replace('IID', '0x%08X' % IID).replace('GID', '0x%08X' % self.parent.parent.GID).replace('examplarName', examplarName))))

            for prop2CreatID in category.setProperties.keys():
                if prop2CreatID in propCreated:
                    pass
                elif prop2CreatID == 2317746857L and self.examplar.GetProp(2319542937L):
                    pass
                elif prop2CreatID == 2308635565L and self.examplar.GetProp(3393284789L):
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

                    props.append(CreateAPropFromString(self.virtualDAT.properties[prop2CreatID], ','.join(prop2CreatValue)))

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

                    props.append(CreateAPropFromString(self.virtualDAT.properties[prop2CreatID], ','.join(prop2CreatValue)))

            if category.parent != None:
                category = category.parent
            else:
                break

        props.sort(cmp=lambda x, y: cmp(x[2:2 + 8], y[2:2 + 8]))
        category = self.virtualDAT.categories[includedCats[0][1]]
        props = [ p for p in props if unicode(p[2:2 + 8].upper()) not in category.removeProperties.values() ]
        for prop in category.removeProperties.keys():
            self.examplar.RemoveProp(prop)

        UVNK = self.examplar.GetProp(2319542937L)
        IDK = self.examplar.GetProp(3393284789L)
        if UVNK != None:
            props = [ p for p in props if unicode(p[2:2 + 8].upper()) != '899AFBAD' ]
        if IDK != None:
            props = [ p for p in props if unicode(p[2:2 + 8].upper()) != '8A2602A9' ]
        for prop in props:
            self.examplar.AddTextProp(prop)

        self.listProperties.DeleteAllItems()
        self.FillTheList()
        self.bSave.Enable(True)
        self.descriptor.name = self.examplar.GetProp(32)[0]
        self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
        self.parent.parent.listItems.Refresh()
        self.OnOpenLotWithBuilding(event)
        if IsFromCategory(self.virtualDAT.categories[2895100787L], self.examplar):
            for p in self.openedLots:
                p.OnRecomputeStage(event)

        return

    def OnRebuildOccupantSize(self, event):
        if self.view:
            try:
                data = self.view.viewingData[0].mainMesh
                data.ReadFile()
                Height = height = oldRound(data.bboxY, 4)
                Width = width = oldRound(clamp2Tile(data.bboxX), 4)
                Depth = depth = oldRound(clamp2Tile(data.bboxZ), 4)
            except:
                Height = height = 3
                Width = width = 8
                Depth = depth = 8

            newPropStr = CreateAPropFromString(self.virtualDAT.properties[662775824], '%f,%f,%f' % (Width, Height, Depth))
            if not self.examplar.AddTextProp(newPropStr):
                return None
            self.listProperties.DeleteAllItems()
            self.FillTheList()
            self.bSave.Enable(True)
            self.descriptor.name = self.examplar.GetProp(32)[0]
            self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
            self.parent.parent.listItems.Refresh()
        return None

    def OnOpenFamily(self, event):
        idMenu = event.GetId()
        familyIdx = idMenu - self.popupID13
        family = self.examplar.GetProp(662775920)[familyIdx]
        for desc in self.virtualDAT.categories[family].descriptors:
            self.parent.AddNewDesc(desc, self.virtualDAT, False)

    def DuplicateLTEXTEntry(self, examplar, utxt, t, g, i):
        newVal = utxt.encode('unicode_internal')
        buffer = struct.pack('III', t, g, i)
        buffer += struct.pack('II', 0, 4 + len(newVal))
        ltextEntry = SC4Entry(buffer, 0, examplar.entry.fileName)
        buffer = struct.pack('H', len(utxt))
        buffer += struct.pack('H', 4096)
        buffer += newVal
        ltextEntry.content = buffer
        ltextEntry.Maj()
        self.virtualDAT.addEntries([ltextEntry], None, False, False)
        return ltextEntry

    def CreateLTEXTEntry(self, utxt, t, g, i, propid2add, propid2remove=0):
        newVal = utxt.encode('unicode_internal')
        buffer = struct.pack('III', t, g, i)
        buffer += struct.pack('II', 0, 4 + len(newVal))
        ltextEntry = SC4Entry(buffer, 0, self.examplar.entry.fileName)
        buffer = struct.pack('H', len(utxt))
        buffer += struct.pack('H', 4096)
        buffer += newVal
        ltextEntry.content = buffer
        ltextEntry.Maj()
        self.InternalSave(ltextEntry.fileName)
        self.virtualDAT.addEntries([ltextEntry], None, False, False)
        self.examplar.RemoveProp(propid2remove)
        if propid2add:
            newPropStr = CreateAPropFromString(self.virtualDAT.properties[propid2add], '0x%08X,0x%08X,0x%08X' % (t, g, i))
            self.examplar.AddTextProp(newPropStr)
        self.listProperties.DeleteAllItems()
        self.FillTheList()
        if propid2add:
            self.bSave.Enable(True)
        self.descriptor.name = self.examplar.GetProp(32)[0]
        self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
        self.parent.parent.listItems.Refresh()
        return

    def OnAddLangUVNK(self, event):
        idMenu = event.GetId()
        txt = self.examplar.GetPropObject(32).rawdata
        try:
            utxt = unicode(txt)
        except:
            try:
                utxt = txt.decode('unicode_internal')
            except:
                utxt = txt.decode('utf8')

        UVNK = self.examplar.GetProp(2319542937L)
        if UVNK:
            uvnks = [ self.virtualDAT.getEntry(UVNK[0], UVNK[1] + i, UVNK[2]) for i in offsetGID ]
            for i, uvnk in enumerate(uvnks):
                if uvnk:
                    uvnk.ReadFile(None, True, True)
                    try:
                        utxt = uvnk.content[4:].decode('unicode_internal')
                    except UnicodeDecodeError:
                        utxt = uvnk.content.decode('utf8')

                    break

        idx = self.AddLangUVNK_IDs.index(idMenu)
        self.CreateLTEXTEntry(utxt, 539399691, 1782082854 + offsetGID[idx], self.examplar.entry.tgi[2], 0)
        return

    def OnConvertToUVNK(self, event):
        try:
            txt = self.examplar.GetPropObject(2308635565L).rawdata
        except:
            txt = self.examplar.GetPropObject(32).rawdata

        try:
            utxt = unicode(txt)
        except:
            try:
                utxt = txt.decode('unicode_internal')
            except:
                utxt = txt.decode('utf8')

        if self.examplar.GetProp(1788208387) and self.examplar.GetProp(1788208387)[0] == True:
            newProp = CreateAProp(self.virtualDAT.properties[1788208387], (False,))
            self.examplar.AddTextProp(newProp)
        self.CreateLTEXTEntry(utxt, 539399691, 1782082854, self.examplar.entry.tgi[2], 2319542937L, 2308635565L)

    def OnAddLangIDK(self, event):
        idMenu = event.GetId()
        txt = self.examplar.GetPropObject(32).rawdata
        try:
            utxt = unicode(txt)
        except:
            try:
                utxt = txt.decode('unicode_internal')
            except:
                utxt = txt.decode('utf8')

        IDK = self.examplar.GetProp(3393284789L)
        if IDK:
            idks = [ self.virtualDAT.getEntry(IDK[0], IDK[1] + i, IDK[2]) for i in offsetGID ]
            for i, idk in enumerate(idks):
                if idk:
                    idk.ReadFile(None, True, True)
                    try:
                        utxt = idk.content[4:].decode('unicode_internal')
                    except UnicodeDecodeError:
                        utxt = idk.content.decode('utf8')

                    break

        idx = self.AddLangIDK_IDs.index(idMenu)
        self.CreateLTEXTEntry(utxt, 539399691, self.examplar.entry.tgi[1] + offsetGID[idx], self.examplar.entry.tgi[2], 0)
        return

    def OnConvertToIDK(self, event):
        txt = self.examplar.GetPropObject(2317746857L).rawdata
        try:
            utxt = unicode(txt)
        except:
            try:
                utxt = txt.decode('unicode_internal')
            except:
                utxt = txt.decode('utf8')

        self.CreateLTEXTEntry(utxt, 539399691, self.examplar.entry.tgi[1], self.examplar.entry.tgi[2], 3393284789L, 2317746857L)

    def OnAddItemName(self, event):
        newPropStr = CreateAPropFromString(self.virtualDAT.properties[2308635565L], self.examplar.GetPropObject(32).rawdata)
        if not self.examplar.AddTextProp(newPropStr):
            return None
        if self.examplar.GetProp(1788208387) and self.examplar.GetProp(1788208387)[0] == True:
            newProp = CreateAProp(self.virtualDAT.properties[1788208387], (False,))
            self.examplar.AddTextProp(newProp)
        self.listProperties.DeleteAllItems()
        self.FillTheList()
        self.bSave.Enable(True)
        self.descriptor.name = self.examplar.GetProp(32)[0]
        self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
        self.parent.parent.listItems.Refresh()
        return None

    def OnAddDescription(self, event):
        try:
            txt = self.examplar.GetPropObject(2308635565L).rawdata
        except:
            txt = self.examplar.GetPropObject(32).rawdata

        newPropStr = CreateAPropFromString(self.virtualDAT.properties[2317746857L], txt)
        if not self.examplar.AddTextProp(newPropStr):
            return None
        self.listProperties.DeleteAllItems()
        self.FillTheList()
        self.bSave.Enable(True)
        self.descriptor.name = self.examplar.GetProp(32)[0]
        self.parent.SetPageText(self.parent.currentPage, self.descriptor.name)
        self.parent.parent.listItems.Refresh()
        return None

    def OnAddProperty(self, event):
        k = self.virtualDAT.properties.keys()
        choices = [ self.virtualDAT.properties[idx].Name for idx in k ]
        choices.sort(key=str.lower)
        dlg = wx.SingleChoiceDialog(self, addPropertyMsg, addPropertyTitle, choices, wx.CHOICEDLG_STYLE)
        if dlg.ShowModal() == wx.ID_OK:
            choose = dlg.GetStringSelection()
            propChoosen = None
            for id, v in self.virtualDAT.properties.iteritems():
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
                    newPropStr = CreateAPropFromString(self.virtualDAT.properties[propChoosen], newValue)
                    if not self.examplar.AddTextProp(newPropStr):
                        dlgVal.Destroy()
                        dlg.Destroy()
                        return
                    self.listProperties.DeleteAllItems()
                    self.FillTheList()
                    self.bSave.Enable(True)
                    self.descriptor.name = self.examplar.GetProp(32)[0]
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
            if i >= 0 and i < len(self.examplar.props):
                prop = self.examplar.props[i]
                if prop.id >= 2297284864L and prop.id < 2297286144L:
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
            if i >= 0 and i < len(self.examplar.props):
                self.parent.clipboard.append(self.examplar.props[i].TextRep())
            index = self.listProperties.GetNextSelected(index)

    def OnPaste(self, event):
        prop2Add = []
        for line in self.parent.clipboard:
            id = int(line[2:2 + 8].lower(), 16)
            if id >= 2297284864L and id < 2297286144L:
                prop2Add.append(line)
            else:
                self.examplar.AddTextProp(line)

        if prop2Add != []:
            currentID = 2297284864L
            for id in range(2297284864L, 2297286144L):
                values = self.examplar.GetProp(id)
                if values == None:
                    currentID = id
                    break

            for prop in prop2Add:
                line = hex2str(currentID) + prop[10:]
                self.examplar.AddTextProp(line)
                currentID += 1

            self.examplar.ReindexLotConfig(True)
        if self.parent.clipboard != []:
            self.listProperties.DeleteAllItems()
            self.FillTheList()
            self.bSave.Enable(True)
            self.descriptor.name = self.examplar.GetProp(32)[0]
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
            if i >= 0 and i < len(self.examplar.props):
                prop2Remove.append(self.examplar.props[i].id)
            index = self.listProperties.GetNextSelected(index)

        bNeedReindex = False
        for id in prop2Remove:
            if id >= 2297284864L and id < 2297286144L:
                bNeedReindex = True
            self.examplar.RemoveProp(id)

        if bNeedReindex:
            self.examplar.ReindexLotConfig()
        if prop2Remove != []:
            self.listProperties.DeleteAllItems()
            self.FillTheList()
            self.bSave.Enable(True)
            self.descriptor.name = self.examplar.GetProp(32)[0]
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
        il = wx.ImageList(47, 37)
        for i, cat in virtualDAT.categories.iteritems():
            cat.imgIdx = il.Add(wx.Image(cat.imgName).ConvertToBitmap())

        self.AssignImageList(il)

    def OnPageChanged(self, event):
        newPage = event.GetSelection()
        self.RestorePage(newPage)
        event.Skip()

    def OnFocus(self, event):
        if self.currentPage == None:
            return
        self.ChangeSelection(self.currentPage)
        self.RestorePage(self.currentPage)
        event.Skip()
        return

    def RestorePage(self, newPage):
        self.Freeze()
        self.parent.staticFileName.SetLabel(unknownRK)
        self.currentPage = newPage
        if self.parent.viewer.S3DMesh != None:
            self.parent.viewer.S3DMesh.Free3D(self.parent.viewer.s3DTexturesHolder)
            self.parent.viewer.S3DMesh = None
            self.parent.viewer.Refresh(False)
        descriptor = self.descriptors[newPage]
        examplar = descriptor.examplar
        rkt4 = examplar.GetProp(662775844)
        self.parent.cbStateChoice.Clear()
        self.parent.cbStateChoice.SetValue('')
        if rkt4 != None:
            choices = []
            for z in xrange(len(rkt4) / 8):
                choices.append(('Model #%d' % z, z))

            for ch in choices:
                self.parent.cbStateChoice.Append(ch[0], ch[1])

            self.parent.cbStateChoice.SetValue(choices[0][0])
        try:
            self.GetPage(newPage).RebuildViewer()
            view = self.GetPage(newPage).view
        except:
            view = None

        if view:
            zoom = self.parent.cbZoom.GetClientData(self.parent.cbZoom.GetSelection())
            rot = self.parent.cbRotation.GetClientData(self.parent.cbRotation.GetSelection())
            try:
                state = self.parent.cbStateChoice.GetClientData(self.parent.cbStateChoice.GetSelection())
            except:
                state = 0

            if zoom == -1:
                nZoom = 0
            else:
                nZoom = zoom
            view.Draw(self.parent.viewer, self.parent.staticFileName, zoom, rot, state)
            self.parent.currentModel = view
        else:
            self.parent.currentModel = None
            self.parent.staticFileName.SetLabel(unknownRK)
        self.Thaw()
        return

    def CloseCurrentTab(self):
        self.GetCurrentPage().UndoInCaseModified()
        self.GetCurrentPage().OnClose()
        del self.descriptors[self.currentPage]
        oldPage = self.currentPage
        if self.currentPage >= len(self.descriptors):
            self.currentPage = len(self.descriptors) - 1
            if self.currentPage == -1:
                self.currentPage = None
        self.DeletePage(oldPage)
        if self.currentPage != None:
            self.ChangeSelection(self.currentPage)
            self.RestorePage(self.currentPage)
        self.Refresh(False)
        return

    def OnCloseTab(self, event):
        self.GetCurrentPage().UndoInCaseModified()
        self.GetCurrentPage().OnClose()
        del self.descriptors[self.currentPage]
        oldPage = self.currentPage
        if self.currentPage >= len(self.descriptors):
            self.currentPage = len(self.descriptors) - 1
            if self.currentPage == -1:
                self.currentPage = None
        self.DeletePage(oldPage)
        if self.currentPage != None:
            self.ChangeSelection(self.currentPage)
            self.RestorePage(self.currentPage)
        self.Refresh(False)
        return

    def ReplaceCurrentPage(self, descriptor, virtualDAT):
        if self.parent.viewer.S3DMesh != None:
            self.parent.viewer.S3DMesh.Free3D(self.parent.viewer.s3DTexturesHolder)
            self.parent.viewer.S3DMesh = None
            self.parent.viewer.Refresh(False)
        for i, desc in enumerate(self.descriptors):
            if descriptor.examplar.entry.tgi == desc.examplar.entry.tgi:
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
        except:
            img = virtualDAT.categories[4089082401L].imgIdx

        if bAdd and len(self.descriptors):
            panel = self.GetCurrentPage()
            if not panel.examplar.modified:
                self.ReplaceCurrentPage(descriptor, virtualDAT)
                self.SetPageImage(self.currentPage, img)
                return self.currentPage
        if self.parent.viewer.S3DMesh != None:
            self.parent.viewer.S3DMesh.Free3D(self.parent.viewer.s3DTexturesHolder)
            self.parent.viewer.S3DMesh = None
            self.parent.viewer.Refresh(False)
        for i, desc in enumerate(self.descriptors):
            if descriptor.examplar.entry.tgi == desc.examplar.entry.tgi:
                self.ChangeSelection(i)
                self.RestorePage(i)
                self.SetPageImage(i, img)
                return self.GetPage(i)

        self.Freeze()
        page = NoteBookPanel(self, descriptor, virtualDAT)
        self.descriptors.append(descriptor)
        self.AddPage(page, descriptor.name.decode('unicode_escape'), True, img)
        self.ChangeSelection(self.GetPageCount() - 1)
        self.Thaw()
        return page


class ConfigureDialog(sc.SizedDialog):

    def __init__(self, parent):
        sc.SizedDialog.__init__(self, parent, -1, configurationDialogTitle, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.ReadConfig()
        pane = self.GetContentsPane()
        pane.SetSizerType('vertical')
        wx.StaticText(pane, -1, configurationDialogGID % parent.GID)
        self.listFolder = [parent.maxisFolder, parent.maxisPluginsFolder, parent.rootFolder]
        toCheck = [
         0, 1, 2]
        for root, dirs, files in os.walk(parent.rootFolder):
            for i, folder in enumerate(dirs):
                self.listFolder.append(os.path.join(parent.rootFolder, folder))
                if os.path.join(parent.rootFolder, folder) in self.pathToScan:
                    toCheck.append(i + 3)

            break

        self.lb1 = wx.CheckListBox(pane, -1, choices=self.listFolder, style=wx.LB_SINGLE | wx.LB_HSCROLL, size=(700,
                                                                                                                -1))
        self.lb1.SetSelection(0)
        self.lb1.SetSizerProp('expand', True)
        self.lb1.SetSizerProp('proportion', 1)
        for checked in toCheck:
            self.lb1.Check(checked)

        buttonPane = sc.SizedPanel(pane, -1)
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.Fit()
        self.SetMinSize(self.GetSize())

    def ReadConfig(self):
        self.pathToScan = []
        try:

            def getText(nodelist):
                rc = ''
                for node in nodelist:
                    if node.nodeType == node.TEXT_NODE:
                        rc = rc + node.data

                return rc

            configXML = xml.dom.minidom.parse('config.xml')
            for node in configXML.documentElement.childNodes:
                if node.nodeType == node.ELEMENT_NODE and node.tagName == 'folders':
                    for subNode in node.childNodes:
                        if subNode.nodeType == subNode.ELEMENT_NODE and subNode.tagName == 'folder':
                            recurse = int(subNode.getAttribute('recurse'))
                            path = unicode(getText(subNode.childNodes)).decode('unicode_escape').replace('\\\\', '\\')
                            self.pathToScan.append(path)

        except:
            pass

    def OnSave(self, parent):
        xmlData = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xmlData += '<config>\n'
        xmlData += ' <folders>\n'
        for i, path in enumerate(self.listFolder):
            if self.lb1.IsChecked(i):
                if i == 0 or i == 2:
                    xmlData += '  <folder recurse="0">%s</folder>\n' % path.replace('\\', '\\\\').encode('unicode_escape')
                else:
                    xmlData += '  <folder recurse="1">%s</folder>\n' % path.replace('\\', '\\\\').encode('unicode_escape')

        xmlData += ' </folders>\n'
        xmlData += '</config>\n'
        fconfig = open('config.xml', 'wt')
        fconfig.write(xmlData)
        fconfig.close()


class MainFrame(wx.Frame):

    def __init__(self):
        wx.Frame.__init__(self, None, title='SC4 PIM Extended 2009 RC8', size=(800,
                                                                               800))
        try:
            maxisKey = win32api.RegOpenKeyEx(win32con.HKEY_LOCAL_MACHINE, 'SOFTWARE\\Maxis\\SimCity 4\\Tools')
            self.GID = win32api.RegQueryValueEx(maxisKey, 'User Group ID')[0]
            x = struct.pack('L', self.GID)
            self.GID = struct.unpack('L', x)[0]
        except:
            init = datetime.datetime(2005, 5, 5, 21, 24, 15)
            today = datetime.datetime.today()
            dt = today - init
            dt = dt.days * 24 * 3600 + dt.seconds
            first = random.randrange(1, 15, 2)
            self.GID = first * 268435456L + (dt & 268435455)
            x = struct.pack('L', self.GID)
            self.GID = struct.unpack('L', x)[0]
            keypath = 'SOFTWARE\\Maxis\\SimCity 4\\Tools'.split('\\')
            keyhandle = win32con.HKEY_LOCAL_MACHINE
            for subkey in keypath:
                keyhandle = win32api.RegCreateKey(keyhandle, subkey)

            maxisKey = win32api.RegOpenKeyEx(win32con.HKEY_LOCAL_MACHINE, 'SOFTWARE\\Maxis\\SimCity 4\\Tools', 0, win32con.KEY_SET_VALUE)
            iid = struct.unpack('i', struct.pack('I', self.GID))[0]
            win32api.RegSetValueEx(maxisKey, 'User Group ID', 0, win32con.REG_DWORD, iid)

        menuBar = wx.MenuBar()
        menu1 = wx.Menu()
        menu1.Append(104, menuItem1_1)
        menuBar.Append(menu1, menuItem1)
        self.SetMenuBar(menuBar)
        self.Bind(wx.EVT_MENU, self.OnQuit, id=104)
        self.Bind(wx.EVT_MENU, self.OnConfigure, id=201)
        splitter = wx.SplitterWindow(self, -1, style=wx.CLIP_CHILDREN | wx.SP_LIVE_UPDATE | wx.SP_3D)
        splitterHoriz = wx.SplitterWindow(splitter, -1, style=wx.CLIP_CHILDREN | wx.SP_LIVE_UPDATE | wx.SP_3D)
        rightUpPanel = wx.Panel(splitterHoriz)
        rightDownPanel = wx.Panel(splitterHoriz)
        leftPanel = wx.Panel(splitter)
        self.currentModel = None
        self.listItemsCat = None
        self.virtualDAT = VirtualDat(None)
        self.virtualDAT.getEntry(0, 0, 0)
        self.tree = MyTreeCtrl(self.virtualDAT, leftPanel, self, style=wx.TR_HAS_BUTTONS | wx.TR_ROW_LINES | wx.TAB_TRAVERSAL, size=(400,
                                                                                                                                     400))
        self.tree.ExpandAll()
        self.virtualDAT.tree = self.tree
        dt = treeDnD.DropTarget(self.tree, self.OnDrop, self.OnDropFile)
        self.tree.SetDropTarget(dt)
        self.Bind(wx.EVT_TREE_SEL_CHANGED, self.OnSelChanged, self.tree)
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
        choices = [(viewerZoomBest, -1), (viewerZoom1, 0), (viewerZoom2, 1), (viewerZoom3, 2), (viewerZoom4, 3), (viewerZoom5, 4)]
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
        self.staticFileName = wx.StaticText(leftPanel, -1, '??')
        self.listItems = VirtualListCtrl(rightUpPanel)
        self.listItems.InsertColumn(0, itemColumName)
        self.listItems.InsertColumn(1, itemColumFilename)
        self.listItems.Bind(wx.EVT_LIST_BEGIN_DRAG, self.OnBeginDrag)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemListSelected, self.listItems)
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnItemListSelected, self.listItems)
        self.Bind(wx.EVT_LIST_ITEM_FOCUSED, self.OnItemListSelected, self.listItems)
        self.nb = SC4NoteBook(rightDownPanel, self)
        boxLeft = wx.BoxSizer(wx.VERTICAL)
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
        boxRight.Add(self.listItems, 1, wx.ALL | wx.GROW, 5)
        rightUpPanel.SetSizer(boxRight)
        boxRight = wx.BoxSizer(wx.VERTICAL)
        boxRight.Add(self.nb, 1, wx.ALL | wx.EXPAND, 5)
        rightDownPanel.SetSizer(boxRight)
        splitterHoriz.SplitHorizontally(rightUpPanel, rightDownPanel, 400)
        splitterHoriz.SetMinimumPaneSize(200)
        splitter.SplitVertically(leftPanel, splitterHoriz, 300)
        splitter.SetMinimumPaneSize(300)
        self.nb.LoadPics(self.virtualDAT)
        self.Bind(wx.EVT_CLOSE, self.OnCloseWindow)
        if self.PreLoadDatas():
            self.LoadDatas()
            self.bLoaded = True
        else:
            self.bLoaded = False
        return

    def OnCloseWindow(self, event):
        dlg = wx.MessageDialog(self, quitMsg, 'SC4 PIMX', wx.YES_NO | wx.YES_DEFAULT | wx.ICON_INFORMATION)
        res = dlg.ShowModal()
        dlg.Destroy()
        if res == wx.ID_NO:
            event.Veto()
            return
        self.Destroy()
        sys.exit(1)

    def OnConfigure(self, event):
        dlg = ConfigureDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            dlg.OnSave(self)
        dlg.Destroy()

    def OnQuit(self, event):
        self.OnCloseWindow(event)

    def OnDrop(self, data, item):
        what = self.listItemsCat[data]
        category = self.tree.GetPyData(item)
        bbox = (8, 1, 8)
        try:
            mesh = what.sc4Model.s3dMeshes[4][0]
            mesh.ReadFile()
            bbox = (mesh.bboxX, mesh.bboxY, mesh.bboxZ)
        except:
            pass

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
        if IsAChild(category, 3431971885L):
            descFileName = '%s-0x%08x-0x%08x-0x%08x._LooseDesc' % (fileNameBase, 1697917002, self.GID, IID)
        else:
            descFileName = '%s-0x%08x-0x%08x-0x%08x.SC4Desc' % (fileNameBase, 1697917002, self.GID, IID)
        entry = SC4Entry(buffer, 0, os.path.join(self.rootFolder, descFileName))
        props = []
        Height = height = oldRound(bbox[1], 4)
        Width = width = oldRound(clamp2Tile(bbox[0]), 4)
        Depth = depth = oldRound(clamp2Tile(bbox[2]), 4)
        LotSizeX = 1
        LotSizeY = 1
        if fd == None:
            fillingDegree = 0.5
        else:
            fillingDegree = fd[0]
        Volume = volume = Height * Width * Depth * fillingDegree
        examplarName = str(fileNameBase)
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

            if cat.parent != None:
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
                    except:
                        print variables
                        print codetxt
                        raise

                    prop2CreatValue = []
                    if values.__class__ != tuple:
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

                    props.append(CreateAPropFromString(self.virtualDAT.properties[prop2CreatID], ','.join(prop2CreatValue)))

            for prop2CreatID in category.programProperties.keys():
                if prop2CreatID in propCreated:
                    pass
                else:
                    propCreated.append(prop2CreatID)
                    prop2CreatValue = category.programProperties[prop2CreatID]
                    props.append(CreateAPropFromString(self.virtualDAT.properties[prop2CreatID], str(prop2CreatValue.replace('IID', '0x%08X' % IID).replace('GID', '0x%08X' % self.GID).replace('examplarName', examplarName))))

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

                    props.append(CreateAPropFromString(self.virtualDAT.properties[prop2CreatID], ','.join(prop2CreatValue)))

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

                    props.append(CreateAPropFromString(self.virtualDAT.properties[prop2CreatID], ','.join(prop2CreatValue)))

            if category.parent != None:
                category = category.parent
            else:
                break

        if 662775824 not in propCreated:
            props.append(CreateAProp(self.virtualDAT.properties[662775824], (Width, Height, Depth)))
        try:
            whatRTK = tuple(whatRTK)
        except:
            print 'Failed ', whatRTK
            raise

        if whatRTK in self.virtualDAT.standardModelsDict:
            if 662775841 not in propCreated:
                props.append(CreateAProp(self.virtualDAT.properties[662775841], whatRTK))
        elif 662775840 not in propCreated:
            props.append(CreateAProp(self.virtualDAT.properties[662775840], whatRTK))
        props.sort(cmp=lambda x, y: cmp(x[2:2 + 8], y[2:2 + 8]))
        props = [ p for p in props if unicode(p[2:2 + 8].upper()) not in initcat.removeProperties.values() ]
        buffer = 'EQZT1###\r\n' + 'ParentCohort=Key:{0x00000000,0x00000000,0x00000000}\r\n' + 'PropCount=0x%08x\r\n' % len(props)
        buffer += '\r\n'.join(props)
        entry.content = entry.rawContent = buffer
        examplar = Examplar(entry, self.virtualDAT)
        examplar.entry = entry
        entry.examplar = examplar
        data = descriptor = BuildingDesc(entry)
        self.FillPropList(data, False)
        entries = [entry]
        if examplar.GetProp(2319542937L) is not None:
            tgi = examplar.GetProp(2319542937L)
            if tgi != [0, 0, 0]:
                txt = u'Name of the building' + examplarName
                txt = txt.encode('unicode_internal')
                buffer = struct.pack('III', tgi[0], tgi[1], tgi[2])
                buffer += struct.pack('II', 0, 4 + len(txt))
                entry2 = SC4Entry(buffer, 0, os.path.join(self.rootFolder, descFileName))
                buffer = struct.pack('H', len(txt) / 2)
                buffer += struct.pack('H', 4096)
                buffer += txt
                entry2.content = entry2.rawContent = buffer
                entries.append(entry2)
        if examplar.GetProp(3393284789L) is not None:
            tgi = examplar.GetProp(3393284789L)
            if tgi != [0, 0, 0]:
                txt = u'Description of the building' + v
                txt = txt.encode('unicode_internal')
                buffer = struct.pack('III', tgi[0], tgi[1], tgi[2])
                buffer += struct.pack('II', 0, 4 + len(txt))
                entry2 = SC4Entry(buffer, 0, os.path.join(self.rootFolder, descFileName))
                buffer = struct.pack('H', len(txt) / 2)
                buffer += struct.pack('H', 4096)
                buffer += txt
                entry2.content = entry2.rawContent = buffer
                entries.append(entry2)
        entry.examplar.Maj()
        WriteADat(entry.fileName, entries, None, True)
        self.virtualDAT.addEntries(entries, None, False, False)
        Categorize(self.virtualDAT.rootCategory, descriptor)
        desc = descriptor
        return descriptor

    def OnDropFile(self, filenames, item):
        return None

    def OnBeginDrag(self, event):
        idx = event.GetIndex()
        what = self.listItemsCat[idx]
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
        self.pathToScan = []
        try:
            maxisKey = win32api.RegOpenKeyEx(win32con.HKEY_LOCAL_MACHINE, 'SOFTWARE\\Maxis\\SimCity 4')
            self.maxisFolder = unicode(win32api.RegQueryValueEx(maxisKey, 'Install Dir')[0])
        except:
            self.maxisFolder = ''
            self.maxisPluginsFolder = ''

        if self.maxisFolder != '':
            self.maxisPluginsFolder = os.path.join(self.maxisFolder, 'plugins')
        self.mydocs = wx.StandardPaths.Get().GetDocumentsDir()
        self.rootFolder = os.path.join(self.mydocs, 'SimCity 4\\Plugins')
        dlg = ConfigureDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            dlg.OnSave(self)
            dlg.Destroy()
            return True
        dlg.Destroy()
        return False

    def LoadDatas(self):
        wx.BeginBusyCursor()
        bLoadMaxisModel = False
        bLoadMaxisDesc = False
        try:

            def getText(nodelist):
                rc = ''
                for node in nodelist:
                    if node.nodeType == node.TEXT_NODE:
                        rc = rc + node.data

                return rc

            configXML = xml.dom.minidom.parse('config.xml')
            for node in configXML.documentElement.childNodes:
                if node.nodeType == node.ELEMENT_NODE and node.tagName == 'folders':
                    for subNode in node.childNodes:
                        if subNode.nodeType == subNode.ELEMENT_NODE and subNode.tagName == 'folder':
                            recurse = int(subNode.getAttribute('recurse'))
                            path = unicode(getText(subNode.childNodes)).decode('unicode_escape').replace('\\\\', '\\')
                            self.pathToScan.append((path, recurse))

        except:
            pass

        dlg = ProcessDlg(self, loadingDialogMsg)
        dlg.Show()
        start = time.time()
        self.virtualDAT.addFile(dlg, 'cohorts.dat', True)
        if self.maxisFolder != '':
            if bLoadMaxisDesc or bLoadMaxisModel:
                pass
        for path, recurse in self.pathToScan:
            if path == self.maxisFolder:
                self.virtualDAT.addFile(dlg, os.path.join(self.maxisFolder, 'simcity_1.dat'))
                self.virtualDAT.addFile(dlg, os.path.join(self.maxisFolder, 'simcity_2.dat'))
                self.virtualDAT.addFile(dlg, os.path.join(self.maxisFolder, 'simcity_3.dat'))
                self.virtualDAT.addFile(dlg, os.path.join(self.maxisFolder, 'simcity_4.dat'))
                self.virtualDAT.addFile(dlg, os.path.join(self.maxisFolder, 'simcity_5.dat'))
                self.virtualDAT.addFile(dlg, os.path.join(self.maxisFolder, 'ep1.dat'))
                maxisKey = win32api.RegOpenKeyEx(win32con.HKEY_LOCAL_MACHINE, 'SOFTWARE\\Maxis\\SimCity 4\\1.0')
                language = win32api.RegQueryValueEx(maxisKey, 'Language')[0]
                paths = {1: 'English',2: 'French',3: 'German',4: 'Italian',5: 'Spanish',6: 'Swedish',7: 'Finnish',8: 'Dutch',9: 'Danish',10: 'Portgese',11: 'Czech',12: 'Hebrew',13: 'Greek',14: 'Japanese',15: 'Korean',16: 'Russian',17: 'SChinese',18: 'TChinese',19: 'UKEnglsh',20: 'Polish',21: 'Thai',22: 'Norwgian'}
                localeFolder = ''
                try:
                    localeFolder = os.path.join(paths[language], 'simcitylocale.dat')
                except:
                    localeFolder = os.path.join('English', 'simcitylocale.dat')

                self.virtualDAT.addFile(dlg, os.path.join(self.maxisFolder, localeFolder))
            else:
                self.virtualDAT.addFolder(dlg, path, recurse)

        self.virtualDAT.Finalize(dlg)
        texLoader = ImageListLoaderTexture(self.virtualDAT)
        texLoader.Start()
        if len(self.virtualDAT.missingPics) > 0:
            dlg2 = ImageDBBuilder(self, -1, 'Builder')
            dlg2.Show()
            for data in self.virtualDAT.missingPics:
                dlg2.Draw(data)
                dlg.Increment()

            dlg2.Destroy()
        propLoader = ImageListLoaderProps(self.virtualDAT)
        propLoader.Start()
        wx.EndBusyCursor()
        self.tree.EnsureVisible(self.tree.StandardModelsItem)
        self.tree.SelectItem(self.tree.StandardModelsItem)
        self.tree.EnsureVisible(self.tree.root)
        InfoEx()
        dlg.Destroy()
        self.t2 = wx.CallLater(500, self.RefreshEvent)

    def RefreshEvent(self):
        if self.currentModel is not None:
            zoom = self.cbZoom.GetClientData(self.cbZoom.GetSelection())
            rot = self.cbRotation.GetClientData(self.cbRotation.GetSelection())
            if zoom == -1:
                nZoom = 0
            else:
                nZoom = zoom
            if self.currentModel.__class__ == ATC:
                self.currentModel.Draw(self.viewer, self.staticFileName, zoom, rot)
            else:
                try:
                    state = self.cbStateChoice.GetClientData(self.cbStateChoice.GetSelection())
                except:
                    state = 0

                self.currentModel.Draw(self.viewer, self.staticFileName, zoom, rot, state)
            self.t2.Restart(100)
            return
        self.t2.Restart(500)
        return

    def EvtComboBoxState(self, evt):
        zoom = self.cbZoom.GetClientData(self.cbZoom.GetSelection())
        rot = self.cbRotation.GetClientData(self.cbRotation.GetSelection())
        try:
            state = self.cbStateChoice.GetClientData(self.cbStateChoice.GetSelection())
        except:
            state = 0

        if zoom == -1:
            nZoom = 0
        else:
            nZoom = zoom
        if self.currentModel:
            self.currentModel.Draw(self.viewer, self.staticFileName, zoom, rot, state)

    def EvtComboBoxRotation(self, evt):
        zoom = self.cbZoom.GetClientData(self.cbZoom.GetSelection())
        rot = self.cbRotation.GetClientData(self.cbRotation.GetSelection())
        try:
            state = self.cbStateChoice.GetClientData(self.cbStateChoice.GetSelection())
        except:
            state = 0

        if zoom == -1:
            nZoom = 0
        else:
            nZoom = zoom
        if self.currentModel:
            self.currentModel.Draw(self.viewer, self.staticFileName, zoom, rot, state)

    def EvtComboBoxZoom(self, evt):
        zoom = self.cbZoom.GetClientData(self.cbZoom.GetSelection())
        rot = self.cbRotation.GetClientData(self.cbRotation.GetSelection())
        try:
            state = self.cbStateChoice.GetClientData(self.cbStateChoice.GetSelection())
        except:
            state = 0

        if zoom == -1:
            nZoom = 0
        else:
            nZoom = zoom
        if self.currentModel:
            self.currentModel.Draw(self.viewer, self.staticFileName, zoom, rot, state)

    def RefreshItemsList(self):
        if self.backupCat != None:
            self.FillItemsList(self.tree.virtualDAT.categories[self.backupCat])
        return

    def FillItemsList(self, cat):
        self.backupCat = cat.ID
        self.listItemsCat = cat
        if self.listItems.GetColumnCount() == 3:
            self.listItems.DeleteAllItems()
        else:
            self.listItems.ClearAll()
            self.listItems.InsertColumn(0, itemColumName)
            self.listItems.InsertColumn(1, itemColumFilename)
            self.listItems.InsertColumn(2, itemColumDate)
            self.listItems.SetColumnWidth(0, 150)
            self.listItems.SetColumnWidth(1, 500)
            self.listItems.SetColumnWidth(2, 200)
        cat.descriptors.sort(cmp=lambda d1, d2: cmp(d2.examplar.entry.dateUpdated, d1.examplar.entry.dateUpdated))
        self.listItems.listdatas = cat.descriptors
        self.listItems.SetItemCount(len(cat.descriptors))

    def FillItemsListModel(self, what):
        self.backupCat = None
        self.listItemsCat = what
        if self.listItems.GetColumnCount() == 2:
            self.listItems.DeleteAllItems()
        else:
            self.listItems.ClearAll()
            self.listItems.InsertColumn(0, itemColumName)
            self.listItems.InsertColumn(1, itemColumFilename)
        self.listItems.listdatas = what
        self.listItems.SetItemCount(len(what))
        return

    def FillPropList(self, descriptor, bAdd):
        examplar = descriptor.examplar
        self.cbStateChoice.Clear()
        self.cbStateChoice.SetValue('')
        rkt4 = examplar.GetProp(662775844)
        if rkt4 != None:
            choices = []
            for z in xrange(len(rkt4) / 8):
                choices.append(('Model #%d' % z, z))

            for ch in choices:
                self.cbStateChoice.Append(ch[0], ch[1])

            self.cbStateChoice.SetValue(choices[0][0])
        self.nb.AddNewDesc(descriptor, self.virtualDAT, bAdd)
        return

    def OnItemListSelected(self, event):
        item = event.GetItem()
        idx = event.m_itemIndex
        if self.viewer.S3DMesh != None:
            self.viewer.S3DMesh.Free3D(self.viewer.s3DTexturesHolder)
            self.viewer.S3DMesh = None
            self.viewer.Refresh(False)
        if self.listItemsCat != None:
            if self.listItemsCat.__class__.__name__ == 'list':
                self.cbStateChoice.Clear()
                self.cbStateChoice.SetValue('')
                data = self.listItemsCat[idx].sc4Model
                zoom = self.cbZoom.GetClientData(self.cbZoom.GetSelection())
                rot = self.cbRotation.GetClientData(self.cbRotation.GetSelection())
                if zoom == -1:
                    nZoom = 0
                else:
                    nZoom = zoom
                self.viewer = data.__class__.viewer
                self.viewer.InitGL()
                self.viewer.S3DMesh = None
                self.viewer.Refresh(False)
                self.staticFileName.SetLabel(self.listItemsCat[idx].fileName)
                data.Draw(self.viewer, self.staticFileName, zoom, rot)
                self.currentModel = data
            elif self.listItemsCat.__class__.__name__ == 'DictWrapper':
                data = self.listItemsCat.descriptors[idx]
                self.FillPropList(data, not wx.GetKeyState(wx.WXK_CONTROL))
        return

    def OnSelChanged(self, event):
        item = event.GetItem()
        tree = event.GetEventObject()
        try:
            data = tree.GetPyData(item)
        except:
            data = None

        if data:
            if data.__class__.__name__ == 'list':
                self.FillItemsListModel(data)
                if self.viewer.S3DMesh != None:
                    self.viewer.S3DMesh.Free3D(self.viewer.s3DTexturesHolder)
                    self.viewer.S3DMesh = None
                    self.viewer.Refresh(False)
            if data.__class__.__name__ == 'DictWrapper':
                self.FillItemsList(data)
                if self.viewer.S3DMesh != None:
                    self.viewer.S3DMesh.Free3D(self.viewer.s3DTexturesHolder)
                    self.viewer.S3DMesh = None
                    self.viewer.Refresh(False)
        else:
            self.listItemsCat = None
            self.listItems.DeleteAllItems()
            self.listItems.SetItemCount(0)
            if self.viewer.S3DMesh != None:
                self.viewer.S3DMesh.Free3D(self.viewer.s3DTexturesHolder)
                self.viewer.S3DMesh = None
                self.viewer.Refresh(False)
            self.currentModel = None
        return


class SplashScreen(wx.SplashScreen):

    def __init__(self):
        bmp = wx.Image('splash.jpg', wx.BITMAP_TYPE_JPEG).ConvertToBitmap()
        wx.SplashScreen.__init__(self, bmp, wx.SPLASH_CENTRE_ON_SCREEN | wx.SPLASH_TIMEOUT, 500, None, -1)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        return

    def OnClose(self, evt):
        evt.Skip()
        self.Hide()
        self.ShowMain()

    def ShowMain(self):
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


if 1:
    try:
        os.mkdir('ImageDB')
    except:
        pass

    try:
        os.mkdir('ImageDBLarge')
    except:
        pass

    blank = Image.new('RGB', (64, 64), 8355711)
    blank.save('ImageDB/0xbadb57f1-0x00000000.jpg')
    blank.save('ImageDB/0x00000000-0x00000000.jpg')
    blank = Image.new('RGB', (128, 128), 8355711)
    blank.save('ImageDBLarge/0xbadb57f1-0x00000000.jpg')
    blank.save('ImageDBLarge/0x00000000-0x00000000.jpg')
    prog = App()
    prog.MainLoop()
# okay decompiling SC4PIMApp.pyo
