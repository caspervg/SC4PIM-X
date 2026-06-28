"""Transit-enabled lot-object helpers for the lot editor.

TE lots are regular lots with type-7 LotConfigPropertyLotObject entries.
This module keeps the TE-specific names, presets, value packing, inspector
controls, and OpenGL overlay drawing out of the main lot editor.
"""
import math

import wx
from OpenGL.GL import (
    GL_BLEND,
    GL_DEPTH_TEST,
    GL_ONE_MINUS_SRC_ALPHA,
    GL_SRC_ALPHA,
    glBlendFunc,
    glDisable,
    glEnable,
)

from .SC4DataFunctions import ToCoord, ToUnsigned
from .SC4PathPicker import pick_sc4path
from .SC4PathReader import point_to_lot_2d, point_to_lot_3d
from .translation import *

# Maps the lot-editor "network" value (NETWORK_TYPES) to SC4Path transport
# types worth preselecting in the path picker. Empty tuple = no preselection
# (show all). The values match SC4PathReader.TRANSPORT_TYPES.
NETWORK_TO_TRANSPORTS = {
    0: (1, 2),       # Road -> Car + Sim
    1: (3,),         # Rail -> Train
    2: (1,),         # Highway -> Car
    3: (1, 2),       # Street -> Car + Sim
    4: (),           # Pipe
    5: (),           # Powerline
    6: (1, 2),       # Avenue
    7: (4,),         # Subway
    8: (6,),         # Light rail -> Elevated train
    9: (7,),         # Monorail
    10: (1, 2),      # One-way road
    11: (1, 2),      # Dirt road
    12: (1,),        # Ground highway
}


TRANSIT_OBJECT_TYPE = 7

NETWORK_TYPES = [
    (0, "Road", "Rd"),
    (1, "Rail", "Rail"),
    (2, "Highway", "Hwy"),
    (3, "Street", "St"),
    (4, "Pipe", "Pipe"),
    (5, "Powerline", "Pwr"),
    (6, "Avenue", "Ave"),
    (7, "Subway", "Sub"),
    (8, "Light rail", "El"),
    (9, "Monorail", "Mono"),
    (10, "One-way road", "OWR"),
    (11, "Dirt road", "Dirt"),
    (12, "Ground highway", "GHwy"),
]

NETWORK_NAMES = {value: label for value, label, _short in NETWORK_TYPES}
NETWORK_SHORT_NAMES = {value: short for value, _label, short in NETWORK_TYPES}

EDGE_PRESETS = [
    ("Parking lot", 0x00000000),
    ("South", 0x00000200),
    ("North", 0x02000000),
    ("East", 0x00000002),
    ("West", 0x00020000),
    ("South-west 90", 0x00020200),
    ("North-west 90", 0x02020000),
    ("North-east 90", 0x02000002),
    ("South-east 90", 0x00000202),
    ("North-south", 0x02000200),
    ("East-west", 0x00020002),
    ("SEW tee", 0x00020202),
    ("NSE tee", 0x02000202),
    ("NEW tee", 0x02020002),
    ("NSW tee", 0x02020200),
    ("4-way intersection", 0x02020202),
    ("NS west side (ave/hwy)", 0x02040200),
    ("NS east side (ave/hwy)", 0x02000204),
    ("EW north side (ave/hwy)", 0x04020002),
    ("EW south side (ave/hwy)", 0x00020402),
]

EDGE_PRESET_LABELS = [label for label, _mask in EDGE_PRESETS]
EDGE_PRESET_BY_MASK = {mask: label for label, mask in EDGE_PRESETS}

DEFAULT_TRANSIT_SETTINGS = {
    "network": 0,
    "rep14": 0,
    "direction_mask": 0x00020002,
    "rep16": 0,
}

