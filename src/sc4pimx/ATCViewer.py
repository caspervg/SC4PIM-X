"""ATC (Animated Texture Catalog) OpenGL viewer for SC4."""
from OpenGL.GL import (
    GL_ALPHA_TEST,
    GL_BLEND,
    GL_COLOR_BUFFER_BIT,
    GL_CULL_FACE,
    GL_DEPTH_BUFFER_BIT,
    GL_DEPTH_TEST,
    GL_FILL,
    GL_FRONT_AND_BACK,
    GL_MODELVIEW,
    GL_PROJECTION,
    GL_QUADS,
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
    glShadeModel,
    glVertex3f,
    glViewport,
)
from wx import Size

from sc4pimx.S3DTexturesHolder import S3DTexturesHolder


class ATCViewer(object):
    ZOOM_SCALE = [1.0 / 16.0, 1.0 / 8.0, 1.0 / 4.0, 1.0 / 2.0, 1.0]

    def __init__(self, atc, opengl_canvas):
        self.opengl_canvas = opengl_canvas
        self.opengl_canvas.displayer = self
        self.s3d_textures_holder = S3DTexturesHolder(self.opengl_canvas)
        self.s3d_mesh = atc
        self.use_best_fit = True
        self.size = Size(0, 0)
        self.zoom = 4
        self.angle_mul = 1
        self.pre_angle = 0

    def refresh(self, b):
        self.opengl_canvas.displayer = self
        self.opengl_canvas.Refresh(b)

    def init_gl(self):
        self.opengl_canvas.displayer = self
        glClearColor(0.15, 0.17, 0.20, 0.0)
        glClearDepth(1.0)
        glShadeModel(GL_SMOOTH)
        glMatrixMode(GL_MODELVIEW)
        glDisable(GL_CULL_FACE)

    def reinitialize(self):
        self.opengl_canvas.displayer = self
        if self.s3d_mesh is None:
            return

    def draw_background(self):
        size = self.opengl_canvas.GetClientSize()
        w = max(size[0], 1)
        h = max(size[1], 1)
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, 1, 0, 1, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glDisable(GL_ALPHA_TEST)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_BLEND)
        glBegin(GL_QUADS)
        glColor3f(0.15, 0.17, 0.20)
        glVertex3f(0, 0, 0)
        glVertex3f(1, 0, 0)
        glColor3f(0.36, 0.39, 0.42)
        glVertex3f(1, 1, 0)
        glVertex3f(0, 1, 0)
        glEnd()
        glColor3f(1.0, 1.0, 1.0)

    def on_draw(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self.draw_background()
        if self.s3d_mesh is None:
            self.opengl_canvas.SwapBuffers()
            return

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        self.size = self.opengl_canvas.GetClientSize()
        w = self.size[0]
        h = self.size[1]
        val_width = w * 1.0 / 4.0
        val_height = h * 1.0 / 4.0
        glViewport(0, 0, w, h)
        if self.use_best_fit:
            glOrtho(-self.s3d_mesh.size[0], self.s3d_mesh.size[0], -self.s3d_mesh.size[1], self.s3d_mesh.size[1], -1000,
                    1000)
        else:
            glOrtho(-val_width, val_width, -val_height, val_height, -1000, 1000)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glEnable(GL_TEXTURE_2D)
        self.s3d_mesh.DrawGL(self.s3d_textures_holder)
        self.opengl_canvas.SwapBuffers()
