"""SC4 Lot Editor (LE) tools for editing building lots."""
import datetime
import io
import random

import wx
import wx.lib.agw.balloontip as BT
from PIL import Image, ImageDraw

try:
    import win32gui
except ImportError:
    win32gui = None

from . import FSHConverter, treeDnD
from .ATCReader import *
from .config import load_lot_editor
from .paths import asset_path, ensure_user_data_dir, image_db_path, user_data_path
from .SC4Data import *
from .SC4OpenGL import *
from .translation import *
from .util import basic_cmp


def CmpTGI(tgi1, tgi2):
    if tgi1[0] == tgi2[0]:
        if tgi1[1] == tgi2[1]:
            return basic_cmp(tgi1[2], tgi2[2])
        else:
            return basic_cmp(tgi1[1], tgi2[1])
    else:
        return basic_cmp(tgi1[0], tgi2[0])


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
            if isinstance(item, tuple):
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
                        if not isinstance(item, tuple):
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
        except Exception:
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
            if isinstance(what, tuple):
                if what not in self.items:
                    self.items.append(what)
            elif what not in self.items:
                self.items.append(what)
                if self.itemIdx is not None and tree is not None:
                    try:
                        sub = VirtualDat.this.categories[what]
                    except KeyError:
                        return

                    idx = tree.AppendItem(self.itemIdx, sub.Name)
                    tree.SetPyData(idx, sub.ID)
                    tree.Refresh(False)
        if self.kind == 4:
            if isinstance(what, tuple):
                if what not in self.items:
                    self.items.append(what)
        return

    def Display(self, lstCtrl):
        if self.kind == 0 or self.kind == 1:
            lst = [ VirtualDat.this.getEntry(2058686020, 159781726, IID) for IID in self.items ]
            lst = [ desc for desc in lst if desc is not None ]
            lst.sort(key=lambda n: n.tgi)
            if self.kind == 0:
                il = VirtualDat.this.ilBase
            else:
                il = VirtualDat.this.ilOver
            lstCtrl.Reset(il, lst, FillListForTex, DisplayNameForTex)
        else:

            def GetDescFromTGI(tgi):
                selectedDesc = None
                if isinstance(tgi, tuple):
                    t = tgi[0]
                    g = tgi[1]
                    i = tgi[2]
                    possibles = filter(lambda desc: desc.exemplar.entry.tgi[0] == t and desc.exemplar.entry.tgi[1] == g and desc.exemplar.entry.tgi[2] == i, VirtualDat.this.categories[210746660].descriptors)
                    for desc in possibles:
                        selectedDesc = desc
                        break

                return selectedDesc

            lst = [ GetDescFromTGI(tgi) for tgi in self.items ]
            lst = [ desc for desc in lst if desc is not None ]
            lst.sort(key=lambda n: n.name.upper())
            lstCtrl.Reset(VirtualDat.this.ilStandardModels, lst, FillListForProps, DisplayNameForPropsName)
        return


def BuildImageForTGI(tgi, size=128):
    fileName = str(image_db_path('%s-%s.jpg' % (hex2str(tgi[1]), hex2str(tgi[2])), large=True))
    if not os.path.exists(fileName):
        fileName = str(asset_path('other', 'NoPreview.jpg'))
    return Image.open(fileName).convert('RGB').resize((size, size), Image.BICUBIC)


def BitmapFromPIL(pilz):
    image = wx.Image(pilz.size[0], pilz.size[1])
    image.SetData(pilz.convert('RGB').tobytes())
    return image.ConvertToBitmap()


def BuildImagesForPropStates(exemplar, size=128):
    rkt0 = exemplar.GetProp(662775840)
    rkt1 = exemplar.GetProp(662775841)
    rkt3 = exemplar.GetProp(662775843)
    rkt4 = exemplar.GetProp(662775844)
    rkt5 = exemplar.GetProp(662775845)
    if rkt0 and rkt0[0] == 1523640343:
        return [BuildImageForTGI(tuple(rkt0), size)]
    elif rkt1 and rkt1[0] == 1523640343:
        return [BuildImageForTGI(tuple(rkt1), size)]
    elif rkt3 and rkt3[0] == 1523640343:
        return [BuildImageForTGI(tuple(rkt3[0:2] + [rkt3[-1]]), size)]
    elif rkt4:
        nbChoices = len(rkt4) // 8
        images = []
        for cb in range(nbChoices):
            rkt = rkt4[cb * 8:cb * 8 + 8]
            rkt = rkt[4:]
            tgi = (0, 0, 0)
            if rkt[0] == 662775840 and rkt[1] == 1523640343:
                tgi = tuple(rkt[1:])
            elif rkt[0] == 662775841 and rkt[1] == 1523640343:
                tgi = tuple(rkt[1:])
            elif rkt[0] == 662775845 and rkt[1] == 1523640343:
                tgi = tuple(rkt[1:])
            images.append(BuildImageForTGI(tgi, size))
        return images
    elif rkt5 and rkt5[0] == 1523640343:
        return [BuildImageForTGI(tuple(rkt5), size)]
    return [Image.open(asset_path('other', 'NoPreview.jpg')).convert('RGB').resize((size, size), Image.BICUBIC)]


