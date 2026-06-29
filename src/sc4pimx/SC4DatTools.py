"""SC4 DAT file parsing and manipulation tools.

This module provides classes and functions for reading, parsing, and writing
SimCity 4 .dat files, including compressed entries and property handling.
"""
import io
import logging
import os
import os.path
import re
import struct
import time

import wx

from . import QFS
from .translation import compactingMegaPackMsg, genDirectoryMsg

logger = logging.getLogger(__name__)

binEx = 0
textEx = 0
binProp = 0

# Sentinel for Prop(..., kind=...): lets callers pass the exemplar's already
# resolved ExemplarType (property 16) so each Prop need not re-resolve it.
_KIND_UNSET = object()


def format_float_value(v):
    """Format a Float32 property value for display.

    Uses 8 decimal places (the editor's serialisation precision) then strips
    redundant trailing zeros, keeping one digit after the dot so the value
    still reads as a float. Small values keep their significant digits
    (0.0067), large values lose the noise (22500.0), no scientific notation.
    """
    s = ('%.8f' % v).rstrip('0')
    if s.endswith('.'):
        s += '0'
    return s


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
translationTable = bytes([35] * 32 + list(range(32, 128)) + [35] * 128)

def InfoEx():
    pass


def hex2str(v, size=32, upper=False):
    # ``upper`` capitalises the hex digits (not the ``0x`` prefix) for display;
    # it is opt-in so the default lower-case form used in saved/round-tripped
    # values is unchanged.
    x = 'X' if upper else 'x'
    if v >= 0:
        if size == 8:
            return ('0x%02' + x) % int(v)
        elif size == 32:
            return ('0x%08' + x) % int(v)
        else:
            return ('0x%016' + x) % int(v)
    elif size == 32:
        return ('0x%08' + x) % (int(v) & 0xFFFFFFFF)
    elif size == 8:
        return ('0x%02' + x) % (int(v) & 0xFF)
    else:
        return ('0x%016' + x) % (int(v) & 0xFFFFFFFFFFFFFFFF)


