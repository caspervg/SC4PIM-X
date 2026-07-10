"""S3D 3D model viewer with OpenGL rendering."""
from OpenGL.GL import (
    GL_BLEND,
    GL_COLOR_BUFFER_BIT,
    GL_CULL_FACE,
    GL_DEPTH_BUFFER_BIT,
    GL_DEPTH_TEST,
    GL_LINES,
    GL_MULTISAMPLE,
    glClear,
    glClearColor,
    glClearDepth,
    glDisable,
    glEnable,
    glViewport,
)

from . import SC4Matrix
from .S3DShaders import DAY_PRESET, NIGHT_PRESET, SC4LightingProgram
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
        self.shader_program = None
        self.is_night = False
        self.is_prelit = False
        self.lighting_state = dict(DAY_PRESET)

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
        glClearColor(0.23, 0.25, 0.28, 0.0)
        glClearDepth(1.0)
        glEnable(GL_MULTISAMPLE)  # anti-aliased edges when an MSAA buffer exists
        glDisable(GL_CULL_FACE)
        if self.shader_program is None:
            self.shader_program = self.openGLCanvas.renderer.register(SC4LightingProgram())
        self._update_lighting_state()

    def reinitialize(self):
        self.openGLCanvas.displayer = self
        if self.s3d_mesh is None:
            return
        self.posy = self.s3d_mesh.miny
        self.posx = (self.s3d_mesh.maxx + self.s3d_mesh.minx) / 2.0
        self.posz = (self.s3d_mesh.maxz + self.s3d_mesh.minz) / 2.0
        return

    def on_draw(self):
        self.render_frame()
        self.openGLCanvas.SwapBuffers()

    def render_frame(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self.draw_background()
        if self.s3d_mesh is None:
            return
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
            diff = max(diffX, diffY, 1e-6) * 1.1
            self.posx = (maxX + minX) / 2.0
            self.posy = (maxY + minY) / 2.0
            self.posz = maxZ
            self.size = self.openGLCanvas.GetClientSize()
            w, h = self.openGLCanvas.GetPhysicalSize()
            if w > h:
                w = h
            if h > w:
                h = w
            glViewport(0, 0, w, h)
            proj_l, proj_r, proj_b, proj_t = -diff / 2.0, diff / 2.0, -diff / 2.0, diff / 2.0
        else:
            if self.zoom == 4 or self.zoom == 3:
                angleX = 45
            elif self.zoom == 2:
                angleX = 40
            elif self.zoom == 1:
                angleX = 35
            else:
                angleX = 30
            self.size = self.openGLCanvas.GetClientSize()
            w, h = self.openGLCanvas.GetPhysicalSize()
            w = max(w, 1)
            h = max(h, 1)
            valW = w * 20.0 / 400.0
            valH = h * 20.0 / 400.0
            glViewport(0, 0, w, h)
            proj_l, proj_r, proj_b, proj_t = -valW, valW, -valH, valH
        self.rx = self.angle_mul * angleX
        self.ry = -22.5 + self.pre_angle
        self.rz = 0
        mv = SC4Matrix.scale(1, 1, -1)
        if not self.use_best_fit:
            scaling = S3DViewer.zoomScale[self.zoom]
            mv = mv @ SC4Matrix.scale(scaling, scaling, scaling)
            self.posx -= self.openGLCanvas.dx * 0.25
            self.posy += self.openGLCanvas.dy * 0.25
            self.openGLCanvas.dx = 0
            self.openGLCanvas.dy = 0
        mv = mv @ SC4Matrix.translate(-self.posx, -self.posy, -self.posz)
        mv = mv @ SC4Matrix.rotate_x(self.rx)
        mv = mv @ SC4Matrix.rotate_y(self.ry)
        proj = SC4Matrix.ortho(proj_l, proj_r, proj_b, proj_t, 40000, -40000)
        self._model_mvp = proj @ mv
        self._model_normal = SC4Matrix.normal_matrix(mv)
        self._update_lighting_state()
        if self.drawAxis:
            self._draw_axes_and_bounds(self._model_mvp)
        self.s3d_mesh.draw(self.s3d_textures_holder, self.shader_program, self.lighting_state,
                           mvp=self._model_mvp, normal_matrix=self._model_normal)
        return

    def draw_background(self):
        w, h = self.openGLCanvas.GetPhysicalSize()
        w = max(w, 1)
        h = max(h, 1)
        glViewport(0, 0, w, h)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        projection = SC4Matrix.ortho(0, 1, 0, 1, -1, 1)
        self.openGLCanvas.renderer.primitives.quad(
            ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)),
            projection,
            colors=(
                (0.15, 0.17, 0.20, 1.0), (0.15, 0.17, 0.20, 1.0),
                (0.36, 0.39, 0.42, 1.0), (0.36, 0.39, 0.42, 1.0),
            ),
        )

    def _draw_axes_and_bounds(self, mvp):
        mesh = self.s3d_mesh
        positions = [
            (0, 0, 0), (mesh.bboxX * 2, 0, 0),
            (0, 0, 0), (0, mesh.bboxY * 2, 0),
            (0, 0, 0), (0, 0, mesh.bboxZ * 2),
        ]
        colors = [
            (1, 0, 0, 1), (1, 0, 0, 1),
            (0, 1, 0, 1), (0, 1, 0, 1),
            (0, 0, 1, 1), (0, 0, 1, 1),
        ]
        x0, x1 = mesh.minx, mesh.maxx
        y0, y1 = mesh.miny, mesh.maxy
        z0, z1 = mesh.minz, mesh.maxz
        corners = (
            (x0, y0, z0), (x1, y0, z0), (x0, y1, z0), (x1, y1, z0),
            (x0, y0, z1), (x1, y0, z1), (x0, y1, z1), (x1, y1, z1),
        )
        for a, b in ((0, 1), (2, 3), (4, 5), (6, 7),
                     (0, 2), (1, 3), (4, 6), (5, 7),
                     (0, 4), (1, 5), (2, 6), (3, 7)):
            positions.extend((corners[a], corners[b]))
            colors.extend(((1, 1, 0, 1), (1, 1, 0, 1)))
        self.openGLCanvas.renderer.primitives.draw(
            GL_LINES, positions, mvp, colors=colors,
        )

    def set_night_mode(self, enabled):
        enabled = bool(enabled)
        if enabled == self.is_night:
            return False
        self.is_night = enabled
        self._update_lighting_state()
        return True

    def set_prelit(self, enabled):
        enabled = bool(enabled)
        if enabled == self.is_prelit:
            return False
        self.is_prelit = enabled
        self._update_lighting_state()
        return True

    def _update_lighting_state(self):
        preset = NIGHT_PRESET if self.is_night else DAY_PRESET
        state = dict(preset)
        state['prelit'] = self.is_prelit
        self.lighting_state = state
