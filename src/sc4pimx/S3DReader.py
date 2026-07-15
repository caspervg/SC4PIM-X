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
    glDrawElementsInstanced,
    glEnable,
    glFrontFace,
)

logger = logging.getLogger(__name__)

# A handful of published models are malformed: stale bytes left inside a chunk
# by a hex edit, a chunk length that does not match its payload, or a truncated
# tail. Rather than failing the whole model (and, at startup, the whole plugin
# load), skip forward to the next chunk tag when the parser lands on junk.
_RESYNC_LIMIT = 4096


def project_shadow_decal(positions, uvs, direction, plane_y=0.0):
    """Fit SC4's alpha-texture projector and return a ground receiver quad.

    The game's shadow path does not flatten the individual LOD-box faces.  It
    projects their vertices along the light direction, then finds one affine
    mapping from that shadow plane back into the model texture.  Drawing the
    fitted texture over a ground rectangle decouples the alpha silhouette from
    the fake carrier faces (which is especially important for trees).

    Returns ``(quad_positions, quad_uvs, uv_bounds)`` or ``None`` when the
    projection is degenerate, matching the game's failed-projector behaviour.
    """
    positions = np.asarray(positions, dtype=np.float64)
    uvs = np.asarray(uvs, dtype=np.float64)
    direction = np.asarray(direction, dtype=np.float64)
    if (
        positions.ndim != 2
        or positions.shape[1] != 3
        or uvs.shape != (len(positions), 2)
        or len(positions) < 3
        or direction.shape != (3,)
        or not np.all(np.isfinite(positions))
        or not np.all(np.isfinite(uvs))
        or not np.all(np.isfinite(direction))
        or abs(direction[1]) < 1.0e-6
    ):
        return None

    distance = (float(plane_y) - positions[:, 1]) / direction[1]
    projected = positions + distance[:, None] * direction
    design = np.column_stack((projected[:, 0], projected[:, 2], np.ones(len(projected))))
    try:
        coefficients, _residuals, rank, _singular = np.linalg.lstsq(design, uvs, rcond=None)
    except np.linalg.LinAlgError:
        return None
    if rank < 3 or not np.all(np.isfinite(coefficients)):
        return None

    min_x, max_x = float(projected[:, 0].min()), float(projected[:, 0].max())
    min_z, max_z = float(projected[:, 2].min()), float(projected[:, 2].max())
    if max_x - min_x < 1.0e-6 or max_z - min_z < 1.0e-6:
        return None
    quad_positions = np.asarray(
        (
            (min_x, plane_y, min_z),
            (max_x, plane_y, min_z),
            (max_x, plane_y, max_z),
            (min_x, plane_y, max_z),
        ),
        dtype=np.float32,
    )
    quad_design = np.column_stack(
        (quad_positions[:, 0], quad_positions[:, 2], np.ones(4, dtype=np.float32))
    )
    quad_uvs = np.asarray(quad_design @ coefficients, dtype=np.float32)
    uv_bounds = (
        float(uvs[:, 0].min()),
        float(uvs[:, 1].min()),
        float(uvs[:, 0].max()),
        float(uvs[:, 1].max()),
    )
    return quad_positions, quad_uvs, uv_bounds


class S3DParseError(OSError):
    """A malformed S3D payload that cannot be decoded."""