DIR_BITS = [
    ("N", 0x02000000, 0x04000000, 0),
    ("E", 0x00000002, 0x00000004, 1),
    ("S", 0x00000200, 0x00000400, 2),
    ("W", 0x00020000, 0x00040000, 3),
]

DIR_GEOMETRY = [
    ((0.5, 1.0), (0.5, 0.62)),
    ((1.0, 0.5), (0.62, 0.5)),
    ((0.5, 0.0), (0.5, 0.38)),
    ((0.0, 0.5), (0.38, 0.5)),
]

# The 32-bit transit direction value is four independent per-edge bytes, not a
# bit set. SC4Tool's LotTile.GetTrafficDirection splits the hex string as
# North/West/South/East from the most- to least-significant byte.
DIRECTION_BYTE_SHIFTS = (("N", 24), ("W", 16), ("S", 8), ("E", 0))

# SC4Tool's FormTransitDirection only offers these six per-edge values; any
# other byte is flagged as needing expert editing (LotTile.m_MustExpert).
VALID_DIRECTION_VALUES = (0x00, 0x01, 0x02, 0x03, 0x04, 0xFF)


def direction_bytes(value):
    """Split a 32-bit transit direction value into (north, west, south, east)."""
    value = int(value) & 0xFFFFFFFF
    return tuple((value >> shift) & 0xFF for _name, shift in DIRECTION_BYTE_SHIFTS)


def pack_direction(north, west, south, east):
    """Pack four per-edge bytes back into a 32-bit transit direction value."""
    result = 0
    for byte, (_name, shift) in zip((north, west, south, east), DIRECTION_BYTE_SHIFTS):
        result |= (int(byte) & 0xFF) << shift
    return result & 0xFFFFFFFF


def is_transit_object(values):
    return bool(values) and values[0] == TRANSIT_OBJECT_TYPE


def ensure_transit_values(values):
    """Pad a type-7 lot-config list so UI code can address TE extension fields."""
    if not is_transit_object(values):
        return values
    while len(values) <= 15:
        values.append(0)
    return values


def tile_quad(tile_x, tile_y):
    minx = int(tile_x) * 16
    miny = int(tile_y) * 16
    return [minx, miny, minx + 16, miny + 16]


def quad_for_values(values):
    return [
        ToCoord(values[6]),
        ToCoord(values[7]),
        ToCoord(values[8]),
        ToCoord(values[9]),
    ]


def format_hex32(value):
    return "0x%08X" % (int(value) & 0xFFFFFFFF)


def parse_hex32(text):
    value = int(str(text).strip(), 0)
    if value < 0 or value > 0xFFFFFFFF:
        raise ValueError(value)
    return value


def direction_label(mask):
    return EDGE_PRESET_BY_MASK.get(int(mask) & 0xFFFFFFFF, format_hex32(mask))


def mask_label(mask):
    return direction_label(mask)


def network_label(value):
    return NETWORK_NAMES.get(int(value), "Network %d" % int(value))


def network_short_label(value):
    return NETWORK_SHORT_NAMES.get(int(value), "N%d" % int(value))


def make_transit_values(object_id, tile_x, tile_y, settings=None):
    settings = dict(DEFAULT_TRANSIT_SETTINGS if settings is None else settings)
    minx, miny, maxx, maxy = tile_quad(tile_x, tile_y)
    cx = minx + 8
    cy = miny + 8
    return [
        TRANSIT_OBJECT_TYPE,
        0,
        2,
        ToUnsigned(cx * 65536),
        0,
        ToUnsigned(cy * 65536),
        ToUnsigned(minx * 65536),
        ToUnsigned(miny * 65536),
        ToUnsigned(maxx * 65536),
        ToUnsigned(maxy * 65536),
        0,
        object_id,
        int(settings.get("network", DEFAULT_TRANSIT_SETTINGS["network"])),
        int(settings.get("rep14", DEFAULT_TRANSIT_SETTINGS["rep14"])),
        int(settings.get("direction_mask", DEFAULT_TRANSIT_SETTINGS["direction_mask"])),
        int(settings.get("rep16", DEFAULT_TRANSIT_SETTINGS["rep16"])),
    ]


