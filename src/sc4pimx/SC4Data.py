"""SC4 data structures and virtual DAT file management.

This module provides classes for managing SC4 building descriptions, textures,
lots, and virtual DAT file collections.
"""
import codecs
import functools
import logging
import os
import threading
import xml.dom.minidom
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageDraw, ImageFont

from . import FSHConverter
from .paths import asset_path, image_db_path
from .S3DReader import *
from .SC4DataFunctions import ToTile
from .SC4DatTools import *
from .translation import *
from .util import basic_cmp

logger = logging.getLogger(__name__)


def _text_size(font, text):
    """Return the (width, height) of rendered text.

    Replaces ``ImageFont.getsize()``, which was removed in Pillow 10.
    """
    left, top, right, bottom = font.getbbox(text)
    return (right - left, bottom - top)


class Family:

    def __init__(self, familyID, virtualDAT, tree):
        self.familyID = familyID
        self.name = '0x%08X' % familyID
        self.bNamed = False
        potentialCohorts = virtualDAT.getEntries(87304289, 0, familyID + 268435456, gMask=0)
        if potentialCohorts != []:
            for cohort in potentialCohorts:
                try:
                    if cohort.exemplar.entry == cohort:
                        pass
                except Exception:
                    cohort.read_file(None, True, True)
                    exemplar = SC4Exemplar(cohort)
                    cohort.exemplar = exemplar
                    cohort.rawContent = None
                    cohort.content = None

                name = cohort.exemplar.GetProp(32)
                if name is not None:
                    self.name = name[0] + ' [%s]' % self.name
                    self.bNamed = True
                break

        self.members = []
        self.item = None
        self.tree = tree
        return

    def addMember(self, propDesc):
        self.members.append(propDesc)
        item = self.tree.AppendItem(self.item, propDesc.exemplar.GetProp(32)[0])
        self.tree.SetPyData(item, propDesc)


class FloraDesc():

    def __init__(self, entry):
        self.exemplar = entry.exemplar
        try:
            self.name = entry.exemplar.GetProp(32)[0]
        except Exception:
            self.name = 'Unnamed 0x%08X-0x%08X-0x%08X' % (entry.tgi[0], entry.tgi[1], entry.tgi[2])

        self.fileName = entry.fileName
        self.rtk = None
        self.rtk = self.exemplar.GetProp(662775840)
        if self.rtk is not None:
            self.rtk = tuple(self.rtk)
        else:
            self.rtk = self.exemplar.GetProp(662775841)
            if self.rtk is not None:
                self.rtk = tuple(self.rtk)
            else:
                self.rtk = self.exemplar.GetProp(662775844)
                if self.rtk is not None:
                    self.rtk = tuple(self.rtk[5:8])
                else:
                    self.rtk = self.exemplar.GetProp(662775843)
                    if self.rtk is not None:
                        self.rtk = tuple(self.rtk[0:2] + [self.rtk[-1]])
        return


class ATCProxy():

    def __init__(self, entry, atc):
        if entry is None:
            self.fileName = invisibleATC
            self.name = unknonwMsg
        else:
            self.name = '0x%08X-0x%08X' % (entry.tgi[1], entry.tgi[2])
            self.fileName = entry.fileName
        self.sc4Model = atc
        return


class FoundationDesc():

    def __init__(self, entry):
        self.exemplar = entry.exemplar
        try:
            self.name = entry.exemplar.GetProp(32)[0]
        except Exception:
            self.name = 'Unnamed 0x%08X-0x%08X-0x%08X' % (entry.tgi[0], entry.tgi[1], entry.tgi[2])

        self.fileName = entry.fileName
        self.rtk = None
        self.rtk = self.exemplar.GetProp(662775840)
        if self.rtk is not None:
            self.rtk = tuple(self.rtk)
        else:
            self.rtk = self.exemplar.GetProp(662775841)
            if self.rtk is not None:
                self.rtk = tuple(self.rtk)
            else:
                self.rtk = self.exemplar.GetProp(662775844)
                if self.rtk is not None:
                    self.rtk = tuple(self.rtk[5:8])
                else:
                    self.rtk = self.exemplar.GetProp(662775843)
                    if self.rtk is not None:
                        self.rtk = tuple(self.rtk[0:2] + [self.rtk[-1]])
        return


def GetCategories(root, desc):
    if CheckAgainstFilter(root, desc.exemplar):
        b = False
        if len(root.childs) == 0:
            if len(root.setProperties) + len(root.factorProperties) + len(root.pairedFactorProperties) + len(
                    root.programProperties) + len(root.evalProperties) + len(root.code) > 0:
                b = True
                if desc not in root.descriptors:
                    root.descriptors.append(desc)
                return (True, [(root.Name, root.ID)])
        else:
            names = []
            for child in root.childs:
                b1, namesunder = GetCategories(child, desc)
                if b1:
                    names += namesunder
                    if desc not in root.descriptors:
                        root.descriptors.append(desc)
                b = b or b1

            return (
                b, names)
    return (
        False, [])