class Prop():
    # __slots__ avoids per-instance __dict__: at warm-start scale we create
    # ~440k Props during Finalize, and the dict overhead alone was a
    # measurable chunk of that time. All attributes ever written by any
    # code path (binary parser, text parser, and external mutators) must be
    # listed here. Conditionally-set attributes (``rawdata`` for string
    # props, ``named`` for text-parsed props) are still legal to leave unset
    # -- ``hasattr`` checks behave the same with slots.
    __slots__ = ('exemplar', 'id', 'values', 'typeValue', 'sizeOfCounter',
                 'count', 'rawdata', 'sized', 'named')

    validFormat = {1792: 'i',2304: 'f',768: 'I',2816: 'b',256: 'B',2048: 'q',512: 'h'}
    format2String = {768: 'Uint32',3072: 'String',2304: 'Float32',2816: 'Bool',256: 'Uint8',2048: 'Sint64',1792: 'Sint32'}

    def __init__(self, line, binary, exemplar, initPos=0, kind=_KIND_UNSET):
        global binProp
        self.exemplar = exemplar
        # ExemplarType (prop 16) is identical for every prop of an exemplar;
        # callers decoding a whole exemplar pass it in so it is resolved once
        # instead of once per prop (a linear scan, often into the parent
        # cohort -- previously O(nbrProp) wasted work per exemplar).
        if kind is _KIND_UNSET:
            kind = exemplar.GetProp(16)
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
                tt = line.read(strlen)
                self.rawdata = tt
                txtConv = tt.translate(translationTable).decode("latin-1")
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
                if self.typeValue not in Prop.validFormat:
                    logger.error('Unknown prop type in exemplar 0x%X-0x%X-0x%X located in %s',
                                 self.exemplar.entry.TGI['t'], self.exemplar.entry.TGI['g'],
                                 self.exemplar.entry.TGI['i'], self.exemplar.entry.fileName)
                s = struct.calcsize(Prop.validFormat[self.typeValue] * nbr)
                self.values = list(struct.unpack(Prop.validFormat[self.typeValue] * nbr, line.read(s)))
                count += 1 + s + offset
            self.sized = count
        else:
            try:
                initialLine = line[:]
                self.values = []
                comp = line.split('"')
                IID = hex(self.exemplar.entry.TGI['i'])
                comp[1] = comp[1].replace(':', '_')
                line = '"'.join(comp)
                if line[-1] == ' ':
                    line = line[:-1]
                # Limit the split so colons inside the value section -- e.g.
                # sc4pac-style labelled values "{Width: 0}" or strings that
                # contain ':' -- aren't mistaken for field separators.
                fields = line.split(':', 3)

                def stripLabel(token):
                    # Labelled text exemplars write each value as "Name: x";
                    # keep only the value part. Plain "0", "0x0A" pass through.
                    token = token.strip()
                    if ':' in token:
                        token = token.rsplit(':', 1)[-1].strip()
                    return token

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
                        if stripLabel(v) == 'True':
                            self.values.append(True)
                        else:
                            self.values.append(False)

                else:
                    if tv == 'String':
                        tt = fields[3][2:-2]
                        self.rawdata = tt
                        txtConv = tt.encode("latin-1", errors="replace").translate(translationTable).decode("latin-1")
                        self.values = [txtConv]
                    elif tv == 'Float32':
                        if fields[3][1:-1].split(',') != ['']:
                            self.values = [ float(stripLabel(x)) for x in fields[3][1:-1].split(',') ]
                    elif fields[3][1:-1].split(',') != ['']:

                        def convH(s):
                            mul = 1
                            if s[0] == '-':
                                mul = -1
                                s = s[1:]
                            is_hex = len(s) > 2 and s[1].upper() == 'X'
                            try:
                                v = int(s, 16) if is_hex else int(s)
                            except ValueError:
                                is_hex = True
                                v = int(s, 16)

                            v *= mul
                            if self.typeValue == 768:
                                if v < 0:
                                    return 0
                                if v > 4294967295:
                                    return 4294967295
                            if self.typeValue == 1792:
                                if is_hex:
                                    v &= 0xFFFFFFFF
                                    if v >= 0x80000000:
                                        v -= 0x100000000
                                if v > 2147483647:
                                    return 2147483647
                                if v < -2147483648:
                                    return -2147483648
                            if self.typeValue == 2816:
                                if is_hex:
                                    v &= 0xFF
                                    if v >= 0x80:
                                        v -= 0x100
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

                        self.values = [ convH(stripLabel(x)) for x in fields[3][1:-1].split(',') ]
            except Exception:
                logger.exception('Error parsing exemplar 0x%X-0x%X-0x%X located in %s\n  line: %s',
                                 self.exemplar.entry.TGI['t'], self.exemplar.entry.TGI['g'],
                                 self.exemplar.entry.TGI['i'], self.exemplar.entry.fileName, initialLine)
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
            except Exception:
                logger.exception('Error in prop %s value %r type %s', hex2str(self.id), v, type(v))
                raise

        if self.typeValue == 3072:
            return v
        if self.typeValue == 2304:
            return format_float_value(v)
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
            ret += ':{"%s"}=' % self.exemplar.entry.virtual_dat.properties[self.id].Name
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
            if self.exemplar.entry.virtual_dat.properties[self.id].Count == 1:
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
                encoded = self.values[0].encode("latin-1", errors="replace")
                ret += struct.pack('I', len(encoded))
                ret += encoded
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
                    except Exception:
                        raise

            return ret
        except Exception:
            logger.exception('Error in exemplar 0x%X-0x%X-0x%X prop 0x%X located in %s',
                             self.exemplar.entry.TGI['t'], self.exemplar.entry.TGI['g'],
                             self.exemplar.entry.TGI['i'], self.id, self.exemplar.entry.fileName)
            raise


