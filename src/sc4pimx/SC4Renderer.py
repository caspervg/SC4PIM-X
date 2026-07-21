"""OpenGL 3.3 core rendering infrastructure used by every SC4 preview.

The renderer deliberately exposes scene-level operations rather than the old
fixed-function state machine.  Matrices live on the CPU, geometry is submitted
through VAOs/VBOs, and textures are paired with immutable sampler objects.
"""
from __future__ import annotations

import ctypes
import functools
import logging
import math
from contextlib import contextmanager
from dataclasses import dataclass

import numpy
from OpenGL.GL import (
    GL_ARRAY_BUFFER,
    GL_BLEND,
    GL_CLAMP_TO_EDGE,
    GL_COLOR_ATTACHMENT0,
    GL_COLOR_BUFFER_BIT,
    GL_DEPTH24_STENCIL8,
    GL_DEPTH_STENCIL_ATTACHMENT,
    GL_DRAW_FRAMEBUFFER,
    GL_DYNAMIC_DRAW,
    GL_FALSE,
    GL_FLOAT,
    GL_FRAGMENT_SHADER,
    GL_FRAMEBUFFER,
    GL_FRAMEBUFFER_BINDING,
    GL_FRAMEBUFFER_COMPLETE,
    GL_LINE_LOOP,
    GL_LINE_STRIP,
    GL_LINEAR,
    GL_LINEAR_MIPMAP_LINEAR,
    GL_LINES,
    GL_MAX_SAMPLES,
    GL_NEAREST,
    GL_NEAREST_MIPMAP_NEAREST,
    GL_ONE_MINUS_SRC_ALPHA,
    GL_PACK_ALIGNMENT,
    GL_R8,
    GL_READ_FRAMEBUFFER,
    GL_RED,
    GL_RENDERBUFFER,
    GL_RGB,
    GL_RGB8,
    GL_RGBA,
    GL_RGBA8,
    GL_SRC_ALPHA,
    GL_SRGB8,
    GL_SRGB8_ALPHA8,
    GL_TEXTURE0,
    GL_TEXTURE_2D,
    GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_MIN_FILTER,
    GL_TEXTURE_WRAP_S,
    GL_TEXTURE_WRAP_T,
    GL_TRIANGLES,
    GL_TRUE,
    GL_UNPACK_ALIGNMENT,
    GL_UNSIGNED_BYTE,
    GL_VERTEX_SHADER,
    GL_VIEWPORT,
    glActiveTexture,
    glBindBuffer,
    glBindFramebuffer,
    glBindRenderbuffer,
    glBindSampler,
    glBindTexture,
    glBindVertexArray,
    glBlendFunc,
    glBlitFramebuffer,
    glBufferData,
    glBufferSubData,
    glCheckFramebufferStatus,
    glDeleteBuffers,
    glDeleteFramebuffers,
    glDeleteProgram,
    glDeleteRenderbuffers,
    glDeleteSamplers,
    glDeleteTextures,
    glDeleteVertexArrays,
    glDisable,
    glDrawArrays,
    glEnable,
    glEnableVertexAttribArray,
    glFramebufferRenderbuffer,
    glFramebufferTexture2D,
    glGenBuffers,
    glGenerateMipmap,
    glGenFramebuffers,
    glGenRenderbuffers,
    glGenSamplers,
    glGenTextures,
    glGenVertexArrays,
    glGetIntegerv,
    glGetUniformLocation,
    glIsEnabled,
    glPixelStorei,
    glReadPixels,
    glRenderbufferStorage,
    glRenderbufferStorageMultisample,
    glSamplerParameterf,
    glSamplerParameteri,
    glTexImage2D,
    glTexParameteri,
    glUniform1f,
    glUniform1i,
    glUniform2f,
    glUniformMatrix4fv,
    glUseProgram,
    glVertexAttribPointer,
    glViewport,
)
from OpenGL.GL.shaders import compileProgram, compileShader
from PIL import Image, ImageDraw, ImageFont

from . import SC4Matrix

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=64)
def _cached_rotation(degrees, x, y, z):
    """Memoized rotation matrix; treat the result as immutable.

    A lot frame issues the same few rotations (camera turn, four 90-degree
    prop orientations) hundreds of times; rebuilding the matrix each call
    dominated TransformStack.rotate.
    """
    return SC4Matrix.rotate(degrees, x, y, z)


# GL_EXT_texture_filter_anisotropic is an OpenGL 3.3 extension (core since 4.6).
# Probe for it lazily so a missing extension degrades to plain trilinear.
try:
    from OpenGL.GL.EXT.texture_filter_anisotropic import (
        GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT,
        GL_TEXTURE_MAX_ANISOTROPY_EXT,
    )
