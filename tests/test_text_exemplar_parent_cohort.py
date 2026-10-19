import struct
from types import SimpleNamespace

from sc4pimx.SC4DatTools import SC4Exemplar


class _VirtualDat:
    properties = {}

    def __init__(self):
        self.lookups = []

    def getEntry(self, t, g, i):
        self.lookups.append((t, g, i))
        return None


def _exemplar(parent_key):
    content = (
        'EQZT1###\r\n'
        'ParentCohort=Key:{%s}\r\n'
        'PropCount=0x00000000\r\n' % parent_key
    ).encode('latin-1')
    entry = SimpleNamespace(content=content, tgi=(0x6534284A, 1, 2), fileName='x.dat')
    virtual_dat = _VirtualDat()
    return SC4Exemplar(entry, virtual_dat), virtual_dat


def _written_key(exemplar):
    return exemplar.TextRep().split(b'\r\n')[1]


def test_text_parent_cohort_round_trips_in_group_instance_type_order():
    exemplar, virtual_dat = _exemplar('0xa8fbd372,0xaa1b5001,0x05342861')

    assert virtual_dat.lookups == [(0x05342861, 0xA8FBD372, 0xAA1B5001)]
    assert _written_key(exemplar) == b'ParentCohort=Key:{0xA8FBD372,0xAA1B5001,0x05342861}'


def test_scrambled_text_parent_cohort_is_repaired_on_save():
    exemplar, virtual_dat = _exemplar('0x05342861,0xA8FBD372,0xAA1B5001')

    assert virtual_dat.lookups == [(0x05342861, 0xA8FBD372, 0xAA1B5001)]
    assert _written_key(exemplar) == b'ParentCohort=Key:{0xA8FBD372,0xAA1B5001,0x05342861}'


def test_text_parent_cohort_with_non_cohort_type_is_read_as_group_instance_type():
    exemplar, virtual_dat = _exemplar('0xBADB57F1,0x54589520,0x5AD0E817')

    assert virtual_dat.lookups == [(0x5AD0E817, 0xBADB57F1, 0x54589520)]
    assert _written_key(exemplar) == b'ParentCohort=Key:{0xBADB57F1,0x54589520,0x5AD0E817}'


def test_binary_parent_cohort_with_non_cohort_type_is_not_rotated():
    content = b'EQZB1###' + struct.pack('<4I', 0x5AD0E817, 0xBADB57F1, 0x54589520, 0)
    entry = SimpleNamespace(content=content, tgi=(0x6534284A, 1, 2), fileName='x.dat')
    virtual_dat = _VirtualDat()

    exemplar = SC4Exemplar(entry, virtual_dat)

    assert virtual_dat.lookups == [(0x5AD0E817, 0xBADB57F1, 0x54589520)]
    assert exemplar.BinaryRep()[8:20] == content[8:20]
