"""S3D (SimCity 4 3D model) file reader."""
import struct

import numpy
import numpy as np
from OpenGL.GL import *  # noqa: F403  (GL names used in draw())

from .S3DViewer import *


class S3D(object):

    def __init__(self, entry):
        self.entry = entry
        if entry is None:
            return
        self.tgi = entry.tgi
        return

    def ReadFile(self):
        if hasattr(self, 'vertexBuffers'):
            return
        if self.entry is None:
            return
        entry = self.entry
        entry.read_file(None, True, True)
        buffer = entry.content
        if buffer[:4] != b'3DMD':
            print('not 3DMD')
            print(buffer[:4])
            buffer = None
            del buffer
            entry.content = None
            entry.rawContent = None
            self.entry = None
            raise IOError
        length = struct.unpack('I', buffer[4:8])[0]
        buffer = buffer[8:]
        buffer = self.ReadHead(buffer)
        buffer = self.ReadVert(buffer)
        buffer = self.ReadIndx(buffer)
        buffer = self.ReadPrim(buffer)
        buffer = self.ReadMats(buffer)
        buffer = self.ReadAnim(buffer)
        self.bboxX = self.maxx - self.minx
        self.bboxY = self.maxy - self.miny
        self.bboxZ = self.maxz - self.minz
        buffer = None
        del buffer
        entry.content = None
        entry.rawContent = None
        self.currentFrame = 0
        return

    def ReadHead(self, buffer):
        if buffer[:4] != b'HEAD':
            print('not head')
            raise IOError
        length = struct.unpack('I', buffer[4:8])[0]
        self.majorRevision = struct.unpack('H', buffer[8:10])[0]
        self.minorRevision = struct.unpack('H', buffer[10:12])[0]
        return buffer[12:]

    def ReadVert(self, buffer):
        if buffer[:4] != b'VERT':
            print('not vert')
            raise IOError
        length = struct.unpack('I', buffer[4:8])[0]
        nbrBlock = struct.unpack('I', buffer[8:12])[0]
        buffer = buffer[12:]
        self.vertexBuffers = []
        bounds_set = False
        for x in range(nbrBlock):
            vb = []
            flag = struct.unpack('H', buffer[0:2])[0]
            count = struct.unpack('H', buffer[2:4])[0]
            if self.minorRevision >= 4:
                format = struct.unpack('I', buffer[4:8])[0]
                if format & 2147483648 == 2147483648:
                    coordsNb = format & 3
                    colorsNb = (format & 384) >> 8
                    texsNb = (format & 49152) >> 14
                else:
                    if format == 1:
                        coordsNb = 1
                        colorsNb = 1
                        texsNb = 0
                    if format == 2:
                        coordsNb = 1
                        colorsNb = 0
                        texsNb = 1
                    if format == 3:
                        coordsNb = 1
                        colorsNb = 0
                        texsNb = 2
                    if format == 10:
                        coordsNb = 1
                        colorsNb = 1
                        texsNb = 1
                    if format == 11:
                        coordsNb = 1
                        colorsNb = 1
                        texsNb = 2
                vertexSize = 3 * 4 * coordsNb + 4 * colorsNb + 2 * 4 * texsNb
                stride = vertexSize
            else:
                format = struct.unpack('H', buffer[4:6])[0]
                stride = struct.unpack('H', buffer[6:8])[0]
                if format == 1:
                    coordsNb = 1
                    colorsNb = 1
                    texsNb = 0
                if format == 2:
                    coordsNb = 1
                    colorsNb = 0
                    texsNb = 1
                if format == 3:
                    coordsNb = 1
                    colorsNb = 0
                    texsNb = 2
                if format == 10:
                    coordsNb = 1
                    colorsNb = 1
                    texsNb = 1
                if format == 11:
                    coordsNb = 1
                    colorsNb = 1
                    texsNb = 2
                vertexSize = 3 * 4 * coordsNb + 4 * colorsNb + 2 * 4 * texsNb
            buffer = buffer[8:]
            # Vectorised vertex read: the old per-vertex struct.unpack loop
            # cost milliseconds per model. Slice the fixed-stride block with
            # numpy instead -- coords are the first 12 bytes of each vertex,
            # the UV pair the next 8.
            nbytes = count * stride
            arr = numpy.frombuffer(buffer[:nbytes], dtype=numpy.uint8).reshape(count, stride)
            buffer = buffer[nbytes:]
            vertices = numpy.ascontiguousarray(arr[:, 0:12]).view('<f4')
            if stride >= 20:
                uvs = numpy.ascontiguousarray(arr[:, 12:20]).view('<f4')
            else:
                uvs = numpy.zeros((count, 2), dtype=numpy.float32)
            if count:
                bmin = vertices.min(axis=0)
                bmax = vertices.max(axis=0)
                if not bounds_set:
                    self.minx, self.miny, self.minz = (float(bmin[0]), float(bmin[1]), float(bmin[2]))
                    self.maxx, self.maxy, self.maxz = (float(bmax[0]), float(bmax[1]), float(bmax[2]))
                    bounds_set = True
                else:
                    self.minx = min(self.minx, float(bmin[0]))
                    self.maxx = max(self.maxx, float(bmax[0]))
                    self.miny = min(self.miny, float(bmin[1]))
                    self.maxy = max(self.maxy, float(bmax[1]))
                    self.minz = min(self.minz, float(bmin[2]))
                    self.maxz = max(self.maxz, float(bmax[2]))
            self.vertexBuffers.append((vertices.tobytes(), uvs.tobytes()))

        if not bounds_set:
            self.minx = self.maxx = self.miny = self.maxy = self.minz = self.maxz = 0.0
        return buffer

    def ReadIndx(self, buffer):
        if buffer[:4] != b'INDX':
            print('not indx')
            raise IOError
        length = struct.unpack('I', buffer[4:8])[0]
        nbrBlock = struct.unpack('I', buffer[8:12])[0]
        buffer = buffer[12:]
        self.IndexBlocks = []
        for i in range(nbrBlock):
            flag = struct.unpack('H', buffer[0:2])[0]
            stride = struct.unpack('H', buffer[2:4])[0]
            count = struct.unpack('H', buffer[4:6])[0]
            buffer = buffer[6:]
            indices = struct.unpack('H' * count, buffer[:count * 2])
            idxs = np.asarray(indices, dtype=np.uint16)
            self.IndexBlocks.append((idxs.tobytes(), count))
            buffer = buffer[count * 2:]

        return buffer

    def ReadPrim(self, buffer):
        if buffer[:4] != b'PRIM':
            print('not PRIM')
            raise IOError
        length = struct.unpack('I', buffer[4:8])[0]
        nbrBlock = struct.unpack('I', buffer[8:12])[0]
        buffer = buffer[12:]
        self.primBlocks = []
        for bloc in range(nbrBlock):
            nbrPrims = struct.unpack('H', buffer[0:2])[0]
            buffer = buffer[2:]
            subprims = []
            for prim in range(nbrPrims):
                typePrim = struct.unpack('I', buffer[0:4])[0]
                first = struct.unpack('I', buffer[4:8])[0]
                length = struct.unpack('I', buffer[8:12])[0]
                subprims.append((typePrim, first, length))
                buffer = buffer[12:]

            self.primBlocks.append(subprims)

        return buffer

    def ReadMats(self, buffer):
        if buffer[:4] != b'MATS':
            print('not MATS')
            raise IOError
        length = struct.unpack('I', buffer[4:8])[0]
        nbrBlock = struct.unpack('I', buffer[8:12])[0]
        buffer = buffer[12:]
        self.matBlocks = []
        for matNb in range(nbrBlock):
            flags = struct.unpack('I', buffer[0:4])[0]
            alphaFunc = struct.unpack('B', buffer[4:5])[0]
            depthFunc = struct.unpack('B', buffer[5:6])[0]
            srcBlend = struct.unpack('B', buffer[6:7])[0]
            dstBlend = struct.unpack('B', buffer[7:8])[0]
            alphaThreshold = float(struct.unpack('H', buffer[8:10])[0]) / 65535
            materialClass = struct.unpack('I', buffer[10:14])[0]
            reserved = struct.unpack('B', buffer[14:15])[0]
            textureCount = struct.unpack('B', buffer[15:16])[0]
            buffer = buffer[16:]
            textures = []
            for tex in range(textureCount):
                magFilter = 0
                minFilter = 0
                textureID = struct.unpack('I', buffer[:4])[0]
                wrapS = struct.unpack('B', buffer[4:5])[0]
                wrapT = struct.unpack('B', buffer[5:6])[0]
                buffer = buffer[6:]
                if self.minorRevision == 5:
                    magFilter = struct.unpack('B', buffer[:1])[0]
                    minFilter = struct.unpack('B', buffer[1:2])[0]
                    buffer = buffer[2:]
                animRate = struct.unpack('H', buffer[:2])[0]
                animMode = struct.unpack('H', buffer[2:4])[0]
                animNameLen = struct.unpack('B', buffer[4:5])[0]
                animName = buffer[5:5 + animNameLen]
                buffer = buffer[5 + animNameLen:]
                texture = {'magFilter': magFilter,'minFilter': minFilter,'textureID': textureID,'wrapS': wrapS,'wrapT': wrapT}
                textures.append(texture)

            material = {'flags': flags,'alphaFunc': alphaFunc,'depthFunc': depthFunc,'srcBlend': srcBlend,'dstBlend': dstBlend,'alphaThreshold': alphaThreshold,'textures': textures}
            self.matBlocks.append(material)

        return buffer

    def ReadAnim(self, buffer):
        if buffer[:4] != b'ANIM':
            print('not ANIM')
            raise IOError
        length = struct.unpack('I', buffer[4:8])[0]
        buffer = buffer[8:]
        frameCount = struct.unpack('H', buffer[0:2])[0]
        frameRate = struct.unpack('H', buffer[2:4])[0]
        animMode = struct.unpack('H', buffer[4:6])[0]
        flags = struct.unpack('I', buffer[6:10])[0]
        disp = struct.unpack('f', buffer[10:14])[0]
        nbrMeshes = struct.unpack('H', buffer[14:16])[0]
        buffer = buffer[16:]
        self.anims = {}
        self.anims['frameCount'] = frameCount
        self.anims['animatedMeshes'] = []
        for nMesh in range(nbrMeshes):
            nameLen = struct.unpack('B', buffer[0:1])[0]
            flags = struct.unpack('B', buffer[1:2])[0]
            name = buffer[2:2 + nameLen - 1]
            buffer = buffer[2 + nameLen:]
            frames = []
            for frame in range(frameCount):
                vertBlock = struct.unpack('H', buffer[0:2])[0]
                indexBlock = struct.unpack('H', buffer[2:4])[0]
                primBlock = struct.unpack('H', buffer[4:6])[0]
                matsBlock = struct.unpack('H', buffer[6:8])[0]
                buffer = buffer[8:]
                frameMesh = {'vertBlock': vertBlock,'indexBlock': indexBlock,'primBlock': primBlock,'matsBlock': matsBlock}
                frames.append(frameMesh)

            animatedMesh = {'name': name,'frames': frames}
            self.anims['animatedMeshes'].append(animatedMesh)

        return buffer

    def draw(self, s3DTexturesHolder):
        if self.entry is None:
            return
        glColor3f(1.0, 1.0, 1.0)
        glEnable(GL_TEXTURE_2D)
        try:
            meshes = self.anims['animatedMeshes']
        except Exception:
            return

        self.currentFrame += 1
        if self.currentFrame == self.anims['frameCount']:
            self.currentFrame = 0
        funcTable = [
         GL_NEVER, GL_LESS, GL_EQUAL, GL_LEQUAL, GL_GREATER, GL_NOTEQUAL, GL_GEQUAL, GL_ALWAYS]
        funcTableReverse = [GL_ALWAYS, GL_GEQUAL, GL_NOTEQUAL, GL_GREATER, GL_LEQUAL, GL_EQUAL, GL_LESS, GL_NEVER]
        blendTable = [GL_ZERO, GL_ONE, GL_SRC_COLOR, GL_ONE_MINUS_SRC_COLOR, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ZERO, GL_ZERO, GL_DST_COLOR, GL_ONE_MINUS_DST_COLOR]
        for mesh in meshes:
            frameInfo = mesh['frames'][self.currentFrame]
            try:
                vertexBuffer = self.vertexBuffers[frameInfo['vertBlock']]
            except IndexError:
                continue

            try:
                indexBuffer = self.IndexBlocks[frameInfo['indexBlock']]
            except IndexError:
                continue

            try:
                material = self.matBlocks[frameInfo['matsBlock']]
            except IndexError:
                continue

            s3DTexturesHolder.SetCurrentTex((self.tgi2search[1], material['textures'][0]['textureID']))
            flags = material['flags']
            if flags & 1:
                glEnable(GL_ALPHA_TEST)
                glAlphaFunc(funcTable[material['alphaFunc']], material['alphaThreshold'])
            else:
                glDisable(GL_ALPHA_TEST)
            if flags & 2:
                glEnable(GL_DEPTH_TEST)
                glDepthFunc(funcTable[material['depthFunc']])
            else:
                glDisable(GL_DEPTH_TEST)
            if flags & 16:
                glEnable(GL_BLEND)
                try:
                    glBlendFunc(blendTable[material['srcBlend']], blendTable[material['dstBlend']])
                except Exception:
                    print('srcBlend =', material['srcBlend'])
                    print('dstBlend =', material['dstBlend'])
                    raise

            else:
                glDisable(GL_BLEND)
            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_TEXTURE_COORD_ARRAY)
            glVertexPointer(3, GL_FLOAT, 0, vertexBuffer[0])
            glTexCoordPointer(2, GL_FLOAT, 0, vertexBuffer[1])
            glDrawElements(GL_TRIANGLES, indexBuffer[1], GL_UNSIGNED_SHORT, indexBuffer[0])
            glDisableClientState(GL_VERTEX_ARRAY)
            glDisableClientState(GL_TEXTURE_COORD_ARRAY)

        return

    def FreeAll(self, s3DTexturesHolder):
        s3DTexturesHolder.Free()
        self.vertexBuffers = None
        self.matBlocks = None
        self.primBlocks = None
        self.IndexBlocks = None
        self.anims = None
        del self.vertexBuffers
        del self.matBlocks
        del self.primBlocks
        del self.IndexBlocks
        del self.anims
        return

    def free_3d(self, s3DTexturesHolder):
        s3DTexturesHolder.Free()

    def initialize(self, virtualDAT, viewer):
        if viewer.s3d_mesh == self:
            return
        if viewer.s3d_mesh is not None:
            viewer.s3d_mesh.free_3d(viewer.s3d_textures_holder)
        if self.entry is None:
            viewer.reinitialize()
            viewer.refresh(False)
            return
        self.LEInit(virtualDAT, viewer.s3d_textures_holder)
        viewer.s3d_mesh = self
        viewer.reinitialize()
        viewer.refresh(False)
        return

    def LEInit(self, virtualDAT, s3DTexturesHolder):
        if self.entry is None:
            return
        self.ReadFile()
        meshes = self.anims['animatedMeshes']
        for mesh in meshes:
            frameInfo = mesh['frames'][0]
            try:
                material = self.matBlocks[frameInfo['matsBlock']]
            except IndexError:
                continue

            try:
                textureID = material['textures'][0]['textureID']
            except IndexError:
                continue

            if self.tgi[1] == 3134937073:
                self.tgi2search = (
                 2058686020, 448690301, textureID)
            else:
                self.tgi2search = (
                 2058686020, self.tgi[1], textureID)
            entry = virtualDAT.getEntry(self.tgi2search[0], self.tgi2search[1], self.tgi2search[2])
            s3DTexturesHolder.PrecacheTex((self.tgi2search[1], textureID), entry)

        return
