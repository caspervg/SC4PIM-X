# uncompyle6 version 2.11.5
# Python bytecode 2.4 (62061)
# Decompiled from: Python 2.7.18 (default, Oct 15 2023, 16:43:11) 
# [GCC 11.4.0]
# Embedded file name: SC4Data.pyo
# Compiled at: 2010-01-15 23:55:13
from SC4DatTools import *
from S3DReader import *
import xml.dom.minidom
from translation import *
import time
import itertools
import thread
import FSHConverter
import Image
import ImageDraw
import ImageFont
import wx
import dircache

def ToUnsigned(val):
    try:
        return struct.unpack('L', struct.pack('l', val))[0]
    except:
        print type(val), val
        raise


def ToTile(val):
    try:
        return float(struct.unpack('l', struct.pack('L', int(val)))[0]) / float(1048576)
    except:
        print type(val), val
        raise


def ToCoord(val):
    return ToTile(val) * 16.0


class DictWrapper(object):

    def __init__(self, mapping):
        object.__init__(self)
        object.__setattr__(self, 'mapping', mapping)

    def __getitem__(self, key):
        if key.__class__.__name__ == 'unicode' or key.__class__.__name__ == 'str':
            if key[:2].upper() == '0X':
                key = '0x' + key[2:10].upper() + key[10:]
        if key in self.mapping.keys():
            return self.mapping[key]
        if key.__class__.__name__ == 'unicode' or key.__class__.__name__ == 'str':
            sub = key.find('.')
            if sub == -1:
                return ''
            k = key[0:sub]
            after = key[sub + 1:]
            return self.mapping[k][after]
        raise KeyError

    def __setitem__(self, key, value):
        self.mapping[key] = value

    def __getattr__(self, attr):
        if attr in self.mapping.keys():
            return self.mapping[attr]
        raise AttributeError, attr

    def __setattr__(self, attr, value):
        self.mapping[attr] = value

    def __str__(self):
        return str(self.mapping)

    def __repr__(self):
        return str(self.mapping)

    def update(self, other):
        self.mapping.update(other.mapping)

    def keys(self):
        return self.mapping.keys()

    def values(self):
        return self.mapping.values()

    def __len__(self):
        return len(self.mapping.keys())


def getText(nodelist):
    rc = ''
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data

    return rc


def readCategoryDef(node):
    cat = DictWrapper({})
    cat.descriptors = []
    cat.parent = None
    cat.imgName = None
    cat.imgIdx = None
    cat.imgName = node.getAttribute('img')
    cat.Name = node.getAttribute('Name')
    id = node.getAttribute('ID').upper()
    if id[:2] == '0X':
        cat.ID = int(node.getAttribute('ID'), 16)
    else:
        cat.ID = node.getAttribute('ID').upper()
    parentID = node.getAttribute('ParentID').upper()
    if parentID[:2] == '0X':
        cat.parentID = int(node.getAttribute('ParentID'), 16)
    else:
        cat.parentID = node.getAttribute('ParentID').upper()
    if cat.ID in categoryLocalized:
        cat.Name = categoryLocalized[cat.ID]
    cat.code = []
    cat.childs = []
    cat.filters = DictWrapper({})
    cat.filters.needed = []
    cat.filters.notallowed = []
    cat.setProperties = DictWrapper({})
    cat.factorProperties = DictWrapper({})
    cat.pairedFactorProperties = DictWrapper({})
    cat.programProperties = DictWrapper({})
    cat.evalProperties = DictWrapper({})
    cat.removeProperties = DictWrapper({})
    for subNode in node.childNodes:
        if subNode.nodeType == node.ELEMENT_NODE and subNode.tagName == 'PROPERTIES':
            for subsubNode in subNode.childNodes:
                if subsubNode.nodeType == node.ELEMENT_NODE and subsubNode.tagName == 'eval':
                    name = subsubNode.getAttribute('name')
                    expr = subsubNode.getAttribute('value')
                    cat.code.append((name, expr))
                if subsubNode.nodeType == node.ELEMENT_NODE and subsubNode.tagName == 'PROPERTY':
                    id = subsubNode.getAttribute('ID').upper()
                    if id[:2] == '0X':
                        id = int(id.lower(), 16)
                    else:
                        id = int(id)
                    removep = subsubNode.getAttribute('Remove')
                    if removep == '':
                        removep = None
                    else:
                        cat.removeProperties[id] = removep
                    value = subsubNode.getAttribute('Value')
                    if value == '':
                        value = None
                    if value:
                        cat.setProperties[id] = value
                    factor = subsubNode.getAttribute('Factor')
                    if factor == '':
                        factor = None
                    if factor:
                        cat.factorProperties[id] = [ float(f) for f in factor.split(',') ]
                    pairedFactor = subsubNode.getAttribute('PairedFactor')
                    if pairedFactor == '':
                        pairedFactor = None
                    if pairedFactor:
                        paired = pairedFactor.split(',')
                        cat.pairedFactorProperties[id] = []
                        for i in xrange(len(paired) / 2):
                            cat.pairedFactorProperties[id].append((paired[i * 2], float(paired[i * 2 + 1])))

                    setVal = subsubNode.getAttribute('Set')
                    if setVal == '':
                        setVal = None
                    if setVal:
                        cat.programProperties[id] = setVal
                    evalVal = subsubNode.getAttribute('Eval')
                    if evalVal == '':
                        evalVal = None
                    if evalVal:
                        cat.evalProperties[id] = evalVal

        if subNode.nodeType == node.ELEMENT_NODE and subNode.tagName == 'FILTERS':
            for subsubNode in subNode.childNodes:
                if subsubNode.nodeType == node.ELEMENT_NODE and subsubNode.tagName == 'NEEDED':
                    id = subsubNode.getAttribute('ID').upper()
                    if id[:2] == '0X':
                        id = int(id.lower(), 16)
                    else:
                        id = int(id)
                    value = subsubNode.getAttribute('Value')
                    if value == '':
                        value = None
                    if value:
                        value = value.upper()
                        if value[:2] == '0X':
                            value = int(value.lower(), 16)
                        else:
                            value = int(value)
                    cat.filters.needed.append((id, value))
                if subsubNode.nodeType == node.ELEMENT_NODE and subsubNode.tagName == 'NOT':
                    id = subsubNode.getAttribute('ID').upper()
                    if id[:2] == '0X':
                        id = int(id.lower(), 16)
                    else:
                        id = int(id)
                    value = subsubNode.getAttribute('Value')
                    if value == '':
                        value = None
                    if value:
                        value = value.upper()
                        if value[:2] == '0X':
                            value = int(value.lower(), 16)
                        else:
                            value = int(value)
                    cat.filters.notallowed.append((id, value))

    return cat


