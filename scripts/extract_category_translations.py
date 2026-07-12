"""Add missing CATEGORY labels from new_properties.xml to a TOML language file.

This is a maintenance/bootstrap tool. Existing translations are never replaced:
the language catalog is the primary source after extraction, while the XML Name
attribute remains the runtime fallback for category IDs absent from the catalog.
"""
from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path
from xml.etree import ElementTree

TABLE_RE = re.compile(r"^\s*\[([^]]+)]\s*(?:#.*)?$")


def xml_categories(path: Path) -> list[tuple[int, str]]:
    root = ElementTree.parse(path).getroot()
    categories: list[tuple[int, str]] = []
    seen: set[int] = set()
    for node in root.iter("CATEGORY"):
        raw_id = node.get("ID", "")
        if not raw_id.lower().startswith("0x"):
            continue
        category_id = int(raw_id, 16)
        if category_id in seen:
            continue
        seen.add(category_id)
        categories.append((category_id, node.get("Name", "")))
    return categories


def add_missing_categories(xml_path: Path, lang_path: Path) -> int:
    text = lang_path.read_text(encoding="utf-8")
    parsed = tomllib.loads(text)
    existing = {int(str(key), 16) for key in parsed.get("categories", {})}
    missing = [(category_id, name) for category_id, name in xml_categories(xml_path)
               if category_id not in existing]
    if not missing:
        return 0

    lines = text.splitlines(keepends=True)
    category_start = None
    insert_at = len(lines)
    for index, line in enumerate(lines):
        match = TABLE_RE.match(line.rstrip("\r\n"))
        if not match:
            continue
        if match.group(1).strip() == "categories":
            category_start = index
        elif category_start is not None:
            insert_at = index
            break
    if category_start is None:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += "\n"
        lines.extend(["\n", "[categories]\n"])
        insert_at = len(lines)

    additions = [f"0x{category_id:08X} = {json.dumps(name, ensure_ascii=False)}\n"
                 for category_id, name in missing]
    lines[insert_at:insert_at] = additions
    lang_path.write_text("".join(lines), encoding="utf-8", newline="")
    return len(missing)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xml", type=Path, default=Path("assets/new_properties.xml"))
    parser.add_argument("--lang", type=Path, default=Path("assets/lang/en.toml"))
    args = parser.parse_args()
    added = add_missing_categories(args.xml, args.lang)
    print(f"Added {added} missing categories to {args.lang}")


if __name__ == "__main__":
    main()
