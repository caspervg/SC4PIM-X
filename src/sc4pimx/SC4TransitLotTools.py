"""Transit-enabled lot-object helpers for the lot editor.

TE lots are regular lots with type-7 LotConfigPropertyLotObject entries.
This module keeps the TE-specific names, presets, value packing, inspector
controls, and OpenGL overlay drawing out of the main lot editor.
"""
import math

import wx
from OpenGL.GL import (
    GL_BLEND,
    GL_LINES,
    GL_LINE_LOOP,
    GL_ONE_MINUS_SRC_ALPHA,
    GL_QUADS,
    GL_SRC_ALPHA,
    GL_TEXTURE_2D,
    glBegin,
    glBlendFunc,
    glColor3f,
    glColor4f,
    glDisable,
    glEnable,
    glEnd,
    glLineWidth,
    glPopMatrix,
    glPushMatrix,
    glRectf,
    glTranslatef,
    glVertex2f,
    glVertex3f,
)

from .SC4DataFunctions import ToCoord, ToUnsigned
from .translation import *


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
            (LEXTransitRep16, self.rep16Hex),
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

    glPushMatrix()
    try:
        glTranslatef(-editor.lotSizeXOffset, -editor.lotSizeYOffset, 0)
        glDisable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        if selected:
            glColor4f(0.10, 0.52, 0.95, 0.42)
        elif active:
            glColor4f(0.08, 0.36, 0.78, 0.30)
        else:
            glColor4f(0.08, 0.36, 0.78, 0.20)
        glRectf(minx, miny, maxx, maxy)
        glDisable(GL_BLEND)

        glLineWidth(1.5)
        glColor3f(0.1, 0.32, 0.95)
        _draw_mask_edges(minx, miny, min_mask, orientation)
        glLineWidth(2.5)
        glColor3f(0.95, 0.15, 0.12)
        _draw_mask_edges(minx, miny, max_mask, orientation)
        glLineWidth(1.0)

        glBegin(GL_LINE_LOOP)
        glColor3f(0.02, 0.16, 0.35)
        glVertex3f(minx, miny, 0)
        glVertex3f(maxx, miny, 0)
        glVertex3f(maxx, maxy, 0)
        glVertex3f(minx, maxy, 0)
        glEnd()

        if active or selected:
            editor.glCanvas2D.text_2d(
                minx + 3,
                miny + 10,
                network_short_label(network),
                rot2d,
                scaling,
            )
    finally:
        glPopMatrix()


def _draw_mask_edges(minx, miny, mask, orientation):
    cx = minx + 8
    cy = miny + 8
    # Lot-object rotation flag 2 is the unrotated tile orientation used by
    # the rest of the lot editor texture rendering.
    rotation_steps = ((int(orientation) & 15) - 2) % 4
    glBegin(GL_LINES)
    for _name, normal_bit, alt_bit, direction in DIR_BITS:
        if mask & (normal_bit | alt_bit):
            edge, inner = DIR_GEOMETRY[(direction + rotation_steps) % 4]
            ex = minx + edge[0] * 16
            ey = miny + edge[1] * 16
            ix = minx + inner[0] * 16
            iy = miny + inner[1] * 16
            glVertex2f(cx, cy)
            glVertex2f(ix, iy)
            glVertex2f(ix, iy)
            glVertex2f(ex, ey)
    glEnd()
