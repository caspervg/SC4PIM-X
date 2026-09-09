"""Cache bookkeeping for the LotConfigurations preview images.

Pure Python (no wx / OpenGL): enumerates the eight views cached per lot,
maps them to their on-disk PNG paths, picks the default view from a lot's
required-road flags, and reports which cached files are still missing (the
lot analogue of ``VirtualDat.missing_pictures``). The actual offscreen
rendering lives with the GL viewer in ``SC4LotPreview``; keeping the
path/selection logic here means it stays unit-testable without a GL context.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .paths import image_db_lots_dir, image_db_lots_path
from .SC4CityContext import LOT_VIEW_SIDES, required_road_default_rotation

# Day and night are both cached for every side.
LOT_VIEW_PHASES = (False, True)

# Bump when the render output changes meaningfully: a cache written by an older
# generator no longer matches (see cache_version_current) and is treated as
# stale so it re-renders.
LOT_PREVIEW_GENERATOR_VERSION = 2
_CACHE_VERSION_FILENAME = ".version"


@dataclass(frozen=True)
class LotView:
    """One cached view of a lot: a rep-3 rotation and a day/night phase."""

    rotation: int
    night: bool

    @property
    def side(self) -> str:
        """Compass side letter facing the viewer (``S``/``W``/``N``/``E``)."""
        return LOT_VIEW_SIDES[self.rotation]


def lot_views() -> tuple[LotView, ...]:
    """The eight cached views, ordered side-major then day-before-night."""
    return tuple(LotView(rotation, night) for rotation in range(len(LOT_VIEW_SIDES)) for night in LOT_VIEW_PHASES)


def lot_view_path(gid: int, iid: int, view: LotView) -> Path:
    """On-disk PNG path for a single cached lot view."""
    return image_db_lots_path(gid, iid, view.side, night=view.night)


def default_lot_view(flags: object, night: bool = False) -> LotView:
    """The view shown by default: the lot's first required-road side.

    ``flags`` is the raw 0x4A4A88F0 "LotConfig Required Roads" value (int,
    ``None``, or malformed); it degrades to the unrotated South view.
    """
    return LotView(required_road_default_rotation(flags), night)


def cache_version_path() -> Path:
    """Path to the sidecar recording the generator version of the cache."""
    return image_db_lots_dir() / _CACHE_VERSION_FILENAME


def read_cache_version() -> int | None:
    """Generator version recorded for the cache, or None if absent/unreadable."""
    try:
        return int(cache_version_path().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def write_cache_version(version: int = LOT_PREVIEW_GENERATOR_VERSION) -> None:
    """Record ``version`` as the generator version of the whole cache."""
    path = cache_version_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(int(version)), encoding="utf-8")


def ensure_cache_version() -> None:
    """Record the current version if the cache has none yet (bootstrap)."""
    if read_cache_version() is None:
        write_cache_version()


def cache_version_current() -> bool:
    """True when the cached images were produced by the current generator."""
    return read_cache_version() == LOT_PREVIEW_GENERATOR_VERSION


def lot_view_fresh(
    gid: int,
    iid: int,
    view: LotView,
    updated: float | None = None,
    version_current: bool = True,
) -> bool:
    """True when the cached view is present, current-generation and up to date.

    ``updated`` is the lot's last-modified Unix time (``entry.dateUpdated``);
    a cached view older than that means the lot changed after it was rendered.
    """
    try:
        mtime = lot_view_path(gid, iid, view).stat().st_mtime
    except OSError:
        return False
    if not version_current:
        return False
    if updated is not None and mtime < float(updated):
        return False
    return True


def stale_lot_pictures(
    lots: Iterable[tuple[int, int, float | None]],
    version_current: bool | None = None,
) -> list[tuple[Path, int, int, LotView]]:
    """Render worklist honouring generator version and per-lot modification time.

    ``lots`` is an iterable of ``(gid, iid, updated)`` where ``updated`` is the
    lot's Unix mtime (or None to skip the time check). Returns one
    ``(path, gid, iid, view)`` per view that is missing, from an older
    generator, or older than the lot.
    """
    if version_current is None:
        version_current = cache_version_current()
    worklist: list[tuple[Path, int, int, LotView]] = []
    for gid, iid, updated in lots:
        for view in lot_views():
            if not lot_view_fresh(gid, iid, view, updated, version_current):
                worklist.append((lot_view_path(gid, iid, view), gid, iid, view))
    return worklist
