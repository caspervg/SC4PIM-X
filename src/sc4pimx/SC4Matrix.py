"""Column-vector 4x4 transform helpers used by the core renderer.

Matrices compose with post-multiplication: ``m1 @ m2`` applies ``m2`` first.
Uniform uploads pass these row-major math matrices with ``transpose=GL_TRUE``.
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


def rotate_z(degrees):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    m = identity()
    m[0, 0], m[0, 1], m[1, 0], m[1, 1] = c, -s, s, c
    return m


def rotate(degrees, x, y, z):
    """Return an axis-angle rotation matrix for a normalized arbitrary axis."""
    axis = numpy.asarray((x, y, z), dtype=numpy.float64)
    length = numpy.linalg.norm(axis)
    if length <= 1.0e-12:
        return identity()
    x, y, z = axis / length
    c = math.cos(math.radians(degrees))
    s = math.sin(math.radians(degrees))
    t = 1.0 - c
    m = identity()
    m[0, 0] = t * x * x + c
    m[0, 1] = t * x * y - s * z
    m[0, 2] = t * x * z + s * y
    m[1, 0] = t * x * y + s * z
    m[1, 1] = t * y * y + c
    m[1, 2] = t * y * z - s * x
    m[2, 0] = t * x * z - s * y
    m[2, 1] = t * y * z + s * x
    m[2, 2] = t * z * z + c
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
