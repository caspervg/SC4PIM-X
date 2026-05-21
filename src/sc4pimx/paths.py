import os
import sys
from pathlib import Path

APP_DIR_NAME = "sc4pimx"


def _bundle_root() -> Path | None:
    """Root of the extracted PyInstaller bundle, or None for a source run."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return None


def project_root() -> Path:
    bundle = _bundle_root()
    if bundle is not None:
        return bundle
    return Path(__file__).resolve().parents[2]


def asset_path(*parts: str) -> Path:
    return project_root().joinpath("assets", *parts)


def data_file_path(name: str) -> Path:
    """Locate a bundled data file (config.toml, new_properties.xml, ...).

    A user-supplied override in the per-user data directory takes precedence;
    otherwise the copy shipped in ``assets/`` is used.
    """
    user_path = user_data_path(name)
    if user_path.exists():
        return user_path
    return asset_path(name)


def user_data_dir() -> Path:
    """Per-user writable directory for config and runtime state.

    Windows: ``%APPDATA%\\sc4pimx``. Other platforms fall back to
    ``~/.local/share/sc4pimx``.
    """
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_DIR_NAME
    return Path.home() / ".local" / "share" / APP_DIR_NAME


def user_data_path(name: str) -> Path:
    """Path to a file inside :func:`user_data_dir` (not guaranteed to exist)."""
    return user_data_dir() / name


def ensure_user_data_dir() -> Path:
    """Return :func:`user_data_dir`, creating it if necessary."""
    path = user_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def image_db_dir(large: bool = False) -> Path:
    """Directory holding the cached model-thumbnail JPGs.

    ``ImageDB`` for the small (64px) thumbnails, ``ImageDBLarge`` for the
    128px ones, both inside the per-user data directory.
    """
    return user_data_dir() / ("ImageDBLarge" if large else "ImageDB")


def image_db_path(name: str, large: bool = False) -> Path:
    """Path to a single cached thumbnail inside :func:`image_db_dir`."""
    return image_db_dir(large) / name