class SC4Exemplar():
    # Slotted for the same reason as Prop: ~67k SC4Exemplar instances are
    # created during a warm Finalize, and the per-instance __dict__ adds up.
    __slots__ = ('modified', 'entry', 'virtualDAT', 'buffer', 'props',
                 'parentCohort', 'sig', 'nbrProp', 'link')

    def __init__(self, entry, virtualDAT):
        self.modified = False
        self.entry = entry
        self.virtualDAT = virtualDAT
        if entry:
            self.entry.virtual_dat = virtualDAT
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
        for id in range(2297284864, 2297286144):
            values = self.GetProp(id)
            if values is not None:
                lotObjects.append(values[:])
                removeIds.append(id)

        for id in removeIds:
            self.RemoveProp(id)

        currentID = 2297284864
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
            prop.exemplar = None

        self.entry = None
        return

    def AddBinaryProp(self, buffer):
        p = Prop(buffer, True, self)
        self.props.append(p)

    def AddTextProp(self, line):
        self.modified = True
        try:
            p = Prop(line, False, self)
        except Exception:
            raise
            return False

        self.RemoveProp(p.id)
        self.props.append(p)
        self.props.sort(key=lambda p: p.id)
        return True

    def BinaryRep(self):
        if self.sig[0] == 'E':
            newBuff = b'EQZB1###'
        else:
            newBuff = b'CQZB1###'
        newBuff += struct.pack('III', self.parentCohort[0], self.parentCohort[1], self.parentCohort[2])
        self.nbrProp = len(self.props)
        newBuff += struct.pack('I', self.nbrProp)
        self.props.sort(key=lambda p: p.id)
        for p in self.props:
            rep = p.BinaryRep()
            newBuff += rep

        return newBuff

    def DecodeBinary(self, bLazy=True):
        # Hot path: this runs ~67k times during a warm Finalize and parses
        # ~440k Prop records. The previous implementation wrapped the buffer
        # in a BytesIO and went through ``Prop.__init__`` via ``map(lambda
        # ...)``, paying file-like read() overhead and lambda dispatch per
        # prop. The rewrite below uses ``struct.unpack_from`` with a manual
        # offset cursor and bypasses ``Prop.__init__`` via ``Prop.__new__``.
        global binEx
        binEx += 1
        buf = self.buffer
        unpack_from = struct.unpack_from
        self.sig = bytes(buf[:8]).decode("latin-1")
        self.parentCohort = unpack_from('III', buf, 8)
        self.LinkToParent()
        nbrProp = unpack_from('I', buf, 20)[0]
        self.nbrProp = nbrProp
        # self.props is still empty here, so GetProp(16) resolves via the
        # parent cohort -- exactly what each Prop would compute individually.
        kind = self.GetProp(16)
        if kind is not None and kind[0] not in (30, 2, 17, 15, 16):
            # Whole-exemplar skip: every Prop would no-op with id=0 anyway.
            # Synthesise minimal stubs without parsing the buffer.
            stubs = [None] * nbrProp
            new_prop = Prop.__new__
            for i in range(nbrProp):
                p = new_prop(Prop)
                p.exemplar = self
                p.id = 0
                stubs[i] = p
            self.props = stubs
            return
        pos = 24
        props = [None] * nbrProp
        valid_format = Prop.validFormat
        calcsize = struct.calcsize
        new_prop = Prop.__new__
        translate = translationTable
        for i in range(nbrProp):
            p = new_prop(Prop)
            p.exemplar = self
            prop_id, type_value, size_of_counter = unpack_from('IHH', buf, pos)
            p.id = prop_id
            p.typeValue = type_value
            p.sizeOfCounter = size_of_counter
            pos += 8
            if type_value == 3072:
                # String: 1B subcount, 4B length, then raw bytes.
                p.count = buf[pos]
                strlen = unpack_from('I', buf, pos + 1)[0]
                tt = bytes(buf[pos + 5:pos + 5 + strlen])
                p.rawdata = tt
                p.values = [tt.translate(translate).decode("latin-1")]
                pos += 1 + 4 + strlen
            else:
                if size_of_counter > 0:
                    # padding + count uint16 + padding
                    p.count = unpack_from('H', buf, pos + 1)[0]
                    pos += 5
                else:
                    p.count = buf[pos]
                    pos += 1
                nbr = p.count
                if nbr == 0 and size_of_counter == 0:
                    nbr = 1
                fmt = valid_format.get(type_value)
                if fmt is None:
                    logger.error('Unknown prop type in exemplar 0x%X-0x%X-0x%X located in %s',
                                 self.entry.TGI['t'], self.entry.TGI['g'],
                                 self.entry.TGI['i'], self.entry.fileName)
                    p.values = []
                    props[i] = p
                    self.props = props[:i + 1]
                    return
                fmt_n = fmt * nbr
                s = calcsize(fmt_n)
                p.values = list(unpack_from(fmt_n, buf, pos))
                pos += s
            props[i] = p
        self.props = props

    def DecodeBuffer(self, bLazy=True):
        self.props = []
        magic = self.buffer[:4]
        if isinstance(magic, bytes):
            if magic in (b'CQZB', b'EQZB'):
                self.DecodeBinary(bLazy)
            elif magic in (b'EQZT', b'CQZT'):
                self.DecodeText(bLazy)
        else:
            if magic in ('CQZB', 'EQZB'):
                self.DecodeBinary(bLazy)
            elif magic in ('EQZT', 'CQZT'):
                self.DecodeText(bLazy)

    def DecodeText(self, bLazy=True):
        global textEx
        textEx += 1
        text = self.buffer
        if isinstance(text, (bytes, bytearray)):
            text = text.decode("latin-1", errors="replace")
        lines = text.split('\r\n')
        self.sig = lines[0]
        l = lines[1].find('{')
        lines[1] = lines[1][l + 1:-1]
        self.parentCohort = tuple([ int(x, 16) for x in lines[1].split(',') ])
        self.LinkToParent()
        self.nbrProp = int(lines[2].split('=')[1], 16)
        lines = lines[3:]
        self.props = []
        for x in lines:
            if x != '':
                try:
                    prop = Prop(x, False, self)
                    self.props.append(prop)
                except Exception:
                    pass

    def FlattenProps(self):
        raise NotImplementedError

    def GetPropObject(self, key):
        for p in self.props:
            if p.id == key:
                return p

        if self.link is not None:
            return self.link.exemplar.GetPropObject(key)
        return

    def GetProp(self, key):
        for p in self.props:
            if p.id == key:
                return p.values

        if self.link is not None:
            return self.link.exemplar.GetProp(key)
        return

    def GetPropRange(self, lo, hi):
        """One-pass {id: values} for property ids in [lo, hi).

        Honors the parent-cohort link exactly like GetProp (a child prop
        overrides the inherited one). Callers that read a contiguous block of
        ids — e.g. the 1280 lot-config-property slots — can resolve every slot
        in O(props) instead of an O(N) GetProp scan per slot (O(N^2) overall).
        """
        result = {}
        ex = self
        seen = set()
        while ex is not None:
            for p in ex.props:
                if lo <= p.id < hi and p.id not in result:
                    result[p.id] = p.values
            link = ex.link
            if link is None or id(link) in seen:
                break
            seen.add(id(link))
            ex = getattr(link, 'exemplar', None)
        return result

    def LinkToParent(self):
        self.link = None
        if self.parentCohort != (0, 0, 0):
            if self.parentCohort[0] != 87304289:
                self.parentCohort = (
                 self.parentCohort[2], self.parentCohort[0], self.parentCohort[1])
            self.link = self.virtualDAT.getEntry(self.parentCohort[0], self.parentCohort[1], self.parentCohort[2])
            if self.link is not None:
                if 'exemplar' not in self.link.__dict__:
                    logger.debug('Loading required cohort 0x%08X 0x%08X 0x%08X',
                                 self.parentCohort[0], self.parentCohort[1], self.parentCohort[2])
                    self.link.read_file(None, True, True)
                    cohort = SC4Exemplar(self.link, self.virtualDAT)
                    self.link.exemplar = cohort
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

        except Exception:
            pass

    def Rep(self):
        if self.sig[3] == 'T':
            return self.TextRep()
        else:
            return self.BinaryRep()

    def Reread(self):
        self.modified = False
        if self.entry:
            self.entry.read_file(None, True, True)
            self.buffer = self.entry.content
        self.props = []
        self.parentCohort = (0, 0, 0)
        if self.entry:
            self.DecodeBuffer(False)
        self.buffer = None
        return

    def SetProp(self, key, values):
        raise NotImplementedError

    def TextRep(self):
        lines = []
        if self.sig[0] == 'E':
            newBuff = 'EQZT1###'
        else:
            newBuff = 'CQZT1###'
        lines.append(newBuff)
        lines.append('ParentCohort=Key:{0x%08X,0x%08X,0x%08X}' % (self.parentCohort[0], self.parentCohort[1], self.parentCohort[2]))
        lines.append('PropCount=0x%08X' % len(self.props))
        self.props.sort(key=lambda p: p.id)
        for p in self.props:
            lines.append(p.TextRep())

        return ('\r\n'.join(lines) + '\r\n').encode("latin-1", errors="replace")