class S3D(object):

    def __init__(self, entry):
        self.entry = entry
        if entry is None:
            return
        self.tgi = entry.tgi
        return
    def _describe(self):
        tgi = getattr(self, 'tgi', None)
        if not tgi:
            return '<unknown>'
        return '0x%08X-0x%08X-0x%08X' % tgi

    def _seek_chunk(self, buffer, tag):
        """Return buffer positioned at `tag`, skipping junk bytes before it."""
        if buffer[:4] == tag:
            return buffer
        offset = buffer.find(tag)
        if offset < 0 or offset > _RESYNC_LIMIT:
            raise S3DParseError('S3D %s: expected %s chunk, got %r'
                                % (self._describe(), tag.decode('ascii'), bytes(buffer[:4])))
        logger.warning('S3D %s: skipped %d junk bytes before %s chunk',
                       self._describe(), offset, tag.decode('ascii'))
        return buffer[offset:]

    def _set_empty(self):
        """Degrade to an empty mesh so a broken model renders as nothing."""
        self.vertexBuffers = []
        self.IndexBlocks = []
        self.primBlocks = []
        self.matBlocks = []
        self.anims = {'frameCount': 1, 'frameRate': 0, 'animMode': 1, 'animatedMeshes': []}
        self._normal_cache = {}
        self.minx = self.maxx = self.miny = self.maxy = self.minz = self.maxz = 0.0
        self.bboxX = self.bboxY = self.bboxZ = 0.0
        self.currentFrame = 0
        self._lastFrameTime = None

    def ReadFile(self):
        if hasattr(self, 'vertexBuffers'):
            return
        if self.entry is None:
            return
        entry = self.entry
        entry.read_file(None, True, True)
        try:
            self._parse(entry.content)
        except (S3DParseError, struct.error, ValueError, IndexError) as exc:
            logger.error('Unreadable S3D %s in %s: %s',
                         self._describe(), entry.fileName, exc)
            self._set_empty()
        finally:
            entry.content = None
            entry.rawContent = None
        return

    def _parse(self, buffer):
        if buffer[:4] != b'3DMD':
            raise S3DParseError('S3D %s: expected 3DMD header, got %r'
                                % (self._describe(), bytes(buffer[:4])))
        struct.unpack('I', buffer[4:8])[0]
        buffer = buffer[8:]
        readers = ((b'HEAD', self.ReadHead), (b'VERT', self.ReadVert),
                   (b'INDX', self.ReadIndx), (b'PRIM', self.ReadPrim),
                   (b'MATS', self.ReadMats), (b'ANIM', self.ReadAnim))
        chunkStart = None
        for tag, reader in readers:
            if buffer[:4] != tag and chunkStart is not None and chunkStart.find(tag) > 0:
                # The previous chunk was malformed and consumed past this tag;
                # rewind to where it began and search forward from there.
                logger.warning('S3D %s: rewinding to recover the %s chunk',
                               self._describe(), tag.decode('ascii'))
                buffer = chunkStart
            chunkStart = buffer
            try:
                buffer = reader(buffer)
            except (struct.error, ValueError, IndexError) as exc:
                # Geometry chunks are load-bearing, but a garbled material or
                # animation list still leaves a drawable model, so keep what was
                # decoded and let the next chunk resync from this one's start.
                if tag not in (b'MATS', b'ANIM'):
                    raise
                logger.warning('S3D %s: truncated %s chunk (%s)',
                               self._describe(), tag.decode('ascii'), exc)
                buffer = b''
        if not hasattr(self, 'anims'):
            self.anims = {'frameCount': 1, 'frameRate': 0, 'animMode': 1, 'animatedMeshes': []}
        self.bboxX = self.maxx - self.minx
        self.bboxY = self.maxy - self.miny
        self.bboxZ = self.maxz - self.minz
        self.currentFrame = 0
        self._lastFrameTime = None
        return

    def ReadHead(self, buffer):
        buffer = self._seek_chunk(buffer, b'HEAD')
        struct.unpack('I', buffer[4:8])[0]
        self.majorRevision = struct.unpack('H', buffer[8:10])[0]
        self.minorRevision = struct.unpack('H', buffer[10:12])[0]
        return buffer[12:]

    def ReadVert(self, buffer):
        buffer = self._seek_chunk(buffer, b'VERT')
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
        buffer = self._seek_chunk(buffer, b'INDX')
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
        buffer = self._seek_chunk(buffer, b'PRIM')
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
        buffer = self._seek_chunk(buffer, b'MATS')
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
        buffer = self._seek_chunk(buffer, b'ANIM')
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

    def draw(self, s3DTexturesHolder, shader_program, lighting_state, mvp, normal_matrix,
             shadow=False, shadow_projection=None):
        return self.draw_instanced(
            s3DTexturesHolder, shader_program, lighting_state, [mvp], [normal_matrix],
            shadow=shadow, shadow_projection=shadow_projection,
        )

    def draw_instanced(self, s3DTexturesHolder, shader_program, lighting_state,
                       mvps, normal_matrices, shadow=False, shadow_projection=None):
        if not mvps or len(mvps) != len(normal_matrices) or len(mvps) > 32:
            raise ValueError('S3D instance batch must contain 1..32 matching transforms')
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
        shader_program.bind_instanced(lighting_state, mvps, normal_matrices)
        instance_count = len(mvps)

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
            # Self-illuminated glow meshes (framebuffer-blended: light flares,
            # lit windows) are not solid geometry and must not cast a shadow.
            if shadow and (flags & 16):
                continue
            # A projective shadow has no meaningful fallback without its alpha
            # texture.  During asynchronous FSH loading, treating the mesh as
            # untextured fills the entire receiver quad and produces the huge
            # dark wedges seen around flora.  The texture completion callback
            # refreshes the canvas, so skip this caster until its silhouette is
            # actually available.
            if shadow and not textured:
                continue
            if flags & 1:
                alpha_func = material['alphaFunc']
            else:
                alpha_func = 7
            if shadow:
                # Plain alpha-test discard in the shadow shader gives the crisp
                # silhouette; alpha-to-coverage would fringe it.
                glDisable(GL_SAMPLE_ALPHA_TO_COVERAGE)
            elif flags & 1:
                glEnable(GL_SAMPLE_ALPHA_TO_COVERAGE)
            else:
                glDisable(GL_SAMPLE_ALPHA_TO_COVERAGE)
            shader_program.set_material(
                alpha_func=alpha_func,
                alpha_threshold=material['alphaThreshold'],
                textured=textured,
                # Framebuffer-blended materials are self-illuminated glows
                # (light flares, lit windows); render them unlit so night
                # lighting does not dim them away under additive blending.
                emissive=bool(flags & 16),
            )
            if shadow:
                # The caller accumulates every projected fragment into one
                # stencil coverage mask. Do not write depth or colour here:
                # overlapping flattened faces/casters must all contribute to
                # the mask without racing on nominally coplanar depth values.
                glEnable(GL_DEPTH_TEST)
                glDepthFunc(GL_LEQUAL)
                glDepthMask(GL_FALSE)
                glDisable(GL_CULL_FACE)
                glDisable(GL_BLEND)
                if shadow_projection is None:
                    continue
                direction, plane_y = shadow_projection
                decal = project_shadow_decal(
                    vertexBuffer['positions'], vertexBuffer['uvs'], direction, plane_y,
                )
                if decal is None:
                    continue
                decal_positions, decal_uvs, uv_bounds = decal
                shader_program.set_uv_bounds(uv_bounds)
                normals = np.zeros((4, 3), dtype=np.float32)
                idx_bytes = np.asarray((0, 1, 2, 0, 2, 3), dtype=np.uint16)
                buffers = s3DTexturesHolder.get_mesh_buffers(self)
                vert_block = frameInfo['vertBlock']
                projection_key = tuple(round(float(value), 6) for value in (*direction, plane_y))
                vao_key = ('shadow-decal', vert_block, projection_key)
                vao = buffers.mesh_vao(
                    vao_key, decal_positions, normals, decal_uvs, idx_bytes,
                )
                glBindVertexArray(vao)
                glDrawElementsInstanced(
                    GL_TRIANGLES, 6, GL_UNSIGNED_SHORT, ctypes.c_void_p(0), instance_count,
                )
                glBindVertexArray(0)
                glBindSampler(0, 0)
                continue
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
                    glDrawElementsInstanced(GL_TRIANGLES, length, GL_UNSIGNED_SHORT,
                                            ctypes.c_void_p(first * 2), instance_count)
                elif typePrim == 1:
                    glDrawElementsInstanced(GL_TRIANGLE_STRIP, length, GL_UNSIGNED_SHORT,
                                            ctypes.c_void_p(first * 2), instance_count)
                elif typePrim == 2:
                    # GL_QUADS is absent from core profiles; each source quad
                    # is equivalent to a four-index triangle fan.
                    for quad_first in range(first, first + length - 3, 4):
                        glDrawElementsInstanced(GL_TRIANGLE_FAN, 4, GL_UNSIGNED_SHORT,
                                                ctypes.c_void_p(quad_first * 2), instance_count)
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
            try:
                frameInfo = mesh['frames'][0]
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
