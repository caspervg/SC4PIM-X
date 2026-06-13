from types import SimpleNamespace

from sc4pimx.SC4PIMApp import build_category_props_for_preset


class Exemplar:
    def GetProp(self, _prop_id):
        return None


def _category(eval_properties, code=None, parent=None):
    return SimpleNamespace(
        parent=parent,
        code=code or [],
        evalProperties=eval_properties,
        programProperties={},
        setProperties={},
        factorProperties={},
        pairedFactorProperties={},
        removeProperties={},
    )


def _prop(prop_id, name, prop_type="Float32", count=1):
    return SimpleNamespace(ID=prop_id, Name=name, Type=prop_type, Count=count)


def test_category_prop_generator_can_skip_unwanted_broken_formulas():
    transit_capacity = 0xE90E25A3
    bulldoze_cost = 0x099AFACD
    category = _category(
        {
            bulldoze_cost: "BCost",
            transit_capacity: "TSCap",
        },
        code=[("TSCap", "12345.0")],
    )
    virtual_dat = SimpleNamespace(
        properties={
            transit_capacity: _prop(transit_capacity, "Transit Switch Traffic Capacity"),
            bulldoze_cost: _prop(bulldoze_cost, "Bulldoze Cost"),
        }
    )

    lines = build_category_props_for_preset(
        virtual_dat,
        Exemplar(),
        category,
        {},
        emit_prop_ids={transit_capacity},
    )

    assert lines == ['0xe90e25a3:{"Transit Switch Traffic Capacity"}=Float32:0:(12345.0)']
