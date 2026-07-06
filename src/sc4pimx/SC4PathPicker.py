"""SC4Path picker dialog.

Browses every SC4Path resource loaded in the VirtualDat, lets the user filter
by transport type and IID prefix, and previews each entry as an axonometric
thumbnail so elevation differences (GLR/elevated rail/subway) are obvious.

The visual style follows :mod:`SC4OccupantGroupPicker`: a top filter row, a
report-mode list with an image column, manual hex entry, and a
``StdDialogButtonSizer`` footer.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

import wx

from .paths import SC4PATH_THUMB_SIZE, sc4path_thumb_dir, sc4path_thumb_path
from .SC4PathReader import (
    TRANSPORT_LABELS,
    TRANSPORT_TYPES,
    SC4PathCatalogItem,
    SC4PathFile,
    list_sc4path_entries,
    load_catalog_item,
)
from .TablerIcons import set_button_icon
from .translation import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

THUMB_SIZE = SC4PATH_THUMB_SIZE
# Back-wall height range in tile-local units (1u == 1m). 30m matches the NAM
# L4 elevation tier; -15m leaves room for subway/tunnel paths below grade.
# Fixed bounds keep every thumbnail framed at the same comparable scale.
WALL_BOTTOM = -15.0
WALL_TOP = 30.0


# Shared transport color palette. Keep in sync with
# ``SC4TransitLotTools._set_transport_color`` so overlay and thumbnail read
# as related.
TRANSPORT_COLORS = {
    1: (115, 215, 115),   # Car
    2: (60, 130, 235),    # Sim
    3: (235, 115, 115),   # Train (surface rail)
    4: (235, 220, 60),    # Subway
    5: (170, 170, 170),   # Unused
    6: (235, 110, 200),   # Elevated train
    7: (175, 130, 235),   # Monorail
}

DEFAULT_TRANSPORT_COLOR = (235, 235, 235)


# ---------------------------------------------------------------------------
# Helpers


def _centre_on_top_level(dialog: wx.Dialog, parent: wx.Window) -> None:
    top = wx.GetTopLevelParent(parent)
    if top is None:
        dialog.CentreOnParent()
        return
    top_pos = top.GetScreenPosition()
    top_size = top.GetSize()
    dlg_size = dialog.GetSize()
    x = top_pos.x + max(0, (top_size.width - dlg_size.width) // 2)
    y = top_pos.y + max(0, (top_size.height - dlg_size.height) // 2)
    dialog.SetPosition((x, y))


def _transport_color(transport: int) -> tuple[int, int, int]:
    return TRANSPORT_COLORS.get(int(transport), DEFAULT_TRANSPORT_COLOR)


def _below_grade_color(color: tuple[int, int, int]) -> tuple[int, int, int]:
    r, g, b = color
    return (max(0, int(r * 0.62)), max(0, int(g * 0.62)), max(0, int(b * 0.62)))


class _TransportSwatch(wx.Panel):
    def __init__(self, parent: wx.Window, colour: tuple[int, int, int]):
        wx.Panel.__init__(self, parent, -1, size=(26, 12))
        self.SetMinSize((26, 12))
        self._colour = wx.Colour(*colour)
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.PaintDC(self)
        dc.SetBackground(wx.Brush(self.GetParent().GetBackgroundColour()))
        dc.Clear()
        width, height = self.GetClientSize()
        y = max(1, height // 2)
        dc.SetPen(wx.Pen(self._colour, 4, wx.PENSTYLE_SOLID))
        dc.DrawLine(2, y, max(2, width - 2), y)


# ---------------------------------------------------------------------------
# Thumbnail rendering
#
# We project tile-local coordinates (x_east, y_north, z_height) onto a 2D
# canvas using a tilted-camera axonometric basis. A high pitch (~65°) gives a
# near-top-down view so colinear / parallel paths (NS or EW runs that overlap
# on a flat iso projection) stay visually separated, while still tilting
# enough to read elevation differences.

_AZIMUTH = math.radians(45.0)
_PITCH = math.radians(50.0)
_FLOOR_X_COS = math.cos(_AZIMUTH)
_FLOOR_X_SIN = math.sin(_AZIMUTH)
_FLOOR_Y_COMPRESS = math.sin(_PITCH)
_HEIGHT_COMPRESS = math.cos(_PITCH)
_DEPTH_FLOOR_COMPRESS = math.cos(_PITCH)
_DEPTH_HEIGHT_COMPRESS = math.sin(_PITCH)


@dataclass(frozen=True)
class _AxoProjector:
    """Project (east, north, height) to thumbnail pixel space."""
    cx: float
    cy: float
    scale: float

    def project(self, x: float, y: float, z: float) -> tuple[float, float]:
        sx = self.cx + (x * _FLOOR_X_COS - y * _FLOOR_X_SIN) * self.scale
        floor_y = (x * _FLOOR_X_SIN + y * _FLOOR_X_COS) * _FLOOR_Y_COMPRESS
        sy = self.cy + floor_y * self.scale - z * _HEIGHT_COMPRESS * self.scale
        return sx, sy

    def depth(self, x: float, y: float, z: float) -> float:
        floor_depth = (x * _FLOOR_X_SIN + y * _FLOOR_X_COS) * _DEPTH_FLOOR_COMPRESS
        return floor_depth + z * _DEPTH_HEIGHT_COMPRESS


def _make_projector(size: tuple[int, int], _path_file: SC4PathFile) -> _AxoProjector:
    width, height = size
    # Always frame the standard 16x16 tile + fixed wall top so different paths
    # render at the same scale — the user can compare elevations by eye.
    half = 8.0
    margin = 4
    floor_w = 2 * half * (_FLOOR_X_COS + _FLOOR_X_SIN)
    floor_h = 2 * half * (_FLOOR_X_SIN + _FLOOR_X_COS) * _FLOOR_Y_COMPRESS
    top_lift = WALL_TOP * _HEIGHT_COMPRESS
    bottom_drop = abs(WALL_BOTTOM) * _HEIGHT_COMPRESS
    scale = min(
        (width - 2 * margin) / floor_w,
        (height - 2 * margin) / (floor_h + top_lift + bottom_drop),
    )
    if scale <= 0:
        scale = 1.0
    cx = width / 2
    # Total drawn vertical extent runs from (cy - floor_h/2 - top_lift)*scale
    # to (cy + floor_h/2 + bottom_drop)*scale. Solving for the top edge gives
    # the centring expression below.
    cy = margin + (floor_h / 2 + top_lift) * scale
    return _AxoProjector(cx=cx, cy=cy, scale=scale)


def _draw_floor_grid(gc: wx.GraphicsContext, projector: _AxoProjector) -> None:
    # 16x16 tile floor, drawn at z=0.
    half = 8.0
    gc.SetPen(wx.Pen(wx.Colour(72, 82, 92), 1))
    for n in (-half, half):
        x1, y1 = projector.project(-half, n, 0)
        x2, y2 = projector.project(half, n, 0)
        path = gc.CreatePath()
        path.MoveToPoint(x1, y1)
        path.AddLineToPoint(x2, y2)
        gc.StrokePath(path)
    for n in (-half, half):
        x1, y1 = projector.project(n, -half, 0)
        x2, y2 = projector.project(n, half, 0)
        path = gc.CreatePath()
        path.MoveToPoint(x1, y1)
        path.AddLineToPoint(x2, y2)
        gc.StrokePath(path)
    # Faint inner grid every 4 units.
    gc.SetPen(wx.Pen(wx.Colour(55, 62, 70), 1, wx.PENSTYLE_DOT))
    for t in (-4.0, 0.0, 4.0):
        x1, y1 = projector.project(t, -half, 0)
        x2, y2 = projector.project(t, half, 0)
        path = gc.CreatePath()
        path.MoveToPoint(x1, y1)
        path.AddLineToPoint(x2, y2)
        gc.StrokePath(path)
        x1, y1 = projector.project(-half, t, 0)
        x2, y2 = projector.project(half, t, 0)
        path = gc.CreatePath()
        path.MoveToPoint(x1, y1)
        path.AddLineToPoint(x2, y2)
        gc.StrokePath(path)


def _draw_back_walls(gc: wx.GraphicsContext, projector: _AxoProjector) -> None:
    """Faint back-edge elevation rulers for reading z without a boxed scene."""
    half = 8.0
    bottom = WALL_BOTTOM
    top = WALL_TOP
    P = projector.project

    edge = wx.Colour(70, 78, 86)
    tick = wx.Colour(70, 78, 86)

    def stroke(p1, p2):
        path = gc.CreatePath()
        path.MoveToPoint(*p1)
        path.AddLineToPoint(*p2)
        gc.StrokePath(path)

    # Faint elevation ticks at below-grade and NAM elevated tiers.
    gc.SetPen(wx.Pen(tick, 1, wx.PENSTYLE_DOT))
    for z in (-7.5, 7.5, 15.0, 22.5):
        stroke(P(-half, -half, z), P(-half, half, z))
        stroke(P(-half, -half, z), P(half, -half, z))
    # Solid ground/top/bottom edges keep the elevation range legible.
    gc.SetPen(wx.Pen(edge, 1))
    for z in (bottom, 0.0, top):
        stroke(P(-half, -half, z), P(-half, half, z))
        stroke(P(-half, -half, z), P(half, -half, z))
    stroke(P(-half, -half, bottom), P(-half, -half, top))
    stroke(P(-half, half, bottom), P(-half, half, top))
    stroke(P(half, -half, bottom), P(half, -half, top))


def _draw_path_segment(
    gc: wx.GraphicsContext,
    projector: _AxoProjector,
    p1,
    p2,
    color,
    arrow: bool = False,
) -> None:
    if p1 is None or p2 is None:
        return
    r, g, b = color
    gc.SetPen(wx.Pen(wx.Colour(r, g, b), 2))
    line = gc.CreatePath()
    x1, y1 = projector.project(p1.x_east, p1.y_north, p1.z_height)
    x2, y2 = projector.project(p2.x_east, p2.y_north, p2.z_height)
    line.MoveToPoint(x1, y1)
    line.AddLineToPoint(x2, y2)
    gc.StrokePath(line)
    if not arrow:
        return
    # Arrowhead on the final segment so directionality is visible at glance.
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 0.5:
        return
    dx /= length
    dy /= length
    size = 5.0
    bx = x2 - dx * size
    by = y2 - dy * size
    px = -dy * size * 0.55
    py = dx * size * 0.55
    head = gc.CreatePath()
    head.MoveToPoint(x2, y2)
    head.AddLineToPoint(bx + px, by + py)
    head.MoveToPoint(x2, y2)
    head.AddLineToPoint(bx - px, by - py)
    gc.StrokePath(head)


def _path_depth_key(projector: _AxoProjector, points) -> tuple[float, float]:
    count = max(1, len(points))
    avg_z = sum(p.z_height for p in points) / count
    avg_depth = sum(projector.depth(p.x_east, p.y_north, p.z_height) for p in points) / count
    return avg_z, avg_depth


def _draw_stop(gc: wx.GraphicsContext, projector: _AxoProjector, point, color) -> None:
    sx, sy = projector.project(point.x_east, point.y_north, point.z_height)
    r, g, b = color
    gc.SetPen(wx.Pen(wx.Colour(20, 20, 20), 1))
    gc.SetBrush(wx.Brush(wx.Colour(r, g, b)))
    gc.DrawEllipse(sx - 2.5, sy - 2.5, 5, 5)


def _draw_depth_sorted_paths(
    gc: wx.GraphicsContext,
    projector: _AxoProjector,
    path_file: SC4PathFile,
) -> None:
    drawables = []
    for path in path_file.paths:
        points = path.points
        for idx in range(max(0, len(points) - 1)):
            segment_points = (points[idx], points[idx + 1])
            color = _transport_color(path.transport)
            if (points[idx].z_height + points[idx + 1].z_height) / 2.0 < 0:
                color = _below_grade_color(color)
            drawables.append((
                _path_depth_key(projector, segment_points),
                "path",
                segment_points,
                color,
                idx == len(points) - 2,
            ))
    for stop in path_file.stops:
        point = stop.point
        drawables.append((
            _path_depth_key(projector, (point,)),
            "stop",
            (point,),
            _transport_color(stop.transport),
            False,
        ))

    # Painter sort: lower/farther geometry first, higher/nearer geometry last.
    # This approximates depth testing for the small 2D thumbnail renderer and
    # ensures elevated paths visibly cross above below-grade or surface paths.
    for _key, kind, points, color, arrow in sorted(drawables, key=lambda item: item[0]):
        if kind == "path":
            _draw_path_segment(gc, projector, points[0], points[1], color, arrow)
        else:
            _draw_stop(gc, projector, points[0], color)


def _metadata_from_item(item: SC4PathCatalogItem) -> dict:
    md = {
        "transports": set(),
        "paths": 0,
        "stops": 0,
        "warnings": 0,
        "warning_text": "",
        "file_name": item.file_name or "",
        "error": item.error,
    }
    if item.path_file is not None:
        md["transports"] = item.transports
        md["paths"] = len(item.path_file.paths)
        md["stops"] = len(item.path_file.stops)
        md["warnings"] = len(item.path_file.warnings)
        md["warning_text"] = "\n".join(item.path_file.warnings)
    return md


def populate_sc4path_cache(item: SC4PathCatalogItem,
                           png_path: Optional[str] = None,
                           preview: Optional["SC4PathImageBuilder"] = None) -> dict:
    """Parse an SC4Path entry, optionally render+save its thumbnail PNG, and
    return its picker-grid metadata.

    Intended to be driven by ``SC4PIMApp._load_finalize`` once per SC4Path
    entry at startup so the picker can open instantly with everything cached.
    The ``png_path`` argument is non-None only for entries on the
    ``missing_sc4path_pictures`` list — already-cached PNGs are left alone.
    The optional preview remains hidden until the first thumbnail is rendered.
    """
    load_catalog_item(item)
    metadata = _metadata_from_item(item)
    if png_path is None or item.path_file is None:
        return metadata
    try:
        bitmap = render_path_thumbnail(item.path_file)
        if bitmap.IsOk():
            sc4path_thumb_dir().mkdir(parents=True, exist_ok=True)
            bitmap.ConvertToImage().SaveFile(png_path, wx.BITMAP_TYPE_PNG)
            if preview is not None:
                preview.Show(item, bitmap)
    except Exception:
        logger.debug("Failed to render SC4Path thumbnail %s", png_path, exc_info=True)
    return metadata


# ---------------------------------------------------------------------------
# Embedded live preview adapter (mirrors ImageDBBuilder for model thumbs)


class SC4PathImageBuilder:
    """Route generated SC4Path thumbnails to the in-window startup surface."""

    def __init__(self, target):
        self.target = target

    def Show(self, item: Optional[SC4PathCatalogItem] = None,
             bitmap: Optional[wx.Bitmap] = None, show: bool = True) -> bool:
        if item is None or bitmap is None or not show:
            return False
        self.target.ShowBitmapPreview(item, bitmap)
        return True

    def Destroy(self) -> None:
        self.target = None


def _load_disk_thumb(iid: int) -> Optional[wx.Bitmap]:
    """Return a cached PNG thumbnail for ``iid`` from disk, or ``None``."""
    path = sc4path_thumb_path(iid)
    if not path.exists():
        return None
    try:
        image = wx.Image(str(path), wx.BITMAP_TYPE_PNG)
        if not image.IsOk():
            return None
        return image.ConvertToBitmap()
    except Exception:
        logger.debug("Failed to load thumbnail %s", path, exc_info=True)
        return None


def _save_disk_thumb(iid: int, bitmap: wx.Bitmap) -> None:
    """Persist a rendered thumbnail PNG for future picker opens."""
    if not bitmap.IsOk():
        return
    try:
        sc4path_thumb_dir().mkdir(parents=True, exist_ok=True)
        bitmap.ConvertToImage().SaveFile(str(sc4path_thumb_path(iid)), wx.BITMAP_TYPE_PNG)
    except Exception:
        logger.debug("Failed to save thumbnail for 0x%08X", iid, exc_info=True)


class _PathThumbProvider:
    """Lazy thumbnail loader, mirroring SC4LETools' ThumbnailProvider.

    Bitmaps are decoded from the on-disk PNG cache in small batches on the
    GUI thread. The picker only requests rows that wx is about to display;
    scrolling promotes those requests ahead of older pending work. Instances
    are shared across picker opens via the VirtualDat so the second open is
    effectively free.
    """

    # Decoded per drain tick. wx.CallAfter has 5-15ms tick overhead on
    # Windows, so a single decode per tick caps the loader at ~50/sec.
    # Batches keep the UI responsive while pushing real throughput.
    BATCH_SIZE = 4

    def __init__(self) -> None:
        self.cache: dict[int, wx.Bitmap] = {}
        self._queue: list[int] = []
        self._queue_cb: dict[int, "Callable[[int, wx.Bitmap], None]"] = {}
        self._draining = False

    def Get(self, iid: int,
            on_loaded: "Optional[Callable[[int, wx.Bitmap], None]]" = None,
            priority: bool = False) -> Optional[wx.Bitmap]:
        if iid in self.cache:
            return self.cache[iid]
        if on_loaded is not None:
            self._queue_cb[iid] = on_loaded
            if iid in self._queue:
                if priority:
                    self._queue.remove(iid)
                    self._queue.append(iid)
            else:
                self._queue.append(iid)
            self._kick()
        return None

    def _kick(self) -> None:
        if not self._draining and self._queue:
            self._draining = True
            wx.CallAfter(self._drain)

    def RestrictTo(self, iids: Iterable[int]) -> None:
        """Prioritise already-pending requests in *iids*.

        The drain pops from the end of the list. Rebuild just the requested
        subset so the first IID in *iids* is decoded first, without creating
        new work or dropping older requests.
        """
        priority: list[int] = []
        seen: set[int] = set()
        for iid in iids:
            if iid in self._queue_cb and iid not in seen:
                seen.add(iid)
                priority.append(iid)
        if not priority:
            self._kick()
            return
        self._queue = [iid for iid in self._queue
                       if iid in self._queue_cb and iid not in seen]
        self._queue.extend(reversed(priority))
        self._kick()

    def PreloadSync(self, iids: Iterable[int]) -> None:
        """Synchronously decode and cache the given IIDs. Used at picker open
        for the rows already visible so the first paint shows real art."""
        for iid in iids:
            if iid in self.cache:
                continue
            bmp = _load_disk_thumb(iid)
            if bmp is not None:
                self.cache[iid] = bmp
            # Drop any duplicate pending request to avoid re-decoding.
            self._queue_cb.pop(iid, None)
            if iid in self._queue:
                self._queue.remove(iid)

    def _drain(self) -> None:
        for _ in range(self.BATCH_SIZE):
            if not self._queue:
                self._draining = False
                return
            iid = self._queue.pop()
            cb = self._queue_cb.pop(iid, None)
            if iid not in self.cache:
                bmp = _load_disk_thumb(iid)
                if bmp is not None:
                    self.cache[iid] = bmp
            if cb is not None and iid in self.cache:
                try:
                    cb(iid, self.cache[iid])
                except RuntimeError:
                    pass
        if self._queue:
            wx.CallAfter(self._drain)
        else:
            self._draining = False


def _thumb_provider_for(virtual_dat) -> _PathThumbProvider:
    provider = getattr(virtual_dat, "_sc4path_thumb_provider", None)
    if provider is None:
        provider = _PathThumbProvider()
        try:
            virtual_dat._sc4path_thumb_provider = provider
        except AttributeError:
            # Stub objects in tests may forbid new attrs; just return it.
            pass
    return provider


def _make_missing_bitmap(size: tuple[int, int] = THUMB_SIZE) -> wx.Bitmap:
    width, height = size
    bmp = wx.Bitmap(width, height)
    dc = wx.MemoryDC(bmp)
    dc.SetBackground(wx.Brush(wx.Colour(30, 36, 42)))
    dc.Clear()
    dc.SetPen(wx.Pen(wx.Colour(200, 110, 60), 2))
    dc.DrawLine(8, 8, width - 8, height - 8)
    dc.DrawLine(8, height - 8, width - 8, 8)
    dc.SelectObject(wx.NullBitmap)
    return bmp


def _make_placeholder_bitmap(size: tuple[int, int] = THUMB_SIZE) -> wx.Bitmap:
    width, height = size
    bmp = wx.Bitmap(width, height)
    dc = wx.MemoryDC(bmp)
    dc.SetBackground(wx.Brush(wx.Colour(30, 36, 42)))
    dc.Clear()
    dc.SelectObject(wx.NullBitmap)
    return bmp


def render_path_thumbnail(path_file: Optional[SC4PathFile], size: tuple[int, int] = THUMB_SIZE,
                          background: Optional[wx.Colour] = None) -> wx.Bitmap:
    width, height = size
    bmp = wx.Bitmap(width, height)
    dc = wx.MemoryDC(bmp)
    bg = background or wx.Colour(30, 36, 42)
    dc.SetBackground(wx.Brush(bg))
    dc.Clear()
    gc = wx.GraphicsContext.Create(dc)
    if gc is None or path_file is None:
        if path_file is None:
            dc.SetTextForeground(wx.Colour(200, 110, 60))
            dc.SetFont(wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT))
            dc.DrawText("?", width // 2 - 4, height // 2 - 8)
        dc.SelectObject(wx.NullBitmap)
        return bmp
    projector = _make_projector(size, path_file)
    _draw_floor_grid(gc, projector)
    _draw_back_walls(gc, projector)
    _draw_depth_sorted_paths(gc, projector, path_file)
    dc.SelectObject(wx.NullBitmap)
    return bmp


# ---------------------------------------------------------------------------
# Dialog


class _PathListCtrl(wx.ListCtrl):
    def __init__(self, parent: wx.Window):
        wx.ListCtrl.__init__(
            self,
            parent,
            -1,
            style=(wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_SINGLE_SEL
                   | wx.LC_HRULES | wx.BORDER_SUNKEN),
        )
        self._rows: list[tuple[int, str, str, str, str]] = []
        self.Bind(wx.EVT_SIZE, self._on_size)

    def _on_size(self, event: wx.SizeEvent) -> None:
        event.Skip()
        wx.CallAfter(self._auto_fill)

    def _auto_fill(self) -> None:
        count = self.GetColumnCount()
        if count < 2:
            return
        used = sum(self.GetColumnWidth(c) for c in range(count - 1))
        remaining = self.GetClientSize().width - used - 4
        if remaining > 80:
            self.SetColumnWidth(count - 1, remaining)

    def set_rows(self, rows: list[tuple[int, str, str, str, str]]) -> None:
        self._rows = rows
        self.SetItemCount(len(rows))
        if rows:
            self.RefreshItems(0, len(rows) - 1)

    def OnGetItemText(self, item: int, col: int) -> str:
        if item < 0 or item >= len(self._rows):
            return ""
        if col <= 0:
            return ""
        try:
            return self._rows[item][col]
        except IndexError:
            return ""

    def OnGetItemImage(self, item: int) -> int:
        if item < 0 or item >= len(self._rows):
            return -1
        return self._rows[item][0]

    def set_row_image(self, row: int, image_index: int) -> None:
        if row < 0 or row >= len(self._rows):
            return
        _old_image, hex_iid, transports, source, information = self._rows[row]
        self._rows[row] = (image_index, hex_iid, transports, source, information)


class SC4PathPickerDialog(wx.Dialog):
    """Pick an SC4Path IID from those loaded in the VirtualDat."""

    def __init__(
        self,
        parent: wx.Window,
        virtual_dat,
        current_iid: int = 0,
        preselect_transports: Iterable[int] = (),
        title: Optional[str] = None,
    ):
        wx.Dialog.__init__(
            self,
            parent,
            -1,
            title or LEXSC4PathPickerTitle,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.virtual_dat = virtual_dat
        self.current_iid = int(current_iid) & 0xFFFFFFFF
        self._catalog: list[SC4PathCatalogItem] = list_sc4path_entries(virtual_dat)
        self._metadata_table: dict[int, dict] = getattr(virtual_dat, "sc4path_metadata", {}) or {}
        self._visible: list[SC4PathCatalogItem] = []
        self._selected_iid: int = self.current_iid
        self._result_iid: Optional[int] = None
        self._missing_thumb = _make_missing_bitmap()
        self._placeholder = _make_placeholder_bitmap()
        self._thumb_provider = _thumb_provider_for(virtual_dat)
        # Image list backing the preview column. Index 0 = placeholder,
        # index 1 = missing/error glyph. Real thumbs are appended lazily and
        # the row's image index is updated via SetItem.
        self._image_list = wx.ImageList(*THUMB_SIZE)
        self._placeholder_idx = self._image_list.Add(self._placeholder)
        self._missing_idx = self._image_list.Add(self._missing_thumb)
        self._image_index_by_iid: dict[int, int] = {}
        self._row_by_iid: dict[int, int] = {}

        active = set(int(t) for t in preselect_transports)
        if not active:
            active = {value for value, _label in TRANSPORT_TYPES}
        self._active_transports: set[int] = active

        # --- Filter row ----------------------------------------------------
        self.search = wx.SearchCtrl(self, -1, style=wx.TE_PROCESS_ENTER)
        if hasattr(self.search, "SetHint"):
            self.search.SetHint(LEXSC4PathPickerSearchHint)
        self.transportChecks: dict[int, wx.CheckBox] = {}
        transport_row = wx.BoxSizer(wx.HORIZONTAL)
        transport_row.Add(wx.StaticText(self, -1, LEXSC4PathPickerTransport), 0,
                          wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        transport_filters = wx.FlexGridSizer(rows=0, cols=3, vgap=4, hgap=12)
        for value, label in TRANSPORT_TYPES:
            item = wx.BoxSizer(wx.HORIZONTAL)
            cb = wx.CheckBox(self, -1, label)
            cb.SetValue(value in self._active_transports)
            cb.Bind(wx.EVT_CHECKBOX, self._on_transport_filter)
            self.transportChecks[value] = cb
            item.Add(cb, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)
            item.Add(_TransportSwatch(self, _transport_color(value)), 0,
                     wx.ALIGN_CENTER_VERTICAL)
            transport_filters.Add(item, 0, wx.ALIGN_CENTER_VERTICAL)
        self.transportAllButton = wx.Button(self, -1, LEXSC4PathPickerAll,
                                            style=wx.BU_EXACTFIT)
        self.transportNoneButton = wx.Button(self, -1, LEXSC4PathPickerNone,
                                             style=wx.BU_EXACTFIT)
        set_button_icon(self.transportAllButton, "select-all")
        set_button_icon(self.transportNoneButton, "deselect")
        self.transportAllButton.Bind(wx.EVT_BUTTON, self._on_transport_all)
        self.transportNoneButton.Bind(wx.EVT_BUTTON, self._on_transport_none)
        filter_buttons = wx.BoxSizer(wx.HORIZONTAL)
        filter_buttons.Add(self.transportAllButton, 0, wx.RIGHT, 4)
        filter_buttons.Add(self.transportNoneButton, 0)
        transport_filters.Add(filter_buttons, 0, wx.ALIGN_CENTER_VERTICAL)
        transport_row.Add(transport_filters, 1, wx.EXPAND)

        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(self.search, 1, wx.EXPAND)

        # --- List ----------------------------------------------------------
        self.list = _PathListCtrl(self)
        self.list.SetImageList(self._image_list, wx.IMAGE_LIST_SMALL)
        self.list.InsertColumn(0, LEXSC4PathPickerColPreview, width=THUMB_SIZE[0] + 16)
        self.list.InsertColumn(1, LEXSC4PathPickerColIID, width=110)
        self.list.InsertColumn(2, LEXSC4PathPickerColTransport, width=180)
        self.list.InsertColumn(3, LEXSC4PathPickerColFile, width=220)
        self.list.InsertColumn(4, LEXSC4PathPickerColInformation, width=380)
        self.list.SetMinSize((1040, 520))
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_select)
        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_activate)
        self.list.Bind(wx.EVT_LIST_CACHE_HINT, self._on_cache_hint)
        # Re-prioritise pending decodes whenever the visible window changes.
        self.list.Bind(wx.EVT_SCROLLWIN, self._on_scroll)
        self.list.Bind(wx.EVT_MOUSEWHEEL, self._on_scroll)

        self.countText = wx.StaticText(self, -1, "")

        # --- Manual entry --------------------------------------------------
        self.hexText = wx.TextCtrl(self, -1, "", style=wx.TE_PROCESS_ENTER)
        if hasattr(self.hexText, "SetHint"):
            self.hexText.SetHint(LEXSC4PathPickerManualHint)
        self.useHexButton = wx.Button(self, -1, LEXSC4PathPickerUseHex)
        set_button_icon(self.useHexButton, "check")
        manual_row = wx.BoxSizer(wx.HORIZONTAL)
        manual_row.Add(wx.StaticText(self, -1, LEXSC4PathPickerManualLabel), 0,
                       wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        manual_row.Add(self.hexText, 1, wx.RIGHT | wx.EXPAND, 6)
        manual_row.Add(self.useHexButton, 0)

        # --- Footer --------------------------------------------------------
        self.clearButton = wx.Button(self, -1, LEXSC4PathPickerClear)
        set_button_icon(self.clearButton, "route-off")
        self.okButton = wx.Button(self, wx.ID_OK)
        self.okButton.SetDefault()
        cancelButton = wx.Button(self, wx.ID_CANCEL)

        btns = wx.StdDialogButtonSizer()
        btns.AddButton(self.okButton)
        btns.AddButton(cancelButton)
        btns.Realize()
        footer = wx.BoxSizer(wx.HORIZONTAL)
        footer.Add(self.clearButton, 0)
        footer.AddStretchSpacer(1)
        footer.Add(btns, 0)

        # --- Compose -------------------------------------------------------
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(top, 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(transport_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        sizer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        sizer.Add(self.countText, 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(manual_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        sizer.Add(footer, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizerAndFit(sizer)
        self.SetMinSize(self.GetSize())

        # --- Bindings ------------------------------------------------------
        self.search.Bind(wx.EVT_TEXT, self._on_filter)
        self.search.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self._on_filter)
        self.clearButton.Bind(wx.EVT_BUTTON, self._on_clear)
        self.useHexButton.Bind(wx.EVT_BUTTON, self._on_use_hex)
        self.hexText.Bind(wx.EVT_TEXT_ENTER, self._on_use_hex)
        self.Bind(wx.EVT_BUTTON, self._on_ok, self.okButton)

        self._refresh()

    # -- Filtering -----------------------------------------------------------

    def _metadata_for(self, item: SC4PathCatalogItem) -> dict:
        md = self._metadata_table.get(item.iid)
        if md is not None:
            return md
        # Fallback: Finalize was skipped (safe mode / env flag) or this is a
        # newly-loaded entry. Parse on demand and cache for the session.
        populate_sc4path_cache(item, str(sc4path_thumb_path(item.iid)))
        md = _metadata_from_item(item)
        self._metadata_table[item.iid] = md
        return md

    def _passes_filters(self, item: SC4PathCatalogItem) -> bool:
        prefix = self.search.GetValue().strip().lower().replace("0x", "")
        if prefix and prefix not in item.hex_iid.lower().replace("0x", ""):
            return False
        if not self._active_transports:
            return False
        transports = self._metadata_for(item).get("transports", set())
        if not transports:
            return False
        if self._active_transports.isdisjoint(transports):
            return False
        return True

    def _refresh(self) -> None:
        self._visible = [it for it in self._catalog if self._passes_filters(it)]
        self._row_by_iid.clear()
        initial_iids = [it.iid for it in self._visible[: self._estimate_visible_rows()]
                        if it.iid not in self._thumb_provider.cache]
        if initial_iids:
            self._thumb_provider.PreloadSync(initial_iids)
        target_row = -1
        self.list.Freeze()
        try:
            rows = []
            for row, item in enumerate(self._visible):
                md = self._metadata_for(item)
                image_index = self._image_index_for(item)
                transports_text = (", ".join(TRANSPORT_LABELS.get(t, "T%d" % t)
                                             for t in sorted(md.get("transports", ())))
                                   or md.get("error", "") or "")
                source = os.path.basename(md.get("file_name", "") or item.file_name or "")
                warnings = md.get("warning_text") or ""
                if not warnings and md.get("warnings"):
                    warnings = "%d warning%s" % (
                        int(md["warnings"]),
                        "" if int(md["warnings"]) == 1 else "s",
                    )
                info_lines = [
                    "%d path%s, %d stop point%s" % (
                        int(md.get("paths") or 0),
                        "" if int(md.get("paths") or 0) == 1 else "s",
                        int(md.get("stops") or 0),
                        "" if int(md.get("stops") or 0) == 1 else "s",
                    )
                ]
                if warnings:
                    info_lines.extend(str(warnings).splitlines())
                rows.append((image_index, item.hex_iid, transports_text,
                             source, "\n".join(info_lines)))
                self._row_by_iid[item.iid] = row
                if item.iid == self._selected_iid:
                    target_row = row
            self.list.set_rows(rows)
        finally:
            self.list.Thaw()
        if target_row >= 0:
            self.list.Select(target_row)
            self.list.EnsureVisible(target_row)
        self.countText.SetLabel(
            LEXSC4PathPickerCount % (len(self._visible), len(self._catalog))
        )
        self._prioritise_visible()

    def _image_index_for(self, item: SC4PathCatalogItem) -> int:
        idx = self._image_index_by_iid.get(item.iid)
        if idx is not None:
            return idx
        if item.error:
            return self._missing_idx
        return self._placeholder_idx

    def _request_thumb(self, item: SC4PathCatalogItem, priority: bool = False) -> None:
        if item.error or item.iid in self._image_index_by_iid:
            return
        cached = self._thumb_provider.Get(item.iid)
        if cached is not None:
            self._on_thumb_ready(item.iid, cached)
            return
        self._thumb_provider.Get(item.iid, self._on_thumb_ready, priority=priority)

    def _on_thumb_ready(self, iid: int, bitmap: wx.Bitmap) -> None:
        if bitmap is None or not bitmap.IsOk():
            return
        idx = self._image_index_by_iid.get(iid)
        if idx is None:
            idx = self._image_list.Add(bitmap)
            self._image_index_by_iid[iid] = idx
        else:
            try:
                self._image_list.Replace(idx, bitmap)
            except Exception:
                pass
        row = self._row_by_iid.get(iid)
        if row is not None:
            try:
                self.list.set_row_image(row, idx)
                self.list.RefreshItems(row, row)
            except RuntimeError:
                pass

    def _estimate_visible_rows(self) -> int:
        # GetCountPerPage isn't always trustworthy before first layout;
        # fall back to a generous estimate so the eager preload covers the
        # whole opening viewport.
        try:
            n = int(self.list.GetCountPerPage())
        except Exception:
            n = 0
        return max(n, 12)

    def _visible_iids(self) -> list[int]:
        start, end = self._visible_range(extra=4)
        return [self._visible[i].iid for i in range(start, end)
                if self._visible[i].iid not in self._thumb_provider.cache]

    def _visible_range(self, extra: int = 0) -> tuple[int, int]:
        try:
            top = int(self.list.GetTopItem())
            count = int(self.list.GetCountPerPage())
        except Exception:
            top = 0
            count = 12
        start = max(0, top - extra)
        end = min(len(self._visible), top + max(count, 1) + extra)
        return start, end

    def _request_rows(self, start: int, end: int, priority: bool = True) -> None:
        start = max(0, start)
        end = min(len(self._visible), end)
        for row in range(end - 1, start - 1, -1):
            self._request_thumb(self._visible[row], priority=priority)

    def _prioritise_visible(self) -> None:
        start, end = self._visible_range(extra=6)
        self._request_rows(start, end, priority=True)
        self._thumb_provider.RestrictTo(self._visible_iids())

    def _on_scroll(self, event: wx.Event) -> None:
        # Defer to after the scroll completes so GetTopItem reports the new
        # row, then re-prioritise the loader queue.
        wx.CallAfter(self._prioritise_visible)
        event.Skip()

    def _on_cache_hint(self, event: wx.ListEvent) -> None:
        start = max(0, event.GetCacheFrom() - 2)
        end = event.GetCacheTo() + 3
        self._request_rows(start, end, priority=False)
        event.Skip()

    # -- Events --------------------------------------------------------------

    def _on_filter(self, event: wx.Event) -> None:
        self._refresh()
        if hasattr(event, "Skip"):
            event.Skip()

    def _sync_transport_filter(self) -> None:
        self._active_transports = {
            value for value, cb in self.transportChecks.items() if cb.GetValue()
        }
        self._refresh()

    def _on_transport_filter(self, event: wx.Event) -> None:
        self._sync_transport_filter()
        event.Skip()

    def _on_transport_all(self, event: wx.Event) -> None:
        for cb in self.transportChecks.values():
            cb.SetValue(True)
        self._sync_transport_filter()
        event.Skip()

    def _on_transport_none(self, event: wx.Event) -> None:
        for cb in self.transportChecks.values():
            cb.SetValue(False)
        self._sync_transport_filter()
        event.Skip()

    def _on_select(self, event: wx.ListEvent) -> None:
        idx = event.GetIndex()
        if 0 <= idx < len(self._visible):
            self._selected_iid = self._visible[idx].iid
        event.Skip()

    def _on_activate(self, event: wx.ListEvent) -> None:
        idx = event.GetIndex()
        if 0 <= idx < len(self._visible):
            self._selected_iid = self._visible[idx].iid
            self._result_iid = self._selected_iid
            self.EndModal(wx.ID_OK)
        event.Skip()

    def _on_use_hex(self, event: wx.Event) -> None:
        raw = self.hexText.GetValue().strip()
        if not raw:
            return
        try:
            value = int(raw, 16) if not raw.lower().startswith("0x") else int(raw, 16)
            if value < 0 or value > 0xFFFFFFFF:
                raise ValueError
        except ValueError:
            wx.MessageBox(LEXSC4PathPickerInvalidHex, LEXSC4PathPickerTitle,
                          wx.OK | wx.ICON_ERROR, self)
            return
        self._result_iid = value
        self.EndModal(wx.ID_OK)

    def _on_clear(self, event: wx.Event) -> None:
        self._result_iid = 0
        self.EndModal(wx.ID_OK)

    def _on_ok(self, event: wx.Event) -> None:
        self._result_iid = self._selected_iid
        event.Skip()

    # -- Public --------------------------------------------------------------

    def GetSelectedIID(self) -> Optional[int]:
        return self._result_iid


def pick_sc4path(parent: wx.Window, virtual_dat, current_iid: int = 0,
                 preselect_transports: Iterable[int] = (),
                 title: Optional[str] = None) -> Optional[int]:
    """Show the picker and return the chosen IID (0 to clear, None on cancel)."""
    dlg = SC4PathPickerDialog(parent, virtual_dat, current_iid, preselect_transports, title)
    try:
        _centre_on_top_level(dlg, parent)
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.GetSelectedIID()
        return None
    finally:
        dlg.Destroy()