def BuildSortedFilesList(folder, bRecurse=True):
    fileNames = []
    subFolders = []
    # NB: no wx calls here -- this runs on the background loader thread.
    for root, dirs, files in os.walk(folder):
        for fileName in files:
            fileNames.append(os.path.join(root, fileName))

        fileNames.sort(key=str.lower)
        if bRecurse:
            for subFolder in dirs:
                subFolders.append(os.path.join(root, subFolder))

            subFolders.sort(key=str.lower)
            for subFolder in subFolders:
                fileNames += BuildSortedFilesList(subFolder)

        break

    return fileNames


class SC4Entry():

    def __init__(self, buffer, idx, fileName):
        try:
            t, g, i, self.fileLocation, self.filesize = struct.unpack('<IIIII', buffer)
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
        except Exception as exc:
            # Logged as debug only; the caller logs a single warning per file.
            logger.debug('Unreadable entry %s in %s: %s', idx, fileName, exc)
            raise

        return

    def read_file(self, sc4, readWhole=True, decompress=False):
        if self.rawContent is not None:
            return False
        if self.tgi[0] == 1697917002 or self.tgi[0] == 87304289 or self.tgi[0] == 2289530369:
            readWhole = True
            decompress = True
        if readWhole:
            self.compressed = False
            bClose = False
            if sc4 is None:
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
                if uncompress is None:
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
        content = self.content
        if isinstance(content, str):
            content = content.encode("latin-1", errors="replace")
        self.rawContent = content
        self.lenContent = len(content)
        self.filesize = self.lenContent
        self.buffer = struct.pack('<IIIII', self.tgi[0], self.tgi[1], self.tgi[2], 0, self.filesize)

    def IsItThisTGI(self, tgi):
        return tgi[0] == self.TGI['t'] and tgi[1] == self.TGI['g'] and tgi[2] == self.TGI['i']


