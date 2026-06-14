"""S3D textures holder for OpenGL rendering."""
import logging
import os
import weakref

import numpy as np
from OpenGL.GL import (
    GL_ARRAY_BUFFER,
    GL_CLAMP_TO_EDGE,
    GL_ELEMENT_ARRAY_BUFFER,
    GL_LINEAR,
    GL_MIRRORED_REPEAT,
    GL_NEAREST,
    GL_REPEAT,
    GL_RGBA,
    GL_STATIC_DRAW,
    GL_TEXTURE_2D,
    GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_MIN_FILTER,
    GL_TEXTURE_WRAP_S,
    GL_TEXTURE_WRAP_T,
    GL_UNPACK_ALIGNMENT,
    GL_UNSIGNED_BYTE,
    GL_VIEWPORT,
    glBindBuffer,
    glBindTexture,
    glBufferData,
    glColor3f,
    glDeleteBuffers,
    glDeleteTextures,
    glDisable,
    glEnable,
    glGenBuffers,
    glGenTextures,
    glGetIntegerv,
    glPixelStorei,
    glTexParameterf,
    glTexImage2D,
    glViewport,
)
from PIL import Image

from . import FSHConverter

logger = logging.getLogger(__name__)


class _MeshGLBuffers(object):
    """Lazily-created VBO/IBO set for one S3D mesh in one GL context.

    Buffer names are valid only in the context that created them, so each
    per-canvas holder owns its own set (see S3DTexturesHolder). Geometry is
    immutable once read, so buffers are uploaded once (GL_STATIC_DRAW) and
    keyed by the S3D block index they came from.
    """

    def __init__(self):
        self._arrays = {}   # key -> array buffer name
        self._indices = {}  # key -> element buffer name
        self._ids = []

    def _make(self, target, data):
        size = len(data) if isinstance(data, (bytes, bytearray)) else data.nbytes
        name = int(glGenBuffers(1))
        glBindBuffer(target, name)
        glBufferData(target, size, data, GL_STATIC_DRAW)
        glBindBuffer(target, 0)
        self._ids.append(name)
        return name

    def array_vbo(self, key, data):
        vbo = self._arrays.get(key)
        if vbo is None:
            vbo = self._make(GL_ARRAY_BUFFER, data)
            self._arrays[key] = vbo
        return vbo

    def index_ibo(self, key, data):
        ibo = self._indices.get(key)
        if ibo is None:
            ibo = self._make(GL_ELEMENT_ARRAY_BUFFER, data)
            self._indices[key] = ibo
        return ibo

    def delete(self):
        if self._ids:
            try:
                glDeleteBuffers(len(self._ids), self._ids)
            except Exception:
                pass
        self._ids = []
        self._arrays.clear()
        self._indices.clear()


def _texture_name(value):
    return int(value)


def _delete_texture(value):
    glDeleteTextures([_texture_name(value)])


def _decode_layers(entry):
    """Decode an FSH entry into a list of (size, rgba_bytes) per layer.

    Returns None on any failure. Reads entry.content in place and clears it.
    """
    try:
        entry.read_file(None, True, True)
        nbrLayers, _trueAlpha, img, alpha, size = FSHConverter.decodeFSH(entry.content)
    except Exception:
        try:
            entry.content = None
            entry.rawContent = None
        except Exception:
            pass
        return None
    try:
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
    finally:
        entry.content = None
        entry.rawContent = None


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