def cached_transit(values):
    values = ensure_transit_values(values[:])
    return [
        int(math.floor(ToCoord(values[3]) / 16.0)),
        int(math.floor(ToCoord(values[5]) / 16.0)),
        values[2],
        (values[12], 0),
        values[14],
        values[11],
        values[13],
        values[15],
    ]


def update_cached_transit(cache, values):
    replacement = cached_transit(values)
    for idx, item in enumerate(cache):
        if len(item) > 5 and item[5] == values[11]:
            cache[idx] = replacement
            return
    cache.append(replacement)


def remove_cached_transit(cache, object_id):
    for item in list(cache):
        if len(item) > 5 and item[5] == object_id:
            cache.remove(item)


def transit_path_info(tex_data):
    if len(tex_data) > 8 and isinstance(tex_data[8], dict):
        return tex_data[8]
    return None


def transit_path_status(tex_data):
    info = transit_path_info(tex_data)
    if not info:
        return ""
    iid = int(info.get("iid", 0) or 0)
    if not iid:
        return "No SC4Path ID"
    path_file = info.get("path_file")
    if path_file is not None:
        suffix = ""
        if getattr(path_file, "warnings", None):
            suffix = " (%d warning%s)" % (
                len(path_file.warnings),
                "" if len(path_file.warnings) == 1 else "s",
            )
        return "SC4Path 0x%08X: %d paths, %d stops%s" % (
            iid,
            len(path_file.paths),
            len(path_file.stops),
            suffix,
        )
    error = info.get("error")
    if error:
        return "SC4Path 0x%08X: %s" % (iid, error)
    return "SC4Path 0x%08X: missing" % iid


def _preset_index(mask):
    mask = int(mask) & 0xFFFFFFFF
    for idx, (_label, preset_mask) in enumerate(EDGE_PRESETS):
        if preset_mask == mask:
            return idx
    return wx.NOT_FOUND


def _network_index(network):
    network = int(network)
    for idx, (value, _label, _short) in enumerate(NETWORK_TYPES):
        if value == network:
            return idx
    return 0


