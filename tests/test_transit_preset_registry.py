from sc4pimx import SC4TransitPresetRegistry as registry


def test_registry_loads_base_rules_and_presets():
    loaded = registry.load_registry()

    assert loaded.bases
    assert loaded.rowsets
    assert loaded.presets
    assert registry.allowed_placements_for_base("bus_stop") == ("proximity",)
    assert "garage" in registry.allowed_options_for_base("elevated_rail_station")


def test_registry_presets_obey_base_rules():
    loaded = registry.load_registry()
    bases = loaded.bases_by_id

    for preset in loaded.presets:
        base = bases[preset.base]
        assert preset.placement in base.placements
        assert set(preset.options).issubset(set(base.options))
        assert registry.find_preset(preset.base, preset.placement, preset.options) == preset


def test_registry_ids_have_labels():
    loaded = registry.load_registry()

    for base in loaded.bases:
        assert registry.label_for_base(base.id) != base.id
    for placement in registry.PLACEMENT_IDS:
        assert registry.label_for_placement(placement) != placement
    for option in registry.OPTION_IDS:
        assert registry.label_for_option(option) != option


def test_rowset_presets_compile_to_switch_bytes():
    preset = registry.find_preset(
        "elevated_rail_station",
        "on_top_we",
        ["bus_stop", "garage", "subway_station"],
    )

    assert preset is not None
    assert len(preset.switches) % 4 == 0
    assert preset.switches[:8] == (
        0x81,
        0xA0,
        0x07,
        0x07,
        0x82,
        0xA0,
        0x07,
        0x07,
    )
    assert (0x81, 0xA0, 0x01, 0x01) in _chunks(preset.switches)
    assert (0x81, 0xA0, 0x02, 0x02) in _chunks(preset.switches)
    assert (0x81, 0xA0, 0x04, 0x04) in _chunks(preset.switches)


def test_raw_switch_fallback_still_supported():
    assert registry.parse_switch_bytes("0x81,0xF0,0x00,0x00") == (0x81, 0xF0, 0x00, 0x00)


def _chunks(values):
    return [tuple(values[idx : idx + 4]) for idx in range(0, len(values), 4)]