class DatFile():

    def __init__(self, fileName, dlg, lowerRam, bOnlyCohort=False):
        self.fileName = fileName
        self.entries = []
        self.cohorts = []
        self.sc4 = None
        try:
            self.sc4 = open(self.fileName, 'rb')
            self.ReadHeader(dlg)
            self.ReadEntries(bOnlyCohort, dlg, lowerRam)
        except IOError:
            if dlg:
                dlg.LogError('error in file: %s' % self.fileName)
        except Exception:
            if dlg:
                dlg.LogError('Unknown error while reading SC4 file : %s' % self.fileName)
            raise
        finally:
            if self.sc4 is not None:
                try:
                    self.sc4.close()
                except Exception:
                    pass

    def ReadHeader(self, dlg):
        self.header = self.sc4.read(96)
        if self.header[:4] != b'DBPF':
            if dlg:
                dlg.LogError('Not a valid SC4 file : %s' % self.fileName)
            raise IOError
        self.header = self.header[0:48] + b'\x00' * 12 + self.header[48 + 12:96]
        header = io.BytesIO(self.header)
        header.read(4)
        try:
            self.fileVersionMajor = struct.unpack('<i', header.read(4))[0]
            self.fileVersionMinor = struct.unpack('<i', header.read(4))[0]
            header.read(12)
            self.dateCreated = struct.unpack('<I', header.read(4))[0]
            self.dateUpdated = struct.unpack('<I', header.read(4))[0]
            self.indexRecordType = struct.unpack('<i', header.read(4))[0]
            self.dateLastAccess = os.stat(self.fileName)[-2]
            self.indexRecordEntryCount = struct.unpack('<i', header.read(4))[0]
            self.indexRecordPosition = struct.unpack('<i', header.read(4))[0]
            self.indexRecordLength = struct.unpack('<i', header.read(4))[0]
            self.holeRecordEntryCount = struct.unpack('<i', header.read(4))[0]
            self.holeRecordPosition = struct.unpack('<i', header.read(4))[0]
            self.holeRecordLength = struct.unpack('<i', header.read(4))[0]
        except struct.error:
            if dlg:
                dlg.LogError('Undecodable file : %s' % self.fileName)
            raise IOError

        header.close()

    def ReadEntries(self, bOnlyCohort, dlg, lowerRam):
        # NB: no wx calls here -- this runs inside background worker threads.
        self.sc4.seek(self.indexRecordPosition)
        header = io.BytesIO(self.sc4.read(self.indexRecordLength))
        dirEntry = None
        dictEntries = {}
        compressedIncluded = False
        try:
            entries = list(map(lambda idx: SC4Entry(header.read(20), idx, self.fileName), range(self.indexRecordEntryCount)))
        except Exception:
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
            dirEntry.read_file(self.sc4, True, True)
            nbrCompressedEntries = dirEntry.filesize // 16
            for idx in range(nbrCompressedEntries):
                subBuf = dirEntry.rawContent[idx * 16:idx * 16 + 16]
                t, g, i, lenUncompressed = struct.unpack('<IIII', subBuf[0:0 + 16])
                try:
                    dictEntries[t, g, i].lenContent = lenUncompressed
                    dictEntries[t, g, i].compressed = True
                    continue
                except KeyError:
                    pass

        toBeRead = list(filter(lambda entry: entry.tgi[0] == 1697917002 or entry.tgi[0] == 87304289 or entry.tgi[0] == 2289530369, self.entries))
        temp = list(map(lambda entry: entry.read_file(self.sc4, True, True), toBeRead))
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
    header = struct.pack('I', 3899334383)
    header += struct.pack('I', 3899334383)
    header += struct.pack('I', 678108931)
    header += struct.pack('I', 0)
    header += struct.pack('I', 16 * nbrCompressed)
    dirEnt = SC4Entry(header, 0, fileName)
    buffer = b''
    for entry in allEntries:
        if entry.compressed:
            buffer += entry.buffer[0:12]
            buffer += struct.pack('I', entry.lenContent)

    dirEnt.rawContent = buffer
    dirEnt.lenContent = len(dirEnt.rawContent)
    return dirEnt


