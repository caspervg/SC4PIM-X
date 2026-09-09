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


def is_user_override(name: str) -> bool:
    """True if a user-supplied override of ``name`` is active."""
    return user_data_path(name).exists()


def override_label(name: str) -> str:
    """Display name of a user override, from its root ``DisplayName`` attribute.

    Empty string when there is no override or the attribute/file is unusable.
    """
    path = user_data_path(name)
    if not path.exists():
        return ""
    try:
        import xml.etree.ElementTree as ET

        return (ET.parse(path).getroot().get("DisplayName") or "").strip()
    except Exception:
        return ""


def background_path(name: str) -> Path:
    """Locate an optional Lot Editor transit-overlay image.

    A user-supplied override in ``<user_data_dir>/backgrounds`` takes
    precedence over the packaged ``assets/backgrounds`` folder.
    """
    user_path = user_data_dir() / "backgrounds" / name
    if user_path.exists():
        return user_path
    return asset_path("backgrounds", name)


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


def catalog_db_path() -> Path:
    """Path to the downloaded SC4 Prop & Texture Catalog SQLite database.

    Re-downloadable cache, so it lives beside the other per-user state rather
    than in ``assets``; a missing file just means the next lookup falls back to
    the online catalog API until the download runs.
    """
    return user_data_dir() / "Catalog.db"


SC4PATH_THUMB_SIZE = (192, 128)


def sc4path_thumb_dir() -> Path:
    """Directory holding the cached SC4Path picker thumbnails (PNG, line art).

    Sibling of ``ImageDB`` / ``ImageDBLarge`` so per-user state stays tidy.
    """
    return user_data_dir() / "ImageDBPaths"


def sc4path_thumb_path(iid: int, size: tuple[int, int] = SC4PATH_THUMB_SIZE) -> Path:
    """Path to a single SC4Path picker thumbnail, keyed by IID + size.

    The width/height suffix means changing the picker's thumbnail size
    invalidates the on-disk cache automatically — old files stay on disk but
    no longer collide with the new ones, so the next Finalize re-renders.
    """
    w, h = size
    return sc4path_thumb_dir() / ("0x%08X-%dx%d.png" % (int(iid) & 0xFFFFFFFF, w, h))


def image_db_lots_dir() -> Path:
    """Directory holding the cached lot-preview PNGs (one per view).

    Sibling of ``ImageDB`` / ``ImageDBLarge``. Unlike the baked-background model
    thumbnail JPGs, lot previews are rendered with transparency so the app
    composites the grey background at display time; they get their own PNG
    cache keyed on GID + IID + view side + day/night phase.
    """
    return user_data_dir() / "ImageDBLots"


def image_db_lots_path(gid: int, iid: int, side: str, night: bool = False) -> Path:
    """Path to a single cached lot-preview PNG inside :func:`image_db_lots_dir`.

    Keyed on GID + IID (IID alone is not unique across groups — a building and
    its lot can share an IID under different GIDs), the compass ``side`` letter
    facing the viewer (``S``/``E``/``N``/``W``) and the day/night phase, e.g.
    ``0xa8fbd372-0xe6b9b2a7-S-D.png``.
    """
    phase = "N" if night else "D"
    name = "0x%08x-0x%08x-%s-%s.png" % (int(gid) & 0xFFFFFFFF, int(iid) & 0xFFFFFFFF, side, phase)
    return image_db_lots_dir() / name
