"""S3D textures holder for OpenGL rendering."""
import ctypes
import logging
import time
import weakref
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from OpenGL.GL import (
    GL_ARRAY_BUFFER,
    GL_CLAMP_TO_EDGE,
    GL_ELEMENT_ARRAY_BUFFER,
    GL_FALSE,
    GL_FLOAT,
    GL_LINEAR,
    GL_MIRRORED_REPEAT,
    GL_NEAREST,
    GL_REPEAT,
    GL_STATIC_DRAW,
    GL_TEXTURE_2D,
    glBindBuffer,
    glBindSampler,
    glBindTexture,
    glBindVertexArray,
    glBufferData,
    glDeleteBuffers,
    glDeleteTextures,
    glDeleteVertexArrays,
    glEnableVertexAttribArray,
    glGenBuffers,
    glGenVertexArrays,
    glVertexAttribPointer,
)
from PIL import Image

from . import FSHConverter
from .SC4Renderer import create_texture_2d

logger = logging.getLogger(__name__)

# DBPF entries can share an underlying file handle. A single decode worker
# keeps reads serialized while moving FSH decompression/composition off the UI
# thread. GL uploads remain on the context-owning UI thread.
_decode_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sc4-fsh-decode")


class _MeshGLBuffers(object):
    """Lazily-created VBO/IBO set for one S3D mesh in one GL context.

    Buffer names are valid only in the context that created them, so each
    per-canvas holder owns its own set (see S3DTexturesHolder). Geometry is
    immutable once read, so buffers are uploaded once (GL_STATIC_DRAW) and
    keyed by the S3D block index they came from.
    """

    def __init__(self):
        self._meshes = {}  # key -> (vao, interleaved_vbo, index_ibo)
        self._buffer_ids = []
        self._vao_ids = []

    def _make(self, target, data):
        size = len(data) if isinstance(data, (bytes, bytearray)) else data.nbytes
        name = int(glGenBuffers(1))
        glBindBuffer(target, name)
        glBufferData(target, size, data, GL_STATIC_DRAW)
        glBindBuffer(target, 0)
        self._buffer_ids.append(name)
        return name

    def mesh_vao(self, key, positions, normals, uvs, indices):
        cached = self._meshes.get(key)
        if cached is not None:
            return cached[0]
        vertices = np.ascontiguousarray(
            np.column_stack((positions, normals, uvs)), dtype=np.float32,
        )
        vao = int(glGenVertexArrays(1))
        self._vao_ids.append(vao)
        glBindVertexArray(vao)
        vbo = self._make(GL_ARRAY_BUFFER, vertices)
        ibo = self._make(GL_ELEMENT_ARRAY_BUFFER, indices)
        # Vertex attribute bindings capture the currently bound array buffer
        # in the VAO. _make() unbinds after upload, so restore both buffers
        # before describing the interleaved layout.
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ibo)
        stride = 8 * 4
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(12))
        glEnableVertexAttribArray(2)
        glVertexAttribPointer(2, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(24))
        glBindVertexArray(0)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        self._meshes[key] = (vao, vbo, ibo)
        return vao

    def delete(self):
        if self._buffer_ids:
            try:
                glDeleteBuffers(len(self._buffer_ids), self._buffer_ids)
            except Exception:
                pass
        if self._vao_ids:
            try:
                glDeleteVertexArrays(len(self._vao_ids), self._vao_ids)
            except Exception:
                pass
        self._buffer_ids = []
        self._vao_ids = []
        self._meshes.clear()


def _texture_name(value):
    return int(value)


def _delete_texture(value):
    glDeleteTextures([_texture_name(value)])


def _snapshot_content(entry):
    if entry is None:
        return None
    try:
        entry.read_file(None, True, True)
        return bytes(entry.content)
    except Exception:
        return None
    finally:
        entry.content = None
        entry.rawContent = None


def _decode_layers(content):
    """Decode a snapped FSH byte string into (size, RGBA bytes) layers."""
    if content is None:
        return None
    try:
        nbrLayers, _trueAlpha, img, alpha, size = FSHConverter.decodeFSH(content)
        nbOfBytes = size[0] * size[1]
        expected_img = nbOfBytes * 3 * nbrLayers
        expected_alpha = nbOfBytes * nbrLayers
        if len(img) < expected_img or len(alpha) < expected_alpha:
            nbrLayers = 1
        layers = []
        for li in range(nbrLayers):
            rgb = img[nbOfBytes * 3 * li:nbOfBytes * 3 * (li + 1)]
            a = alpha[nbOfBytes * li:nbOfBytes * (li + 1)]
            imBmp = Image.frombytes('RGB', size, rgb)
            imAlpha = Image.frombytes('L', size, a)
            im = Image.merge('RGBA', imBmp.split() + imAlpha.split())
            layers.append((size, im.tobytes('raw', 'RGBA')))
        return layers
    except Exception:
        return None