def DuplicateProp(dup, newID):
    prop = DictWrapper({})
    prop.Name = dup.Name
    prop.ID = newID
    prop.Type = dup.Type
    prop.Count = dup.Count
    prop.ShowAsHex = dup.ShowAsHex
    prop.ShowAsMap = dup.ShowAsMap
    prop.maxVal = dup.maxVal
    prop.minVal = dup.minVal
    prop.Options = dup.Options
    return prop


class Family():

    def __init__(self, familyID, virtualDAT, tree):
        self.familyID = familyID
        self.name = '0x%08X' % familyID
        self.bNamed = False
        potentialCohorts = virtualDAT.getEntries(87304289, 0, familyID + 268435456, gMask=0)
        if potentialCohorts != []:
            for cohort in potentialCohorts:
                try:
                    if cohort.examplar.entry == cohort:
                        pass
                except:
                    cohort.ReadFile(None, True, True)
                    examplar = Examplar(cohort)
                    cohort.examplar = examplar
                    cohort.rawContent = None
                    cohort.content = None

                name = cohort.examplar.GetProp(32)
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
        item = self.tree.AppendItem(self.item, propDesc.examplar.GetProp(32)[0])
        self.tree.SetPyData(item, propDesc)


def FinalizeCategory(root):
    root.descriptors = set(root.descriptors)
    for child in root.childs:
        FinalizeCategory(child)
        root.descriptors.update(set(child.descriptors))

    root.descriptors = list(root.descriptors)
    root.descriptors.sort(cmp=lambda a, b: cmp(a.fileName, b.fileName))


def AddDescRecurs(virtualDAT, catID, desc):
    if desc not in virtualDAT.categories[catID].descriptors:
        virtualDAT.categories[catID].descriptors.append(desc)
        if virtualDAT.categories[catID].parentID != 0:
            AddDescRecurs(virtualDAT, virtualDAT.categories[catID].parentID, desc)


class FloraDesc():

    def __init__(self, entry):
        self.examplar = entry.examplar
        try:
            self.name = entry.examplar.GetProp(32)[0]
        except:
            self.name = 'Unnamed 0x%08X-0x%08X-0x%08X' % (entry.tgi[0], entry.tgi[1], entry.tgi[2])

        self.fileName = entry.fileName
        self.rtk = None
        self.rtk = self.examplar.GetProp(662775840)
        if self.rtk is not None:
            self.rtk = tuple(self.rtk)
        else:
            self.rtk = self.examplar.GetProp(662775841)
            if self.rtk is not None:
                self.rtk = tuple(self.rtk)
            else:
                self.rtk = self.examplar.GetProp(662775844)
                if self.rtk is not None:
                    self.rtk = tuple(self.rtk[5:8])
                else:
                    self.rtk = self.examplar.GetProp(662775843)
                    if self.rtk is not None:
                        self.rtk = tuple(self.rtk[0:2] + [self.rtk[-1]])
        return


class ATCProxy():

    def __init__(self, entry, atc):
        if entry == None:
            self.fileName = invisibleATC
            self.name = unknonwMsg
        else:
            self.name = '0x%08X-0x%08X' % (entry.tgi[1], entry.tgi[2])
            self.fileName = entry.fileName
        self.sc4Model = atc
        return


