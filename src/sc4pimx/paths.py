import os
from pathlib import Path

APP_DIR_NAME = "sc4pimx"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def asset_path(*parts: str) -> Path:
    return project_root().joinpath("assets", *parts)


def package_data_path(name: str) -> Path:
    return Path(__file__).resolve().parent / name


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
