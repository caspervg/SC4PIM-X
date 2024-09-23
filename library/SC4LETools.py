# uncompyle6 version 2.11.5
# Python bytecode 2.4 (62061)
# Decompiled from: Python 2.7.18 (default, Oct 15 2023, 16:43:11) 
# [GCC 11.4.0]
# Embedded file name: SC4LETools.pyo
# Compiled at: 2009-11-05 21:00:28
import wx
import wx.lib.sized_controls as sc
import FSHConverter
import Image
import ImageDraw
import treeDnD
import StringIO
import random
import dircache
import datetime
import types
import BalloonTip as BT
import win32gui
from SC4OpenGL import *
from translation import *
from SC4Data import *
from ATCReader import *

def CmpTGI(tgi1, tgi2):
    if tgi1[0] == tgi2[0]:
        if tgi1[1] == tgi2[1]:
            return cmp(tgi1[2], tgi2[2])
        else:
            return cmp(tgi1[1], tgi2[1])
    else:
        return cmp(tgi1[0], tgi2[0])


class TreeDropTarget(wx.PyDropTarget):

    def __init__(self, tree):
        wx.PyDropTarget.__init__(self)
        self._makeObjects()
        self.tree = tree

    def _makeObjects(self):
        self.data = treeDnD.DropData()
        comp = wx.DataObjectComposite()
        comp.Add(self.data)
        self.comp = comp
        self.SetDataObject(comp)

    def OnEnter(self, x, y, d):
        return d

    def OnLeave(self):
        pass

    def OnDrop(self, x, y):
        self.item, self.flags = self.tree.HitTest((x, y))
        return True

    def OnDragOver(self, x, y, d):
        item, flags = self.tree.HitTest((x, y))
        if item:
            self.tree.EnsureVisible(item)
            pyData = self.tree.GetPyData(item)
            if pyData:
                if pyData.__class__ != GroupProxy:
                    return wx.DragNone
                return d
            return wx.DragNone
        return wx.DragNone

    def OnData(self, x, y, d):
        item, flags = self.tree.HitTest((x, y))
        if item:
            if self.GetData():
                data = self.data.getObject()
                pyData = self.tree.GetPyData(item)
                bOk = False
                if pyData.kind == 0 and data.__class__ == BaseProxy:
                    bOk = True
                else:
                    if pyData.kind == 1 and data.__class__ == OverlayProxy:
                        bOk = True
                    elif pyData.kind == 4 and data.__class__ == PropProxy:
                        bOk = True
                    elif pyData.kind == 2 and data.__class__ == PropProxy:
                        bOk = True
                    elif pyData.kind == 2 and data.__class__ == FamilyProxy:
                        bOk = True
                    if bOk:
                        pyData.AddItem(data.what, self.tree)
                        return d
                return wx.DragNone
            return d


def CreateIID():
    init = datetime.datetime(2005, 5, 5, 21, 24, 15)
    today = datetime.datetime.today()
    dt = today - init
    dt = dt.days * 24 * 3600 + dt.seconds
    first = random.randrange(0, 15)
    IID = first * 268435456 + (dt & 268435455)
    return IID