class FoundationDesc():

    def __init__(self, entry):
        self.examplar = entry.examplar
        try:
            self.name = entry.examplar.GetProp(32)[0]
        except:
            self.name = 'Unnamed 0x%08X-0x%08X-0x%08X' % (entry.tgi[0], entry.tgi[1], entry.tgi[2])

        self.fileName = entry.fileName
        self.rtk = None
        self.rtk = self.examplar.GetProp(662775840)
        if self.rtk is not None:
            self.rtk = tuple(self.rtk)
        else:
            self.rtk = self.examplar.GetProp(662775841)
            if self.rtk is not None:
                self.rtk = tuple(self.rtk)
            else:
                self.rtk = self.examplar.GetProp(662775844)
                if self.rtk is not None:
                    self.rtk = tuple(self.rtk[5:8])
                else:
                    self.rtk = self.examplar.GetProp(662775843)
                    if self.rtk is not None:
                        self.rtk = tuple(self.rtk[0:2] + [self.rtk[-1]])
        return


def GetCategories(root, desc):
    if CheckAgainstFilter(root, desc.examplar):
        b = False
        if len(root.childs) == 0:
            if len(root.setProperties) + len(root.factorProperties) + len(root.pairedFactorProperties) + len(root.programProperties) + len(root.evalProperties) + len(root.code) > 0:
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
        self.examplar = entry.examplar
        try:
            self.name = entry.examplar.GetProp(32)[0]
        except:
            self.name = 'Unnamed 0x%08X-0x%08X-0x%08X' % (entry.tgi[0], entry.tgi[1], entry.tgi[2])

        self.fileName = entry.fileName
        self.rtk = None
        self.rtk = self.examplar.GetProp(662775840)
        if self.rtk is not None:
            self.rtk = tuple(self.rtk)
        else:
            self.rtk = self.examplar.GetProp(662775841)
            if self.rtk is not None:
                self.rtk = tuple(self.rtk)
            else:
                self.rtk = self.examplar.GetProp(662775844)
                if self.rtk is not None:
                    self.rtk = tuple(self.rtk[5:8])
                else:
                    self.rtk = self.examplar.GetProp(662775843)
                    if self.rtk is not None:
                        self.rtk = tuple(self.rtk[0:2] + [self.rtk[-1]])
        return


def Categorize(root, desc):
    if CheckAgainstFilter(root, desc.examplar):
        b = False
        if len(root.childs) == 0:
            b = True
            root.descriptors.append(desc)
            try:
                desc.cats.append(root.ID)
            except:
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


def CheckAgainstFilter(cat, examplar):
    needed = cat.filters.needed
    for f in needed:
        id = f[0]
        value = f[1]
        examplarValue = examplar.GetProp(id)
        if value == None and examplarValue is None:
            return False
        if value is not None:
            if examplarValue is None:
                return False
            if value not in examplarValue:
                return False

    notallowed = cat.filters.notallowed
    for f in notallowed:
        id = f[0]
        value = f[1]
        examplarValue = examplar.GetProp(id)
        if value == None and examplarValue is not None:
            return False
        if value is not None:
            if examplarValue is None:
                pass
            elif value in examplarValue:
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
    if prop.id >= 2297284864L and prop.id <= 2297286143L:
        mapFirstVal = [
         'Building', 'Prop', 'Texture', 'Fence', 'Flora', 'Water', 'Land', 'Network']
        mapSecondVal = ['all', 'med only', 'high only']
        mapThirdVal = ['South', 'West', 'North', 'East']
        mapIdx = ['Type', 'LOD', 'Orientation', 'X Pos', 'Z Pos', 'Y Pos', 'xmin', 'ymin', 'xmax', 'ymax', 'Usage', 'ObjectID', 'RefID', 'RUL', 'RUL Flags', 'SC4Path']
        resultat += '%s: ' % mapIdx[0]
        resultat += mapFirstVal[prop.values[0]]
        resultat += ' - %s: ' % mapIdx[1]
        resultat += mapSecondVal[prop.values[1] / 16]
        resultat += ' - %s: ' % mapIdx[2]
        try:
            resultat += mapThirdVal[prop.values[2]]
        except:
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
                except:
                    resultat += ' - unknown: '

                resultat += hex2str(v)

        return resultat
    for i, v in enumerate(prop.values):
        if resultat != u'':
            resultat += ' '
        if 'COL:%d' % i in propFormat.Options:
            resultat += propFormat.Options['COL:%d' % i].encode('unicode_escape') + ':'
        if v in propFormat.Options:
            resultat += propFormat.Options[v].encode('unicode_escape')
        elif prop.typeValue == 2816:
            if v == 0:
                resultat += 'False'
            else:
                resultat += 'True'
        elif prop.typeValue == 3072:
            resultat += v.decode('unicode_escape')
        elif prop.typeValue == 2304:
            resultat += '%.01f' % v
        elif prop.typeValue == 2048 and propFormat.ShowAsHex == True:
            resultat += '0x%016X' % v
        elif propFormat.ShowAsHex == True:
            resultat += '0x%08X' % v
        else:
            resultat += '%d' % v

    return resultat


def CreateAPropFromString(prop, value):
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