def _blend_night_over_day(day_rgba, night_rgba):
    """Alpha-composite the night layer over the day layer.

    Night FSHes are sparse (mostly transparent except window/light pixels);
    a straight swap would render the building black, so we blend night.rgb
    over day.rgb using night.a as the mix factor. The composite *keeps the
    day alpha* — the night layer is meant to modulate the existing day
    surface, not extend it. If we used max(day.a, night.a) instead, any
    halo or bleed in the night FSH outside the day silhouette would suddenly
    pass the alpha test and reveal whatever LOD / shadow plane sits behind
    the building.
    """
    d = np.frombuffer(day_rgba, dtype=np.uint8).reshape(-1, 4).astype(np.uint16)
    n = np.frombuffer(night_rgba, dtype=np.uint8).reshape(-1, 4).astype(np.uint16)
    a = n[:, 3:4]
    inv = 255 - a
    out = np.empty_like(d)
    out[:, 0:3] = (d[:, 0:3] * inv + n[:, 0:3] * a) // 255
    out[:, 3:4] = d[:, 3:4]
    return out.astype(np.uint8).tobytes()


def _prepare_layers(day_content, night_content, night_mode):
    day_layers = _decode_layers(day_content)
    night_layers = _decode_layers(night_content) if night_mode else None
    if night_mode and day_layers and night_layers:
        chosen = []
        for index, (size, day_rgba) in enumerate(day_layers):
            if index < len(night_layers):
                night_size, night_rgba = night_layers[index]
                if night_size == size:
                    chosen.append((size, _blend_night_over_day(day_rgba, night_rgba)))
                    continue
            chosen.append((size, day_rgba))
        return chosen
    if night_mode and night_layers and not day_layers:
        return night_layers
    return day_layers or []


