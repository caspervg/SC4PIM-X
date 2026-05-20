"""S3D 3D model viewer with OpenGL rendering."""
from OpenGL.GL import (
    GL_COLOR_BUFFER_BIT,
    GL_CULL_FACE,
    GL_DEPTH_BUFFER_BIT,
    GL_FILL,
    GL_FRONT_AND_BACK,
    GL_LINE,
    GL_LINES,
    GL_MODELVIEW,
    GL_PROJECTION,
    GL_SMOOTH,
    GL_TEXTURE_2D,
    glBegin,
    glClear,
    glClearColor,
    glClearDepth,
    glColor3f,
    glDisable,
    glEnable,
    glEnd,
    glLoadIdentity,
    glMatrixMode,
    glOrtho,
    glPolygonMode,
    glRotatef,
    glScalef,
    glShadeModel,
    glTranslate,
    glVertex3f,
    glViewport,
)

from .S3DTexturesHolder import S3DTexturesHolder
from .SC4OpenGL import rotate_around_x, rotate_around_y


class S3DViewer(object):
    __module__ = __name__
    zoomScale = [1.0 / 16.0, 1.0 / 8.0, 1.0 / 4.0, 1.0 / 2.0, 1]

    def __init__(self, S3DMesh, openGLCanvas):
        self.openGLCanvas = openGLCanvas
        self.openGLCanvas.displayer = self
        self.s3d_mesh = S3DMesh
        self.s3d_textures_holder = S3DTexturesHolder(self.openGLCanvas)
        self.use_best_fit = True
        self.zoom = 4
        self.angle_mul = 1
        self.pre_angle = 0
        self.drawAxis = True

    @property
    def useBestFit(self):
        return self.use_best_fit

    @useBestFit.setter
    def useBestFit(self, value):
        self.use_best_fit = value

    @property
    def angleMul(self):
        return self.angle_mul

    @angleMul.setter
    def angleMul(self, value):
        self.angle_mul = value

    @property
    def preAngle(self):
        return self.pre_angle

    @preAngle.setter
    def preAngle(self, value):
        self.pre_angle = value

    def refresh(self, b):
        self.openGLCanvas.displayer = self
        self.openGLCanvas.Refresh(b)

    def init_gl(self):
        self.openGLCanvas.displayer = self
        self.openGLCanvas.SetCurrent()
        self.drawAxis = True
        glClearColor(0.0, 0.0, 0.0, 0.0)
        glClearDepth(1.0)
        glShadeModel(GL_SMOOTH)
        glMatrixMode(GL_MODELVIEW)
        glDisable(GL_CULL_FACE)

    def reinitialize(self):
        self.openGLCanvas.displayer = self
        if self.s3d_mesh is None:
            return
        self.posy = self.s3d_mesh.miny
        self.posx = (self.s3d_mesh.maxx + self.s3d_mesh.minx) / 2.0
        self.posz = (self.s3d_mesh.maxz + self.s3d_mesh.minz) / 2.0
        return

    def on_draw(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if self.s3d_mesh is None:
            self.openGLCanvas.SwapBuffers()
            return
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        if self.use_best_fit:
            angleX = 45
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
                r = rotate_around_x(-self.angle_mul * angleX,
                                    rotate_around_y(22.5 - self.pre_angle, Corner(self.s3d_mesh, i)))
                p.append(r)

            xs = [c[0] for c in p]
            ys = [c[1] for c in p]
            zs = [c[2] for c in p]
            minX = min(xs)
            minY = min(ys)
            maxX = max(xs)
            maxY = max(ys)
            maxZ = max(zs)
            diffX = maxX - minX
            diffY = maxY - minY
            diff = max(diffX, diffY) * 1.1
            self.posx = (maxX + minX) / 2.0
            self.posy = (maxY + minY) / 2.0
            self.posz = maxZ
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
        else:
            if self.zoom == 4 or self.zoom == 3:
                angleX = 45
            elif self.zoom == 2:
                angleX = 40
            elif self.zoom == 1:
                angleX = 35
            else:
                angleX = 30
            size = self.size = self.openGLCanvas.GetClientSize()
            w = self.size[0]
            h = self.size[1]
            valW = w * 20.0 / 400.0
            valH = h * 20.0 / 400.0
            glViewport(0, 0, w, h)
            glOrtho(-valW, valW, -valH, valH, 40000, -40000)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        self.rx = self.angle_mul * angleX
        self.ry = -22.5 + self.pre_angle
        self.rz = 0
        glScalef(1, 1, -1)
        if not self.use_best_fit:
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
            glVertex3f(self.s3d_mesh.bboxX * 2, 0, 0)
            glEnd()
            glColor3f(0.0, 1.0, 0.0)
            glBegin(GL_LINES)
            glVertex3f(0, 0, 0)
            glVertex3f(0, self.s3d_mesh.bboxY * 2, 0)
            glEnd()
            glColor3f(0.0, 0.0, 1.0)
            glBegin(GL_LINES)
            glVertex3f(0, 0, 0)
            glVertex3f(0, 0, self.s3d_mesh.bboxZ * 2)
            glEnd()
            glColor3f(1.0, 1.0, 0.0)
            glBegin(GL_LINES)
            glVertex3f(self.s3d_mesh.minx, self.s3d_mesh.miny, self.s3d_mesh.minz)
            glVertex3f(self.s3d_mesh.minx, self.s3d_mesh.maxy, self.s3d_mesh.minz)
            glVertex3f(self.s3d_mesh.maxx, self.s3d_mesh.miny, self.s3d_mesh.minz)
            glVertex3f(self.s3d_mesh.maxx, self.s3d_mesh.maxy, self.s3d_mesh.minz)
            glVertex3f(self.s3d_mesh.minx, self.s3d_mesh.miny, self.s3d_mesh.maxz)
            glVertex3f(self.s3d_mesh.minx, self.s3d_mesh.maxy, self.s3d_mesh.maxz)
            glVertex3f(self.s3d_mesh.maxx, self.s3d_mesh.miny, self.s3d_mesh.maxz)
            glVertex3f(self.s3d_mesh.maxx, self.s3d_mesh.maxy, self.s3d_mesh.maxz)
            glVertex3f(self.s3d_mesh.minx, self.s3d_mesh.miny, self.s3d_mesh.minz)
            glVertex3f(self.s3d_mesh.minx, self.s3d_mesh.miny, self.s3d_mesh.maxz)
            glVertex3f(self.s3d_mesh.maxx, self.s3d_mesh.miny, self.s3d_mesh.minz)
            glVertex3f(self.s3d_mesh.maxx, self.s3d_mesh.miny, self.s3d_mesh.maxz)
            glVertex3f(self.s3d_mesh.minx, self.s3d_mesh.maxy, self.s3d_mesh.minz)
            glVertex3f(self.s3d_mesh.minx, self.s3d_mesh.maxy, self.s3d_mesh.maxz)
            glVertex3f(self.s3d_mesh.maxx, self.s3d_mesh.maxy, self.s3d_mesh.minz)
            glVertex3f(self.s3d_mesh.maxx, self.s3d_mesh.maxy, self.s3d_mesh.maxz)
            glVertex3f(self.s3d_mesh.minx, self.s3d_mesh.miny, self.s3d_mesh.minz)
            glVertex3f(self.s3d_mesh.maxx, self.s3d_mesh.miny, self.s3d_mesh.minz)
            glVertex3f(self.s3d_mesh.minx, self.s3d_mesh.maxy, self.s3d_mesh.minz)
            glVertex3f(self.s3d_mesh.maxx, self.s3d_mesh.maxy, self.s3d_mesh.minz)
            glVertex3f(self.s3d_mesh.minx, self.s3d_mesh.miny, self.s3d_mesh.maxz)
            glVertex3f(self.s3d_mesh.maxx, self.s3d_mesh.miny, self.s3d_mesh.maxz)
            glVertex3f(self.s3d_mesh.minx, self.s3d_mesh.maxy, self.s3d_mesh.maxz)
            glVertex3f(self.s3d_mesh.maxx, self.s3d_mesh.maxy, self.s3d_mesh.maxz)
            glEnd()
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glEnable(GL_TEXTURE_2D)
        self.s3d_mesh.draw(self.s3d_textures_holder)
        self.openGLCanvas.SwapBuffers()
        return