def WriteADat(fileName, allEntries, dlg, bRecompress):
    if dlg:
        dlg.SetTitle(compactingMegaPackMsg)
    withoutDir = []
    if dlg:
        dlg.labelg2.SetLabel(genDirectoryMsg % fileName)
    if dlg:
        dlg.g2.SetRange(len(allEntries))
    for i, entry in enumerate(allEntries):
        if dlg:
            dlg.g2.SetValue(i)
        wx.Yield()
        if entry.tgi == (3899334383, 3899334383, 678108931):
            pass
        else:
            if bRecompress and not entry.compressed:
                if entry.rawContent is None:
                    sc4In = open(entry.fileName, 'rb')
                    entry.read_file(sc4In)
                    sc4In.close()
            if bRecompress and not entry.compressed and len(entry.rawContent) > 600:
                compression = QFS.encode(entry.rawContent)
                if compression and len(compression) < len(entry.rawContent):
                    compression = struct.pack('<i', len(compression)) + compression
                    entry.filesize = len(compression)
                    entry.rawContent = compression
                    entry.buffer = entry.buffer[:16] + struct.pack('I', entry.filesize) + entry.buffer[16 + 4:]
                    entry.compressed = True
            withoutDir.append(entry)

    allEntries = withoutDir

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
    header = b'\x00' * 96
    header = b'DBPF' + header[4:]
    header = header[:4] + struct.pack('<i', fileVersionMajor) + header[4 + 4:]
    header = header[:8] + struct.pack('<i', fileVersionMinor) + header[8 + 4:]
    header = header[:24] + struct.pack('I', dateCreated) + header[24 + 4:]
    header = header[:28] + struct.pack('I', dateUpdated) + header[28 + 4:]
    header = header[:32] + struct.pack('<i', indexRecordType) + header[32 + 4:]
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
        newbuffer = entry.buffer[0:12] + struct.pack('<II', entry.fileLocation, entry.filesize) + entry.buffer[12 + 8:]
        entry.buffer = newbuffer
        pos += entry.filesize
        if entry.filesize == 0:
            logger.warning('Entry %s-%s-%s (%s) has a 0 size len in file %s',
                           hex2str(entry.tgi[0]), hex2str(entry.tgi[1]), hex2str(entry.tgi[2]),
                           'compressed' if entry.compressed else 'uncompressed', entry.fileName)
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
        if entry.rawContent is None:
            sc4In = open(entry.fileName, 'rb')
            entry.read_file(sc4In)
            sc4In.close()
        raw = entry.rawContent
        if isinstance(raw, str):
            raw = raw.encode("latin-1", errors="replace")
        sc4.write(raw)

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