except ImportError:  # pragma: no cover - depends on the PyOpenGL build
    GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT = None
    GL_TEXTURE_MAX_ANISOTROPY_EXT = None


@dataclass(frozen=True)
class RenderingSettings:
    """Resolved graphics-quality knobs from ``[Rendering]`` in config.toml."""

    samples: int = 4
    srgb: bool = True
    mipmaps: bool = True
    anisotropy: float = 8.0


_RENDERING_SETTINGS: RenderingSettings | None = None
_MAX_ANISOTROPY: float | None = None


def rendering_settings() -> RenderingSettings:
    """Load and cache the rendering settings (config.toml is read once)."""
    global _RENDERING_SETTINGS
    if _RENDERING_SETTINGS is None:
        raw: dict = {}
        try:
            from . import config

            raw = config.load_rendering()
        except Exception:
            logger.exception("Failed to load [Rendering] config; using defaults")
        _RENDERING_SETTINGS = RenderingSettings(
            samples=max(0, int(raw.get("Samples", 4))),
            srgb=bool(raw.get("SRGB", True)),
            mipmaps=bool(raw.get("Mipmaps", True)),
            anisotropy=max(1.0, float(raw.get("Anisotropy", 8.0))),
        )
    return _RENDERING_SETTINGS


def quality_summary(samples, srgb) -> str:
    """One-line description of the *effective* rendering quality, for logging.

    ``samples`` / ``srgb`` come from the live canvas (already clamped to what
    the display actually granted, which may be less than requested); mipmaps
    and anisotropy come from config clamped to the GPU limits. Must be called
    with a current GL context (the anisotropy maximum is queried).
    """
    settings = rendering_settings()
    msaa = f"{int(samples)}x" if int(samples) > 1 else "off"
    aniso = _effective_anisotropy()
    if aniso > 1.0:
        maximum = _MAX_ANISOTROPY or aniso
        aniso_text = f"{aniso:.0f}x(max={maximum:.0f})"
    elif settings.anisotropy > 1.0:
        aniso_text = "off(unsupported)"
    else:
        aniso_text = "off"
    return (
        f"msaa={msaa} srgb={'on' if srgb else 'off'} "
        f"mipmaps={'on' if settings.mipmaps else 'off'} anisotropy={aniso_text}"
    )


def _effective_anisotropy() -> float:
    """Configured anisotropy clamped to the current GPU's maximum (1.0 = off)."""
    requested = rendering_settings().anisotropy
    if requested <= 1.0 or GL_TEXTURE_MAX_ANISOTROPY_EXT is None:
        return 1.0
    global _MAX_ANISOTROPY
    if _MAX_ANISOTROPY is None:
        try:
            from OpenGL.GL import glGetFloatv

            _MAX_ANISOTROPY = float(glGetFloatv(GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT))
        except Exception:
            _MAX_ANISOTROPY = 1.0
    return max(1.0, min(requested, _MAX_ANISOTROPY))


PRIMITIVE_VERTEX_SHADER = """#version 330 core
layout(location = 0) in vec3 a_position;
layout(location = 1) in vec4 a_color;
layout(location = 2) in vec2 a_texcoord;

uniform mat4 u_mvp;

out vec4 v_color;
out vec2 v_texcoord;

void main()
{
    gl_Position = u_mvp * vec4(a_position, 1.0);
    v_color = a_color;
    v_texcoord = a_texcoord;
}
"""


