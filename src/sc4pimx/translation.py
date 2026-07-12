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

import logging
import tomllib

from .config import load_settings
from .paths import asset_path, user_data_path

DEFAULT_LANGUAGE = "en"
logger = logging.getLogger(__name__)

# Populated by _apply() with the message keys actually loaded, so that
# `from .translation import *` exports the strings and nothing else.
__all__: list[str] = []


def available_languages() -> list[str]:
    """Language codes that ship with the app (``assets/lang/*.toml``)."""
    lang_dir = asset_path("lang")
    if not lang_dir.is_dir():
        return [DEFAULT_LANGUAGE]
    return sorted(path.stem for path in lang_dir.glob("*.toml"))


def language_display_name(code: str) -> str:
    """Return the language's self-described menu name, falling back to its code."""
    data = _load_language(code)
    metadata = data.get("meta", {})
    if isinstance(metadata, dict):
        name = metadata.get("Name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return code


def _load_language(code: str) -> dict:
    """Parse a language file without allowing a bad translation to abort startup."""
    for path in (user_data_path(f"lang/{code}.toml"), asset_path("lang", f"{code}.toml")):
        if path.exists():
            try:
                with open(path, "rb") as handle:
                    return tomllib.load(handle)
            except (OSError, tomllib.TOMLDecodeError) as exc:
                logger.error("Could not load language file %s: %s", path, exc)
                # A broken user override must not hide a valid bundled file.
                continue
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
    if isinstance(categories, dict):
        localized = namespace.setdefault("categoryLocalized", {})
        for key, value in categories.items():
            try:
                category_id = int(str(key), 16)
            except (TypeError, ValueError):
                logger.error("Ignoring invalid translated category ID %r", key)
                continue
            if not isinstance(value, str):
                logger.error("Ignoring non-text translation for category 0x%08X", category_id)
                continue
            localized[category_id] = value
        if "categoryLocalized" not in __all__:
            __all__.append("categoryLocalized")


# English is always loaded first as the fallback base.
_apply(_load_language(DEFAULT_LANGUAGE))

_selected_language = str(load_settings().get("Language", DEFAULT_LANGUAGE))
if _selected_language and _selected_language != DEFAULT_LANGUAGE:
    _apply(_load_language(_selected_language))
