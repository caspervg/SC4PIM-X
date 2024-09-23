# uncompyle6 version 2.11.5
# Python bytecode 2.4 (62061)
# Decompiled from: Python 2.7.18 (default, Oct 15 2023, 16:43:11) 
# [GCC 11.4.0]
# Embedded file name: ATCReader.pyo
# Compiled at: 2008-04-07 22:32:26
from SC4Data import *
from SC4OpenGL import *
import struct
import wx
import Image
import ImageChops
import FSHConverter

class ATC(object):

    def __init__(self, entry, virtualDAT):
        self.entry = entry
        if entry == None:
            return
        self.tgi = entry.tgi
        self.virtualDAT = virtualDAT
        self.currentFrame = 0
        return

    def ReadFile(self):
        if hasattr(self, 'fshTGI'):
            return
        if self.entry == None:
            return
        entry = self.entry
        entry.ReadFile(None, True, True)
        buffer = entry.content
        self.type = struct.unpack('I', buffer[0:4])[0]
        self.fshTGI = struct.unpack('III', buffer[4:16])
        self.avpTID = struct.unpack('I', buffer[16:20])[0]
        self.avpGID = struct.unpack('I', buffer[20:24])[0]
        self.avpIIDs = struct.unpack('IIIII', buffer[24:44])
        self.nbrFrames = struct.unpack('I', buffer[44:48])[0]
        buffer = None
        del buffer
        entry.content = None
        entry.rawContent = None
        return

    def Free3D(self, s3DTexturesHolder):
        s3DTexturesHolder.Free()

    def Initialize(self, virtualDAT, viewer):
        self.PreLoad(virtualDAT, viewer.s3DTexturesHolder)

    def PreLoad(self, virtualDAT, s3DTexturesHolder):
        self.ReadFile()
        fshEntry = virtualDAT.getEntry(self.fshTGI[0], self.fshTGI[1], self.fshTGI[2])
        s3DTexturesHolder.PrecacheTex((self.fshTGI[1], self.fshTGI[2]), fshEntry)
        if fshEntry:
            self.avps = []
            for avpID in self.avpIIDs:
                if avpID == 0:
                    self.avps.append(None)
                else:
                    self.avps.append(AVP(virtualDAT.getEntry(self.avpTID, self.avpGID, avpID), 256))

        return

    def Draw(self, viewer, staticFileName, zoom, rot, state=0):
        if zoom == -1:
            viewer.useBestFit = True
            zoom = 4
        else:
            viewer.useBestFit = False
        if 'avps' not in self.__dict__:
            self.Initialize(self.virtualDAT, viewer)
        if 'avps' not in self.__dict__:
            return None
        if self.DrawLE(zoom, rot):
            viewer.S3DMesh = self
            viewer.Reinit()
            viewer.Refresh(False)
        return None

    def DrawLE(self, zoom, rot):
        self.hotSpot = (0, 0)
        if zoom == -1:
            zoom = 4
        if 'avps' not in self.__dict__:
            return False
        if self.avps[zoom] == None:
            return False
        if self.avps[zoom].nbrViewPoint == 8:
            rot *= 2
        if rot >= len(self.avps[zoom].chunks):
            return False
        self.currentFrame += 1
        if self.currentFrame == self.nbrFrames:
            self.currentFrame = 0
        avpData = self.avps[zoom].chunks[rot]
        self.hotSpot = avpData[3]
        self.currentLayer = avpData[0]
        size = (256, 256)
        self.quaduvsFrame0 = [avpData[1][0], avpData[1][1], avpData[1][0] + avpData[2][0], avpData[1][1] + avpData[2][1]]
        self.quaduvs = self.quaduvsFrame0
        for frame in xrange(self.currentFrame):
            self.quaduvs[0] += avpData[2][0]
            self.quaduvs[2] += avpData[2][0]
            if self.quaduvs[2] > size[0]:
                self.quaduvs[0] = 0
                self.quaduvs[2] = avpData[2][0]
                self.quaduvs[1] += avpData[2][1]
                self.quaduvs[3] += avpData[2][1]
                if self.quaduvs[3] > size[1]:
                    self.quaduvs[1] = 0
                    self.quaduvs[3] = avpData[2][1]
                    self.currentLayer += 1

        self.size = avpData[2]
        self.quaduvs = [float(self.quaduvs[0]) / size[0], float(self.quaduvs[1]) / size[1], float(self.quaduvs[2]) / size[0], float(self.quaduvs[3]) / size[1]]
        return True

    def DrawGL(self, s3DTexturesHolder):
        glTranslate(self.hotSpot[0], -self.hotSpot[1], 0)
        s3DTexturesHolder.SetCurrentTex((self.fshTGI[1], self.fshTGI[2]), self.currentLayer)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor3f(1.0, 1.0, 1.0)
        glBegin(GL_QUADS)
        glTexCoord2f(self.quaduvs[0], self.quaduvs[3])
        glVertex3f(-self.size[0] / 2, -self.size[1] / 2, 1)
        glTexCoord2f(self.quaduvs[0], self.quaduvs[1])
        glVertex3f(-self.size[0] / 2, self.size[1] / 2, 1)
        glTexCoord2f(self.quaduvs[2], self.quaduvs[1])
        glVertex3f(self.size[0] / 2, self.size[1] / 2, 1)
        glTexCoord2f(self.quaduvs[2], self.quaduvs[3])
        glVertex3f(self.size[0] / 2, -self.size[1] / 2, 1)
        glEnd()


class AVP(object):

    def __init__(self, entry, imageWidth):
        self.entry = entry
        if entry == None:
            return
        self.tgi = entry.tgi
        self.ReadFile(imageWidth)
        return

    def ReadFile(self, imageWidth):
        if self.entry == None:
            return
        entry = self.entry
        entry.ReadFile(None, True, True)
        buffer = entry.content
        self.magic = struct.unpack('I', buffer[0:4])[0]
        self.nbrViewPoint = struct.unpack('I', buffer[4:8])[0]
        self.majorVersion = struct.unpack('I', buffer[8:12])[0]
        self.minorVersion = struct.unpack('I', buffer[12:16])[0]
        self.reserved = struct.unpack('IIII', buffer[16:32])
        self.count = struct.unpack('I', buffer[32:36])[0]
        self.chunks = []
        buffer = buffer[36:]
        for x in xrange(self.count):
            plane = struct.unpack('B', buffer[0:1])[0]
            storageType = struct.unpack('B', buffer[1:2])[0]
            offset = struct.unpack('H', buffer[2:4])[0]
            xStart = offset % imageWidth
            yStart = offset / imageWidth
            width = struct.unpack('B', buffer[4:5])[0]
            height = struct.unpack('B', buffer[5:6])[0]
            hotSpotX = width / 2 - struct.unpack('B', buffer[6:7])[0]
            hotSpotY = height / 2 - struct.unpack('B', buffer[7:8])[0]
            self.chunks.append([plane, (xStart, yStart), (width, height), (hotSpotX, hotSpotY)])
            buffer = buffer[8:]

        buffer = None
        del buffer
        entry.content = None
        entry.rawContent = None
        return
# okay decompiling ATCReader.pyo