PRIMITIVE_FRAGMENT_SHADER = """#version 330 core
uniform sampler2D u_texture;
// 0 = untextured, 1 = RGBA texture, 2 = single-channel glyph atlas.
uniform int u_texture_mode;
// Context-only fade. Ordinary primitive draws keep mode 0. 1 = cursor lens,
// 2 = global ghost coverage, 4 = opaque complement outside the cursor lens.
uniform int u_fade_mode;
uniform vec2 u_fade_center;
uniform vec2 u_fade_radius;
uniform float u_fade_coverage;
// 0 = smooth alpha, 1 = fine irregular grain, 2 = ordered 4x4,
// 3 = clean cutaway.
uniform int u_fade_style;

in vec4 v_color;
in vec2 v_texcoord;
out vec4 out_color;

float bayer4(ivec2 pixel)
{
    const float values[16] = float[16](
         0.5,  8.5,  2.5, 10.5,
        12.5,  4.5, 14.5,  6.5,
         3.5, 11.5,  1.5,  9.5,
        15.5,  7.5, 13.5,  5.5
    );
    ivec2 cell = ivec2(pixel.x & 3, pixel.y & 3);
    return values[cell.y * 4 + cell.x] / 16.0;
}

float fine_noise(ivec2 pixel)
{
    vec2 p = vec2(pixel);
    return fract(52.9829189 * fract(dot(p, vec2(0.06711056, 0.00583715))));
}

void main()
{
    vec4 texel = vec4(1.0);
    if (u_texture_mode == 1)
        texel = texture(u_texture, v_texcoord);
    else if (u_texture_mode == 2)
        texel.a = texture(u_texture, v_texcoord).r;
    if (u_fade_mode == 4)
    {
        if (distance(gl_FragCoord.xy, u_fade_center) < u_fade_radius.y)
            discard;
        out_color = v_color * texel;
        return;
    }
    if (u_fade_mode != 0)
    {
        float coverage = u_fade_coverage;
        if (u_fade_mode == 1)
        {
            float distance_px = distance(gl_FragCoord.xy, u_fade_center);
            coverage = mix(
                u_fade_coverage,
                1.0,
                smoothstep(u_fade_radius.x, u_fade_radius.y, distance_px)
            );
        }
        // Vertex alpha is fade participation. Context ground uses a smaller
        // value so roads remain useful while tall obstructions become x-rayed.
        coverage = mix(1.0, coverage, clamp(v_color.a, 0.0, 1.0));
        if (u_fade_style == 0)
        {
            if (u_fade_mode == 1 && distance(gl_FragCoord.xy, u_fade_center) >= u_fade_radius.y)
                discard;
            out_color = vec4(v_color.rgb * texel.rgb, texel.a * coverage);
            return;
        }
        float threshold = u_fade_style == 1
            ? fine_noise(ivec2(gl_FragCoord.xy))
            : bayer4(ivec2(gl_FragCoord.xy));
        if (u_fade_style == 3 ? coverage < 0.999 : coverage < threshold)
            discard;
    }
    out_color = v_color * texel;
}
"""


class TransformStack:
    """Explicit column-vector scene transform stack."""

    def __init__(self, projection=None, model=None):
        self.projection = numpy.asarray(
            SC4Matrix.identity() if projection is None else projection,
            dtype=numpy.float64,
        )
        self.model = numpy.asarray(
            SC4Matrix.identity() if model is None else model,
            dtype=numpy.float64,
        )
        self._stack = []
        self._normal_cache = {}

    @property
    def mvp(self):
        return self.projection @ self.model

    @property
    def normal_matrix(self):
        # The normal matrix depends only on the model's 3x3 rotation/scale
        # part; a lot scene reuses a handful of orientations (4 rotFlags x
        # camera turn) across hundreds of props, so cache the inverse by the
        # 3x3 bytes instead of running numpy.linalg.inv per prop per frame.
        key = self.model[0:3, 0:3].tobytes()
        cached = self._normal_cache.get(key)
        if cached is None:
            if len(self._normal_cache) >= 256:
                self._normal_cache.clear()
            cached = SC4Matrix.normal_matrix(self.model)
            self._normal_cache[key] = cached
        return cached

    def load_identity(self):
        self.model = SC4Matrix.identity()

    def translate(self, x, y, z):
        self.model = self.model @ SC4Matrix.translate(x, y, z)

    def scale(self, x, y, z):
        self.model = self.model @ SC4Matrix.scale(x, y, z)

    def rotate(self, degrees, x, y, z):
        self.model = self.model @ _cached_rotation(degrees, x, y, z)

    @contextmanager
    def pushed(self):
        self._stack.append(self.model.copy())
        try:
            yield self
        finally:
            self.model = self._stack.pop()

    def unproject(self, window_x, window_y, window_z, viewport):
        """Map device-pixel window coordinates back into object coordinates."""
        vx, vy, vw, vh = (float(value) for value in viewport)
        if vw <= 0 or vh <= 0:
            return 0.0, 0.0, 0.0
        ndc = numpy.array(
            (
                (window_x - vx) * 2.0 / vw - 1.0,
                (window_y - vy) * 2.0 / vh - 1.0,
                window_z * 2.0 - 1.0,
                1.0,
            ),
            dtype=numpy.float64,
        )
        try:
            obj = numpy.linalg.inv(self.mvp) @ ndc
        except numpy.linalg.LinAlgError:
            return 0.0, 0.0, 0.0
        if abs(obj[3]) > 1.0e-12:
            obj /= obj[3]
        return float(obj[0]), float(obj[1]), float(obj[2])


