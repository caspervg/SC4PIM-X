"""S3D (SimCity 4 3D model) file reader."""
import ctypes
import logging
import struct
import time

import numpy
import numpy as np
from OpenGL.GL import (
    GL_ALWAYS,
    GL_BACK,
    GL_BLEND,
    GL_CCW,
    GL_CULL_FACE,
    GL_DEPTH_TEST,
    GL_DST_COLOR,
    GL_EQUAL,
    GL_FALSE,
    GL_GEQUAL,
    GL_GREATER,
    GL_LEQUAL,
    GL_LESS,
    GL_NEVER,
    GL_NOTEQUAL,
    GL_ONE,
    GL_ONE_MINUS_DST_COLOR,
    GL_ONE_MINUS_SRC_ALPHA,
    GL_ONE_MINUS_SRC_COLOR,
    GL_SAMPLE_ALPHA_TO_COVERAGE,
    GL_SRC_ALPHA,
    GL_SRC_COLOR,
    GL_TRIANGLE_FAN,
    GL_TRIANGLE_STRIP,
    GL_TRIANGLES,
    GL_TRUE,
    GL_UNSIGNED_SHORT,
    GL_ZERO,
    glBindSampler,
    glBindVertexArray,
    glBlendFunc,
    glCullFace,
    glDepthFunc,
    glDepthMask,
    glDisable,
    glDrawElements,
    glEnable,
    glFrontFace,
)

