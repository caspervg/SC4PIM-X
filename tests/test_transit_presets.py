from types import SimpleNamespace

from sc4pimx import SC4TransitSwitchTools as tsw
from sc4pimx.SC4TransitPresets import (
    PresetWizardDialog,
    apply_overrides,
    _override_from_field,
)


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


# --- Fix #1: a field is an override only when edited away from its seed ------
# A category that legitimately evaluates cost/capacity to 0 must not be treated
# as an explicit "force 0" override (which clobbered the category's own value).


def test_field_equal_to_seed_is_not_an_override():
    # Category seeds 0 and the user leaves it: no override, the category line
    # flows through untouched instead of being re-applied as a forced 0.
    assert _override_from_field("0", "0") is None
    assert _override_from_field("5", "5") is None
    # Whitespace-only differences do not count as an edit.
    assert _override_from_field(" 5 ", "5") is None


def test_blank_or_unparseable_field_is_not_an_override():
    assert _override_from_field("", "5") is None
    assert _override_from_field("   ", "") is None
    assert _override_from_field("abc", "5") is None


def test_edited_field_becomes_an_override():
    assert _override_from_field("10", "5") == 10.0
    # Forcing 0 when the seed was non-zero is a real, intentional override.
    assert _override_from_field("0", "5") == 0.0
    # Editing a previously-blank seed is an override too.
    assert _override_from_field("1200", "") == 1200.0


# --- Fix #2: changing the preset selection reseeds cost/capacity -------------
# Ticking an option (or changing placement) selects a preset with a different
# category_id, so the cost/capacity fields must be reseeded. Editing the
# cost/capacity fields themselves must NOT reseed (that would recurse via
# EVT_TEXT and discard the user's typing).


def _dispatch_on_changed(event_source):
    """Drive PresetWizardDialog._on_changed against a fake self and report
    which refresh hooks fired for an event coming from ``event_source``."""
    calls = []
    fake = SimpleNamespace(
        baseChoice=object(),
        placementRadio=object(),
        optionCheck=object(),
        costText=object(),
        capacityText=object(),
        _refresh_base_dependent=lambda: calls.append("base"),
        _refresh_preset_dependent=lambda: calls.append("preset"),
        _refresh_preview=lambda: calls.append("preview"),
    )
    source = getattr(fake, event_source)
    event = SimpleNamespace(
        GetEventObject=lambda: source,
        Skip=lambda: None,
    )
    PresetWizardDialog._on_changed(fake, event)
    return calls


def test_option_change_reseeds_cost_and_capacity():
    calls = _dispatch_on_changed("optionCheck")
    assert "preset" in calls  # category_id may have changed -> reseed
    assert "base" not in calls  # base did not change


def test_placement_change_reseeds_cost_and_capacity():
    calls = _dispatch_on_changed("placementRadio")
    assert "preset" in calls
    assert "base" not in calls


def test_base_change_reseeds_base_and_preset():
    calls = _dispatch_on_changed("baseChoice")
    assert calls[:2] == ["base", "preset"]


def test_editing_cost_field_does_not_reseed():
    # Reseeding here would overwrite the user's edit and recurse via EVT_TEXT.
    assert _dispatch_on_changed("costText") == ["preview"]
    assert _dispatch_on_changed("capacityText") == ["preview"]
