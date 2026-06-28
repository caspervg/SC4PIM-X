"""OpenGL 3.3 core canvas wrapper for SC4 rendering."""
import ctypes
import logging
import math
import os

import wx
from OpenGL.GL import (
    GL_EXTENSIONS,
    GL_FRAMEBUFFER_SRGB,
    GL_NUM_EXTENSIONS,
    GL_RENDERER,
    GL_SHADING_LANGUAGE_VERSION,
    GL_VENDOR,
    GL_VERSION,
    glEnable,
    glGetIntegerv,
    glGetString,
    glGetStringi,
    glViewport,
)
from wx import glcanvas
from wx.glcanvas import GLContext

from .SC4Renderer import RenderDevice

logger = logging.getLogger(__name__)


class MyCanvasBase(glcanvas.GLCanvas):

    @staticmethod
    def _gl_attributes(samples, depth, srgb):
        attribs = wx.glcanvas.GLAttributes()
        attribs.PlatformDefaults().MinRGBA(8, 8, 8, 8).DoubleBuffer().Depth(depth)
        if srgb:
            attribs.FrameBuffersRGB()
        if samples:
            attribs.SampleBuffers(1).Samplers(samples)
        attribs.EndList()
        return attribs

    @staticmethod
    def _context_attributes():
        attribs = wx.glcanvas.GLContextAttrs()
        attribs.PlatformDefaults().CoreProfile().OGLVersion(3, 3).ForwardCompatible()
        if os.environ.get("SC4PIM_GL_DEBUG"):
            attribs.DebugCtx()
        attribs.EndList()
        return attribs

    def __init__(self, parent, size=(256, 256)):
        # Prefer a 4x-multisampled, 24-bit depth context: smooth (anti-aliased)
        # model edges and far less z-fighting. Fall back through plainer
        # configs if the display cannot supply it.
        samples = 0
        attribs = None
        srgb = False
        for try_samples, try_depth, try_srgb in (
            (4, 24, True), (0, 24, True),
            (4, 24, False), (0, 24, False), (0, 16, False),
        ):
            candidate = self._gl_attributes(try_samples, try_depth, try_srgb)
            if glcanvas.GLCanvas.IsDisplaySupported(candidate):
                attribs, samples, srgb = candidate, try_samples, try_srgb
                break
        if attribs is None:
            attribs = self._gl_attributes(0, 16, False)
        self.samples = samples
        self.srgb = srgb
        glcanvas.GLCanvas.__init__(self, parent, attribs, size=size)
        self.context = GLContext(self, ctxAttrs=self._context_attributes())
        if not self.context.IsOK():
            raise RuntimeError("OpenGL 3.3 core profile is required")
        self.renderer = None
        self._frame_call = None
        self._debug_callback = None
        self.displayer = None
        self.init = False
        self.mouseX = self.mouseY = 30
        self.last_x = self.x = 30
        self.last_y = self.y = 30
        self.dx = self.dy = 0
        self.click_x = self.click_y = 0
        self.size = None
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.on_erase_background)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_mouse_down)
        self.Bind(wx.EVT_LEFT_UP, self.on_mouse_up)
        self.Bind(wx.EVT_MOTION, self.on_mouse_motion)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.on_destroy)
        return

    def on_erase_background(self, event):
        pass

    def SetCurrent(self, context=None):
        # wxPython 4 (Phoenix) requires a GLContext argument; classic allowed
        # a no-arg call. Default to this canvas's own context so existing
        # no-arg call sites keep working.
        super().SetCurrent(context if context is not None else self.context)
        if self.renderer is None:
            self.renderer = RenderDevice.create()
            values = {}
            for label, enum in (
                ("vendor", GL_VENDOR),
                ("renderer", GL_RENDERER),
                ("version", GL_VERSION),
                ("glsl", GL_SHADING_LANGUAGE_VERSION),
            ):
                raw = glGetString(enum)
                values[label] = raw.decode("utf-8", "replace") if raw else "unknown"
            logger.info(
                "OpenGL core context: vendor=%s renderer=%s version=%s GLSL=%s",
                values["vendor"], values["renderer"], values["version"], values["glsl"],
            )
            if self.srgb:
                glEnable(GL_FRAMEBUFFER_SRGB)
            self._install_debug_output()

    def _install_debug_output(self):
        if not os.environ.get("SC4PIM_GL_DEBUG"):
            return
        try:
            extensions = {
                glGetStringi(GL_EXTENSIONS, index).decode("ascii", "replace")
                for index in range(int(glGetIntegerv(GL_NUM_EXTENSIONS)))
            }
            if "GL_KHR_debug" not in extensions:
                logger.info("GL_KHR_debug is not available")
                return
            from OpenGL.GL.KHR.debug import (
                GL_DEBUG_OUTPUT,
                GL_DEBUG_OUTPUT_SYNCHRONOUS,
                glDebugMessageCallback,
            )

            def debug_message(_source, _kind, message_id, severity, length, message, _user):
                text = ctypes.string_at(message, length).decode("utf-8", "replace")
                logger.debug(
                    "OpenGL debug id=%s severity=0x%X: %s",
                    message_id, severity, text,
                )

            self._debug_callback = debug_message
            glEnable(GL_DEBUG_OUTPUT)
            glEnable(GL_DEBUG_OUTPUT_SYNCHRONOUS)
            glDebugMessageCallback(self._debug_callback, None)
        except Exception:
            logger.exception("Failed to enable OpenGL debug output")

    def GetPhysicalSize(self):
        """GL framebuffer size in device pixels, accounting for Retina/HiDPI.

        GetClientSize() returns logical pixels; on a 2x Retina display the
        actual OpenGL framebuffer is twice as large in each dimension.
        All glViewport and glReadPixels calls must use device pixels.
        """
        size = self.GetClientSize()
        scale = self.GetContentScaleFactor()
        return int(size[0] * scale), int(size[1] * scale)

    def on_size(self, event):
        self.size = self.GetClientSize()
        if self.context:
            self.SetCurrent(self.context)
            w, h = self.GetPhysicalSize()
            if w > h:
                w = h
            if h > w:
                h = w
            glViewport(0, 0, w, h)
        event.Skip()

    def on_paint(self, event):
        self.SetCurrent(self.context)
        _dc = wx.PaintDC(self)
        if not self.init:
            if self.displayer:
                self.displayer.init_gl()
                self.init = True
        if self.init and self.displayer:
            self.displayer.on_draw()

    def request_animation(self, delay_ms=100):
        """Request one future repaint; repeated requests coalesce per canvas."""
        if self._frame_call is not None and self._frame_call.IsRunning():
            return
        self._frame_call = wx.CallLater(max(1, int(delay_ms)), self._on_animation_frame)

    def _on_animation_frame(self):
        self._frame_call = None
        if self and self.IsShownOnScreen():
            self.Refresh(False)

    def on_destroy(self, event):
        if event.GetEventObject() is not self:
            event.Skip()
            return
        if self._frame_call is not None:
            self._frame_call.Stop()
            self._frame_call = None
        if self.renderer is not None:
            try:
                super().SetCurrent(self.context)
                self.renderer.release_gl()
            except (RuntimeError, wx.PyDeadObjectError):
                pass
            self.renderer = None
        event.Skip()

    def on_mouse_down(self, evt):
        self.CaptureMouse()
        self.click_x, self.click_y = self.x, self.y = self.last_x, self.last_y = evt.GetPosition()

    def on_mouse_up(self, _):
        try:
            self.ReleaseMouse()
        except Exception:
            pass

    def on_mouse_motion(self, evt):
        self.mouseX, self.mouseY = evt.GetPosition()
        if evt.Dragging() and evt.LeftIsDown():
            self.last_x, self.last_y = self.x, self.y
            self.x, self.y = evt.GetPosition()
            self.dx = self.x - self.last_x
            self.dy = self.y - self.last_y
            self.Refresh(False)


def rotate_around_x(angle, v):
    cosa = math.cos(math.radians(angle))
    sina = math.sin(math.radians(angle))
    return (
     v[0], v[1] * cosa + v[2] * sina, -v[1] * sina + v[2] * cosa)


def rotate_around_y(angle, v):
    cosa = math.cos(math.radians(angle))
    sina = math.sin(math.radians(angle))
    return (
     v[0] * cosa - v[2] * sina, v[1], v[0] * sina + v[2] * cosa)


def translation(direction, v):
    return (
        v[0] + direction[0], v[1] + direction[1], v[2] + direction[2])