class BuildingDesc():

    def __init__(self, entry):
        self.exemplar = entry.exemplar
        try:
            self.name = entry.exemplar.GetProp(32)[0]
        except Exception:
            self.name = 'Unnamed 0x%08X-0x%08X-0x%08X' % (entry.tgi[0], entry.tgi[1], entry.tgi[2])

        self.fileName = entry.fileName
        self.rtk = None
        self.rtk = self.exemplar.GetProp(662775840)
        if self.rtk is not None:
            self.rtk = tuple(self.rtk)
        else:
            self.rtk = self.exemplar.GetProp(662775841)
            if self.rtk is not None:
                self.rtk = tuple(self.rtk)
            else:
                self.rtk = self.exemplar.GetProp(662775844)
                if self.rtk is not None:
                    self.rtk = tuple(self.rtk[5:8])
                else:
                    self.rtk = self.exemplar.GetProp(662775843)
                    if self.rtk is not None:
                        self.rtk = tuple(self.rtk[0:2] + [self.rtk[-1]])
        return


def Categorize(root, desc):
    if CheckAgainstFilter(root, desc.exemplar):
        b = False
        if len(root.childs) == 0:
            b = True
            root.descriptors.append(desc)
            try:
                desc.cats.append(root.ID)
            except Exception:
                desc.cats = [
                    root.ID]

        else:
            for child in root.childs:
                b1 = Categorize(child, desc)
                b = b or b1
                if b1:
                    break

        return b
    return False


def CheckAgainstFilter(cat, exemplar):
    needed = cat.filters.needed
    for f in needed:
        id = f[0]
        value = f[1]
        exemplarValue = exemplar.GetProp(id)
        if value is None and exemplarValue is None:
            return False
        if value is not None:
            if exemplarValue is None:
                return False
            if value not in exemplarValue:
                return False

    notallowed = cat.filters.notallowed
    for f in notallowed:
        id = f[0]
        value = f[1]
        exemplarValue = exemplar.GetProp(id)
        if value is None and exemplarValue is not None:
            return False
        if value is not None:
            if exemplarValue is None:
                pass
            elif value in exemplarValue:
                return False

    return True


def Clamp(prop, v):
    if prop.minVal and v < prop.minVal:
        v = prop.minVal
    if prop.maxVal and v > prop.maxVal:
        v = prop.maxVal
    return v