class SamplerCache:
    def __init__(self):
        self._samplers = {}

    def get(self, min_filter=GL_LINEAR, mag_filter=GL_LINEAR,
            wrap_s=GL_CLAMP_TO_EDGE, wrap_t=GL_CLAMP_TO_EDGE, *, mipmapped=False):
        """Return a cached immutable sampler.

        When ``mipmapped`` is set and mipmaps are enabled the minification
        filter is promoted to a trilinear/mipmapped variant and anisotropic
        filtering is applied. Only pass ``mipmapped=True`` for textures that
        were actually uploaded with mipmaps (see :func:`create_texture_2d`).
        """
        anisotropy = 1.0
        if mipmapped and rendering_settings().mipmaps:
            if int(min_filter) == int(GL_NEAREST):
                min_filter = GL_NEAREST_MIPMAP_NEAREST
            else:
                min_filter = GL_LINEAR_MIPMAP_LINEAR
            anisotropy = _effective_anisotropy()
        key = (int(min_filter), int(mag_filter), int(wrap_s), int(wrap_t),
               round(anisotropy, 3))
        sampler = self._samplers.get(key)
        if sampler is not None:
            return sampler
        sampler = int(glGenSamplers(1))
        glSamplerParameteri(sampler, GL_TEXTURE_MIN_FILTER, key[0])
        glSamplerParameteri(sampler, GL_TEXTURE_MAG_FILTER, key[1])
        glSamplerParameteri(sampler, GL_TEXTURE_WRAP_S, key[2])
        glSamplerParameteri(sampler, GL_TEXTURE_WRAP_T, key[3])
        if anisotropy > 1.0 and GL_TEXTURE_MAX_ANISOTROPY_EXT is not None:
            glSamplerParameterf(sampler, GL_TEXTURE_MAX_ANISOTROPY_EXT, anisotropy)
        self._samplers[key] = sampler
        return sampler

    def release_gl(self):
        if self._samplers:
            values = list(self._samplers.values())
            glDeleteSamplers(len(values), values)
            self._samplers.clear()


def create_texture_2d(width, height, pixels, *, channels=4, srgb=True, mipmaps=False):
    """Create a fully initialized core-profile 2D texture.

    Texture filtering and wrapping intentionally live in sampler objects.
    OpenGL 3.3 does not guarantee immutable texture storage, so allocation uses
    glTexImage2D while all subsequent sampling state remains immutable.

    When ``mipmaps`` is requested *and* mipmaps are enabled in config a full
    mipmap chain is generated (no-op for empty/``None`` pixel data). Callers
    that opt in must request the texture through a sampler created with
    ``mipmapped=True`` to actually sample the chain.
    """
    formats = {
        1: (GL_R8, GL_RED),
        3: (GL_SRGB8 if srgb else GL_RGB8, GL_RGB),
        4: (GL_SRGB8_ALPHA8 if srgb else GL_RGBA8, GL_RGBA),
    }
    internal_format, data_format = formats[channels]
    texture = int(glGenTextures(1))
    glBindTexture(GL_TEXTURE_2D, texture)
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
    glTexImage2D(
        GL_TEXTURE_2D, 0, internal_format, int(width), int(height), 0,
        data_format, GL_UNSIGNED_BYTE, pixels,
    )
    want_mipmaps = bool(mipmaps) and pixels is not None and rendering_settings().mipmaps
    if want_mipmaps:
        glGenerateMipmap(GL_TEXTURE_2D)
    # A texture must remain complete even when no sampler is bound.
    glTexParameteri(
        GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER,
        GL_LINEAR_MIPMAP_LINEAR if want_mipmaps else GL_LINEAR,
    )
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    glBindTexture(GL_TEXTURE_2D, 0)
    return texture


