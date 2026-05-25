from sc4pimx.SC4StructuredPropertyEditors import (
    demand_pairs,
    demand_pairs_to_text,
    editor_kind,
    option_label,
)


class Prop:
    def __init__(self, prop_id, values):
        self.id = prop_id
        self.values = values


class PropDef:
    def __init__(self, typ, count, options=None):
        self.Type = typ
        self.Count = count
        self.Options = options or {}
        self.Name = "Test"


def test_pollution_and_effect_properties_use_vector_editor():
    assert editor_kind(Prop(0x27812851, [0, -10, 0, 0]), PropDef("Sint32", 4)) == "vector"
    assert editor_kind(Prop(0x68EE9764, [2.0, 1.0, 0.0, 0.0]), PropDef("Float32", 4)) == "vector"
    assert editor_kind(Prop(0x2781284F, [50, 6]), PropDef("Sint32", 2)) == "vector"


def test_demand_capacity_properties_use_pair_editor():
    assert editor_kind(
        Prop(0x27812834, [0x00001010, 25, 0x00001020, 10]),
        PropDef("Uint32", -2),
    ) == "pairs"


def test_demand_pairs_round_trip_to_property_text():
    pairs = demand_pairs([0x00002010, 12, 0x00002020, 34])

    assert pairs == [(0x00002010, 12), (0x00002020, 34)]
    assert demand_pairs_to_text(pairs) == "0x00002010,12,0x00002020,34"


def test_option_label_prefers_property_option_names():
    prop_def = PropDef("Uint32", -2, {0x00002010: "Jobs $"})

    assert option_label(prop_def, 0x00002010) == "Jobs $"
    assert option_label(prop_def, 0x00002020) == "0x00002020"
