"""User settings and configuration loader for SC4PIM."""
from __future__ import annotations

import ast
import configparser
import os
from pathlib import Path

from paths import package_data_path

ItemOrderForPloppable = 1
ItemOrderForElementary = 2
ItemOrderForHighSchool = 5
ItemOrderForLibrary = 3
ItemOrderForCollege = 7
ItemOrderForMuseum = 6
bAdvancedUser = False


def _env_true(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _coerce_value(value: str):
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return value


def _load_ini(path: Path) -> None:
    if not path.exists():
        return
    raw = path.read_text(encoding="utf-8", errors="replace")
    if not raw.strip():
        return
    if not raw.lstrip().startswith("["):
        raw = "[settings]\n" + raw
    parser = configparser.ConfigParser()
    parser.read_string(raw)
    if "settings" not in parser:
        return
    for key, value in parser["settings"].items():
        globals()[key] = _coerce_value(value)


def _load_legacy_exec(path: Path) -> None:
    if not path.exists() or not _env_true("SC4PIM_ALLOW_SETTINGS_EXEC"):
        return
    source = path.read_text(encoding="utf-8", errors="replace")
    exec(compile(source, str(path), "exec"), globals())


def _load_settings_file(name: str) -> None:
    cwd_path = Path.cwd() / name
    package_path = package_data_path(name)
    _load_ini(cwd_path)
    _load_ini(package_path)
    _load_legacy_exec(cwd_path)
    _load_legacy_exec(package_path)


_load_settings_file("settings.ini")
_load_settings_file("config.ini")
