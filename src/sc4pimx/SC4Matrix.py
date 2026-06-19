"""Column-vector 4x4 transform helpers (GL/math convention) built on numpy.

Matrices compose with post-multiplication (m1 @ m2 applies m2 first), matching
fixed-function glMultMatrix order. gl_columns() returns the column-major float32
buffer expected by glLoadMatrixf; for glUniformMatrix*fv upload the math matrix
directly with transpose=GL_TRUE.
"""
import math

import numpy


def identity():
    return numpy.identity(4, dtype=numpy.float64)


def translate(x, y, z):
    m = identity()
    m[0, 3], m[1, 3], m[2, 3] = x, y, z
    return m


def scale(x, y, z):
    m = identity()
    m[0, 0], m[1, 1], m[2, 2] = x, y, z
    return m


def rotate_x(degrees):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    m = identity()
    m[1, 1], m[1, 2], m[2, 1], m[2, 2] = c, -s, s, c
    return m


def rotate_y(degrees):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    m = identity()
    m[0, 0], m[0, 2], m[2, 0], m[2, 2] = c, s, -s, c
    return m


def ortho(left, right, bottom, top, near, far):
    m = identity()
    m[0, 0] = 2.0 / (right - left)
    m[1, 1] = 2.0 / (top - bottom)
    m[2, 2] = -2.0 / (far - near)
    m[0, 3] = -(right + left) / (right - left)
    m[1, 3] = -(top + bottom) / (top - bottom)
    m[2, 3] = -(far + near) / (far - near)
    return m


def normal_matrix(modelview):
    """Inverse-transpose of the upper-left 3x3 (correct under non-uniform scale)."""
    mv3 = numpy.asarray(modelview)[0:3, 0:3]
    try:
        return numpy.linalg.inv(mv3).T
    except numpy.linalg.LinAlgError:
        return mv3


def gl_columns(m):
    """Column-major float32 buffer for glLoadMatrixf."""
    return numpy.ascontiguousarray(numpy.asarray(m).T, dtype=numpy.float32)
