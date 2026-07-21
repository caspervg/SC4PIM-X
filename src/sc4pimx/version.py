"""Application version helpers."""

import os
from importlib import metadata

VERSION = "2026.8.0"


def get_version() -> str:
    """Return the display version for source runs and packaged builds."""
    override = os.environ.get("SC4PIMX_VERSION")
    if override:
        return override.removeprefix("v")
    if VERSION:
        return VERSION
    try:
        return metadata.version("sc4pim-x")
    except metadata.PackageNotFoundError:
        return "unknown"
