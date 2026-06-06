"""Convert Tyberius' transit switch preset notes to registry TOML.

The source note is an authoring aid, not TOML.  This importer keeps the mapping
rules explicit so future revisions of the note can be converted and reviewed
without hand-copying long switch byte strings.
"""

from __future__ import annotations

import argparse
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SOURCE = Path(".claude/extra-info/SC4PIM-X v2026 Transit Station Switch Pre-Sets v0.5.txt")
DEFAULT_TARGET = Path("assets/transit_switch_presets.toml")
IMPORTED_MARKER = "# Additional presets converted from Tyberius' v0.5 switch pre-set notes."

PLACEMENT_PROXIMITY = "proximity"
PLACEMENT_ON_TOP_NS = "on_top_ns"
PLACEMENT_ON_TOP_WE = "on_top_we"

CATEGORY_IDS = {
    "bus_stop": "0x6c8fbcef",
    "subway_station": "0x0c8fbcf9",
    "elevated_rail_station": "0x4cb2392f",
    "passenger_train_station": "0x0c8fbd07",
    "freight_train_station": "0x6c8fbd13",
    "passenger_freight_station": "0x0c8fbd07",
    "monorail_station": "0x0cb23934",
    "hrw_station": "0x0c8fbd07",
    "garage": "0xacbb8bb5",
}

BASES_WITH_GARAGE_OPTION = {
    "bus_stop",
    "subway_station",
    "elevated_rail_station",
    "passenger_train_station",
    "passenger_freight_station",
    "monorail_station",
    "hrw_station",
    "rail_elevated_rail_station",
    "monorail_elevated_rail_station",
    "hrw_elevated_rail_station",
}

GARAGE_SWITCH = "0x81,0xF0,0x01,0x00"

ART_NAMES = {
    0x81: "outside_in",
    0x82: "inside_out",
}

EDGE_NAMES = {
    0xF0: "all",
    0xA0: "we",
    0x50: "ns",
    0x80: "west",
    0x40: "north",
    0x20: "east",
    0x10: "south",
}

TRAVEL_NAMES = {
    0x00: "walk",
    0x01: "car",
    0x02: "bus",
    0x03: "train",
    0x04: "freight_truck",
    0x05: "freight_train",
    0x06: "subway",
    0x07: "el_train",
    0x08: "monorail",
}

BASE_PATTERNS = (
    ("carpark/garage", "garage"),
    ("bus stop", "bus_stop"),
    ("subway station", "subway_station"),
    ("passanger rail station", "passenger_train_station"),
    ("passenger rail station", "passenger_train_station"),
    ("freight rail station", "freight_train_station"),
    ("passenger and freight rail", "passenger_freight_station"),
    ("el-rail/glr", "elevated_rail_station"),
    ("monorail/btm/hsr", "monorail_station"),
    ("hybrid railway", "hrw_station"),
)

OPTION_PATTERNS = (
    ("bus", "bus_stop"),
    ("subway", "subway_station"),
    ("carpark", "garage"),
)


@dataclass(frozen=True)
class ImportedPreset:
    base: str
    placement: str
    options: tuple[str, ...]
    switches: tuple[int, ...]
    source_label: str

    @property
    def key(self) -> tuple[str, str, tuple[str, ...]]:
        return (self.base, self.placement, self.options)

    @property
    def id(self) -> str:
        parts = [self.base, self.placement, *self.options]
        return ".".join(parts)


def _clean_label(value: str) -> str:
    value = re.sub(r"\([^)]*\)", "", value)
    value = value.replace("+", " ")
    return " ".join(value.lower().split())


def _base_from_label(label: str) -> str | None:
    clean = _clean_label(label)
    for needle, base in BASE_PATTERNS:
        if needle in clean:
            return base
    return None


def _options_from_label(label: str) -> tuple[str, ...]:
    clean = _clean_label(label)
    options = []
    for needle, option in OPTION_PATTERNS:
        if needle in clean:
            options.append(option)
    return tuple(sorted(set(options)))


def _placement_from_label(label: str) -> str | None:
    clean = _clean_label(label)
    if "north-south" in clean or "n-s" in clean:
        return PLACEMENT_ON_TOP_NS
    if "west-east" in clean or "w-e" in clean:
        return PLACEMENT_ON_TOP_WE
    return None


def _normalize_switches(line: str) -> tuple[int, ...]:
    values = [int(token.strip(), 0) & 0xFF for token in line.split(",") if token.strip()]
    if len(values) % 4:
        raise ValueError("switch byte count is not divisible by 4: %s" % line)
    return tuple(values)