logger = logging.getLogger(__name__)


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
            logger.error('Invalid S3D header: expected 3DMD, got %r', buffer[:4])
            buffer = None
            del buffer
            entry.content = None
            entry.rawContent = None
            self.entry = None
            raise IOError
        struct.unpack('I', buffer[4:8])[0]
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
        self._lastFrameTime = None
        return

    def ReadHead(self, buffer):
        if buffer[:4] != b'HEAD':
            logger.error('Invalid S3D HEAD chunk: got %r', buffer[:4])
            raise IOError
        struct.unpack('I', buffer[4:8])[0]
        self.majorRevision = struct.unpack('H', buffer[8:10])[0]
        self.minorRevision = struct.unpack('H', buffer[10:12])[0]
        return buffer[12:]

    def ReadVert(self, buffer):
        if buffer[:4] != b'VERT':
            logger.error('Invalid S3D VERT chunk: got %r', buffer[:4])
            raise IOError
        struct.unpack('I', buffer[4:8])[0]
        nbrBlock = struct.unpack('I', buffer[8:12])[0]
        buffer = buffer[12:]
        self.vertexBuffers = []
        bounds_set = False
        for x in range(nbrBlock):
            struct.unpack('H', buffer[0:2])[0]
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
                stride = vertexSize
            buffer = buffer[8:]
            # Vectorized vertex read. S3D stores positions first and may
            # append packed color and one or more UV sets depending on format.
            nbytes = count * stride
            arr = numpy.frombuffer(buffer[:nbytes], dtype=numpy.uint8).reshape(count, stride)
            buffer = buffer[nbytes:]
            vertices = numpy.ascontiguousarray(arr[:, 0:12]).view('<f4').reshape(count, 3)
            offset = 12 * coordsNb
            colors = None
            if colorsNb:
                color_bytes = colorsNb * 4
                colors = numpy.ascontiguousarray(arr[:, offset:offset + color_bytes])
                offset += color_bytes
            if texsNb:
                uvs = numpy.ascontiguousarray(arr[:, offset:offset + 8]).view('<f4').reshape(count, 2)
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
            self.vertexBuffers.append({
                'positions': numpy.ascontiguousarray(vertices, dtype=numpy.float32),
                'uvs': numpy.ascontiguousarray(uvs, dtype=numpy.float32),
                'colors': colors,
            })

        if not bounds_set:
            self.minx = self.maxx = self.miny = self.maxy = self.minz = self.maxz = 0.0
        self._normal_cache = {}
        return buffer

    def ReadIndx(self, buffer):
        if buffer[:4] != b'INDX':
            logger.error('Invalid S3D INDX chunk: got %r', buffer[:4])
            raise IOError
        struct.unpack('I', buffer[4:8])[0]
        nbrBlock = struct.unpack('I', buffer[8:12])[0]
        buffer = buffer[12:]
        self.IndexBlocks = []
        for i in range(nbrBlock):
            struct.unpack('H', buffer[0:2])[0]
            struct.unpack('H', buffer[2:4])[0]
            count = struct.unpack('H', buffer[4:6])[0]
            buffer = buffer[6:]
            indices = struct.unpack('H' * count, buffer[:count * 2])
            idxs = np.asarray(indices, dtype=np.uint16)
            self.IndexBlocks.append((idxs.tobytes(), count))
            buffer = buffer[count * 2:]

        return buffer

    def ReadPrim(self, buffer):
        if buffer[:4] != b'PRIM':
            logger.error('Invalid S3D PRIM chunk: got %r', buffer[:4])
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
            logger.error('Invalid S3D MATS chunk: got %r', buffer[:4])
            raise IOError
        struct.unpack('I', buffer[4:8])[0]
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
            struct.unpack('I', buffer[10:14])[0]
            struct.unpack('B', buffer[14:15])[0]
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
                struct.unpack('H', buffer[:2])[0]
                struct.unpack('H', buffer[2:4])[0]
                animNameLen = struct.unpack('B', buffer[4:5])[0]
                buffer[5:5 + animNameLen]
                buffer = buffer[5 + animNameLen:]
                texture = {'magFilter': magFilter,'minFilter': minFilter,'textureID': textureID,'wrapS': wrapS,'wrapT': wrapT}
                textures.append(texture)

            material = {'flags': flags,'alphaFunc': alphaFunc,'depthFunc': depthFunc,'srcBlend': srcBlend,'dstBlend': dstBlend,'alphaThreshold': alphaThreshold,'textures': textures}
            self.matBlocks.append(material)

        return buffer

    def ReadAnim(self, buffer):
        if buffer[:4] != b'ANIM':
            logger.error('Invalid S3D ANIM chunk: got %r', buffer[:4])
            raise IOError
        struct.unpack('I', buffer[4:8])[0]
        buffer = buffer[8:]
        frameCount = struct.unpack('H', buffer[0:2])[0]
        frameRate = struct.unpack('H', buffer[2:4])[0]
        animMode = struct.unpack('H', buffer[4:6])[0]
        struct.unpack('I', buffer[6:10])[0]
        struct.unpack('f', buffer[10:14])[0]
        nbrMeshes = struct.unpack('H', buffer[14:16])[0]
        buffer = buffer[16:]
        self.anims = {}
        self.anims['frameCount'] = frameCount
        self.anims['frameRate'] = frameRate
        # 1 = Loop (default), 2 = Ping-pong, 3 = One-shot. Loop fallback for
        # unknown values to preserve current behaviour.
        self.anims['animMode'] = animMode
        self.anims['animatedMeshes'] = []
        for nMesh in range(nbrMeshes):
            nameLen = struct.unpack('B', buffer[0:1])[0]
            struct.unpack('B', buffer[1:2])[0]
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

    def draw(self, s3DTexturesHolder, shader_program, lighting_state, mvp, normal_matrix):
        if self.entry is None:
            return
        try:
            meshes = self.anims['animatedMeshes']
        except Exception:
            return

        frame_count = max(1, self.anims.get('frameCount', 1))
        if frame_count > 1:
            # Decouple animation speed from draw call rate: advance by elapsed
            # time at the model's intended frameRate, not once per draw.
            fps = self.anims.get('frameRate') or 10
            interval = 1.0 / fps
            now = time.monotonic()
            if self._lastFrameTime is None:
                self._lastFrameTime = now
            elapsed = now - self._lastFrameTime
            steps = int(elapsed / interval)
            if steps > 0:
                self._lastFrameTime += steps * interval
                # animMode encoding is not yet confirmed against real BAT data;
                # always loop until ping-pong / one-shot values can be verified
                # so we never freeze on the last frame.
                self.currentFrame = (self.currentFrame + steps) % frame_count
            s3DTexturesHolder.glCanvas.request_animation(max(1, int(interval * 1000)))
        if self.currentFrame >= frame_count:
            self.currentFrame = 0
        funcTable = [
         GL_NEVER, GL_LESS, GL_EQUAL, GL_LEQUAL, GL_GREATER, GL_NOTEQUAL, GL_GEQUAL, GL_ALWAYS]
        blendTable = [GL_ZERO, GL_ONE, GL_SRC_COLOR, GL_ONE_MINUS_SRC_COLOR, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ZERO, GL_ZERO, GL_DST_COLOR, GL_ONE_MINUS_DST_COLOR]
        mesh_tex_keys = getattr(self, 'mesh_tex_keys', None) or []
        shader_program.bind(lighting_state, mvp, normal_matrix)

        def pass_order(item):
            _index, candidate = item
            try:
                info = candidate['frames'][self.currentFrame]
                return 1 if self.matBlocks[info['matsBlock']]['flags'] & 16 else 0
            except (IndexError, KeyError):
                return 0

        # Opaque/cutout meshes establish depth first; blended meshes retain
        # their source order and render afterward.
        for mi, mesh in sorted(enumerate(meshes), key=pass_order):
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
                primBlock = self.primBlocks[frameInfo['primBlock']]
            except IndexError:
                continue

            try:
                material = self.matBlocks[frameInfo['matsBlock']]
            except IndexError:
                continue

            textures = material.get('textures') or []
            texInfo = textures[0] if textures else {}
            # Use the per-mesh key resolved in LEInit. Fall back to the
            # historical single tgi2search if the per-mesh list is missing
            # (older code path, defensive).
            tex_key = None
            if mi < len(mesh_tex_keys):
                tex_key = mesh_tex_keys[mi]
            if tex_key is None and textures and hasattr(self, 'tgi2search'):
                tex_key = (self.tgi2search[1], texInfo['textureID'])
            textured = False
            if tex_key is not None:
                textured = bool(s3DTexturesHolder.SetCurrentTex(
                    tex_key,
                    min_filter=texInfo.get('minFilter'),
                    mag_filter=texInfo.get('magFilter'),
                    wrap_s=texInfo.get('wrapS'),
                    wrap_t=texInfo.get('wrapT'),
                ))
            flags = material['flags']
            if flags & 1:
                alpha_func = material['alphaFunc']
                glEnable(GL_SAMPLE_ALPHA_TO_COVERAGE)
            else:
                alpha_func = 7
                glDisable(GL_SAMPLE_ALPHA_TO_COVERAGE)
            shader_program.set_material(
                alpha_func=alpha_func,
                alpha_threshold=material['alphaThreshold'],
                textured=textured,
            )
            if flags & 2:
                glEnable(GL_DEPTH_TEST)
                glDepthFunc(funcTable[material['depthFunc']])
            else:
                glDisable(GL_DEPTH_TEST)
            # Backface culling flag. Wiki lists Mats checkboxes in the order
            # alpha-test (bit 0=1), depth-test (bit 1=2), backface-culling,
            # framebuffer-blending (bit 4=16), texturing — so culling sits at
            # bit 2 (value 4). Maxis convention is CCW = visible, CW = culled,
            # which matches GL defaults (glFrontFace=GL_CCW, GL_CULL_FACE=GL_BACK).
            if flags & 4:
                glEnable(GL_CULL_FACE)
                glCullFace(GL_BACK)
                glFrontFace(GL_CCW)
            else:
                glDisable(GL_CULL_FACE)
            if flags & 16:
                glEnable(GL_BLEND)
                glDepthMask(GL_FALSE)
                try:
                    glBlendFunc(blendTable[material['srcBlend']], blendTable[material['dstBlend']])
                except Exception:
                    logger.exception(
                        'Invalid S3D blend mode srcBlend=%r dstBlend=%r',
                        material['srcBlend'], material['dstBlend'])
                    raise

            else:
                glDisable(GL_BLEND)
                glDepthMask(GL_TRUE)
            normals = self._normal_buffer(frameInfo, vertexBuffer, indexBuffer, primBlock)
            idx_bytes = indexBuffer[0]
            idx_count = indexBuffer[1]
            # Upload once as an interleaved core-profile VAO.
            buffers = s3DTexturesHolder.get_mesh_buffers(self)
            vert_block = frameInfo['vertBlock']
            norm_key = (vert_block, frameInfo['indexBlock'], frameInfo['primBlock'])
            vao_key = (vert_block, norm_key, frameInfo['indexBlock'])
            vao = buffers.mesh_vao(
                vao_key, vertexBuffer['positions'], normals, vertexBuffer['uvs'], idx_bytes,
            )
            glBindVertexArray(vao)
            # Per the S3D Prim wiki each PRIM sub-entry has a first-index
            # offset and a triangle-index count; the parent INDX block may
            # back several sub-prims or carry padding past them. Draw each
            # sub-prim explicitly rather than blasting the whole INDX. With an
            # element buffer bound, the final arg is a byte offset into it.
            for typePrim, first, length in primBlock:
                if length == 0 or first + length > idx_count:
                    continue
                if typePrim == 0:
                    glDrawElements(GL_TRIANGLES, length, GL_UNSIGNED_SHORT,
                                   ctypes.c_void_p(first * 2))
                elif typePrim == 1:
                    glDrawElements(GL_TRIANGLE_STRIP, length, GL_UNSIGNED_SHORT,
                                   ctypes.c_void_p(first * 2))
                elif typePrim == 2:
                    # GL_QUADS is absent from core profiles; each source quad
                    # is equivalent to a four-index triangle fan.
                    for quad_first in range(first, first + length - 3, 4):
                        glDrawElements(GL_TRIANGLE_FAN, 4, GL_UNSIGNED_SHORT,
                                       ctypes.c_void_p(quad_first * 2))
                else:
                    logger.debug('S3D PRIM type %d not supported (first=%d length=%d) tgi=%r',
                                 typePrim, first, length, getattr(self, 'tgi', None))
            glBindVertexArray(0)
            glBindSampler(0, 0)

        glDisable(GL_SAMPLE_ALPHA_TO_COVERAGE)
        glDepthMask(GL_TRUE)
        shader_program.unbind()
        return

    def _normal_buffer(self, frame_info, vertex_buffer, index_buffer, prim_block):
        key = (frame_info['vertBlock'], frame_info['indexBlock'], frame_info['primBlock'])
        cached = self._normal_cache.get(key)
        if cached is not None:
            return cached
        positions = vertex_buffer['positions']
        normals = numpy.zeros_like(positions, dtype=numpy.float32)
        idx_bytes, idx_count = index_buffer
        for type_prim, first, length in prim_block:
            if length < 3 or first + length > idx_count:
                continue
            indices = numpy.frombuffer(idx_bytes, dtype=numpy.uint16, count=length, offset=first * 2)
            if type_prim == 0:
                triangles = indices[:(length // 3) * 3].reshape(-1, 3)
            elif type_prim == 1:
                triangles = numpy.column_stack((indices[:-2], indices[1:-1], indices[2:]))
                if len(triangles) > 1:
                    odd = triangles[1::2].copy()
                    triangles[1::2, 0] = odd[:, 1]
                    triangles[1::2, 1] = odd[:, 0]
            elif type_prim == 2:
                quads = indices[:(length // 4) * 4].reshape(-1, 4)
                triangles = numpy.vstack((quads[:, (0, 1, 2)], quads[:, (0, 2, 3)]))
            else:
                continue
            tri_pos = positions[triangles]
            edge1 = tri_pos[:, 1] - tri_pos[:, 0]
            edge2 = tri_pos[:, 2] - tri_pos[:, 0]
            face_normals = numpy.cross(edge1, edge2)
            for corner in range(3):
                numpy.add.at(normals, triangles[:, corner], face_normals)
        lengths = numpy.linalg.norm(normals, axis=1)
        zero_mask = lengths <= 1.0e-6
        if numpy.any(~zero_mask):
            normals[~zero_mask] /= lengths[~zero_mask][:, numpy.newaxis]
        if numpy.any(zero_mask):
            normals[zero_mask] = numpy.array([0.0, 1.0, 0.0], dtype=numpy.float32)
        normals = numpy.ascontiguousarray(normals, dtype=numpy.float32)
        self._normal_cache[key] = normals
        return normals

    def FreeAll(self, s3DTexturesHolder):
        s3DTexturesHolder.drop_mesh_buffers(self)
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
        s3DTexturesHolder.drop_mesh_buffers(self)
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
        # Per-mesh resolved (group, instance) cache keys so draw() does not
        # need to share a single self.tgi2search across meshes with different
        # textures.
        self.mesh_tex_keys = [None] * len(meshes)
        FSH_TYPE = 2058686020       # 0x7AB50E44
        SHARED_GROUP = 448690301    # 0x1ABE787D
        MAXIS_S3D_GROUP = 3134937073  # 0xBADB57F1
        NIGHT_OFFSET = 0x8000       # RKT1 group-of-20 convention per the
                                    # S3D Mats wiki; widely applied by modders.
        for mi, mesh in enumerate(meshes):
            frameInfo = mesh['frames'][0]
            try:
                material = self.matBlocks[frameInfo['matsBlock']]
            except IndexError:
                continue

            try:
                textureID = material['textures'][0]['textureID']
            except IndexError:
                continue

            # Per the S3D Mats wiki the texture is normally in the S3D's own
            # group; transit / Maxis-shared content lives in 0x1ABE787D. Try
            # own group first, then the shared group as fallback. Maxis content
            # rarely ships its own group's textures, so try shared first there.
            if self.tgi[1] in (MAXIS_S3D_GROUP, SHARED_GROUP):
                candidate_groups = (SHARED_GROUP,)
            else:
                candidate_groups = (self.tgi[1], SHARED_GROUP)
            day_entry = None
            resolved_group = candidate_groups[0]
            for group in candidate_groups:
                day_entry = virtualDAT.getEntry(FSH_TYPE, group, textureID)
                if day_entry is not None:
                    resolved_group = group
                    break
            # Night sibling lives in the same group as the resolved day
            # texture, at instance + 0x8000. Silent fallback if absent.
            night_entry = virtualDAT.getEntry(
                FSH_TYPE, resolved_group, textureID + NIGHT_OFFSET)
            key = (resolved_group, textureID)
            self.mesh_tex_keys[mi] = key
            # Back-compat: legacy callers read self.tgi2search; keep the
            # last-resolved entry available for them.
            self.tgi2search = (FSH_TYPE, resolved_group, textureID)
            s3DTexturesHolder.PrecacheTex(key, day_entry, night_entry=night_entry)

        return