class ImageListLoaderProps():

    def __init__(self, virtualDAT):
        self.virtualDAT = virtualDAT
        self.keepGoing = self.running = False

    def Start(self):
        self.keepGoing = self.running = True
        thread.start_new_thread(self.Run, ())

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
        image = wx.EmptyImage(pil.size[0], pil.size[1])
        image.SetData(pil.convert('RGB').tostring())
        return image.ConvertToBitmap()

    def Run(self, dlg=None):
        fileName = 'NoPreview.jpg'
        image = wx.Image(fileName)
        idx = self.virtualDAT.ilStandardModels.Add(image.ConvertToBitmap())
        for s3d in self.virtualDAT.standardModels:
            if self.keepGoing == False:
                break
            fileName = 'ImageDB/%s-%s.jpg' % (hex2str(s3d.sc4Model.GID), hex2str(s3d.sc4Model.IID))
            if dlg:
                dlg.Increment()
            if os.path.exists(fileName):
                time.sleep(0)
                image = wx.Bitmap(fileName, wx.BITMAP_TYPE_JPEG)
                idx = self.virtualDAT.ilStandardModels.Add(image)
                if idx == -1:
                    print 'PropLoader : Error addind jpg file for', fileName, image.GetWidth(), 'by', image.GetHeight(), 'nbr already loaded:', self.virtualDAT.ilStandardModels.GetImageCount()
                self.virtualDAT.s3dEntries[s3d.entry.tgi] = idx

        self.running = False


class ImageListLoaderTexture():

    def __init__(self, virtualDAT):
        self.virtualDAT = virtualDAT
        self.keepGoing = self.running = False
        self.font = ImageFont.truetype('arial.ttf', 12)
        self.offset = self.font.getsize('R')

    def Start(self):
        self.keepGoing = self.running = True
        thread.start_new_thread(self.Run, ())

    def Stop(self):
        self.keepGoing = False

    def IsRunning(self):
        return self.running

    def Reset(self):
        self.Stop()
        while self.IsRunning():
            time.sleep(0.01)

        self.Start()

    def Run(self):

        def CmpTGI(tgi1, tgi2):
            if tgi1[0] == tgi2[0]:
                if tgi1[1] == tgi2[1]:
                    return cmp(tgi1[2], tgi2[2])
                else:
                    return cmp(tgi1[1], tgi2[1])
            else:
                return cmp(tgi1[0], tgi2[0])

        allTex = self.virtualDAT.allTextures
        for texEntry in allTex:
            if self.keepGoing == False:
                break
            texEntry.ReadFile(None, True, True)
            nbrLayers, trueAlpha, img, alpha, size = FSHConverter.decodeFSH(texEntry.content)
            texEntry.content = None
            texEntry.rawContent = None
            pilz = Image.fromstring('RGB', size, img)
            if trueAlpha:
                blank = Image.new('RGB', size, 16777215)
                alpha = Image.fromstring('L', size, alpha)
                pilz = Image.composite(pilz, blank, alpha)
            image = wx.EmptyImage(64, 64)
            pilz = pilz.resize((64, 64), Image.BICUBIC)
            if nbrLayers > 1:
                try:
                    draw = ImageDraw.Draw(pilz)
                    draw.ellipse((64 - self.offset[0] - 8, 64 - self.offset[1] - 2, 64 - self.offset[0] + 6, 64 - self.offset[1] + 12), fill=(156,
                                                                                                                                              181,
                                                                                                                                              140))
                    draw.text((64 - self.offset[0] - 5, 64 - self.offset[1] - 2), 'R', font=self.font, fill=(0,
                                                                                                             0,
                                                                                                             0))
                except:
                    print 'blem'
                    raise

            IID = texEntry.tgi[2] & 61440
            if IID == 0 or IID == 4096 or IID == 8192 or IID == 12288:
                signs = {0: '0',4096: '$',8192: '$$',12288: '$$$'}
                length = self.font.getsize(signs[IID])
                draw = ImageDraw.Draw(pilz)
                draw.ellipse((2, 64 - self.offset[1] - 2, length[0] + 7, 64 - self.offset[1] + 12), fill=(156,
                                                                                                          181,
                                                                                                          140))
                draw.text((5, 64 - self.offset[1] - 2), signs[IID], font=self.font, fill=(0,
                                                                                          0,
                                                                                          0))
            image.SetData(pilz.convert('RGB').tostring())
            if trueAlpha:
                idx = self.virtualDAT.ilOver.Add(image.ConvertToBitmap())
                if idx == -1:
                    print 'OverlayLoader : Error addind fsh %s-%s-%s from %s' % (hex2str(texEntry.tgi[0]), hex2str(texEntry.tgi[1]), hex2str(texEntry.tgi[2]), texEntry.fileName)
                self.virtualDAT.overTexEntriesDict[texEntry] = idx
                self.virtualDAT.overTexEntries.append(texEntry)
            else:
                idx = self.virtualDAT.ilBase.Add(image.ConvertToBitmap())
                if idx == -1:
                    print 'BaseLoader : Error addind fsh %s-%s-%s from %s' % (hex2str(texEntry.tgi[0]), hex2str(texEntry.tgi[1]), hex2str(texEntry.tgi[2]), texEntry.fileName)
                self.virtualDAT.baseTexEntriesDict[texEntry] = idx
                self.virtualDAT.baseTexEntries.append(texEntry)

        self.virtualDAT.baseTexEntries.sort(cmp=lambda n1, n2: CmpTGI(n1.tgi, n2.tgi))
        self.virtualDAT.overTexEntries.sort(cmp=lambda n1, n2: CmpTGI(n1.tgi, n2.tgi))
        self.running = False
        return


