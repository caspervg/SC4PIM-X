"""Data-backed transit switch preset registry.

The wizard resolves one authored preset by base network, placement, and option
checkboxes. Presets may be written as readable rowsets/fragments in TOML, but
the loader compiles each preset to a complete Transit Switch Point byte array
before the UI sees it.
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Optional

from . import SC4TransitSwitchTools as tsw
from .paths import data_file_path
from .translation import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

REGISTRY_FILENAME = "transit_switch_presets.toml"

PLACEMENT_PROXIMITY = "proximity"
PLACEMENT_ON_TOP_WE = "on_top_we"
PLACEMENT_ON_TOP_NS = "on_top_ns"

PLACEMENT_IDS = (PLACEMENT_PROXIMITY, PLACEMENT_ON_TOP_WE, PLACEMENT_ON_TOP_NS)

PLACEMENT_LABELS = {
    PLACEMENT_PROXIMITY: LEXTransitPresetOrientationProximity,
    PLACEMENT_ON_TOP_WE: LEXTransitPresetOrientationOnTopWE,
    PLACEMENT_ON_TOP_NS: LEXTransitPresetOrientationOnTopNS,
}

ART_IDS = {
    "outside_in": tsw.ART_OUTSIDE_TO_INSIDE,
    "inside_out": tsw.ART_INSIDE_TO_OUTSIDE,
}

EDGE_IDS = {
    "all": tsw.EDGE_BITS_ALL,
    "we": tsw.EDGE_BIT_WEST | tsw.EDGE_BIT_EAST,
    "ew": tsw.EDGE_BIT_WEST | tsw.EDGE_BIT_EAST,
    "ns": tsw.EDGE_BIT_NORTH | tsw.EDGE_BIT_SOUTH,
    "sn": tsw.EDGE_BIT_NORTH | tsw.EDGE_BIT_SOUTH,
    "north": tsw.EDGE_BIT_NORTH,
    "east": tsw.EDGE_BIT_EAST,
    "south": tsw.EDGE_BIT_SOUTH,
    "west": tsw.EDGE_BIT_WEST,
}

TRAVEL_IDS = {
    "walk": tsw.TRAVEL_WALK,
    "car": tsw.TRAVEL_CAR,
    "bus": tsw.TRAVEL_BUS,
    "train": tsw.TRAVEL_TRAIN,
    "passenger_train": tsw.TRAVEL_TRAIN,
    "freight_truck": tsw.TRAVEL_FREIGHT_TRUCK,
    "freight_train": tsw.TRAVEL_FREIGHT_TRAIN,
    "subway": tsw.TRAVEL_SUBWAY,
    "el_train": tsw.TRAVEL_EL_TRAIN,
    "elevated_rail": tsw.TRAVEL_EL_TRAIN,
    "monorail": tsw.TRAVEL_MONORAIL,
}

@dataclass(frozen=True)
class RegistryPreset:
    id: str
    base: str
    placement: str
    options: tuple[str, ...]
    category_id: int
    switches: tuple[int, ...]
    blank_prop_ids: tuple[int, ...] = ()
    note: str = ""

    @property
    def key(self) -> tuple[str, str, tuple[str, ...]]:
        return (self.base, self.placement, normalize_options(self.options))


@dataclass(frozen=True)
class RegistryBase:
    id: str
    label: str
    placements: tuple[str, ...]
    options: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True)
class RegistryOption:
    id: str
    label: str


@dataclass(frozen=True)
class RegistryInference:
    base: str
    requires: tuple[frozenset[int], ...]


@dataclass(frozen=True)
class RegistryRowset:
    id: str
    rows: tuple[tsw.SwitchRow, ...]


@dataclass(frozen=True)
class Registry:
    bases: tuple[RegistryBase, ...]
    options: tuple[RegistryOption, ...]
    inference: tuple[RegistryInference, ...]
    rowsets: tuple[RegistryRowset, ...]
    presets: tuple[RegistryPreset, ...]

    @property
    def bases_by_id(self) -> dict[str, RegistryBase]:
        return {base.id: base for base in self.bases}

    @property
    def options_by_id(self) -> dict[str, RegistryOption]:
        return {option.id: option for option in self.options}

    @property
    def rowsets_by_id(self) -> dict[str, RegistryRowset]:
        return {rowset.id: rowset for rowset in self.rowsets}

    @property
    def presets_by_key(self) -> dict[tuple[str, str, tuple[str, ...]], RegistryPreset]:
        return {preset.key: preset for preset in self.presets}


def normalize_options(options: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(str(option).strip() for option in options if str(option).strip()))


def label_for_base(base: str) -> str:
    base_def = load_registry().bases_by_id.get(base)
    return base if base_def is None or not base_def.label else base_def.label


def label_for_placement(placement: str) -> str:
    return PLACEMENT_LABELS.get(placement, placement)


def label_for_option(option: str) -> str:
    option_def = load_registry().options_by_id.get(option)
    return option if option_def is None or not option_def.label else option_def.label


def option_ids() -> tuple[str, ...]:
    return tuple(option.id for option in load_registry().options)


def allowed_options_for_base(base: str) -> tuple[str, ...]:
    base_def = load_registry().bases_by_id.get(base)
    return () if base_def is None else base_def.options


def note_for_base(base: str) -> str:
    base_def = load_registry().bases_by_id.get(base)
    return "" if base_def is None else base_def.note


def allowed_placements_for_base(base: str) -> tuple[str, ...]:
    base_def = load_registry().bases_by_id.get(base)
    return () if base_def is None else base_def.placements


def parse_switch_bytes(value: str) -> tuple[int, ...]:
    out: list[int] = []
    for token in str(value).split(","):
        token = token.strip()
        if token:
            out.append(int(token, 0) & 0xFF)
    if len(out) % tsw.SWITCH_ROW_SIZE:
        raise ValueError("switch byte count is not a multiple of %d" % tsw.SWITCH_ROW_SIZE)
    rows = tsw.decode_switch_array(out)
    expert_rows = [tsw.row_hex(row) for row in rows if row.expert]
    if expert_rows:
        raise ValueError("switch row uses unrecognised bytes: %s" % ", ".join(expert_rows))
    return tuple(out)


def encode_rows(rows: Iterable[tsw.SwitchRow]) -> tuple[int, ...]:
    return tuple(tsw.encode_switch_array(rows))


def _value_from(table: dict[str, int], value, field_name: str) -> int:
    if isinstance(value, int):
        return value
    key = str(value).strip().lower()
    if key in table:
        return table[key]
    try:
        return int(key, 0)
    except ValueError as exc:
        raise ValueError("unknown transit row %s %r" % (field_name, value)) from exc


def parse_row(value) -> tsw.SwitchRow:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("transit row must be [art, edges, from, to], got %r" % (value,))
    row = tsw.SwitchRow(
        art=_value_from(ART_IDS, value[0], "art"),
        edges=_value_from(EDGE_IDS, value[1], "edges"),
        frm=_value_from(TRAVEL_IDS, value[2], "from"),
        to=_value_from(TRAVEL_IDS, value[3], "to"),
    )
    decoded = tsw.decode_switch_array(row.as_bytes())
    if not decoded or decoded[0].expert:
        raise ValueError("transit row uses unrecognised bytes: %s" % tsw.row_hex(row))
    return row


def _compile_preset_switches(item: dict, rowsets_by_id: dict[str, RegistryRowset]) -> tuple[int, ...]:
    rows: list[tsw.SwitchRow] = []
    for rowset_id in item.get("rowsets", []):
        rowset_id = str(rowset_id)
        if rowset_id not in rowsets_by_id:
            raise ValueError("preset %s references unknown rowset %s" % (item.get("id"), rowset_id))
        rows.extend(rowsets_by_id[rowset_id].rows)
    rows.extend(parse_row(row) for row in item.get("rows", []))
    if rows:
        return encode_rows(rows)
    if "switches" in item:
        return parse_switch_bytes(str(item["switches"]))
    raise ValueError("preset %s must define rowsets, rows, or switches" % item.get("id"))


def _parse_int(value) -> int:
    if isinstance(value, int):
        return value
    return int(str(value), 0)


def _parse_prop_id(value) -> int:
    if isinstance(value, int):
        return value & 0xFFFFFFFF
    return int(str(value).strip(), 0) & 0xFFFFFFFF


def parse_prop_ids(values: Iterable) -> tuple[int, ...]:
    out: list[int] = []
    seen: set[int] = set()
    for value in values or ():
        prop_id = _parse_prop_id(value)
        if prop_id not in seen:
            seen.add(prop_id)
            out.append(prop_id)
    return tuple(out)


def _load_raw() -> dict:
    path = data_file_path(REGISTRY_FILENAME)
    if not path.exists():
        return {}
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    return data


@lru_cache(maxsize=1)
def load_registry() -> Registry:
    raw = _load_raw()
    options: list[RegistryOption] = []
    seen_options: set[str] = set()
    for item in raw.get("option", []):
        option = RegistryOption(id=str(item["id"]), label=str(item.get("label", "")).strip())
        if not option.id:
            raise ValueError("transit preset option without an id")
        if option.id in seen_options:
            raise ValueError("duplicate transit preset option %r" % option.id)
        seen_options.add(option.id)
        options.append(option)

    bases: list[RegistryBase] = []
    seen_bases: set[str] = set()
    for item in raw.get("base", []):
        base = RegistryBase(
            id=str(item["id"]),
            label=str(item.get("label", "")).strip(),
            placements=tuple(str(v) for v in item.get("placements", [])),
            options=normalize_options(item.get("options", [])),
            note=str(item.get("note", "")).strip(),
        )
        if base.id in seen_bases:
            raise ValueError("duplicate transit preset base %r" % base.id)
        unknown_placements = [placement for placement in base.placements if placement not in PLACEMENT_IDS]
        if unknown_placements:
            raise ValueError("unknown placement(s) %r for %s" % (unknown_placements, base.id))
        unknown_options = [option for option in base.options if option not in seen_options]
        if unknown_options:
            raise ValueError("unknown option(s) %r for %s" % (unknown_options, base.id))
        seen_bases.add(base.id)
        bases.append(base)

    bases_by_id = {base.id: base for base in bases}

    inference: list[RegistryInference] = []
    for item in raw.get("inference", []):
        rule = RegistryInference(
            base=str(item["base"]),
            requires=tuple(frozenset(_parse_int(v) & 0xFFFFFFFF for v in req) for req in item.get("requires", [])),
        )
        if rule.base not in bases_by_id:
            raise ValueError("inference rule references unknown base %r" % rule.base)
        if not rule.requires or any(not req for req in rule.requires):
            raise ValueError("inference rule for %s needs non-empty requires lists" % rule.base)
        inference.append(rule)

    rowsets: list[RegistryRowset] = []
    seen_rowsets: set[str] = set()
    for item in raw.get("rowset", []):
        rowset = RegistryRowset(
            id=str(item["id"]),
            rows=tuple(parse_row(row) for row in item.get("rows", [])),
        )
        if rowset.id in seen_rowsets:
            raise ValueError("duplicate transit rowset %r" % rowset.id)
        if not rowset.rows:
            raise ValueError("transit rowset %s has no rows" % rowset.id)
        seen_rowsets.add(rowset.id)
        rowsets.append(rowset)

    rowsets_by_id = {rowset.id: rowset for rowset in rowsets}
    presets: list[RegistryPreset] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for item in raw.get("preset", []):
        preset = RegistryPreset(
            id=str(item["id"]),
            base=str(item["base"]),
            placement=str(item["placement"]),
            options=normalize_options(item.get("options", [])),
            category_id=_parse_int(item["category_id"]),
            switches=_compile_preset_switches(item, rowsets_by_id),
            blank_prop_ids=parse_prop_ids(item.get("blank_props", [])),
            note=str(item.get("note", "")).strip(),
        )
        if preset.base not in bases_by_id:
            raise ValueError("preset %s references base %s without a [[base]] definition" % (preset.id, preset.base))
        if preset.placement not in PLACEMENT_IDS:
            raise ValueError("unknown transit preset placement %r in %s" % (preset.placement, preset.id))
        unknown_options = [option for option in preset.options if option not in seen_options]
        if unknown_options:
            raise ValueError("unknown transit preset option(s) %r in %s" % (unknown_options, preset.id))
        base_def = bases_by_id[preset.base]
        invalid_options = [option for option in preset.options if option not in base_def.options]
        if invalid_options:
            raise ValueError("option(s) %r are not allowed for %s" % (invalid_options, preset.base))
        if preset.placement not in base_def.placements:
            raise ValueError("placement %s is not allowed for %s" % (preset.placement, preset.base))
        if preset.key in seen:
            raise ValueError("duplicate transit preset key %r" % (preset.key,))
        seen.add(preset.key)
        presets.append(preset)
    return Registry(tuple(bases), tuple(options), tuple(inference), tuple(rowsets), tuple(presets))


def registry_by_key() -> dict[tuple[str, str, tuple[str, ...]], RegistryPreset]:
    return load_registry().presets_by_key


def find_preset(base: str, placement: str, options: Iterable[str]) -> Optional[RegistryPreset]:
    return registry_by_key().get((base, placement, normalize_options(options)))


def bases_with_presets() -> tuple[str, ...]:
    return tuple(base.id for base in load_registry().bases)


def infer_base_from_occupant_groups(
    occupant_groups: Iterable[int],
    allowed_bases: Optional[Iterable[str]] = None,
) -> Optional[str]:
    """Infer the closest transit-preset base from an exemplar's OccupantGroups.

    Walks the ``[[inference]]`` rules in declaration order; a rule matches when
    every ``requires`` list intersects the exemplar's groups. First match wins.
    """
    groups = {int(group) & 0xFFFFFFFF for group in occupant_groups or ()}
    registry = load_registry()
    if allowed_bases is None:
        allowed = set(registry.bases_by_id)
    else:
        allowed = {str(base) for base in allowed_bases}
    if not groups or not allowed:
        return None
    for rule in registry.inference:
        if rule.base in allowed and all(groups & req for req in rule.requires):
            return rule.base
    return None
