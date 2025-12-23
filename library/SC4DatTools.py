"""SC4 DAT file parsing and manipulation tools.

This module provides classes and functions for reading, parsing, and writing
SimCity 4 .dat files, including compressed entries and property handling.
"""
import wx
import time
import struct
import QFS
import os
import os.path
import re
import io
binEx = 0
textEx = 0
binProp = 0

def CreateAProp(prop, values):
    count = prop.Count
    if count == 1:
        count = 0
    else:
        count = len(values)
    strVal = []
    for v in values:
        if prop.Type == 'String':
            strVal.append('"%s"' % v)
        elif prop.Type == 'Float32':
            strVal.append('%.8f' % v)
        elif prop.Type == 'Bool':
            if v:
                strVal.append('True')
            else:
                strVal.append('False')
        elif prop.Type == 'Sint64':
            strVal.append(hex2str(v, 64))
        elif prop.Type == 'Uint8':
            strVal.append(hex2str(v, 8))
        else:
            strVal.append(hex2str(v))

    buffer = '0x%08x:{"%s"}=%s:%d:(%s)' % (prop.ID, prop.Name, prop.Type, count, ','.join(strVal))
    return buffer


propRegex = re.compile('0[xX]([\\dA-Fa-f]+):{"([a-zA-Z0-9_ \\.,/:\\(\\)]+)"}=([a-zA-Z0-9]+):([0-9]+):{(.*)}')
generic_saveValue = 3
COMPRESSED_SIG = 64272
translationTable = '#' * 32 + ''.join([ chr(x) for x in range(32, 128) ]) + '#' * 128

def InfoEx():
    pass


def hex2str(v, size=32):
    if v >= 0:
        if size == 8:
            return '0x%02x' % int(v)
        elif size == 32:
            return '0x%08x' % int(v)
        else:
            return '0x%016x' % int(v)
    elif size == 32:
        return hex(struct.unpack('I', struct.pack('i', v))[0])[:-1]
    elif size == 8:
        return '0x%02x' % int(255 - ~v)
    else:
        return '0x%016x' % int(18446744073709551615 - ~v)


