import struct

import numpy
import pytest

from sc4pimx.S3DReader import (
    S3D,
    material_casts_shadow,
    project_indexed_shadow_decals,
    project_shadow_decal,
)


class FakeEntry:
    """Minimal stand-in for an already-decompressed DBPF entry."""

    def __init__(self, content):
        self.tgi = (1523640343, 0xBADB57F1, 0x10632000)
        self.content = content
        self.rawContent = None
        self.fileName = 'test.dat'

    def read_file(self, sc4, readWhole=True, decompress=False):
        return True


def _chunk(tag, payload):
    return tag + struct.pack('<I', len(payload) + 8) + payload


def _model(mats_payload=None, mats_trailer=b''):
    head = _chunk(b'HEAD', struct.pack('<HH', 1, 5))

    vert_block = struct.pack('<HHI', 0, 3, 2)  # 3 vertices, format 2: xyz + uv
    for i in range(3):
        vert_block += struct.pack('<fffff', float(i), 0.0, 0.0, 0.0, 0.0)
    vert = _chunk(b'VERT', struct.pack('<I', 1) + vert_block)

    indx = _chunk(b'INDX', struct.pack('<I', 1) + struct.pack('<HHH', 0, 0, 3)
                  + struct.pack('<HHH', 0, 1, 2))

    prim = _chunk(b'PRIM', struct.pack('<I', 1) + struct.pack('<H', 1)
                  + struct.pack('<III', 0, 0, 3))

    if mats_payload is None:
        material = struct.pack('<IBBBBHIBB', 0xB3, 4, 3, 8, 1, 0x7FFF, 0, 0, 1)
        texture = (struct.pack('<IBBBBHHB', 0x09C6CC22, 3, 3, 0, 0, 33, 2, 4)
                   + b'tex\x00')
        mats_payload = struct.pack('<I', 1) + material + texture
    mats = _chunk(b'MATS', mats_payload) + mats_trailer

    anim_mesh = struct.pack('<BB', 5, 0) + b'mesh\x00' + struct.pack('<HHHH', 0, 0, 0, 0)
    anim = _chunk(b'ANIM', struct.pack('<HHHIfH', 1, 0, 1, 0, 0.0, 1) + anim_mesh)

    body = head + vert + indx + prim + mats + anim
    return b'3DMD' + struct.pack('<I', len(body) + 8) + body


def _read(content):
    mesh = S3D(FakeEntry(content))
    mesh.ReadFile()
    return mesh


def test_reads_a_well_formed_model():
    mesh = _read(_model())
    assert len(mesh.vertexBuffers) == 1
    assert len(mesh.matBlocks) == 1
    assert mesh.matBlocks[0]['textures'][0]['textureID'] == 0x09C6CC22
    assert len(mesh.anims['animatedMeshes']) == 1


def test_recovers_from_junk_bytes_left_inside_a_chunk():
    # Some published models (e.g. in NAM's 150-mods.dat) carry stale bytes at
    # the end of MATS, which used to derail every following chunk.
    mesh = _read(_model(mats_trailer=b'hts\x00\x00\x00\x06\x00'))
    assert len(mesh.matBlocks) == 1
    assert len(mesh.anims['animatedMeshes']) == 1


def test_truncated_mats_still_yields_a_drawable_model():
    # Material count claims far more materials than the chunk holds.
    material = struct.pack('<IBBBBHIBB', 0xB3, 4, 3, 8, 1, 0x7FFF, 0, 0, 1)
    mesh = _read(_model(mats_payload=struct.pack('<I', 99) + material))
    assert len(mesh.vertexBuffers) == 1
    assert len(mesh.anims['animatedMeshes']) == 1


def test_unreadable_model_degrades_to_an_empty_mesh():
    mesh = _read(b'NOPE' + b'\x00' * 64)
    assert mesh.vertexBuffers == []
    assert mesh.anims['animatedMeshes'] == []
    assert mesh.bboxX == 0.0


def test_reading_twice_does_not_reparse():
    entry = FakeEntry(_model())
    mesh = S3D(entry)
    mesh.ReadFile()
    mesh.ReadFile()  # content is dropped after the first read
    assert len(mesh.vertexBuffers) == 1


def test_shadow_decal_recovers_affine_alpha_projector_on_ground_plane():
    direction = numpy.asarray((0.5, -1.0, 0.25))
    plane_y = -2.0
    positions = numpy.asarray(
        (
            (-2.0, 0.0, -1.0),
            (2.0, 0.0, -1.0),
            (-2.0, 5.0, 1.0),
            (2.0, 5.0, 1.0),
            (0.0, 8.0, 0.0),
        )
    )
    distance = (plane_y - positions[:, 1]) / direction[1]
    projected = positions + distance[:, None] * direction
    design = numpy.column_stack((projected[:, 0], projected[:, 2], numpy.ones(len(projected))))
    coefficients = numpy.asarray(((0.08, -0.03), (0.02, 0.11), (0.4, 0.2)))
    uvs = design @ coefficients

    decal = project_shadow_decal(positions, uvs, direction, plane_y)

    assert decal is not None
    quad_positions, quad_uvs, uv_bounds = decal
    quad_design = numpy.column_stack(
        (quad_positions[:, 0], quad_positions[:, 2], numpy.ones(4))
    )
    assert quad_positions[:, 1] == pytest.approx(plane_y)
    assert quad_uvs == pytest.approx(quad_design @ coefficients, abs=1.0e-6)
    assert uv_bounds == pytest.approx(
        (uvs[:, 0].min(), uvs[:, 1].min(), uvs[:, 0].max(), uvs[:, 1].max())
    )


