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

from .paths import data_file_path, ensure_user_data_dir, user_data_path

CONFIG_FILENAME = "config.toml"

DEFAULT_LOT_EDITOR = {
    "BrowserWidth": 330,
    "InspectorWidth": 280,
    "AssetScope": "lot",
    "AssetFilter": "all",
    "AssetSort": "name",
    "AssetSortAscending": True,
    "AssetSearch": "",
    "AssetCompact": False,
    "BackgroundSet": "Default",
    "VisibleLayers2D": {},
    "VisibleLayers3D": {},
    "UndoLimit": 40,
    "Favorites": [],
    "ThumbSize": 72,
    "PreviewMonth": 1,
    "PreviewDay": 1,
    "PreviewMinutes": 720,
    "ShowInactiveProps": False,
    "LightingProfile": "maxis",
}

DEFAULT_MAIN_WINDOW = {
    "Width": 900,
    "Height": 800,
    "X": -1,
    "Y": -1,
    "Maximized": False,
    "TreeSash": 300,
    "ListSash": 400,
    # Resource list (listItems) column widths; the Date column auto-fills.
    "ColName": 240,
    "ColTGI": 195,
    "ColFile": 260,
    # Property detail table (listProperties) column widths; Value auto-fills.
    "PropColName": 210,
    "PropColNameValue": 110,
    "PropColType": 80,
    "PropColRep": 45,
    # Identifiers of tree categories that were expanded when the app last closed.
    "TreeExpanded": [],
}

DEFAULT_DEPENDENCY_CATALOG = {
    "Enabled": False,
    "BaseUrl": "",
    "TimeoutSeconds": 15,
}

DEFAULT_RENDERING = {
    # Multisample anti-aliasing sample count for the on-screen canvas and the
    # offscreen thumbnail/export framebuffers. 0 or 1 disables MSAA; typical
    # values are 2, 4 or 8. Clamped at runtime to what the GPU supports.
    "Samples": 4,
    # Render and blend in a linear/sRGB-correct color space. Disable only if a
    # driver mishandles GL_FRAMEBUFFER_SRGB.
    "SRGB": True,
    # Generate mipmaps for model textures and sample them trilinearly. Removes
    # shimmering on minified/distant textures.
    "Mipmaps": True,
    # Maximum anisotropic filtering for minified model textures (needs Mipmaps).
    # 1.0 disables it; 8.0/16.0 sharpen textures viewed at a grazing angle.
    # Clamped at runtime to the GPU maximum.
    "Anisotropy": 8.0,
}

DEFAULT_STARTUP = {
    # Existing installations intentionally inherit True when this key is
    # absent, giving users one opportunity to review the new setting.
    "ShowFileConfigurationAtStartup": True,
}


def config_path() -> Path:
    """The config.toml that is actually read.

    The per-user copy in ``%APPDATA%\\sc4pimx`` if it exists, otherwise the
    copy shipped in ``assets/`` (the factory settings).
    """
    return data_file_path(CONFIG_FILENAME)


def user_config_path() -> Path:
    """The per-user config path, without falling back to bundled defaults."""
    return user_data_path(CONFIG_FILENAME)


def local_config_has_values() -> bool:
    """Return whether the per-user config exists and contains TOML values."""
    path = user_config_path()
    if not path.exists():
        return False
    try:
        with open(path, "rb") as fh:
            return bool(tomllib.load(fh))
    except (OSError, tomllib.TOMLDecodeError):
        return False


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


def load_user_plugins_root(default: str = "") -> str:
    """Configured root of the user's Plugins folder."""
    paths = load().get("Paths", {})
    if not isinstance(paths, dict):
        return default
    value = str(paths.get("UserPluginsRoot", "")).strip()
    return value or default


def load_lot_editor() -> dict:
    """Persisted LotEditor workbench preferences."""
    value = load().get("LotEditor", {})
    settings = DEFAULT_LOT_EDITOR.copy()
    if isinstance(value, dict):
        settings.update(value)
    return settings