def BuildImageForProp(exemplar):
    images = BuildImagesForPropStates(exemplar, 128)
    if len(images) == 1:
        return (BitmapFromPIL(images[0]), False)
    fullImage = Image.new('RGB', (128 * len(images), 128))
    draw = ImageDraw.Draw(fullImage)
    for idx, img in enumerate(images):
        fullImage.paste(img.convert('RGB'), (128 * idx, 0))
        draw.rectangle((128 * idx, 0, 128 * idx + 127, 127), outline=(255, 255, 255))
    return (BitmapFromPIL(fullImage), True)


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
        if win32gui is not None:
            win32gui.SendMessage(self.GetHandle(), 4096 + 53, 0, 64 + 10)

    def OnRemoveItem(self, event):
        group = self.parent.IsItPersonalGroup(self.parent.currentItem)
        if group is not None:
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
            exemplar = entry.exemplar
            img, multi = BuildImageForProp(exemplar)
            tipballoon.SetBalloonIcon(img)
            if multi:
                tipballoon.SetBalloonMessage('Seasonal/Timed prop\n' + os.path.split(entry.fileName)[1])
            else:
                tipballoon.SetBalloonMessage(os.path.split(entry.fileName)[1])
        elif data.__class__ == FamilyProxy:
            catID = data.what
            thisId = idx
            tgi = (0, 0, 0)
            VirtualDat.this.categories[catID].descriptors.sort(key=lambda n: n.name.upper())
            thisDesc = None
            for desc in VirtualDat.this.categories[catID].descriptors:
                if desc.exemplar.entry.tgi[0] != 1697917002:
                    continue
                if desc.exemplar.GetProp(16)[0] != 30 and desc.exemplar.GetProp(16)[0] != 15:
                    continue
                if thisId == 0:
                    tgi = GetTGIForProp(desc)
                    thisDesc = desc
                    break
                thisId -= 1

            img, multi = BuildImageForProp(thisDesc.exemplar)
            tipballoon.SetBalloonIcon(img)
            if multi:
                tipballoon.SetBalloonMessage('Seasonal/Timed prop\n' + os.path.split(thisDesc.exemplar.entry.fileName)[1])
            else:
                tipballoon.SetBalloonMessage(os.path.split(thisDesc.exemplar.entry.fileName)[1])
        elif data.__class__ == BaseProxy or data.__class__ == OverlayProxy:

            def LoadTexForTGI(tgi):
                texEntry = VirtualDat.this.getEntry(2058686020, 159781726, tgi + 4)
                if texEntry is None:
                    return (Image.open(asset_path('other', 'NoPreview.jpg')).resize((128, 128), Image.BICUBIC), 0, '')
                texEntry.read_file(None, True, True)
                nbrLayers, trueAlpha, img, alpha, size = FSHConverter.decodeFSH(texEntry.content)
                nbOfBytes = size[0] * size[1]
                texEntry.content = None
                texEntry.rawContent = None
                fullImage = Image.new('RGB', (128 * nbrLayers, 128))
                for layerIdx in range(nbrLayers):
                    imBmp = Image.frombytes('RGB', size, img[nbOfBytes * 3 * layerIdx:nbOfBytes * 3 * (layerIdx + 1)])
                    if trueAlpha:
                        blank = Image.new('RGB', size, 16777215)
                        alphaLayer = Image.frombytes('L', size, alpha[nbOfBytes * layerIdx:nbOfBytes * (layerIdx + 1)])
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
                    img, nb, fName = LoadTexForTGI((tgi & 4294905855) + iid)
                    if nb > 0:
                        nbValid += 1
                    imgs.append(img)
                    maxWidth = max(maxWidth, img.size[0])

                if nbValid > 1:
                    fullImage = Image.new(fullImage.mode, (maxWidth, 4 * 128), 0)
                    for i, img in enumerate(imgs):
                        fullImage.paste(img.convert('RGB'), (0, 128 * i))

            image = wx.Image(fullImage.size[0], fullImage.size[1])
            image.SetData(fullImage.convert('RGB').tobytes())
            tipballoon.SetBalloonIcon(image.ConvertToBitmap())
            strMsg = os.path.split(fileName)[1]
            tipballoon.SetBalloonMessage(strMsg)
        else:
            tipballoon.SetBalloonIcon(None)
        return True

    def OnItemListSelected(self, event):
        item = event.GetItem()
        idx = event.GetIndex()

    def SetPyData(self, idx, what):
        self.pyDatas[idx] = what

    def GetPyData(self, idx):
        try:
            return self.pyDatas[idx]
        except Exception:
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
        if catID is None:
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
                if py is not None:
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
        except Exception:
            try:
                idx = VirtualDat.this.baseTexEntriesDict[texEntry]
                ProxyClass = BaseProxy
            except Exception:
                continue

        index = self.InsertImageStringItem(self.GetItemCount(), fnPrint(texEntry), idx)
        self.SetItemImage(index, idx, idx)
        self.SetPyData(index, ProxyClass(texEntry))


class PropProxy():

    def __init__(self, desc):
        self.what = desc.exemplar.entry.tgi


class FamilyProxy():

    def __init__(self, familyID):
        self.what = familyID


def FillListForPropsAsFamily(self, entries, fnPrint, catID):
    FillListForProps(self, entries, fnPrint, catID)


def FillListForPropsAsSingle(self, entries, fnPrint):
    FillListForProps(self, entries, fnPrint)


def GetTGIForProp(desc):
    rkt0 = desc.exemplar.GetProp(662775840)
    rkt1 = desc.exemplar.GetProp(662775841)
    rkt3 = desc.exemplar.GetProp(662775843)
    rkt4 = desc.exemplar.GetProp(662775844)
    rkt5 = desc.exemplar.GetProp(662775845)
    tgi = (0, 0, 0)
    if rkt0 and rkt0[0] == 1523640343:
        tgi = tuple(rkt0)
    elif rkt1 and rkt1[0] == 1523640343:
        tgi = tuple(rkt1)
    elif rkt3 and rkt3[0] == 1523640343:
        tgi = tuple(rkt3[0:2] + [rkt3[-1]])
    else:
        if rkt4:
            nbChoices = len(rkt4) // 4
            for cb in range(nbChoices):
                rkt = rkt4[cb * 4:cb * 4 + 4]
                if rkt[0] == 662775841:
                    tgi = tuple(rkt[1:])
                    break

        if rkt5 and rkt5[0] == 1523640343:
            tgi = tuple(rkt5)
    return tgi


def FillListForProps(self, entries, fnPrint, catID=None):
    for desc in entries:
        if desc.exemplar.entry.tgi[0] != 1697917002:
            continue
        if desc.exemplar.GetProp(16)[0] != 30 and desc.exemplar.GetProp(16)[0] != 15:
            continue
        tgi = GetTGIForProp(desc)
        idx = 0
        if tgi != (0, 0, 0):
            # Lazily decode + register this model's thumbnail on first use.
            idx = EnsureStandardModelImage(VirtualDat.this, tgi)

        if idx == -1:
            self.InsertItem(self.GetItemCount(), fnPrint(desc))
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
        if texEntry is not None:
            try:
                if texEntry.content is None:
                    texEntry.read_file(None, True, True)
            except Exception:
                texEntry.read_file(None, True, True)

            cIO = io.BytesIO(texEntry.content)
            pilz = Image.open(cIO).convert('RGB')
            cIO.close()
            image = wx.Image(44 * 4, 44)
            image.SetData(pilz.convert('RGB').tobytes())
            VirtualDat.this.ilIcon.Replace(0, image.ConvertToBitmap())
            index = self.InsertImageStringItem(self.GetItemCount(), fnPrint(texEntry), 0)
            self.SetItemImage(index, 0, 0)

    return


def FillListForNothing(self, entries, fnPrint):
    pass


def DisplayNameForPropsTGI(desc):
    return '%s\n%s' % (hex2str(desc.exemplar.entry.tgi[2])[2:], desc.exemplar.GetProp(32)[0])


def DisplayNameForPropsName(desc):
    return '%s\n%s' % (desc.exemplar.GetProp(32)[0], hex2str(desc.exemplar.entry.tgi[2])[2:])


def DisplayNameForTex(entry):
    return '%s' % hex2str(entry.tgi[2] - 3)[2:]


