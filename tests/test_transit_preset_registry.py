import importlib.util
import sys
from pathlib import Path

from sc4pimx import SC4TransitPresetRegistry as registry


ROOT = Path(__file__).resolve().parents[1]
_IMPORTER_SPEC = importlib.util.spec_from_file_location(
    "import_transit_presets",
    ROOT / "scripts" / "import_transit_presets.py",
)
assert _IMPORTER_SPEC is not None and _IMPORTER_SPEC.loader is not None
tyberius_importer = importlib.util.module_from_spec(_IMPORTER_SPEC)
sys.modules[_IMPORTER_SPEC.name] = tyberius_importer
_IMPORTER_SPEC.loader.exec_module(tyberius_importer)


def test_registry_loads_base_rules_and_presets():
    loaded = registry.load_registry()

    assert loaded.bases
    assert loaded.rowsets
    assert loaded.presets
    assert registry.allowed_placements_for_base("bus_stop") == ("proximity", "on_top_we", "on_top_ns")
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


def test_tyberius_on_top_bus_stop_preset_is_loaded():
    preset = registry.find_preset("bus_stop", "on_top_we", [])

    assert preset is not None
    assert (0x81, 0xA0, 0x01, 0x01) in _chunks(preset.switches)
    assert (0x82, 0xF0, 0x02, 0x00) in _chunks(preset.switches)


def test_tyberius_imported_presets_match_source_switches():
    source = ROOT / tyberius_importer.DEFAULT_SOURCE
    target = ROOT / tyberius_importer.DEFAULT_TARGET
    existing_keys = tyberius_importer._existing_keys(target, ignore_imported_block=True)
    imported_presets = tyberius_importer.add_global_garage_variants(tyberius_importer.parse_source(source))

    expected_presets = []
    seen = set(existing_keys)
    for imported in imported_presets:
        if imported.key in seen:
            continue
        seen.add(imported.key)
        expected_presets.append(imported)

    assert len(expected_presets) == 69
    for imported in expected_presets:
        preset = registry.find_preset(imported.base, imported.placement, imported.options)

        assert preset is not None, imported.id
        assert preset.switches == imported.switches, imported.id


def test_infers_transit_preset_base_from_occupant_groups():
    assert registry.infer_base_from_occupant_groups([0x1301]) == "bus_stop"
    assert registry.infer_base_from_occupant_groups([0x1302]) == "subway_station"
    assert registry.infer_base_from_occupant_groups([0x1305]) == "passenger_train_station"
    assert registry.infer_base_from_occupant_groups([0x1306]) == "freight_train_station"
    assert registry.infer_base_from_occupant_groups([0x1303]) == "elevated_rail_station"
    assert registry.infer_base_from_occupant_groups([0x1307]) == "monorail_station"
    assert registry.infer_base_from_occupant_groups([0x130A]) == "garage"
    assert registry.infer_base_from_occupant_groups([0x130B]) == "toll_booth"


def test_infers_specific_multimodal_transit_preset_base_first():
    assert registry.infer_base_from_occupant_groups([0x1305, 0x1306]) == "passenger_freight_station"
    assert registry.infer_base_from_occupant_groups([0x1305, 0x1303]) == "rail_elevated_rail_station"
    assert registry.infer_base_from_occupant_groups([0x1307, 0x1303]) == "monorail_elevated_rail_station"
    assert registry.infer_base_from_occupant_groups([0xB5C00DFA, 0x1303]) == "hrw_elevated_rail_station"


def test_inferred_transit_preset_base_respects_allowed_bases():
    assert registry.infer_base_from_occupant_groups(
        [0x1305, 0x1303],
        ["passenger_train_station", "elevated_rail_station"],
    ) == "elevated_rail_station"
    assert registry.infer_base_from_occupant_groups([0x1305], ["bus_stop"]) is None


def _chunks(values):
    return [tuple(values[idx : idx + 4]) for idx in range(0, len(values), 4)]
