from sc4pimx.SC4DatTools import CreateAProp, Prop


class DummyEntry:
    TGI = {"t": 0, "g": 0, "i": 0}
    fileName = "test.dat"


class DummyExemplar:
    entry = DummyEntry()

    def GetProp(self, key):
        return None


class DummyPropertyDef:
    ID = 0x27812851
    Name = "Pollution at center"
    Type = "Sint32"
    Count = 4


def parse_prop(line):
    return Prop(line, False, DummyExemplar(), kind=(16,))


def test_sint32_hex_literals_parse_as_twos_complement_values():
    prop = parse_prop(
        '0x27812851:{"Pollution at center"}=Sint32:4:'
        '{0xFFFFFFFF,0xFFFFFFF6,0x00000000,0x0000000A}'
    )

    assert prop.values == [-1, -10, 0, 10]


def test_generated_sint32_property_text_round_trips_negative_values():
    line = CreateAProp(DummyPropertyDef(), (-1, -10, 0, 10))
    prop = parse_prop(line)

    assert prop.values == [-1, -10, 0, 10]
    assert prop.ToStr() == "0xffffffff,0xfffffff6,0x00000000,0x0000000a"
