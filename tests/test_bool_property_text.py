from types import SimpleNamespace

from sc4pimx.SC4Data import CreateAPropFromString
from sc4pimx.SC4DatTools import Prop


class DummyEntry:
    TGI = {"t": 0, "g": 0, "i": 0}
    fileName = "test.dat"


class DummyExemplar:
    entry = DummyEntry()

    def GetProp(self, key):
        return [2] if key == 16 else None


def parse_prop(line):
    return Prop(line, False, DummyExemplar(), kind=(16,))


def test_bool_property_text_normalizes_hex_values_before_parsing():
    prop_def = SimpleNamespace(ID=0xAA1DD401, Name="Building Is Wall-to-Wall", Type="Bool", Count=1)

    true_line = CreateAPropFromString(prop_def, "0x01")
    false_line = CreateAPropFromString(prop_def, "0x00")

    assert true_line == '0xaa1dd401:{"Building Is Wall-to-Wall"}=Bool:0:(True)'
    assert false_line == '0xaa1dd401:{"Building Is Wall-to-Wall"}=Bool:0:(False)'
    assert parse_prop(true_line).values == [True]
    assert parse_prop(false_line).values == [False]


def test_bool_property_text_accepts_case_insensitive_literals():
    prop_def = SimpleNamespace(ID=0xAA1DD402, Name="Building Styles PIMX Template Marker", Type="Bool", Count=1)

    assert CreateAPropFromString(prop_def, "true").endswith(":(True)")
    assert CreateAPropFromString(prop_def, "false").endswith(":(False)")
