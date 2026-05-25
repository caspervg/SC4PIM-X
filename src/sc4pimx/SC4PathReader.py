"""SC4Path parser and coordinate helpers.

SC4Path files are line-oriented ASCII resources. The renderer-facing model in
this module normalizes coordinate triples to east/north/height values while
keeping parser warnings non-fatal so broken custom files can still be inspected.
"""
from __future__ import annotations

from dataclasses import dataclass, field


SC4PATH_TYPE = 0x296678F7
SC4PATH_MODEL_GID = 0xA966883F
SC4PATH_TEXTURE_GID = 0x69668828
SC4PATH_GIDS = (SC4PATH_MODEL_GID, SC4PATH_TEXTURE_GID)

SUPPORTED_VERSIONS = ("1.0", "1.1", "1.2")
EDGE_TOLERANCE = 0.35

# SC4Path transport-type values. See Network Specs: there are exactly seven,
# and value 5 is reserved/unused.
TRANSPORT_TYPES = (
    (1, "Car"),
    (2, "Sim"),
    (3, "Train"),
    (4, "Subway"),
    (5, "Unused"),
    (6, "Elevated train"),
    (7, "Monorail"),
)

TRANSPORT_LABELS = {value: label for value, label in TRANSPORT_TYPES}


@dataclass(frozen=True)
class SC4PathPoint:
    x_east: float
    y_north: float
    z_height: float
    line_no: int = 0


@dataclass(frozen=True)
class SC4PathSegment:
    name: str
    comments: tuple[str, ...]
    transport: int
    path_number: int
    entry_side: int
    exit_side: int
    junction_key: int
    points: tuple[SC4PathPoint, ...]
    line_no: int = 0


@dataclass(frozen=True)
class SC4StopPoint:
    name: str
    comments: tuple[str, ...]
    drive_side: int
    transport: int
    path_number: int
    entry_side: int
    exit_side: int
    point: SC4PathPoint
    line_no: int = 0


