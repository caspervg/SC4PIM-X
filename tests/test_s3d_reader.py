import struct

import pytest

from sc4pimx.S3DReader import S3D


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