class Prop():
    validFormat = {1792: 'i',2304: 'f',768: 'I',2816: 'b',256: 'B',2048: 'q',512: 'h'}
    format2String = {768: 'Uint32',3072: 'String',2304: 'Float32',2816: 'Bool',256: 'Uint8',2048: 'Sint64',1792: 'Sint32'}

    def __init__(self, line, binary, examplar, initPos=0):
        global binProp
        self.examplar = examplar
        kind = examplar.GetProp(16)
        if kind is not None:
            if kind[0] not in [30, 2, 17, 15, 16]:
                self.id = 0
                return
        if binary:
            binProp += 1
            self.values = []
            self.id, self.typeValue, self.sizeOfCounter = struct.unpack('IHH', line.read(8))
            count = 8
            if self.typeValue == 3072:
                self.count = struct.unpack('B', line.read(1))[0]
                strlen = struct.unpack('I', line.read(4))[0]
                tt = str(line.read(strlen))
                self.rawdata = tt
                txtConv = tt.translate(translationTable)
                self.values = [txtConv]
                count += 1 + 4 + strlen
            else:
                offset = 0
                if self.sizeOfCounter > 0:
                    line.read(1)
                    self.count = struct.unpack('H', line.read(2))[0]
                    line.read(2)
                    offset = 4
                else:
                    self.count = struct.unpack('B', line.read(1))[0]
                nbr = self.count
                if nbr == 0 and self.sizeOfCounter == 0:
                    nbr = 1
                if self.typeValue not in Prop.validFormat.keys():
                    print('*' * 21, 'ERROR', '*' * 21)
                    print('in examplar', hex(self.examplar.entry.TGI['t']), 
                          hex(self.examplar.entry.TGI['g']), 
                          hex(self.examplar.entry.TGI['i']))
                    print('located in', self.examplar.entry.fileName)
                    print('Unknown prop type')
                s = struct.calcsize(Prop.validFormat[self.typeValue] * nbr)
                self.values = list(struct.unpack(Prop.validFormat[self.typeValue] * nbr, line.read(s)))
                count += 1 + s + offset
            self.sized = count
        else:
            try:
                initialLine = line[:]
                self.values = []
                comp = line.split('"')
                IID = hex(self.examplar.entry.TGI['i'])
                comp[1] = comp[1].replace(':', '_')
                line = '"'.join(comp)
                if line[-1] == ' ':
                    line = line[:-1]
                fields = line.split(':')
                self.id = int(fields[0], 16)
                self.count = int(fields[2])
                if self.count == 0:
                    self.sizeOfCounter = 0
                else:
                    self.sizeOfCounter = 128
                self.typeValue = fields[1].split('=')[1]
                self.named = fields[1].split('=')[0]
                self.named = self.named.split('"')[1]
                if self.named[:4] == 'SFX_':
                    self.named = 'SFX:' + self.named[4:]
                tv = self.typeValue
                vconv = {'Uint32': 768,'String': 3072,'Float32': 2304,'Bool': 2816,'Sint8': 2816,'Uint8': 256,'Sint64': 2048,'Sint32': 1792}
                self.typeValue = vconv[self.typeValue]
                if tv == 'Bool':
                    values = fields[3][1:-1].split(',')
                    self.values = []
                    for v in values:
                        if v == 'True':
                            self.values.append(True)
                        else:
                            self.values.append(False)

                else:
                    if tv == 'String':
                        tt = fields[3][2:-2]
                        self.rawdata = tt
                        txtConv = tt.translate(translationTable)
                        self.values = [txtConv]
                    if tv == 'Float32':
                        if fields[3][1:-1].split(',') != ['']:
                            self.values = [ float(x) for x in fields[3][1:-1].split(',') ]
                    if fields[3][1:-1].split(',') != ['']:

                        def convH(s):
                            mul = 1
                            if s[0] == '-':
                                mul = -1
                                s = s[1:]
                            if len(s) > 2:
                                if s[1].upper() == 'X':
                                    v = int(s, 16)
                                else:
                                    try:
                                        v = int(s)
                                    except ValueError:
                                        v = int(s, 16)

                            else:
                                try:
                                    v = int(s)
                                except ValueError:
                                    v = int(s, 16)

                                v *= mul
                                if self.typeValue == 768:
                                    if v < 0:
                                        return 0
                                    if v > 4294967295:
                                        return 4294967295
                                if self.typeValue == 1792:
                                    v = struct.unpack('l', struct.pack('L', v))[0]
                                    if v > 2147483647:
                                        return 2147483647
                                    if v < -2147483648:
                                        return -2147483648
                                if self.typeValue == 2816:
                                    v = struct.unpack('b', struct.pack('B', v))[0]
                                    if v > 127:
                                        return 127
                                    if v < -128:
                                        return -128
                                if self.typeValue == 256:
                                    if v < 0:
                                        return 0
                                    if v > 255:
                                        return 255
                            return v

                        self.values = [ convH(x) for x in fields[3][1:-1].split(',') ]
            except Exception as e:
                print('*' * 21, 'ERROR', '*' * 21)
                print('in examplar', hex(self.examplar.entry.TGI['t']),
                      hex(self.examplar.entry.TGI['g']),
                      hex(self.examplar.entry.TGI['i']))
                print('located in', self.examplar.entry.fileName)
                print(initialLine)
                print('*' * 49)
                raise

        return

    def __str__(self):
        h = hex(self.id)
        h += ' ' + hex(self.typeValue) + ' '
        h += str(self.count) + ' '
        h += str(self.values)
        return h

    def ToStr(self):

        def convert(v):
            if self.typeValue == 3072:
                return v
            if self.typeValue == 2304:
                return '%.08f' % v
            if self.typeValue == 2816:
                if v == 0:
                    return 'False'
                return 'True'
            if self.typeValue == 256:
                return hex2str(v, 8)
            if self.typeValue == 2048:
                return hex2str(v, 64)
            if self.typeValue == 1792:
                return hex2str(v)
            if self.typeValue == 768:
                return hex2str(v)
            raise KeyError

        return ','.join([ convert(v) for v in self.values ])

    def RepValue(self, v):
        if self.typeValue == 768:
            try:
                return hex2str(v)
            except:
                print 'error in prop',
                print hex2str(self.id),
                print v,
                print type(v)
                raise

        if self.typeValue == 3072:
            return v
        if self.typeValue == 2304:
            s = '%.8f' % v
            while 1:
                if s[-1] == '0':
                    s = s[:-1]
                elif s[-1] == '.':
                    s = s[:-1]
                    break
                else:
                    break

            return s
        if self.typeValue == 2816:
            if v == 0:
                return 'False'
            return 'True'
        if self.typeValue == 256:
            return hex2str(v, 8)
        if self.typeValue == 2048:
            return hex2str(v, 64)
        if self.typeValue == 1792:
            return hex2str(v)
        raise KeyError

    def TextRep(self):
        ret = '0x%08x' % self.id
        if hasattr(self, 'named'):
            ret += ':{"%s"}=' % self.named
        else:
            ret += ':{"%s"}=' % self.examplar.entry.virtualDAT.properties[self.id].Name
        namedType = {768: 'Uint32',3072: 'String',2304: 'Float32',2816: 'Bool',256: 'Uint8',2048: 'Sint64',1792: 'Sint32'}
        ret += namedType[self.typeValue]
        ret += ':'
        self.count = len(self.values)
        if self.count == 1 and self.sizeOfCounter == 0:
            self.count = 0
        ret += '%d' % self.count
        ret += ':{'
        if self.typeValue == 3072:
            ret += '"'
        ret += ','.join([ self.RepValue(v) for v in self.values ])
        if self.typeValue == 3072:
            ret += '"'
        ret += '}'
        return ret

    def BinaryRep(self):
        try:
            ret = struct.pack('I', self.id)
            ret += struct.pack('H', self.typeValue)
            if self.examplar.entry.virtualDAT.properties[self.id].Count == 1:
                self.sizeOfCounter = 0
            else:
                self.sizeOfCounter = 128
            if self.typeValue == 3072:
                self.sizeOfCounter = 128
            ret += struct.pack('H', self.sizeOfCounter)
            self.count = len(self.values)
            if self.count == 1 and self.sizeOfCounter == 0:
                self.count = 0
            if self.typeValue == 3072:
                ret += struct.pack('B', 0)
                ret += struct.pack('I', len(self.values[0]))
                ret += str(self.values[0])
            else:
                if self.sizeOfCounter > 0:
                    ret += struct.pack('B', 0)
                    ret += struct.pack('H', self.count)
                    ret += struct.pack('H', 0)
                else:
                    ret += struct.pack('B', self.count)
                for v in self.values:
                    try:
                        ret += struct.pack(Prop.validFormat[self.typeValue], v)
                        continue
                    except:
                        raise

            return ret
        except:
            print '*' * 21,
            print 'ERROR',
            print '*' * 21
            print 'in examplar',
            print hex(self.examplar.entry.TGI['t']),
            print hex(self.examplar.entry.TGI['g']),
            print hex(self.examplar.entry.TGI['i'])
            print 'located in',
            print self.examplar.entry.fileName
            print 'Prop ',
            print hex(self.id)
            print '*' * 49
            raise