def IsAChild(cat, id):
    if cat == None:
        return False
    if cat.ID == id:
        return True
    return IsAChild(cat.parent, id)


def IsFromCategoryDesc(cat, desc):
    return desc in cat.descriptors


def IsFromCategory(cat, examplar):
    if cat == None:
        return True
    return CheckAgainstFilter(cat, examplar) and IsFromCategory(cat.parent, examplar)


class LotDesc():

    def __init__(self, entry):
        self.examplar = entry.examplar
        try:
            self.name = entry.examplar.GetProp(32)[0]
        except:
            self.name = 'Unnamed 0x%08X-0x%08X-0x%08X' % (entry.tgi[0], entry.tgi[1], entry.tgi[2])

        self.fileName = entry.fileName
        self.rtk = None
        return


def PrintCat(cat, spaces=0):
    print ' ' * spaces,
    print cat.Name
    for child in cat.childs:
        PrintCat(child, spaces + 1)


class PropDesc():

    def __init__(self, entry):
        self.examplar = entry.examplar
        try:
            self.name = entry.examplar.GetProp(32)[0]
        except:
            self.name = 'Unnamed 0x%08X-0x%08X-0x%08X' % (entry.tgi[0], entry.tgi[1], entry.tgi[2])

        self.fileName = entry.fileName
        self.rtk = None
        self.rtk = self.examplar.GetProp(662775840)
        if self.rtk is not None:
            self.rtk = tuple(self.rtk)
        else:
            self.rtk = self.examplar.GetProp(662775841)
            if self.rtk is not None:
                self.rtk = tuple(self.rtk)
            else:
                self.rtk = self.examplar.GetProp(662775844)
                if self.rtk is not None:
                    self.rtk = tuple(self.rtk[5:8])
                else:
                    self.rtk = self.examplar.GetProp(662775843)
                    if self.rtk is not None:
                        self.rtk = tuple(self.rtk[0:2] + [self.rtk[-1]])
        return


def ReadStageVsDensity(node):
    purpose = str(node.getAttribute('purpose'))
    wealth = int(node.getAttribute('wealth'))
    ratio = [ float(x) for x in str(node.getAttribute('ratio')).split(',') ]
    baseTex = int(node.getAttribute('baseTex'), 16)
    return (
     ratio, purpose, wealth, baseTex)


def ReadZoning(node):
    purpose = str(node.getAttribute('purpose'))
    value = int(node.getAttribute('value'))
    stages = [ int(x) for x in str(node.getAttribute('stages')).split(',') ]
    height = int(node.getAttribute('height'))
    return (
     purpose, value, stages, height)


