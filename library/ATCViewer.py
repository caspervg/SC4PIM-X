# uncompyle6 version 2.11.5
# Python bytecode 2.4 (62061)
# Decompiled from: Python 2.7.18 (default, Oct 15 2023, 16:43:11) 
# [GCC 11.4.0]
# Embedded file name: ATCViewer.pyo
# Compiled at: 2008-03-18 00:19:48
from SC4OpenGL import *
from S3DTexturesHolder import *

class ATCViewer(object):
    __module__ = __name__
    zoomScale = [1.0 / 16.0, 1.0 / 8.0, 1.0 / 4.0, 1.0 / 2.0, 1]

    def __init__(self, atc, openGLCanvas):
        self.openGLCanvas = openGLCanvas
        self.openGLCanvas.displayer = self
        self.s3DTexturesHolder = S3DTexturesHolder(self.openGLCanvas)
        self.S3DMesh = atc
        self.useBestFit = True
        self.zoom = 4
        self.angleMul = 1
        self.preAngle = 0

    def Refresh(self, b):
        self.openGLCanvas.displayer = self
        self.openGLCanvas.Refresh(b)

    def InitGL(self):
        self.openGLCanvas.displayer = self
        glClearColor(0.2, 0.5, 0.2, 0.0)
        glClearDepth(1.0)
        glShadeModel(GL_SMOOTH)
        glMatrixMode(GL_MODELVIEW)
        glDisable(GL_CULL_FACE)

    def Reinit(self):
        self.openGLCanvas.displayer = self
        if self.S3DMesh == None:
            return
        return

    def OnDraw(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if self.S3DMesh == None:
            self.openGLCanvas.SwapBuffers()
            return
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        size = self.size = self.openGLCanvas.GetClientSize()
        w = self.size[0]
        h = self.size[1]
        valW = w * 1.0 / 4.0
        valH = h * 1.0 / 4.0
        glViewport(0, 0, w, h)
        if self.useBestFit:
            glOrtho(-self.S3DMesh.size[0], self.S3DMesh.size[0], -self.S3DMesh.size[1], self.S3DMesh.size[1], -1000, 1000)
        else:
            glOrtho(-valW, valW, -valH, valH, -1000, 1000)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glEnable(GL_TEXTURE_2D)
        self.S3DMesh.DrawGL(self.s3DTexturesHolder)
        self.openGLCanvas.SwapBuffers()
        return
# okay decompiling ATCViewer.pyo