class PrimitiveRenderer:
    """Streaming renderer for colored/textured triangles and line primitives."""

    _FLOATS_PER_VERTEX = 9

    def __init__(self, samplers):
        self.samplers = samplers
        # Create and bind VAO before compileProgram: macOS Core Profile requires
        # a VAO bound during shader validation or it raises ShaderValidationError.
        self.vao = int(glGenVertexArrays(1))
        self.vbo = int(glGenBuffers(1))
        glBindVertexArray(self.vao)
        self.program = compileProgram(
            compileShader(PRIMITIVE_VERTEX_SHADER, GL_VERTEX_SHADER),
            compileShader(PRIMITIVE_FRAGMENT_SHADER, GL_FRAGMENT_SHADER),
        )
        self._mvp_location = glGetUniformLocation(self.program, "u_mvp")
        self._texture_location = glGetUniformLocation(self.program, "u_texture")
        self._texture_mode_location = glGetUniformLocation(self.program, "u_texture_mode")
        self._fade_mode_location = glGetUniformLocation(self.program, "u_fade_mode")
        self._fade_center_location = glGetUniformLocation(self.program, "u_fade_center")
        self._fade_radius_location = glGetUniformLocation(self.program, "u_fade_radius")
        self._fade_coverage_location = glGetUniformLocation(self.program, "u_fade_coverage")
        self._fade_style_location = glGetUniformLocation(self.program, "u_fade_style")
        self._capacity = 0
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        stride = self._FLOATS_PER_VERTEX * 4
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 4, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(12))
        glEnableVertexAttribArray(2)
        glVertexAttribPointer(2, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(28))
        glBindVertexArray(0)
        self._font_texture = None
        self._font_glyphs = None

    def draw(self, mode, positions, mvp, *, color=(1.0, 1.0, 1.0, 1.0),
             colors=None, uvs=None, texture=0, sampler=0, texture_mode=None):
        positions = numpy.asarray(positions, dtype=numpy.float32)
        if positions.size == 0:
            return
        if positions.ndim != 2:
            positions = positions.reshape(-1, positions.shape[-1])
        if positions.shape[1] == 2:
            positions = numpy.column_stack((positions, numpy.zeros(len(positions), dtype=numpy.float32)))
        count = len(positions)
        if colors is None:
            colors = numpy.tile(numpy.asarray(color, dtype=numpy.float32), (count, 1))
        else:
            colors = numpy.asarray(colors, dtype=numpy.float32).reshape(count, 4)
        if uvs is None:
            uvs = numpy.zeros((count, 2), dtype=numpy.float32)
        else:
            uvs = numpy.asarray(uvs, dtype=numpy.float32).reshape(count, 2)
        vertices = numpy.ascontiguousarray(numpy.column_stack((positions[:, :3], colors, uvs)), dtype=numpy.float32)
        self.draw_interleaved(
            mode, vertices, mvp, texture=texture, sampler=sampler,
            texture_mode=texture_mode,
        )

    def draw_interleaved(self, mode, vertices, mvp, *, texture=0, sampler=0,
                         texture_mode=None, fade=None):
        """Draw prebuilt position/RGBA/UV rows without a per-frame array copy."""
        vertices = numpy.asarray(vertices, dtype=numpy.float32)
        if vertices.size == 0:
            return
        vertices = numpy.ascontiguousarray(vertices.reshape(-1, self._FLOATS_PER_VERTEX))
        count = len(vertices)
        byte_count = vertices.nbytes
        glBindVertexArray(self.vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        if byte_count > self._capacity:
            self._capacity = 1 << max(12, int(math.ceil(math.log2(max(byte_count, 1)))))
            glBufferData(GL_ARRAY_BUFFER, self._capacity, None, GL_DYNAMIC_DRAW)
        glBufferSubData(GL_ARRAY_BUFFER, 0, byte_count, vertices)
        glUseProgram(self.program)
        matrix = numpy.ascontiguousarray(mvp, dtype=numpy.float32)
        glUniformMatrix4fv(self._mvp_location, 1, GL_TRUE, matrix)
        glUniform1i(self._texture_location, 0)
        if texture_mode is None:
            texture_mode = 1 if texture else 0
        glUniform1i(self._texture_mode_location, int(texture_mode))
        if fade is None:
            glUniform1i(self._fade_mode_location, 0)
        else:
            fade_mode, center, radii, coverage = fade[:4]
            fade_style = fade[4] if len(fade) > 4 else 2
            glUniform1i(self._fade_mode_location, int(fade_mode))
            glUniform2f(self._fade_center_location, float(center[0]), float(center[1]))
            glUniform2f(self._fade_radius_location, float(radii[0]), float(radii[1]))
            glUniform1f(self._fade_coverage_location, float(coverage))
            glUniform1i(self._fade_style_location, int(fade_style))
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, int(texture or 0))
        glBindSampler(0, int(sampler or 0))
        glDrawArrays(mode, 0, count)
        glBindSampler(0, 0)
        glBindVertexArray(0)
        glUseProgram(0)

    def quad(self, points, mvp, *, color=(1.0, 1.0, 1.0, 1.0), colors=None,
             uvs=None, texture=0, sampler=0):
        order = (0, 1, 2, 0, 2, 3)
        positions = [points[index] for index in order]
        expanded_colors = None if colors is None else [colors[index] for index in order]
        expanded_uvs = None if uvs is None else [uvs[index] for index in order]
        self.draw(
            GL_TRIANGLES, positions, mvp, color=color, colors=expanded_colors,
            uvs=expanded_uvs, texture=texture, sampler=sampler,
        )

    def quad_batch(self, quads, mvp, *, color=(1.0, 1.0, 1.0, 1.0),
                   uv_quads=None, texture=0, sampler=0):
        """Submit multiple quads sharing one texture/render state in one draw."""
        quads = numpy.asarray(quads, dtype=numpy.float32)
        if quads.size == 0:
            return
        quads = quads.reshape(-1, 4, 3)
        order = numpy.asarray((0, 1, 2, 0, 2, 3), dtype=numpy.intp)
        positions = quads[:, order, :].reshape(-1, 3)
        uvs = None
        if uv_quads is not None:
            uv_quads = numpy.asarray(uv_quads, dtype=numpy.float32).reshape(-1, 4, 2)
            uvs = uv_quads[:, order, :].reshape(-1, 2)
        self.draw(
            GL_TRIANGLES, positions, mvp, color=color, uvs=uvs,
            texture=texture, sampler=sampler,
        )

    def rect(self, minx, miny, maxx, maxy, mvp, *, z=0.0,
             color=(1.0, 1.0, 1.0, 1.0), filled=True, width=1.0):
        points = (
            (minx, miny, z), (maxx, miny, z),
            (maxx, maxy, z), (minx, maxy, z),
        )
        if filled:
            self.quad(points, mvp, color=color)
        else:
            self.lines(points, mvp, color=color, width=width, loop=True)

    def lines(self, positions, mvp, *, color=(1.0, 1.0, 1.0, 1.0),
              width=1.0, strip=False, loop=False):
        """Draw portable pixel-width lines without relying on glLineWidth.

        OpenGL 3.3 only guarantees a native width of one pixel. Wider lines
        are expanded into clip-space triangle quads using the active viewport.
        """
        positions = numpy.asarray(positions, dtype=numpy.float64)
        if len(positions) < 2:
            return
        if positions.shape[1] == 2:
            positions = numpy.column_stack((positions, numpy.zeros(len(positions))))
        if width <= 1.0:
            mode = GL_LINE_LOOP if loop else GL_LINE_STRIP if strip else GL_LINES
            self.draw(mode, positions, mvp, color=color)
            return

        if strip or loop:
            pairs = [(index, index + 1) for index in range(len(positions) - 1)]
            if loop:
                pairs.append((len(positions) - 1, 0))
        else:
            pairs = [(index, index + 1) for index in range(0, len(positions) - 1, 2)]

        homogeneous = numpy.column_stack((positions[:, :3], numpy.ones(len(positions))))
        clip = (numpy.asarray(mvp, dtype=numpy.float64) @ homogeneous.T).T
        valid = numpy.abs(clip[:, 3]) > 1.0e-12
        ndc = numpy.zeros((len(positions), 3), dtype=numpy.float64)
        ndc[valid] = clip[valid, :3] / clip[valid, 3:4]
        viewport = glGetIntegerv(GL_VIEWPORT)
        viewport_w = max(float(viewport[2]), 1.0)
        viewport_h = max(float(viewport[3]), 1.0)
        triangles = []
        for first, second in pairs:
            if not valid[first] or not valid[second]:
                continue
            a, b = ndc[first], ndc[second]
            dx = (b[0] - a[0]) * viewport_w * 0.5
            dy = (b[1] - a[1]) * viewport_h * 0.5
            length = math.hypot(dx, dy)
            if length <= 1.0e-9:
                continue
            half = float(width) * 0.5
            offset_x = (-dy / length) * half * 2.0 / viewport_w
            offset_y = (dx / length) * half * 2.0 / viewport_h
            a_plus = (a[0] + offset_x, a[1] + offset_y, a[2])
            a_minus = (a[0] - offset_x, a[1] - offset_y, a[2])
            b_plus = (b[0] + offset_x, b[1] + offset_y, b[2])
            b_minus = (b[0] - offset_x, b[1] - offset_y, b[2])
            triangles.extend((a_plus, a_minus, b_minus, a_plus, b_minus, b_plus))
        if triangles:
            self.draw(GL_TRIANGLES, triangles, SC4Matrix.identity(), color=color)

    def _ensure_font_atlas(self):
        if self._font_texture is not None:
            return
        chars = "".join(chr(value) for value in range(32, 127))
        # Cells must be wide enough for the widest glyph at this font size or
        # capitals like 'W'/'N' get clipped on the right edge.
        cell_w, cell_h, columns = 16, 18, 16
        rows = math.ceil(len(chars) / columns)
        image = Image.new("L", (columns * cell_w, rows * cell_h), 0)
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.load_default(size=14)
        except TypeError:
            font = ImageFont.load_default()
        glyphs = {}
        for index, char in enumerate(chars):
            col, row = index % columns, index // columns
            x, y = col * cell_w, row * cell_h
            draw.text((x + 1, y), char, fill=255, font=font)
            glyphs[char] = (
                x / image.width, y / image.height,
                (x + cell_w) / image.width, (y + cell_h) / image.height,
            )
        self._font_texture = create_texture_2d(image.width, image.height, image.tobytes(), channels=1)
        self._font_glyphs = glyphs

    def text(self, x, y, text, mvp, *, color=(1.0, 1.0, 1.0, 1.0),
             scale=0.12, rotation=0.0, z=0.0, flip_y=False):
        """Draw a text string from the glyph atlas.

        ``flip_y`` mirrors the glyph vertically, which keeps text upright when
        the caller's model matrix negates Y (as the 2D lot view does). It flips
        the texture coordinates rather than the geometry so glyph rotation and
        advance are unaffected.
        """
        self._ensure_font_atlas()
        positions = []
        uvs = []
        cursor = 0.0
        c, s = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
        # Cell aspect (16:18) so glyphs aren't horizontally squashed.
        glyph_w, glyph_h = 10.6 * scale, 12.0 * scale
        for char in str(text):
            u0, v0, u1, v1 = self._font_glyphs.get(char, self._font_glyphs["?"])
            local = (
                (cursor, 0.0), (cursor + glyph_w, 0.0),
                (cursor + glyph_w, glyph_h), (cursor, glyph_h),
            )
            quad = []
            for px, py in local:
                quad.append((x + px * c - py * s, y + px * s + py * c, z))
            order = (0, 1, 2, 0, 2, 3)
            positions.extend(quad[index] for index in order)
            if flip_y:
                glyph_uvs = ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
            else:
                glyph_uvs = ((u0, v1), (u1, v1), (u1, v0), (u0, v0))
            uvs.extend(glyph_uvs[index] for index in order)
            cursor += glyph_w * 0.78
        sampler = self.samplers.get(GL_LINEAR, GL_LINEAR, GL_CLAMP_TO_EDGE, GL_CLAMP_TO_EDGE)
        # Glyphs are an alpha mask (texture_mode 2); without blending the quad
        # fills solid with the text colour (the "yellow box" bug). Enable alpha
        # blending for the draw and restore the caller's prior blend state.
        was_blend = bool(glIsEnabled(GL_BLEND))
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        self.draw(
            GL_TRIANGLES, positions, mvp, color=color, uvs=uvs,
            texture=self._font_texture, sampler=sampler, texture_mode=2,
        )
        if not was_blend:
            glDisable(GL_BLEND)

    def release_gl(self):
        if self._font_texture:
            glDeleteTextures([self._font_texture])
            self._font_texture = None
        if self.vbo:
            glDeleteBuffers(1, [self.vbo])
            self.vbo = 0
        if self.vao:
            glDeleteVertexArrays(1, [self.vao])
            self.vao = 0
        if self.program:
            glDeleteProgram(self.program)
            self.program = 0