class Examplar():

    def __init__(self, entry, virtualDAT):
        self.modified = False
        self.entry = entry
        self.virtualDAT = virtualDAT
        if entry:
            self.entry.virtualDAT = virtualDAT
            self.buffer = entry.content
        self.props = []
        self.parentCohort = (0, 0, 0)
        if entry:
            self.DecodeBuffer(False)
        self.buffer = None
        return

    def ReindexLotConfig(self, renum=False):
        lotObjects = []
        removeIds = []
        objectID = 0
        for id in range(2297284864L, 2297286144L):
            values = self.GetProp(id)
            if values != None:
                lotObjects.append(values[:])
                removeIds.append(id)

        for id in removeIds:
            self.RemoveProp(id)

        currentID = 2297284864L
        for v in lotObjects:
            if renum:
                v[11] = objectID
            self.AddTextProp(CreateAProp(self.virtualDAT.properties[currentID], v))
            objectID += 1
            currentID += 1

        return

    def free(self):
        self.virtualDAT = None
        for prop in self.props:
            prop.examplar = None

        self.entry = None
        return

    def AddBinaryProp(self, buffer):
        p = Prop(buffer, True, self)
        self.props.append(p)

    def AddTextProp(self, line):
        self.modified = True
        try:
            p = Prop(line, False, self)
        except:
            raise
            return False

        self.RemoveProp(p.id)
        self.props.append(p)
        self.props.sort(cmp=lambda x, y: cmp(x.id, y.id))
        return True

    def BinaryRep(self):
        if self.sig[0] == 'E':
            newBuff = 'EQZB1###'
        else:
            newBuff = 'CQZB1###'
        newBuff += struct.pack('III', self.parentCohort[0], self.parentCohort[1], self.parentCohort[2])
        self.nbrProp = len(self.props)
        newBuff += struct.pack('I', self.nbrProp)
        self.props.sort(cmp=lambda p1, p2: cmp(p1.id, p2.id))
        for p in self.props:
            rep = p.BinaryRep()
            newBuff += rep

        return newBuff

    def DecodeBinary(self, bLazy=True):
        global binEx
        binEx += 1
        buf = io.BytesIO(self.buffer)
        self.sig = buf.read(8)
        self.parentCohort = tuple(struct.unpack('III', buf.read(12)))
        self.LinkToParent()
        self.nbrProp = struct.unpack('I', buf.read(4))[0]
        try:
            self.props = list(map(lambda x: Prop(buf, True, self), range(self.nbrProp)))
        except:
            raise

    def DecodeBuffer(self, bLazy=True):
        self.props = []
        if self.buffer[:4] == 'CQZB':
            self.DecodeBinary(bLazy)
        elif self.buffer[:4] == 'EQZB':
            self.DecodeBinary(bLazy)
        elif self.buffer[:4] == 'EQZT':
            self.DecodeText(bLazy)
        elif self.buffer[:4] == 'CQZT':
            self.DecodeText(bLazy)

    def DecodeText(self, bLazy=True):
        global textEx
        textEx += 1
        lines = self.buffer.split('\r\n')
        self.sig = lines[0]
        l = lines[1].find('{')
        lines[1] = lines[1][l + 1:-1]
        self.parentCohort = tuple([ int(x, 16) for x in lines[1].split(',') ])
        self.LinkToParent()
        self.nbrProp = int(lines[2].split('=')[1], 16)
        lines = lines[3:]
        self.props = []
        for x in lines:
            if x is not '':
                try:
                    prop = Prop(x, False, self)
                    self.props.append(prop)
                except:
                    pass

    def FlattenProps(self):
        raise NotImplemented

    def GetPropObject(self, key):
        for p in self.props:
            if p.id == key:
                return p

        if self.link is not None:
            return self.link.examplar.GetPropObject(key)
        return

    def GetProp(self, key):
        for p in self.props:
            if p.id == key:
                return p.values

        if self.link is not None:
            return self.link.examplar.GetProp(key)
        return

    def LinkToParent(self):
        self.link = None
        if self.parentCohort != (0, 0, 0):
            if self.parentCohort[0] != 87304289:
                self.parentCohort = (
                 self.parentCohort[2], self.parentCohort[0], self.parentCohort[1])
            self.link = self.virtualDAT.getEntry(self.parentCohort[0], self.parentCohort[1], self.parentCohort[2])
            if self.link is not None:
                if 'examplar' not in self.link.__dict__:
                    print 'require a cohort 0x%08X 0x%08X 0x%08X' % (self.parentCohort[0], self.parentCohort[1], self.parentCohort[2])
                    self.link.ReadFile(None, True, True)
                    cohort = Examplar(self.link, self.virtualDAT)
                    self.link.examplar = cohort
                    self.link.rawContent = None
                    self.link.content = None
        return

    def Maj(self):
        self.modified = False
        if self.sig[3] == 'T':
            self.buffer = self.TextRep()
        else:
            self.buffer = self.BinaryRep()
        self.entry.content = self.buffer
        self.entry.Maj()

    def RemoveProp(self, k):
        try:
            for p in self.props:
                if p.id == k:
                    self.props.remove(p)
                    self.modified = True
                    break

        except:
            pass

    def Rep(self):
        if self.sig[3] == 'T':
            return self.TextRep()
        else:
            return self.BinaryRep()

    def Reread(self):
        self.modified = False
        if self.entry:
            self.entry.ReadFile(None, True, True)
            self.buffer = self.entry.content
        self.props = []
        self.parentCohort = (0, 0, 0)
        if self.entry:
            self.DecodeBuffer(False)
        self.buffer = None
        return

    def SetProp(self, key, values):
        raise NotImplemented

    def TextRep(self):
        lines = []
        if self.sig[0] == 'E':
            newBuff = 'EQZT1###'
        else:
            newBuff = 'CQZT1###'
        lines.append(newBuff)
        lines.append('ParentCohort=Key:{0x%08X,0x%08X,0x%08X}' % (self.parentCohort[0], self.parentCohort[1], self.parentCohort[2]))
        lines.append('PropCount=0x%08X' % len(self.props))
        self.props.sort(cmp=lambda p1, p2: cmp(p1.id, p2.id))
        for p in self.props:
            z = p.TextRep()
            if z.__class__ == unicode:
                print '*' * 10,
                print 'ERROR'
                print z
                print z.__class__
            lines.append(z)

        return '\r\n'.join(lines) + '\r\n'