def readPropertyDef(node):
    prop = DictWrapper({})
    prop.Name = str(node.getAttribute('Name'))
    id = node.getAttribute('ID').upper()
    if id[:2] == '0X':
        prop.ID = int(node.getAttribute('ID'), 16)
    else:
        prop.ID = node.getAttribute('ID').upper()
    prop.Type = str(node.getAttribute('Type'))
    count = node.getAttribute('Count').upper()
    if count == '':
        count = '1'
    prop.Count = int(count)
    if node.getAttribute('ShowAsHex').upper() == 'Y':
        prop.ShowAsHex = True
    else:
        prop.ShowAsHex = False
    options = {}
    prop.ShowAsMap = False
    minVal = node.getAttribute('MinValue')
    maxVal = node.getAttribute('MaxValue')
    if minVal is None or minVal == '':
        if prop.Type == 'Uint32' or prop.Type == 'Uint8':
            minVal = 0
        if prop.Type == 'Sint32' or prop.Type == 'Sint64':
            minVal = -100000000
        if prop.Type == 'Float32':
            minVal = -100000000.0
    else:
        if len(minVal) > 1 and minVal[1] == 'x':
            minVal = int(minVal, 16)
        else:
            minVal = int(minVal)
        if maxVal is None or maxVal == '':
            if prop.Type == 'Uint32':
                maxVal = 4294967295L
            if prop.Type == 'Uint8':
                maxVal = 255
            if prop.Type == 'Sint32':
                maxVal = 2147483647
            if prop.Type == 'Sint64':
                maxVal = 9223372036854775807L
            if prop.Type == 'Float32':
                maxVal = 100000000.0
        elif len(maxVal) > 1 and maxVal[1] == 'x':
            maxVal = int(maxVal, 16)
        else:
            maxVal = int(maxVal)
        prop.maxVal = maxVal
        prop.minVal = minVal
        for subNode in node.childNodes:
            if subNode.nodeType == node.ELEMENT_NODE and subNode.tagName == 'FORMAT':
                prop.ShowAsMap = True
            if subNode.nodeType == node.ELEMENT_NODE and subNode.tagName == 'OPTION':
                value = subNode.getAttribute('Value').upper()
                if value[:3] == 'COL':
                    pass
                elif len(value) > 2 and value[1] == 'X':
                    value = int('0x' + value[2:], 16)
                else:
                    value = int(value)
                meaning = subNode.getAttribute('Name')
                options[value] = meaning

    prop.Options = options
    return prop


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
                if what.bValid == False:
                    return None
                virtualDAT.otherModels.append(StandardModel(virtualDAT.getEntry(rktData[0], rktData[1], rktData[2]), what))
                virtualDAT.otherModelsDict[rktData] = what
                self.viewingData.append(what)
        if self.rkType == 662775841 or self.rkType == 662775845:
            if rktData in virtualDAT.standardModelsDict:
                self.viewingData.append(virtualDAT.standardModelsDict[rktData])
            else:
                what = SC4Model(rktData[1], rktData[2], virtualDAT)
                if not what.bValid:
                    return None
                virtualDAT.standardModels.append(StandardModel(virtualDAT.getEntry(rktData[0], rktData[1], rktData[2]), what))
                virtualDAT.standardModelsDict[rktData] = what
                self.viewingData.append(what)
        if self.rkType == 662775843:
            if rktData[0:3] in virtualDAT.otherModelsDict:
                self.viewingData.append(virtualDAT.otherModelsDict[rktData[0:3]])
            else:
                what = SC4Model1MeshPerZoom(rktData[0], rktData[1], rktData[2:], virtualDAT)
                if not what.bValid:
                    return None
                virtualDAT.otherModels.append(StandardModel(virtualDAT.getEntry(rktData[0], rktData[1], rktData[2]), what))
                virtualDAT.otherModelsDict[rktData[0:3]] = what
                self.viewingData.append(what)
        if self.rkType == 662775844:
            for line in xrange(len(rktData) / 8):
                data = rktData[line * 8:line * 8 + 8]
                if data[4] == 662775840:
                    if data[5] == 698733036:
                        if data[5:] in virtualDAT.atcsDict:
                            self.viewingData.append(virtualDAT.atcsDict[data[5:]])
                    elif data[5:] in virtualDAT.otherModelsDict:
                        self.viewingData.append(virtualDAT.otherModelsDict[data[5:]])
                    else:
                        what = SC4ModelMesh(data[6], data[7], virtualDAT)
                        if what.bValid == False:
                            continue
                        else:
                            virtualDAT.otherModels.append(StandardModel(virtualDAT.getEntry(rktData[5], rktData[6], rktData[7]), what))
                            virtualDAT.otherModelsDict[data[5:]] = what
                            self.viewingData.append(what)
                if data[4] == 662775841:
                    if data[5:] in virtualDAT.standardModelsDict:
                        self.viewingData.append(virtualDAT.standardModelsDict[data[5:]])
                    else:
                        what = SC4Model(data[6], data[7], virtualDAT)
                        if not what.bValid:
                            pass
                        else:
                            virtualDAT.standardModelsDict.append(StandardModel(virtualDAT.getEntry(rktData[5], rktData[6], rktData[7]), what))
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

    def Draw(self, viewer, fileNameStatic, zoom, rot, state):
        if state == None:
            state = 0
        try:
            what = self.viewingData[state]
        except IndexError:
            if viewer.S3DMesh != None:
                viewer.S3DMesh.Free3D(viewer.s3DTexturesHolder)
                viewer.S3DMesh = None
            viewer.Refresh(False)
            return
        except:
            print state
            raise

        viewer = what.__class__.viewer
        self.mainFrame.viewer = viewer
        viewer.InitGL()
        viewer.Refresh(False)
        if what.__class__ == SC4Model:
            what.Draw(viewer, fileNameStatic, zoom, rot)
            if what.mainMesh.entry == None:
                fileNameStatic.SetLabel(invisibleModel)
            else:
                fileNameStatic.SetLabel(what.mainMesh.entry.fileName)
            fileNameStatic.Refresh(False)
        else:
            what.Draw(viewer, fileNameStatic, zoom, rot)
        return


class SC4Model1MeshPerZoom():

    def __init__(self, TID, GID, IIDs, virtualDAT):
        self.name = '0x%08X-0x%08X' % (GID, IIDs[0])
        self.GID = GID
        self.IID = IIDs[0]
        self.virtualDAT = virtualDAT
        self.s3dMeshes = [ S3D(virtualDAT.getEntry(1523640343, GID, x)) for x in IIDs ]
        self.mainMesh = self.s3dMeshes[0]
        self.bValid = True
        self.descName = self.name
        for mesh in self.s3dMeshes:
            if mesh.entry == None:
                self.bValid = False

        return

    def PreLoad(self, virtualDAT, s3DTexturesHolder):
        for mesh in self.s3dMeshes:
            mesh.LEInit(virtualDAT, s3DTexturesHolder)

    def Draw(self, viewer, fileNameStatic, nZoom=-1, nRot=0, state=0):
        viewer.angleMul = 1
        if nZoom == -1:
            viewer.useBestFit = True
            self.s3dMeshes[4].Initialize(self.virtualDAT, viewer)
        else:
            viewer.useBestFit = False
            viewer.zoom = nZoom
            self.s3dMeshes[nZoom].Initialize(self.virtualDAT, viewer)