def _clamp_samples(samples):
    """Clamp a requested MSAA sample count to what the driver supports."""
    samples = int(samples)
    if samples <= 1:
        return 0
    try:
        maximum = int(glGetIntegerv(GL_MAX_SAMPLES))
    except Exception:
        maximum = 0
    return max(0, min(samples, maximum))


class RenderTarget:
    """Exact-size offscreen color/depth target for previews and thumbnails.

    When MSAA is enabled the scene is rendered into a multisampled colour and
    depth renderbuffer, then resolved (blitted) into a single-sample colour
    texture on :meth:`read_rgb` so antialiased thumbnails and exports come out
    smooth. The on-screen path is unchanged; this only affects offscreen
    captures, which previously had no antialiasing at all.
    """

    def __init__(self, width, height, *, srgb=True, samples=None):
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        if samples is None:
            samples = rendering_settings().samples
        self.samples = _clamp_samples(samples)
        internal_format = GL_SRGB8_ALPHA8 if srgb else GL_RGBA8

        # Single-sample resolve target: the texture glReadPixels reads from.
        self.framebuffer = int(glGenFramebuffers(1))
        self.color = create_texture_2d(self.width, self.height, None, channels=4, srgb=srgb)
        glBindFramebuffer(GL_FRAMEBUFFER, self.framebuffer)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self.color, 0)

        self._ms_fbo = 0
        self._ms_color = 0
        self.depth = int(glGenRenderbuffers(1))
        if self.samples:
            # Multisampled colour + depth live in their own framebuffer; the
            # resolve framebuffer above only carries the single-sample texture.
            self._ms_color = int(glGenRenderbuffers(1))
            glBindRenderbuffer(GL_RENDERBUFFER, self._ms_color)
            glRenderbufferStorageMultisample(
                GL_RENDERBUFFER, self.samples, internal_format, self.width, self.height,
            )
            glBindRenderbuffer(GL_RENDERBUFFER, self.depth)
            glRenderbufferStorageMultisample(
                GL_RENDERBUFFER, self.samples, GL_DEPTH24_STENCIL8, self.width, self.height,
            )
            self._ms_fbo = int(glGenFramebuffers(1))
            glBindFramebuffer(GL_FRAMEBUFFER, self._ms_fbo)
            glFramebufferRenderbuffer(
                GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, self._ms_color,
            )
            glFramebufferRenderbuffer(
                GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT, GL_RENDERBUFFER, self.depth,
            )
        else:
            glBindRenderbuffer(GL_RENDERBUFFER, self.depth)
            glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH24_STENCIL8, self.width, self.height)
            glFramebufferRenderbuffer(
                GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT, GL_RENDERBUFFER, self.depth,
            )

        status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        if status != GL_FRAMEBUFFER_COMPLETE:
            self.release_gl()
            raise RuntimeError(f"Incomplete OpenGL framebuffer: 0x{status:04X}")

    @property
    def _draw_framebuffer(self):
        """The framebuffer the scene is rendered into."""
        return self._ms_fbo or self.framebuffer

    @contextmanager
    def bound(self):
        old_framebuffer = int(glGetIntegerv(GL_FRAMEBUFFER_BINDING))
        old_viewport = tuple(int(value) for value in glGetIntegerv(GL_VIEWPORT))
        glBindFramebuffer(GL_FRAMEBUFFER, self._draw_framebuffer)
        glViewport(0, 0, self.width, self.height)
        try:
            yield self
        finally:
            glBindFramebuffer(GL_FRAMEBUFFER, old_framebuffer)
            glViewport(*old_viewport)

    def _resolve(self):
        """Blit the multisampled buffer down into the single-sample texture."""
        if not self._ms_fbo:
            return
        glBindFramebuffer(GL_READ_FRAMEBUFFER, self._ms_fbo)
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, self.framebuffer)
        glBlitFramebuffer(
            0, 0, self.width, self.height,
            0, 0, self.width, self.height,
            GL_COLOR_BUFFER_BIT, GL_NEAREST,
        )

    def read_rgb(self, x=0, y=0, width=None, height=None):
        width = self.width if width is None else int(width)
        height = self.height if height is None else int(height)
        self._resolve()
        glBindFramebuffer(GL_READ_FRAMEBUFFER, self.framebuffer)
        glPixelStorei(GL_PACK_ALIGNMENT, 1)
        return glReadPixels(int(x), int(y), width, height, GL_RGB, GL_UNSIGNED_BYTE)

    def release_gl(self):
        if getattr(self, "_ms_fbo", 0):
            glDeleteFramebuffers(1, [self._ms_fbo])
            self._ms_fbo = 0
        if getattr(self, "_ms_color", 0):
            glDeleteRenderbuffers(1, [self._ms_color])
            self._ms_color = 0
        if getattr(self, "depth", 0):
            glDeleteRenderbuffers(1, [self.depth])
            self.depth = 0
        if getattr(self, "color", 0):
            glDeleteTextures([self.color])
            self.color = 0
        if getattr(self, "framebuffer", 0):
            glDeleteFramebuffers(1, [self.framebuffer])
            self.framebuffer = 0


@dataclass
class RenderDevice:
    samplers: SamplerCache
    primitives: PrimitiveRenderer
    resources: list

    @classmethod
    def create(cls):
        samplers = SamplerCache()
        return cls(samplers=samplers, primitives=PrimitiveRenderer(samplers), resources=[])

    def register(self, resource):
        if resource not in self.resources:
            self.resources.append(resource)
        return resource

    def release_gl(self):
        for resource in reversed(self.resources):
            try:
                resource.release_gl()
            except Exception:
                logger.exception("Failed to release GL resource %r", resource)
        self.resources.clear()
        self.primitives.release_gl()
        self.samplers.release_gl()