def BuildSortedFilesList(folder, bRecurse=True):
    fileNames = []
    subFolders = []
    for root, dirs, files in os.walk(folder):
        for fileName in files:
            wx.Yield()
            fileNames.append(os.path.join(root, fileName))

        fileNames.sort(key=unicode.lower)
        if bRecurse:
            for subFolder in dirs:
                subFolders.append(os.path.join(root, subFolder))

            subFolders.sort(key=unicode.lower)
            for subFolder in subFolders:
                fileNames += BuildSortedFilesList(subFolder)

        break

    return fileNames


class SC4Entry():

    def __init__(self, buffer, idx, fileName):
        try:
            t, g, i, self.fileLocation, self.filesize = struct.unpack('LLLLL', buffer)
            self.compressed = False
            self.fileName = fileName
            self.buffer = buffer
            self.order = idx
            self.initialFileLocation = self.fileLocation
            self.lenContent = self.filesize
            self.order = idx
            self.TGI = {'t': t,'g': g,'i': i}
            self.tgi = (t, g, i)
            self.rawContent = None
            self.dateCreated = int(time.time())
            self.dateUpdated = int(time.time())
        except:
            print 'unexpectable error in',
            print fileName,
            print 'in the entry number',
            print idx
            raise

        return

    def ReadFile(self, sc4, readWhole=True, decompress=False):
        if self.rawContent != None:
            return False
        if self.tgi[0] == 1697917002 or self.tgi[0] == 87304289 or self.tgi[0] == 2289530369L:
            readWhole = True
            decompress = True
        if readWhole:
            self.compressed = False
            bClose = False
            if sc4 == None:
                bClose = True
                sc4 = open(self.fileName, 'rb')
            sc4.seek(self.initialFileLocation)
            self.rawContent = sc4.read(self.filesize)
            if len(self.rawContent) >= 8:
                compress_sig = struct.unpack('H', self.rawContent[4:4 + 2])[0]
                if compress_sig == COMPRESSED_SIG:
                    self.compressed = True
            if self.compressed:
                self.lenContent = -1
                uncompress = QFS.decode(self.rawContent[4:])
                if uncompress == None:
                    raise IOError
                self.lenContent = len(uncompress)
                self.content = uncompress
            else:
                self.content = self.rawContent
                self.lenContent = len(self.content)
            if bClose:
                sc4.close()
        return True

    def Maj(self):
        self.compressed = False
        self.rawContent = self.content
        self.lenContent = len(self.content)
        self.filesize = self.lenContent
        self.buffer = struct.pack('LLLLL', self.tgi[0], self.tgi[1], self.tgi[2], 0, self.filesize)

    def IsItThisTGI(self, tgi):
        return tgi[0] == self.TGI['t'] and tgi[1] == self.TGI['g'] and tgi[2] == self.TGI['i']


