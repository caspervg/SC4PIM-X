"""ATC (Animated Texture Catalog) OpenGL 3.3 viewer."""
from OpenGL.GL import (
    GL_COLOR_BUFFER_BIT,
    GL_DEPTH_BUFFER_BIT,
    GL_DEPTH_TEST,
    glClear,
    glClearColor,
    glClearDepth,
    glDisable,
    glViewport,
)
from wx import Size

from sc4pimx import SC4Matrix
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

    def refresh(self, erase_background):
        self.opengl_canvas.displayer = self
        self.opengl_canvas.Refresh(erase_background)

    def init_gl(self):
        self.opengl_canvas.displayer = self
        self.opengl_canvas.SetCurrent()
        glClearColor(0.15, 0.17, 0.20, 0.0)
        glClearDepth(1.0)

    def reinitialize(self):
        self.opengl_canvas.displayer = self

    def draw_background(self):
        width, height = self.opengl_canvas.GetPhysicalSize()
        width, height = max(width, 1), max(height, 1)
        glViewport(0, 0, width, height)
        glDisable(GL_DEPTH_TEST)
        projection = SC4Matrix.ortho(0, 1, 0, 1, -1, 1)
        self.opengl_canvas.renderer.primitives.quad(
            ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)),
            projection,
            colors=(
                (0.15, 0.17, 0.20, 1), (0.15, 0.17, 0.20, 1),
                (0.36, 0.39, 0.42, 1), (0.36, 0.39, 0.42, 1),
            ),
        )

    def on_draw(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self.draw_background()
        if self.s3d_mesh is None:
            self.opengl_canvas.SwapBuffers()
            return

        self.size = self.opengl_canvas.GetClientSize()
        width, height = self.opengl_canvas.GetPhysicalSize()
        glViewport(0, 0, width, height)
        if self.use_best_fit:
            projection = SC4Matrix.ortho(
                -self.s3d_mesh.size[0], self.s3d_mesh.size[0],
                -self.s3d_mesh.size[1], self.s3d_mesh.size[1], -1000, 1000,
            )
        else:
            val_width = self.size[0] / 4.0
            val_height = self.size[1] / 4.0
            projection = SC4Matrix.ortho(
                -val_width, val_width, -val_height, val_height, -1000, 1000,
            )
        self.s3d_mesh.DrawGL(
            self.s3d_textures_holder,
            self.opengl_canvas.renderer,
            projection,
            SC4Matrix.identity(),
        )
        self.opengl_canvas.SwapBuffers()
