"""Unified TOML configuration for SC4PIM.

`config.toml` replaces the old settings.ini, config.ini and config.xml. It
holds both the scalar settings used by the category eval formulas and the
plugin-scan folder list. A copy in the current working directory overrides
the bundled package copy.

Reading uses the stdlib :mod:`tomllib`. Writing uses :mod:`tomlkit`, which
preserves comments and the original integer representation (so the hex query
GUIDs are not normalised to decimal when the folder list is saved).
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import tomlkit

from .paths import data_file_path, ensure_user_data_dir

CONFIG_FILENAME = "config.toml"


def config_path() -> Path:
    """The config.toml that is actually read.

    The per-user copy in ``%APPDATA%\\sc4pimx`` if it exists, otherwise the
    copy shipped in ``assets/`` (the factory settings).
    """
    return data_file_path(CONFIG_FILENAME)


def load() -> dict:
    """Parse config.toml. Returns an empty dict if it is missing."""
    path = config_path()
    if not path.exists():
        return {}
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def load_settings() -> dict:
    """Top-level scalar settings, keyed by their exact (case-sensitive) name."""
    return {
        key: value
        for key, value in load().items()
        if not isinstance(value, (dict, list))
    }


def load_folders() -> list[tuple[str, int]]:
    """Plugin-scan folders as (path, recurse) pairs."""
    folders: list[tuple[str, int]] = []
    for entry in load().get("Folders", []):
        path = str(entry.get("Path", "")).strip()
        if path:
            folders.append((path, int(bool(entry.get("Recurse", False)))))
    return folders


def save_folders(folders) -> Path:
    """Persist the plugin-scan folder list, preserving the existing settings.

    Only the ``Folders`` array of tables is replaced; tomlkit keeps the rest
    of the document (settings, hex literals, comments) byte-for-byte.
    `folders` is an iterable of (path, recurse) pairs. The result is written
    to config.toml in the per-user data directory (%APPDATA%\\sc4pimx).
    """
    source = config_path()
    text = source.read_text(encoding="utf-8") if source.exists() else ""
    doc = tomlkit.parse(text)

    array_of_tables = tomlkit.aot()
    for path, recurse in folders:
        path = str(path)
        if path.strip():
            table = tomlkit.table()
            # Literal string keeps Windows backslashes unescaped; fall back to
            # a basic string for the rare path containing a single quote.
            literal = "'" not in path and "\n" not in path
            table["Path"] = tomlkit.string(path, literal=literal)
            table["Recurse"] = bool(recurse)
            array_of_tables.append(table)
    doc["Folders"] = array_of_tables

    target = ensure_user_data_dir() / CONFIG_FILENAME
    target.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return target