class DatFile():

    def __init__(self, fileName, dlg, lowerRam, bOnlyCohort=False):
        self.fileName = fileName
        self.entries = []
        self.cohorts = []
        try:
            self.sc4 = open(self.fileName, 'rb')
            self.ReadHeader(dlg)
            self.ReadEntries(bOnlyCohort, dlg, lowerRam)
        except IOError:
            if dlg:
                dlg.LogError('error in file: %s' % self.fileName)
        except:
            if dlg:
                dlg.LogError('Unknown error while reading SC4 file : %s' % self.fileName)
            raise

    def ReadHeader(self, dlg):
        self.header = self.sc4.read(96)
        if self.header[:4] != 'DBPF':
            if dlg:
                dlg.LogError('Not a valid SC4 file : %s' % self.fileName)
            raise IOError
        self.header = self.header[0:48] + '\x00' * 12 + self.header[48 + 12:96]
        header = io.BytesIO(self.header)
        header.read(4)
        try:
            self.fileVersionMajor = struct.unpack('l', header.read(4))[0]
            self.fileVersionMinor = struct.unpack('l', header.read(4))[0]
            header.read(12)
            self.dateCreated = struct.unpack('I', header.read(4))[0]
            self.dateUpdated = struct.unpack('I', header.read(4))[0]
            self.indexRecordType = struct.unpack('l', header.read(4))[0]
            self.dateLastAccess = os.stat(self.fileName)[-2]
            self.indexRecordEntryCount = struct.unpack('l', header.read(4))[0]
            self.indexRecordPosition = struct.unpack('l', header.read(4))[0]
            self.indexRecordLength = struct.unpack('l', header.read(4))[0]
            self.holeRecordEntryCount = struct.unpack('l', header.read(4))[0]
            self.holeRecordPosition = struct.unpack('l', header.read(4))[0]
            self.holeRecordLength = struct.unpack('l', header.read(4))[0]
        except struct.error:
            if dlg:
                dlg.LogError('Undecodable file : %s' % self.fileName)
            raise IOError

        header.close()

    def ReadEntries(self, bOnlyCohort, dlg, lowerRam):
        wx.Yield()
        self.sc4.seek(self.indexRecordPosition)
        header = io.BytesIO(self.sc4.read(self.indexRecordLength))
        dirEntry = None
        dictEntries = {}
        compressedIncluded = False
        try:
            entries = list(map(lambda idx: SC4Entry(header.read(20), idx, self.fileName), range(self.indexRecordEntryCount)))
        except:
            raise

        dirEntries = list(filter(lambda ent: ent.IsItThisTGI((3899334383, 3899334383, 678108931)), entries))
        if dirEntries != []:
            dirEntry = dirEntries[-1]
        for entry in entries:
            try:
                if dlg:
                    dlg.Increment()
                if entry.tgi in dictEntries:
                    continue
                else:
                    self.entries.append(entry)
                    entry.dateUpdated = self.dateLastAccess
                    dictEntries[entry.tgi] = entry
                    continue
            except IOError:
                if dlg:
                    dlg.LogError('Undecodable entry index %d in %s' % (entry.order, self.fileName))

        header.close()
        if dirEntry is not None:
            dirEntry.ReadFile(self.sc4, True, True)
            nbrCompressedEntries = dirEntry.filesize / 16
            for idx in range(nbrCompressedEntries):
                subBuf = dirEntry.rawContent[idx * 16:idx * 16 + 16]
                t, g, i, lenUncompressed = struct.unpack('LLLL', subBuf[0:0 + 16])
                try:
                    dictEntries[t, g, i].lenContent = lenUncompressed
                    dictEntries[t, g, i].compressed = True
                    continue
                except KeyError:
                    pass

        toBeRead = list(filter(lambda entry: entry.tgi[0] == 1697917002 or entry.tgi[0] == 87304289 or entry.tgi[0] == 2289530369, self.entries))
        temp = list(map(lambda entry: entry.ReadFile(self.sc4, True, True), toBeRead))
        del temp
        del toBeRead
        del entries
        del dictEntries
        self.sc4.close()
        return


