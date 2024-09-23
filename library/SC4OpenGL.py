# uncompyle6 version 2.11.5
# Python bytecode 2.4 (62061)
# Decompiled from: Python 2.7.18 (default, Oct 15 2023, 16:43:11) 
# [GCC 11.4.0]
# Embedded file name: SC4OpenGL.pyo
# Compiled at: 2008-05-13 08:48:33
import wx
import math
try:
    from wx import glcanvas
    haveGLCanvas = True
except ImportError:
    haveGLCanvas = False

try:
    from OpenGL.GL import *
    from OpenGL.GLU import *
    from OpenGL.GLUT import *
    haveOpenGL = True
except ImportError:
    haveOpenGL = False

if haveOpenGL:
    print 'haveOpenGL'
else:
    print 'Download the GLU32.dll and GLUT32.dll from http://www.dll-files.com/ and put them in SC4PIM folder'

class MyCanvasBase(glcanvas.GLCanvas):

    def __init__(self, parent, size=(256, 256)):
        glcanvas.GLCanvas.__init__(self, parent, -1, size=size)
        self.displayer = None
        self.init = False
        self.mouseX = self.mouseY = 30
        self.lastx = self.x = 30
        self.lasty = self.y = 30
        self.dx = self.dy = 0
        self.clicX = self.clicY = 0
        self.size = None
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnMouseDown)
        self.Bind(wx.EVT_LEFT_UP, self.OnMouseUp)
        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        return

    def OnEraseBackground(self, event):
        pass

    def Text2D(self, x, y, text, rot2D, scaling):
        glPushMatrix()
        glTranslatef(x, y, 0)
        glRotatef(-rot2D, 0, 0, 1)
        glScalef(0.02, -0.02, 0.02)
        for c in text:
            glutStrokeCharacter(GLUT_STROKE_ROMAN, ord(c))

        glPopMatrix()

    def OnSize(self, event):
        size = self.size = self.GetClientSize()
        if self.GetContext():
            self.SetCurrent()
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

    def OnPaint(self, event):
        dc = wx.PaintDC(self)
        self.SetCurrent()
        if not self.init:
            if self.displayer:
                self.displayer.InitGL()
                self.init = True
        if self.init and self.displayer:
            self.displayer.OnDraw()

    def OnMouseDown(self, evt):
        self.CaptureMouse()
        self.clicX, self.clicY = self.x, self.y = self.lastx, self.lasty = evt.GetPosition()

    def OnMouseUp(self, evt):
        try:
            self.ReleaseMouse()
        except:
            pass

    def OnMouseMotion(self, evt):
        self.mouseX, self.mouseY = evt.GetPosition()
        if evt.Dragging() and evt.LeftIsDown():
            self.lastx, self.lasty = self.x, self.y
            self.x, self.y = evt.GetPosition()
            self.dx = self.x - self.lastx
            self.dy = self.y - self.lasty
            self.Refresh(False)


def RotateAroundX(angle, v):
    cosa = math.cos(math.radians(angle))
    sina = math.sin(math.radians(angle))
    return (
     v[0], v[1] * cosa + v[2] * sina, -v[1] * sina + v[2] * cosa)


def RotateAroundY(angle, v):
    cosa = math.cos(math.radians(angle))
    sina = math.sin(math.radians(angle))
    return (
     v[0] * cosa - v[2] * sina, v[1], v[0] * sina + v[2] * cosa)


def Translation(dir, v):
    return (
     v[0] + dir[0], v[1] + dir[1], v[2] + dir[2])
# okay decompiling SC4OpenGL.pyo