class GroupProxy():

    def __init__(self, name, kind):
        self.name = name
        self.IID = CreateIID()
        self.kind = kind
        self.items = []
        self.itemIdx = None
        return

    def Save(self, fout):
        fout.write('group = GroupProxy( "%s" , %d )\n' % (self.name, self.kind))
        for item in self.items:
            if type(item) == types.TupleType:
                fout.write('group.AddItem( (%s) )\n' % ','.join([ hex2str(i) for i in item ]))
            elif self.kind == 0 or self.kind == 1:
                fout.write('group.AddItem( %s )\n' % hex2str(item - 3))
            else:
                fout.write('group.AddItem( %s )\n' % hex2str(item))

        fout.write('self.AddGroup( group )\n\n')

    def AddToTree(self, tree):
        root = None
        if self.kind == 0:
            root = tree.personalBaseTexturesItem
        else:
            if self.kind == 1:
                root = tree.personalOverlayTexturesItem
            elif self.kind == 2:
                root = tree.personalPropsItem
            elif self.kind == 4:
                root = tree.personalFloraItem
            if root:
                self.itemIdx = tree.AppendItem(root, self.name)
                tree.SetPyData(self.itemIdx, self)
                if self.kind == 2:
                    for item in self.items:
                        if type(item) != types.TupleType:
                            try:
                                sub = VirtualDat.this.categories[item]
                            except KeyError:
                                continue

                            idx = tree.AppendItem(self.itemIdx, sub.Name)
                            tree.SetPyData(idx, sub.ID)

        return

    def RemoveItem(self, what):
        try:
            value = what.what
        except:
            value = what

        if self.kind == 0 or self.kind == 1:
            value = what.what + 3
        if value in self.items:
            self.items.remove(value)

    def AddItem(self, what, tree=None):
        if self.kind == 0 or self.kind == 1:
            if what + 3 not in self.items:
                self.items.append(what + 3)
        if self.kind == 2 or self.kind == 3:
            if type(what) == types.TupleType:
                if what not in self.items:
                    self.items.append(what)
            elif what not in self.items:
                self.items.append(what)
                if self.itemIdx != None and tree != None:
                    try:
                        sub = VirtualDat.this.categories[what]
                    except KeyError:
                        return

                    idx = tree.AppendItem(self.itemIdx, sub.Name)
                    tree.SetPyData(idx, sub.ID)
                    tree.Refresh(False)
        if self.kind == 4:
            if type(what) == types.TupleType:
                if what not in self.items:
                    self.items.append(what)
        return

    def Display(self, lstCtrl):
        if self.kind == 0 or self.kind == 1:
            lst = [ VirtualDat.this.getEntry(2058686020, 159781726, IID) for IID in self.items ]
            lst = [ desc for desc in lst if desc is not None ]
            lst.sort(cmp=lambda n1, n2: CmpTGI(n1.tgi, n2.tgi))
            if self.kind == 0:
                il = VirtualDat.this.ilBase
            else:
                il = VirtualDat.this.ilOver
            lstCtrl.Reset(il, lst, FillListForTex, DisplayNameForTex)
        else:

            def GetDescFromTGI(tgi):
                selectedDesc = None
                if type(tgi) == types.TupleType:
                    t = tgi[0]
                    g = tgi[1]
                    i = tgi[2]
                    possibles = filter(lambda desc: desc.examplar.entry.tgi[0] == t and desc.examplar.entry.tgi[1] == g and desc.examplar.entry.tgi[2] == i, VirtualDat.this.categories[210746660].descriptors)
                    for desc in possibles:
                        selectedDesc = desc
                        break

                return selectedDesc

            lst = [ GetDescFromTGI(tgi) for tgi in self.items ]
            lst = [ desc for desc in lst if desc is not None ]
            lst.sort(cmp=lambda n1, n2: cmp(n1.name.upper(), n2.name.upper()))
            lstCtrl.Reset(VirtualDat.this.ilStandardModels, lst, FillListForProps, DisplayNameForPropsName)
        return


def BuildImageForProp(examplar):

    def BuildImageForTGI(tgi):
        fileName = 'ImageDBLarge/%s-%s.jpg' % (hex2str(tgi[1]), hex2str(tgi[2]))
        if not os.path.exists(fileName):
            fileName = 'NoPreview.jpg'
        return Image.open(fileName).resize((128, 128), Image.BICUBIC)

    def BitmapFromTGI(tgi):
        pilz = BuildImageForTGI(tgi)
        image = wx.EmptyImage(pilz.size[0], pilz.size[1])
        image.SetData(pilz.tostring())
        return image.ConvertToBitmap()

    rkt0 = examplar.GetProp(662775840)
    rkt1 = examplar.GetProp(662775841)
    rkt3 = examplar.GetProp(662775843)
    rkt4 = examplar.GetProp(662775844)
    rkt5 = examplar.GetProp(662775845)
    tgi = (0, 0, 0)
    if rkt0 and rkt0[0] == 1523640343:
        tgi = tuple(rkt0)
        return (
         BitmapFromTGI(tgi), False)
    elif rkt1 and rkt1[0] == 1523640343:
        tgi = tuple(rkt1)
        return (
         BitmapFromTGI(tgi), False)
    elif rkt3 and rkt3[0] == 1523640343:
        tgi = tuple(rkt3[0:2] + [rkt3[-1]])
        return (
         BitmapFromTGI(tgi), False)
    elif rkt4:
        nbChoices = len(rkt4) / 8
        fullImage = Image.new('RGB', (128 * nbChoices, 128))
        for cb in xrange(nbChoices):
            rkt = rkt4[cb * 8:cb * 8 + 8]
            rkt = rkt[4:]
            tgi = (0, 0, 0)
            if rkt[0] == 662775840 and rkt[1] == 1523640343:
                tgi = tuple(rkt[1:])
            elif rkt[0] == 662775841 and rkt[1] == 1523640343:
                tgi = tuple(rkt[1:])
            elif rkt[0] == 662775845 and rkt[1] == 1523640343:
                tgi = tuple(rkt[1:])
            img = BuildImageForTGI(tgi)
            fullImage.paste(img.convert('RGB'), (128 * cb, 0))
            draw = ImageDraw.Draw(fullImage)
            draw.rectangle((128 * cb, 0, 128 * cb + 127, 127), outline=(255, 255, 255))

        image = wx.EmptyImage(128 * nbChoices, 128)
        image.SetData(fullImage.tostring())
        return (
         image.ConvertToBitmap(), nbChoices > 1)
    elif rkt5 and rkt5[0] == 1523640343:
        tgi = tuple(rkt5)
        return (
         BitmapFromTGI(tgi), False)
    fileName = 'NoPreview.jpg'
    return (
     wx.Bitmap(fileName, wx.BITMAP_TYPE_JPEG), False)