def test_shadow_decal_rejects_parallel_or_degenerate_projection():
    positions = numpy.asarray(((0, 0, 0), (1, 0, 0), (2, 0, 0)), dtype=float)
    uvs = numpy.asarray(((0, 0), (0.5, 0), (1, 0)), dtype=float)

    assert project_shadow_decal(positions, uvs, (1, 0, 0)) is None
    assert project_shadow_decal(positions, uvs, (0.5, -1, 0.25)) is None


def test_indexed_shadow_decal_ignores_vertices_outside_current_primitives():
    direction = numpy.asarray((0.5, -1.0, 0.25))
    positions = numpy.asarray(
        ((-2, 0, -1), (2, 0, -1), (2, 4, 1), (-2, 4, 1), (100, 100, 100)),
        dtype=float,
    )
    projected = positions + ((0.0 - positions[:, 1]) / direction[1])[:, None] * direction
    design = numpy.column_stack((projected[:, 0], projected[:, 2], numpy.ones(len(projected))))
    uvs = design @ numpy.asarray(((0.08, -0.03), (0.02, 0.11), (0.4, 0.2)))
    indices = numpy.asarray((0, 1, 2, 3, 4), dtype=numpy.uint16)

    decals = project_indexed_shadow_decals(
        positions,
        uvs,
        (indices.tobytes(), len(indices)),
        [(2, 0, 4)],
        direction,
    )

    assert len(decals) == 1
    quad_positions, _quad_uvs, uv_bounds = decals[0]
    assert quad_positions[:, 0].max() < 10
    assert uv_bounds == pytest.approx(
        (uvs[:4, 0].min(), uvs[:4, 1].min(), uvs[:4, 0].max(), uvs[:4, 1].max())
    )


def test_indexed_shadow_decals_split_disconnected_animation_planes():
    positions = numpy.asarray(
        (
            (-2, 0, 0), (0, 0, 0), (0, 4, 0), (-2, 4, 0),
            (10, 0, 0), (12, 0, 0), (12, 4, 0), (10, 4, 0),
        ),
        dtype=float,
    )
    uvs = numpy.asarray(((0, 0), (1, 0), (1, 1), (0, 1)) * 2, dtype=float)
    indices = numpy.arange(8, dtype=numpy.uint16)

    decals = project_indexed_shadow_decals(
        positions,
        uvs,
        (indices.tobytes(), len(indices)),
        [(2, 0, len(indices))],
        (0.5, -1.0, 0.25),
    )

    assert len(decals) == 2
    assert all(numpy.ptp(decal[0][:, 0]) < 5 for decal in decals)


def test_only_ordinary_alpha_blending_casts_a_blended_shadow():
    assert material_casts_shadow({'flags': 0})
    assert material_casts_shadow({'flags': 16, 'srcBlend': 4, 'dstBlend': 5})
    assert material_casts_shadow({'flags': 16, 'srcBlend': 1, 'dstBlend': 5})
    assert not material_casts_shadow({'flags': 16, 'srcBlend': 1, 'dstBlend': 1})


def test_le_init_precaches_textures_for_every_animation_material():
    mesh = S3D(FakeEntry(b''))
    mesh.ReadFile = lambda: None
    mesh.anims = {
        'animatedMeshes': [
            {'frames': [{'matsBlock': 0}, {'matsBlock': 1}, {'matsBlock': 0}]},
        ],
    }
    mesh.matBlocks = [
        {'textures': [{'textureID': 0x100}]},
        {'textures': [{'textureID': 0x200}]},
    ]

    class VirtualDat:
        def getEntry(self, _tid, group, iid):
            return (group, iid)

    class Holder:
        def __init__(self):
            self.precached = []

        def PrecacheTex(self, key, day_entry, night_entry=None):
            self.precached.append((key, day_entry, night_entry))

    holder = Holder()
    mesh.LEInit(VirtualDat(), holder)

    group = 0x1ABE787D
    assert mesh.mesh_tex_keys == {(0, 0): (group, 0x100), (0, 1): (group, 0x200)}
    assert [item[0] for item in holder.precached] == [(group, 0x100), (group, 0x200)]


def test_shared_frame_time_keeps_shadow_and_visible_animation_in_sync(monkeypatch):
    import sc4pimx.S3DReader as reader

    monkeypatch.setattr(reader, 'glDisable', lambda *_args: None)
    monkeypatch.setattr(reader, 'glDepthMask', lambda *_args: None)
    mesh = S3D(FakeEntry(b''))
    mesh.anims = {'frameCount': 2, 'frameRate': 10, 'animatedMeshes': []}
    mesh.currentFrame = 0
    mesh._lastFrameTime = 0.0

    class Canvas:
        def request_animation(self, _delay):
            return None

    class Shader:
        def bind_instanced(self, *_args):
            return None

        def unbind(self):
            return None

    holder = type('Holder', (), {'glCanvas': Canvas()})()
    for _pass in ('shadow', 'visible'):
        mesh.draw_instanced(holder, Shader(), None, [numpy.identity(4)], [None], frame_time=0.11)

    assert mesh.currentFrame == 1