class SC4ModelMesh():

    def __init__(self, GID, IID, virtualDAT):
        self.name = '0x%08X-0x%08X' % (GID, IID)
        self.GID = GID
        self.IID = IID
        self.virtualDAT = virtualDAT
        self.mainMesh = S3D(virtualDAT.getEntry(1523640343, GID, IID + 0))
        self.bValid = True
        self.descName = self.name
        if self.mainMesh.entry == None:
            self.bValid = False
        xmlEntry = virtualDAT.getEntry(2289530369L, GID, IID)
        if xmlEntry:
            xmlEntry.ReadFile(None, True, True)
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
            except:
                print 'Error reading the xml in',
                print xmlEntry.fileName
                print 'xml for model 0x%08X-0x%08X' % (GID, IID)
                print xmlEntry.content
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

    def Draw(self, viewer, fileNameStatic, nZoom=-1, nRot=0, state=0):
        preAngle = [0, 90, 180, 270]
        viewer.preAngle = preAngle[nRot]
        viewer.angleMul = 1
        if nZoom == -1:
            viewer.useBestFit = True
            self.mainMesh.Initialize(self.virtualDAT, viewer)
        else:
            viewer.useBestFit = False
            viewer.zoom = nZoom
            self.mainMesh.Initialize(self.virtualDAT, viewer)


class SC4Model():

    def __init__(self, GID, IID, virtualDAT):
        self.name = '0x%08X-0x%08X' % (GID, IID)
        self.GID = GID
        self.IID = IID
        self.virtualDAT = virtualDAT
        mainMesh = virtualDAT.getEntry(1523640343, GID, IID + 0)
        self.s3dMeshes = [None, None, None, None, None]
        self.s3dMeshes[0] = [mainMesh, virtualDAT.getEntry(1523640343, GID, IID + 48) or mainMesh, virtualDAT.getEntry(1523640343, GID, IID + 32) or mainMesh, virtualDAT.getEntry(1523640343, GID, IID + 16) or mainMesh]
        self.s3dMeshes[1] = [
         virtualDAT.getEntry(1523640343, GID, IID + 256) or mainMesh, virtualDAT.getEntry(1523640343, GID, IID + 304) or mainMesh, virtualDAT.getEntry(1523640343, GID, IID + 288) or mainMesh, virtualDAT.getEntry(1523640343, GID, IID + 272) or mainMesh]
        self.s3dMeshes[2] = [
         virtualDAT.getEntry(1523640343, GID, IID + 512) or mainMesh, virtualDAT.getEntry(1523640343, GID, IID + 560) or mainMesh, virtualDAT.getEntry(1523640343, GID, IID + 544) or mainMesh, virtualDAT.getEntry(1523640343, GID, IID + 528) or mainMesh]
        self.s3dMeshes[3] = [
         virtualDAT.getEntry(1523640343, GID, IID + 768) or mainMesh, virtualDAT.getEntry(1523640343, GID, IID + 816) or mainMesh, virtualDAT.getEntry(1523640343, GID, IID + 800) or mainMesh, virtualDAT.getEntry(1523640343, GID, IID + 784) or mainMesh]
        self.s3dMeshes[4] = [
         virtualDAT.getEntry(1523640343, GID, IID + 1024) or mainMesh, virtualDAT.getEntry(1523640343, GID, IID + 1072) or mainMesh, virtualDAT.getEntry(1523640343, GID, IID + 1056) or mainMesh, virtualDAT.getEntry(1523640343, GID, IID + 1040) or mainMesh]
        nbrInit = 0
        for zoom in self.s3dMeshes:
            for rot in zoom:
                if rot == mainMesh:
                    nbrInit += 1

        if nbrInit > 1:
            self.bValid = False
            return
        self.bValid = True
        xmlEntry = virtualDAT.getEntry(2289530369L, GID, IID)
        if xmlEntry:
            xmlEntry.ReadFile(None, True, True)
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
            except:
                print 'Error reading the xml in',
                print xmlEntry.fileName
                print 'xml for model 0x%08X-0x%08X' % (GID, IID)
                print xmlEntry.content
                xmlEntry.content = None
                xmlEntry.rawContent = None
                self.descName = self.name
                del xmlEntry

        else:
            self.name = self.name + xmlNotFound
            self.descName = self.name
        wx.Yield()
        for zoom in xrange(0, 5):
            self.s3dMeshes[zoom] = [ S3D(entry) for entry in self.s3dMeshes[zoom] ]

        self.mainMesh = self.s3dMeshes[0][0]
        return

    def Draw(self, viewer, fileNameStatic, nZoom=-1, nRot=0, state=0):
        viewer.preAngle = 0
        viewer.angleMul = 1
        if nZoom == -1:
            viewer.useBestFit = True
            self.s3dMeshes[4][nRot].Initialize(self.virtualDAT, viewer)
        else:
            viewer.useBestFit = False
            viewer.zoom = nZoom
            self.s3dMeshes[nZoom][nRot].Initialize(self.virtualDAT, viewer)

    def PreLoad(self, virtualDAT, s3DTexturesHolder):
        for zoom in xrange(5):
            for rotation in xrange(4):
                self.s3dMeshes[zoom][rotation].LEInit(virtualDAT, s3DTexturesHolder)