class S3DTexturesHolder(object):
    __module__ = __name__

    def __init__(self, glCanvas):
        # textures[key] = source entries plus, per night_mode, a worker future
        # and the uploaded GL layer names. Both the day (False) and night (True)
        # sets are kept resident so toggling night_mode is an instant swap.
        self.textures = {}
        self.glCanvas = glCanvas
        self.night_mode = False
        # Generate mipmaps + sample model textures trilinearly/anisotropically.
        # Worth it for interactive views; the asset-thumbnail prerender turns it
        # off (set on its dedicated holder) since every texture is uploaded,
        # rendered once into a tiny downscaled capture and freed -- mipmap
        # generation there is pure overhead with no visible benefit.
        self.mipmaps = True
        self.max_texture_bytes = 256 * 1024 * 1024
        self._texture_bytes = 0
        self._use_serial = 0
        # Per-mesh VBO/IBO sets, keyed by id(mesh). A weakref guards against
        # id() reuse after a mesh is garbage-collected (a recycled id maps to a
        # different object, so we rebuild instead of handing back stale buffers).
        self._mesh_buffers = {}

    def get_mesh_buffers(self, mesh):
        """Return this context's _MeshGLBuffers for mesh, creating it lazily.

        The caller is responsible for having made this canvas's GL context
        current (every draw entry point does so once at frame start). We must
        NOT SetCurrent here: on macOS wx's GLCanvas.SetCurrent() resets the GL
        viewport to the full drawable, and this runs mid-frame -- per sub-mesh
        -- after the split-screen preview has installed its half-pane viewport.
        A make-current here both clobbered that viewport (models rendered into
        the whole canvas) and cost a context switch on every sub-mesh. Relying
        on the frame-start make-current avoids both; it's the same contract the
        texture path has always used.
        """
        key = id(mesh)
        entry = self._mesh_buffers.get(key)
        if entry is not None:
            ref, buffers = entry
            if ref is None or ref() is mesh:
                return buffers
            # id was reused by a different object -- drop the stale buffers.
            buffers.delete()
        buffers = _MeshGLBuffers()
        try:
            ref = weakref.ref(mesh)
        except TypeError:
            ref = None
        self._mesh_buffers[key] = (ref, buffers)
        return buffers

    def drop_mesh_buffers(self, mesh):
        """Free the buffers held for a single mesh (called when it unloads)."""
        entry = self._mesh_buffers.pop(id(mesh), None)
        if entry is not None:
            self.glCanvas.SetCurrent()
            entry[1].delete()

    def _free_mesh_buffers(self):
        for _ref, buffers in self._mesh_buffers.values():
            buffers.delete()
        self._mesh_buffers.clear()

    def SetNightMode(self, enabled):
        """Toggle night-lighting composition.

        Day and night GL layer sets are cached side by side (see
        :meth:`PrecacheTex`), so flipping the mode is a pointer swap on the next
        bind — no re-decode, no re-upload, no red-model flash. We only kick off
        a background decode for the newly active mode if it was never built
        (e.g. the entry was registered after some earlier toggle).

        Returns True when the mode actually changed (caller should trigger a
        repaint), False when this was a no-op.
        """
        enabled = bool(enabled)
        if enabled == self.night_mode:
            return False
        self.night_mode = enabled
        self.glCanvas.SetCurrent()
        for cached in self.textures.values():
            mode = self._effective_mode(cached)
            if cached['gl'].get(mode) is None and cached['future'].get(mode) is None:
                self._schedule_decode(cached, mode)
        return True

    def _effective_mode(self, cached):
        """Which cached set a bind should use right now.

        A texture with no night sibling composites to the same pixels in both
        modes, so it only ever keeps the ``False`` (day) set — that halves the
        memory cost of the dual cache for the common night-less texture.
        """
        return bool(self.night_mode and cached.get('night') is not None)

    def _free_gl_layers(self, cached, mode=None):
        """Free the GL layers for one mode, or both when mode is None."""
        modes = (mode,) if mode is not None else (False, True)
        for m in modes:
            layers = cached['gl'].get(m)
            if layers:
                for name in layers:
                    _delete_texture(name)
            self._texture_bytes -= int(cached['gl_bytes'].get(m, 0))
            self._texture_bytes = max(0, self._texture_bytes)
            cached['gl_bytes'][m] = 0
            cached['gl'][m] = None

    def Free(self):
        self.glCanvas.SetCurrent()
        for cached in self.textures.values():
            for future in cached['future'].values():
                if future is not None:
                    future.cancel()
            self._free_gl_layers(cached)
        self._free_mesh_buffers()

    def PrecacheTex(self, textureID, entry, night_entry=None):
        """Register a texture under textureID.

        entry is the daytime FSH entry; night_entry, when provided, is the
        nightlight sibling (typically the day instance + 0x8000 in the same
        group) — composited over day when night_mode is on. When a night
        sibling exists, both the day and night composites are decoded up front
        so a later night/day toggle is an instant swap.
        """
        try:
            self.glCanvas.SetCurrent()
            old = self.textures[textureID]
            self._free_gl_layers(old)
        except Exception:
            pass
        cached = {
            'day': entry,
            'night': night_entry,
            'gl': {False: None, True: None},
            'gl_bytes': {False: 0, True: 0},
            'future': {False: None, True: None},
            'generation': {False: 0, True: 0},
            'last_used': 0,
        }
        self.textures[textureID] = cached
        self._schedule_decode(cached, False)
        if night_entry is not None:
            self._schedule_decode(cached, True)

    def _schedule_decode(self, cached, mode):
        generation = cached['generation'].get(mode, 0) + 1
        cached['generation'][mode] = generation
        old_future = cached['future'].get(mode)
        if old_future is not None:
            old_future.cancel()
        future = _decode_executor.submit(
            _prepare_layers,
            _snapshot_content(cached.get('day')),
            _snapshot_content(cached.get('night')) if mode else None,
            mode,
        )
        cached['future'][mode] = future
        holder_ref = weakref.ref(self)

        def decoded(_future):
            holder = holder_ref()
            if holder is None or cached['generation'].get(mode) != generation:
                return
            try:
                import wx
                wx.CallAfter(holder.glCanvas.Refresh, False)
            except Exception:
                pass

        future.add_done_callback(decoded)

    def _upload_layers(self, cached, mode):
        """Decode + (optionally) blend + upload GL textures for one mode.

        Populates ``cached['gl'][mode]`` in place (empty list on full failure).
        """
        future = cached['future'].get(mode)
        if future is None:
            self._schedule_decode(cached, mode)
            return False
        if not future.done():
            return False
        try:
            chosen = future.result()
        except Exception:
            logger.exception("Failed to decode S3D texture")
            chosen = []
        cached['future'][mode] = None

        new_layers = []
        uploaded_bytes = 0
        for size, rgba in chosen:
            try:
                texName = create_texture_2d(
                    size[0], size[1], rgba, channels=4,
                    srgb=getattr(self.glCanvas, 'srgb', False),
                    mipmaps=self.mipmaps,
                )
                new_layers.append(texName)
                uploaded_bytes += int(size[0]) * int(size[1]) * 4
            except Exception:
                continue
        self._free_gl_layers(cached, mode)
        cached['gl'][mode] = new_layers
        cached['gl_bytes'][mode] = uploaded_bytes
        self._texture_bytes += uploaded_bytes
        self._evict_texture_layers(cached)
        return True

    def flush_pending(self, timeout=15.0):
        """Block until the active-mode decode for every texture is uploaded.

        Normal rendering is lazy: FSH decoding runs on a background worker and
        the GL upload is deferred to the first :meth:`SetCurrentTex` after the
        future resolves. A *synchronous* prerender (asset thumbnails) can reach
        the capture before that happens, so the model draws with no texture and
        the shader paints it solid red (the untextured marker colour). Here the
        decodes for the currently active mode are awaited, then the uploads run
        on this thread (which owns the GL context). Returns True if everything
        is ready, False on timeout.
        """
        self.glCanvas.SetCurrent()
        deadline = time.monotonic() + max(0.0, timeout)
        ready = True
        for cached in list(self.textures.values()):
            mode = self._effective_mode(cached)
            future = cached['future'].get(mode)
            if future is None:
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.warning("flush_pending timed out waiting for texture decode")
                ready = False
                break
            try:
                future.result(timeout=remaining)
            except Exception:
                logger.exception("Texture decode failed during flush_pending")
                ready = False
        # Uploads must happen on the context-owning thread, so do them here
        # rather than inside the decode worker.
        for cached in list(self.textures.values()):
            mode = self._effective_mode(cached)
            if cached['future'].get(mode) is not None:
                if not self._upload_layers(cached, mode):
                    ready = False
        return ready

    def _evict_texture_layers(self, exclude):
        if self._texture_bytes <= self.max_texture_bytes:
            return
        candidates = sorted(
            (value for value in self.textures.values()
             if value is not exclude
             and (value['gl'].get(False) or value['gl'].get(True))),
            key=lambda value: value.get('last_used', 0),
        )
        for cached in candidates:
            self._free_gl_layers(cached)
            if self._texture_bytes <= self.max_texture_bytes:
                break

    def SetCurrentTex(self, textureID, layer=0, min_filter=None, mag_filter=None,
                      wrap_s=None, wrap_t=None):
        cached = self.textures.get(textureID)
        if cached is None:
            return False
        self._use_serial += 1
        cached['last_used'] = self._use_serial
        # No SetCurrent here -- the context is already current for the frame
        # (see get_mesh_buffers). A mid-frame make-current would reset the
        # split-pane viewport on macOS and cost a context switch per mesh.
        if cached.get('day') is None and cached.get('night') is None:
            return False
        mode = self._effective_mode(cached)
        future = cached['future'].get(mode)
        if future is not None and future.done():
            # This mode's decode finished — swap it in (frees its old set).
            self._upload_layers(cached, mode)
        layers = cached['gl'].get(mode)
        if layers is None:
            # Active-mode set not ready yet: show the other mode's layers as a
            # stand-in while it decodes, instead of flashing the red marker.
            fallback = cached['gl'].get(not mode)
            if fallback:
                layers = fallback
            elif self._upload_layers(cached, mode):
                layers = cached['gl'].get(mode)
            else:
                return False
        layers = layers or []
        if not layers:
            return False
        # The requested layer (e.g. an ATC animation plane) can run past the
        # number of decoded layers; clamp instead of raising IndexError.
        if layer >= len(layers):
            layer = len(layers) - 1
        elif layer < 0:
            layer = 0
        glBindTexture(GL_TEXTURE_2D, layers[layer])
        # Maxis default per S3D Mats wiki is NEAREST; bilinear is the special
        # case (mainly road textures). Caller passes 0 for nearest, >0 for
        # linear; None preserves the upload-time default.
        min_value = GL_LINEAR if min_filter is None or min_filter > 0 else GL_NEAREST
        mag_value = GL_LINEAR if mag_filter is None or mag_filter > 0 else GL_NEAREST
        # S3D Mats wrap values: 0 = repeat, 1 = "clamb" (Maxis-speak for
        # mirrored repeat per the wiki). None preserves upload-time default.
        wrap_s_value = GL_CLAMP_TO_EDGE if wrap_s is None else (GL_MIRRORED_REPEAT if wrap_s == 1 else GL_REPEAT)
        wrap_t_value = GL_CLAMP_TO_EDGE if wrap_t is None else (GL_MIRRORED_REPEAT if wrap_t == 1 else GL_REPEAT)
        sampler = self.glCanvas.renderer.samplers.get(
            min_value, mag_value, wrap_s_value, wrap_t_value, mipmapped=self.mipmaps,
        )
        glBindSampler(0, sampler)
        return layers[layer], sampler