def ConvertAPropToReadable(prop, propFormat):
    resultat = u''
    if prop.id >= 2297284864 and prop.id <= 2297286143:
        mapFirstVal = [
            'Building', 'Prop', 'Texture', 'Fence', 'Flora', 'Water', 'Land', 'Network']
        mapSecondVal = ['all', 'med only', 'high only']
        mapThirdVal = ['South', 'West', 'North', 'East']
        mapIdx = ['Type', 'LOD', 'Orientation', 'X Pos', 'Z Pos', 'Y Pos', 'xmin', 'ymin', 'xmax', 'ymax', 'Usage',
                  'ObjectID', 'RefID', 'RUL', 'RUL Flags', 'SC4Path']
        resultat += '%s: ' % mapIdx[0]
        resultat += mapFirstVal[prop.values[0]]
        resultat += ' - %s: ' % mapIdx[1]
        resultat += mapSecondVal[prop.values[1] // 16]
        resultat += ' - %s: ' % mapIdx[2]
        try:
            resultat += mapThirdVal[prop.values[2]]
        except Exception:
            resultat += hex2str(prop.values[2])

        for i, v in enumerate(prop.values):
            if i in range(3, 6):
                fvalue = ToTile(v)
                resultat += ' - %s: ' % mapIdx[i]
                resultat += '%d / %.3f' % (int(fvalue), (fvalue - int(fvalue)) * 16)
            if i in range(6, 10):
                fvalue = ToTile(v)
                resultat += ' - %s: ' % mapIdx[i]
                resultat += '%.3f' % (fvalue * 16)

        for i, v in enumerate(prop.values):
            if i >= 10:
                try:
                    resultat += ' - %s: ' % mapIdx[i]
                except Exception:
                    resultat += ' - unknown: '

                resultat += hex2str(v)

        return resultat
    for i, v in enumerate(prop.values):
        if resultat != u'':
            resultat += ' '
        if 'COL:%d' % i in propFormat.Options:
            resultat += codecs.encode(propFormat.Options['COL:%d' % i], 'unicode_escape').decode('ascii') + ':'
        if v in propFormat.Options:
            resultat += codecs.encode(propFormat.Options[v], 'unicode_escape').decode('ascii')
        elif prop.typeValue == 2816:
            if v == 0:
                resultat += 'False'
            else:
                resultat += 'True'
        elif prop.typeValue == 3072:
            if isinstance(v, bytes):
                resultat += v.decode('unicode_escape')
            else:
                resultat += codecs.decode(v, 'unicode_escape')
        elif prop.typeValue == 2304:
            resultat += format_float_value(v)
        elif prop.typeValue == 2048 and propFormat.ShowAsHex:
            resultat += '0x%016X' % v
        elif propFormat.ShowAsHex:
            resultat += '0x%08X' % v
        else:
            resultat += '%d' % v

    return resultat


def CreateAPropFromString(prop, value):
    if isinstance(value, bytes):
        value = value.decode('utf-8', errors='replace')
    else:
        value = str(value)
    count = prop.Count
    if count == 1:
        count = 0
    elif prop.Type != 'String':
        count = len(value.split(','))
    if prop.Type == 'Bool':
        if value == '0':
            value = 'False'
        if value == '1':
            value = 'True'
    if prop.Type == 'String':
        count = 1
        buffer = '0x%08x:{"%s"}=%s:%d:("%s")' % (prop.ID, prop.Name, prop.Type, count, value)
    else:
        buffer = '0x%08x:{"%s"}=%s:%d:(%s)' % (prop.ID, prop.Name, prop.Type, count, value)
    return buffer


def _env_true(name):
    return os.environ.get(name, '').strip().lower() in ('1', 'true', 'yes', 'on')


def EnsureStandardModelImage(virtual_dat, tgi):
    """Return the ilStandardModels index for a model's thumbnail.

    The thumbnail JPG is decoded and added to the image list on first use
    (lazy loading), so the LE picker only pays for the models it actually
    shows. The result -- including index 0 (the NoPreview placeholder) when
    the thumbnail is missing or unreadable -- is cached in s3dEntries, so each
    model is decoded at most once per session.
    """
    idx = virtual_dat.s3dEntries.get(tgi)
    if idx is not None:
        return idx
    idx = 0
    file_name = str(image_db_path('%s-%s.jpg' % (hex2str(tgi[1]), hex2str(tgi[2]))))
    if os.path.exists(file_name):
        image = wx.Bitmap(file_name, wx.BITMAP_TYPE_JPEG)
        if image.IsOk():
            added = virtual_dat.ilStandardModels.Add(image)
            if added != -1:
                idx = added
    virtual_dat.s3dEntries[tgi] = idx
    return idx


class ImageListLoaderProps(object):

    def __init__(self, virtualDAT):
        self.virtualDAT = virtualDAT
        self.keepGoing = self.running = False

    def Start(self):
        self.keepGoing = self.running = True
        if _env_true('SC4PIM_SKIP_PROP_IMAGES'):
            self.running = False
            return
        wx.CallAfter(self.Run)

    def Stop(self):
        self.keepGoing = False

    def IsRunning(self):
        return self.running

    def Reset(self):
        self.Stop()
        while self.IsRunning():
            time.sleep(0.01)

        self.Start()

    def LoadJPGToBitmap(self, fileName):
        pil = Image.open(fileName)
        image = wx.Image(pil.size[0], pil.size[1])
        image.SetData(pil.convert('RGB').tobytes())
        return image.ConvertToBitmap()

    def _AddStandardModelImage(self, file_name, tgi=None):
        if not os.path.exists(file_name):
            return
        image = wx.Bitmap(file_name, wx.BITMAP_TYPE_JPEG)
        if not image.IsOk():
            return
        idx = self.virtualDAT.ilStandardModels.Add(image)
        if idx == -1:
            logger.error('PropLoader: error adding JPG file for %s (%dx%d), %d already loaded',
                         file_name, image.GetWidth(), image.GetHeight(),
                         self.virtualDAT.ilStandardModels.GetImageCount())
        elif tgi is not None:
            self.virtualDAT.s3dEntries[tgi] = idx

    def Run(self, dlg=None):
        if _env_true('SC4PIM_SKIP_PROP_IMAGES'):
            self.running = False
            return
        # Model thumbnails used to be decoded up front -- thousands of JPG
        # decodes + wx.ImageList.Add calls that froze the UI for seconds right
        # after load. They are now loaded lazily by EnsureStandardModelImage()
        # the first time each model is shown in an LE picker. Here we only
        # build the pre-sized image list (so later Add() calls stay O(1) --
        # an unsized wx.ImageList regrows its master bitmap on every Add) and
        # register the NoPreview placeholder at index 0.
        self.virtualDAT.ilStandardModels = wx.ImageList(
            64, 64, True, len(self.virtualDAT.standardModels) + 2)
        self.virtualDAT.s3dEntries = {}
        self._AddStandardModelImage(str(asset_path('other', 'NoPreview.jpg')), None)
        self.running = False


class ImageListLoaderTexture(object):

    def __init__(self, virtualDAT):
        self.virtualDAT = virtualDAT
        self.keepGoing = self.running = False
        self.font = ImageFont.truetype('arial.ttf', 12)
        self.offset = _text_size(self.font, 'R')
        # PIL FreeType font objects are not safe to share across threads, so
        # each worker thread gets its own via _thread_font().
        self._tls = threading.local()

    def _thread_font(self):
        font = getattr(self._tls, 'font', None)
        if font is None:
            font = ImageFont.truetype('arial.ttf', 12)
            self._tls.font = font
        return font

    def Start(self):
        self.keepGoing = self.running = True
        if _env_true('SC4PIM_SKIP_TEXTURE_IMAGES'):
            self.running = False
            return
        # wx objects must be created on the GUI thread, so pre-size the image
        # lists here; the FSH decoding then runs on a background worker pool.
        allTex = self.virtualDAT.allTextures
        self.virtualDAT.ilBase = wx.ImageList(64, 64, True, len(allTex) + 2)
        self.virtualDAT.ilOver = wx.ImageList(64, 64, True, len(allTex) + 2)
        threading.Thread(target=self.Run, name='sc4-texture-loader',
                         daemon=True).start()

    def Stop(self):
        self.keepGoing = False

    def IsRunning(self):
        return self.running

    def Reset(self):
        self.Stop()
        while self.IsRunning():
            time.sleep(0.01)

        self.Start()

    @staticmethod
    def _CmpTGI(tgi1, tgi2):
        if tgi1[0] == tgi2[0]:
            if tgi1[1] == tgi2[1]:
                return basic_cmp(tgi1[2], tgi2[2])
            else:
                return basic_cmp(tgi1[1], tgi2[1])
        else:
            return basic_cmp(tgi1[0], tgi2[0])

    def _AddTextureImage(self, rgb_bytes, size, trueAlpha, texEntry):
        expected = size[0] * size[1] * 3
        if len(rgb_bytes) != expected:
            logger.error('TextureLoader: invalid RGB buffer size for %s (%d != %d)',
                         texEntry.fileName, len(rgb_bytes), expected)
            return
        image = wx.Image(size[0], size[1])
        image.SetData(rgb_bytes)
        if trueAlpha:
            idx = self.virtualDAT.ilOver.Add(image.ConvertToBitmap())
            if idx == -1:
                logger.error('OverlayLoader: error adding fsh %s-%s-%s from %s',
                             hex2str(texEntry.tgi[0]), hex2str(texEntry.tgi[1]),
                             hex2str(texEntry.tgi[2]), texEntry.fileName)
            self.virtualDAT.overTexEntriesDict[texEntry] = idx
            self.virtualDAT.overTexEntries.append(texEntry)
        else:
            idx = self.virtualDAT.ilBase.Add(image.ConvertToBitmap())
            if idx == -1:
                logger.error('BaseLoader: error adding fsh %s-%s-%s from %s',
                             hex2str(texEntry.tgi[0]), hex2str(texEntry.tgi[1]),
                             hex2str(texEntry.tgi[2]), texEntry.fileName)
            self.virtualDAT.baseTexEntriesDict[texEntry] = idx
            self.virtualDAT.baseTexEntries.append(texEntry)

    def _FinalizeTextureLists(self):
        self.virtualDAT.baseTexEntries.sort(key=functools.cmp_to_key(lambda n1, n2: self._CmpTGI(n1.tgi, n2.tgi)))
        self.virtualDAT.overTexEntries.sort(key=functools.cmp_to_key(lambda n1, n2: self._CmpTGI(n1.tgi, n2.tgi)))

    def Run(self):
        if _env_true('SC4PIM_SKIP_TEXTURE_IMAGES'):
            self.running = False
            return
        allTex = list(self.virtualDAT.allTextures)
        workers = max(2, min(8, (os.cpu_count() or 4)))
        logger.debug('Decoding %d textures with %d worker threads',
                     len(allTex), workers)
        try:
            # Decode FSH textures in parallel; only the wx.ImageList.Add
            # (in _AddTextureImage) is marshalled back to the GUI thread.
            # Each entry stores its own returned index and the lists are
            # sorted afterwards, so out-of-order completion is harmless.
            with ThreadPoolExecutor(max_workers=workers,
                                    thread_name_prefix='sc4-tex') as pool:
                for result in pool.map(self._decode_texture, allTex):
                    if not self.keepGoing:
                        break
                    if result is not None:
                        rgb_bytes, trueAlpha, texEntry = result
                        wx.CallAfter(self._AddTextureImage, rgb_bytes,
                                     (64, 64), trueAlpha, texEntry)
        except Exception:
            logger.exception('Texture loader thread failed')
        wx.CallAfter(self._FinalizeTextureLists)
        self.running = False

    def _decode_texture(self, texEntry):
        """Decode one FSH texture to a 64x64 RGB byte buffer.

        Runs on a worker thread and performs no wx calls. Returns
        ``(rgb_bytes, trueAlpha, texEntry)`` or ``None`` on failure.
        """
        if not self.keepGoing:
            return None
        try:
            texEntry.read_file(None, True, True)
            nbrLayers, trueAlpha, img, alpha, size = FSHConverter.decodeFSH(
                texEntry.content
            )
        except Exception as exc:
            logger.warning('TextureLoader: failed to decode FSH from %s: %s',
                           texEntry.fileName, exc)
            texEntry.content = None
            texEntry.rawContent = None
            return None
        texEntry.content = None
        texEntry.rawContent = None
        try:
            pilz = Image.frombytes('RGB', size, img)
        except Exception as exc:
            logger.warning('TextureLoader: failed to load RGB for %s: %s',
                           texEntry.fileName, exc)
            return None
        if trueAlpha:
            try:
                blank = Image.new('RGB', size, 16777215)
                alpha = Image.frombytes('L', size, alpha)
                pilz = Image.composite(pilz, blank, alpha)
            except Exception as exc:
                logger.warning('TextureLoader: failed alpha composite for %s: %s',
                               texEntry.fileName, exc)
                return None
        pilz = pilz.resize((64, 64), Image.BICUBIC)
        font = self._thread_font()
        if nbrLayers > 1:
            try:
                draw = ImageDraw.Draw(pilz)
                draw.ellipse((64 - self.offset[0] - 8, 64 - self.offset[1] - 2,
                              64 - self.offset[0] + 6, 64 - self.offset[1] + 12),
                             fill=(156, 181, 140))
                draw.text((64 - self.offset[0] - 5, 64 - self.offset[1] - 2), 'R',
                          font=font, fill=(0, 0, 0))
            except Exception:
                logger.exception('Error generating texture overlay for %s',
                                 texEntry.fileName)
                return None

        IID = texEntry.tgi[2] & 61440
        if IID == 0 or IID == 4096 or IID == 8192 or IID == 12288:
            signs = {0: '0', 4096: '$', 8192: '$$', 12288: '$$$'}
            length = _text_size(font, signs[IID])
            draw = ImageDraw.Draw(pilz)
            draw.ellipse((2, 64 - self.offset[1] - 2, length[0] + 7,
                          64 - self.offset[1] + 12), fill=(156, 181, 140))
            draw.text((5, 64 - self.offset[1] - 2), signs[IID], font=font,
                      fill=(0, 0, 0))
        return pilz.convert('RGB').tobytes(), trueAlpha, texEntry
        return


def IsAChild(cat, id):
    if cat is None:
        return False
    if cat.ID == id:
        return True
    return IsAChild(cat.parent, id)


def IsFromCategoryDesc(cat, desc):
    return desc in cat.descriptors


def IsFromCategory(cat, exemplar):
    if cat is None:
        return True
    return CheckAgainstFilter(cat, exemplar) and IsFromCategory(cat.parent, exemplar)


class LotDesc():

    def __init__(self, entry):
        self.exemplar = entry.exemplar
        try:
            self.name = entry.exemplar.GetProp(32)[0]
        except Exception:
            self.name = 'Unnamed 0x%08X-0x%08X-0x%08X' % (entry.tgi[0], entry.tgi[1], entry.tgi[2])

        self.fileName = entry.fileName
        self.rtk = None
        return


def PrintCat(cat, spaces=0):
    logger.debug('%s%s', ' ' * spaces, cat.Name)
    for child in cat.childs:
        PrintCat(child, spaces + 1)


class PropDesc(object):

    def __init__(self, entry):
        self.exemplar = entry.exemplar
        try:
            self.name = entry.exemplar.GetProp(32)[0]
        except Exception:
            self.name = 'Unnamed 0x%08X-0x%08X-0x%08X' % (entry.tgi[0], entry.tgi[1], entry.tgi[2])

        self.fileName = entry.fileName
        self.rtk = None
        self.rtk = self.exemplar.GetProp(662775840)
        if self.rtk is not None:
            self.rtk = tuple(self.rtk)
        else:
            self.rtk = self.exemplar.GetProp(662775841)
            if self.rtk is not None:
                self.rtk = tuple(self.rtk)
            else:
                self.rtk = self.exemplar.GetProp(662775844)
                if self.rtk is not None:
                    self.rtk = tuple(self.rtk[5:8])
                else:
                    self.rtk = self.exemplar.GetProp(662775843)
                    if self.rtk is not None:
                        self.rtk = tuple(self.rtk[0:2] + [self.rtk[-1]])
        return


class ResourceKey():

    def __init__(self, TID, GID, IID, virtualDAT):
        self.name = '0x%08X-0x%08X-0x%08X' % (TID, GID, IID)
        self.GID = GID
        self.IID = IID
        self.virtualDAT = virtualDAT


class ResourceViewer():

    def __init__(self, rkType, rktData, virtualDAT, mainFrame, tgi=None, name=None):
        rktData = tuple(rktData)
        self.Name = name
        self.tgi = tgi
        self.mainFrame = mainFrame
        self.rkType = rkType
        self.rktData = rktData
        self.viewingData = []
        if self.rkType == 662775840:
            if rktData[0] == 698733036:
                if rktData in virtualDAT.atcsDict:
                    self.viewingData.append(virtualDAT.atcsDict[rktData])
            elif rktData in virtualDAT.otherModelsDict:
                self.viewingData.append(virtualDAT.otherModelsDict[rktData])
            else:
                what = SC4ModelMesh(rktData[1], rktData[2], virtualDAT)
                if not what.is_valid:
                    return None
                virtualDAT.otherModels.append(
                    StandardModel(virtualDAT.getEntry(rktData[0], rktData[1], rktData[2]), what))
                virtualDAT.otherModelsDict[rktData] = what
                self.viewingData.append(what)
        if self.rkType == 662775841 or self.rkType == 662775845:
            if rktData in virtualDAT.standardModelsDict:
                self.viewingData.append(virtualDAT.standardModelsDict[rktData])
            else:
                what = SC4Model(rktData[1], rktData[2], virtualDAT)
                if not what.is_valid:
                    return None
                virtualDAT.standardModels.append(
                    StandardModel(virtualDAT.getEntry(rktData[0], rktData[1], rktData[2]), what))
                virtualDAT.standardModelsDict[rktData] = what
                self.viewingData.append(what)
        if self.rkType == 662775843:
            if rktData[0:3] in virtualDAT.otherModelsDict:
                self.viewingData.append(virtualDAT.otherModelsDict[rktData[0:3]])
            else:
                what = SC4Model1MeshPerZoom(rktData[0], rktData[1], rktData[2:], virtualDAT)
                if not what.bValid:
                    return None
                virtualDAT.otherModels.append(
                    StandardModel(virtualDAT.getEntry(rktData[0], rktData[1], rktData[2]), what))
                virtualDAT.otherModelsDict[rktData[0:3]] = what
                self.viewingData.append(what)
        if self.rkType == 662775844:
            for line in range(len(rktData) // 8):
                data = rktData[line * 8:line * 8 + 8]
                if data[4] == 662775840:
                    if data[5] == 698733036:
                        if data[5:] in virtualDAT.atcsDict:
                            self.viewingData.append(virtualDAT.atcsDict[data[5:]])
                    elif data[5:] in virtualDAT.otherModelsDict:
                        self.viewingData.append(virtualDAT.otherModelsDict[data[5:]])
                    else:
                        what = SC4ModelMesh(data[6], data[7], virtualDAT)
                        if not what.is_valid:
                            continue
                        else:
                            virtualDAT.otherModels.append(
                                StandardModel(virtualDAT.getEntry(rktData[5], rktData[6], rktData[7]), what))
                            virtualDAT.otherModelsDict[data[5:]] = what
                            self.viewingData.append(what)
                if data[4] == 662775841:
                    if data[5:] in virtualDAT.standardModelsDict:
                        self.viewingData.append(virtualDAT.standardModelsDict[data[5:]])
                    else:
                        what = SC4Model(data[6], data[7], virtualDAT)
                        if not what.is_valid:
                            pass
                        else:
                            virtualDAT.standardModelsDict.append(
                                StandardModel(virtualDAT.getEntry(rktData[5], rktData[6], rktData[7]), what))
                            virtualDAT.standardModelsDict[data[5:]] = what
                            self.viewingData.append(what)

        return None

    def PreLoad(self, virtualDAT, s3DTexturesHolder):
        try:
            what = self.viewingData[0]
        except IndexError:
            return None

        what.PreLoad(virtualDAT, s3DTexturesHolder)
        return None

    def draw(self, viewer, fileNameStatic, zoom, rot, state):
        if state is None:
            state = 0
        try:
            what = self.viewingData[state]
        except IndexError:
            if viewer.s3d_mesh is not None:
                viewer.s3d_mesh.free_3d(viewer.s3d_textures_holder)
                viewer.s3d_mesh = None
            viewer.refresh(False)
            return
        except Exception:
            logger.exception('Model render failed (state=%r)', state)
            raise

        viewer = what.__class__.viewer
        self.mainFrame.viewer = viewer
        viewer.init_gl()
        viewer.refresh(False)
        if what.__class__ == SC4Model:
            what.draw(viewer, fileNameStatic, zoom, rot)
            if what.mainMesh.entry is None:
                fileNameStatic.SetLabel(invisibleModel)
            else:
                fileNameStatic.SetLabel(what.mainMesh.entry.fileName)
            fileNameStatic.Refresh(False)
        else:
            what.draw(viewer, fileNameStatic, zoom, rot)
        return


class SC4Model1MeshPerZoom():

    def __init__(self, TID, GID, IIDs, virtualDAT):
        self.name = '0x%08X-0x%08X' % (GID, IIDs[0])
        self.GID = GID
        self.IID = IIDs[0]
        self.virtualDAT = virtualDAT
        self.s3dMeshes = [S3D(virtualDAT.getEntry(1523640343, GID, x)) for x in IIDs]
        self.mainMesh = self.s3dMeshes[0]
        self.bValid = True
        self.descName = self.name
        for mesh in self.s3dMeshes:
            if mesh.entry is None:
                self.bValid = False

        return

    def PreLoad(self, virtualDAT, s3DTexturesHolder):
        for mesh in self.s3dMeshes:
            mesh.LEInit(virtualDAT, s3DTexturesHolder)

    def draw(self, viewer, fileNameStatic, nZoom=-1, nRot=0, state=0):
        viewer.angle_mul = 1
        if nZoom == -1:
            viewer.use_best_fit = True
            self.s3dMeshes[4].initialize(self.virtualDAT, viewer)
        else:
            viewer.use_best_fit = False
            viewer.zoom = nZoom
            self.s3dMeshes[nZoom].initialize(self.virtualDAT, viewer)


class SC4ModelMesh():

    def __init__(self, GID, IID, virtualDAT):
        self.name = '0x%08X-0x%08X' % (GID, IID)
        # Always define descName; an xml SC4PLUGINDESC entry overrides it below
        # when present. Without this default, models lacking that xml raise
        # AttributeError in StandardModel.__init__.
        self.descName = self.name
        self.GID = GID
        self.IID = IID
        self.virtualDAT = virtualDAT
        self.mainMesh = S3D(virtualDAT.getEntry(1523640343, GID, IID + 0))
        self.is_valid = True
        self.descName = self.name
        if self.mainMesh.entry is None:
            self.is_valid = False
        xmlEntry = virtualDAT.getEntry(2289530369, GID, IID)
        if xmlEntry:
            xmlEntry.read_file(None, True, True)
            try:
                xmlDoc = xml.dom.minidom.parseString(xmlEntry.content)
                for node in xmlDoc.childNodes:
                    if node.nodeType == node.ELEMENT_NODE and node.tagName == 'SC4PLUGINDESC':
                        self.name = self.name + ' [' + node.getAttribute('Name') + ']'
                        self.descName = node.getAttribute('Name')

                del xmlDoc
                xmlEntry.content = None
                xmlEntry.rawContent = None
                del xmlEntry
            except Exception:
                logger.exception('Error reading XML for model 0x%08X-0x%08X in %s',
                                 GID, IID, xmlEntry.fileName)
                xmlEntry.content = None
                xmlEntry.rawContent = None
                self.descName = self.name
                del xmlEntry

        else:
            self.name = self.name + xmlNotFound
            self.descName = self.name
        return

    def PreLoad(self, virtualDAT, s3DTexturesHolder):
        self.mainMesh.LEInit(virtualDAT, s3DTexturesHolder)

    def draw(self, viewer, fileNameStatic, nZoom=-1, nRot=0, state=0):
        preAngle = [0, 90, 180, 270]
        viewer.pre_angle = preAngle[nRot]
        viewer.angle_mul = 1
        if nZoom == -1:
            viewer.use_best_fit = True
            self.mainMesh.initialize(self.virtualDAT, viewer)
        else:
            viewer.use_best_fit = False
            viewer.zoom = nZoom
            self.mainMesh.initialize(self.virtualDAT, viewer)


class SC4Model():

    def __init__(self, GID, IID, virtualDAT):
        self.name = '0x%08X-0x%08X' % (GID, IID)
        # Always define descName; an xml SC4PLUGINDESC entry overrides it below
        # when present. Without this default, models lacking that xml raise
        # AttributeError in StandardModel.__init__.
        self.descName = self.name
        self.GID = GID
        self.IID = IID
        self.virtualDAT = virtualDAT
        mainMesh = virtualDAT.getEntry(1523640343, GID, IID + 0)
        self.s3dMeshes = [None, None, None, None, None]
        self.s3dMeshes[0] = [mainMesh, virtualDAT.getEntry(1523640343, GID, IID + 48) or mainMesh,
                             virtualDAT.getEntry(1523640343, GID, IID + 32) or mainMesh,
                             virtualDAT.getEntry(1523640343, GID, IID + 16) or mainMesh]
        self.s3dMeshes[1] = [
            virtualDAT.getEntry(1523640343, GID, IID + 256) or mainMesh,
            virtualDAT.getEntry(1523640343, GID, IID + 304) or mainMesh,
            virtualDAT.getEntry(1523640343, GID, IID + 288) or mainMesh,
            virtualDAT.getEntry(1523640343, GID, IID + 272) or mainMesh]
        self.s3dMeshes[2] = [
            virtualDAT.getEntry(1523640343, GID, IID + 512) or mainMesh,
            virtualDAT.getEntry(1523640343, GID, IID + 560) or mainMesh,
            virtualDAT.getEntry(1523640343, GID, IID + 544) or mainMesh,
            virtualDAT.getEntry(1523640343, GID, IID + 528) or mainMesh]
        self.s3dMeshes[3] = [
            virtualDAT.getEntry(1523640343, GID, IID + 768) or mainMesh,
            virtualDAT.getEntry(1523640343, GID, IID + 816) or mainMesh,
            virtualDAT.getEntry(1523640343, GID, IID + 800) or mainMesh,
            virtualDAT.getEntry(1523640343, GID, IID + 784) or mainMesh]
        self.s3dMeshes[4] = [
            virtualDAT.getEntry(1523640343, GID, IID + 1024) or mainMesh,
            virtualDAT.getEntry(1523640343, GID, IID + 1072) or mainMesh,
            virtualDAT.getEntry(1523640343, GID, IID + 1056) or mainMesh,
            virtualDAT.getEntry(1523640343, GID, IID + 1040) or mainMesh]
        nbrInit = 0
        for zoom in self.s3dMeshes:
            for rot in zoom:
                if rot == mainMesh:
                    nbrInit += 1

        if nbrInit > 1:
            self.is_valid = False
            return
        self.is_valid = True
        xmlEntry = virtualDAT.getEntry(2289530369, GID, IID)
        if xmlEntry:
            xmlEntry.read_file(None, True, True)
            try:
                xmlDoc = xml.dom.minidom.parseString(xmlEntry.content)
                for node in xmlDoc.childNodes:
                    if node.nodeType == node.ELEMENT_NODE and node.tagName == 'SC4PLUGINDESC':
                        self.name = self.name + ' [' + node.getAttribute('Name') + ']'
                        self.descName = node.getAttribute('Name')

                del xmlDoc
                xmlEntry.content = None
                xmlEntry.rawContent = None
                del xmlEntry
            except Exception:
                logger.exception('Error reading XML for model 0x%08X-0x%08X in %s',
                                 GID, IID, xmlEntry.fileName)
                xmlEntry.content = None
                xmlEntry.rawContent = None
                self.descName = self.name
                del xmlEntry

        else:
            self.name = self.name + xmlNotFound
            self.descName = self.name
        wx.Yield()
        for zoom in range(0, 5):
            self.s3dMeshes[zoom] = [S3D(entry) for entry in self.s3dMeshes[zoom]]

        self.mainMesh = self.s3dMeshes[0][0]
        return

    def draw(self, viewer, fileNameStatic, nZoom=-1, nRot=0, state=0):
        viewer.pre_angle = 0
        viewer.angle_mul = 1
        if nZoom == -1:
            viewer.use_best_fit = True
            self.s3dMeshes[4][nRot].initialize(self.virtualDAT, viewer)
        else:
            viewer.use_best_fit = False
            viewer.zoom = nZoom
            self.s3dMeshes[nZoom][nRot].initialize(self.virtualDAT, viewer)

    def PreLoad(self, virtualDAT, s3DTexturesHolder):
        for zoom in range(5):
            for rotation in range(4):
                self.s3dMeshes[zoom][rotation].LEInit(virtualDAT, s3DTexturesHolder)


class StandardModel():

    def __init__(self, entry, sc4Model):
        self.name = sc4Model.descName
        if entry is None:
            self.fileName = invisibleModel
        else:
            self.fileName = entry.fileName
        self.sc4Model = sc4Model
        self.entry = entry
        return