class ImageListCtrl(wx.ListCtrl):

    def __init__(self, frame, parent, il, entries, fnFill, fnPrint):
        wx.ListCtrl.__init__(self, parent, -1, style=wx.LC_SINGLE_SEL | wx.LC_ICON | wx.LC_AUTOARRANGE | wx.LC_HRULES | wx.LC_VRULES)
        self.Reset(il, entries, fnFill, fnPrint)
        self.Bind(wx.EVT_LIST_BEGIN_DRAG, self.OnBeginDrag)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemListSelected)
        self.Bind(wx.EVT_MENU, self.OnRemoveItem, id=wx.ID_CUT)
        self.SetAcceleratorTable(wx.AcceleratorTable([(wx.ACCEL_NORMAL, wx.WXK_DELETE, wx.ID_CUT)]))
        self.parent = frame
        tipballoon = BT.BalloonTip(message='PIM')
        tipballoon.SetTarget(self)
        tipballoon.SetStartDelay(500)
        win32gui.SendMessage(self.GetHandle(), 4096 + 53, 0, 64 + 10)

    def OnRemoveItem(self, event):
        group = self.parent.IsItPersonalGroup(self.parent.currentItem)
        if group != None:
            items = self.GetSelectedItems()
            for idx in items:
                data = self.GetPyData(idx)
                group.RemoveItem(data)
                self.DeleteItem(idx)
                break

        return

    def OnBalloonPopup(self, tipballoon, mousePos):
        mousePosX, mousePosY = self.ScreenToClientXY(mousePos[0], mousePos[1])
        idx, flag = self.HitTest((mousePosX, mousePosY))
        if idx == -1:
            return False
        data = self.GetPyData(idx)
        if data.__class__ == PropProxy:
            entry = VirtualDat.this.getEntry(data.what[0], data.what[1], data.what[2])
            examplar = entry.examplar
            img, multi = BuildImageForProp(examplar)
            tipballoon.SetBalloonIcon(img)
            if multi:
                tipballoon.SetBalloonMessage('Seasonal/Timed prop\n' + os.path.split(entry.fileName)[1])
            else:
                tipballoon.SetBalloonMessage(os.path.split(entry.fileName)[1])
        elif data.__class__ == FamilyProxy:
            catID = data.what
            thisId = idx
            tgi = (0, 0, 0)
            VirtualDat.this.categories[catID].descriptors.sort(cmp=lambda n1, n2: cmp(n1.name.upper(), n2.name.upper()))
            thisDesc = None
            for desc in VirtualDat.this.categories[catID].descriptors:
                if desc.examplar.entry.tgi[0] != 1697917002:
                    continue
                if desc.examplar.GetProp(16)[0] != 30 and desc.examplar.GetProp(16)[0] != 15:
                    continue
                if thisId == 0:
                    tgi = GetTGIForProp(desc)
                    thisDesc = desc
                    break
                thisId -= 1

            img, multi = BuildImageForProp(thisDesc.examplar)
            tipballoon.SetBalloonIcon(img)
            if multi:
                tipballoon.SetBalloonMessage('Seasonal/Timed prop\n' + os.path.split(thisDesc.examplar.entry.fileName)[1])
            else:
                tipballoon.SetBalloonMessage(os.path.split(thisDesc.examplar.entry.fileName)[1])
        elif data.__class__ == BaseProxy or data.__class__ == OverlayProxy:

            def LoadTexForTGI(tgi):
                texEntry = VirtualDat.this.getEntry(2058686020, 159781726, tgi + 4)
                if texEntry == None:
                    return (Image.open('NoPreview.jpg').resize((128, 128), Image.BICUBIC), 0, '')
                texEntry.ReadFile(None, True, True)
                nbrLayers, trueAlpha, img, alpha, size = FSHConverter.decodeFSH(texEntry.content)
                nbOfBytes = size[0] * size[1]
                texEntry.content = None
                texEntry.rawContent = None
                fullImage = Image.new('RGB', (128 * nbrLayers, 128))
                for layerIdx in xrange(nbrLayers):
                    imBmp = Image.fromstring('RGB', size, img[nbOfBytes * 3 * layerIdx:nbOfBytes * 3 * (layerIdx + 1)])
                    if trueAlpha:
                        blank = Image.new('RGB', size, 16777215)
                        alphaLayer = Image.fromstring('L', size, alpha[nbOfBytes * layerIdx:nbOfBytes * (layerIdx + 1)])
                        imBmp = Image.composite(imBmp, blank, alphaLayer)
                    imBmp = imBmp.resize((128, 128), Image.BICUBIC)
                    fullImage.paste(imBmp.convert('RGB'), (128 * layerIdx, 0))
                    draw = ImageDraw.Draw(fullImage)
                    draw.rectangle((128 * layerIdx, 0, 128 * layerIdx + 127, 127), outline=(0,
                                                                                            0,
                                                                                            0))

                return (fullImage, nbrLayers, texEntry.fileName)

            tgi = data.what
            IID = tgi & 61440
            fullImage, nbrLayers, fileName = LoadTexForTGI(tgi)
            if IID in [0, 4096, 8192, 12288]:
                imgs = []
                maxWidth = 0
                nbValid = 0
                for iid in [0, 4096, 8192, 12288]:
                    img, nb, fName = LoadTexForTGI((tgi & 4294905855L) + iid)
                    if nb > 0:
                        nbValid += 1
                    imgs.append(img)
                    maxWidth = max(maxWidth, img.size[0])

                if nbValid > 1:
                    fullImage = Image.new(fullImage.mode, (maxWidth, 4 * 128), 0)
                    for i, img in enumerate(imgs):
                        fullImage.paste(img.convert('RGB'), (0, 128 * i))

            image = wx.EmptyImage(fullImage.size[0], fullImage.size[1])
            image.SetData(fullImage.convert('RGB').tostring())
            tipballoon.SetBalloonIcon(image.ConvertToBitmap())
            strMsg = os.path.split(fileName)[1]
            tipballoon.SetBalloonMessage(strMsg)
        else:
            tipballoon.SetBalloonIcon(None)
        return True

    def OnItemListSelected(self, event):
        item = event.GetItem()
        idx = event.m_itemIndex

    def SetPyData(self, idx, what):
        self.pyDatas[idx] = what

    def GetPyData(self, idx):
        try:
            return self.pyDatas[idx]
        except:
            return None

        return None

    def Reset(self, il, entries, fnFill, fnPrint, catID=None):
        wx.BeginBusyCursor()
        self.pyDatas = {}
        self.Freeze()
        self.ClearAll()
        self.InsertColumn(0, 'Image')
        self.il = il
        self.SetColumnWidth(0, 10)
        if catID == None:
            fnFill(self, entries, fnPrint)
        else:
            fnFill(self, entries, fnPrint, catID)
        self.SetImageList(self.il, wx.IMAGE_LIST_NORMAL)
        self.Thaw()
        wx.EndBusyCursor()
        return

    def GetSelectedItems(self):
        item = -1
        selection = []
        while 1:
            item = self.GetNextItem(item, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)
            if item == -1:
                break
            selection.append(item)

        return selection

    def OnBeginDrag(self, event):
        selection = self.GetSelectedItems()

        def DoDragDrop():
            comp = wx.DataObjectComposite()
            dd = treeDnD.DropData()
            for selected in selection:
                py = self.GetPyData(selected)
                if py != None:
                    dd.setObject(py)

            comp.Add(dd)
            dropSource = wx.DropSource(self)
            dropSource.SetData(comp)
            result = dropSource.DoDragDrop(wx.Drag_AllowMove)
            return

        wx.CallAfter(DoDragDrop)


