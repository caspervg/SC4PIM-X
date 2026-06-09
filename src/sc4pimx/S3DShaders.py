"""Shader support for SC4-style S3D preview lighting."""
import math

import numpy

from OpenGL.GL import (
    GL_FALSE,
    GL_FRAGMENT_SHADER,
    GL_LINK_STATUS,
    GL_MODELVIEW_MATRIX,
    GL_PROJECTION_MATRIX,
    GL_TRUE,
    GL_VERTEX_SHADER,
    glGetAttribLocation,
    glGetFloatv,
    glGetProgramInfoLog,
    glGetProgramiv,
    glGetUniformLocation,
    glUniform1f,
    glUniform1i,
    glUniform3f,
    glUniformMatrix3fv,
    glUniformMatrix4fv,
    glUseProgram,
)
from OpenGL.GL.shaders import compileProgram, compileShader


def _normalize(vec3):
    length = math.sqrt(sum(component * component for component in vec3))
    if length <= 1.0e-6:
        return (0.0, 1.0, 0.0)
    return tuple(component / length for component in vec3)


# Approximate the proven Mac GetModelLight/GetColor path:
# GetColor(terrainNormal) -> lerp toward white by (1 - terrainShadowAmount)
# -> multiply by current global light color.
DAY_PRESET = {
    'global_color': (1.0, 1.0, 1.0),
    'ambient_color': (0.05, 0.05, 0.05),
    'sun_dir': _normalize((-1.0, 1.0, 1.0)),
    'sun_color': (1.0, 1.0, 0.8),
    'sky_dir': _normalize((1.0, 0.5, -1.0)),
    'sky_color': (0.0, 0.1, 0.5),
    'terrain_normal': (0.0, 1.0, 0.0),
    'terrain_shadow_amount': 0.40,
}

NIGHT_PRESET = {
    'global_color': (0.50, 0.50, 0.50),
    'ambient_color': (0.05, 0.05, 0.05),
    'sun_dir': _normalize((-1.0, 1.0, 1.0)),
    'sun_color': (1.0, 1.0, 0.8),
    'sky_dir': _normalize((1.0, 0.5, -1.0)),
    'sky_color': (0.0, 0.1, 0.5),
    'terrain_normal': (0.0, 1.0, 0.0),
    'terrain_shadow_amount': 0.40,
}


VERTEX_SHADER = """
#version 120

// Generic vertex attributes (fed from VBOs via glVertexAttribPointer) and
// explicit matrix uniforms instead of the deprecated fixed-function built-ins
// (gl_Vertex / gl_Normal / ftransform / gl_NormalMatrix). macOS' legacy GL
// drops shaders that touch those built-ins to software vertex processing, and
// that SW path then ignores a partial glViewport -- which is what skewed the
// split-screen preview models. Staying on generic attributes keeps the model
// draw on the hardware path so it honours whatever viewport we set.
attribute vec3 a_position;
attribute vec3 a_normal;
attribute vec2 a_texcoord;

uniform mat4 u_mvp;
uniform mat3 u_normal_matrix;

varying vec2 v_texcoord;
varying vec3 v_normal;

void main(void)
{
    v_texcoord = a_texcoord;
    v_normal = normalize(u_normal_matrix * a_normal);
    gl_Position = u_mvp * vec4(a_position, 1.0);
}
"""


FRAGMENT_SHADER = """
#version 120

uniform sampler2D u_texture;
uniform vec3 u_global_color;
uniform vec3 u_ambient_color;
uniform vec3 u_sun_dir;
uniform vec3 u_sun_color;
uniform vec3 u_sky_dir;
uniform vec3 u_sky_color;
uniform vec3 u_terrain_normal;
uniform float u_terrain_shadow_amount;
uniform float u_prelit;

varying vec2 v_texcoord;
varying vec3 v_normal;

vec3 sc4_getcolor(vec3 normal)
{
    float sun_amount = max(dot(normal, normalize(u_sun_dir)), 0.0);
    float sky_amount = max(dot(normal, normalize(u_sky_dir)), 0.0);
    vec3 lit = u_ambient_color;
    lit += sun_amount * u_sun_color;
    lit += sky_amount * u_sky_color;
    return clamp(lit, 0.0, 1.0);
}

vec3 sc4_getmodellight()
{
    vec3 base = sc4_getcolor(normalize(u_terrain_normal));
    vec3 shadow_lifted = mix(base, vec3(1.0, 1.0, 1.0), 1.0 - u_terrain_shadow_amount);
    return clamp(shadow_lifted * u_global_color, 0.0, 1.0);
}

void main(void)
{
    vec4 texel = texture2D(u_texture, v_texcoord);
    vec3 lighting = mix(sc4_getmodellight(), vec3(1.0, 1.0, 1.0), u_prelit);
    gl_FragColor = vec4(texel.rgb * lighting, texel.a);
}
"""


