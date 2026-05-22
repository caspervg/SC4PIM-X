"""OpenGL canvas wrapper for SC4 3D rendering."""
import math

import wx
from OpenGL.GL import (
    GL_MODELVIEW,
    GL_PROJECTION,
    glLoadIdentity,
    glMatrixMode,
    glPopMatrix,
    glPushMatrix,
    glRotatef,
    glScalef,
    glTranslatef,
    glViewport,
)
from OpenGL.GLUT import glutInit, glutStrokeCharacter
from OpenGL.GLUT.fonts import GLUT_STROKE_ROMAN
from wx import glcanvas
from wx.glcanvas import GLContext

# glutStrokeCharacter aborts the process ("called without first calling
# glutInit") unless GLUT has been initialised. Do it lazily and once.
_glut_ready = None


def _glut_available():
    global _glut_ready
    if _glut_ready is None:
        try:
            glutInit()
            _glut_ready = True
        except Exception:
            _glut_ready = False
    return _glut_ready


class MyCanvasBase(glcanvas.GLCanvas):

    @staticmethod
    def _gl_attributes(samples, depth):
        attribs = wx.glcanvas.GLAttributes()
        attribs.PlatformDefaults().MinRGBA(8, 8, 8, 8).DoubleBuffer().Depth(depth)
        if samples:
            attribs.SampleBuffers(1).Samplers(samples)
        attribs.EndList()
        return attribs

    def __init__(self, parent, size=(256, 256)):
        # Prefer a 4x-multisampled, 24-bit depth context: smooth (anti-aliased)
        # model edges and far less z-fighting. Fall back through plainer
        # configs if the display cannot supply it.
        samples = 0
        attribs = None
        for try_samples, try_depth in ((4, 24), (0, 24), (0, 16)):
            candidate = self._gl_attributes(try_samples, try_depth)
            if glcanvas.GLCanvas.IsDisplaySupported(candidate):
                attribs, samples = candidate, try_samples
                break
        if attribs is None:
            attribs = self._gl_attributes(0, 16)
        self.samples = samples
        glcanvas.GLCanvas.__init__(self, parent, attribs, size=size)
        self.context = GLContext(self)
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
        return

    def on_erase_background(self, event):
        pass

    def SetCurrent(self, context=None):
        # wxPython 4 (Phoenix) requires a GLContext argument; classic allowed
        # a no-arg call. Default to this canvas's own context so existing
        # no-arg call sites keep working.
        super().SetCurrent(context if context is not None else self.context)

    def text_2d(self, x, y, text, rot_2d, scaling):
        if not _glut_available():
            return
        glPushMatrix()
        glTranslatef(x, y, 0)
        glRotatef(-rot_2d, 0, 0, 1)
        glScalef(0.02, -0.02, 0.02)
        for c in text:
            glutStrokeCharacter(GLUT_STROKE_ROMAN, ord(c))

        glPopMatrix()

    def on_size(self, event):
        self.size = self.GetClientSize()
        if self.context:
            self.SetCurrent(self.context)
            w = self.size[0]
            h = self.size[1]
            if w > h:
                w = h
            if h > w:
                h = w
            glViewport(0, 0, w, h)
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            glMatrixMode(GL_MODELVIEW)
        event.Skip()

    def on_paint(self, event):
        self.SetCurrent(self.context)
        dc = wx.PaintDC(self)
        if not self.init:
            if self.displayer:
                self.displayer.init_gl()
                self.init = True
        if self.init and self.displayer:
            self.displayer.on_draw()

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