class OverlayProxy():

    def __init__(self, texEntry):
        self.what = texEntry.tgi[2] - 3


class BaseProxy():

    def __init__(self, texEntry):
        self.what = texEntry.tgi[2] - 3


def FillListForTex(self, entries, fnPrint):
    for texEntry in entries:
        try:
            idx = VirtualDat.this.overTexEntriesDict[texEntry]
            ProxyClass = OverlayProxy
        except:
            try:
                idx = VirtualDat.this.baseTexEntriesDict[texEntry]
                ProxyClass = BaseProxy
            except:
                continue

        index = self.InsertImageStringItem(self.GetItemCount(), fnPrint(texEntry), idx)
        self.SetItemImage(index, idx, idx)
        self.SetPyData(index, ProxyClass(texEntry))


class PropProxy():

    def __init__(self, desc):
        self.what = desc.examplar.entry.tgi


class FamilyProxy():

    def __init__(self, familyID):
        self.what = familyID


def FillListForPropsAsFamily(self, entries, fnPrint, catID):
    FillListForProps(self, entries, fnPrint, catID)


def FillListForPropsAsSingle(self, entries, fnPrint):
    FillListForProps(self, entries, fnPrint)


def GetTGIForProp(desc):
    rkt0 = desc.examplar.GetProp(662775840)
    rkt1 = desc.examplar.GetProp(662775841)
    rkt3 = desc.examplar.GetProp(662775843)
    rkt4 = desc.examplar.GetProp(662775844)
    rkt5 = desc.examplar.GetProp(662775845)
    tgi = (0, 0, 0)
    if rkt0 and rkt0[0] == 1523640343:
        tgi = tuple(rkt0)
    elif rkt1 and rkt1[0] == 1523640343:
        tgi = tuple(rkt1)
    elif rkt3 and rkt3[0] == 1523640343:
        tgi = tuple(rkt3[0:2] + [rkt3[-1]])
    else:
        if rkt4:
            nbChoices = len(rkt4) / 4
            for cb in xrange(nbChoices):
                rkt = rkt4[cb * 4:cb * 4 + 4]
                if rkt[0] == 662775841:
                    tgi = tuple(rkt[1:])
                    break

        if rkt5 and rkt5[0] == 1523640343:
            tgi = tuple(rkt5)
    return tgi