@dataclass(frozen=True)
class SC4PathFile:
    version: str
    normal_count: int
    stop_count: int
    terrain_key: int
    paths: tuple[SC4PathSegment, ...] = ()
    stops: tuple[SC4StopPoint, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_paths(self) -> bool:
        return bool(self.paths or self.stops)


class SC4PathParseError(ValueError):
    """Raised when a file cannot be parsed as an SC4Path at all."""


class _Scanner:
    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.index = 0
        self.pending_comments: list[str] = []

    def next_value(self, label: str) -> tuple[str, int]:
        while self.index < len(self.lines):
            raw = self.lines[self.index]
            line_no = self.index + 1
            self.index += 1
            value = raw.strip()
            if not value:
                continue
            if value.startswith("--"):
                self.pending_comments.append(value[2:].strip())
                continue
            return value, line_no
        raise SC4PathParseError("Missing %s" % label)

    def consume_comments(self) -> tuple[str, ...]:
        comments = tuple(self.pending_comments)
        self.pending_comments = []
        return comments

    def has_more_values(self) -> bool:
        while self.index < len(self.lines):
            value = self.lines[self.index].strip()
            if not value:
                self.index += 1
                continue
            if value.startswith("--"):
                self.pending_comments.append(value[2:].strip())
                self.index += 1
                continue
            return True
        return False


def parse_sc4path(data: bytes | str) -> SC4PathFile:
    """Parse an SC4Path resource.

    Coordinate lines are interpreted as ``x,y,z``: east-west, north-south, then
    height. That matches the Network Specs coordinate examples and edge values.
    """
    if isinstance(data, bytes):
        text = data.decode("latin-1", errors="replace")
    else:
        text = str(data)

    scanner = _Scanner(text.replace("\r\n", "\n").replace("\r", "\n"))
    warnings: list[str] = []

    header, line_no = scanner.next_value("SC4PATHS header")
    if header.upper() != "SC4PATHS":
        raise SC4PathParseError("Line %d: expected SC4PATHS header" % line_no)

    version, version_line = scanner.next_value("path version")
    if version not in SUPPORTED_VERSIONS:
        warnings.append("Line %d: unsupported SC4Path version %s" % (version_line, version))

    normal_count = _read_int(scanner, "normal path count")
    if version == "1.0":
        stop_count = 0
    else:
        stop_count = _read_int(scanner, "stop path count")
    terrain_key = _read_int(scanner, "terrain variance key")

    paths: list[SC4PathSegment] = []
    stops: list[SC4StopPoint] = []

    for _idx in range(max(0, normal_count)):
        paths.append(_read_path(scanner, version))
    for _idx in range(max(0, stop_count)):
        stops.append(_read_stop(scanner))

    if scanner.has_more_values():
        value, extra_line = scanner.next_value("extra value")
        warnings.append("Line %d: extra value after expected paths: %s" % (extra_line, value))

    _validate_paths(paths, warnings)
    _validate_duplicate_zero_paths(paths, warnings)

    return SC4PathFile(
        version=version,
        normal_count=normal_count,
        stop_count=stop_count,
        terrain_key=terrain_key,
        paths=tuple(paths),
        stops=tuple(stops),
        warnings=tuple(warnings),
    )


@dataclass
class SC4PathCatalogItem:
    """One SC4Path entry as it appears in a VirtualDat, parsed lazily."""

    iid: int
    gid: int
    file_name: str = ""
    entry: object = None
    path_file: SC4PathFile | None = None
    error: str = ""

    @property
    def hex_iid(self) -> str:
        return "0x%08X" % (self.iid & 0xFFFFFFFF)

    @property
    def transports(self) -> set[int]:
        if self.path_file is None:
            return set()
        types = {p.transport for p in self.path_file.paths}
        types |= {s.transport for s in self.path_file.stops}
        return types


def list_sc4path_entries(virtual_dat) -> list[SC4PathCatalogItem]:
    """Return one catalog item per SC4Path entry in the loaded DBPFs.

    Entries are not parsed here — call ``load_catalog_item`` on demand. The
    catalog is stable across calls so callers can cache thumbnails by IID.
    """
    items: list[SC4PathCatalogItem] = []
    seen: set[tuple[int, int]] = set()
    for entry in getattr(virtual_dat, "allEntries", ()):  # tolerate missing attr in tests
        tgi = getattr(entry, "tgi", None)
        if not tgi or tgi[0] != SC4PATH_TYPE:
            continue
        if tgi[1] not in SC4PATH_GIDS:
            continue
        key = (tgi[1], tgi[2])
        if key in seen:
            continue
        seen.add(key)
        items.append(
            SC4PathCatalogItem(
                iid=tgi[2],
                gid=tgi[1],
                file_name=getattr(entry, "fileName", "") or "",
                entry=entry,
            )
        )
    items.sort(key=lambda it: (it.iid, it.gid))
    return items


def load_catalog_item(item: SC4PathCatalogItem) -> SC4PathCatalogItem:
    """Parse the underlying entry on first access. Idempotent."""
    if item.path_file is not None or item.error:
        return item
    entry = item.entry
    if entry is None:
        item.error = "missing"
        return item
    try:
        entry.read_file(None, True, True)
        item.path_file = parse_sc4path(entry.content)
    except SC4PathParseError as exc:
        item.error = "parse error: %s" % exc
    except Exception as exc:  # broad: any decode/decompress failure
        item.error = "load error: %s" % exc
    finally:
        entry.rawContent = None
        entry.content = None
    return item


def transport_summary(path_file: SC4PathFile | None) -> str:
    """Short human-readable list of transport labels in a path file."""
    if path_file is None:
        return ""
    types = sorted({p.transport for p in path_file.paths} |
                   {s.transport for s in path_file.stops})
    if not types:
        return ""
    return ", ".join(TRANSPORT_LABELS.get(t, "T%d" % t) for t in types)


def path_bounds(path_file: SC4PathFile) -> tuple[float, float, float, float, float, float]:
    """Return (min_x, min_y, min_z, max_x, max_y, max_z) over every point."""
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for path in path_file.paths:
        for point in path.points:
            xs.append(point.x_east)
            ys.append(point.y_north)
            zs.append(point.z_height)
    for stop in path_file.stops:
        xs.append(stop.point.x_east)
        ys.append(stop.point.y_north)
        zs.append(stop.point.z_height)
    if not xs:
        return (-8.0, -8.0, 0.0, 8.0, 8.0, 0.0)
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def rotate_local_point(point: SC4PathPoint, orientation: int) -> SC4PathPoint:
    """Rotate a tile-local path point by a lot-object orientation flag.

    Flag 2 is the unrotated orientation used by tile textures. The remaining
    flags follow the same texture-coordinate rotation used by the lot preview.
    """
    x = point.x_east
    y = -point.y_north
    for _idx in range((int(orientation) - 2) % 4):
        x, y = -y, x
    return SC4PathPoint(x, y, point.z_height, point.line_no)


def point_to_lot_2d(tile_x: int, tile_y: int, orientation: int, point: SC4PathPoint) -> tuple[float, float]:
    rotated = rotate_local_point(point, orientation)
    return (
        tile_x * 16.0 + 8.0 + rotated.x_east,
        tile_y * 16.0 + 8.0 + rotated.y_north,
    )


def point_to_lot_3d(
    tile_x: int,
    tile_y: int,
    orientation: int,
    point: SC4PathPoint,
    lift: float = 0.15,
) -> tuple[float, float, float]:
    rotated = rotate_local_point(point, orientation)
    return (
        tile_x * 16.0 + 8.0 + rotated.x_east,
        rotated.z_height + lift,
        tile_y * 16.0 + 8.0 + rotated.y_north,
    )


def _read_int(scanner: _Scanner, label: str) -> int:
    value, line_no = scanner.next_value(label)
    try:
        return int(value, 0)
    except ValueError as exc:
        raise SC4PathParseError("Line %d: invalid %s: %s" % (line_no, label, value)) from exc


def _read_point(scanner: _Scanner, label: str) -> SC4PathPoint:
    value, line_no = scanner.next_value(label)
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 3:
        raise SC4PathParseError("Line %d: invalid coordinate: %s" % (line_no, value))
    try:
        x_east, y_north, z_height = (float(part) for part in parts)
    except ValueError as exc:
        raise SC4PathParseError("Line %d: invalid coordinate: %s" % (line_no, value)) from exc
    return SC4PathPoint(x_east, y_north, z_height, line_no)


def _read_path(scanner: _Scanner, version: str) -> SC4PathSegment:
    transport, line_no = scanner.next_value("transport type")
    comments = scanner.consume_comments()
    name = comments[-1] if comments else ""
    try:
        transport_value = int(transport, 0)
    except ValueError as exc:
        raise SC4PathParseError("Line %d: invalid transport type: %s" % (line_no, transport)) from exc
    path_number = _read_int(scanner, "path number")
    entry_side = _read_int(scanner, "entry side")
    exit_side = _read_int(scanner, "exit side")
    junction_key = _read_int(scanner, "junction key") if version == "1.2" else 0
    point_count = _read_int(scanner, "path point count")
    points = tuple(_read_point(scanner, "path point") for _idx in range(max(0, point_count)))
    return SC4PathSegment(
        name=name,
        comments=comments,
        transport=transport_value,
        path_number=path_number,
        entry_side=entry_side,
        exit_side=exit_side,
        junction_key=junction_key,
        points=points,
        line_no=line_no,
    )


def _read_stop(scanner: _Scanner) -> SC4StopPoint:
    drive_side, line_no = scanner.next_value("stop drive side")
    comments = scanner.consume_comments()
    name = comments[-1] if comments else ""
    try:
        drive_side_value = int(drive_side, 0)
    except ValueError as exc:
        raise SC4PathParseError("Line %d: invalid stop drive side: %s" % (line_no, drive_side)) from exc
    transport = _read_int(scanner, "stop transport type")
    path_number = _read_int(scanner, "stop path number")
    entry_side = _read_int(scanner, "stop entry side")
    exit_side = _read_int(scanner, "stop exit side")
    point = _read_point(scanner, "stop point")
    return SC4StopPoint(
        name=name,
        comments=comments,
        drive_side=drive_side_value,
        transport=transport,
        path_number=path_number,
        entry_side=entry_side,
        exit_side=exit_side,
        point=point,
        line_no=line_no,
    )


def _validate_paths(paths: list[SC4PathSegment], warnings: list[str]) -> None:
    for path in paths:
        if not path.points:
            warnings.append("Line %d: path has no plotting points" % path.line_no)
            continue
        _validate_side(path, path.entry_side, path.points[0], "entry", warnings)
        _validate_side(path, path.exit_side, path.points[-1], "exit", warnings)


def _validate_side(
    path: SC4PathSegment,
    side: int,
    point: SC4PathPoint,
    label: str,
    warnings: list[str],
) -> None:
    if side == 255:
        return
    expected = {
        0: (point.x_east, -8.0, "west"),
        1: (point.y_north, 8.0, "north"),
        2: (point.x_east, 8.0, "east"),
        3: (point.y_north, -8.0, "south"),
    }.get(side)
    if expected is None:
        warnings.append("Line %d: unknown %s side %d" % (path.line_no, label, side))
        return
    value, target, side_name = expected
    if abs(value - target) > EDGE_TOLERANCE:
        warnings.append(
            "Line %d: %s point does not touch %s edge"
            % (point.line_no, label.capitalize(), side_name)
        )


def _validate_duplicate_zero_paths(paths: list[SC4PathSegment], warnings: list[str]) -> None:
    seen: set[tuple[int, int, int]] = set()
    for path in paths:
        if path.path_number != 0:
            continue
        key = (path.transport, path.entry_side, path.exit_side)
        if key in seen:
            warnings.append(
                "Line %d: duplicate zero path number for transport %d entry %d exit %d"
                % (path.line_no, path.transport, path.entry_side, path.exit_side)
            )
        seen.add(key)