class S3DTexturesHolder(object):
    __module__ = __name__

    def __init__(self, glCanvas):
        # textures[key] = {'day': entry|None, 'night': entry|None, 'gl_layers': None|list}
        # gl_layers is the uploaded GL texture names for the current night_mode.
        self.textures = {}
        self.glCanvas = glCanvas
        self.night_mode = False
        # Per-mesh VBO/IBO sets, keyed by id(mesh). A weakref guards against
        # id() reuse after a mesh is garbage-collected (a recycled id maps to a
        # different object, so we rebuild instead of handing back stale buffers).
        self._mesh_buffers = {}
        self._vp_logged = False

    def _set_current_preserving_viewport(self):
        """SetCurrent() without losing the active glViewport.

        On macOS, wx's GLCanvas.SetCurrent() (via NSOpenGLContext) resets the
        GL viewport to the full drawable. The split-screen preview sets a
        half-pane viewport once per frame and then draws both textures and
        models into it -- but models reach this holder mid-frame (texture bind
        / VBO upload), so a naked SetCurrent here silently reverts the viewport
        and the models render into the whole canvas (stretched + recentered)
        while the textures, which never call SetCurrent, stay correct. Saving
        and restoring the viewport around the call keeps the pane intact and is
        a harmless no-op on platforms that don't reset it.
        """
        try:
            saved = glGetIntegerv(GL_VIEWPORT)
        except Exception:
            saved = None
        self.glCanvas.SetCurrent()
        if saved is None:
            return
        if os.environ.get('SC4PIM_GL_DEBUG') and not self._vp_logged:
            self._vp_logged = True
            try:
                after = tuple(int(v) for v in glGetIntegerv(GL_VIEWPORT))
            except Exception:
                after = None
            logger.debug('S3DTexturesHolder SetCurrent viewport before=%s after=%s',
                         tuple(int(v) for v in saved), after)
        if int(saved[2]) > 0 and int(saved[3]) > 0:
            glViewport(int(saved[0]), int(saved[1]), int(saved[2]), int(saved[3]))

    def get_mesh_buffers(self, mesh):
        """Return this context's _MeshGLBuffers for mesh, creating it lazily."""
        self._set_current_preserving_viewport()
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
        """Toggle night-lighting composition. Invalidates uploaded textures so
        the next bind re-composes from the stored day/night entry pair.

        Returns True when the mode actually changed (caller should trigger a
        repaint), False when this was a no-op.
        """
        enabled = bool(enabled)
        if enabled == self.night_mode:
            return False
        self.night_mode = enabled
        self.glCanvas.SetCurrent()
        for cached in self.textures.values():
            self._free_gl_layers(cached)
        return True

    def _free_gl_layers(self, cached):
        layers = cached.get('gl_layers')
        if layers:
            for name in layers:
                _delete_texture(name)
        cached['gl_layers'] = None

    def Free(self):
        self.glCanvas.SetCurrent()
        for cached in self.textures.values():
            self._free_gl_layers(cached)
        self._free_mesh_buffers()

    def PrecacheTex(self, textureID, entry, night_entry=None):
        """Register a texture under textureID.

        entry is the daytime FSH entry; night_entry, when provided, is the
        nightlight sibling (typically the day instance + 0x8000 in the same
        group) — composited over day when night_mode is on.
        """
        try:
            self.glCanvas.SetCurrent()
            old = self.textures[textureID]
            self._free_gl_layers(old)
        except Exception:
            pass
        self.textures[textureID] = {'day': entry, 'night': night_entry, 'gl_layers': None}

    def _upload_layers(self, cached):
        """Decode + (optionally) blend + upload GL textures for this cache entry.

        Populates cached['gl_layers'] in place (empty list on full failure).
        """
        day = cached.get('day')
        night = cached.get('night')
        day_layers = _decode_layers(day) if day is not None else None
        night_layers = None
        if self.night_mode and night is not None:
            night_layers = _decode_layers(night)

        if self.night_mode and day_layers and night_layers:
            chosen = []
            for i, (size, day_rgba) in enumerate(day_layers):
                if i < len(night_layers):
                    n_size, night_rgba = night_layers[i]
                    if n_size == size:
                        chosen.append((size, _blend_night_over_day(day_rgba, night_rgba)))
                        continue
                chosen.append((size, day_rgba))
        elif self.night_mode and night_layers and not day_layers:
            # Pathological: night exists, day missing. Render night as-is.
            chosen = night_layers
        else:
            chosen = day_layers or []

        cached['gl_layers'] = []
        for size, rgba in chosen:
            try:
                texName = _texture_name(glGenTextures(1))
                cached['gl_layers'].append(texName)
                glBindTexture(GL_TEXTURE_2D, texName)
                glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
                # S3D buildings are often split across several FSH tiles.
                # Per-tile mipmaps can average dark padding into tile edges.
                glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size[0], size[1],
                             0, GL_RGBA, GL_UNSIGNED_BYTE, rgba)
                glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
                glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            except Exception:
                continue

    def SetCurrentTex(self, textureID, layer=0, min_filter=None, mag_filter=None,
                      wrap_s=None, wrap_t=None):
        glEnable(GL_TEXTURE_2D)
        cached = self.textures.get(textureID)
        if cached is None:
            glDisable(GL_TEXTURE_2D)
            return
        self._set_current_preserving_viewport()
        if cached.get('day') is None and cached.get('night') is None:
            glColor3f(1, 0, 0)
            glDisable(GL_TEXTURE_2D)
            return
        if cached.get('gl_layers') is None:
            self._upload_layers(cached)
        layers = cached.get('gl_layers') or []
        if not layers:
            glDisable(GL_TEXTURE_2D)
            glColor3f(1, 1, 1)
            return
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
        if min_filter is not None:
            glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER,
                            GL_LINEAR if min_filter > 0 else GL_NEAREST)
        if mag_filter is not None:
            glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER,
                            GL_LINEAR if mag_filter > 0 else GL_NEAREST)
        # S3D Mats wrap values: 0 = repeat, 1 = "clamb" (Maxis-speak for
        # mirrored repeat per the wiki). None preserves upload-time default.
        if wrap_s is not None:
            glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S,
                            GL_MIRRORED_REPEAT if wrap_s == 1 else GL_REPEAT)
        if wrap_t is not None:
            glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T,
                            GL_MIRRORED_REPEAT if wrap_t == 1 else GL_REPEAT)
        return
