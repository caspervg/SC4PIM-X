"""Shader support for SC4-style S3D preview lighting."""
import math

import numpy
from OpenGL.GL import (
    GL_FRAGMENT_SHADER,
    GL_LINK_STATUS,
    GL_TRUE,
    GL_VERTEX_SHADER,
    glDeleteProgram,
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
#version 330 core

// Explicit core-profile attributes and CPU-computed matrices keep all model
// draws on the same hardware path on Windows, Linux and macOS.
layout(location = 0) in vec3 a_position;
layout(location = 1) in vec3 a_normal;
layout(location = 2) in vec2 a_texcoord;

uniform mat4 u_mvp;
uniform mat3 u_normal_matrix;
uniform int u_instanced;
uniform mat4 u_instance_mvp[32];
uniform mat3 u_instance_normal[32];

out vec2 v_texcoord;
out vec3 v_normal;

void main(void)
{
    mat4 model_mvp = u_instanced != 0 ? u_instance_mvp[gl_InstanceID] : u_mvp;
    mat3 model_normal = u_instanced != 0 ? u_instance_normal[gl_InstanceID] : u_normal_matrix;
    v_texcoord = a_texcoord;
    v_normal = normalize(model_normal * a_normal);
    gl_Position = model_mvp * vec4(a_position, 1.0);
}
"""


FRAGMENT_SHADER = """
#version 330 core

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
uniform float u_emissive;
uniform int u_alpha_func;
uniform float u_alpha_threshold;
uniform int u_textured;

in vec2 v_texcoord;
in vec3 v_normal;
out vec4 out_color;

bool alpha_passes(float alpha)
{
    if (u_alpha_func == 0) return false;
    if (u_alpha_func == 1) return alpha < u_alpha_threshold;
    if (u_alpha_func == 2) return abs(alpha - u_alpha_threshold) <= (1.0 / 255.0);
    if (u_alpha_func == 3) return alpha <= u_alpha_threshold;
    if (u_alpha_func == 4) return alpha > u_alpha_threshold;
    if (u_alpha_func == 5) return abs(alpha - u_alpha_threshold) > (1.0 / 255.0);
    if (u_alpha_func == 6) return alpha >= u_alpha_threshold;
    return true;
}

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
    vec4 texel = u_textured != 0 ? texture(u_texture, v_texcoord) : vec4(1.0, 0.0, 0.0, 1.0);
    if (!alpha_passes(texel.a))
        discard;
    // Framebuffer-blended materials (light flares / lit windows) are
    // self-illuminated: keep them full-bright so their glow is not dimmed by
    // night lighting and washed out under additive blending.
    float unlit = max(u_prelit, u_emissive);
    vec3 lighting = mix(sc4_getmodellight(), vec3(1.0, 1.0, 1.0), unlit);
    out_color = vec4(texel.rgb * lighting, texel.a);
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
            'emissive': glGetUniformLocation(self.program, 'u_emissive'),
            'mvp': glGetUniformLocation(self.program, 'u_mvp'),
            'normal_matrix': glGetUniformLocation(self.program, 'u_normal_matrix'),
            'instanced': glGetUniformLocation(self.program, 'u_instanced'),
            'instance_mvp': glGetUniformLocation(self.program, 'u_instance_mvp[0]'),
            'instance_normal': glGetUniformLocation(self.program, 'u_instance_normal[0]'),
            'alpha_func': glGetUniformLocation(self.program, 'u_alpha_func'),
            'alpha_threshold': glGetUniformLocation(self.program, 'u_alpha_threshold'),
            'textured': glGetUniformLocation(self.program, 'u_textured'),
        }

    def bind(self, lighting_state, mvp, normal_matrix):
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
        glUniform1i(self._uniforms['instanced'], 0)
        self._upload_explicit_matrices(mvp, normal_matrix)

    def bind_instanced(self, lighting_state, mvps, normal_matrices):
        """Bind lighting plus up to 32 per-instance transforms."""
        if not mvps or len(mvps) != len(normal_matrices) or len(mvps) > 32:
            raise ValueError('S3D instance batch must contain 1..32 matching transforms')
        self.bind(lighting_state, mvps[0], normal_matrices[0])
        glUniform1i(self._uniforms['instanced'], 1)
        mvp_data = numpy.ascontiguousarray(mvps, dtype=numpy.float32)
        normal_data = numpy.ascontiguousarray(normal_matrices, dtype=numpy.float32)
        glUniformMatrix4fv(self._uniforms['instance_mvp'], len(mvps), GL_TRUE, mvp_data)
        glUniformMatrix3fv(self._uniforms['instance_normal'], len(normal_matrices), GL_TRUE, normal_data)

    def set_material(self, alpha_func=7, alpha_threshold=0.0, textured=True,
                     emissive=False):
        glUniform1i(self._uniforms['alpha_func'], int(alpha_func))
        glUniform1f(self._uniforms['alpha_threshold'], float(alpha_threshold))
        glUniform1i(self._uniforms['textured'], 1 if textured else 0)
        glUniform1f(self._uniforms['emissive'], 1.0 if emissive else 0.0)

    def _upload_explicit_matrices(self, mvp, normal_matrix):
        """Upload caller-computed math matrices (row-major -> transpose=GL_TRUE)."""
        mvp = numpy.ascontiguousarray(mvp, dtype=numpy.float32)
        glUniformMatrix4fv(self._uniforms['mvp'], 1, GL_TRUE, mvp)
        normal_matrix = numpy.ascontiguousarray(normal_matrix, dtype=numpy.float32)
        glUniformMatrix3fv(self._uniforms['normal_matrix'], 1, GL_TRUE, normal_matrix)

    def unbind(self):
        glUseProgram(0)

    def release_gl(self):
        if self.program:
            glDeleteProgram(self.program)
            self.program = 0

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
