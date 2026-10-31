"""Cache bookkeeping for the LotConfigurations preview images.

Pure Python (no wx / OpenGL): enumerates the eight views cached per lot,
maps them to their on-disk PNG paths, picks the default view from a lot's
required-road flags, and reports which cached files are still missing (the
lot analogue of ``VirtualDat.missing_pictures``). The actual offscreen
rendering lives with the GL viewer in ``SC4LotPreview``; keeping the
path/selection logic here means it stays unit-testable without a GL context.
"""

from __future__ import annotations

import math
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .paths import image_db_lots_dir, image_db_lots_path
from .SC4CityContext import LOT_VIEW_SIDES, required_road_default_rotation

# Day and night are both cached for every side.
LOT_VIEW_PHASES = (False, True)

# Bump when the render output changes meaningfully: a cache written by an older
# generator no longer matches (see cache_valid_since) and is treated as stale
# so it re-renders.
LOT_PREVIEW_GENERATOR_VERSION = 2
_CACHE_VERSION_FILENAME = ".version"
# Seconds the valid-since stamp is backed off to absorb coarse (up to 2 s,
# FAT) filesystem mtime resolution.
_MTIME_SLACK = 2


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


def read_cache_stamp() -> tuple[int, float] | None:
    """``(version, valid_since)`` recorded for the cache, or None if absent/unreadable.

    ``valid_since`` is the Unix time the version took effect: only images
    written at or after it were produced by that generator.
    """
    try:
        version, valid_since = cache_version_path().read_text(encoding="utf-8").split()
        return int(version), float(valid_since)
    except (OSError, ValueError):
        return None


def read_cache_version() -> int | None:
    """Generator version recorded for the cache, or None if absent/unreadable."""
    stamp = read_cache_stamp()
    return None if stamp is None else stamp[0]


def write_cache_version(version: int = LOT_PREVIEW_GENERATOR_VERSION, valid_since: float | None = None) -> None:
    """Record ``version`` as the generator version of images written from ``valid_since`` on.

    ``valid_since`` (default now) is backed off a few seconds so coarse
    filesystem mtimes of images written right after it still count as newer.
    """
    if valid_since is None:
        valid_since = time.time()
    path = cache_version_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{int(version)} {math.floor(valid_since) - _MTIME_SLACK}", encoding="utf-8")


def cache_valid_since() -> float | None:
    """Time from which cached images are current-generation, or None if none are."""
    stamp = read_cache_stamp()
    if stamp is None or stamp[0] != LOT_PREVIEW_GENERATOR_VERSION:
        return None
    return stamp[1]


def ensure_cache_version(valid_since: float | None = None) -> float:
    """Make the current generator version the recorded one; return its ``valid_since``.

    Leaves an already-current stamp alone (re-stamping would invalidate every
    image rendered since). Otherwise stamps it from ``valid_since`` (default
    now), which keeps any older image stale.
    """
    current = cache_valid_since()
    if current is not None:
        return current
    write_cache_version(valid_since=valid_since)
    return cache_valid_since()


def lot_view_fresh(
    gid: int,
    iid: int,
    view: LotView,
    updated: float | None = None,
    valid_since: float | None = 0.0,
) -> bool:
    """True when the cached view is present, current-generation and up to date.

    ``updated`` is the lot's last-modified Unix time (``entry.dateUpdated``);
    a cached view older than that means the lot changed after it was rendered.
    ``valid_since`` is :func:`cache_valid_since`: a view written before it
    came from an older generator (or None: no view is current-generation).
    """
    if valid_since is None:
        return False
    try:
        mtime = lot_view_path(gid, iid, view).stat().st_mtime
    except OSError:
        return False
    if mtime < valid_since:
        return False
    if updated is not None and mtime < float(updated):
        return False
    return True


def stale_lot_pictures(
    lots: Iterable[tuple[int, int, float | None]],
    valid_since: float | None = 0.0,
) -> list[tuple[Path, int, int, LotView]]:
    """Render worklist honouring generator version and per-lot modification time.

    ``lots`` is an iterable of ``(gid, iid, updated)`` where ``updated`` is the
    lot's Unix mtime (or None to skip the time check). Returns one
    ``(path, gid, iid, view)`` per view that is missing, from an older
    generator (see :func:`cache_valid_since`), or older than the lot.
    """
    worklist: list[tuple[Path, int, int, LotView]] = []
    for gid, iid, updated in lots:
        for view in lot_views():
            if not lot_view_fresh(gid, iid, view, updated, valid_since):
                worklist.append((lot_view_path(gid, iid, view), gid, iid, view))
    return worklist