class TransitInspectorPanel(wx.Panel):
    """Controls for type-7 lot-config objects and placement defaults."""

    def __init__(self, parent, editor):
        wx.Panel.__init__(self, parent, -1)
        self.editor = editor
        self._updating = False
        self._has_selection = False
        self._dir_mask = 0
        box = wx.StaticBox(self, -1, LEXTransitInspector)
        sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        grid = wx.FlexGridSizer(0, 2, 4, 6)
        grid.AddGrowableCol(1, 1)

        self.networkChoice = wx.Choice(
            self,
            -1,
            choices=["%d - %s" % (value, label) for value, label, _short in NETWORK_TYPES],
        )
        self.directionPresetChoice = wx.Choice(self, -1, choices=EDGE_PRESET_LABELS)
        self.directionHex = wx.TextCtrl(self, -1, "", style=wx.TE_READONLY | wx.TE_CENTER)
        self.rep14Hex = wx.TextCtrl(self, -1, "", style=wx.TE_PROCESS_ENTER)
        self.rep16Hex = wx.TextCtrl(self, -1, "", style=wx.TE_PROCESS_ENTER)
        self.pickPathButton = wx.Button(self, -1, LEXTransitPickPath, style=wx.BU_EXACTFIT)
        self.clearPathButton = wx.Button(self, -1, LEXTransitClearPath, style=wx.BU_EXACTFIT)
        rep16_row = wx.BoxSizer(wx.HORIZONTAL)
        rep16_row.Add(self.rep16Hex, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        rep16_row.Add(self.pickPathButton, 0, wx.RIGHT, 2)
        rep16_row.Add(self.clearPathButton, 0)

        # Per-edge direction bytes laid out as a cross. The 2D lot view is
        # South-up (an orientation-0 / South-facing object faces up), so the
        # cross is South-top / North-bottom to match the viewport; East is on
        # the right, West on the left.
        self.dirCtrls = []
        for _name, _shift in DIRECTION_BYTE_SHIFTS:
            ctrl = wx.TextCtrl(self, -1, "00", size=(36, 22),
                               style=wx.TE_PROCESS_ENTER | wx.TE_CENTER)
            ctrl.SetMaxLength(2)
            self.dirCtrls.append(ctrl)
        dir_n, dir_w, dir_s, dir_e = self.dirCtrls
        cross = wx.GridSizer(3, 3, 2, 2)
        for cell in (None, (LEXFacingSouth, dir_s), None,
                     (LEXFacingWest, dir_w), None, (LEXFacingEast, dir_e),
                     None, (LEXFacingNorth, dir_n), None):
            if cell is None:
                cross.Add((0, 0))
            else:
                pair = wx.BoxSizer(wx.HORIZONTAL)
                pair.Add(wx.StaticText(self, -1, cell[0]), 0,
                         wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2)
                pair.Add(cell[1], 0)
                cross.Add(pair, 0, wx.ALIGN_CENTER)

        for label, ctrl in [
            (LEXTransitNetworkType, self.networkChoice),
            (LEXTransitDirectionPreset, self.directionPresetChoice),
            (LEXTransitDirectionHex, self.directionHex),
            (LEXTransitRep14, self.rep14Hex),
            (LEXTransitRep16, rep16_row),
        ]:
            grid.Add(wx.StaticText(self, -1, label), 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)

        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 4)
        # The compass cross is too wide for the label/value grid, so it gets
        # its own full-width centred row.
        sizer.Add(wx.StaticText(self, -1, LEXTransitDirectionEdges), 0,
                  wx.LEFT | wx.RIGHT | wx.TOP, 4)
        sizer.Add(cross, 0, wx.ALIGN_CENTER | wx.ALL, 4)
        self.status = wx.StaticText(self, -1, "")
        sizer.Add(self.status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        self.SetSizer(sizer)

        self.networkChoice.Bind(wx.EVT_CHOICE, self.OnControl)
        self.directionPresetChoice.Bind(wx.EVT_CHOICE, self.OnPreset)
        for ctrl in self.dirCtrls + [self.rep14Hex, self.rep16Hex]:
            ctrl.Bind(wx.EVT_TEXT_ENTER, self.OnTextControl)
            ctrl.Bind(wx.EVT_KILL_FOCUS, self.OnTextControl)
        self.pickPathButton.Bind(wx.EVT_BUTTON, self.OnPickPath)
        self.clearPathButton.Bind(wx.EVT_BUTTON, self.OnClearPath)

    def ShowFor(self, values_list, defaults):
        values_list = values_list or []
        self._has_selection = bool(values_list)
        self._updating = True
        if values_list:
            first = ensure_transit_values(values_list[0][:])
            self.status.SetLabel(LEXTransitSelectedObjects % len(values_list))
            settings = {
                "network": first[12],
                "rep14": first[13],
                "direction_mask": first[14],
                "rep16": first[15],
            }
        else:
            self.status.SetLabel(LEXTransitDefaults)
            settings = defaults
        self.networkChoice.SetSelection(_network_index(settings["network"]))
        self._set_direction_fields(settings["direction_mask"])
        self.rep14Hex.SetValue(format_hex32(settings["rep14"]))
        self.rep16Hex.SetValue(format_hex32(settings["rep16"]))
        self._updating = False
        self.Show()
        self.Layout()

    def _set_direction_fields(self, mask):
        """Refresh the edge cross, hex display and preset choice from a mask."""
        self._dir_mask = int(mask) & 0xFFFFFFFF
        for ctrl, byte in zip(self.dirCtrls, direction_bytes(self._dir_mask)):
            ctrl.SetValue("%02X" % byte)
            ctrl.SetBackgroundColour(wx.NullColour)
        self.directionHex.SetValue(format_hex32(self._dir_mask))
        self.directionPresetChoice.SetSelection(_preset_index(self._dir_mask))

    def _read_direction_mask(self):
        """Pack the four edge fields into a mask, validating each byte.

        Raises ValueError if a field is not hex or not one of the six edge
        values SC4Tool accepts (00-04, FF); the offending field is highlighted.
        """
        edge_bytes = []
        invalid = []
        for ctrl in self.dirCtrls:
            try:
                byte = int(ctrl.GetValue().strip() or "0", 16)
            except ValueError:
                byte = None
            if byte is None or byte not in VALID_DIRECTION_VALUES:
                invalid.append(ctrl)
                ctrl.SetBackgroundColour(wx.Colour(255, 220, 220))
            else:
                ctrl.SetBackgroundColour(wx.NullColour)
            edge_bytes.append(byte)
        for ctrl in self.dirCtrls:
            ctrl.Refresh()
        if invalid:
            raise ValueError("invalid edge direction value")
        return pack_direction(*edge_bytes)

    def _choice_network(self):
        idx = self.networkChoice.GetSelection()
        if idx == wx.NOT_FOUND:
            idx = 0
        return NETWORK_TYPES[idx][0]

    def OnControl(self, event):
        self._apply_controls(event)

    def OnTextControl(self, event):
        self._apply_controls(event)

    def OnPreset(self, event):
        if not self._updating:
            idx = self.directionPresetChoice.GetSelection()
            if idx != wx.NOT_FOUND:
                self._updating = True
                self._set_direction_fields(EDGE_PRESETS[idx][1])
                self._updating = False
        self._apply_controls(event)

    def _apply_controls(self, event):
        if self._updating:
            if hasattr(event, "Skip"):
                event.Skip()
            return
        try:
            direction_mask = self._read_direction_mask()
        except ValueError:
            self.status.SetLabel(LEXTransitInvalidDirValue)
            if hasattr(event, "Skip"):
                event.Skip()
            return
        try:
            values = {
                "network": self._choice_network(),
                "direction_mask": direction_mask,
                "rep14": parse_hex32(self.rep14Hex.GetValue()),
                "rep16": parse_hex32(self.rep16Hex.GetValue()),
            }
        except ValueError:
            self.status.SetLabel(LEXTransitInvalidHex)
            if hasattr(event, "Skip"):
                event.Skip()
            return
        self._updating = True
        self.directionHex.SetValue(format_hex32(direction_mask))
        self.directionPresetChoice.SetSelection(_preset_index(direction_mask))
        self._dir_mask = direction_mask
        self._updating = False
        self.editor.ApplyTransitInspectorEdit(values)
        if hasattr(event, "Skip"):
            event.Skip()

    def OnPickPath(self, event):
        virtual_dat = getattr(self.editor, "virtualDAT", None)
        if virtual_dat is None:
            event.Skip()
            return
        try:
            current = parse_hex32(self.rep16Hex.GetValue())
        except ValueError:
            current = 0
        network = self._choice_network()
        preselect = NETWORK_TO_TRANSPORTS.get(network, ())
        chosen = pick_sc4path(self, virtual_dat, current_iid=current,
                              preselect_transports=preselect)
        if chosen is None:
            event.Skip()
            return
        self.rep16Hex.SetValue(format_hex32(chosen))
        self._apply_controls(event)

    def OnClearPath(self, event):
        self.rep16Hex.SetValue(format_hex32(0))
        self._apply_controls(event)


def draw_transit_overlay(editor, tex_data, active, rot2d, scaling):
    tile_x = tex_data[0]
    tile_y = tex_data[1]
    orientation = tex_data[2] & 15
    network = tex_data[3][0]
    max_mask = tex_data[4]
    object_id = tex_data[5] if len(tex_data) > 5 else None
    min_mask = tex_data[6] if len(tex_data) > 6 else 0
    minx = tile_x * 16
    miny = tile_y * 16
    maxx = minx + 16
    maxy = miny + 16
    selected = object_id in getattr(editor, "selected", [])

    render = editor._render_context
    primitives = editor.glCanvas2D.renderer.primitives
    ox, oy = editor.lotSizeXOffset, editor.lotSizeYOffset
    minx, maxx, miny, maxy = minx - ox, maxx - ox, miny - oy, maxy - oy
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    fill = ((0.10, 0.52, 0.95, 0.42) if selected else
            (0.08, 0.36, 0.78, 0.30) if active else
            (0.08, 0.36, 0.78, 0.20))
    primitives.rect(minx, miny, maxx, maxy, render.mvp, color=fill)
    glDisable(GL_BLEND)

    _draw_mask_edges(primitives, render.mvp, minx, miny, min_mask, orientation,
                     (0.1, 0.32, 0.95, 1.0), 1.5)
    _draw_mask_edges(primitives, render.mvp, minx, miny, max_mask, orientation,
                     (0.95, 0.15, 0.12, 1.0), 2.5)
    primitives.lines(
        ((minx, miny, 0), (maxx, miny, 0), (maxx, maxy, 0), (minx, maxy, 0)),
        render.mvp, color=(0.02, 0.16, 0.35, 1.0), loop=True,
    )
    if active or selected:
        primitives.text(
            minx + 3, miny + 10, network_short_label(network), render.mvp,
            color=(1, 1, 1, 1), scale=0.12, rotation=-rot2d, flip_y=True,
        )


def draw_sc4path_overlay_2d(editor, tex_data, active=False):
    info = transit_path_info(tex_data)
    if not info:
        return
    if int(info.get("iid", 0) or 0) == 0:
        return
    tile_x, tile_y, orientation = tex_data[0], tex_data[1], tex_data[2] & 15
    selected = tex_data[5] in getattr(editor, "selected", [])

    render = editor._render_context
    primitives = editor.glCanvas2D.renderer.primitives
    offset = (-editor.lotSizeXOffset, -editor.lotSizeYOffset)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    path_file = info.get("path_file")
    if path_file is None:
        _draw_path_warning_2d(primitives, render.mvp, tile_x, tile_y, offset)
        glDisable(GL_BLEND)
        return
    path_width = 3.0 if selected else 2.0 if active else 1.5
    for path in path_file.paths:
        color = _transport_color(path.transport, 0.95 if selected or active else 0.72)
        _draw_path_line_2d(primitives, render.mvp, tile_x, tile_y, orientation,
                           path.points, offset, color, path_width)
        _draw_path_arrow_2d(primitives, render.mvp, tile_x, tile_y, orientation,
                            path.points, offset, color, path_width)
    for stop in path_file.stops:
        _draw_stop_cross_2d(primitives, render.mvp, tile_x, tile_y, orientation,
                            stop.point, offset)
    glDisable(GL_BLEND)


def draw_sc4path_overlay_3d(editor, tex_data, active=False):
    info = transit_path_info(tex_data)
    if not info:
        return
    if int(info.get("iid", 0) or 0) == 0:
        return
    tile_x, tile_y, orientation = tex_data[0], tex_data[1], tex_data[2] & 15
    selected = tex_data[5] in getattr(editor, "selected", [])

    render = editor._render_context
    primitives = editor.glCanvas2D.renderer.primitives
    offset = (-editor.lotSizeXOffset, 0, -editor.lotSizeYOffset)
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    path_file = info.get("path_file")
    if path_file is None:
        _draw_path_warning_3d(primitives, render.mvp, tile_x, tile_y, offset)
        glDisable(GL_BLEND)
        return
    path_width = 3.0 if selected else 2.0 if active else 1.5
    for path in path_file.paths:
        color = _transport_color(path.transport, 0.95 if selected or active else 0.76)
        _draw_path_line_3d(primitives, render.mvp, tile_x, tile_y, orientation,
                           path.points, offset, color, path_width)
        _draw_path_arrow_3d(primitives, render.mvp, tile_x, tile_y, orientation,
                            path.points, offset, color, path_width)
    for stop in path_file.stops:
        _draw_stop_cross_3d(primitives, render.mvp, tile_x, tile_y, orientation,
                            stop.point, offset)
    glDisable(GL_BLEND)


def _draw_mask_edges(primitives, mvp, minx, miny, mask, orientation, color, width):
    cx = minx + 8
    cy = miny + 8
    # Lot-object rotation flag 2 is the unrotated tile orientation used by
    # the rest of the lot editor texture rendering.
    rotation_steps = ((int(orientation) & 15) - 2) % 4
    positions = []
    for _name, normal_bit, alt_bit, direction in DIR_BITS:
        if mask & (normal_bit | alt_bit):
            edge, inner = DIR_GEOMETRY[(direction - rotation_steps) % 4]
            ex = minx + edge[0] * 16
            ey = miny + edge[1] * 16
            ix = minx + inner[0] * 16
            iy = miny + inner[1] * 16
            positions.extend(((cx, cy), (ix, iy), (ix, iy), (ex, ey)))
    primitives.lines(positions, mvp, color=color, width=width)


def _transport_color(transport, alpha):
    colors = {
        1: (0.45, 1.0, 0.45),   # Car/road: light green
        2: (0.18, 0.48, 1.0),   # Sim/pedestrian: blue
        3: (1.0, 0.42, 0.42),   # Surface rail: light red
        4: (1.0, 0.9, 0.12),    # Subway: yellow
        5: (0.72, 0.72, 0.72),  # Unused: neutral gray
        6: (1.0, 0.42, 0.82),   # Elevated rail: pink
        7: (0.72, 0.52, 1.0),   # Monorail: light purple
    }
    r, g, b = colors.get(int(transport), (0.95, 0.95, 0.95))
    return r, g, b, alpha


def _draw_path_line_2d(primitives, mvp, tile_x, tile_y, orientation, points, offset, color, width):
    if len(points) < 2:
        return
    positions = []
    for point in points:
        x, y = point_to_lot_2d(tile_x, tile_y, orientation, point)
        positions.append((x + offset[0], y + offset[1]))
    primitives.lines(positions, mvp, color=color, width=width, strip=True)


def _draw_path_line_3d(primitives, mvp, tile_x, tile_y, orientation, points, offset, color, width):
    if len(points) < 2:
        return
    positions = []
    for point in points:
        x, y, z = point_to_lot_3d(tile_x, tile_y, orientation, point)
        positions.append((x + offset[0], y + offset[1], z + offset[2]))
    primitives.lines(positions, mvp, color=color, width=width, strip=True)


def _draw_path_arrow_2d(primitives, mvp, tile_x, tile_y, orientation, points, offset, color, width):
    if len(points) < 2:
        return
    x1, y1 = point_to_lot_2d(tile_x, tile_y, orientation, points[-2])
    x2, y2 = point_to_lot_2d(tile_x, tile_y, orientation, points[-1])
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length < 0.01:
        return
    dx /= length
    dy /= length
    size = 1.4
    bx = x2 - dx * size
    by = y2 - dy * size
    px = -dy * size * 0.55
    py = dx * size * 0.55
    ox, oy = offset
    primitives.lines(
        ((x2 + ox, y2 + oy), (bx + px + ox, by + py + oy),
         (x2 + ox, y2 + oy), (bx - px + ox, by - py + oy)),
        mvp, color=color, width=width,
    )


def _draw_path_arrow_3d(primitives, mvp, tile_x, tile_y, orientation, points, offset, color, width):
    if len(points) < 2:
        return
    x1, y1, z1 = point_to_lot_3d(tile_x, tile_y, orientation, points[-2])
    x2, y2, z2 = point_to_lot_3d(tile_x, tile_y, orientation, points[-1])
    dx = x2 - x1
    dz = z2 - z1
    length = math.hypot(dx, dz)
    if length < 0.01:
        return
    dx /= length
    dz /= length
    size = 1.4
    bx = x2 - dx * size
    bz = z2 - dz * size
    px = -dz * size * 0.55
    pz = dx * size * 0.55
    ox, oy, oz = offset
    primitives.lines(
        ((x2 + ox, y2 + oy, z2 + oz), (bx + px + ox, y2 + oy, bz + pz + oz),
         (x2 + ox, y2 + oy, z2 + oz), (bx - px + ox, y2 + oy, bz - pz + oz)),
        mvp, color=color, width=width,
    )


def _draw_stop_cross_2d(primitives, mvp, tile_x, tile_y, orientation, point, offset):
    x, y = point_to_lot_2d(tile_x, tile_y, orientation, point)
    x, y = x + offset[0], y + offset[1]
    size = 0.75
    primitives.lines(
        ((x - size, y - size), (x + size, y + size),
         (x - size, y + size), (x + size, y - size)),
        mvp, color=(0.06, 0.04, 0.04, 0.95), width=2.0,
    )
    size *= 0.55
    primitives.lines(
        ((x - size, y - size), (x + size, y + size),
         (x - size, y + size), (x + size, y - size)),
        mvp, color=(0.78, 0.05, 0.04, 0.85),
    )


def _draw_stop_cross_3d(primitives, mvp, tile_x, tile_y, orientation, point, offset):
    x, y, z = point_to_lot_3d(tile_x, tile_y, orientation, point)
    x, y, z = x + offset[0], y + offset[1], z + offset[2]
    size = 0.75
    primitives.lines(
        ((x - size, y, z - size), (x + size, y, z + size),
         (x - size, y, z + size), (x + size, y, z - size),
         (x, y, z), (x, y + 1.2, z)),
        mvp, color=(0.06, 0.04, 0.04, 0.95), width=2.0,
    )
    size *= 0.55
    primitives.lines(
        ((x - size, y + 0.02, z - size), (x + size, y + 0.02, z + size),
         (x - size, y + 0.02, z + size), (x + size, y + 0.02, z - size),
         (x, y + 0.02, z), (x, y + 0.8, z)),
        mvp, color=(0.78, 0.05, 0.04, 0.85),
    )


def _draw_path_warning_2d(primitives, mvp, tile_x, tile_y, offset):
    minx = tile_x * 16 + 2
    miny = tile_y * 16 + 2
    maxx = tile_x * 16 + 14
    maxy = tile_y * 16 + 14
    ox, oy = offset
    primitives.lines(
        ((minx + ox, miny + oy), (maxx + ox, maxy + oy),
         (minx + ox, maxy + oy), (maxx + ox, miny + oy)),
        mvp, color=(1.0, 0.55, 0.0, 0.95), width=2.0,
    )


def _draw_path_warning_3d(primitives, mvp, tile_x, tile_y, offset):
    minx = tile_x * 16 + 2
    minz = tile_y * 16 + 2
    maxx = tile_x * 16 + 14
    maxz = tile_y * 16 + 14
    y = 0.25
    ox, oy, oz = offset
    primitives.lines(
        ((minx + ox, y + oy, minz + oz), (maxx + ox, y + oy, maxz + oz),
         (minx + ox, y + oy, maxz + oz), (maxx + ox, y + oy, minz + oz)),
        mvp, color=(1.0, 0.55, 0.0, 0.95), width=2.0,
    )