class LEAssetItem(object):

    def __init__(self, kind, label, sublabel, proxy, source=None, badge=None, extra_text=''):
        self.kind = kind
        self.label = label
        self.sublabel = sublabel
        self.proxy = proxy
        self.source = source
        self.badge = badge or kind
        # Extra free text folded into search (e.g. a family's member names).
        self.extra_text = extra_text

    @property
    def search_text(self):
        file_name = ''
        try:
            src = self.source
            if hasattr(src, 'fileName'):
                file_name = src.fileName or ''
            elif hasattr(src, 'exemplar'):
                file_name = src.exemplar.entry.fileName or ''
        except Exception:
            file_name = ''
        return ('%s %s %s %s %s %s' % (self.kind, self.badge, self.label,
                                       self.sublabel, self.extra_text, file_name)).lower()

    @property
    def type_label(self):
        labels = {
            'base texture': LEXAssetTypeBaseTexture,
            'overlay texture': LEXAssetTypeOverlayTexture,
            'prop': LEXAssetTypeProp,
            'flora': LEXAssetTypeFlora,
            'family': LEXAssetTypeFamily,
            'icon': LEXAssetTypeIcon,
        }
        return labels.get(self.kind, self.kind)

    @property
    def fav_key(self):
        """Stable identifier for the favorites list (survives rebuilds)."""
        try:
            if self.kind in ('base texture', 'overlay texture'):
                return '%s:%d' % (self.kind, self.source.tgi[2])
            if self.kind in ('prop', 'flora'):
                t = self.source.exemplar.entry.tgi
                return '%s:%d-%d-%d' % (self.kind, t[0], t[1], t[2])
            if self.kind == 'family':
                return 'family:%d' % self.source
        except Exception:
            pass
        return '%s:%s' % (self.kind, self.sublabel)


