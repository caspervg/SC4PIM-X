"""UI strings and translations for SC4PIM.

Strings live in ``assets/lang/<code>.toml``. English (``en``) is the base
language; whatever language is selected via the ``Language`` key in
config.toml is overlaid on top, so a partial translation transparently falls
back to English for any missing key.

A ``<code>.toml`` dropped into ``%APPDATA%/sc4pimx/lang/`` overrides the
bundled copy, which makes it easy to test or ship a translation without
rebuilding.

Modules consume the strings via ``from .translation import *``; only the
loaded message keys are exported (see ``__all__``).
"""
from __future__ import annotations

import tomllib

from .config import load_settings
from .paths import asset_path, user_data_path

DEFAULT_LANGUAGE = "en"

# Populated by _apply() with the message keys actually loaded, so that
# `from .translation import *` exports the strings and nothing else.
__all__: list[str] = []


def available_languages() -> list[str]:
    """Language codes that ship with the app (``assets/lang/*.toml``)."""
    lang_dir = asset_path("lang")
    if not lang_dir.is_dir():
        return [DEFAULT_LANGUAGE]
    return sorted(path.stem for path in lang_dir.glob("*.toml"))


def _load_language(code: str) -> dict:
    """Parse a language file; a user override takes precedence over the bundled copy."""
    for path in (user_data_path(f"lang/{code}.toml"), asset_path("lang", f"{code}.toml")):
        if path.exists():
            with open(path, "rb") as handle:
                return tomllib.load(handle)
    return {}


def _apply(data: dict) -> None:
    """Merge a parsed language file into this module's namespace."""
    namespace = globals()
    for section in ("strings", "lists"):
        for key, value in data.get(section, {}).items():
            namespace[key] = value
            if key not in __all__:
                __all__.append(key)
    categories = data.get("categories")
    if categories:
        localized = namespace.setdefault("categoryLocalized", {})
        for key, value in categories.items():
            localized[int(key, 16)] = value
        if "categoryLocalized" not in __all__:
            __all__.append("categoryLocalized")


# English is always loaded first as the fallback base.
_apply(_load_language(DEFAULT_LANGUAGE))

_selected_language = str(load_settings().get("Language", DEFAULT_LANGUAGE))
if _selected_language and _selected_language != DEFAULT_LANGUAGE:
    _apply(_load_language(_selected_language))
