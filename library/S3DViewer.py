"""S3D 3D model viewer with OpenGL rendering."""
from SC4OpenGL import *
from S3DTexturesHolder import *
import numpy as np

class S3DViewer(object):
    __module__ = __name__
    zoomScale = [1.0 / 16.0, 1.0 / 8.0, 1.0 / 4.0, 1.0 / 2.0, 1]

    def __init__(self, S3DMesh, openGLCanvas):
        self.openGLCanvas = openGLCanvas
        self.openGLCanvas.displayer = self
        self.S3DMesh = S3DMesh
        self.s3DTexturesHolder = S3DTexturesHolder(self.openGLCanvas)
        self.useBestFit = True
        self.zoom = 4
        self.angleMul = 1
        self.preAngle = 0
        self.drawAxis = True

    def Refresh(self, b):
        self.openGLCanvas.displayer = self
        self.openGLCanvas.Refresh(b)

    def InitGL(self):
        self.openGLCanvas.displayer = self
        self.openGLCanvas.SetCurrent()
        self.drawAxis = True
        glClearColor(0.0, 0.0, 0.0, 0.0)
        glClearDepth(1.0)
        glShadeModel(GL_SMOOTH)
        glMatrixMode(GL_MODELVIEW)
        glDisable(GL_CULL_FACE)

    def Reinit(self):
        self.openGLCanvas.displayer = self
        if self.S3DMesh == None:
            return
        self.posy = self.S3DMesh.miny
        self.posx = (self.S3DMesh.maxx + self.S3DMesh.minx) / 2.0
        self.posz = (self.S3DMesh.maxz + self.S3DMesh.minz) / 2.0
        return

    def OnDraw(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if self.S3DMesh == None:
            self.openGLCanvas.SwapBuffers()
            return
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        if self.useBestFit:
            angleX = 45
        else:
            if self.zoom == 4 or self.zoom == 3:
                angleX = 45
            else:
                if self.zoom == 2:
                    angleX = 40
                else:
                    if self.zoom == 1:
                        angleX = 35
                    elif self.zoom == 0:
                        angleX = 30
                    if self.useBestFit:
                        p = []

                        def Corner(mesh, c):
                            v = [0, 0, 0]
                            if c & 1 == 1:
                                v[0] = mesh.maxx
                            else:
                                v[0] = mesh.minx
                            if c & 4 == 4:
                                v[1] = mesh.maxy
                            else:
                                v[1] = mesh.miny
                            if c & 2 == 2:
                                v[2] = mesh.maxz
                            else:
                                v[2] = mesh.minz
                            return v

                        for i in range(8):
                            r = RotateAroundX(-self.angleMul * angleX, RotateAroundY(22.5 - self.preAngle, Corner(self.S3DMesh, i)))
                            p.append(r)

                        xs = [ c[0] for c in p ]
                        ys = [ c[1] for c in p ]
                        zs = [ c[2] for c in p ]
                        minX = min(xs)
                        minY = min(ys)
                        maxX = max(xs)
                        maxY = max(ys)
                        minZ = min(zs)
                        maxZ = max(zs)
                        diffX = maxX - minX
                        diffY = maxY - minY
                        diff = max(diffX, diffY)
                        self.posx = (maxX + minX) / 2.0
                        self.posy = (maxY + minY) / 2.0
                        self.posz = maxZ
                        diff = diff * 1.1
                        maxX = diff / 2.0
                        minX = -diff / 2.0
                        maxY = diff / 2.0
                        minY = -diff / 2.0
                        size = self.size = self.openGLCanvas.GetClientSize()
                        w = self.size[0]
                        h = self.size[1]
                        if w > h:
                            w = h
                        if h > w:
                            h = w
                        glViewport(0, 0, w, h)
                        glOrtho(minX, maxX, minY, maxY, 40000, -40000)
                    size = self.size = self.openGLCanvas.GetClientSize()
                    w = self.size[0]
                    h = self.size[1]
                    valW = w * 20.0 / 400.0
                    valH = h * 20.0 / 400.0
                    glViewport(0, 0, w, h)
                    glOrtho(-valW, valW, -valH, valH, 40000, -40000)
                glMatrixMode(GL_MODELVIEW)
                glLoadIdentity()
                self.rx = self.angleMul * angleX
                self.ry = -22.5 + self.preAngle
                self.rz = 0
                glScalef(1, 1, -1)
                if not self.useBestFit:
                    scaling = S3DViewer.zoomScale[self.zoom]
                    glScalef(scaling, scaling, scaling)
                    self.posx -= self.openGLCanvas.dx * 0.25
                    self.posy += self.openGLCanvas.dy * 0.25
                    self.openGLCanvas.dx = 0
                    self.openGLCanvas.dy = 0
            glTranslate(-self.posx, -self.posy, -self.posz)
            glRotatef(self.rx, 1.0, 0.0, 0.0)
            glRotatef(self.ry, 0.0, 1.0, 0.0)
            glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
            glDisable(GL_TEXTURE_2D)
            glColor3f(0.0, 0.5, 1.0)
            if self.drawAxis:
                glColor3f(1.0, 0.0, 0.0)
                glBegin(GL_LINES)
                glVertex3f(0, 0, 0)
                glVertex3f(self.S3DMesh.bboxX * 2, 0, 0)
                glEnd()
                glColor3f(0.0, 1.0, 0.0)
                glBegin(GL_LINES)
                glVertex3f(0, 0, 0)
                glVertex3f(0, self.S3DMesh.bboxY * 2, 0)
                glEnd()
                glColor3f(0.0, 0.0, 1.0)
                glBegin(GL_LINES)
                glVertex3f(0, 0, 0)
                glVertex3f(0, 0, self.S3DMesh.bboxZ * 2)
                glEnd()
                glColor3f(1.0, 1.0, 0.0)
                glBegin(GL_LINES)
                glVertex3f(self.S3DMesh.minx, self.S3DMesh.miny, self.S3DMesh.minz)
                glVertex3f(self.S3DMesh.minx, self.S3DMesh.maxy, self.S3DMesh.minz)
                glVertex3f(self.S3DMesh.maxx, self.S3DMesh.miny, self.S3DMesh.minz)
                glVertex3f(self.S3DMesh.maxx, self.S3DMesh.maxy, self.S3DMesh.minz)
                glVertex3f(self.S3DMesh.minx, self.S3DMesh.miny, self.S3DMesh.maxz)
                glVertex3f(self.S3DMesh.minx, self.S3DMesh.maxy, self.S3DMesh.maxz)
                glVertex3f(self.S3DMesh.maxx, self.S3DMesh.miny, self.S3DMesh.maxz)
                glVertex3f(self.S3DMesh.maxx, self.S3DMesh.maxy, self.S3DMesh.maxz)
                glVertex3f(self.S3DMesh.minx, self.S3DMesh.miny, self.S3DMesh.minz)
                glVertex3f(self.S3DMesh.minx, self.S3DMesh.miny, self.S3DMesh.maxz)
                glVertex3f(self.S3DMesh.maxx, self.S3DMesh.miny, self.S3DMesh.minz)
                glVertex3f(self.S3DMesh.maxx, self.S3DMesh.miny, self.S3DMesh.maxz)
                glVertex3f(self.S3DMesh.minx, self.S3DMesh.maxy, self.S3DMesh.minz)
                glVertex3f(self.S3DMesh.minx, self.S3DMesh.maxy, self.S3DMesh.maxz)
                glVertex3f(self.S3DMesh.maxx, self.S3DMesh.maxy, self.S3DMesh.minz)
                glVertex3f(self.S3DMesh.maxx, self.S3DMesh.maxy, self.S3DMesh.maxz)
                glVertex3f(self.S3DMesh.minx, self.S3DMesh.miny, self.S3DMesh.minz)
                glVertex3f(self.S3DMesh.maxx, self.S3DMesh.miny, self.S3DMesh.minz)
                glVertex3f(self.S3DMesh.minx, self.S3DMesh.maxy, self.S3DMesh.minz)
                glVertex3f(self.S3DMesh.maxx, self.S3DMesh.maxy, self.S3DMesh.minz)
                glVertex3f(self.S3DMesh.minx, self.S3DMesh.miny, self.S3DMesh.maxz)
                glVertex3f(self.S3DMesh.maxx, self.S3DMesh.miny, self.S3DMesh.maxz)
                glVertex3f(self.S3DMesh.minx, self.S3DMesh.maxy, self.S3DMesh.maxz)
                glVertex3f(self.S3DMesh.maxx, self.S3DMesh.maxy, self.S3DMesh.maxz)
                glEnd()
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glEnable(GL_TEXTURE_2D)
        self.S3DMesh.Draw(self.s3DTexturesHolder)
        self.openGLCanvas.SwapBuffers()
        return