class LEAssetThumbnailProvider(object):

    def __init__(self):
        self.cache = {}
        self.state_counts = {}
        self.state_strips = {}
        self.thumb_size = 72
        self.placeholder = self._build_placeholder('...')
        # Pending thumbnail loads. The grid rebuilds this via RestrictTo()
        # after every repaint, so a fast scroll never leaves a backlog of
        # off-screen thumbnails queued ahead of the ones now on screen.
        self._queue = []            # keys; the end is processed first
        self._queue_item = {}       # key -> item
        self._queue_cb = {}         # key -> on_loaded callback
        self._draining = False

    def SetThumbSize(self, size):
        """Change the thumbnail edge length and drop now-wrong cached bitmaps."""
        size = int(size)
        if size == self.thumb_size:
            return
        self.thumb_size = size
        self.cache = {}
        self.placeholder = self._build_placeholder('...')

    def _build_placeholder(self, label, size=None):
        size = size or self.thumb_size
        margin = max(4, size // 12)
        inner = size - 2 * margin
        bmp = wx.Bitmap(size, size)
        dc = wx.MemoryDC(bmp)
        dc.SetBackground(wx.Brush(wx.Colour(232, 235, 238)))
        dc.Clear()
        dc.SetPen(wx.Pen(wx.Colour(180, 187, 194)))
        dc.SetBrush(wx.Brush(wx.Colour(245, 247, 249)))
        dc.DrawRoundedRectangle(margin, margin, inner, inner, 6)
        dc.SetTextForeground(wx.Colour(98, 108, 118))
        dc.DrawLabel(label, wx.Rect(0, 0, size, size), wx.ALIGN_CENTER)
        dc.SelectObject(wx.NullBitmap)
        return bmp

    def _bitmap_from_pil(self, image, size=None):
        if size is None:
            size = (self.thumb_size, self.thumb_size)
        pil = image.convert('RGB').resize(size, Image.BICUBIC)
        wx_image = wx.Image(pil.size[0], pil.size[1])
        wx_image.SetData(pil.tobytes())
        return wx_image.ConvertToBitmap()

    def _scale_bitmap(self, bmp, size=None):
        if not bmp or not bmp.IsOk():
            return self.placeholder
        if size is None:
            size = (self.thumb_size, self.thumb_size)
        image = bmp.ConvertToImage()
        image = image.Scale(size[0], size[1], wx.IMAGE_QUALITY_HIGH)
        return image.ConvertToBitmap()

    def _texture_bitmap(self, entry, overlay):
        try:
            image_list = VirtualDat.this.ilOver if overlay else VirtualDat.this.ilBase
            idx_map = VirtualDat.this.overTexEntriesDict if overlay else VirtualDat.this.baseTexEntriesDict
            idx = idx_map.get(entry)
            if idx is not None:
                return self._scale_bitmap(image_list.GetBitmap(idx))
        except Exception:
            pass
        try:
            entry.read_file(None, True, True)
            nbrLayers, trueAlpha, img, alpha, size = FSHConverter.decodeFSH(entry.content)
            pil = Image.frombytes('RGB', size, img[:size[0] * size[1] * 3])
            if trueAlpha:
                blank = Image.new('RGB', size, 16777215)
                alpha_layer = Image.frombytes('L', size, alpha[:size[0] * size[1]])
                pil = Image.composite(pil, blank, alpha_layer)
            return self._bitmap_from_pil(pil)
        except Exception:
            return self._build_placeholder('!')
        finally:
            try:
                entry.content = None
                entry.rawContent = None
            except Exception:
                pass

    def _prop_bitmap(self, desc):
        try:
            images = BuildImagesForPropStates(desc.exemplar, 128)
            return self._bitmap_from_pil(images[0])
        except Exception:
            return self._build_placeholder('!')

    def _family_descs(self, cat_id):
        try:
            descs = VirtualDat.this.categories[cat_id].descriptors
        except Exception:
            return []
        usable = []
        for desc in descs:
            try:
                if desc.exemplar.entry.tgi[0] != 1697917002:
                    continue
                if desc.exemplar.GetProp(16)[0] in (30, 15):
                    usable.append(desc)
            except Exception:
                pass
        usable.sort(key=lambda n: n.name.upper())
        return usable

    def _family_images(self, item, size=96):
        images = []
        for desc in self._family_descs(item.source):
            try:
                images.append(BuildImagesForPropStates(desc.exemplar, size)[0])
            except Exception:
                pass
        if not images:
            images.append(Image.open(asset_path('other', 'NoPreview.jpg')).convert('RGB').resize((size, size), Image.BICUBIC))
        return images

    def _family_bitmap(self, item):
        try:
            return self._bitmap_from_pil(self._family_images(item, 128)[0])
        except Exception:
            return self._build_placeholder('F')

    def _prop_state_images(self, item):
        key = self._cache_key(item)
        if key not in self.state_strips:
            images = BuildImagesForPropStates(item.source.exemplar, 96)
            self.state_counts[key] = len(images)
            full = Image.new('RGB', (96 * len(images), 96), 0xffffff)
            draw = ImageDraw.Draw(full)
            for idx, img in enumerate(images):
                full.paste(img.convert('RGB'), (96 * idx, 0))
                draw.rectangle((96 * idx, 0, 96 * idx + 95, 95), outline=(190, 195, 200))
            self.state_strips[key] = BitmapFromPIL(full)
        return self.state_strips[key]

    def _family_state_images(self, item):
        key = self._cache_key(item)
        if key not in self.state_strips:
            images = self._family_images(item, 80)
            self.state_counts[key] = len(images)
            cols = min(6, max(1, len(images)))
            rows = (len(images) + cols - 1) // cols
            full = Image.new('RGB', (80 * cols, 80 * rows), 0xffffff)
            draw = ImageDraw.Draw(full)
            for idx, img in enumerate(images):
                x = idx % cols * 80
                y = idx // cols * 80
                full.paste(img.convert('RGB'), (x, y))
                draw.rectangle((x, y, x + 79, y + 79), outline=(190, 195, 200))
            self.state_strips[key] = BitmapFromPIL(full)
        return self.state_strips[key]

    def StateCount(self, item):
        if item.kind not in ('prop', 'flora', 'family') or item.source is None:
            return 1
        key = self._cache_key(item)
        if key not in self.state_counts:
            try:
                if item.kind == 'family':
                    self.state_counts[key] = len(self._family_descs(item.source))
                else:
                    rkt4 = item.source.exemplar.GetProp(662775844)
                    if rkt4:
                        self.state_counts[key] = max(1, len(rkt4) // 8)
                    else:
                        self.state_counts[key] = 1
            except Exception:
                self.state_counts[key] = 1
        return self.state_counts.get(key, 1)

    def StateStrip(self, item):
        if self.StateCount(item) <= 1:
            return None
        try:
            if item.kind == 'family':
                return self._family_state_images(item)
            return self._prop_state_images(item)
        except Exception:
            return None

    def CountLabel(self, item):
        if item.kind == 'family':
            return LEXAssetBrowserMembers
        return LEXAssetBrowserStates

    def _cache_key(self, item):
        return (item.kind, item.sublabel, id(item.source))

    def _build_bitmap(self, item):
        bmp = self.placeholder
        if item.kind == 'base texture':
            bmp = self._texture_bitmap(item.source, False)
        elif item.kind == 'overlay texture':
            bmp = self._texture_bitmap(item.source, True)
        elif item.kind in ('prop', 'flora'):
            bmp = self._prop_bitmap(item.source)
        elif item.kind == 'family':
            bmp = self._family_bitmap(item)
        elif item.kind == 'icon':
            bmp = self._build_placeholder('I')
        return bmp

    def _drain(self):
        if not self._queue:
            self._draining = False
            return
        key = self._queue.pop()
        item = self._queue_item.pop(key, None)
        on_loaded = self._queue_cb.pop(key, None)
        if item is not None and key not in self.cache:
            try:
                self.cache[key] = self._build_bitmap(item)
            except Exception:
                self.cache[key] = self._build_placeholder('!')
            if on_loaded:
                try:
                    on_loaded(False)
                except RuntimeError:
                    pass
        wx.CallLater(1, self._drain)

    def RestrictTo(self, items):
        """Limit pending loads to *items* (the currently visible cards).

        Called by the grid after every repaint: requests for cards scrolled
        past are dropped, and the queue is ordered so the visible cards
        decode top-to-bottom instead of behind a stale backlog.
        """
        keep = []
        seen = set()
        for it in items:
            key = self._cache_key(it)
            if key in self._queue_item and key not in seen:
                seen.add(key)
                keep.append(key)
                self._queue_item[key] = it
        for key in list(self._queue_item.keys()):
            if key not in seen:
                self._queue_item.pop(key, None)
                self._queue_cb.pop(key, None)
        # _drain() pops from the end, so reverse for top-down decode order.
        self._queue = list(reversed(keep))

    def GetBitmap(self, item, on_loaded=None):
        key = self._cache_key(item)
        if key in self.cache:
            return self.cache[key]
        if on_loaded is not None:
            self._queue_item[key] = item
            self._queue_cb[key] = on_loaded
            if key not in self._queue:
                self._queue.append(key)
            if not self._draining:
                self._draining = True
                wx.CallLater(1, self._drain)
        return self.placeholder

    def GetBitmapNow(self, item):
        key = self._cache_key(item)
        if key in self.cache:
            return self.cache[key]
        bmp = self._build_bitmap(item)
        self.cache[key] = bmp
        return bmp


class LEAssetGrid(wx.ScrolledWindow):

    GAP = 10

    def __init__(self, parent, thumbnail_provider, on_select=None, on_context=None, on_activate=None):
        wx.ScrolledWindow.__init__(self, parent, -1, style=wx.BORDER_NONE | wx.VSCROLL)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetScrollRate(0, 24)
        self.thumbnail_provider = thumbnail_provider
        # Card size tracks the thumbnail size; CARD_W/H are derived from it.
        self.THUMB = thumbnail_provider.thumb_size
        self._set_card_metrics()
        self.on_select = on_select
        self.on_context = on_context
        self.on_activate = on_activate
        self.items = []
        self.selected = -1
        self.hovered = -1
        self.drag_start = None
        self.state_popup = None
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        self.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)
        self.Bind(wx.EVT_MOTION, self.OnMotion)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeaveWindow)
        self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
        self.Bind(wx.EVT_LEFT_DCLICK, self.OnDoubleClick)

    def SetItems(self, items):
        self.items = items
        self.selected = -1
        self.hovered = -1
        self._hide_state_popup()
        self._update_virtual_size()
        self.Refresh(False)

    def _set_card_metrics(self):
        """Derive card width/height from the thumbnail size.

        Small thumbnails drop the badge and sub-label so the card stays a
        tight frame around the image instead of mostly chrome.
        """
        self.compact_cards = self.THUMB < 72
        if self.compact_cards:
            self.CARD_W = self.THUMB + 40
            self.CARD_H = self.THUMB + 42
        else:
            self.CARD_W = self.THUMB + 70
            self.CARD_H = self.THUMB + 88

    def SetThumbSize(self, size):
        """Resize the thumbnails (and the cards that frame them)."""
        self.thumbnail_provider.SetThumbSize(size)
        self.THUMB = self.thumbnail_provider.thumb_size
        self._set_card_metrics()
        self._update_virtual_size()
        self.Refresh(False)

    def _columns(self):
        width = max(1, self.GetClientSize()[0])
        return max(1, (width + self.GAP) // (self.CARD_W + self.GAP))

    def _update_virtual_size(self):
        cols = self._columns()
        rows = (len(self.items) + cols - 1) // cols
        self.SetVirtualSize((max(self.CARD_W, self.GetClientSize()[0]), rows * (self.CARD_H + self.GAP) + self.GAP))

    def OnSize(self, event):
        self._update_virtual_size()
        self.Refresh(False)
        event.Skip()

    def _item_rect(self, idx):
        cols = self._columns()
        col = idx % cols
        row = idx // cols
        x = self.GAP + col * (self.CARD_W + self.GAP)
        y = self.GAP + row * (self.CARD_H + self.GAP)
        return wx.Rect(x, y, self.CARD_W, self.CARD_H)

    def _hit_test(self, pos):
        x, y = self.CalcUnscrolledPosition(pos[0], pos[1])
        cols = self._columns()
        col = x // (self.CARD_W + self.GAP)
        row = y // (self.CARD_H + self.GAP)
        idx = int(row * cols + col)
        if idx < 0 or idx >= len(self.items):
            return -1
        if self._item_rect(idx).Contains(x, y):
            return idx
        return -1

    def _shorten(self, dc, text, width):
        if dc.GetTextExtent(text)[0] <= width:
            return text
        ellipsis = '...'
        while text and dc.GetTextExtent(text + ellipsis)[0] > width:
            text = text[:-1]
        return text + ellipsis

    def OnPaint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        self.PrepareDC(dc)
        dc.SetBackground(wx.Brush(wx.Colour(248, 249, 250)))
        dc.Clear()
        if not self.items:
            dc.SetTextForeground(wx.Colour(92, 99, 106))
            dc.DrawLabel(LEXAssetBrowserNoMatches, wx.Rect(0, 20, self.GetClientSize()[0], 30), wx.ALIGN_CENTER)
            return
        view_y = self.CalcUnscrolledPosition(0, 0)[1]
        end_y = view_y + self.GetClientSize()[1]
        cols = self._columns()
        start_row = max(0, view_y // (self.CARD_H + self.GAP))
        end_row = min((len(self.items) + cols - 1) // cols, end_y // (self.CARD_H + self.GAP) + 2)
        visible = []
        for row in range(int(start_row), int(end_row)):
            for col in range(cols):
                idx = row * cols + col
                if idx >= len(self.items):
                    break
                self._draw_card(dc, idx, self._item_rect(idx))
                visible.append(self.items[idx])
        # Drop thumbnail loads for cards no longer on screen so the cards we
        # scrolled TO decode immediately instead of behind a stale backlog.
        self.thumbnail_provider.RestrictTo(visible)

    def _draw_card(self, dc, idx, rect):
        item = self.items[idx]
        selected = idx == self.selected
        bg = wx.Colour(221, 235, 249) if selected else wx.Colour(255, 255, 255)
        border = wx.Colour(65, 123, 188) if selected else wx.Colour(209, 214, 219)
        dc.SetBrush(wx.Brush(bg))
        dc.SetPen(wx.Pen(border, 2 if selected else 1))
        dc.DrawRoundedRectangle(rect.x, rect.y, rect.width, rect.height, 6)
        bmp = self.thumbnail_provider.GetBitmap(item, self.Refresh)
        tx = rect.x + (rect.width - self.THUMB) // 2
        ty = rect.y + 12
        dc.DrawBitmap(bmp, tx, ty, True)
        state_count = self.thumbnail_provider.StateCount(item)
        if state_count > 1:
            state_label = str(state_count)
            indicator = wx.Rect(tx + self.THUMB - 22, ty + self.THUMB - 20, 20, 18)
            dc.SetBrush(wx.Brush(wx.Colour(45, 92, 150)))
            dc.SetPen(wx.Pen(wx.Colour(45, 92, 150)))
            dc.DrawRoundedRectangle(indicator.x, indicator.y, indicator.width, indicator.height, 6)
            dc.SetTextForeground(wx.Colour(255, 255, 255))
            dc.SetFont(wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
            dc.DrawLabel(state_label, indicator, wx.ALIGN_CENTER)
        if self.compact_cards:
            # Small cards: just the name under the thumbnail.
            dc.SetTextForeground(wx.Colour(25, 29, 33))
            dc.SetFont(wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
            dc.DrawLabel(self._shorten(dc, item.label, rect.width - 10),
                         wx.Rect(rect.x + 5, rect.y + 19 + self.THUMB, rect.width - 10, 16),
                         wx.ALIGN_CENTER)
            return
        badge_rect = wx.Rect(rect.x + 10, rect.y + 19 + self.THUMB, rect.width - 20, 18)
        dc.SetBrush(wx.Brush(wx.Colour(238, 241, 244)))
        dc.SetPen(wx.Pen(wx.Colour(220, 224, 228)))
        dc.DrawRoundedRectangle(badge_rect.x, badge_rect.y, badge_rect.width, badge_rect.height, 5)
        dc.SetTextForeground(wx.Colour(74, 82, 90))
        dc.SetFont(wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        dc.DrawLabel(self._shorten(dc, item.badge, badge_rect.width - 8), badge_rect.Deflate(4, 0), wx.ALIGN_CENTER)
        dc.SetTextForeground(wx.Colour(25, 29, 33))
        dc.SetFont(wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        dc.DrawLabel(self._shorten(dc, item.label, rect.width - 18), wx.Rect(rect.x + 9, rect.y + 44 + self.THUMB, rect.width - 18, 18), wx.ALIGN_CENTER)
        dc.SetTextForeground(wx.Colour(96, 104, 112))
        dc.SetFont(wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        dc.DrawLabel(self._shorten(dc, item.sublabel, rect.width - 18), wx.Rect(rect.x + 9, rect.y + 65 + self.THUMB, rect.width - 18, 18), wx.ALIGN_CENTER)

    def OnLeftDown(self, event):
        self._hide_state_popup()
        self.SetFocus()
        idx = self._hit_test(event.GetPosition())
        if idx != -1:
            self.selected = idx
            self.drag_start = event.GetPosition()
            if self.on_select:
                self.on_select(self.items[idx])
            self.Refresh(False)
        event.Skip()

    def OnLeftUp(self, event):
        self.drag_start = None
        event.Skip()

    def OnRightDown(self, event):
        self._hide_state_popup()
        idx = self._hit_test(event.GetPosition())
        if idx != -1:
            self.selected = idx
            if self.on_select:
                self.on_select(self.items[idx])
            self.Refresh(False)
            if self.on_context:
                self.on_context(self.items[idx])
        event.Skip()

    def OnDoubleClick(self, event):
        idx = self._hit_test(event.GetPosition())
        if idx != -1 and self.on_activate:
            self.on_activate(self.items[idx])
        event.Skip()

    def _card_tooltip(self, item):
        lines = [item.label, item.type_label]
        if item.sublabel and item.sublabel != item.label:
            lines.append(item.sublabel)
        try:
            source = item.source
            file_name = getattr(source, 'fileName', None)
            if file_name is None and hasattr(source, 'exemplar'):
                file_name = source.exemplar.entry.fileName
            if file_name:
                lines.append(os.path.split(file_name)[1])
        except Exception:
            pass
        return '\n'.join(lines)

    def OnMotion(self, event):
        idx = self._hit_test(event.GetPosition())
        if idx != self.hovered:
            self.hovered = idx
            self._show_state_popup(idx, event.GetPosition())
            if idx == -1:
                self.UnsetToolTip()
            else:
                self.SetToolTip(self._card_tooltip(self.items[idx]))
        if not event.Dragging() or not event.LeftIsDown() or self.drag_start is None:
            event.Skip()
            return
        if abs(event.GetX() - self.drag_start.x) < 5 and abs(event.GetY() - self.drag_start.y) < 5:
            event.Skip()
            return
        idx = self.selected
        self.drag_start = None
        if idx < 0 or idx >= len(self.items):
            event.Skip()
            return
        comp = wx.DataObjectComposite()
        dd = treeDnD.DropData()
        dd.setObject(self.items[idx].proxy)
        comp.Add(dd)
        dropSource = wx.DropSource(self)
        dropSource.SetData(comp)
        dropSource.DoDragDrop(wx.Drag_AllowMove)
        event.Skip()

    def OnLeaveWindow(self, event):
        self.hovered = -1
        self._hide_state_popup()
        event.Skip()

    def _hide_state_popup(self):
        if self.state_popup is not None:
            try:
                self.state_popup.Destroy()
            except RuntimeError:
                pass
            self.state_popup = None

    def _show_state_popup(self, idx, pos):
        self._hide_state_popup()
        if idx < 0 or idx >= len(self.items):
            return
        item = self.items[idx]
        strip = self.thumbnail_provider.StateStrip(item)
        if strip is None:
            return
        popup = wx.PopupTransientWindow(self, wx.BORDER_SIMPLE)
        panel = wx.Panel(popup, -1)
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(panel, -1, '%d %s' % (self.thumbnail_provider.StateCount(item), self.thumbnail_provider.CountLabel(item)))
        sizer.Add(label, 0, wx.ALL, 6)
        sizer.Add(wx.StaticBitmap(panel, -1, strip), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        panel.SetSizer(sizer)
        sizer.Fit(panel)
        popup.SetSize(panel.GetBestSize())
        screen_pos = self.ClientToScreen((pos.x + 16, pos.y + 18))
        popup.Position(screen_pos, (0, 0))
        popup.Popup()
        self.state_popup = popup


class LEAssetList(wx.ListCtrl):

    def __init__(self, parent, on_select=None, on_context=None, on_activate=None):
        wx.ListCtrl.__init__(self, parent, -1, style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_SINGLE_SEL | wx.BORDER_NONE)
        self.items = []
        self.on_select = on_select
        self.on_context = on_context
        self.on_activate = on_activate
        self.InsertColumn(0, LEXInspectorName)
        self.InsertColumn(1, LEXInspectorType)
        self.InsertColumn(2, LEXInspectorID)
        self.SetColumnWidth(0, 190)
        self.SetColumnWidth(1, 95)
        self.SetColumnWidth(2, 95)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnSelected)
        self.Bind(wx.EVT_LIST_BEGIN_DRAG, self.OnBeginDrag)
        self.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.OnRightClick)
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnActivated)

    def SetItems(self, items):
        self.items = items
        self.SetItemCount(len(items))
        self.Refresh(False)

    def OnGetItemText(self, item, col):
        if item < 0 or item >= len(self.items):
            return ''
        asset = self.items[item]
        if col == 0:
            return asset.label
        if col == 1:
            return asset.type_label
        return asset.sublabel

    def OnSelected(self, event):
        idx = event.GetIndex()
        if self.on_select and 0 <= idx < len(self.items):
            self.on_select(self.items[idx])

    def OnRightClick(self, event):
        idx = event.GetIndex()
        if self.on_context and 0 <= idx < len(self.items):
            self.on_context(self.items[idx])

    def OnActivated(self, event):
        idx = event.GetIndex()
        if self.on_activate and 0 <= idx < len(self.items):
            self.on_activate(self.items[idx])

    def OnBeginDrag(self, event):
        idx = event.GetIndex()
        if idx < 0 or idx >= len(self.items):
            return
        comp = wx.DataObjectComposite()
        dd = treeDnD.DropData()
        dd.setObject(self.items[idx].proxy)
        comp.Add(dd)
        dropSource = wx.DropSource(self)
        dropSource.SetData(comp)
        dropSource.DoDragDrop(wx.Drag_AllowMove)


class LEAssetBrowserPanel(wx.Panel):

    THUMB_STEPS = [56, 72, 96, 120]

    def __init__(self, parent, editor):
        wx.Panel.__init__(self, parent, -1)
        self.editor = editor
        settings = load_lot_editor()
        self.scope = str(settings.get('AssetScope', 'lot'))
        if self.scope not in ('lot', 'library', 'favorites'):
            self.scope = 'lot'
        self.kind_filter = str(settings.get('AssetFilter', 'all'))
        if self.kind_filter not in ('all', 'textures', 'base_textures', 'overlay_textures', 'props', 'flora', 'families'):
            self.kind_filter = 'all'
        self.favorites = set(str(k) for k in (settings.get('Favorites') or []))
        self.all_items = []
        self.thumbnail_provider = LEAssetThumbnailProvider()
        self.thumbnail_provider.SetThumbSize(int(settings.get('ThumbSize', 72)))
        root = wx.BoxSizer(wx.VERTICAL)
        header = wx.BoxSizer(wx.HORIZONTAL)
        title = wx.StaticText(self, -1, LEXAssetBrowserAssets)
        title.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        header.Add(title, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.count_label = wx.StaticText(self, -1, '')
        header.Add(self.count_label, 0, wx.ALIGN_CENTER_VERTICAL)
        root.Add(header, 0, wx.EXPAND | wx.ALL, 10)
        self.search = wx.SearchCtrl(self, -1, style=wx.TE_PROCESS_ENTER)
        self.search.ShowSearchButton(True)
        self.search.ShowCancelButton(True)
        root.Add(self.search, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        scopes = wx.BoxSizer(wx.HORIZONTAL)
        self.scope_buttons = {}
        for scope, label in [
            ('lot', LEXAssetBrowserCurrentLot),
            ('library', LEXAssetBrowserLibrary),
            ('favorites', LEXAssetBrowserFavorites),
        ]:
            btn = wx.ToggleButton(self, -1, label)
            btn.Bind(wx.EVT_TOGGLEBUTTON, lambda evt, value=scope: self.SetScope(value))
            self.scope_buttons[scope] = btn
            scopes.Add(btn, 1, wx.RIGHT, 4)
        root.Add(scopes, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        filters = wx.BoxSizer(wx.HORIZONTAL)
        self.filter_choice = wx.Choice(self, -1, choices=[
            LEXAssetBrowserAll,
            LEXAssetBrowserTextures,
            LETreeBaseTextures,
            LETreeOverlayTextures,
            LEXAssetBrowserProps,
            LETreeFlora,
            LEXAssetBrowserFamilies,
        ])
        self.filter_choice.SetSelection(['all', 'textures', 'base_textures', 'overlay_textures', 'props', 'flora', 'families'].index(self.kind_filter))
        filters.Add(self.filter_choice, 1, wx.EXPAND)
        self.presentation = wx.ToggleButton(self, -1, LEXAssetBrowserCompact)
        filters.Add(self.presentation, 0, wx.LEFT, 6)
        thumb_size = int(settings.get('ThumbSize', 72))
        thumb_idx = min(range(len(self.THUMB_STEPS)),
                        key=lambda i: abs(self.THUMB_STEPS[i] - thumb_size))
        self.thumb_slider = wx.Slider(self, -1, thumb_idx, 0, len(self.THUMB_STEPS) - 1,
                                      size=(90, -1))
        self.thumb_slider.SetToolTip(LEXAssetBrowserThumbSize)
        filters.Add(self.thumb_slider, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 6)
        root.Add(filters, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.grid = LEAssetGrid(self, self.thumbnail_provider, self._on_grid_select,
                                self._on_context, self._on_activate)
        self.list = LEAssetList(self, self._on_grid_select, self._on_context, self._on_activate)
        root.Add(self.grid, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        root.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.list.Hide()
        self.SetSizer(root)
        self.search.Bind(wx.EVT_TEXT, self.OnSearch)
        self.filter_choice.Bind(wx.EVT_CHOICE, self.OnFilter)
        self.presentation.Bind(wx.EVT_TOGGLEBUTTON, self.OnPresentation)
        self.thumb_slider.Bind(wx.EVT_SLIDER, self.OnThumbSize)
        self._debounce = None
        self.search.SetValue(str(settings.get('AssetSearch', '')))
        compact = bool(settings.get('AssetCompact', False))
        self.presentation.SetValue(compact)
        self.OnPresentation(None)
        self.SetScope(self.scope)

    def GetState(self):
        return {
            'AssetScope': self.scope,
            'AssetFilter': self.kind_filter,
            'AssetSearch': self.search.GetValue(),
            'AssetCompact': bool(self.presentation.GetValue()),
            'Favorites': sorted(self.favorites),
            'ThumbSize': self.grid.THUMB,
        }

    def OnThumbSize(self, event):
        self.grid.SetThumbSize(self.THUMB_STEPS[self.thumb_slider.GetValue()])

    def _on_context(self, item):
        is_fav = item.fav_key in self.favorites
        menu = wx.Menu()
        entry = menu.Append(-1, LEXAssetRemoveFavorite if is_fav else LEXAssetAddFavorite)

        def toggle(evt):
            if is_fav:
                self.favorites.discard(item.fav_key)
            else:
                self.favorites.add(item.fav_key)
            if hasattr(self.editor, 'SaveEditorState'):
                self.editor.SaveEditorState()
            self.RefreshAssets()

        menu.Bind(wx.EVT_MENU, toggle, entry)
        self.PopupMenu(menu)
        menu.Destroy()

    def RefreshAssets(self):
        self.all_items = self._build_items()
        self.ApplyFilters()

    def SetScope(self, scope):
        self.scope = scope
        for key, btn in self.scope_buttons.items():
            btn.SetValue(key == scope)
        self.RefreshAssets()

    def OnSearch(self, event):
        if self._debounce:
            self._debounce.Stop()
        self._debounce = wx.CallLater(120, self.ApplyFilters)

    def OnFilter(self, event):
        labels = ['all', 'textures', 'base_textures', 'overlay_textures', 'props', 'flora', 'families']
        self.kind_filter = labels[self.filter_choice.GetSelection()]
        self.ApplyFilters()

    def OnPresentation(self, event):
        compact = self.presentation.GetValue()
        self.presentation.SetLabel(LEXAssetBrowserGrid if compact else LEXAssetBrowserCompact)
        self.grid.Show(not compact)
        self.list.Show(compact)
        self.Layout()

    def _on_grid_select(self, item):
        if hasattr(self.editor, 'UpdateAssetInspector'):
            self.editor.UpdateAssetInspector(item)

    def _on_activate(self, item):
        """Double-click / Enter: drop the asset at the centre of the lot."""
        if hasattr(self.editor, 'PlaceAssetCentered'):
            self.editor.PlaceAssetCentered(item.proxy)

    def _texture_item(self, entry, overlay):
        iid = entry.tgi[2] - 3
        kind = 'overlay texture' if overlay else 'base texture'
        badge = LEXAssetBrowserOverlayBadge if overlay else LEXAssetBrowserBaseBadge
        return LEAssetItem(kind, hex2str(iid)[2:], os.path.split(entry.fileName)[1], OverlayProxy(entry) if overlay else BaseProxy(entry), entry, badge)

    def _prop_item(self, desc, flora=False):
        name = desc.exemplar.GetProp(32)
        label = name[0] if name else hex2str(desc.exemplar.entry.tgi[2])[2:]
        kind = 'flora' if flora else 'prop'
        badge = LEXAssetBrowserFloraBadge if flora else LEXAssetBrowserPropBadge
        return LEAssetItem(kind, label, hex2str(desc.exemplar.entry.tgi[2])[2:], PropProxy(desc), desc, badge)

    def _family_member_names(self, cat_id):
        names = []
        try:
            for desc in VirtualDat.this.categories[cat_id].descriptors:
                if desc.exemplar.entry.tgi[0] != 1697917002:
                    continue
                if desc.exemplar.GetProp(16)[0] not in (30, 15):
                    continue
                name = desc.exemplar.GetProp(32)
                if name:
                    names.append(str(name[0]))
        except Exception:
            pass
        return names

    def _family_item(self, cat_id):
        try:
            category = VirtualDat.this.categories[cat_id]
            label = category.Name
        except Exception:
            label = hex2str(cat_id)
        members = ' '.join(self._family_member_names(cat_id))
        return LEAssetItem('family', label, hex2str(cat_id)[2:], FamilyProxy(cat_id), cat_id,
                           LEXAssetBrowserFamilyBadge, members)

    def _build_items(self):
        items = []
        if self.scope == 'lot':
            for iid in getattr(self.editor, 'lotBaseTextures', []):
                entry = VirtualDat.this.getEntry(2058686020, 159781726, iid)
                if entry is not None:
                    items.append(self._texture_item(entry, False))
            for iid in getattr(self.editor, 'lotOverTextures', []):
                entry = VirtualDat.this.getEntry(2058686020, 159781726, iid)
                if entry is not None:
                    items.append(self._texture_item(entry, True))
            for desc in getattr(self.editor, 'lotPropDescs', []):
                items.append(self._prop_item(desc, False))
            for desc in getattr(self.editor, 'lotFloraDescs', []):
                items.append(self._prop_item(desc, True))
            for cat_id in getattr(self.editor, 'lotFamiliesPropID', []):
                items.append(self._family_item(cat_id))
            return items
        for entry in getattr(VirtualDat.this, 'baseTexEntries', []):
            items.append(self._texture_item(entry, False))
        for entry in getattr(VirtualDat.this, 'overTexEntries', []):
            items.append(self._texture_item(entry, True))
        prop_category = VirtualDat.this.categories.get(210746660)
        if prop_category is not None:
            prop_descs = prop_category.descriptors
        else:
            prop_descs = []
        for desc in prop_descs:
            try:
                if desc.exemplar.entry.tgi[0] == 1697917002 and desc.exemplar.GetProp(16)[0] in (30, 15):
                    items.append(self._prop_item(desc, False))
            except Exception:
                pass
        flora_category = VirtualDat.this.categories.get(1830116951)
        if flora_category is not None:
            flora_descs = flora_category.descriptors
        else:
            flora_descs = []
        for desc in flora_descs:
            try:
                if desc.exemplar.entry.tgi[0] == 1697917002 and desc.exemplar.GetProp(16)[0] in (30, 15):
                    items.append(self._prop_item(desc, True))
            except Exception:
                pass
        for root_id in (4089086497, 4089087265):
            category = VirtualDat.this.categories.get(root_id)
            if category is None:
                continue
            for sub in category.childs:
                if self._is_prop_family(sub.descriptors):
                    items.append(self._family_item(sub.ID))
        if self.scope == 'favorites':
            return [it for it in items if it.fav_key in self.favorites]
        return items

    def _is_prop_family(self, descriptors):
        for desc in descriptors:
            try:
                if desc.exemplar.entry.tgi[0] != 1697917002:
                    continue
                if desc.exemplar.GetProp(16)[0] in (30, 15):
                    return True
            except Exception:
                pass
        return False

    def ApplyFilters(self):
        text = self.search.GetValue().strip().lower()
        filtered = []
        for item in self.all_items:
            if self.kind_filter == 'textures' and item.kind not in ('base texture', 'overlay texture'):
                continue
            if self.kind_filter == 'base_textures' and item.kind != 'base texture':
                continue
            if self.kind_filter == 'overlay_textures' and item.kind != 'overlay texture':
                continue
            if self.kind_filter == 'props' and item.kind != 'prop':
                continue
            if self.kind_filter == 'flora' and item.kind != 'flora':
                continue
            if self.kind_filter == 'families' and item.kind != 'family':
                continue
            if text and text not in item.search_text:
                continue
            filtered.append(item)
        self.count_label.SetLabel('%d' % len(filtered))
        self.grid.SetItems(filtered)
        self.list.SetItems(filtered)


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
                if desc.exemplar.entry.tgi[0] != 1697917002:
                    continue
                if desc.exemplar.GetProp(16)[0] != 30 and desc.exemplar.GetProp(16)[0] != 15:
                    continue
                return True

            return False

        listSub = self.virtualDAT.categories[4089086497].childs[:]
        listSub.sort(key=lambda n: n.ID)
        for sub in listSub:
            if IsItAPropFamilies(sub.descriptors):
                idx = self.AppendItem(self.familiesPropsItem, sub.Name)
                self.SetPyData(idx, sub.ID)

        listSub = self.virtualDAT.categories[4089087265].childs[:]
        listSub.sort(key=lambda n: n.ID)
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
        groups_file = user_data_path('groups.ini')
        if groups_file.exists():
            with open(groups_file, 'r', encoding='utf-8', errors='replace') as group_file:
                exec(compile(group_file.read(), 'groups.ini', 'exec'), globals(), locals())
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
        if self.IsItPersonalGroup(item) is not None:
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
            VirtualDat.this.categories[210746660].descriptors.sort(key=lambda n: n.exemplar.entry.tgi)
            self.propList.Reset(VirtualDat.this.ilStandardModels, VirtualDat.this.categories[210746660].descriptors, FillListForProps, DisplayNameForPropsTGI)
        elif item == tree.singlePropsItemName:
            VirtualDat.this.categories[210746660].descriptors.sort(key=lambda n: n.name.upper())
            self.propList.Reset(VirtualDat.this.ilStandardModels, VirtualDat.this.categories[210746660].descriptors, FillListForProps, DisplayNameForPropsName)
        elif item == tree.floraItem:
            VirtualDat.this.categories[1830116951].descriptors.sort(key=lambda n: n.name.upper())
            self.propList.Reset(VirtualDat.this.ilStandardModels, VirtualDat.this.categories[1830116951].descriptors, FillListForProps, DisplayNameForPropsName)
        elif item == tree.lotBaseTexturesItem:
            lst = [ VirtualDat.this.getEntry(2058686020, 159781726, IID) for IID in self.parent.lotBaseTextures ]
            lst.sort(key=lambda n: n.tgi)
            self.propList.Reset(VirtualDat.this.ilBase, lst, FillListForTex, DisplayNameForTex)
        elif item == tree.lotOverlayTexturesItem:
            lst = [ VirtualDat.this.getEntry(2058686020, 159781726, IID) for IID in self.parent.lotOverTextures ]
            lst.sort(key=lambda n: n.tgi)
            self.propList.Reset(VirtualDat.this.ilOver, lst, FillListForTex, DisplayNameForTex)
        elif item == tree.lotPropsItem:
            self.parent.lotPropDescs.sort(key=lambda n: n.name.upper())
            self.propList.Reset(VirtualDat.this.ilStandardModels, self.parent.lotPropDescs, FillListForPropsAsSingle, DisplayNameForPropsName)
        elif item == tree.lotFloraItem:
            self.parent.lotFloraDescs.sort(key=lambda n: n.name.upper())
            self.propList.Reset(VirtualDat.this.ilStandardModels, self.parent.lotFloraDescs, FillListForPropsAsSingle, DisplayNameForPropsName)
        elif item == tree.lotIcon:
            IID = self.parent.exemplar.entry.tgi[2]
            entry = VirtualDat.this.getEntry(2238569388, 1782082854, IID)
            self.propList.Reset(VirtualDat.this.ilIcon, [entry], FillListForIcon, DisplayNameForIcon)
        else:
            catID = tree.GetPyData(item)
            if catID is not None:
                if catID.__class__ == GroupProxy:
                    catID.Display(self.propList)
                else:
                    VirtualDat.this.categories[catID].descriptors.sort(key=lambda n: n.name.upper())
                    self.propList.Reset(VirtualDat.this.ilStandardModels, VirtualDat.this.categories[catID].descriptors, FillListForPropsAsFamily, DisplayNameForPropsName, catID)
            else:
                self.propList.Reset(VirtualDat.this.ilBase, None, FillListForNothing, DisplayNameForTex)
        return

    def Save(self):
        fout = open(ensure_user_data_dir() / 'groups.ini', 'wt')
        x, y = self.GetPosition()
        w, h = self.GetSize()
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