def FillListForProps(self, entries, fnPrint, catID=None):
    for desc in entries:
        if desc.examplar.entry.tgi[0] != 1697917002:
            continue
        if desc.examplar.GetProp(16)[0] != 30 and desc.examplar.GetProp(16)[0] != 15:
            continue
        tgi = GetTGIForProp(desc)
        idx = 0
        if tgi != (0, 0, 0):
            try:
                idx = VirtualDat.this.s3dEntries[tgi]
            except KeyError:
                pass

        if idx == -1:
            self.InsertStringItem(self.GetItemCount(), fnPrint(desc))
        else:
            index = self.InsertImageStringItem(self.GetItemCount(), fnPrint(desc), idx)
            self.SetItemImage(index, idx, idx)
            if catID:
                self.SetPyData(index, FamilyProxy(catID))
            else:
                self.SetPyData(index, PropProxy(desc))


def DisplayNameForIcon(entry):
    return '%s' % hex2str(entry.tgi[2])[2:]


def FillListForIcon(self, entries, fnPrint):
    for texEntry in entries:
        if texEntry != None:
            try:
                if texEntry.content == None:
                    texEntry.ReadFile(None, True, True)
            except:
                texEntry.ReadFile(None, True, True)

            cIO = StringIO(texEntry.content)
            pilz = Image.open(cIO).convert('RGB')
            cIO.close()
            image = wx.EmptyImage(44 * 4, 44)
            image.SetData(pilz.convert('RGB').tostring())
            VirtualDat.this.ilIcon.Replace(0, image.ConvertToBitmap())
            index = self.InsertImageStringItem(self.GetItemCount(), fnPrint(texEntry), 0)
            self.SetItemImage(index, 0, 0)

    return


def FillListForNothing(self, entries, fnPrint):
    pass


def DisplayNameForPropsTGI(desc):
    return '%s\n%s' % (hex2str(desc.examplar.entry.tgi[2])[2:], desc.examplar.GetProp(32)[0])


def DisplayNameForPropsName(desc):
    return '%s\n%s' % (desc.examplar.GetProp(32)[0], hex2str(desc.examplar.entry.tgi[2])[2:])


def DisplayNameForTex(entry):
    return '%s' % hex2str(entry.tgi[2] - 3)[2:]


class LETreeCtrl(wx.TreeCtrl):

    def __init__(self, frame, virtualDAT, parent):
        wx.TreeCtrl.__init__(self, parent, -1)
        self.virtualDAT = virtualDAT
        self.root = self.AddRoot(LETreeTools)
        self.texturesItem = self.AppendItem(self.root, LETreeTextures)
        self.baseTexturesItem = self.AppendItem(self.texturesItem, LETreeBaseTextures)
        self.overlayTexturesItem = self.AppendItem(self.texturesItem, LETreeOverlayTextures)
        self.propsItem = self.AppendItem(self.root, LETreeProps)
        self.singlePropsItemTGI = self.AppendItem(self.propsItem, LETreePropsByTGI)
        self.singlePropsItemName = self.AppendItem(self.propsItem, LETreePropsByName)
        self.familiesPropsItem = self.AppendItem(self.propsItem, LETreePropsFamily)
        self.floraItem = self.AppendItem(self.root, LETreeFlora)
        self.lotItem = self.AppendItem(self.root, LETreeLot)
        self.lotBaseTexturesItem = self.AppendItem(self.lotItem, LETreeBaseTextures)
        self.lotOverlayTexturesItem = self.AppendItem(self.lotItem, LETreeOverlayTextures)
        self.lotPropsItem = self.AppendItem(self.lotItem, LETreeProps)
        self.lotFloraItem = self.AppendItem(self.lotItem, LETreeFlora)
        self.lotIcon = self.AppendItem(self.lotItem, LETreeIcon)
        self.personalItem = self.AppendItem(self.root, LETreePref)
        self.personalBaseTexturesItem = self.AppendItem(self.personalItem, LETreeBaseTextures)
        self.personalOverlayTexturesItem = self.AppendItem(self.personalItem, LETreeOverlayTextures)
        self.personalPropsItem = self.AppendItem(self.personalItem, LETreeProps)
        self.personalFloraItem = self.AppendItem(self.personalItem, LETreeFlora)

        def IsItAPropFamilies(entries):
            for desc in entries:
                if desc.examplar.entry.tgi[0] != 1697917002:
                    continue
                if desc.examplar.GetProp(16)[0] != 30 and desc.examplar.GetProp(16)[0] != 15:
                    continue
                return True

            return False

        listSub = self.virtualDAT.categories[4089086497L].childs[:]
        listSub.sort(cmp=lambda n1, n2: cmp(n1.ID, n2.ID))
        for sub in listSub:
            if IsItAPropFamilies(sub.descriptors):
                idx = self.AppendItem(self.familiesPropsItem, sub.Name)
                self.SetPyData(idx, sub.ID)

        listSub = self.virtualDAT.categories[4089087265L].childs[:]
        listSub.sort(cmp=lambda n1, n2: cmp(n1.ID, n2.ID))
        for sub in listSub:
            if IsItAPropFamilies(sub.descriptors):
                idx = self.AppendItem(self.familiesPropsItem, sub.Name)
                self.SetPyData(idx, sub.ID)

        self.Bind(wx.EVT_MENU, frame.OnDeleteKey, id=wx.ID_CUT)
        self.SetAcceleratorTable(wx.AcceleratorTable([(wx.ACCEL_NORMAL, wx.WXK_DELETE, wx.ID_CUT)]))
        self.lotSizeXOver = frame.lotSizeXOver
        self.lotSizeYOver = frame.lotSizeXOver

    def IsUnder(self, root, item):
        if item == self.root:
            return False
        if item == root:
            return True
        return self.IsUnder(root, self.GetItemParent(item))