def parse_source(path: Path) -> list[ImportedPreset]:
    presets: list[ImportedPreset] = []
    section = PLACEMENT_PROXIMITY
    base: str | None = None
    base_label = ""
    options: tuple[str, ...] = ()
    placement: str | None = None

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#Proximity"):
            section = PLACEMENT_PROXIMITY
            base = None
            options = ()
            placement = None
            continue
        if line.startswith("#On-Top"):
            section = "on_top"
            base = None
            options = ()
            placement = None
            continue
        if line.startswith("*************************************************************************************************"):
            continue
        if line.startswith("IN ALL CASES"):
            base = None
            continue
        if line.startswith(">>"):
            base_label = line[2:].strip()
            base = _base_from_label(base_label)
            options = ()
            placement = PLACEMENT_PROXIMITY if section == PLACEMENT_PROXIMITY else None
            continue
        if line.startswith(">+"):
            options = _options_from_label(line[2:])
            placement = PLACEMENT_PROXIMITY if section == PLACEMENT_PROXIMITY else None
            continue
        if line.startswith(">"):
            found = _placement_from_label(line[1:])
            if found is not None:
                placement = found
            continue
        if not line.startswith("0x"):
            continue
        if base is None or placement is None:
            continue
        if base not in CATEGORY_IDS:
            continue
        presets.append(
            ImportedPreset(
                base=base,
                placement=placement,
                options=options,
                switches=_normalize_switches(line),
                source_label=base_label,
            )
        )
    return presets


def _existing_keys(path: Path, *, ignore_imported_block: bool = False) -> set[tuple[str, str, tuple[str, ...]]]:
    text = path.read_text(encoding="utf-8")
    if ignore_imported_block and IMPORTED_MARKER in text:
        text = text.split(IMPORTED_MARKER, 1)[0]
    raw = tomllib.loads(text)
    keys = set()
    for item in raw.get("preset", []):
        options = tuple(sorted(str(option) for option in item.get("options", [])))
        keys.add((str(item["base"]), str(item["placement"]), options))
    return keys


def _row_name(table: dict[int, str], value: int, field_name: str) -> str:
    if value not in table:
        raise ValueError("unknown %s byte 0x%02X" % (field_name, value))
    return table[value]


def _format_rows(values: tuple[int, ...]) -> list[str]:
    if len(values) % 4:
        raise ValueError("switch byte count is not divisible by 4")
    rows = ["rows = ["]
    for idx in range(0, len(values), 4):
        art, edges, frm, to = values[idx : idx + 4]
        rows.append(
            '  ["%s", "%s", "%s", "%s"],'
            % (
                _row_name(ART_NAMES, art, "direction"),
                _row_name(EDGE_NAMES, edges, "edge"),
                _row_name(TRAVEL_NAMES, frm, "from travel"),
                _row_name(TRAVEL_NAMES, to, "to travel"),
            )
        )
    rows.append("]")
    return rows


def format_presets(presets: list[ImportedPreset], existing_keys: set[tuple[str, str, tuple[str, ...]]]) -> str:
    lines = [
        "",
        IMPORTED_MARKER,
    ]
    emitted = 0
    seen = set(existing_keys)
    for preset in presets:
        if preset.key in seen:
            continue
        seen.add(preset.key)
        emitted += 1
        lines.extend(
            [
                "",
                "[[preset]]",
                'id = "%s"' % preset.id,
                'base = "%s"' % preset.base,
                'placement = "%s"' % preset.placement,
                "options = [%s]" % ", ".join('"%s"' % option for option in preset.options),
                'category_id = "%s"' % CATEGORY_IDS[preset.base],
            ]
        )
        lines.extend(_format_rows(preset.switches))
    if emitted == 0:
        return ""
    return "\n".join(lines) + "\n"


def _replace_imported_block(path: Path, imported_block: str) -> None:
    text = path.read_text(encoding="utf-8")
    prefix = text.split(IMPORTED_MARKER, 1)[0].rstrip()
    path.write_text("%s\n%s" % (prefix, imported_block), encoding="utf-8", newline="\n")


def add_global_garage_variants(presets: list[ImportedPreset]) -> list[ImportedPreset]:
    out = list(presets)
    for preset in presets:
        if preset.base not in BASES_WITH_GARAGE_OPTION or "garage" in preset.options:
            continue
        options = tuple(sorted((*preset.options, "garage")))
        out.append(
            ImportedPreset(
                base=preset.base,
                placement=preset.placement,
                options=options,
                switches=(*preset.switches, *_normalize_switches(GARAGE_SWITCH)),
                source_label="%s + carpark" % preset.source_label,
            )
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--apply", action="store_true", help="append converted presets to the target TOML")
    args = parser.parse_args()

    presets = add_global_garage_variants(parse_source(args.source))
    output = format_presets(presets, _existing_keys(args.target, ignore_imported_block=True))
    if not output:
        print("No new presets to import.")
        return 0
    if args.apply:
        _replace_imported_block(args.target, output)
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
