import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest

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
    for option in registry.option_ids():
        assert registry.label_for_option(option) != option


def test_new_tyberius_station_types_are_selectable_without_switches_yet():
    expected = {
        "u_rail_station",
        "el_rail_glr_dual_network_station",
        "multipurpose_proximity_station",
        "multipurpose_proximity_hub",
        "multipurpose_on_top_proximity_rail_station",
        "multipurpose_on_top_proximity_el_rail_station",
        "multipurpose_on_top_proximity_monorail_station",
        "multipurpose_on_top_proximity_hrw_station",
    }
    loaded = registry.load_registry()

    assert expected.issubset(set(loaded.bases_by_id))
    for base in expected:
        assert registry.label_for_base(base) != base
        assert registry.allowed_placements_for_base(base)


def test_base_and_preset_notes_load_from_toml():
    loaded = registry.load_registry()

    assert registry.note_for_base("multipurpose_on_top_proximity_hrw_station")
    assert registry.note_for_base("unknown_base") == ""
    for preset in loaded.presets:
        assert isinstance(preset.note, str)


def test_rowset_presets_compile_to_switch_bytes():
    preset = registry.find_preset(
        "elevated_rail_station",
        "on_top_we",
        ["bus_stop", "garage", "subway_station"],
    )

    assert preset is not None
    assert len(preset.switches) % 4 == 0
    chunks = _chunks(preset.switches)
    assert (0x81, 0xA0, 0x07, 0x07) in chunks
    assert (0x82, 0xA0, 0x07, 0x07) in chunks
    assert any(row[2:] == (0x01, 0x00) for row in chunks)
    assert any(row[2:] == (0x02, 0x00) for row in chunks)
    assert any(row[2:] == (0x00, 0x06) for row in chunks)


def test_raw_switch_fallback_still_supported():
    assert registry.parse_switch_bytes("0x81,0xF0,0x00,0x00") == (0x81, 0xF0, 0x00, 0x00)


def test_tyberius_on_top_bus_stop_preset_is_loaded():
    preset = registry.find_preset("bus_stop", "on_top_we", [])

    assert preset is not None
    assert (0x81, 0xA0, 0x01, 0x01) in _chunks(preset.switches)
    assert (0x82, 0xF0, 0x02, 0x00) in _chunks(preset.switches)


def test_tyberius_imported_presets_match_source_switches():
    source = ROOT / tyberius_importer.DEFAULT_SOURCE
    if not source.exists():
        pytest.skip("Tyberius source notes are local authoring input and are not committed")
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

    assert len(expected_presets) >= 69
    for imported in expected_presets:
        preset = registry.find_preset(imported.base, imported.placement, imported.options)

        assert preset is not None, imported.id
        assert len(preset.switches) % 4 == 0, imported.id


def test_tyberius_imported_presets_are_committed():
    target = ROOT / tyberius_importer.DEFAULT_TARGET
    text = target.read_text(encoding="utf-8")
    assert tyberius_importer.IMPORTED_MARKER in text
    imported_text = text.split(tyberius_importer.IMPORTED_MARKER, 1)[1]
    imported_presets = tomllib.loads(imported_text).get("preset", [])

    assert len(imported_presets) >= 69
    for item in imported_presets:
        options = tuple(sorted(str(option) for option in item.get("options", [])))
        preset = registry.find_preset(str(item["base"]), str(item["placement"]), options)
        assert preset is not None, item["id"]


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
    assert registry.infer_base_from_occupant_groups([0x1303, 0xB5C00DF9]) == "el_rail_glr_dual_network_station"
    assert registry.infer_base_from_occupant_groups([0x1305, 0x1303]) == "rail_elevated_rail_station"
    assert registry.infer_base_from_occupant_groups([0x1307, 0x1303]) == "monorail_elevated_rail_station"
    assert registry.infer_base_from_occupant_groups([0xB5C00DFA, 0x1303]) == "hrw_elevated_rail_station"
    assert registry.infer_base_from_occupant_groups(
        [0x1303, 0x1305, 0x1307, 0xB5C00DFA, 0x1302, 0x1301],
    ) == "multipurpose_proximity_station"


def test_inferred_transit_preset_base_respects_allowed_bases():
    assert registry.infer_base_from_occupant_groups(
        [0x1305, 0x1303],
        ["passenger_train_station", "elevated_rail_station"],
    ) == "elevated_rail_station"
    assert registry.infer_base_from_occupant_groups([0x1305], ["bus_stop"]) is None


def test_tyberius_importer_recognises_new_station_type_labels():
    assert tyberius_importer._base_from_label("U-Rail Station") == "u_rail_station"
    assert (
        tyberius_importer._base_from_label("ElRail/GLR Dual Network Stations")
        == "el_rail_glr_dual_network_station"
    )
    assert tyberius_importer._base_from_label("Multipurpose Proximity") == "multipurpose_proximity_station"
    assert tyberius_importer._base_from_label("Multipurpose Proximity Hub") == "multipurpose_proximity_hub"
    assert (
        tyberius_importer._base_from_label("Multipurpose On-Top Proximity Station - Rail")
        == "multipurpose_on_top_proximity_rail_station"
    )
    assert (
        tyberius_importer._base_from_label("Multipurpose On-Top Proximity Station - El-Rail")
        == "multipurpose_on_top_proximity_el_rail_station"
    )
    assert (
        tyberius_importer._base_from_label("Multipurpose On-Top Proximity Station - MonoRail")
        == "multipurpose_on_top_proximity_monorail_station"
    )
    assert (
        tyberius_importer._base_from_label("Multipurpose On-Top Proximity Station - HRW")
        == "multipurpose_on_top_proximity_hrw_station"
    )


def _chunks(values):
    return [tuple(values[idx : idx + 4]) for idx in range(0, len(values), 4)]