class TextureDlg(wx.Frame):

    def __init__(self, parent, style=wx.CLIP_CHILDREN | wx.MAXIMIZE_BOX | wx.MINIMIZE_BOX | wx.CAPTION | wx.FRAME_TOOL_WINDOW | wx.FRAME_FLOAT_ON_PARENT | wx.RESIZE_BORDER):
        wx.Frame.__init__(self, parent, -1, title=LEMainTitle, style=style)
        self.Bind(wx.EVT_CLOSE, self.OnCloseWindow)
        self.parent = parent
        self.lotSizeXOver = parent.lotSizeXOver
        self.lotSizeYOver = parent.lotSizeXOver
        self.currentItem = None
        self.SetMinSize((300, 300))
        splitter = wx.SplitterWindow(self, -1, style=wx.CLIP_CHILDREN | wx.SP_LIVE_UPDATE | wx.SP_3D)
        leftPanel = wx.Panel(splitter)
        self.tree = LETreeCtrl(self, VirtualDat.this, leftPanel)
        self.tree.ExpandAll()
        leftBox = wx.BoxSizer(wx.VERTICAL)
        leftBox.Add(self.tree, 1, wx.EXPAND)
        self.bConfig = wx.Button(leftPanel, -1, LEToggleTop, (-1, -1))
        self.bConfig.Bind(wx.EVT_BUTTON, self.OnButton)
        leftBox.Add(self.bConfig, 0, wx.EXPAND)
        leftPanel.SetSizer(leftBox)
        leftPanel.Layout()
        self.tree.ExpandAll()
        self.Bind(wx.EVT_TREE_SEL_CHANGED, self.OnSelChanged, self.tree)
        self.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.OnRightUp, self.tree)
        self.propList = ImageListCtrl(self, splitter, VirtualDat.this.ilBase, None, FillListForNothing, DisplayNameForTex)
        splitter.SplitVertically(leftPanel, self.propList, 120)
        splitter.SetMinimumPaneSize(120)
        self.parent.lotFamiliesPropID.sort()
        for familyID in self.parent.lotFamiliesPropID:
            self.CreateSubFamilies(familyID, self.tree.lotPropsItem)

        self.groups = []
        if os.path.exists('groups.ini'):
            execfile('groups.ini')
        dt = TreeDropTarget(self.tree)
        self.tree.SetDropTarget(dt)
        return

    def OnButton(self, event):
        style = 0
        if self.GetWindowStyleFlag() & wx.FRAME_FLOAT_ON_PARENT != wx.FRAME_FLOAT_ON_PARENT:
            self.SetWindowStyle(self.GetWindowStyleFlag() | wx.FRAME_FLOAT_ON_PARENT)
            style = wx.CLIP_CHILDREN | wx.MAXIMIZE_BOX | wx.MINIMIZE_BOX | wx.CAPTION | wx.FRAME_TOOL_WINDOW | wx.FRAME_FLOAT_ON_PARENT | wx.RESIZE_BORDER
        else:
            self.SetWindowStyle(self.GetWindowStyleFlag() - wx.FRAME_FLOAT_ON_PARENT)
            style = wx.CLIP_CHILDREN | wx.MAXIMIZE_BOX | wx.MINIMIZE_BOX | wx.CAPTION | wx.FRAME_TOOL_WINDOW | wx.RESIZE_BORDER
        self.parent.LETools = None
        self.Save()
        dlg = TextureDlg(self.parent, style)
        dlg.Show()
        self.Close()
        self.parent.LETools = dlg
        return

    def ReBuildLot(self):
        self.parent.lotFamiliesPropID.sort()
        self.tree.DeleteChildren(self.tree.lotPropsItem)
        for familyID in self.parent.lotFamiliesPropID:
            self.CreateSubFamilies(familyID, self.tree.lotPropsItem)

        if self.currentItem is not None:
            if self.tree.IsUnder(self.tree.lotItem, self.currentItem):
                self.Redraw(self.currentItem, self.tree)
        return

    def OnDrop(self, data, item):
        pass

    def OnDropFile(self, filenames, item):
        pass

    def IsItPersonalGroup(self, item):
        lst = [
         self.tree.personalBaseTexturesItem, self.tree.personalOverlayTexturesItem, self.tree.personalPropsItem, self.tree.personalFloraItem]
        for treeItem in lst:
            if self.tree.IsUnder(treeItem, item):
                data = self.tree.GetPyData(item)
                if data and data.__class__ == GroupProxy:
                    return data

        return None

    def OnDeleteKey(self, event):
        item = self.currentItem
        if self.IsItPersonalGroup(item) != None:
            dlg = wx.MessageDialog(self, LEConfirmDeletGroupMsg, LEConfirmDeletGroupTitle, wx.YES_NO | wx.YES_DEFAULT | wx.ICON_INFORMATION)
            if dlg.ShowModal() == wx.ID_YES:
                self.OnDeleteGroup(event)
            dlg.Destroy()
        else:
            lst = [
             self.tree.personalBaseTexturesItem, self.tree.personalOverlayTexturesItem, self.tree.personalPropsItem, self.tree.personalFloraItem]
            for treeItem in lst:
                if self.tree.IsUnder(treeItem, item):
                    data = self.tree.GetPyData(item)
                    if data and data.__class__ != GroupProxy:
                        dlg = wx.MessageDialog(self, LEConfirmDeletFamilyMsg, LEConfirmDeletFamilyTitle, wx.YES_NO | wx.YES_DEFAULT | wx.ICON_INFORMATION)
                        if dlg.ShowModal() == wx.ID_YES:
                            self.OnRemoveFamily(event)
                        dlg.Destroy()
                        break

        return

    def OnRightUp(self, event):
        item = event.GetItem()
        if item:
            self.currentItem = item
            self.tree.SelectItem(item)
            lst = [self.tree.personalBaseTexturesItem, self.tree.personalOverlayTexturesItem, self.tree.personalPropsItem, self.tree.personalFloraItem]
            for treeItem in lst:
                if self.tree.IsUnder(treeItem, item):
                    menu = wx.Menu()
                    id = -1
                    if item == treeItem:
                        id = menu.Append(-1, LEMenuCreateGroup)
                        self.Bind(wx.EVT_MENU, self.OnAddGroup, id)
                    else:
                        data = self.tree.GetPyData(item)
                        if data and data.__class__ == GroupProxy:
                            id = menu.Append(-1, LEMenuDeleteGroup)
                            self.Bind(wx.EVT_MENU, self.OnDeleteGroup, id)
                        elif data:
                            catID = data
                            id = menu.Append(-1, LEMenuDeleteFamily)
                            self.Bind(wx.EVT_MENU, self.OnRemoveFamily, id)
                        if id != -1:
                            self.PopupMenu(menu)
                    menu.Destroy()
                    break

    def AddGroup(self, group):
        self.groups.append(group)
        group.AddToTree(self.tree)

    def OnAddGroup(self, event):
        dlg = wx.TextEntryDialog(self, LEGroupNameDlg, LEGroupNameDlgTitle, '')
        if dlg.ShowModal() == wx.ID_OK:
            name = dlg.GetValue()
            kind = 0
            if self.currentItem == self.tree.personalBaseTexturesItem:
                kind = 0
            elif self.currentItem == self.tree.personalOverlayTexturesItem:
                kind = 1
            elif self.currentItem == self.tree.personalPropsItem:
                kind = 2
            elif self.currentItem == self.tree.personalFloraItem:
                kind = 4
            group = GroupProxy(name, kind)
            self.AddGroup(group)
            self.tree.Expand(self.currentItem)
            self.Refresh(False)
        dlg.Destroy()

    def OnRemoveFamily(self, event):
        catID = self.tree.GetPyData(self.currentItem)
        self.tree.DeleteChildren(self.currentItem)
        self.tree.Delete(self.currentItem)
        parentItem = self.tree.GetItemParent(self.currentItem)
        self.currentItem = parentItem
        group = self.tree.GetPyData(self.currentItem)
        group.RemoveItem(catID)
        self.Refresh(False)

    def OnDeleteGroup(self, event):
        group = self.tree.GetPyData(self.currentItem)
        self.groups.remove(group)
        self.tree.DeleteChildren(self.currentItem)
        self.tree.Delete(self.currentItem)
        self.Refresh(False)
        self.currentItem = None
        return

    def CreateSubFamilies(self, familyID, rootItem):
        sub = VirtualDat.this.categories[familyID]
        idx = self.tree.AppendItem(rootItem, sub.Name)
        self.tree.SetPyData(idx, sub.ID)

    def OnSelChanged(self, event):
        item = event.GetItem()
        self.currentItem = item
        tree = event.GetEventObject()
        self.Redraw(self.currentItem, tree)

    def Redraw(self, item, tree):
        if item == tree.baseTexturesItem:
            self.propList.Reset(VirtualDat.this.ilBase, VirtualDat.this.baseTexEntries, FillListForTex, DisplayNameForTex)
        elif item == tree.overlayTexturesItem:
            self.propList.Reset(VirtualDat.this.ilOver, VirtualDat.this.overTexEntries, FillListForTex, DisplayNameForTex)
        elif item == tree.singlePropsItemTGI:
            VirtualDat.this.categories[210746660].descriptors.sort(cmp=lambda n1, n2: CmpTGI(n1.examplar.entry.tgi, n2.examplar.entry.tgi))
            self.propList.Reset(VirtualDat.this.ilStandardModels, VirtualDat.this.categories[210746660].descriptors, FillListForProps, DisplayNameForPropsTGI)
        elif item == tree.singlePropsItemName:
            VirtualDat.this.categories[210746660].descriptors.sort(cmp=lambda n1, n2: cmp(n1.name.upper(), n2.name.upper()))
            self.propList.Reset(VirtualDat.this.ilStandardModels, VirtualDat.this.categories[210746660].descriptors, FillListForProps, DisplayNameForPropsName)
        elif item == tree.floraItem:
            VirtualDat.this.categories[1830116951].descriptors.sort(cmp=lambda n1, n2: cmp(n1.name.upper(), n2.name.upper()))
            self.propList.Reset(VirtualDat.this.ilStandardModels, VirtualDat.this.categories[1830116951].descriptors, FillListForProps, DisplayNameForPropsName)
        elif item == tree.lotBaseTexturesItem:
            lst = [ VirtualDat.this.getEntry(2058686020, 159781726, IID) for IID in self.parent.lotBaseTextures ]
            lst.sort(cmp=lambda n1, n2: CmpTGI(n1.tgi, n2.tgi))
            self.propList.Reset(VirtualDat.this.ilBase, lst, FillListForTex, DisplayNameForTex)
        elif item == tree.lotOverlayTexturesItem:
            lst = [ VirtualDat.this.getEntry(2058686020, 159781726, IID) for IID in self.parent.lotOverTextures ]
            lst.sort(cmp=lambda n1, n2: CmpTGI(n1.tgi, n2.tgi))
            self.propList.Reset(VirtualDat.this.ilOver, lst, FillListForTex, DisplayNameForTex)
        elif item == tree.lotPropsItem:
            self.parent.lotPropDescs.sort(cmp=lambda n1, n2: cmp(n1.name.upper(), n2.name.upper()))
            self.propList.Reset(VirtualDat.this.ilStandardModels, self.parent.lotPropDescs, FillListForPropsAsSingle, DisplayNameForPropsName)
        elif item == tree.lotFloraItem:
            self.parent.lotFloraDescs.sort(cmp=lambda n1, n2: cmp(n1.name.upper(), n2.name.upper()))
            self.propList.Reset(VirtualDat.this.ilStandardModels, self.parent.lotFloraDescs, FillListForPropsAsSingle, DisplayNameForPropsName)
        elif item == tree.lotIcon:
            IID = self.parent.examplar.entry.tgi[2]
            entry = VirtualDat.this.getEntry(2238569388L, 1782082854, IID)
            self.propList.Reset(VirtualDat.this.ilIcon, [entry], FillListForIcon, DisplayNameForIcon)
        else:
            catID = tree.GetPyData(item)
            if catID != None:
                if catID.__class__ == GroupProxy:
                    catID.Display(self.propList)
                else:
                    VirtualDat.this.categories[catID].descriptors.sort(cmp=lambda n1, n2: cmp(n1.name.upper(), n2.name.upper()))
                    self.propList.Reset(VirtualDat.this.ilStandardModels, VirtualDat.this.categories[catID].descriptors, FillListForPropsAsFamily, DisplayNameForPropsName, catID)
            else:
                self.propList.Reset(VirtualDat.this.ilBase, None, FillListForNothing, DisplayNameForTex)
        return

    def Save(self):
        fout = open('groups.ini', 'wt')
        x, y = self.GetPositionTuple()
        w, h = self.GetSizeTuple()
        fout.write('self.Move( ( %d, %d ) )\n' % (x, y))
        fout.write('self.SetSize( ( %d, %d ) )\n' % (w, h))
        for group in self.groups:
            group.Save(fout)

        fout.close()

    def OnCloseWindow(self, event):
        self.Save()
        self.parent.LETools = None
        event.Skip()
        return True
# okay decompiling SC4LETools.pyo
