"""OpenGL 3.3 core rendering infrastructure used by every SC4 preview.

The renderer deliberately exposes scene-level operations rather than the old
fixed-function state machine.  Matrices live on the CPU, geometry is submitted
through VAOs/VBOs, and textures are paired with immutable sampler objects.
"""
from __future__ import annotations

import ctypes
import logging
import math
from contextlib import contextmanager
from dataclasses import dataclass

import numpy
from OpenGL.GL import (
    GL_ARRAY_BUFFER,
    GL_CLAMP_TO_EDGE,
    GL_COLOR_ATTACHMENT0,
    GL_DEPTH24_STENCIL8,
    GL_DEPTH_STENCIL_ATTACHMENT,
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
    GL_LINES,
    GL_PACK_ALIGNMENT,
    GL_R8,
    GL_RED,
    GL_RENDERBUFFER,
    GL_RGB,
    GL_RGB8,
    GL_RGBA,
    GL_RGBA8,
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
    glDrawArrays,
    glEnableVertexAttribArray,
    glFramebufferRenderbuffer,
    glFramebufferTexture2D,
    glGenBuffers,
    glGenFramebuffers,
    glGenRenderbuffers,
    glGenSamplers,
    glGenTextures,
    glGenVertexArrays,
    glGetIntegerv,
    glGetUniformLocation,
    glPixelStorei,
    glReadPixels,
    glRenderbufferStorage,
    glSamplerParameteri,
    glTexImage2D,
    glTexParameteri,
    glUniform1i,
    glUniformMatrix4fv,
    glUseProgram,
    glVertexAttribPointer,
    glViewport,
)
from OpenGL.GL.shaders import compileProgram, compileShader
from PIL import Image, ImageDraw, ImageFont

from . import SC4Matrix

logger = logging.getLogger(__name__)


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

in vec4 v_color;
in vec2 v_texcoord;
out vec4 out_color;

void main()
{
    vec4 texel = vec4(1.0);
    if (u_texture_mode == 1)
        texel = texture(u_texture, v_texcoord);
    else if (u_texture_mode == 2)
        texel.a = texture(u_texture, v_texcoord).r;
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

    @property
    def mvp(self):
        return self.projection @ self.model

    @property
    def normal_matrix(self):
        return SC4Matrix.normal_matrix(self.model)

    def load_identity(self):
        self.model = SC4Matrix.identity()

    def translate(self, x, y, z):
        self.model = self.model @ SC4Matrix.translate(x, y, z)

    def scale(self, x, y, z):
        self.model = self.model @ SC4Matrix.scale(x, y, z)

    def rotate(self, degrees, x, y, z):
        self.model = self.model @ SC4Matrix.rotate(degrees, x, y, z)

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
            wrap_s=GL_CLAMP_TO_EDGE, wrap_t=GL_CLAMP_TO_EDGE):
        key = (int(min_filter), int(mag_filter), int(wrap_s), int(wrap_t))
        sampler = self._samplers.get(key)
        if sampler is not None:
            return sampler
        sampler = int(glGenSamplers(1))
        glSamplerParameteri(sampler, GL_TEXTURE_MIN_FILTER, key[0])
        glSamplerParameteri(sampler, GL_TEXTURE_MAG_FILTER, key[1])
        glSamplerParameteri(sampler, GL_TEXTURE_WRAP_S, key[2])
        glSamplerParameteri(sampler, GL_TEXTURE_WRAP_T, key[3])
        self._samplers[key] = sampler
        return sampler

    def release_gl(self):
        if self._samplers:
            values = list(self._samplers.values())
            glDeleteSamplers(len(values), values)
            self._samplers.clear()


def create_texture_2d(width, height, pixels, *, channels=4, srgb=True):
    """Create a fully initialized core-profile 2D texture.

    Texture filtering and wrapping intentionally live in sampler objects.
    OpenGL 3.3 does not guarantee immutable texture storage, so allocation uses
    glTexImage2D while all subsequent sampling state remains immutable.
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
    # A texture must remain complete even when no sampler is bound.
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
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
        self.program = compileProgram(
            compileShader(PRIMITIVE_VERTEX_SHADER, GL_VERTEX_SHADER),
            compileShader(PRIMITIVE_FRAGMENT_SHADER, GL_FRAGMENT_SHADER),
        )
        self._mvp_location = glGetUniformLocation(self.program, "u_mvp")
        self._texture_location = glGetUniformLocation(self.program, "u_texture")
        self._texture_mode_location = glGetUniformLocation(self.program, "u_texture_mode")
        self.vao = int(glGenVertexArrays(1))
        self.vbo = int(glGenBuffers(1))
        self._capacity = 0
        glBindVertexArray(self.vao)
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
        cell_w, cell_h, columns = 12, 18, 16
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
             scale=0.12, rotation=0.0, z=0.0):
        self._ensure_font_atlas()
        positions = []
        uvs = []
        cursor = 0.0
        c, s = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
        glyph_w, glyph_h = 8.0 * scale, 12.0 * scale
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
            glyph_uvs = ((u0, v1), (u1, v1), (u1, v0), (u0, v0))
            uvs.extend(glyph_uvs[index] for index in order)
            cursor += glyph_w * 0.82
        sampler = self.samplers.get(GL_LINEAR, GL_LINEAR, GL_CLAMP_TO_EDGE, GL_CLAMP_TO_EDGE)
        self.draw(
            GL_TRIANGLES, positions, mvp, color=color, uvs=uvs,
            texture=self._font_texture, sampler=sampler, texture_mode=2,
        )

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


class RenderTarget:
    """Exact-size offscreen color/depth target for previews and thumbnails."""

    def __init__(self, width, height, *, srgb=True):
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.framebuffer = int(glGenFramebuffers(1))
        self.color = create_texture_2d(self.width, self.height, None, channels=4, srgb=srgb)
        self.depth = int(glGenRenderbuffers(1))
        glBindRenderbuffer(GL_RENDERBUFFER, self.depth)
        glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH24_STENCIL8, self.width, self.height)
        glBindFramebuffer(GL_FRAMEBUFFER, self.framebuffer)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self.color, 0)
        glFramebufferRenderbuffer(
            GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT, GL_RENDERBUFFER, self.depth,
        )
        status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        if status != GL_FRAMEBUFFER_COMPLETE:
            self.release_gl()
            raise RuntimeError(f"Incomplete OpenGL framebuffer: 0x{status:04X}")

    @contextmanager
    def bound(self):
        old_framebuffer = int(glGetIntegerv(GL_FRAMEBUFFER_BINDING))
        old_viewport = tuple(int(value) for value in glGetIntegerv(GL_VIEWPORT))
        glBindFramebuffer(GL_FRAMEBUFFER, self.framebuffer)
        glViewport(0, 0, self.width, self.height)
        try:
            yield self
        finally:
            glBindFramebuffer(GL_FRAMEBUFFER, old_framebuffer)
            glViewport(*old_viewport)

    def read_rgb(self, x=0, y=0, width=None, height=None):
        width = self.width if width is None else int(width)
        height = self.height if height is None else int(height)
        glPixelStorei(GL_PACK_ALIGNMENT, 1)
        return glReadPixels(int(x), int(y), width, height, GL_RGB, GL_UNSIGNED_BYTE)

    def release_gl(self):
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