def load_main_window() -> dict:
    """Persisted main-window geometry and column layout."""
    value = load().get("MainWindow", {})
    settings = DEFAULT_MAIN_WINDOW.copy()
    if isinstance(value, dict):
        settings.update(value)
    return settings


def load_dependency_catalog() -> dict:
    """Settings for optional online dependency catalog lookups."""
    value = load().get("DependencyCatalog", {})
    settings = DEFAULT_DEPENDENCY_CATALOG.copy()
    if isinstance(value, dict):
        settings.update(value)
    return settings


def load_rendering() -> dict:
    """Graphics-quality settings for the OpenGL preview pipeline."""
    value = load().get("Rendering", {})
    settings = DEFAULT_RENDERING.copy()
    if isinstance(value, dict):
        settings.update(value)
    return settings


def load_startup() -> dict:
    """Startup behavior, with migration-safe defaults for missing keys."""
    value = load().get("Startup", {})
    settings = DEFAULT_STARTUP.copy()
    if isinstance(value, dict):
        settings.update(value)
    return settings


def should_show_file_configuration() -> bool:
    """Decide whether startup must present the plugin-file configuration."""
    if not local_config_has_values():
        return True
    try:
        return bool(load_startup()["ShowFileConfigurationAtStartup"])
    except Exception:
        return True


def save_main_window(settings: dict) -> Path:
    """Persist main-window geometry and column layout in config.toml."""
    source = config_path()
    text = source.read_text(encoding="utf-8") if source.exists() else ""
    doc = tomlkit.parse(text)
    table = doc.get("MainWindow")
    if table is None or not hasattr(table, "update"):
        table = tomlkit.table()
    for key, value in settings.items():
        table[key] = value
    doc["MainWindow"] = table
    target = ensure_user_data_dir() / CONFIG_FILENAME
    target.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return target


def save_language(code: str) -> Path:
    """Persist the selected UI language as a top-level setting."""
    source = config_path()
    text = source.read_text(encoding="utf-8") if source.exists() else ""
    doc = tomlkit.parse(text)
    doc["Language"] = str(code)
    target = ensure_user_data_dir() / CONFIG_FILENAME
    target.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return target


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


def save_user_plugins_root(path: str) -> Path:
    """Persist the user Plugins root in config.toml."""
    source = config_path()
    text = source.read_text(encoding="utf-8") if source.exists() else ""
    doc = tomlkit.parse(text)
    table = doc.get("Paths")
    if table is None or not hasattr(table, "update"):
        table = tomlkit.table()
    path = str(path).strip()
    table["UserPluginsRoot"] = tomlkit.string(path, literal="'" not in path and "\n" not in path)
    doc["Paths"] = table
    target = ensure_user_data_dir() / CONFIG_FILENAME
    target.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return target


def save_startup(settings: dict) -> Path:
    """Persist startup behavior while preserving the rest of config.toml."""
    source = config_path()
    text = source.read_text(encoding="utf-8") if source.exists() else ""
    doc = tomlkit.parse(text)
    table = doc.get("Startup")
    if table is None or not hasattr(table, "update"):
        table = tomlkit.table()
    for key, value in settings.items():
        table[key] = value
    doc["Startup"] = table
    target = ensure_user_data_dir() / CONFIG_FILENAME
    target.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return target


def save_lot_editor(settings: dict) -> Path:
    """Persist LotEditor workbench preferences in the per-user config.toml."""
    source = config_path()
    text = source.read_text(encoding="utf-8") if source.exists() else ""
    doc = tomlkit.parse(text)
    table = doc.get("LotEditor")
    if table is None or not hasattr(table, "update"):
        table = tomlkit.table()
    for key, value in settings.items():
        table[key] = value
    doc["LotEditor"] = table
    target = ensure_user_data_dir() / CONFIG_FILENAME
    target.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return target
