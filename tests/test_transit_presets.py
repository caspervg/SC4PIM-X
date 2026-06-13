from types import SimpleNamespace

from sc4pimx import SC4TransitSwitchTools as tsw
from sc4pimx.SC4TransitPresets import apply_overrides


def _prop(prop_id, name):
    return SimpleNamespace(ID=prop_id, Name=name, Type="Float32", Count=1)


def test_manual_cost_and_capacity_are_added_when_seed_lines_are_blank():
    virtual_dat = SimpleNamespace(
        properties={
            tsw.PROP_TRANSIT_SWITCH_ENTRY_COST: _prop(
                tsw.PROP_TRANSIT_SWITCH_ENTRY_COST,
                "Transit Switch Entry Cost",
            ),
            tsw.PROP_TRANSIT_SWITCH_TRAFFIC_CAPACITY: _prop(
                tsw.PROP_TRANSIT_SWITCH_TRAFFIC_CAPACITY,
                "Transit Switch Traffic Capacity",
            ),
        }
    )

    lines = apply_overrides(
        virtual_dat,
        [],
        None,
        False,
        override_cost=0.5,
        override_capacity=1200,
    )

    assert lines == [
        '0xe90e25a2:{"Transit Switch Entry Cost"}=Float32:0:(0.5)',
        '0xe90e25a3:{"Transit Switch Traffic Capacity"}=Float32:0:(1200.0)',
    ]
