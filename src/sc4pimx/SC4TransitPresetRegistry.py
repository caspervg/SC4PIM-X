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

BASE_IDS = (
    "bus_stop",
    "subway_station",
    "elevated_rail_station",
    "passenger_train_station",
    "freight_train_station",
    "passenger_freight_station",
    "monorail_station",
    "hrw_station",
    "rail_elevated_rail_station",
    "monorail_elevated_rail_station",
    "hrw_elevated_rail_station",
    "garage",
    "toll_booth",
)

OPTION_GARAGE = "garage"
OPTION_BUS_STOP = "bus_stop"
OPTION_SUBWAY_STATION = "subway_station"
OPTION_FREIGHT_TRAIN_PASS_THROUGH = "freight_train_pass_through"
OPTION_PASSENGER_TRAIN_PASS_THROUGH = "passenger_train_pass_through"

OPTION_IDS = (
    OPTION_GARAGE,
    OPTION_BUS_STOP,
    OPTION_SUBWAY_STATION,
    OPTION_FREIGHT_TRAIN_PASS_THROUGH,
    OPTION_PASSENGER_TRAIN_PASS_THROUGH,
)

BASE_LABELS = {
    "bus_stop": LEXTransitPresetBaseBusStop,
    "subway_station": LEXTransitPresetBaseSubwayStation,
    "elevated_rail_station": LEXTransitPresetBaseElevatedRailStation,
    "passenger_train_station": LEXTransitPresetBasePassengerTrainStation,
    "freight_train_station": LEXTransitPresetBaseFreightTrainStation,
    "passenger_freight_station": LEXTransitPresetBasePassengerFreightStation,
    "monorail_station": LEXTransitPresetBaseMonorailStation,
    "hrw_station": LEXTransitPresetBaseHRWStation,
    "rail_elevated_rail_station": LEXTransitPresetBaseRailElevatedRailStation,
    "monorail_elevated_rail_station": LEXTransitPresetBaseMonorailElevatedRailStation,
    "hrw_elevated_rail_station": LEXTransitPresetBaseHRWElevatedRailStation,
    "garage": LEXTransitPresetBaseGarage,
    "toll_booth": LEXTransitPresetBaseTollBooth,
}

PLACEMENT_LABELS = {
    PLACEMENT_PROXIMITY: LEXTransitPresetOrientationProximity,
    PLACEMENT_ON_TOP_WE: LEXTransitPresetOrientationOnTopWE,
    PLACEMENT_ON_TOP_NS: LEXTransitPresetOrientationOnTopNS,
}

