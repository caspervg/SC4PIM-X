"""ATC (Animated Texture Catalog) OpenGL viewer for SC4."""
from OpenGL.GL import (
    GL_COLOR_BUFFER_BIT,
    GL_CULL_FACE,
    GL_DEPTH_BUFFER_BIT,
    GL_FILL,
    GL_FRONT_AND_BACK,
    GL_MODELVIEW,
    GL_PROJECTION,
    GL_SMOOTH,
    GL_TEXTURE_2D,
    glClear,
    glClearColor,
    glClearDepth,
    glDisable,
    glEnable,
    glLoadIdentity,
    glMatrixMode,
    glOrtho,
    glPolygonMode,
    glShadeModel,
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
        glClearColor(0.2, 0.5, 0.2, 0.0)
        glClearDepth(1.0)
        glShadeModel(GL_SMOOTH)
        glMatrixMode(GL_MODELVIEW)
        glDisable(GL_CULL_FACE)

    def reinitialize(self):
        self.opengl_canvas.displayer = self
        if self.s3d_mesh is None:
            return

    def on_draw(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
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