def GenerateDirectory(allEntries, fileName):
    nbrCompressed = 0
    for entry in allEntries:
        if entry.compressed:
            nbrCompressed += 1

    if nbrCompressed == 0:
        return None
    header = struct.pack('I', 3899334383L)
    header += struct.pack('I', 3899334383L)
    header += struct.pack('I', 678108931)
    header += struct.pack('I', 0)
    header += struct.pack('I', 16 * nbrCompressed)
    dirEnt = SC4Entry(header, 0, fileName)
    buffer = ''
    for entry in allEntries:
        if entry.compressed:
            buffer += entry.buffer[0:12]
            buffer += struct.pack('I', entry.lenContent)

    dirEnt.rawContent = buffer
    dirEnt.lenContent = len(dirEnt.rawContent)
    return dirEnt


def WriteADat(fileName, allEntries, dlg, bRecompress):
    if dlg:
        dlg.SetTitle('Compacting mega pack')
    withoutDir = []
    if dlg:
        dlg.labelg2.SetLabel('Generating directory of ' + fileName)
    if dlg:
        dlg.g2.SetRange(len(allEntries))
    for i, entry in enumerate(allEntries):
        if dlg:
            dlg.g2.SetValue(i)
        wx.Yield()
        if entry.tgi == (3899334383L, 3899334383L, 678108931):
            pass
        else:
            if bRecompress and not entry.compressed:
                if entry.rawContent == None:
                    sc4In = open(entry.fileName, 'rb')
                    entry.ReadFile(sc4In)
                    sc4In.close()
            if bRecompress and not entry.compressed and len(entry.rawContent) > 600:
                compression = QFS.encode(entry.rawContent)
                if len(compression) < len(entry.rawContent) and len(compression) > 0:
                    compression = struct.pack('l', len(compression)) + compression
                    entry.filesize = len(compression)
                    entry.rawContent = compression
                    entry.buffer = entry.buffer[:16] + struct.pack('I', entry.filesize) + entry.buffer[16 + 4:]
                    entry.compressed = True
            withoutDir.append(entry)

    allEntries = withoutDir

    def CompEnt(a, b):
        if a.tgi[0] == b.tgi[0]:
            if a.tgi[1] == b.tgi[1]:
                return cmp(a.tgi[2], b.tgi[2])
            else:
                return cmp(a.tgi[1], b.tgi[1])
        else:
            return cmp(a.tgi[0], b.tgi[0])

    dirEnt = GenerateDirectory(allEntries, fileName)
    if dirEnt is not None:
        allEntries.append(dirEnt)
    indexRecordPosition = 0
    indexRecordEntryCount = len(allEntries)
    indexRecordLength = indexRecordEntryCount * 20
    dateCreated = int(time.time())
    dateUpdated = int(time.time())
    fileVersionMajor = 1
    fileVersionMinor = 0
    indexRecordType = 7
    header = '\x00' * 96
    header = 'DBPF' + header[4:]
    header = header[:4] + struct.pack('l', fileVersionMajor) + header[4 + 4:]
    header = header[:8] + struct.pack('l', fileVersionMinor) + header[8 + 4:]
    header = header[:24] + struct.pack('I', dateCreated) + header[24 + 4:]
    header = header[:28] + struct.pack('I', dateUpdated) + header[28 + 4:]
    header = header[:32] + struct.pack('l', indexRecordType) + header[32 + 4:]
    header = header[:36] + struct.pack('I', indexRecordEntryCount) + header[36 + 4:]
    header = header[:40] + struct.pack('I', indexRecordPosition) + header[40 + 4:]
    header = header[:44] + struct.pack('I', indexRecordLength) + header[44 + 4:]
    pos = 96
    if dlg:
        dlg.labelg2.SetLabel('computing entries index of ' + fileName)
    if dlg:
        dlg.g2.SetRange(len(allEntries))
    for i, entry in enumerate(allEntries):
        if dlg:
            dlg.g2.SetValue(i)
        wx.Yield()
        entry.fileLocation = pos
        entry.initialFileLocation = entry.fileLocation
        newbuffer = entry.buffer[0:12] + struct.pack('lI', entry.fileLocation, entry.filesize) + entry.buffer[12 + 8:]
        entry.buffer = newbuffer
        pos += entry.filesize
        if entry.filesize == 0:
            print '*' * 20
            print 'In file', entry.fileName
            print 'Warning : Entry', hex2str(entry.tgi[0]), hex2str(entry.tgi[1]), hex2str(entry.tgi[2]),
            if entry.compressed:
                print '(compressed)',
            else:
                print '(uncompressed)',
            print 'has a 0 size len'
        if dlg:
            dlg.LOG('write;%d;0x%08X;0x%08X;0x%08X;%s;%s' % (i, entry.tgi[0], entry.tgi[1], entry.tgi[2], entry.fileName, fileName))

    indexRecordPosition = pos
    header = header[:40] + struct.pack('I', indexRecordPosition) + header[40 + 4:]
    sc4 = open(fileName, 'wb')
    sc4.write(header)
    if dlg:
        dlg.labelg2.SetLabel('writing all entries to ' + fileName)
    if dlg:
        dlg.g2.SetRange(len(allEntries))
    for i, entry in enumerate(allEntries):
        if dlg:
            dlg.g2.SetValue(i)
        wx.Yield()
        if entry.rawContent == None:
            sc4In = open(entry.fileName, 'rb')
            entry.ReadFile(sc4In)
            sc4In.close()
        sc4.write(entry.rawContent)

    for entry in allEntries:
        sc4.write(entry.buffer)
        entry.content = None
        entry.rawContent = None

    sc4.close()
    return


def breadthFirstFileScan(root, bRecurse=True):
    dirs = [root]
    while len(dirs):
        nextDirs = []
        for parent in dirs:
            for f in os.listdir(parent):
                ff = os.path.join(parent, f)
                if os.path.isdir(ff):
                    if bRecurse:
                        nextDirs.append(ff)
                else:
                    yield ff

        dirs = nextDirs
# okay decompiling SC4DatTools.pyo