OPTION_LABELS = {
    OPTION_GARAGE: LEXTransitPresetOptionGarage,
    OPTION_BUS_STOP: LEXTransitPresetOptionBusStop,
    OPTION_SUBWAY_STATION: LEXTransitPresetOptionSubwayStation,
    OPTION_FREIGHT_TRAIN_PASS_THROUGH: LEXTransitPresetOptionFreightTrainPassThrough,
    OPTION_PASSENGER_TRAIN_PASS_THROUGH: LEXTransitPresetOptionPassengerTrainPassThrough,
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

    @property
    def key(self) -> tuple[str, str, tuple[str, ...]]:
        return (self.base, self.placement, normalize_options(self.options))


@dataclass(frozen=True)
class RegistryBase:
    id: str
    placements: tuple[str, ...]
    options: tuple[str, ...]


@dataclass(frozen=True)
class RegistryRowset:
    id: str
    rows: tuple[tsw.SwitchRow, ...]


@dataclass(frozen=True)
class Registry:
    bases: tuple[RegistryBase, ...]
    rowsets: tuple[RegistryRowset, ...]
    presets: tuple[RegistryPreset, ...]

    @property
    def bases_by_id(self) -> dict[str, RegistryBase]:
        return {base.id: base for base in self.bases}

    @property
    def rowsets_by_id(self) -> dict[str, RegistryRowset]:
        return {rowset.id: rowset for rowset in self.rowsets}

    @property
    def presets_by_key(self) -> dict[tuple[str, str, tuple[str, ...]], RegistryPreset]:
        return {preset.key: preset for preset in self.presets}


def normalize_options(options: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(str(option).strip() for option in options if str(option).strip()))


def label_for_base(base: str) -> str:
    return BASE_LABELS.get(base, base)


def label_for_placement(placement: str) -> str:
    return PLACEMENT_LABELS.get(placement, placement)


def label_for_option(option: str) -> str:
    return OPTION_LABELS.get(option, option)


def allowed_options_for_base(base: str) -> tuple[str, ...]:
    base_def = load_registry().bases_by_id.get(base)
    return () if base_def is None else base_def.options


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
    bases: list[RegistryBase] = []
    seen_bases: set[str] = set()
    for item in raw.get("base", []):
        base = RegistryBase(
            id=str(item["id"]),
            placements=tuple(str(v) for v in item.get("placements", [])),
            options=normalize_options(item.get("options", [])),
        )
        if base.id not in BASE_IDS:
            raise ValueError("unknown transit preset base %r" % base.id)
        if base.id in seen_bases:
            raise ValueError("duplicate transit preset base %r" % base.id)
        unknown_placements = [placement for placement in base.placements if placement not in PLACEMENT_IDS]
        if unknown_placements:
            raise ValueError("unknown placement(s) %r for %s" % (unknown_placements, base.id))
        unknown_options = [option for option in base.options if option not in OPTION_IDS]
        if unknown_options:
            raise ValueError("unknown option(s) %r for %s" % (unknown_options, base.id))
        seen_bases.add(base.id)
        bases.append(base)

    bases_by_id = {base.id: base for base in bases}

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
        )
        if preset.base not in BASE_IDS:
            raise ValueError("unknown transit preset base %r in %s" % (preset.base, preset.id))
        if preset.base not in bases_by_id:
            raise ValueError("preset %s references base %s without a [[base]] definition" % (preset.id, preset.base))
        if preset.placement not in PLACEMENT_IDS:
            raise ValueError("unknown transit preset placement %r in %s" % (preset.placement, preset.id))
        unknown_options = [option for option in preset.options if option not in OPTION_IDS]
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
    return Registry(tuple(bases), tuple(rowsets), tuple(presets))


def registry_by_key() -> dict[tuple[str, str, tuple[str, ...]], RegistryPreset]:
    return load_registry().presets_by_key


def find_preset(base: str, placement: str, options: Iterable[str]) -> Optional[RegistryPreset]:
    return registry_by_key().get((base, placement, normalize_options(options)))


def bases_with_presets() -> tuple[str, ...]:
    registry = load_registry()
    base_ids = {base.id for base in registry.bases}
    return tuple(base for base in BASE_IDS if base in base_ids)


def infer_base_from_occupant_groups(
    occupant_groups: Iterable[int],
    allowed_bases: Optional[Iterable[str]] = None,
) -> Optional[str]:
    """Infer the closest transit-preset base from an exemplar's OccupantGroups.

    The mapping follows the transportation OccupantGroups declared in
    ``new_properties.xml``. More specific multimodal combinations win before
    their individual component modes.
    """
    groups = {int(group) & 0xFFFFFFFF for group in occupant_groups or ()}
    if allowed_bases is None:
        allowed = set(BASE_IDS)
    else:
        allowed = {str(base) for base in allowed_bases}
    if not groups or not allowed:
        return None

    has_rail = bool(groups & {0x1300, 0x1305, 0xB5C00DF3})
    has_freight = bool(groups & {0x1306, 0xB5C00DF4})
    has_el = bool(groups & {0x1303, 0xB5C00DF6, 0xB5C00DF9})
    has_mono = bool(groups & {0x1307, 0xB5C00DF7})
    has_hrw = 0xB5C00DFA in groups

    candidates = (
        ("hrw_elevated_rail_station", has_hrw and has_el),
        ("monorail_elevated_rail_station", has_mono and has_el),
        ("rail_elevated_rail_station", has_rail and has_el),
        ("passenger_freight_station", has_rail and has_freight),
        ("hrw_station", has_hrw),
        ("monorail_station", has_mono),
        ("elevated_rail_station", has_el),
        ("passenger_train_station", has_rail),
        ("freight_train_station", has_freight),
        ("subway_station", bool(groups & {0x1302, 0xB5C00DF5})),
        ("bus_stop", bool(groups & {0x1301, 0x1926, 0xB5C00DF2})),
        ("toll_booth", 0x130B in groups),
        ("garage", bool(groups & {0x130A, 0xB5C00DF1})),
    )
    for base, matches in candidates:
        if matches and base in allowed:
            return base
    return None