class StandardModel():

    def __init__(self, entry, sc4Model):
        self.name = sc4Model.descName
        if entry == None:
            self.fileName = invisibleModel
        else:
            self.fileName = entry.fileName
        self.sc4Model = sc4Model
        self.entry = entry
        return


class VirtualDat():
    this = None

    def __init__(self, visualTree):
        VirtualDat.this = self
        self.ilOver = wx.ImageList(64, 64, True)
        self.ilBase = wx.ImageList(64, 64, True)
        self.ilStandardModels = wx.ImageList(64, 64, True)
        self.ilIcon = wx.ImageList(44 * 4, 44, True)
        image = wx.EmptyImage(44 * 4, 44)
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
        self.tree = visualTree
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
        x = [ v for v in self.zoning.keys() if v[0] == purpose ]
        res = [ self.zoning[v][0] for v in x if height < v[1] ]
        res.sort()
        return res

    def FindBuildingFromID(self, buildingID):
        if buildingID in self.categories:
            bOk = False
            for desc in self.categories[buildingID].descriptors:
                if desc.examplar.GetProp(16)[0] == 2 and desc.examplar.entry.tgi[0] == 1697917002:
                    return desc

        possibles = filter(lambda desc: desc.examplar.entry.tgi[2] == buildingID, self.categories[210746197].descriptors)
        for desc in possibles:
            return desc

    def FindBuildingFromLot(self, lotExamplar):
        buildingID = None
        for lcp in range(2297284864L, 2297286144L):
            values = lotExamplar.GetProp(lcp)
            if values == None:
                return
            if values[0] == 0:
                buildingID = values[12]
                break

        if buildingID == None:
            return
        return self.FindBuildingFromID(buildingID)

    def FindLotFromBuilding(self, buildingExamplar):
        if buildingExamplar.GetProp(662775920) is not None:
            possibles = list(buildingExamplar.GetProp(662775920)) + [buildingExamplar.entry.tgi[2]]
        else:
            possibles = [
             buildingExamplar.entry.tgi[2]]

        def UseThisIID(desc):
            for lcp in range(2297284864L, 2297286143L):
                values = desc.examplar.GetProp(lcp)
                if values == None:
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
            for lcp in range(2297284864L, 2297286143L):
                values = desc.examplar.GetProp(lcp)
                if values == None:
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
                if desc.examplar.GetProp(16)[0] == 30 and desc.examplar.entry.tgi[0] == 1697917002:
                    return desc

        possibles = filter(lambda desc: desc.examplar.entry.tgi[2] == propID, self.categories[210746660].descriptors)
        for desc in possibles:
            return desc

    def GetAllEntriesFromFile(self, fileName):
        return [ entry for entry in self.allEntries if entry.fileName == fileName ]

    def ReadProperties(self):
        propertiesXML = xml.dom.minidom.parse('new_properties.xml')
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
                            if category.imgName == None or category.imgName == '':
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

        fProp = self.properties[2297284864L]
        for lcp in range(2297284865L, 2297286144L):
            self.properties[lcp] = DuplicateProp(fProp, lcp)

        return

    def addFolder(self, dlg, folderName, bRecurse=True, bStandard=False):
        filesName = BuildSortedFilesList(folderName, bRecurse)
        for fileName in filesName:
            self.addFile(dlg, fileName, bStandard)

    def addFile(self, dlg, fileName, bStandard=False, bForceUpdate=False):
        sc4File = DatFile(fileName, dlg, True)
        self.addEntries(sc4File.entries, dlg, bStandard, bForceUpdate)

    def addEntries(self, entries, dlg, bStandard, bForceUpdate):
        for entry in entries:
            entry.bStandard = bStandard
            entry.virtualDAT = self
            try:
                idx = self.TGIIndex[entry.tgi]
                self.allEntries[idx] = entry
            except KeyError:
                self.TGIIndex[entry.tgi] = len(self.allEntries)
                self.allEntries.append(entry)

            if bForceUpdate:
                self.tree.UpdateEntry(entry, self, entry.bStandard, dlg)

    def getEntries(self, t, g, i, tMask=4294967295L, gMask=4294967295L, iMask=4294967295L):
        if t == 87304289 and tMask == 4294967295L:
            return filter(lambda entry: entry.tgi[1] & gMask == g and entry.tgi[2] & iMask == i, self.cohorts)
        return filter(lambda entry: entry.tgi[0] & tMask == t and entry.tgi[1] & gMask == g and entry.tgi[2] & iMask == i, self.allEntries)

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

        for entry in itertools.ifilter(lambda ent: ent.tgi[0] in [2058686020, 1697917002, 698733036, 1523640343], self.allEntries):
            self.tree.UpdateEntry(entry, self, entry.bStandard, dlg)

        FinalizeCategory(self.rootCategory)
        self.missingPics = []
        for s3d in self.standardModels:
            fileName = 'ImageDB/%s-%s.jpg' % (hex2str(s3d.sc4Model.GID), hex2str(s3d.sc4Model.IID))
            if not os.path.exists(fileName):
                self.missingPics.append((fileName, s3d))
# okay decompiling SC4Data.pyo