class SC4LightingProgram:
    """Small wrapper around the S3D preview lighting shader."""

    def __init__(self):
        self.program = compileProgram(
            compileShader(VERTEX_SHADER, GL_VERTEX_SHADER),
            compileShader(FRAGMENT_SHADER, GL_FRAGMENT_SHADER),
        )
        if glGetProgramiv(self.program, GL_LINK_STATUS) != GL_TRUE:
            raise RuntimeError(glGetProgramInfoLog(self.program))
        self._uniforms = {
            'texture': glGetUniformLocation(self.program, 'u_texture'),
            'global_color': glGetUniformLocation(self.program, 'u_global_color'),
            'ambient_color': glGetUniformLocation(self.program, 'u_ambient_color'),
            'sun_dir': glGetUniformLocation(self.program, 'u_sun_dir'),
            'sun_color': glGetUniformLocation(self.program, 'u_sun_color'),
            'sky_dir': glGetUniformLocation(self.program, 'u_sky_dir'),
            'sky_color': glGetUniformLocation(self.program, 'u_sky_color'),
            'terrain_normal': glGetUniformLocation(self.program, 'u_terrain_normal'),
            'terrain_shadow_amount': glGetUniformLocation(self.program, 'u_terrain_shadow_amount'),
            'prelit': glGetUniformLocation(self.program, 'u_prelit'),
            'mvp': glGetUniformLocation(self.program, 'u_mvp'),
            'normal_matrix': glGetUniformLocation(self.program, 'u_normal_matrix'),
        }
        # Generic attribute slots, read by S3D.draw() to wire up the VBOs.
        self.attribs = {
            'position': int(glGetAttribLocation(self.program, 'a_position')),
            'normal': int(glGetAttribLocation(self.program, 'a_normal')),
            'texcoord': int(glGetAttribLocation(self.program, 'a_texcoord')),
        }

    def bind(self, lighting_state):
        glUseProgram(self.program)
        glUniform1i(self._uniforms['texture'], 0)
        self._set_vec3('global_color', lighting_state['global_color'])
        self._set_vec3('ambient_color', lighting_state['ambient_color'])
        self._set_vec3('sun_dir', lighting_state['sun_dir'])
        self._set_vec3('sun_color', lighting_state['sun_color'])
        self._set_vec3('sky_dir', lighting_state['sky_dir'])
        self._set_vec3('sky_color', lighting_state['sky_color'])
        self._set_vec3('terrain_normal', lighting_state['terrain_normal'])
        glUniform1f(
            self._uniforms['terrain_shadow_amount'],
            float(lighting_state['terrain_shadow_amount']),
        )
        glUniform1f(self._uniforms['prelit'], 1.0 if lighting_state.get('prelit') else 0.0)
        self._upload_matrices()

    def _upload_matrices(self):
        """Snapshot the current fixed-function MVP and push it as a uniform.

        Callers still set the camera and per-model placement with the legacy
        glMatrixMode/glOrtho/glScalef/glTranslate/glRotate calls; we read that
        state here (bind() runs after it is fully set up) so the shader sees
        exactly the same transform the fixed-function texture quads use.

        PyOpenGL returns GL matrices as 4x4 arrays whose C-order memory is the
        column-major GL data, i.e. the transpose of the maths matrix. So the
        upload value for u_mvp (= P*MV applied as U*v) is mv @ proj, and the
        normal matrix value (inverse-transpose of the modelview 3x3, to stay
        correct under the preview's non-uniform/negative scale) is inv(mv3).T.
        """
        mv = numpy.array(glGetFloatv(GL_MODELVIEW_MATRIX), dtype=numpy.float64).reshape(4, 4)
        proj = numpy.array(glGetFloatv(GL_PROJECTION_MATRIX), dtype=numpy.float64).reshape(4, 4)
        mvp = numpy.ascontiguousarray(mv @ proj, dtype=numpy.float32)
        glUniformMatrix4fv(self._uniforms['mvp'], 1, GL_FALSE, mvp)
        mv3 = mv[0:3, 0:3]
        try:
            normal_value = numpy.linalg.inv(mv3).T
        except numpy.linalg.LinAlgError:
            normal_value = mv3
        normal_value = numpy.ascontiguousarray(normal_value, dtype=numpy.float32)
        glUniformMatrix3fv(self._uniforms['normal_matrix'], 1, GL_FALSE, normal_value)

    def unbind(self):
        glUseProgram(0)

    def _set_vec3(self, name, value):
        glUniform3f(self._uniforms[name], float(value[0]), float(value[1]), float(value[2]))


def approximate_model_light(lighting_state):
    """CPU-side counterpart to the preview shader's GetModelLight approximation."""
    terrain_normal = _normalize(lighting_state['terrain_normal'])
    sun_dir = _normalize(lighting_state['sun_dir'])
    sky_dir = _normalize(lighting_state['sky_dir'])
    sun_amount = max(sum(a * b for a, b in zip(terrain_normal, sun_dir)), 0.0)
    sky_amount = max(sum(a * b for a, b in zip(terrain_normal, sky_dir)), 0.0)
    base = []
    for ambient, sun, sky in zip(
        lighting_state['ambient_color'],
        lighting_state['sun_color'],
        lighting_state['sky_color'],
    ):
        base.append(min(max(ambient + sun_amount * sun + sky_amount * sky, 0.0), 1.0))
    shadow_mix = 1.0 - float(lighting_state['terrain_shadow_amount'])
    lit = []
    for channel, global_channel in zip(base, lighting_state['global_color']):
        value = channel + (1.0 - channel) * shadow_mix
        lit.append(min(max(value * global_channel, 0.0), 1.0))
    return tuple(lit)
