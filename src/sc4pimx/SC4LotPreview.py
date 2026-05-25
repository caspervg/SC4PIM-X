"""SC4 lot preview and editor with 2D/3D rendering."""
import logging
import math
import os
from contextlib import contextmanager

import numpy
import wx
import wx.lib.sized_controls as sc
from OpenGL.GLU import gluUnProject
from PIL import Image

from . import FSHConverter, SC4IconMakerDlg, treeDnD
from .ATCReader import *
from .config import load_lot_editor, save_lot_editor
from .paths import asset_path, background_path, background_set_dir, background_sets
from .SC4Data import *
from .SC4DataFunctions import ToCoord, ToTile, ToUnsigned, model_is_prelit, night_state_for
from .SC4LETools import *
from .SC4OpenGL import *
from .S3DShaders import DAY_PRESET, NIGHT_PRESET, SC4LightingProgram, approximate_model_light
from .SC4TransitLotTools import (
    DEFAULT_TRANSIT_SETTINGS,
    TRANSIT_OBJECT_TYPE,
    TransitInspectorPanel,
    cached_transit,
    draw_transit_overlay,
    ensure_transit_values,
    format_hex32,
    is_transit_object,
    make_transit_values,
    mask_label,
    network_label,
    quad_for_values,
    remove_cached_transit,
    tile_quad,
    update_cached_transit,
)
from .translation import *

logger = logging.getLogger(__name__)

MODE_PROP_ONLY = 1
MODE_BASETEX_ONLY = 2
MODE_OVERTEX_ONLY = 4
MODE_BUILDING_ONLY = 8
MODE_TE_ONLY = 16
MODE_FLORA_ONLY = 32
MODE_CONSTRAINT_ONLY = 64
MODE_DISPLAY_FULL = MODE_PROP_ONLY | MODE_BASETEX_ONLY | MODE_OVERTEX_ONLY | MODE_BUILDING_ONLY | MODE_TE_ONLY | MODE_FLORA_ONLY | MODE_CONSTRAINT_ONLY
MODE_DISPLAY_LE = MODE_PROP_ONLY | MODE_BASETEX_ONLY | MODE_OVERTEX_ONLY | MODE_BUILDING_ONLY | MODE_FLORA_ONLY
MODE_DISPLAY_TE = MODE_BASETEX_ONLY | MODE_OVERTEX_ONLY | MODE_TE_ONLY
MODE_DISPLAY_CONSTRAINT = MODE_BASETEX_ONLY | MODE_OVERTEX_ONLY | MODE_CONSTRAINT_ONLY
MODE_EDIT_PAN = 0
MODE_EDIT_BASETEX = 1
MODE_EDIT_OVERTEX = 2
MODE_EDIT_PROP = 4
MODE_EDIT_BUILDING = 8
MODE_EDIT_FLORA = 16
MODE_EDIT_TRANSIT = 32
MODE_EDIT_CONSTRAINT = 64
LAYER_BASE = 'base_textures'
LAYER_OVERLAY = 'overlay_textures'
LAYER_WATER = 'water_constraints'
LAYER_LAND = 'land_constraints'
LAYER_TRANSIT = 'transit'
LAYER_ROAD_EDGES = 'road_edges'
LAYER_BUILDING = 'building'
LAYER_PROPS = 'props'
LAYER_FLORA = 'flora'
LAYER_SNAP_GRID = 'snap_grid'
LAYER_SELECTION = 'selection'
LAYER_MISSING = 'missing_markers'
LAYER_CARDINALS = 'cardinal_labels'
LAYER_BACKGROUND = 'terrain_background'
LAYER_SPECS = [
    (LAYER_BASE, LEXLayerBaseTextures),
    (LAYER_OVERLAY, LEXLayerOverlayTextures),
    (LAYER_WATER, LEXLayerWaterConstraints),
    (LAYER_LAND, LEXLayerLandConstraints),
    (LAYER_TRANSIT, LEXLayerTransit),
    (LAYER_ROAD_EDGES, LEXLayerRoadEdges),
    (LAYER_BUILDING, LEXLayerBuilding),
    (LAYER_PROPS, LEXLayerProps),
    (LAYER_FLORA, LEXLayerFlora),
    (LAYER_SNAP_GRID, LEXLayerSnapGrid),
    (LAYER_SELECTION, LEXLayerSelection),
    (LAYER_MISSING, LEXLayerMissingMarkers),
    (LAYER_CARDINALS, LEXLayerCardinalLabels),
    (LAYER_BACKGROUND, LEXLayerTerrainBackground),
]
ID_PAN = wx.NewIdRef()
ID_PROP = wx.NewIdRef()
ID_BUILDING = wx.NewIdRef()
ID_BASETEX = wx.NewIdRef()
ID_OVERTEX = wx.NewIdRef()
ID_FLORA = wx.NewIdRef()
ID_FAMILY = wx.NewIdRef()
ID_DISPLAY = wx.NewIdRef()
ID_VIEW = wx.NewIdRef()
ID_ZOOM = wx.NewIdRef()
ID_UNZOOM = wx.NewIdRef()
ID_ZOOM1 = wx.NewIdRef()
ID_ZOOM2 = wx.NewIdRef()
ID_ZOOM3 = wx.NewIdRef()
ID_ZOOM4 = wx.NewIdRef()
ID_ZOOM5 = wx.NewIdRef()
ID_ROTCW = wx.NewIdRef()
ID_ROTCCW = wx.NewIdRef()

def gl_texture_name(value):
    return int(value)


def delete_gl_texture(value):
    glDeleteTextures([gl_texture_name(value)])


@contextmanager
def pushed_modelview_matrix():
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    try:
        yield
    finally:
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()


def texture_coords_for_flag(flag):
    coords = [(0, 1), (0, 0), (1, 0), (1, 1)]
    rotation = flag & 15
    if rotation == 0:
        coords = [coords[2], coords[3], coords[0], coords[1]]
    elif rotation == 1:
        coords = [coords[1], coords[2], coords[3], coords[0]]
    elif rotation == 3:
        coords = [coords[3], coords[0], coords[1], coords[2]]
    if flag & 2147483648 == 2147483648:
        coords = [(1 - u, v) for u, v in coords]
    return coords


def ToTileOrigin(val):
    # Textures/water/land/TE quads cover whole 16m tiles. The stored position
    # is the object centre, which may not sit exactly on a tile centre, so
    # floor it to the origin of the tile it falls in instead of just shifting
    # by half a tile (ToTile - 0.5) — that left saved textures straddling
    # tile boundaries when the centre was not perfectly aligned.
    return math.floor(ToTile(val))


def minmax(a, b):
    if a < b:
        return (a, b)
    return (b, a)


def QuadInQuad(qIn, qOut):
    minx, maxx = minmax(qOut[0], qOut[2])
    miny, maxy = minmax(qOut[1], qOut[3])
    if qIn[0] > minx and qIn[2] < maxx and qIn[1] > miny and qIn[3] < maxy:
        return True
    return False


class LEDropTarget(wx.PyDropTarget):

    def __init__(self, glCanvas2D):
        wx.PyDropTarget.__init__(self)
        self._makeObjects()
        self.glCanvas2D = glCanvas2D
        self.frame = self.glCanvas2D.displayer

    def _makeObjects(self):
        self.data = treeDnD.DropData()
        comp = wx.DataObjectComposite()
        comp.Add(self.data)
        self.comp = comp
        self.SetDataObject(comp)

    def OnEnter(self, x, y, d):
        return d

    def OnLeave(self):
        pass

    def OnDrop(self, x, y):
        return True

    def OnDragOver(self, x, y, d):
        self.glCanvas2D.SetCurrent()
        self.frame.SetMatForUnproj()
        h = self.frame.size[1]
        px, py, pz = gluUnProject(x, h - y, 0)
        maxx = self.frame.exemplar.GetProp(2297284496)[0] * 8
        maxy = self.frame.exemplar.GetProp(2297284496)[1] * 8
        minx = -maxx
        miny = -maxy
        if px >= minx and px <= maxx and py >= miny and py <= maxy:
            return d
        return wx.DragNone

    def OnData(self, x, y, d):
        if self.GetData():
            data = self.data.getObject()
            self.glCanvas2D.SetCurrent()
            self.frame.SetMatForUnproj()
            h = self.frame.size[1]
            posX, posY, pz = gluUnProject(x, h - y, 0)
            posX /= 16.0
            posY /= 16.0
            posX += self.frame.exemplar.GetProp(2297284496)[0] / 2.0
            posY += self.frame.exemplar.GetProp(2297284496)[1] / 2.0
            self.frame.PlaceAsset(data, posX, posY)
        return d


def RotCW(x, y):
    return (
     -y, x)


def RotCCW(x, y):
    return (
     y, -x)


class CustomStatusBar(wx.StatusBar):

    def __init__(self, parent):
        wx.StatusBar.__init__(self, parent, -1)
        self.SetFieldsCount(6)
        self.SetStatusWidths([-1, -1, -1, -1, -1, -4])
        self.SetStatusText(LEXSBDisplayMode, 0)
        self.SetStatusText(LEXSBDisplayMode0, 1)
        self.SetStatusText(LEXSBEditMode, 2)
        self.SetStatusText(LEXSBEditMode0, 3)
        self.SetStatusText(LEXSBUnderMouse, 4)
        self.SetStatusText('', 5)


class LotIconPreviewDlg(wx.Dialog):
    """Shows the composited 176x44 four-state icon, with an option to apply it."""

    def __init__(self, parent, icon, can_apply):
        wx.Dialog.__init__(self, parent, -1, LEXIconPreviewTitle)
        self.editor = parent
        # The composited icon is RGBA; flatten it onto white for display.
        icon = icon.convert('RGBA')
        flat = Image.new('RGB', icon.size, (255, 255, 255))
        flat.paste(icon, (0, 0), icon)
        sizer = wx.BoxSizer(wx.VERTICAL)
        info = LEXIconPreviewInfo if can_apply else LEXIconPreviewNotALot
        sizer.Add(wx.StaticText(self, -1, info), 0, wx.ALL, 12)
        big = flat.resize((flat.size[0] * 3, flat.size[1] * 3), Image.NEAREST)
        sizer.Add(wx.StaticBitmap(self, -1, BitmapFromPIL(big)), 0, wx.ALIGN_CENTER | wx.ALL, 12)
        sizer.Add(wx.StaticBitmap(self, -1, BitmapFromPIL(flat)), 0,
                  wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        buttons = wx.StdDialogButtonSizer()
        apply_btn = wx.Button(self, wx.ID_OK, LEXIconPreviewApply)
        apply_btn.Enable(can_apply)
        apply_btn.Bind(wx.EVT_BUTTON, self.OnApply)
        buttons.AddButton(apply_btn)
        buttons.AddButton(wx.Button(self, wx.ID_CANCEL, LEXIconPreviewClose))
        buttons.Realize()
        sizer.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizerAndFit(sizer)

    def OnApply(self, event):
        self.editor.OnUpdateIcon(None)
        self.EndModal(wx.ID_OK)


class LEInspectorPanel(wx.Panel):
    """Inspector pane: a read-only summary plus editable position fields."""

    def __init__(self, parent, editor):
        wx.Panel.__init__(self, parent, -1)
        self.editor = editor
        self.SetBackgroundColour(wx.Colour(250, 251, 252))
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.text = wx.TextCtrl(self, -1, LEXInspectorPrompt,
                                style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_NONE)
        self.text.SetBackgroundColour(wx.Colour(250, 251, 252))
        box = wx.StaticBox(self, -1, LEXInspectorEditPlacement)
        fields = wx.StaticBoxSizer(box, wx.VERTICAL)
        grid = wx.FlexGridSizer(3, 2, 4, 6)
        grid.AddGrowableCol(1, 1)
        self.fldX = wx.TextCtrl(self, -1, '', style=wx.TE_PROCESS_ENTER)
        self.fldY = wx.TextCtrl(self, -1, '', style=wx.TE_PROCESS_ENTER)
        self.fldH = wx.TextCtrl(self, -1, '', style=wx.TE_PROCESS_ENTER)
        for label, ctrl in [(LEXInspectorAxisX, self.fldX), (LEXInspectorAxisY, self.fldY),
                             (LEXInspectorHeight, self.fldH)]:
            grid.Add(wx.StaticText(self, -1, label), 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)
            ctrl.Bind(wx.EVT_TEXT_ENTER, self.OnApply)
        fields.Add(grid, 0, wx.EXPAND | wx.ALL, 4)
        # Rotation: one toggle button per compass direction. Per the
        # LotConfigPropertyLotObject spec, rep 3 orientation is
        # South=0, West=1, North=2, East=3.
        rot_row = wx.BoxSizer(wx.HORIZONTAL)
        rot_row.Add(wx.StaticText(self, -1, LEXInspectorFacing), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.rotButtons = {}
        for label, rot in [(LEXFacingNorth, 2), (LEXFacingEast, 3),
                            (LEXFacingSouth, 0), (LEXFacingWest, 1)]:
            btn = wx.ToggleButton(self, -1, label, size=(34, 26))
            btn.Bind(wx.EVT_TOGGLEBUTTON, lambda evt, r=rot: self.OnRotation(r))
            self.rotButtons[rot] = btn
            rot_row.Add(btn, 0, wx.RIGHT, 2)
        fields.Add(rot_row, 0, wx.EXPAND | wx.ALL, 4)
        self.applyBtn = wx.Button(self, -1, LEXInspectorApply, size=(-1, 26))
        self.applyBtn.Bind(wx.EVT_BUTTON, self.OnApply)
        fields.Add(self.applyBtn, 0, wx.EXPAND | wx.ALL, 4)
        self.transitPanel = TransitInspectorPanel(self, editor)
        sizer.Add(self.text, 1, wx.EXPAND | wx.ALL, 6)
        sizer.Add(fields, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        sizer.Add(self.transitPanel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.SetSizer(sizer)
        self._outer = sizer
        self._fields = fields
        self._transit = self.transitPanel
        self.HideFields()
        self.HideTransit()

    def SetText(self, value):
        self.text.SetValue(value)

    def ShowFields(self, x, y, height, rotation):
        self.HideTransit()
        self.fldX.SetValue('%.2f' % x)
        self.fldY.SetValue('%.2f' % y)
        self.fldH.SetValue('%.2f' % height)
        for rot, btn in self.rotButtons.items():
            btn.SetValue(rot == rotation)
        self._outer.Show(self._fields, True, recursive=True)
        self.Layout()

    def HideFields(self):
        self._outer.Show(self._fields, False, recursive=True)
        self.Layout()

    def ShowTransit(self, values_list, defaults):
        self.HideFields()
        self._transit.ShowFor(values_list, defaults)
        self._outer.Show(self._transit, True, recursive=True)
        self.Layout()

    def HideTransit(self):
        self._outer.Show(self._transit, False, recursive=True)
        self.Layout()

    def OnApply(self, event):
        try:
            x = float(self.fldX.GetValue())
            y = float(self.fldY.GetValue())
            height = float(self.fldH.GetValue())
        except ValueError:
            return
        self.editor.ApplyInspectorEdit(x, y, height)

    def OnRotation(self, rotation):
        for rot, btn in self.rotButtons.items():
            btn.SetValue(rot == rotation)
        self.editor.SetSelectionRotation(rotation)


class LotEditorWin(wx.Frame):
    zoomScale = [
     1.0 / 16.0, 1.0 / 8.0, 1.0 / 4.0, 1.0 / 2.0, 1, 2]
    zoomScale3D = [1 / 32.0, 1.0 / 16.0, 1.0 / 8.0, 1.0 / 4.0, 1.0 / 2.0, 1]
    zoomScaleATC = [1 / 64.0, 1.0 / 32.0, 1.0 / 16.0, 1.0 / 8.0, 1.0 / 4.0, 1 / 2.0]

    def __init__(self, parent, ID, title, size):
        wx.Frame.__init__(self, parent, ID, title, size=size, style=wx.DEFAULT_FRAME_STYLE)
        self.descPage = parent
        self.dragQuad = None
        self.dragSelect = False
        self.rtk4Offsets = {}
        self.newIds = []
        self.selected = []
        self.quadSelected = []
        self.sb = CustomStatusBar(self)
        self.SetStatusBar(self.sb)
        panel = wx.Panel(self, -1)
        self.lotOverTextures = []
        self.lotBaseTextures = []
        self.lotPropDescs = []
        self.lotFamiliesPropID = []
        self.lotFloraDescs = []
        self.modeDisplay = MODE_DISPLAY_FULL
        self.modeEdit = MODE_EDIT_PAN
        self.transitDefaults = dict(DEFAULT_TRANSIT_SETTINGS)
        self.glCanvas2D = MyCanvasBase(panel, size=(800, 400))
        self.glCanvas2D.SetWindowStyle(self.glCanvas2D.GetWindowStyleFlag() | wx.WANTS_CHARS)
        self.glCanvas2D.displayer = self
        dt = LEDropTarget(self.glCanvas2D)
        self.glCanvas2D.SetDropTarget(dt)
        self.s3DTexturesHolder = S3DTexturesHolder(self.glCanvas2D)
        self.s3d_shader_program = None
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        self.zoom = 3
        # Continuous multiplier on top of the discrete zoom level, so Fit view
        # can frame the lot exactly. Reset to 1.0 by any explicit zoom.
        self.viewScale = 1.0
        self.rotation = 0
        self.panel = 3
        self.highlighted = []
        self._build_workbench(panel)
        self.posy = 0
        self.posx = 0
        self.posz = 10
        self.Bind(wx.EVT_CLOSE, self.OnCloseWindow)
        self.Bind(wx.EVT_CHAR_HOOK, self._OnCharHook)
        self.glCanvas2D.Bind(wx.EVT_CHAR, self._OnChar)
        self.LETools = None
        self.glCanvas2D.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        self.glCanvas2D.Bind(wx.EVT_LEFT_DOWN, self.OnMouseDown)
        self.glCanvas2D.Bind(wx.EVT_LEFT_UP, self.OnMouseUp)
        self.snapSize = 0
        self.currentSnapSize = 4
        self.BackPosx = 0
        self.BackPosy = 0
        self._texDragTile = None
        self._undo_stack = []
        self._redo_stack = []
        self._drag_undo_pending = False
        return

    def _make_toolbar_button(self, parent, label, tooltip, handler, hint=None, art_id=None, size=(32, 28)):
        tip = tooltip if hint is None else '%s  [%s]' % (tooltip, hint)
        btn = None
        if art_id is not None:
            bmp = wx.ArtProvider.GetBitmap(art_id, wx.ART_TOOLBAR, wx.Size(16, 16))
            if bmp.IsOk():
                btn = wx.BitmapButton(parent, -1, bmp, size=size)
        if btn is None:
            btn = wx.Button(parent, -1, label, size=size)
        btn.SetToolTip(tip)
        btn.Bind(wx.EVT_BUTTON, handler)
        return btn

    def _build_workbench(self, panel):
        root = wx.BoxSizer(wx.VERTICAL)
        command_bar = wx.Panel(panel, -1)
        settings = load_lot_editor()
        self.backgroundSet = str(settings.get('BackgroundSet', 'Default'))
        self.visibleLayers2D = self._load_visible_layers(settings.get('VisibleLayers2D', {}))
        self.visibleLayers3D = self._load_visible_layers(settings.get('VisibleLayers3D', {}))
        self.nightMode = bool(settings.get('NightMode', False))
        self.s3DTexturesHolder.SetNightMode(self.nightMode)
        self._layer_menu_ids = {}
        self._background_menu_ids = {}
        self._undo_limit = max(1, int(settings.get('UndoLimit', 40)))
        command_bar.SetBackgroundColour(wx.Colour(244, 246, 248))
        command_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.lotContextLabel = wx.StaticText(command_bar, -1, LEXNoLotLoaded)
        self.lotContextLabel.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        command_sizer.Add(self.lotContextLabel, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 10)

        # Edit-mode buttons are toggles in a radio group so the active mode is
        # always visible; _sync_mode_buttons keeps them in step with the
        # keyboard shortcuts (h/p/t/v/f/b).
        self.modeButtons = {}
        for label, mode, handler, hint in [
            (LEXPAN, MODE_EDIT_PAN, self.OnModePan, 'H'),
            (LEXProps, MODE_EDIT_PROP, self.OnModeProp, 'P'),
            (LEXBaseTexture, MODE_EDIT_BASETEX, self.OnModeBaseTex, 'T'),
            (LEXOverlayTexture, MODE_EDIT_OVERTEX, self.OnModeOverTex, 'V'),
            (LEXFlora, MODE_EDIT_FLORA, self.OnModeFlora, 'F'),
            (LEXTransit, MODE_EDIT_TRANSIT, self.OnModeTransit, 'E'),
            (LEXConstraint, MODE_EDIT_CONSTRAINT, self.OnModeConstraint, 'W'),
        ]:
            btn = wx.ToggleButton(command_bar, -1, label, size=(-1, 28))
            btn.SetToolTip('%s  [%s]' % (label, hint))
            btn.Bind(wx.EVT_TOGGLEBUTTON, handler)
            self.modeButtons[mode] = btn
            command_sizer.Add(btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

        for label, fallback, handler, hint, art_id in [
            (LEXToolbarDuplicate, '⧉', self.OnDuplicate, 'D', wx.ART_COPY),
            (LEXToolbarDelete, '×', self.OnDelete, 'Del', wx.ART_DELETE),
        ]:
            btn = self._make_toolbar_button(command_bar, fallback, label, handler, hint, art_id)
            command_sizer.Add(btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

        for label, tooltip, handler, hint, art_id in [
            ('◱', LEXToolbarView, self.OnCycleViewMode, 'A', wx.ART_REPORT_VIEW),
            ('−', LEXToolbarZoomOut, self.OnUnzoom, '-', wx.ART_MINUS),
            ('+', LEXToolbarZoomIn, self.OnZoom, '+', wx.ART_PLUS),
            ('⛶', LEXToolbarFitView, self.OnFitView, 'C', wx.ART_FIND),
        ]:
            btn = self._make_toolbar_button(command_bar, label, tooltip, handler, hint, art_id)
            command_sizer.Add(btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2)

        # Snap: plain click toggles the grid, Ctrl+click sets the grid size.
        snap_btn = self._make_toolbar_button(command_bar, '#', '%s\n%s' % (LEXToolbarSnap, LEXToolbarSnapHint),
                                             self.OnSnapButton, 'S')
        command_sizer.Add(snap_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

        icon_btn = self._make_toolbar_button(command_bar, '▣', LEXIconPreviewTitle, self.OnPreviewIcon,
                                             art_id=wx.ART_NORMAL_FILE)
        command_sizer.Add(icon_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

        layers_btn = self._make_toolbar_button(command_bar, '▤', '%s\n%s' % (LEXToolbarLayers, LEXToolbarLayersHint),
                                               self.OnLayersMenu, art_id=wx.ART_LIST_VIEW)
        command_sizer.Add(layers_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

        # Alignment, rotation and mirror: compact buttons (also keyboard).
        # _update_edit_buttons disables these when they do not apply. Each
        # button sits in a holder panel that carries the tooltip, because a
        # disabled button does not show its own tooltip on Windows.
        self.alignButtons = []
        self.rotateButtons = []
        self.mirrorButton = None
        for label, handler, tip, group, art_id in [
            ('◀', self.OnAlignLeft, '%s\n%s' % (LEXToolbarAlignLeft, LEXToolbarAlignHint), 'align', wx.ART_GO_BACK),
            ('▶', self.OnAlignRight, '%s\n%s' % (LEXToolbarAlignRight, LEXToolbarAlignHint), 'align', wx.ART_GO_FORWARD),
            ('▲', self.OnAlignTop, '%s\n%s' % (LEXToolbarAlignTop, LEXToolbarAlignHint), 'align', wx.ART_GO_UP),
            ('▼', self.OnAlignBottom, '%s\n%s' % (LEXToolbarAlignBottom, LEXToolbarAlignHint), 'align', wx.ART_GO_DOWN),
            ('↺', self.OnRotateLeft, '%s  [Home]' % LEXToolbarRotateLeft, 'rotate', None),
            ('↻', self.OnRotateRight, '%s  [End]' % LEXToolbarRotateRight, 'rotate', None),
            ('⇄', self.OnMirror, '%s  [M]' % LEXToolbarMirror, 'mirror', None),
        ]:
            holder = wx.Panel(command_bar, -1)
            btn = self._make_toolbar_button(holder, label, tip, handler, art_id=art_id)
            holder.SetToolTip(tip)
            holder_sizer = wx.BoxSizer(wx.VERTICAL)
            holder_sizer.Add(btn, 0)
            holder.SetSizerAndFit(holder_sizer)
            command_sizer.Add(holder, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2)
            if group == 'align':
                self.alignButtons.append(btn)
            elif group == 'rotate':
                self.rotateButtons.append(btn)
            else:
                self.mirrorButton = btn

        # Undo/redo for every lot-config edit (also Ctrl+Z / Ctrl+Y).
        self.undoButton = self._make_toolbar_button(command_bar, '↶', LEXToolbarUndo, self.OnUndo,
                                                    'Ctrl+Z', wx.ART_UNDO)
        command_sizer.Add(self.undoButton, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.redoButton = self._make_toolbar_button(command_bar, '↷', LEXToolbarRedo, self.OnRedo,
                                                    'Ctrl+Y', wx.ART_REDO)
        command_sizer.Add(self.redoButton, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.undoButton.Disable()
        self.redoButton.Disable()

        command_bar.SetSizer(command_sizer)
        root.Add(command_bar, 0, wx.EXPAND)

        self.mainSplitter = wx.SplitterWindow(panel, -1, style=wx.CLIP_CHILDREN | wx.SP_LIVE_UPDATE | wx.SP_3D)
        self.rightSplitter = wx.SplitterWindow(self.mainSplitter, -1, style=wx.CLIP_CHILDREN | wx.SP_LIVE_UPDATE | wx.SP_3D)
        self.assetBrowser = LEAssetBrowserPanel(self.mainSplitter, self)
        viewport_panel = wx.Panel(self.rightSplitter, -1)
        self.glCanvas2D.Reparent(viewport_panel)
        viewport_sizer = wx.BoxSizer(wx.VERTICAL)
        viewport_sizer.Add(self.glCanvas2D, 1, wx.EXPAND | wx.ALL, 6)
        viewport_panel.SetSizer(viewport_sizer)
        self.inspector = LEInspectorPanel(self.rightSplitter, self)
        inspector_width = int(settings.get('InspectorWidth', 280))
        self.rightSplitter.SplitVertically(viewport_panel, self.inspector, -inspector_width)
        self.rightSplitter.SetMinimumPaneSize(220)
        browser_width = int(settings.get('BrowserWidth', 330))
        self.mainSplitter.SplitVertically(self.assetBrowser, self.rightSplitter, browser_width)
        self.mainSplitter.SetMinimumPaneSize(260)
        root.Add(self.mainSplitter, 1, wx.EXPAND)
        panel.SetSizer(root)
        self._sync_mode_buttons()
        # The constructor size is only the "restore" size; the lot editor is
        # cramped at 800x600, so open it maximized.
        self.Maximize(True)

    def _editor_state(self):
        state = {}
        if hasattr(self, 'assetBrowser'):
            state.update(self.assetBrowser.GetState())
        if hasattr(self, 'mainSplitter'):
            state['BrowserWidth'] = int(self.mainSplitter.GetSashPosition())
        if hasattr(self, 'rightSplitter'):
            width = self.rightSplitter.GetClientSize()[0]
            sash = self.rightSplitter.GetSashPosition()
            state['InspectorWidth'] = max(220, int(width - sash))
        state['BackgroundSet'] = str(getattr(self, 'backgroundSet', 'Default'))
        state['VisibleLayers2D'] = dict(getattr(self, 'visibleLayers2D', self._default_visible_layers()))
        state['VisibleLayers3D'] = dict(getattr(self, 'visibleLayers3D', self._default_visible_layers()))
        state['NightMode'] = bool(getattr(self, 'nightMode', False))
        return state

    def _default_visible_layers(self):
        return {key: True for key, _label in LAYER_SPECS}

    def _load_visible_layers(self, settings):
        layers = self._default_visible_layers()
        if isinstance(settings, dict):
            for key in layers:
                if key in settings:
                    layers[key] = bool(settings[key])
        return layers

    def _is_layer_visible(self, view, key):
        if view == '3d':
            return bool(getattr(self, 'visibleLayers3D', self._default_visible_layers()).get(key, True))
        return bool(getattr(self, 'visibleLayers2D', self._default_visible_layers()).get(key, True))

    def SaveEditorState(self):
        try:
            save_lot_editor(self._editor_state())
        except Exception:
            logger.exception('Failed to save LotEditor state')

    def _update_lot_context(self):
        if not hasattr(self, 'exemplar'):
            self.lotContextLabel.SetLabel(LEXNoLotLoaded)
            return
        name = None
        try:
            name_prop = self.exemplar.GetProp(32)
            if name_prop:
                name = name_prop[0]
        except Exception:
            pass
        if not name:
            name = hex2str(self.exemplar.entry.tgi[2])
        try:
            lot_size = self.exemplar.GetProp(2297284496)
            size_label = '%dx%d' % (lot_size[0], lot_size[1])
        except Exception:
            size_label = '?x?'
        self.lotContextLabel.SetLabel('%s   %s   %s' % (name, hex2str(self.exemplar.entry.tgi[2]), size_label))

    def RefreshAssetBrowser(self):
        if hasattr(self, 'assetBrowser'):
            self.assetBrowser.RefreshAssets()

    def UpdateAssetInspector(self, item):
        hex_id = getattr(item, 'hex_id', '') or ''
        lines = [
            LEXInspectorAsset,
            '',
            '%s: %s' % (LEXInspectorType, item.type_label),
        ]
        if item.label and item.label != hex_id:
            lines.append('%s: %s' % (LEXInspectorName, item.label))
        if hex_id:
            lines.append('%s: 0x%s' % (LEXInspectorID, hex_id))
        size = getattr(item, 'occupant_size', None)
        if size:
            lines.append('%s: %.1f x %.1f x %.1f m' % (LEXInspectorSize, size[0], size[1], size[2]))
        try:
            source = item.source
            file_name = getattr(source, 'fileName', None)
            if file_name is None and hasattr(source, 'exemplar'):
                file_name = source.exemplar.entry.fileName
            if file_name:
                lines.append('%s: %s' % (LEXInspectorFile, os.path.split(file_name)[1]))
        except Exception:
            pass
        self.inspector.SetText('\n'.join(lines))
        self.inspector.HideFields()

    def _lot_config_for_selection(self, selected_id):
        if not hasattr(self, 'exemplar'):
            return None
        for lcp in range(2297284864, 2297286144):
            values = self.exemplar.GetProp(lcp)
            if values is None:
                break
            if values[11] == selected_id:
                return values
        return None

    def _lot_config_type_label(self, values):
        if values[0] == 0:
            return LEXBuilding
        if values[0] == 1:
            return LEXAssetTypeProp
        if values[0] == 2:
            tex_id = values[12]
            for tex in getattr(self, 'texOverlays', []):
                if tex[4] == values[11] and tex[3] == tex_id:
                    return LEXAssetTypeOverlayTexture
            return LEXAssetTypeBaseTexture
        if values[0] == 4:
            return LEXAssetTypeFlora
        if values[0] == 5:
            return LEXConstraintWater
        if values[0] == 6:
            return LEXConstraintLand
        if values[0] == 7:
            return LEXAssetTypeTransit
        return LEXInspectorSelection

    def _lot_summary_text(self):
        """Inspector text shown when nothing is selected: a lot overview."""
        if not hasattr(self, 'exemplar'):
            return LEXInspectorPrompt
        lines = [LEXInspectorLotSummary, '']
        try:
            size = self.exemplar.GetProp(2297284496)
            lines.append('%s: %dx%d' % (LEXInspectorLotSize, size[0], size[1]))
        except Exception:
            pass
        lines.extend([
            '%s: %d' % (LEXAssetTypeProp, len(getattr(self, 'props', []))),
            '%s: %d' % (LEXAssetTypeFlora, len(getattr(self, 'floras', []))),
            '%s: %d' % (LEXAssetTypeBaseTexture, len(getattr(self, 'texBases', []))),
            '%s: %d' % (LEXAssetTypeOverlayTexture, len(getattr(self, 'texOverlays', []))),
            '%s: %d' % (LEXAssetTypeTransit, len(getattr(self, 'te', []))),
            '',
            LEXInspectorNoSelection,
        ])
        return '\n'.join(lines)

    def UpdateSelectionInspector(self):
        self._update_edit_buttons()
        if not hasattr(self, 'inspector'):
            return
        if not self.selected:
            self.inspector.SetText(self._lot_summary_text())
            if self.modeEdit == MODE_EDIT_TRANSIT:
                self.inspector.ShowTransit([], self.transitDefaults)
            else:
                self.inspector.HideFields()
                self.inspector.HideTransit()
            return
        selected_values = []
        for selected_id in self.selected:
            values = self._lot_config_for_selection(selected_id)
            if values is not None:
                selected_values.append(values)
        lines = [
            LEXInspectorSelection,
            '',
            '%s: %d' % (LEXInspectorSelectionCount, len(self.selected)),
        ]
        if selected_values and all(is_transit_object(values) for values in selected_values):
            lines.extend([
                '%s: %s' % (LEXInspectorType, LEXAssetTypeTransit),
                '%s: %s' % (LEXTransitNetworkType,
                            network_label(ensure_transit_values(selected_values[0][:])[12])),
                '%s: %s' % (LEXTransitDirectionMask,
                            mask_label(ensure_transit_values(selected_values[0][:])[14])),
                '%s: %s' % (LEXTransitRep14,
                            format_hex32(ensure_transit_values(selected_values[0][:])[13])),
                '%s: %s' % (LEXTransitRep16,
                            format_hex32(ensure_transit_values(selected_values[0][:])[15])),
            ])
            if len(selected_values) == 1:
                values = ensure_transit_values(selected_values[0][:])
                cx = ToCoord(values[3])
                cy = ToCoord(values[5])
                lines.extend([
                    '%s: %s' % (LEXInspectorID, hex2str(values[11])),
                    '%s: %.2f, %.2f' % (LEXInspectorPosition, cx, cy),
                    '%s: %s' % (LEXInspectorRotation, values[2] & 15),
                ])
            self.inspector.SetText('\n'.join(lines))
            self.inspector.ShowTransit(selected_values, self.transitDefaults)
            return
        editable = False
        if len(self.selected) == 1:
            values = self._lot_config_for_selection(self.selected[0])
            if values is not None:
                cx = ToCoord(values[3])
                cy = ToCoord(values[5])
                bounds = (
                    ToCoord(values[6]),
                    ToCoord(values[7]),
                    ToCoord(values[8]),
                    ToCoord(values[9]),
                )
                lines.extend([
                    '%s: %s' % (LEXInspectorType, self._lot_config_type_label(values)),
                    '%s: %s' % (LEXInspectorID, hex2str(values[11])),
                ])
                # Constraint tiles (type 5/6) carry only reps 1-12, so there
                # is no rep-13 name/reference to show.
                if len(values) > 12:
                    lines.append('%s: %s' % (LEXInspectorName, hex2str(values[12])))
                lines.extend([
                    '%s: %.2f, %.2f' % (LEXInspectorPosition, cx, cy),
                    '%s: %.2f, %.2f - %.2f, %.2f' % ((LEXInspectorBounds,) + bounds),
                    '%s: %.2f' % (LEXInspectorHeight, ToCoord(values[4])),
                    '%s: %s' % (LEXInspectorRotation, values[2]),
                ])
                if values[0] in (0, 1, 4):
                    editable = True
                    self.inspector.ShowFields(cx, cy, ToCoord(values[4]), values[2] & 15)
        self.inspector.SetText('\n'.join(lines))
        if not editable:
            self.inspector.HideFields()
        self.inspector.HideTransit()

    def ApplyInspectorEdit(self, px, py, height):
        """Write inspector position/height fields back to the single selection."""
        if len(self.selected) != 1 or not self.quadSelected:
            return
        sel_id = self.selected[0]
        target = None
        for lcp in range(2297284864, 2297286144):
            values = self.exemplar.GetProp(lcp)
            if values is None:
                break
            if values[11] == sel_id:
                target = values
                break
        if target is None or target[0] not in (0, 1, 4):
            return
        self._push_undo()
        dx = px - ToCoord(target[3])
        dy = py - ToCoord(target[5])
        target[3] = ToUnsigned(int(px * 65536))
        target[5] = ToUnsigned(int(py * 65536))
        for idx in (6, 8):
            target[idx] = ToUnsigned(int((ToCoord(target[idx]) + dx) * 65536))
        for idx in (7, 9):
            target[idx] = ToUnsigned(int((ToCoord(target[idx]) + dy) * 65536))
        target[4] = ToUnsigned(int(height * 65536))
        if target[0] == 0:
            self.building[:-1] = target[:]
        else:
            what = self.floras if target[0] == 4 else self.props
            for prop in what:
                if prop[11] == sel_id:
                    prop[:13] = target
                    break
        q = self.quadSelected[0]
        q[0] = ToCoord(target[6])
        q[1] = ToCoord(target[7])
        q[2] = ToCoord(target[8])
        q[3] = ToCoord(target[9])
        self.UpdatePIM()
        self.UpdateSelectionInspector()
        self.on_draw()

    def SetSelectionRotation(self, rotation):
        """Rotate the single selection to an absolute facing (0=S,1=W,2=N,3=E)."""
        if len(self.selected) != 1:
            return
        values = self._lot_config_for_selection(self.selected[0])
        if values is None or values[0] not in (0, 1, 4):
            return
        # A CW Rotate step maps the rotation flag c -> (c - 1) mod 4, so to
        # reach an absolute facing the step count is (current - target).
        steps = ((values[2] & 15) - rotation) % 4
        if steps == 0:
            return
        self._push_undo()
        for _ in range(steps):
            self.Rotate([3, 0, 1, 2], RotCW)
        self.UpdatePIM()
        self.UpdateSelectionInspector()
        self.on_draw()

    def ApplyTransitInspectorEdit(self, settings):
        """Apply TE defaults or selected type-7 object fields from the inspector."""
        self.transitDefaults.update(settings)
        targets = []
        for selected_id in self.selected:
            values = self._lot_config_for_selection(selected_id)
            if values is not None and is_transit_object(values):
                targets.append(values)
        if not targets:
            return
        self._push_undo()
        for values in targets:
            ensure_transit_values(values)
            values[12] = int(settings['network'])
            values[13] = int(settings['rep14'])
            values[14] = int(settings['direction_mask'])
            values[15] = int(settings['rep16'])
            update_cached_transit(self.te, values)
        self.UpdatePIM()
        self.UpdateSelectionInspector()
        self.on_draw()

    def PlaceTransitNode(self, tile_x, tile_y):
        """Create a type-7 TE lot object on a whole tile."""
        if not hasattr(self, 'exemplar'):
            return
        lot_size = self.exemplar.GetProp(2297284496)
        if tile_x < 0 or tile_y < 0 or tile_x >= lot_size[0] or tile_y >= lot_size[1]:
            return
        currentID = 0
        lastIDProp = 2297284863
        for lcp in range(2297284864, 2297286144):
            values = self.exemplar.GetProp(lcp)
            if values is None:
                break
            if values[11] > currentID:
                currentID = values[11]
            lastIDProp = lcp
        currentID += 1
        lastIDProp += 1
        if lastIDProp >= 2297286144:
            return
        self._push_undo()
        values = make_transit_values(currentID, tile_x, tile_y, self.transitDefaults)
        self.exemplar.AddTextProp(CreateAProp(self.virtualDAT.properties[lastIDProp], values[:]))
        self.PreCacheObject(values[:])
        self.selected = [currentID]
        self.quadSelected = [tile_quad(tile_x, tile_y)]
        self.UpdatePIM()
        self.UpdateSelectionInspector()
        self.on_draw()

    def PlaceConstraint(self, tile_x, tile_y, obj_type):
        """Create a type-5 (water) or type-6 (land) constraint tile.

        Constraint tiles cover a whole 16 m tile and carry only reps 1-12
        (no custom reps), so the value list is a plain whole-tile object.
        """
        if not hasattr(self, 'exemplar'):
            return
        lot_size = self.exemplar.GetProp(2297284496)
        if tile_x < 0 or tile_y < 0 or tile_x >= lot_size[0] or tile_y >= lot_size[1]:
            return
        currentID = 0
        lastIDProp = 2297284863
        for lcp in range(2297284864, 2297286144):
            values = self.exemplar.GetProp(lcp)
            if values is None:
                break
            if values[11] > currentID:
                currentID = values[11]
            lastIDProp = lcp
        currentID += 1
        lastIDProp += 1
        if lastIDProp >= 2297286144:
            return
        self._push_undo()
        minx = tile_x * 16
        miny = tile_y * 16
        cx = minx + 8
        cy = miny + 8
        # Rep 3 (orientation) = 2: the unrotated flag used by every other
        # whole-tile object (PlaceAsset textures, make_transit_values), so the
        # marker texture is not drawn rotated relative to the rest of the lot.
        values = [obj_type, 0, 2,
                  ToUnsigned(cx * 65536), 0, ToUnsigned(cy * 65536),
                  ToUnsigned(minx * 65536), ToUnsigned(miny * 65536),
                  ToUnsigned((minx + 16) * 65536), ToUnsigned((miny + 16) * 65536),
                  0, currentID]
        self.exemplar.AddTextProp(CreateAProp(self.virtualDAT.properties[lastIDProp], values[:]))
        self.PreCacheObject(values[:])
        self.selected = [currentID]
        self.quadSelected = [tile_quad(tile_x, tile_y)]
        self.UpdatePIM()
        self.UpdateSelectionInspector()
        self.on_draw()

    def PlaceAsset(self, data, posX, posY):
        """Add an asset proxy to the lot at tile-space (posX, posY)."""
        currentID = 0
        lastIDProp = 2297284864
        for lcp in range(2297284864, 2297286144):
            values = self.exemplar.GetProp(lcp)
            if values is None:
                break
            if values[11] > currentID:
                currentID = values[11]
            lastIDProp = lcp
        currentID += 1
        lastIDProp += 1
        bOk = False
        width = 0
        depth = 0
        v12 = 2
        vType = 2
        if data.__class__ == BaseProxy:
            v12 = data.what
            vType = 2
            width = 1
            depth = 1
            posX = int(posX) + 0.5
            posY = int(posY) + 0.5
            bOk = True
        elif data.__class__ == OverlayProxy:
            v12 = data.what
            vType = 2
            width = 1
            depth = 1
            posX = int(posX) + 0.5
            posY = int(posY) + 0.5
            bOk = True
        elif data.__class__ == PropProxy:
            entry = VirtualDat.this.getEntry(data.what[0], data.what[1], data.what[2])
            exemplar = entry.exemplar
            try:
                width = exemplar.GetProp(662775824)[0] / 16.0
                depth = exemplar.GetProp(662775824)[2] / 16.0
            except Exception:
                width = 0.5
                depth = 0.5
            v12 = data.what[2]
            if exemplar.GetProp(16)[0] == 15:
                vType = 4
            else:
                vType = 1
            bOk = True
        elif data.__class__ == FamilyProxy:
            catID = data.what
            exemplar = None
            for desc in VirtualDat.this.categories[catID].descriptors:
                if desc.exemplar.entry.tgi[0] != 1697917002:
                    continue
                if desc.exemplar.GetProp(16)[0] != 30 and desc.exemplar.GetProp(16)[0] != 15:
                    continue
                exemplar = desc.exemplar
                width = max(width, exemplar.GetProp(662775824)[0] / 16.0)
                depth = max(depth, exemplar.GetProp(662775824)[2] / 16.0)
            if exemplar is not None:
                v12 = data.what
                vType = 1
                bOk = True
        if not bOk:
            return
        self._push_undo()
        xmin = posX - width / 2.0
        ymin = posY - depth / 2.0
        xmax = posX + width / 2.0
        ymax = posY + depth / 2.0
        posX = ToUnsigned(posX * 1048576)
        posY = ToUnsigned(posY * 1048576)
        xmin = ToUnsigned(xmin * 1048576)
        ymin = ToUnsigned(ymin * 1048576)
        xmax = ToUnsigned(xmax * 1048576)
        ymax = ToUnsigned(ymax * 1048576)
        v = [vType, 0, 2, posX, 0, posY, xmin, ymin, xmax, ymax, 0, currentID, v12]
        self.exemplar.AddTextProp(CreateAProp(self.virtualDAT.properties[lastIDProp], v[:]))
        self.PreCacheObject(v)
        self.UpdatePIM()
        self.RebuildVars()
        self.on_draw()

    def PlaceAssetCentered(self, proxy):
        """Place an asset proxy at the centre of the lot (double-click)."""
        if not hasattr(self, 'exemplar') or proxy is None:
            return
        self.PlaceAsset(proxy, self.lotSizeX / 2.0, self.lotSizeY / 2.0)

    def _sync_mode_buttons(self):
        if hasattr(self, 'modeButtons'):
            for mode, btn in self.modeButtons.items():
                btn.SetValue(mode == self.modeEdit)
        self._update_edit_buttons()

    def _update_edit_buttons(self):
        """Disable align/rotate/mirror buttons when they cannot act.

        The tooltip lives on each button's holder panel, so it still shows
        while the button itself is disabled.
        """
        if not hasattr(self, 'alignButtons'):
            return
        has_sel = bool(self.selected)
        align_ok = has_sel and self.modeEdit in (MODE_EDIT_PROP, MODE_EDIT_FLORA)
        for btn in self.alignButtons:
            btn.Enable(align_ok)
        for btn in self.rotateButtons:
            btn.Enable(has_sel)
        if self.mirrorButton is not None:
            self.mirrorButton.Enable(has_sel and self.modeEdit in (MODE_EDIT_BASETEX, MODE_EDIT_OVERTEX))

    def OnModePan(self, event):
        self.modeEdit = MODE_EDIT_PAN
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        self.sb.SetStatusText(LEXPAN, 3)
        self._sync_mode_buttons()

    def OnModeProp(self, event):
        if self.modeEdit != MODE_EDIT_PROP:
            self.selected = []
            self.newIds = []
            self.quadSelected = []
            self.UpdateSelectionInspector()
        self.modeEdit = MODE_EDIT_PROP
        self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.sb.SetStatusText(LEXProps, 3)
        self._sync_mode_buttons()

    def OnModeBuilding(self, event):
        if self.modeEdit != MODE_EDIT_BUILDING:
            self.selected = []
            self.newIds = []
            self.quadSelected = []
            self.UpdateSelectionInspector()
        self.modeEdit = MODE_EDIT_BUILDING
        self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.sb.SetStatusText(LEXBuilding, 3)
        self._sync_mode_buttons()

    def OnModeBaseTex(self, event):
        if self.modeEdit != MODE_EDIT_BASETEX:
            self.selected = []
            self.quadSelected = []
            self.UpdateSelectionInspector()
        self.modeEdit = MODE_EDIT_BASETEX
        self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.sb.SetStatusText(LEXBaseTexture, 3)
        self._sync_mode_buttons()

    def OnModeOverTex(self, event):
        if self.modeEdit != MODE_EDIT_OVERTEX:
            self.selected = []
            self.newIds = []
            self.quadSelected = []
            self.UpdateSelectionInspector()
        self.modeEdit = MODE_EDIT_OVERTEX
        self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.sb.SetStatusText(LEXOverlayTexture, 3)
        self._sync_mode_buttons()

    def OnModeFlora(self, event):
        if self.modeEdit != MODE_EDIT_FLORA:
            self.selected = []
            self.newIds = []
            self.quadSelected = []
            self.UpdateSelectionInspector()
        self.modeEdit = MODE_EDIT_FLORA
        self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.sb.SetStatusText(LEXFlora, 3)
        self._sync_mode_buttons()

    def OnModeTransit(self, event):
        if self.modeEdit != MODE_EDIT_TRANSIT:
            self.selected = []
            self.newIds = []
            self.quadSelected = []
        self.modeEdit = MODE_EDIT_TRANSIT
        self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.sb.SetStatusText(LEXTransit, 3)
        self.UpdateSelectionInspector()
        self._sync_mode_buttons()

    def OnModeConstraint(self, event):
        if self.modeEdit != MODE_EDIT_CONSTRAINT:
            self.selected = []
            self.newIds = []
            self.quadSelected = []
        self.modeEdit = MODE_EDIT_CONSTRAINT
        self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.sb.SetStatusText(LEXConstraintHint, 3)
        self.UpdateSelectionInspector()
        self._sync_mode_buttons()

    def OnCycleFamily(self, event):
        self.currentBuilding += 1
        if self.currentBuilding >= len(self.buildingViewer):
            self.currentBuilding = 0
        self.glCanvas2D.Refresh(False)

    def OnCycleDisplayMode(self, event):
        sequence = [
         MODE_DISPLAY_FULL, MODE_DISPLAY_LE, MODE_DISPLAY_TE, MODE_DISPLAY_CONSTRAINT]
        modeNames = modeNamesMsg
        idx = sequence.index(self.modeDisplay)
        idx += 1
        idx %= 4
        self.modeDisplay = sequence[idx]
        self.sb.SetStatusText(modeNames[idx], 1)
        self.glCanvas2D.Refresh(False)

    def OnCycleViewMode(self, event):
        self.panel += 1
        if self.panel == 4:
            self.panel = 1
        self.glCanvas2D.Refresh(False)

    def SetZoom(self, zoom):
        zoomStrs = [
         viewerZoom1, viewerZoom2, viewerZoom3, viewerZoom4, viewerZoom5, viewerZoom5]
        self.zoom = zoom
        self.viewScale = 1.0
        self.glCanvas2D.Refresh(False)

    def OnZoom(self, event):
        if self.zoom < 5:
            self.SetZoom(self.zoom + 1)

    def OnUnzoom(self, event):
        if self.zoom > 0:
            self.SetZoom(self.zoom - 1)

    def _exact_fit_scale(self):
        """The 2D world scale at which the whole lot exactly fills the viewport."""
        size = self.glCanvas2D.GetClientSize()
        w = size[0] // 2 if self.panel == 3 else size[0]
        h = size[1]
        x_half = getattr(self, 'lotSizeXOver', 16) / 2.0 + 8
        y_half = getattr(self, 'lotSizeYOver', 16) / 2.0 + 8
        if w <= 0 or h <= 0:
            return LotEditorWin.zoomScale[self.zoom]
        return min((w / 20.0) / x_half, (h / 20.0) / y_half)

    def OnFitView(self, event=None):
        """Recentre and scale so the whole lot exactly fills the 2D viewport.

        The discrete zoom still selects the texture LOD; viewScale is the
        fractional remainder that makes the fit exact.
        """
        self.posx = 0
        self.posy = 0
        self.posz = 10
        self.pos3Dx = 0
        self.pos3Dy = 0
        self.pos3Dz = -10
        self.BackPosx = 0
        self.BackPosy = 0
        exact = self._exact_fit_scale()
        zoom = 0
        for idx, scale in enumerate(LotEditorWin.zoomScale):
            if scale <= exact:
                zoom = idx
        self.zoom = zoom
        self.viewScale = exact / LotEditorWin.zoomScale[zoom]
        self.glCanvas2D.Refresh(False)

    def OnSetZoom1(self, event):
        self.SetZoom(0)

    def OnSetZoom2(self, event):
        self.SetZoom(1)

    def OnSetZoom3(self, event):
        self.SetZoom(2)

    def OnSetZoom4(self, event):
        self.SetZoom(3)

    def OnSetZoom5(self, event):
        self.SetZoom(4)

    def OnSetZoom6(self, event):
        self.SetZoom(5)

    def Rotate(self, rotOrder, rotFunc):
        for id, q in zip(self.selected, self.quadSelected):
            for lcp in range(2297284864, 2297286144):
                values = self.exemplar.GetProp(lcp)
                if values is None:
                    break
                if values[11] == id:
                    flag = values[2]
                    rot = flag & 15
                    flag = (flag & 4294967280) + rotOrder[rot]
                    values[2] = flag
                    if values[0] == 0 or values[0] == 1 or values[0] == 4:
                        dx = values[3]
                        dy = values[5]
                        minx = ToCoord(values[6] - dx)
                        miny = ToCoord(values[7] - dy)
                        maxx = ToCoord(values[8] - dx)
                        maxy = ToCoord(values[9] - dy)
                        p11 = rotFunc(minx, miny)
                        p12 = rotFunc(minx, maxy)
                        p21 = rotFunc(maxx, miny)
                        p22 = rotFunc(maxx, maxy)
                        minx = min(p11[0], p12[0], p21[0], p22[0])
                        maxx = max(p11[0], p12[0], p21[0], p22[0])
                        miny = min(p11[1], p12[1], p21[1], p22[1])
                        maxy = max(p11[1], p12[1], p21[1], p22[1])
                        values[6] = ToUnsigned(int((minx + ToCoord(dx)) * 65536))
                        values[7] = ToUnsigned(int((miny + ToCoord(dy)) * 65536))
                        values[8] = ToUnsigned(int((maxx + ToCoord(dx)) * 65536))
                        values[9] = ToUnsigned(int((maxy + ToCoord(dy)) * 65536))
                        q[0] = ToCoord(values[6])
                        q[1] = ToCoord(values[7])
                        q[2] = ToCoord(values[8])
                        q[3] = ToCoord(values[9])
                    if values[0] == 0:
                        self.building[:-1] = values[:]
                    elif values[0] == 1 or values[0] == 4:
                        what = self.props
                        if values[0] == 4:
                            what = self.floras
                        for prop in what:
                            if prop[11] == id:
                                prop[:13] = values
                                break

                    elif values[0] == 2:

                        def UpdateTexData(what):
                            for texData in what:
                                if texData[4] == id:
                                    texData[2] = flag
                                    what.remove(texData)
                                    what.append(texData)
                                    return True

                            return False

                        z = UpdateTexData(self.texBases)
                        if not z:
                            UpdateTexData(self.texOverlays)
                    elif values[0] == 7:
                        update_cached_transit(self.te, ensure_transit_values(values))
                    elif values[0] in (5, 6):
                        pool = self.waters if values[0] == 5 else self.lands
                        for texData in pool:
                            if texData[4] == id:
                                texData[2] = flag
                                break
                    break

        return

    def GroupRotate(self, rotOrder, rotFunc):
        xCenter = 0
        yCenter = 0
        xMin = None
        yMin = None
        xMax = None
        yMax = None
        for id, q in zip(self.selected, self.quadSelected):
            for lcp in range(2297284864, 2297286144):
                values = self.exemplar.GetProp(lcp)
                if values is None:
                    break
                if values[11] == id:
                    if xMin is None:
                        xMin = ToCoord(values[6])
                    else:
                        xMin = min(xMin, ToCoord(values[6]))
                    if xMax is None:
                        xMax = ToCoord(values[8])
                    else:
                        xMax = max(xMax, ToCoord(values[8]))
                    if yMin is None:
                        yMin = ToCoord(values[7])
                    else:
                        yMin = min(yMin, ToCoord(values[7]))
                    if yMax is None:
                        yMax = ToCoord(values[9])
                    else:
                        yMax = max(yMax, ToCoord(values[9]))
                    break

        xCenter = (xMin + xMax) / 2
        yCenter = (yMin + yMax) / 2
        for id, q in zip(self.selected, self.quadSelected):
            for lcp in range(2297284864, 2297286144):
                values = self.exemplar.GetProp(lcp)
                if values is None:
                    break
                if values[11] == id:
                    flag = values[2]
                    rot = flag & 15
                    flag = (flag & 4294967280) + rotOrder[rot]
                    values[2] = flag
                    if values[0] == 0 or values[0] == 1 or values[0] == 4:
                        dx = xCenter
                        dy = yCenter
                        minx = ToCoord(values[6]) - dx
                        miny = ToCoord(values[7]) - dy
                        maxx = ToCoord(values[8]) - dx
                        maxy = ToCoord(values[9]) - dy
                        p11 = rotFunc(minx, miny)
                        p12 = rotFunc(minx, maxy)
                        p21 = rotFunc(maxx, miny)
                        p22 = rotFunc(maxx, maxy)
                        minx = min(p11[0], p12[0], p21[0], p22[0])
                        maxx = max(p11[0], p12[0], p21[0], p22[0])
                        miny = min(p11[1], p12[1], p21[1], p22[1])
                        maxy = max(p11[1], p12[1], p21[1], p22[1])
                        x, y = rotFunc(ToCoord(values[3]) - dx, ToCoord(values[5]) - dy)
                        values[3] = ToUnsigned(int((x + dx) * 65536))
                        values[5] = ToUnsigned(int((y + dy) * 65536))
                        values[6] = ToUnsigned(int((minx + dx) * 65536))
                        values[7] = ToUnsigned(int((miny + dy) * 65536))
                        values[8] = ToUnsigned(int((maxx + dx) * 65536))
                        values[9] = ToUnsigned(int((maxy + dy) * 65536))
                        q[0] = ToCoord(values[6])
                        q[1] = ToCoord(values[7])
                        q[2] = ToCoord(values[8])
                        q[3] = ToCoord(values[9])
                    if values[0] == 0:
                        self.building[:-1] = values[:]
                    elif values[0] == 1 or values[0] == 4:
                        what = self.props
                        if values[0] == 4:
                            what = self.floras
                        for prop in what:
                            if prop[11] == id:
                                prop[:13] = values
                                break

                    elif values[0] == 2:

                        def UpdateTexData(what):
                            for texData in what:
                                if texData[4] == id:
                                    texData[2] = flag
                                    what.remove(texData)
                                    what.append(texData)
                                    return True

                            return False

                        z = UpdateTexData(self.texBases)
                        if not z:
                            UpdateTexData(self.texOverlays)
                    elif values[0] == 7:
                        update_cached_transit(self.te, ensure_transit_values(values))
                    elif values[0] in (5, 6):
                        pool = self.waters if values[0] == 5 else self.lands
                        for texData in pool:
                            if texData[4] == id:
                                texData[2] = flag
                                break
                    break

        return

    def OnRotateViewRight(self, event):
        rot = self.rotation
        rot += 1
        rot %= 4
        rotStrs = [viewerRotSouth, viewerRotEast, viewerRotNorth, viewerRotWest]
        self.rotation = rot
        self.glCanvas2D.Refresh(False)

    def OnRotateRight(self, event):
        if self.selected:
            self._push_undo()
        if hasattr(event, 'ShiftDown') and event.ShiftDown():
            if self.modeEdit in [MODE_EDIT_PROP, MODE_EDIT_FLORA]:
                self.GroupRotate([3, 0, 1, 2], RotCCW)
                self.UpdatePIM()
        else:
            self.Rotate([3, 0, 1, 2], RotCW)
            self.glCanvas2D.Refresh(False)
            self.UpdatePIM()
        self.UpdateSelectionInspector()

    def OnRotateViewLeft(self, event):
        rot = self.rotation
        if rot > 0:
            rot -= 1
        else:
            rot = 3
        rotStrs = [
         viewerRotSouth, viewerRotEast, viewerRotNorth, viewerRotWest]
        self.rotation = rot
        self.glCanvas2D.Refresh(False)

    def OnRotateLeft(self, event):
        if self.selected:
            self._push_undo()
        if hasattr(event, 'ShiftDown') and event.ShiftDown():
            if self.modeEdit in [MODE_EDIT_PROP, MODE_EDIT_FLORA]:
                self.GroupRotate([1, 2, 3, 0], RotCW)
                self.UpdatePIM()
        else:
            self.Rotate([1, 2, 3, 0], RotCCW)
            self.glCanvas2D.Refresh(False)
            self.UpdatePIM()
        self.UpdateSelectionInspector()

    def OnMirror(self, event):
        if self.modeEdit == MODE_EDIT_BASETEX or self.modeEdit == MODE_EDIT_OVERTEX:
            if self.selected:
                self._push_undo()
            for id, q in zip(self.selected, self.quadSelected):
                for lcp in range(2297284864, 2297286144):
                    values = self.exemplar.GetProp(lcp)
                    if values is None:
                        break
                    if values[11] == id:
                        flag = values[2]
                        mirror = flag & 2147483648
                        if mirror == 2147483648:
                            flag = flag & 268435455
                        else:
                            flag = flag + 2147483648
                        values[2] = flag
                        if values[0] == 2:

                            def UpdateTexData(what):
                                for texData in what:
                                    if texData[4] == id:
                                        texData[2] = flag
                                        what.remove(texData)
                                        what.append(texData)
                                        return True

                                return False

                            z = UpdateTexData(self.texBases)
                            if not z:
                                UpdateTexData(self.texOverlays)
                        break

        self.UpdatePIM()
        return

    def _capture_lot_snapshot(self):
        """Copy every lot-config property so an edit can be reverted."""
        snapshot = []
        for lcp in range(2297284864, 2297286144):
            values = self.exemplar.GetProp(lcp)
            if values is None:
                break
            snapshot.append(values[:])
        return snapshot

    def _push_undo(self):
        """Record the pre-edit state. Call this before a mutating operation."""
        if not hasattr(self, 'exemplar'):
            return
        self._undo_stack.append(self._capture_lot_snapshot())
        if len(self._undo_stack) > self._undo_limit:
            self._undo_stack.pop(0)
        self._redo_stack = []
        self._update_undo_buttons()

    def _update_undo_buttons(self):
        if hasattr(self, 'undoButton'):
            self.undoButton.Enable(bool(self._undo_stack))
            self.redoButton.Enable(bool(self._redo_stack))

    def _rebuild_scene(self):
        """Rebuild the cached render lists from the current lot-config props.

        Reuses the texture cache (`self.textures`), so it is cheap enough for
        an undo/redo step and does not leak GL textures.
        """
        self.glCanvas2D.SetCurrent()
        self.texBases = []
        self.texOverlays = []
        self.building = None
        self.buildingViewer = []
        self.currentBuilding = 0
        self.props = []
        self.propViewers = []
        self.floras = []
        self.floraViewers = []
        self.waters = []
        self.lands = []
        self.te = []
        for lcp in range(2297284864, 2297286144):
            values = self.exemplar.GetProp(lcp)
            if values is None:
                break
            self.PreCacheObject(values[:])
        base_ids = []
        for tex in self.texBases:
            if tex[3] + 3 not in base_ids:
                base_ids.append(tex[3] + 3)
        over_ids = []
        for tex in self.texOverlays:
            if tex[3] + 3 not in over_ids:
                over_ids.append(tex[3] + 3)
        self.lotBaseTextures = base_ids
        self.lotOverTextures = over_ids

    def _apply_lot_snapshot(self, snapshot):
        for lcp in [lcp for lcp in range(2297284864, 2297286144)
                    if self.exemplar.GetProp(lcp) is not None]:
            self.exemplar.RemoveProp(lcp)
        for offset, values in enumerate(snapshot):
            prop_id = 2297284864 + offset
            self.exemplar.AddTextProp(CreateAProp(self.virtualDAT.properties[prop_id], values[:]))
        self.exemplar.ReindexLotConfig()
        self.selected = []
        self.quadSelected = []
        self.newIds = []
        self.highlighted = []
        self._rebuild_scene()
        self.UpdatePIM()
        self.RebuildVars()
        self.UpdateSelectionInspector()
        self.on_draw()

    def OnUndo(self, event=None):
        if not self._undo_stack:
            return
        self._redo_stack.append(self._capture_lot_snapshot())
        self._apply_lot_snapshot(self._undo_stack.pop())
        self._update_undo_buttons()

    def OnRedo(self, event=None):
        if not self._redo_stack:
            return
        self._undo_stack.append(self._capture_lot_snapshot())
        self._apply_lot_snapshot(self._redo_stack.pop())
        self._update_undo_buttons()

    def OnDelete(self, event):
        if self.modeEdit == MODE_EDIT_BUILDING:
            return
        self._push_undo()
        prop2Remove = []
        for id, q in zip(self.selected, self.quadSelected):
            for lcp in range(2297284864, 2297286144):
                values = self.exemplar.GetProp(lcp)
                if values is None:
                    break
                if values[11] == id:
                    prop2Remove.append(lcp)
                    if values[0] == 1:
                        for idx, (what, viewer) in enumerate(zip(self.props, self.propViewers)):
                            if what[11] == id:
                                del self.props[idx]
                                del self.propViewers[idx]
                                break

                    if values[0] == 4:
                        for idx, (what, viewer) in enumerate(zip(self.floras, self.floraViewers)):
                            if what[11] == id:
                                del self.floras[idx]
                                del self.floraViewers[idx]
                                break

                    if values[0] == 2:

                        def UpdateTexData(what):
                            for texData in what:
                                if texData[4] == id:
                                    what.remove(texData)
                                    return True

                            return False

                        if not UpdateTexData(self.texBases):
                            UpdateTexData(self.texOverlays)
                    if values[0] == TRANSIT_OBJECT_TYPE:
                        remove_cached_transit(self.te, values[11])
                    if values[0] in (5, 6):
                        pool = self.waters if values[0] == 5 else self.lands
                        for texData in list(pool):
                            if texData[4] == id:
                                pool.remove(texData)
                                break
                    break

        self.selected = []
        self.quadSelected = []
        self.newIds = []
        for id in prop2Remove:
            self.exemplar.RemoveProp(id)

        self.exemplar.ReindexLotConfig()
        self.UpdatePIM()
        self.RebuildVars()
        self.UpdateSelectionInspector()
        return

    def OnDuplicate(self, event):
        if self.modeEdit not in [MODE_EDIT_BASETEX, MODE_EDIT_OVERTEX, MODE_EDIT_PROP, MODE_EDIT_FLORA, MODE_EDIT_TRANSIT]:
            return
        if len(self.quadSelected) == 0:
            return
        if self.newIds != []:
            return
        self._push_undo()
        currentID = 0
        selection = {}
        lastIDProp = 2297284864
        for lcp in range(2297284864, 2297286144):
            values = self.exemplar.GetProp(lcp)
            if values is None:
                break
            if values[11] > currentID:
                currentID = values[11]
            if values[11] in self.selected:
                selection[values[11]] = values[:]
            lastIDProp = lcp

        currentID += 1
        newSelection = []
        newQuad = []
        lastIDProp += 1
        for id, q in zip(self.selected, self.quadSelected):
            newQuad.append(q[:])
            newSelection.append(currentID)
            v = selection[id]
            if v[0] == TRANSIT_OBJECT_TYPE:
                ensure_transit_values(v)
            v[11] = currentID
            self.exemplar.AddTextProp(CreateAProp(self.virtualDAT.properties[lastIDProp], v[:]))
            self.PreCacheObject(v)
            self.newIds.append(lastIDProp)
            lastIDProp += 1
            currentID += 1

        self.selected = newSelection
        self.quadSelected = newQuad
        self.UpdatePIM()
        self.RefreshAssetBrowser()
        self.UpdateSelectionInspector()
        return

    def ComputeBBox(self):
        xMin = None
        yMin = None
        xMax = None
        yMax = None
        for id, q in zip(self.selected, self.quadSelected):
            for lcp in range(2297284864, 2297286144):
                values = self.exemplar.GetProp(lcp)
                if values is None:
                    break
                if values[11] == id:
                    if xMin is None:
                        xMin = ToCoord(values[6])
                    else:
                        xMin = min(xMin, ToCoord(values[6]))
                    if xMax is None:
                        xMax = ToCoord(values[8])
                    else:
                        xMax = max(xMax, ToCoord(values[8]))
                    if yMin is None:
                        yMin = ToCoord(values[7])
                    else:
                        yMin = min(yMin, ToCoord(values[7]))
                    if yMax is None:
                        yMax = ToCoord(values[9])
                    else:
                        yMax = max(yMax, ToCoord(values[9]))
                    break

        return (
         xMin, yMin, xMax, yMax)

    def Align(self, ids, val):
        self._push_undo()
        for id, q in zip(self.selected, self.quadSelected):
            for lcp in range(2297284864, 2297286144):
                values = self.exemplar.GetProp(lcp)
                if values is None:
                    break
                if values[11] == id:
                    delta = val - ToCoord(values[ids[1]])
                    for iid in ids:
                        values[iid] = ToUnsigned(int((ToCoord(values[iid]) + delta) * 65536))

                    q[0] = ToCoord(values[6])
                    q[1] = ToCoord(values[7])
                    q[2] = ToCoord(values[8])
                    q[3] = ToCoord(values[9])
                    what = self.props
                    if values[0] == 4:
                        what = self.floras
                    for prop in what:
                        if prop[11] == id:
                            prop[:13] = values
                            break

                    break

        return

    def OnAlignLeft(self, event):
        if self.modeEdit not in [MODE_EDIT_PROP, MODE_EDIT_FLORA]:
            return
        if len(self.quadSelected) == 0:
            return
        xMin, yMin, xMax, yMax = self.ComputeBBox()
        self.Align([3, 6, 8], xMin)

    def OnAlignRight(self, event):
        if self.modeEdit not in [MODE_EDIT_PROP, MODE_EDIT_FLORA]:
            return
        if len(self.quadSelected) == 0:
            return
        xMin, yMin, xMax, yMax = self.ComputeBBox()
        self.Align([3, 8, 6], xMax)

    def OnAlignTop(self, event):
        if self.modeEdit not in [MODE_EDIT_PROP, MODE_EDIT_FLORA]:
            return
        if len(self.quadSelected) == 0:
            return
        xMin, yMin, xMax, yMax = self.ComputeBBox()
        self.Align([5, 7, 9], yMin)

    def OnAlignBottom(self, event):
        if self.modeEdit not in [MODE_EDIT_PROP, MODE_EDIT_FLORA]:
            return
        if len(self.quadSelected) == 0:
            return
        xMin, yMin, xMax, yMax = self.ComputeBBox()
        self.Align([5, 9, 7], yMax)

    def _event_shortcut_key(self, event):
        key = event.GetKeyCode()
        if event.ControlDown() and 65 <= key <= 90:
            return key - 64
        if 65 <= key <= 90:
            return ord(chr(key).lower())
        return key

    def _shortcut_focus_allows_editor_keys(self):
        focus = wx.Window.FindFocus()
        if focus is None:
            return True
        if isinstance(focus, wx.SearchCtrl):
            return False
        if isinstance(focus, wx.TextCtrl):
            return bool(focus.GetWindowStyleFlag() & wx.TE_READONLY)
        return True

    def _HandleShortcut(self, event):
        # Shift+B toggles the background; handled before the numeric keymap so
        # it isn't confused with plain 'b' (building mode).
        if (event.ShiftDown() and not event.ControlDown()
                and event.GetKeyCode() in (ord('B'), ord('b'))):
            self.OnToggleBackground(event)
            return True
        key = self._event_shortcut_key(event)
        funcAlign = {0: [self.OnAlignRight, self.OnAlignLeft, self.OnAlignBottom, self.OnAlignTop],1: [self.OnAlignBottom, self.OnAlignTop, self.OnAlignLeft, self.OnAlignRight],2: [self.OnAlignLeft, self.OnAlignRight, self.OnAlignTop, self.OnAlignBottom],3: [self.OnAlignTop, self.OnAlignBottom, self.OnAlignRight, self.OnAlignLeft]}
        rot = self.rotation
        func2call = {97: self.OnCycleViewMode,366: self.OnRotateViewRight,367: self.OnRotateViewLeft,312: self.OnRotateRight,313: self.OnRotateLeft,112: self.OnModeProp,43: self.OnZoom,45: self.OnUnzoom,61: self.OnZoom,95: self.OnUnzoom,wx.WXK_NUMPAD_ADD: self.OnZoom,wx.WXK_NUMPAD_SUBTRACT: self.OnUnzoom,104: self.OnModePan,98: self.OnModeBuilding,116: self.OnModeBaseTex,118: self.OnModeOverTex,102: self.OnModeFlora,101: self.OnModeTransit,119: self.OnModeConstraint,110: self.OnCycleFamily,103: self.OnCycleDisplayMode,49: self.OnSetZoom1,50: self.OnSetZoom2,51: self.OnSetZoom3,52: self.OnSetZoom4,53: self.OnSetZoom5,54: self.OnSetZoom6,wx.WXK_NUMPAD1: self.OnSetZoom1,wx.WXK_NUMPAD2: self.OnSetZoom2,wx.WXK_NUMPAD3: self.OnSetZoom3,wx.WXK_NUMPAD4: self.OnSetZoom4,wx.WXK_NUMPAD5: self.OnSetZoom5,wx.WXK_NUMPAD6: self.OnSetZoom6,109: self.OnMirror,100: self.OnDuplicate,127: self.OnDelete,18: funcAlign[rot][0],12: funcAlign[rot][1],2: funcAlign[rot][2],20: funcAlign[rot][3],314: self.OnKeyMove,315: self.OnKeyMove,316: self.OnKeyMove,317: self.OnKeyMove,115: self.OnToggleSnap,19: self.OnSetSnap,26: self.OnUndo,25: self.OnRedo,99: self.OnFitView}
        if key in func2call.keys():
            func2call[key](event)
            self.on_draw()
            return True
        return False

    def _OnCharHook(self, event):
        if self._shortcut_focus_allows_editor_keys() and self._HandleShortcut(event):
            return
        event.Skip()

    def _OnChar(self, event):
        if self._HandleShortcut(event):
            return
        event.Skip()

    def CanUpdateIcon(self):
        """True when this exemplar is a lot whose building icon can be saved."""
        try:
            if self.exemplar.GetProp(16)[0] != 16:
                return False
            desc = self.virtualDAT.FindBuildingFromLot(self.exemplar)
            return (desc.exemplar.entry.tgi[0] == 1697917002
                    and desc in self.virtualDAT.categories[3431971885].descriptors)
        except Exception:
            return False

    def OnUpdateIcon(self, event):
        if not self.CanUpdateIcon():
            return
        self.on_draw()
        self.on_draw()
        img = self.Save()
        self.descPage.OnUpdateIcon(img)
        self.UpdatePIM()
        self.RebuildVars()

    def OnPreviewIcon(self, event=None):
        """Show the icon the lot would generate, with an option to apply it."""
        self.on_draw()
        self.on_draw()
        icon = SC4IconMakerDlg.compose_lot_icon(self.Save())
        dlg = LotIconPreviewDlg(self, icon, self.CanUpdateIcon())
        dlg.ShowModal()
        dlg.Destroy()

    def _append_layer_menu(self, parent, view_key, title, layers):
        submenu = wx.Menu()
        all_on = wx.NewIdRef()
        all_off = wx.NewIdRef()
        submenu.Append(all_on, LEXLayerAllOn)
        submenu.Append(all_off, LEXLayerAllOff)
        submenu.AppendSeparator()
        submenu.Bind(wx.EVT_MENU, lambda event: self.SetAllLayersVisible(view_key, True), id=all_on)
        submenu.Bind(wx.EVT_MENU, lambda event: self.SetAllLayersVisible(view_key, False), id=all_off)
        for key, label in LAYER_SPECS:
            menu_id = wx.NewIdRef()
            item = submenu.AppendCheckItem(menu_id, label)
            item.Check(bool(layers.get(key, True)))
            self._layer_menu_ids[int(menu_id)] = (view_key, key)
            submenu.Bind(wx.EVT_MENU, self.OnToggleLayerVisibility, id=menu_id)
        parent.AppendSubMenu(submenu, title)

    def _append_background_menu(self, parent):
        submenu = wx.Menu()
        for name, _path in background_sets():
            menu_id = wx.NewIdRef()
            item = submenu.AppendRadioItem(menu_id, name)
            item.Check(name == self.backgroundSet)
            self._background_menu_ids[int(menu_id)] = name
            submenu.Bind(wx.EVT_MENU, self.OnChooseBackgroundSet, id=menu_id)
        parent.AppendSubMenu(submenu, LEXLayerBackgroundSets)

    def OnLayersMenu(self, event=None):
        menu = wx.Menu()
        self._layer_menu_ids = {}
        self._background_menu_ids = {}
        self._append_layer_menu(menu, '2d', LEXLayer2D, self.visibleLayers2D)
        self._append_layer_menu(menu, '3d', LEXLayer3D, self.visibleLayers3D)
        menu.AppendSeparator()
        self._append_background_menu(menu)
        menu.AppendSeparator()
        night_id = wx.NewIdRef()
        night_item = menu.AppendCheckItem(int(night_id), LEXLayerNightMode)
        night_item.Check(bool(getattr(self, 'nightMode', False)))
        menu.Bind(wx.EVT_MENU, self.OnToggleNightMode, id=int(night_id))
        if event is not None and hasattr(event.GetEventObject(), 'PopupMenu'):
            event.GetEventObject().PopupMenu(menu)
        else:
            self.PopupMenu(menu)
        menu.Destroy()

    def OnToggleNightMode(self, event=None):
        self.nightMode = not bool(getattr(self, 'nightMode', False))
        if getattr(self, 's3DTexturesHolder', None) is not None:
            try:
                self.s3DTexturesHolder.SetNightMode(self.nightMode)
            except Exception:
                logger.exception('Failed to switch night-light mode')
        self.SaveEditorState()
        self.on_draw()

    def _ensure_s3d_shader_program(self):
        if self.s3d_shader_program is None:
            self.s3d_shader_program = SC4LightingProgram()
        return self.s3d_shader_program

    def _lot_lighting_state(self, exemplar):
        state = dict(NIGHT_PRESET if self.nightMode else DAY_PRESET)
        state['prelit'] = model_is_prelit(exemplar)
        return state

    def _lot_environment_light(self):
        return approximate_model_light(self._lot_lighting_state(None))

    def OnToggleLayerVisibility(self, event):
        view_key, layer_key = self._layer_menu_ids.get(event.GetId(), (None, None))
        if view_key is None:
            return
        layers = self.visibleLayers3D if view_key == '3d' else self.visibleLayers2D
        layers[layer_key] = not bool(layers.get(layer_key, True))
        self.SaveEditorState()
        self.on_draw()

    def SetAllLayersVisible(self, view_key, visible):
        layers = self.visibleLayers3D if view_key == '3d' else self.visibleLayers2D
        for key in layers:
            layers[key] = bool(visible)
        self.SaveEditorState()
        self.on_draw()

    def OnToggleBackground(self, event=None):
        """Toggle terrain background visibility in both preview views."""
        visible = not (
            self._is_layer_visible('2d', LAYER_BACKGROUND)
            or self._is_layer_visible('3d', LAYER_BACKGROUND)
        )
        self.visibleLayers2D[LAYER_BACKGROUND] = visible
        self.visibleLayers3D[LAYER_BACKGROUND] = visible
        self.SaveEditorState()
        self.on_draw()

    def OnChooseBackgroundSet(self, event):
        """Switch to a different background set and reload its textures."""
        name = self._background_menu_ids.get(event.GetId())
        if not name:
            return
        self.backgroundSet = name
        if self.glCanvas2D is not None:
            try:
                self.glCanvas2D.SetCurrent()
                self.Preload_Background_Tex2()
            except Exception:
                logger.exception('Failed to load background set %s', name)
        self.on_draw()

    def OnToggleSnap(self, event):
        if self.snapSize == 0:
            self.snapSize = self.currentSnapSize
            snapSize = self.snapSize
            xS = 0 - snapSize
            xE = self.lotSizeXOver + snapSize
            yS = 0 - snapSize
            yE = self.lotSizeYOver + snapSize
            snapGrids = []
            glColor3f(0.5, 0, 0.2)
            yC = yS
            xC = xS
            while 1:
                snapGrids.append((xS, yC))
                snapGrids.append((xE, yC))
                yC += snapSize
                if yC > yE:
                    break

            while 1:
                snapGrids.append((xC, yS))
                snapGrids.append((xC, yE))
                xC += snapSize
                if xC > xE:
                    break

            self.nbSnapLines = len(snapGrids)
            self.snapGrids = numpy.asarray(snapGrids, 'f').tobytes()
        else:
            self.snapSize = 0

    def OnSnapButton(self, event):
        """Toolbar Snap button: click toggles, Ctrl+click sets the grid size."""
        if wx.GetKeyState(wx.WXK_CONTROL):
            self.OnSetSnap(event)
        else:
            self.OnToggleSnap(event)
        self.on_draw()

    def OnSetSnap(self, event):
        dlg = wx.TextEntryDialog(self, LEXSnapGripSize, 'LE-X', '%.01f' % self.currentSnapSize)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                value = float(dlg.GetValue())
                # A snap size <= 0 makes the grid-building loops never advance.
                if value <= 0:
                    raise ValueError
                self.currentSnapSize = value
                self.snapSize = 0
                self.OnToggleSnap(event)
            except ValueError:
                pass

        dlg.Destroy()

    def OnCloseWindow(self, event):
        self.SaveEditorState()
        if self.LETools:
            self.LETools.Save()
            self.LETools = None
        if hasattr(self, 't2'):
            self.t2.Stop()
        self.Free()
        event.Skip()
        return True

    def EvtComboBoxZoom(self, evt):
        self.glCanvas2D.Refresh(False)

    def EvtComboBoxRotation(self, evt):
        self.glCanvas2D.Refresh(False)

    def Free(self):
        self.glCanvas2D.SetCurrent()
        for k, tex in self.textures.items():
            for t in tex[0]:
                delete_gl_texture(t)

        self.s3DTexturesHolder.Free()
        self.glCanvas2D.displayer = None
        self.glCanvas2D = None
        return

    def Img2OGL(self, im, bAlpha):
        size = im.size
        if bAlpha:
            im = im.tobytes('raw', 'RGBA')
        else:
            im = im.tobytes('raw', 'RGB')
        glEnable(GL_TEXTURE_2D)
        texName = gl_texture_name(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D, texName)
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        if bAlpha:
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size[0], size[1], 0, GL_RGBA, GL_UNSIGNED_BYTE, im)
        else:
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, size[0], size[1], 0, GL_RGB, GL_UNSIGNED_BYTE, im)
        glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        return texName

    def Preload_Background_Tex2(self):
        texs = [
         'Back01.jpg', 'Back02.jpg', 'Back03.jpg', 'Back04.jpg', 'Back05.jpg']
        self.BackTextures = [None, None, None, None, None]
        self.BackTextureSizes = [None, None, None, None, None]
        set_dir = background_set_dir(getattr(self, 'backgroundSet', 'Default'))
        for i, tex in enumerate(texs):
            try:
                im = Image.open(set_dir / tex)
            except Exception:
                logger.exception("Can't load background texture %s", tex)
                continue

            try:
                texOGL = self.Img2OGL(im, False)
                self.BackTextureSizes[i] = im.size
                self.BackTextures[i] = texOGL
            except Exception:
                logger.exception("Can't convert background texture to OGL: %s", tex)
                continue

        return

    def Preload_TE_Tex(self):
        texs = [
         'TE_Road.jpg', 'TE_Train.jpg', 'TE_ElevatedHighway.jpg', 'TE_Street.jpg', '', '', 'TE_Avenue.jpg', '', 'TE_ElTrain.jpg', 'TE_Monorail.jpg', 'TE_OneWay.jpg', '', 'TE_GroundHighway.jpg']
        for i, tex in enumerate(texs):
            try:
                im = Image.open(background_path(tex))
            except Exception:
                continue

            im = Image.merge('RGBA', im.split() + (im.split()[0],))
            texOGL = self.Img2OGL(im, True)
            textures = [texOGL, texOGL, texOGL, texOGL, texOGL]
            self.textures[i, 0] = [textures, True]

    def GetTextures(self, texID):
        textures = []
        bBase = True
        for zLevel in range(5):
            texEntry = self.virtualDAT.getEntry(2058686020, 159781726, texID + zLevel)
            if texEntry is not None:
                texEntry.read_file(None, True, True)
                nbrLayers, trueAlpha, img, alpha, size = FSHConverter.decodeFSH(texEntry.content)
                texEntry.content = None
                texEntry.rawContent = None
                if trueAlpha:
                    if zLevel == 0:
                        bBase = False
                    imBmp = bBase or Image.frombytes('RGB', size, img)
                    imAlpha = Image.frombytes('L', size, alpha)
                    im = Image.merge('RGBA', imBmp.split() + imAlpha.split())
                    textures.append(self.Img2OGL(im, True))
                    if zLevel == 3:
                        self.lotOverTextures.append(texID + zLevel)
                else:
                    im = Image.frombytes('RGB', size, img)
                    textures.append(self.Img2OGL(im, False))
                    if zLevel == 3:
                        self.lotBaseTextures.append(texID + zLevel)
            else:
                return (
                 False, [])

        return (
         bBase, textures)

    def GetTexturesLE(self, texGID, texIID):
        textures = []
        texEntry = self.virtualDAT.getEntry(2058686020, texGID, texIID)
        if texEntry is not None:
            texEntry.read_file(None, True, True)
            nbrLayers, trueAlpha, img, alpha, size = FSHConverter.decodeFSH(texEntry.content)
            texEntry.content = None
            texEntry.rawContent = None
            imBmp = Image.frombytes('RGB', size, img)
            imAlpha = Image.frombytes('L', size, alpha)
            im = Image.merge('RGBA', imBmp.split() + imAlpha.split())
            texOGL = self.Img2OGL(im, True)
            textures = [texOGL, texOGL, texOGL, texOGL, texOGL]
        return (True, textures)

    def LoadBuildingModel(self, buildingID):
        selectedDesc = []
        self.buildingViewer = []
        self.currentBuilding = 0
        if buildingID in self.virtualDAT.categories:
            name = self.virtualDAT.categories[buildingID].Name
            for desc in self.virtualDAT.categories[buildingID].descriptors:
                if desc.exemplar.GetProp(16)[0] == 2 and desc.exemplar.entry.tgi[0] == 1697917002:
                    selectedDesc.append(desc)

            if selectedDesc == []:
                return 'not found'
        if selectedDesc == []:
            possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == buildingID, self.virtualDAT.categories[210746197].descriptors)
            for desc in possibles:
                selectedDesc.append(desc)
                name = desc.name
                break

        if selectedDesc == []:
            return 'not found'
        for desc in selectedDesc:
            rkt0 = desc.exemplar.GetProp(662775840)
            rkt1 = desc.exemplar.GetProp(662775841)
            rkt3 = desc.exemplar.GetProp(662775843)
            rkt4 = desc.exemplar.GetProp(662775844)
            rkt5 = desc.exemplar.GetProp(662775845)
            buildingViewer = None
            if rkt0:
                buildingViewer = ResourceViewer(662775840, rkt0, self.virtualDAT, None)
            elif rkt1:
                buildingViewer = ResourceViewer(662775841, rkt1, self.virtualDAT, None)
            elif rkt3:
                buildingViewer = ResourceViewer(662775843, rkt3, self.virtualDAT, None)
            elif rkt4:
                self.rtk4Offsets[buildingID] = (
                 ToCoord(rkt4[1]), ToCoord(rkt4[2]), ToCoord(rkt4[3]))
                buildingViewer = ResourceViewer(662775844, rkt4, self.virtualDAT, None)
            elif rkt5:
                buildingViewer = ResourceViewer(662775845, rkt5, self.virtualDAT, None)
            if buildingViewer is not None:
                buildingViewer.night_state = night_state_for(desc.exemplar)
                buildingViewer.lighting_exemplar = desc.exemplar
            self.buildingViewer.append(buildingViewer)
            try:
                self.buildingViewer[-1].PreLoad(self.virtualDAT, self.s3DTexturesHolder)
                continue
            except Exception:
                if buildingViewer is None:
                    pass
                else:
                    logger.exception(
                        "Can't load building model rkType=%s rktData=%s",
                        hex2str(buildingViewer.rkType),
                        '-'.join([hex2str(v) for v in buildingViewer.rktData]))

        return name

    def RebuildVars(self):
        self.lotFamiliesPropID = []
        self.lotPropDescs = []
        self.lotFloraDescs = []
        ids = [ tex[3] for tex in self.texBases ]
        for id in self.lotBaseTextures:
            if ids.count(id - 3) == 0:
                self.lotBaseTextures.remove(id)

        ids = [ tex[3] for tex in self.texOverlays ]
        for id in self.lotOverTextures:
            if ids.count(id - 3) == 0:
                self.lotOverTextures.remove(id)

        for lcp in range(2297284864, 2297286144):
            values = self.exemplar.GetProp(lcp)
            if values is None:
                break
            values = values[:]
            if values[0] == 1 or values[0] == 4:
                propID = values[12]
                selectedDesc = None
                cat = 1830116951
                if values[0] == 1:
                    cat = 210746660
                if propID in self.virtualDAT.categories:
                    bOk = False
                    for desc in self.virtualDAT.categories[propID].descriptors:
                        name = self.virtualDAT.categories[propID].Name
                        if desc.exemplar.GetProp(16)[0] == 30 and desc.exemplar.entry.tgi[0] == 1697917002:
                            bOk = True
                            selectedDesc = desc
                            if propID not in self.lotFamiliesPropID:
                                self.lotFamiliesPropID.append(propID)
                            continue

                    if not bOk:
                        continue
                if selectedDesc is None:
                    possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == propID, self.virtualDAT.categories[cat].descriptors)
                    for desc in possibles:
                        selectedDesc = desc
                        name = selectedDesc.name
                        continue

                if selectedDesc is None:
                    continue
                if values[0] == 1:
                    if selectedDesc not in self.lotPropDescs:
                        self.lotPropDescs.append(selectedDesc)
                elif selectedDesc not in self.lotFloraDescs:
                    self.lotFloraDescs.append(selectedDesc)

        if self.LETools:
            self.LETools.ReBuildLot()
        self.RefreshAssetBrowser()
        return

    def LoadPropModel(self, propID):
        selectedDesc = None
        if propID in self.virtualDAT.categories:
            bOk = False
            for desc in self.virtualDAT.categories[propID].descriptors:
                name = self.virtualDAT.categories[propID].Name
                if desc.exemplar.GetProp(16)[0] == 30 and desc.exemplar.entry.tgi[0] == 1697917002:
                    bOk = True
                    selectedDesc = desc
                    self.lotFamiliesPropID.append(propID)
                    break

            if not bOk:
                return (None, 'not found')
        if selectedDesc is None:
            possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == propID, self.virtualDAT.categories[210746660].descriptors)
            for desc in possibles:
                selectedDesc = desc
                name = selectedDesc.name
                break

        if selectedDesc is None:
            return (None, 'not found')
        rkt0 = selectedDesc.exemplar.GetProp(662775840)
        rkt1 = selectedDesc.exemplar.GetProp(662775841)
        rkt3 = selectedDesc.exemplar.GetProp(662775843)
        rkt4 = selectedDesc.exemplar.GetProp(662775844)
        rkt5 = desc.exemplar.GetProp(662775845)
        self.lotPropDescs.append(selectedDesc)
        propViewer = None
        if rkt0:
            propViewer = ResourceViewer(662775840, rkt0, self.virtualDAT, None)
        elif rkt1:
            propViewer = ResourceViewer(662775841, rkt1, self.virtualDAT, None)
        elif rkt3:
            propViewer = ResourceViewer(662775843, rkt3, self.virtualDAT, None)
        elif rkt4:
            self.rtk4Offsets[propID] = (
             ToCoord(rkt4[1]), ToCoord(rkt4[2]), ToCoord(rkt4[3]))
            propViewer = ResourceViewer(662775844, rkt4, self.virtualDAT, None)
        elif rkt5:
            propViewer = ResourceViewer(662775845, rkt5, self.virtualDAT, None)
        if propViewer is not None:
            propViewer.night_state = night_state_for(selectedDesc.exemplar)
            propViewer.lighting_exemplar = selectedDesc.exemplar
        try:
            propViewer.PreLoad(self.virtualDAT, self.s3DTexturesHolder)
        except Exception:
            if propViewer is None:
                pass
            else:
                logger.exception(
                    "Can't load prop model rkType=%s rktData=%s",
                    hex2str(propViewer.rkType),
                    '-'.join([hex2str(v) for v in propViewer.rktData]))

        return (
         propViewer, name)

    def LoadFloraModel(self, propID):
        selectedDesc = None
        if selectedDesc is None:
            possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == propID, self.virtualDAT.categories[1830116951].descriptors)
            for desc in possibles:
                selectedDesc = desc
                name = selectedDesc.name
                break

        if selectedDesc is None:
            return (None, 'not found')
        self.lotFloraDescs.append(selectedDesc)
        rkt0 = selectedDesc.exemplar.GetProp(662775840)
        rkt1 = selectedDesc.exemplar.GetProp(662775841)
        rkt3 = selectedDesc.exemplar.GetProp(662775843)
        rkt4 = selectedDesc.exemplar.GetProp(662775844)
        rkt5 = selectedDesc.exemplar.GetProp(662775845)
        propViewer = None
        if rkt0:
            propViewer = ResourceViewer(662775840, rkt0, self.virtualDAT, None)
        elif rkt1:
            propViewer = ResourceViewer(662775841, rkt1, self.virtualDAT, None)
        elif rkt3:
            propViewer = ResourceViewer(662775843, rkt3, self.virtualDAT, None)
        elif rkt4:
            self.rtk4Offsets[propID] = (
             ToCoord(rkt4[1]), ToCoord(rkt4[2]), ToCoord(rkt4[3]))
            propViewer = ResourceViewer(662775844, rkt4, self.virtualDAT, None)
        elif rkt5:
            propViewer = ResourceViewer(662775845, rkt5, self.virtualDAT, None)
        if propViewer is not None:
            propViewer.night_state = night_state_for(selectedDesc.exemplar)
            propViewer.lighting_exemplar = selectedDesc.exemplar
        try:
            propViewer.PreLoad(self.virtualDAT, self.s3DTexturesHolder)
        except Exception:
            if propViewer is None:
                pass
            else:
                logger.exception(
                    "Can't load flora model rkType=%s rktData=%s",
                    hex2str(propViewer.rkType),
                    '-'.join([hex2str(v) for v in propViewer.rktData]))

        return (
         propViewer, name)

    def PreCacheObject(self, values):
        if values[0] == 0:
            self.building = values
            self.building.append(self.LoadBuildingModel(values[12]))
        if values[0] == 1:
            bOk = False
            for prop, viewer in zip(self.props, self.propViewers):
                if prop[12] == values[12]:
                    values.append(prop[-1])
                    self.props.append(values)
                    self.propViewers.append(viewer)
                    bOk = True
                    break

            if not bOk:
                propView, name = self.LoadPropModel(values[12])
                values.append(name)
                self.props.append(values)
                self.propViewers.append(propView)
        if values[0] == 2:
            texID = values[12]
            bBase = True
            if texID not in self.textures:
                bBase, textures = self.GetTextures(texID)
                self.textures[texID] = [textures, bBase]
            else:
                bBase = self.textures[texID][1]
            texData = [
             ToTileOrigin(values[3]), ToTileOrigin(values[5]), values[2], texID, values[11]]
            if bBase:
                self.texBases.append(texData)
            else:
                self.texOverlays.append(texData)
        if values[0] == 4:
            bOk = False
            for flora, viewer in zip(self.floras, self.floraViewers):
                if flora[12] == values[12]:
                    values.append(flora[-1])
                    self.floras.append(values)
                    self.floraViewers.append(viewer)
                    bOk = True
                    break

            if not bOk:
                viewer, name = self.LoadFloraModel(values[12])
                values.append(name)
                self.floras.append(values)
                self.floraViewers.append(viewer)
        if values[0] == 5:
            texData = [
             ToTileOrigin(values[3]), ToTileOrigin(values[5]), values[2], 8960, values[11]]
            self.waters.append(texData)
        if values[0] == 6:
            texData = [
             ToTileOrigin(values[3]), ToTileOrigin(values[5]), values[2], 8960, values[11]]
            self.lands.append(texData)
        if values[0] == 7:
            self.te.append(cached_transit(values))

    def PreCache(self):
        self.glCanvas2D.SetCurrent()
        self.LEAnimMissing = ResourceViewer(662775840, (698733036, 707025145, 743768064), self.virtualDAT, None)
        self.LEAnimMissing.PreLoad(self.virtualDAT, self.s3DTexturesHolder)
        self.textures = {}
        self.texBases = []
        self.texOverlays = []
        self.building = None
        self.buildingViewer = []
        self.props = []
        self.propViewers = []
        self.floras = []
        self.floraViewers = []
        self.waters = []
        self.lands = []
        self.te = []
        base, roadTex = self.GetTextures(641146880)
        self.textures[641146880] = [roadTex, base]
        base, waterLandTex = self.GetTexturesLE(3412818905, 1802442183)
        self.textures[1802442183] = [waterLandTex, base]
        self.lotOverTextures = []
        self.lotBaseTextures = []
        self.Preload_TE_Tex()
        self.Preload_Background_Tex2()
        for lcp in range(2297284864, 2297286144):
            values = self.exemplar.GetProp(lcp)
            if values is None:
                break
            values = values[:]
            self.PreCacheObject(values)

        return

    def Display(self, exemplar, virtualDAT, bForIcon=False):
        wx.BeginBusyCursor()
        self.bBackAligned = bForIcon
        self.exemplar = exemplar
        self.lotSizeX = self.exemplar.GetProp(2297284496)[0]
        self.lotSizeY = self.exemplar.GetProp(2297284496)[1]
        self.lotSizeXOver = self.exemplar.GetProp(2297284496)[0] * 16
        self.lotSizeYOver = self.exemplar.GetProp(2297284496)[1] * 16
        self.lotSizeXOffset = self.exemplar.GetProp(2297284496)[0] * 8
        self.lotSizeYOffset = self.exemplar.GetProp(2297284496)[1] * 8
        self.virtualDAT = virtualDAT
        self.PreCache()
        self.posy = 0
        self.posx = 0
        self.posz = 10
        self.pos3Dy = 0
        self.pos3Dx = 0
        self.pos3Dz = -10
        self._update_lot_context()
        if not bForIcon:
            self.RefreshAssetBrowser()
            self.UpdateSelectionInspector()
        wx.EndBusyCursor()
        self.t2 = wx.CallLater(500, self.on_draw)

    def init_gl(self):
        self.glCanvas2D.displayer = self
        self.glCanvas2D.SetCurrent()
        glClearColor(0.5, 0.5, 0.5, 0.0)
        glClearDepth(1.0)
        glShadeModel(GL_SMOOTH)
        glEnable(GL_MULTISAMPLE)  # anti-aliased edges when an MSAA buffer exists
        glMatrixMode(GL_MODELVIEW)
        glDisable(GL_CULL_FACE)

    def on_draw(self):
        # on_draw can be invoked by a pending wx.CallLater (see Display) after
        # the window/canvas has already been destroyed; bail out cleanly
        # instead of touching a freed C/C++ object.
        canvas = self.glCanvas2D
        if not canvas:
            return
        try:
            canvas.SetCurrent()
        except RuntimeError:
            return
        if self.modeEdit == MODE_EDIT_PAN:
            if self.panel == 3:
                if self.glCanvas2D.click_x > self.glCanvas2D.GetClientSize()[0] // 2:
                    self.posx -= self.glCanvas2D.dx * 0.25
                    self.posy -= self.glCanvas2D.dy * 0.25
                else:
                    self.pos3Dx -= self.glCanvas2D.dx * 0.25
                    self.pos3Dy += self.glCanvas2D.dy * 0.25
            if self.panel == 1:
                self.pos3Dx -= self.glCanvas2D.dx * 0.25
                self.pos3Dy += self.glCanvas2D.dy * 0.25
            if self.panel == 2:
                self.posx -= self.glCanvas2D.dx * 0.25
                self.posy -= self.glCanvas2D.dy * 0.25
        self.glCanvas2D.dx = 0
        self.glCanvas2D.dy = 0
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if self.panel == 3 or self.panel == 2:
            self.Draw2D()
        if self.panel == 3 or self.panel == 1:
            self.Draw3D()
        self.glCanvas2D.SwapBuffers()

    def DrawQuad(self, x, y, flag, texID, bAlpha, bHighlighted=False):
        glEnable(GL_TEXTURE_2D)
        zoom = self.zoom
        if zoom == 5:
            zoom = 4
        bTex = True
        try:
            glBindTexture(GL_TEXTURE_2D, self.textures[texID][0][zoom])
        except Exception:
            bTex = False

        if bAlpha:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        else:
            glDisable(GL_BLEND)
        offsetX = x * 16 - self.lotSizeXOffset
        offsetY = y * 16 - self.lotSizeYOffset
        tex_coords = texture_coords_for_flag(flag)
        with pushed_modelview_matrix():
            glTranslate(offsetX, offsetY, 0)
            glMatrixMode(GL_TEXTURE)
            glLoadIdentity()
            glMatrixMode(GL_MODELVIEW)
            if bTex:
                glBegin(GL_QUADS)
                glTexCoord2f(*tex_coords[0])
                glVertex3i(0, 16, 0)
                glTexCoord2f(*tex_coords[1])
                glVertex3i(0, 0, 0)
                glTexCoord2f(*tex_coords[2])
                glVertex3i(16, 0, 0)
                glTexCoord2f(*tex_coords[3])
                glVertex3i(16, 16, 0)
                glEnd()
            if bHighlighted:
                glEnable(GL_BLEND)
                glBlendFunc(GL_ONE, GL_ONE)
                glDisable(GL_TEXTURE_2D)
                glBegin(GL_QUADS)
                glColor3f(1, 0, 0)
                glVertex3i(0, 16, 0)
                glColor3f(1, 0, 0)
                glVertex3i(0, 0, 0)
                glColor3f(1, 0, 0)
                glVertex3i(16, 0, 0)
                glColor3f(1, 0, 0)
                glVertex3i(16, 16, 0)
                glEnd()
                glDisable(GL_BLEND)
            glDisable(GL_TEXTURE_2D)
            glDisable(GL_BLEND)
            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
            glColor3f(1, 1, 1)

    def DrawHighLight(self, minx, miny, maxx, maxy, color=(1, 0, 0)):
        with pushed_modelview_matrix():
            offsetX = -self.lotSizeXOffset
            offsetY = -self.lotSizeYOffset
            glTranslate(offsetX, offsetY, 0)
            glDisable(GL_TEXTURE_2D)
            glDisable(GL_BLEND)
            glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
            glColor3f(color[0], color[1], color[2])
            glRectf(minx, miny, maxx, maxy)
            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

    def DrawQuadsHighLight(self, quads, color=(1, 0, 0)):
        with pushed_modelview_matrix():
            offsetX = -self.lotSizeXOffset
            offsetY = -self.lotSizeYOffset
            glTranslate(offsetX, offsetY, 0)
            glDisable(GL_TEXTURE_2D)
            glDisable(GL_BLEND)
            glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
            glColor3f(color[0], color[1], color[2])
            for quad in quads:
                glRectf(quad[0], quad[1], quad[2], quad[3])

            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

    def DrawQuadColor(self, flag, minx, miny, maxx, maxy, color, bMissing):
        with pushed_modelview_matrix():
            offsetX = -self.lotSizeXOffset
            offsetY = -self.lotSizeYOffset
            glTranslate(offsetX, offsetY, 0)
            glDisable(GL_TEXTURE_2D)
            glColor4f(color[0], color[1], color[2], color[3])
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glRectf(minx, miny, maxx, maxy)
            glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
            glDisable(GL_BLEND)
            glColor3f(color[0], color[1], color[2])
            glRectf(minx, miny, maxx, maxy)
            glColor4f(color[0], color[1], color[2], color[3])
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
            glEnable(GL_TEXTURE_2D)
            tex_coords = texture_coords_for_flag(flag)
            glMatrixMode(GL_TEXTURE)
            glLoadIdentity()
            glColor3f(1, 0, 1)
            glMatrixMode(GL_MODELVIEW)
            glDisable(GL_TEXTURE_2D)
            try:
                glEnable(GL_TEXTURE_2D)
                glBindTexture(GL_TEXTURE_2D, self.textures[1802442183][0][0])
                glBegin(GL_QUADS)
                glTexCoord2f(*tex_coords[0])
                glVertex3f(minx, maxy, 0)
                glTexCoord2f(*tex_coords[1])
                glVertex3f(minx, miny, 0)
                glTexCoord2f(*tex_coords[2])
                glVertex3f(maxx, miny, 0)
                glTexCoord2f(*tex_coords[3])
                glVertex3f(maxx, maxy, 0)
                glEnd()
            except Exception:
                pass

            glDisable(GL_TEXTURE_2D)
            glDisable(GL_BLEND)
            glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
            if bMissing:
                self.missingLines.append((minx, miny))
                self.missingLines.append((maxx, maxy))
                self.missingLines.append((minx, maxy))
                self.missingLines.append((maxx, miny))
            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
            glColor4f(1, 1, 1, 1)

    def Draw2D(self):
        self.missingLines = []
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glDisable(GL_ALPHA_TEST)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        glDisable(GL_TEXTURE_2D)
        glMatrixMode(GL_TEXTURE)
        glLoadIdentity()
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        size = self.size = self.glCanvas2D.GetClientSize()
        if self.panel == 3:
            w = self.size[0] // 2
            s = w
        elif self.panel == 2:
            w = self.size[0]
            s = 0
        else:
            return
        h = self.size[1]
        valW = w * 20.0 / 400.0
        valH = h * 20.0 / 400.0
        glViewport(int(s), 0, int(w), int(h))
        glOrtho(-valW, valW, -valH, valH, 40000, -40000)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        zoom = self.zoom
        scaling = LotEditorWin.zoomScale[zoom] * self.viewScale
        glScalef(scaling, -scaling, scaling)
        rot2D = -self.rotation * 90.0
        glTranslate(-self.posx, -self.posy, -self.posz)
        glRotatef(rot2D, 0, 0, 1)
        px, py, pz = gluUnProject(self.glCanvas2D.mouseX, h - self.glCanvas2D.mouseY, 0)
        lx = self.lotSizeXOffset
        ly = self.lotSizeYOffset
        px += lx
        py += ly
        bUnderMouse = False
        glColor3f(1, 1, 1)
        self.highlighted = []
        self.quadHighs = []
        if self.modeDisplay & MODE_BASETEX_ONLY and self._is_layer_visible('2d', LAYER_BASE):
            for texData in self.texBases:
                if self.modeEdit == MODE_EDIT_BASETEX:
                    minx = texData[0] * 16
                    miny = texData[1] * 16
                    maxx = texData[0] * 16 + 16
                    maxy = texData[1] * 16 + 16
                    if self.dragSelect and QuadInQuad([minx, miny, maxx, maxy], self.dragQuad):
                        self.highlighted.append(texData[4])
                        self.quadHighs.append([minx, miny, maxx, maxy])
                    if not self.dragSelect and px >= minx and px <= maxx and py >= miny and py <= maxy:
                        bUnderMouse = True
                        self.SetStatusText(hex2str(texData[3]), 5)
                        self.quadHighs = [[minx, miny, maxx, maxy]]
                        self.highlighted = [texData[4]]
                self.DrawQuad(texData[0], texData[1], texData[2], texData[3], False)

        if self.modeDisplay & MODE_OVERTEX_ONLY and self._is_layer_visible('2d', LAYER_OVERLAY):
            for texData in self.texOverlays:
                if self.modeEdit == MODE_EDIT_OVERTEX:
                    minx = texData[0] * 16
                    miny = texData[1] * 16
                    maxx = texData[0] * 16 + 16
                    maxy = texData[1] * 16 + 16
                    if self.dragSelect and QuadInQuad([minx, miny, maxx, maxy], self.dragQuad):
                        self.highlighted.append(texData[4])
                        self.quadHighs.append([minx, miny, maxx, maxy])
                    if not self.dragSelect and px >= minx and px <= maxx and py >= miny and py <= maxy:
                        bUnderMouse = True
                        self.SetStatusText(hex2str(texData[3]), 5)
                        self.highlighted = [texData[4]]
                        self.quadHighs = [[minx, miny, maxx, maxy]]
                self.DrawQuad(texData[0], texData[1], texData[2], texData[3], True)

        if self.modeDisplay & MODE_CONSTRAINT_ONLY:
            constraint_layers = (
                (True, self.waters, LAYER_WATER),
                (False, self.lands, LAYER_LAND),
            )
            for is_water, constraints, layer_key in constraint_layers:
                if not self._is_layer_visible('2d', layer_key):
                    continue
                for texData in constraints:
                    if self.modeEdit == MODE_EDIT_CONSTRAINT:
                        minx = texData[0] * 16
                        miny = texData[1] * 16
                        maxx = minx + 16
                        maxy = miny + 16
                        if self.dragSelect and QuadInQuad([minx, miny, maxx, maxy], self.dragQuad):
                            self.highlighted.append(texData[4])
                            self.quadHighs.append([minx, miny, maxx, maxy])
                        if not self.dragSelect and px >= minx and px <= maxx and py >= miny and py <= maxy:
                            bUnderMouse = True
                            self.SetStatusText(LEXConstraintWater if is_water else LEXConstraintLand, 5)
                            self.highlighted = [texData[4]]
                            self.quadHighs = [[minx, miny, maxx, maxy]]
                    if is_water:
                        glColor3f(0.2, 0.2, 0.8)
                    else:
                        glColor3f(0.8, 0.5, 0.2)
                    self.DrawQuad(texData[0], texData[1], texData[2], 1802442183, True)

        if self.modeDisplay & MODE_TE_ONLY and self._is_layer_visible('2d', LAYER_TRANSIT):
            for texData in self.te:
                minx = texData[0] * 16
                miny = texData[1] * 16
                maxx = minx + 16
                maxy = miny + 16
                if self.modeEdit == MODE_EDIT_TRANSIT:
                    if self.dragSelect and QuadInQuad([minx, miny, maxx, maxy], self.dragQuad):
                        self.highlighted.append(texData[5])
                        self.quadHighs.append([minx, miny, maxx, maxy])
                    if not self.dragSelect and px >= minx and px <= maxx and py >= miny and py <= maxy:
                        bUnderMouse = True
                        self.SetStatusText('%s %s' % (network_label(texData[3][0]), mask_label(texData[4])), 5)
                        self.highlighted = [texData[5]]
                        self.quadHighs = [[minx, miny, maxx, maxy]]
                draw_transit_overlay(self, texData, self.modeEdit == MODE_EDIT_TRANSIT, rot2D, scaling)

        glColor3f(1, 1, 1)
        if self._is_layer_visible('2d', LAYER_ROAD_EDGES):
            if self.exemplar.GetProp(1246398704)[0] & 8:
                for x in range(self.exemplar.GetProp(2297284496)[0]):
                    self.DrawQuad(x, self.exemplar.GetProp(2297284496)[1], 1, 641146880, True)

            if self.exemplar.GetProp(1246398704)[0] & 1:
                for y in range(self.exemplar.GetProp(2297284496)[1]):
                    self.DrawQuad(-1, y, 0, 641146880, True)

            if self.exemplar.GetProp(1246398704)[0] & 4:
                for y in range(self.exemplar.GetProp(2297284496)[1]):
                    self.DrawQuad(self.exemplar.GetProp(2297284496)[0], y, 0, 641146880, True)

        if self.snapSize != 0 and self._is_layer_visible('2d', LAYER_SNAP_GRID):
            with pushed_modelview_matrix():
                glTranslate(-self.lotSizeXOffset, -self.lotSizeYOffset, 0)
                glColor3f(0.5, 0, 0.2)
                glEnableClientState(GL_VERTEX_ARRAY)
                glVertexPointer(2, GL_FLOAT, 0, self.snapGrids)
                glDrawArrays(GL_LINES, 0, self.nbSnapLines)
                glDisableClientState(GL_VERTEX_ARRAY)
        if self.modeDisplay & MODE_BUILDING_ONLY and self._is_layer_visible('2d', LAYER_BUILDING):
            if self.building:
                minx = ToCoord(self.building[6])
                miny = ToCoord(self.building[7])
                maxx = ToCoord(self.building[8])
                maxy = ToCoord(self.building[9])
                if self.modeEdit == MODE_EDIT_BUILDING:
                    if self.dragSelect and QuadInQuad([minx, miny, maxx, maxy], self.dragQuad):
                        self.highlighted.append(self.building[11])
                        self.quadHighs.append([minx, miny, maxx, maxy])
                    if not self.dragSelect and px >= minx and px <= maxx and py >= miny and py <= maxy:
                        bUnderMouse = True
                        self.highlighted = [self.building[11]]
                        self.quadHighs = [[minx, miny, maxx, maxy]]
                        self.SetStatusText(hex2str(self.building[12]) + ':' + self.building[-1], 5)
                alphaValue = 0.1
                if self.modeEdit == MODE_EDIT_BUILDING:
                    alphaValue = 0.9
                self.DrawQuadColor(self.building[2], minx, miny, maxx, maxy, (0, 0, 1, alphaValue), self.buildingViewer == [] or self.buildingViewer[self.currentBuilding] is None)
                if self.building[4] != 0 and self.building[11] in self.selected:
                    self.glCanvas2D.text_2d(ToCoord(self.building[3]) - lx, ToCoord(self.building[5]) - ly, '%.02f' % ToCoord(self.building[4]), rot2D, scaling)
        if self.modeDisplay & MODE_PROP_ONLY and self._is_layer_visible('2d', LAYER_PROPS):
            for prop, propViewer in zip(self.props, self.propViewers):
                minx = ToCoord(prop[6])
                miny = ToCoord(prop[7])
                maxx = ToCoord(prop[8])
                maxy = ToCoord(prop[9])
                if self.modeEdit == MODE_EDIT_PROP:
                    if self.dragSelect and QuadInQuad([minx, miny, maxx, maxy], self.dragQuad):
                        self.highlighted.append(prop[11])
                        self.quadHighs.append([minx, miny, maxx, maxy])
                    if not self.dragSelect and px >= minx and px <= maxx and py >= miny and py <= maxy:
                        bUnderMouse = True
                        self.highlighted = [prop[11]]
                        self.quadHighs = [[minx, miny, maxx, maxy]]
                        self.SetStatusText(hex2str(prop[12]) + ':' + prop[-1] + ' ' + hex2str(prop[11]), 5)
                alphaValue = 0.1
                if self.modeEdit == MODE_EDIT_PROP:
                    alphaValue = 0.5
                self.DrawQuadColor(prop[2], minx, miny, maxx, maxy, (1, 1, 0, alphaValue), propViewer is None)
                if prop[4] != 0 and prop[11] in self.selected:
                    self.glCanvas2D.text_2d(ToCoord(prop[3]) - lx, ToCoord(prop[5]) - ly, '%.02f' % ToCoord(prop[4]), rot2D, scaling)

        if self.modeDisplay & MODE_FLORA_ONLY and self._is_layer_visible('2d', LAYER_FLORA):
            for prop in self.floras:
                minx = ToCoord(prop[6])
                miny = ToCoord(prop[7])
                maxx = ToCoord(prop[8])
                maxy = ToCoord(prop[9])
                if self.modeEdit == MODE_EDIT_FLORA:
                    if self.dragSelect and QuadInQuad([minx, miny, maxx, maxy], self.dragQuad):
                        self.highlighted.append(prop[11])
                        self.quadHighs.append([minx, miny, maxx, maxy])
                    if not self.dragSelect and px >= minx and px <= maxx and py >= miny and py <= maxy:
                        bUnderMouse = True
                        self.SetStatusText(hex2str(prop[12]) + ':' + prop[-1], 5)
                        self.quadHighs = [[minx, miny, maxx, maxy]]
                        self.highlighted = [prop[11]]
                self.DrawQuadColor(prop[2], minx, miny, maxx, maxy, (0, 1.0, 0, 0.9), False)
                if prop[4] != 0 and prop[11] in self.selected:
                    self.glCanvas2D.text_2d(ToCoord(prop[3]) - lx, ToCoord(prop[5]) - ly, '%.02f' % ToCoord(prop[4]), rot2D, scaling)

        if self._is_layer_visible('2d', LAYER_SELECTION):
            self.DrawQuadsHighLight(self.quadHighs)
            self.DrawQuadsHighLight(self.quadSelected, (1, 1, 1))
            if self.dragQuad is not None:
                self.DrawHighLight(self.dragQuad[0], self.dragQuad[1], self.dragQuad[2], self.dragQuad[3], (1,
                                                                                                            1,
                                                                                                            1))
        if self._is_layer_visible('2d', LAYER_MISSING):
            with pushed_modelview_matrix():
                glTranslate(-self.lotSizeXOffset, -self.lotSizeYOffset, 0)
                glColor3f(1, 0, 0)
                glEnableClientState(GL_VERTEX_ARRAY)
                glVertexPointer(2, GL_FLOAT, 0, numpy.asarray(self.missingLines, 'f').tobytes())
                glDrawArrays(GL_LINES, 0, len(self.missingLines))
                glDisableClientState(GL_VERTEX_ARRAY)
        if self._is_layer_visible('2d', LAYER_CARDINALS):
            self.DrawCardinalLabels(rot2D, scaling)
        glMatrixMode(GL_TEXTURE)
        glLoadIdentity()
        if not bUnderMouse:
            self.SetStatusText('', 5)
        return

    def DrawCardinalLabels(self, rot2D, scaling):
        """Paint N/E/S/W markers just outside the lot frame in the 2D view.

        The labels sit at the lot-edge midpoints in (centred) lot space, so
        they rotate with the lot as the view turns and always point at the
        true cardinal directions: North is the far edge, South the near edge.
        """
        x = self.lotSizeXOffset
        y = self.lotSizeYOffset
        if not x or not y:
            return
        margin = 6.0
        glColor3f(1.0, 0.85, 0.2)
        for label, lx, ly in (
            (LEXFacingNorth, -1.0, y + margin),
            (LEXFacingSouth, -1.0, -y - margin),
            (LEXFacingEast, x + margin, -1.0),
            (LEXFacingWest, -x - margin, -1.0),
        ):
            self.glCanvas2D.text_2d(lx, ly, label, rot2D, scaling)

    def DrawBackGround2(self, x=0, y=0):
        if not getattr(self, 'BackTextures', None):
            return
        zoom = self.zoom
        scaling = LotEditorWin.zoomScale3D[zoom]
        if zoom == 5:
            zoom = 4
        if self.BackTextures[zoom] is not None and self.BackTextureSizes[zoom] is not None:
            glDisable(GL_DEPTH_TEST)
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, self.BackTextures[zoom])
            glDisable(GL_BLEND)
            glDisable(GL_ALPHA_TEST)
            offsetX = x - self.lotSizeXOffset
            offsetY = y - self.lotSizeYOffset
            with pushed_modelview_matrix():
                env_light = self._lot_environment_light()
                glColor3f(env_light[0], env_light[1], env_light[2])
                glRotatef(-self.ry, 0.0, 1.0, 0.0)
                glRotatef(self.rx, 1.0, 0.0, 0.0)
                scales = [
                 9.2, 4.6, 2.3, 1.0, 1.0 / 2.0]
                scale = scales[zoom]
                glScalef(scale, scale, -scale)
                glTranslate(offsetX, 0, offsetY)
                glMatrixMode(GL_TEXTURE)
                glLoadIdentity()
                glMatrixMode(GL_MODELVIEW)
                glBegin(GL_QUADS)
                w = self.BackTextureSizes[zoom][0] / 3.5
                h = self.BackTextureSizes[zoom][1] / 3.5
                glTexCoord2i(0, 1)
                glVertex3f(0, -0.1, 0)
                glTexCoord2i(0, 0)
                glVertex3f(0, -0.1, h)
                glTexCoord2i(1, 0)
                glVertex3f(w, -0.1, h)
                glTexCoord2i(1, 1)
                glVertex3f(w, -0.1, 0)
                glEnd()
                glColor3f(1.0, 1.0, 1.0)
        return

    def DrawQuad3D(self, x, y, flag, texID, bAlpha):
        glEnable(GL_TEXTURE_2D)
        zoom = self.zoom
        if zoom == 5:
            zoom = 4
        try:
            glBindTexture(GL_TEXTURE_2D, self.textures[texID][0][zoom])
        except Exception:
            return

        if bAlpha:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        else:
            glDisable(GL_BLEND)
        glDisable(GL_ALPHA_TEST)
        offsetX = x * 16 - self.lotSizeXOffset
        offsetY = y * 16 - self.lotSizeYOffset
        tex_coords = texture_coords_for_flag(flag)
        with pushed_modelview_matrix():
            env_light = self._lot_environment_light()
            glColor3f(env_light[0], env_light[1], env_light[2])
            glTranslate(offsetX, 0, offsetY)
            glMatrixMode(GL_TEXTURE)
            glLoadIdentity()
            glMatrixMode(GL_MODELVIEW)
            glBegin(GL_QUADS)
            glTexCoord2f(*tex_coords[0])
            glVertex3f(0, 0, 16)
            glTexCoord2f(*tex_coords[1])
            glVertex3f(0, 0, 0)
            glTexCoord2f(*tex_coords[2])
            glVertex3f(16, 0, 0)
            glTexCoord2f(*tex_coords[3])
            glVertex3f(16, 0, 16)
            glEnd()
            glColor3f(1.0, 1.0, 1.0)

    def DrawModel(self, rtk, resource, rot2D, rot, rotFlag, zoom):
        if resource is None:
            return
        if resource.viewingData == []:
            return
        # Props with exemplar property 0x49C9C93C ("Nighttime State Change")
        # render a different model state at night. The property's value is the
        # destination state index; fall through to state 0 if it points out
        # of range (e.g. an RKT0/1 prop with only one viewing entry).
        state_idx = 0
        if getattr(self, 'nightMode', False):
            night_state = int(getattr(resource, 'night_state', 0) or 0)
            if 0 < night_state < len(resource.viewingData):
                state_idx = night_state
        what = resource.viewingData[state_idx]
        shader_program = self._ensure_s3d_shader_program()
        lighting_state = self._lot_lighting_state(getattr(resource, 'lighting_exemplar', None))
        if what.__class__ == SC4Model:
            rotMapping = [
             180, -90, 0, 90]
            glRotatef(-rotMapping[rotFlag], 0, 1, 0)
            glTranslate(rtk[0], rtk[1], rtk[2])
            glRotatef(rotMapping[rotFlag], 0, 1, 0)
            glRotatef(-rot2D, 0, 1, 0)
            what.s3dMeshes[zoom][rot].draw(self.s3DTexturesHolder, shader_program, lighting_state)
        elif what.__class__ == SC4Model1MeshPerZoom:
            what.s3dMeshes[zoom].draw(self.s3DTexturesHolder, shader_program, lighting_state)
        elif what.__class__ == SC4ModelMesh:
            rotMapping = [
             180, -90, 0, 90]
            glRotatef(rotMapping[rotFlag], 0, 1, 0)
            what.mainMesh.draw(self.s3DTexturesHolder, shader_program, lighting_state)
        elif what.__class__ == ATC:
            glDisable(GL_DEPTH_TEST)
            rotMapping = [1, 0, 3, 2]
            scaleATC = LotEditorWin.zoomScaleATC[zoom]
            modelview = numpy.array(glGetFloatv(GL_MODELVIEW_MATRIX), dtype=numpy.float32).reshape(16)
            modelview[0] = 1
            modelview[1] = 0
            modelview[2] = 0
            modelview[4] = 0
            modelview[5] = 1
            modelview[6] = 0
            modelview[8] = 0
            modelview[9] = 0
            modelview[10] = -1
            glLoadMatrixf(modelview)
            glScalef(1 / 7.0, 1 / 7.0, 1 / 7.0)
            glScalef(0.5, 0.5, 0.5)
            if what.draw_le(zoom, rotMapping[rot]):
                what.DrawGL(self.s3DTexturesHolder)
            glEnable(GL_DEPTH_TEST)
        return

    def Draw3DBackdrop(self, valW, valH):
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glDisable(GL_ALPHA_TEST)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_BLEND)
        env_light = self._lot_environment_light()
        glBegin(GL_QUADS)
        glColor3f(0.15 * env_light[0], 0.17 * env_light[1], 0.20 * env_light[2])
        glVertex3f(-valW, -valH, 0)
        glVertex3f(valW, -valH, 0)
        glColor3f(0.36 * env_light[0], 0.39 * env_light[1], 0.42 * env_light[2])
        glVertex3f(valW, valH, 0)
        glVertex3f(-valW, valH, 0)
        glEnd()
        glColor3f(1.0, 1.0, 1.0)

    def Draw3D(self):
        self.glCanvas2D.SetCurrent()
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        zoom = self.zoom
        if zoom == 5:
            zoom = 4
        if zoom == 4 or zoom == 3:
            angleX = 45
        elif zoom == 2:
            angleX = 40
        elif zoom == 1:
            angleX = 35
        else:
            angleX = 30
        size = self.size = self.glCanvas2D.GetClientSize()
        if self.panel == 3:
            w = self.size[0] // 2
        elif self.panel == 1:
            w = self.size[0]
        else:
            return
        h = self.size[1]
        valW = w * 2.0 / 60.0
        valH = h * 2.0 / 60.0
        glViewport(0, 0, int(w), int(h))
        glOrtho(-valW, valW, -valH, valH, 40000, -40000)
        self.Draw3DBackdrop(valW, valH)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        rotation = self.rotation
        rot2D = rotation * 90.0
        self.rx = angleX
        self.ry = rot2D - 22.5
        self.rz = 0
        scaling = LotEditorWin.zoomScale3D[zoom]
        glScalef(scaling, scaling, -scaling)
        glTranslate(-self.pos3Dx, -self.pos3Dy, -self.pos3Dz)
        glRotatef(self.rx, 1.0, 0.0, 0.0)
        glRotatef(self.ry, 0.0, 1.0, 0.0)
        glColor3f(1.0, 1.0, 1.0)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        # Draw the optional ground background (offset by the user's Shift+drag
        # position), then re-enable depth testing -- DrawBackGround2 disables
        # it -- for the lot's own texture quads.
        background_drawn = self._is_layer_visible('3d', LAYER_BACKGROUND)
        if background_drawn:
            self.DrawBackGround2(self.BackPosx, self.BackPosy)
        glEnable(GL_DEPTH_TEST)
        if self._is_layer_visible('3d', LAYER_BASE):
            for texData in self.texBases:
                self.DrawQuad3D(texData[0], texData[1], texData[2], texData[3], False)

        if self._is_layer_visible('3d', LAYER_OVERLAY):
            for texData in self.texOverlays:
                self.DrawQuad3D(texData[0], texData[1], texData[2], texData[3], True)

        # Road edge overlays clash with a custom ground background, so skip
        # drawing them while background mode is on.
        if self._is_layer_visible('3d', LAYER_ROAD_EDGES) and not background_drawn:
            if self.exemplar.GetProp(1246398704)[0] & 8:
                for x in range(self.exemplar.GetProp(2297284496)[0]):
                    self.DrawQuad3D(x, self.exemplar.GetProp(2297284496)[1], 1, 641146880, True)

            if self.exemplar.GetProp(1246398704)[0] & 1:
                for y in range(self.exemplar.GetProp(2297284496)[1]):
                    self.DrawQuad3D(-1, y, 0, 641146880, True)

            if self.exemplar.GetProp(1246398704)[0] & 4:
                for y in range(self.exemplar.GetProp(2297284496)[1]):
                    self.DrawQuad3D(self.exemplar.GetProp(2297284496)[0], y, 0, 641146880, True)

        glMatrixMode(GL_TEXTURE)
        glLoadIdentity()
        glEnable(GL_DEPTH_TEST)
        glMatrixMode(GL_MODELVIEW)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glEnable(GL_TEXTURE_2D)
        glColor3f(1.0, 1.0, 1.0)
        rotMapping = [2, 1, 0, 3]
        lotSizeXOver = self.lotSizeXOver
        lotSizeYOver = self.lotSizeYOver
        if self._is_layer_visible('3d', LAYER_BUILDING):
            try:
                if self.buildingViewer[self.currentBuilding] is not None:
                    with pushed_modelview_matrix():
                        offsetX = ToCoord(self.building[3]) - lotSizeXOver / 2
                        offsetZ = ToCoord(self.building[5]) - lotSizeYOver / 2
                        offsetY = 0
                        if self.building[12] in self.rtk4Offsets.keys():
                            rtk4 = self.rtk4Offsets[self.building[12]]
                        else:
                            rtk4 = (0, 0, 0)
                        glTranslate(offsetX, offsetY + ToCoord(self.building[4]), offsetZ)
                        self.DrawModel(rtk4, self.buildingViewer[self.currentBuilding], rot2D, (rotation + rotMapping[self.building[2]]) % 4, self.building[2], zoom)
            except IndexError:
                pass

        afters = []
        afterViewers = []
        if self._is_layer_visible('3d', LAYER_PROPS):
            for prop, propViewer in zip(self.props, self.propViewers):
                tempViewer = propViewer
                if tempViewer is None:
                    tempViewer = self.LEAnimMissing
                if tempViewer.viewingData == []:
                    pass
                else:
                    what = tempViewer.viewingData[0]
                    if what.__class__ == ATC:
                        afters.append(prop)
                        afterViewers.append(tempViewer)
                    else:
                        with pushed_modelview_matrix():
                            offsetX = ToCoord(prop[3]) - lotSizeXOver / 2
                            offsetZ = ToCoord(prop[5]) - lotSizeYOver / 2
                            offsetY = 0
                            if prop[12] in self.rtk4Offsets.keys():
                                rtk4 = self.rtk4Offsets[prop[12]]
                            else:
                                rtk4 = (0, 0, 0)
                            glTranslate(offsetX, offsetY + ToCoord(prop[4]), offsetZ)
                            self.DrawModel(rtk4, tempViewer, rot2D, (rotation + rotMapping[prop[2]]) % 4, prop[2], zoom)

        if self._is_layer_visible('3d', LAYER_FLORA):
            for prop, propViewer in zip(self.floras, self.floraViewers):
                tempViewer = propViewer
                if tempViewer is None:
                    tempViewer = self.LEAnimMissing
                if tempViewer.viewingData == []:
                    pass
                else:
                    what = tempViewer.viewingData[0]
                    if what.__class__ == ATC:
                        afters.append(prop)
                        afterViewers.append(tempViewer)
                    else:
                        with pushed_modelview_matrix():
                            offsetX = ToCoord(prop[3]) - lotSizeXOver / 2
                            offsetZ = ToCoord(prop[5]) - lotSizeYOver / 2
                            offsetY = 0
                            if prop[12] in self.rtk4Offsets.keys():
                                rtk4 = self.rtk4Offsets[prop[12]]
                            else:
                                rtk4 = (0, 0, 0)
                            glTranslate(offsetX, offsetY + ToCoord(prop[4]), offsetZ)
                            self.DrawModel(rtk4, tempViewer, rot2D, (rotation + rotMapping[prop[2]]) % 4, prop[2], zoom)

        for prop, propViewer in zip(afters, afterViewers):
            with pushed_modelview_matrix():
                offsetX = ToCoord(prop[3]) - lotSizeXOver / 2
                offsetZ = ToCoord(prop[5]) - lotSizeYOver / 2
                offsetY = 0
                if prop[12] in self.rtk4Offsets.keys():
                    rtk4 = self.rtk4Offsets[prop[12]]
                else:
                    rtk4 = (0, 0, 0)
                glTranslate(offsetX, offsetY + ToCoord(prop[4]), offsetZ)
                self.DrawModel(rtk4, propViewer, rot2D, (rotation + rotMapping[prop[2]]) % 4, prop[2], zoom)

        glColor3f(1.0, 1.0, 1.0)
        return

    def Save(self):
        size = self.glCanvas2D.GetClientSize()
        glReadBuffer(GL_FRONT)
        w = (size[0] // 2) & 4294967280
        h = size[1] & 4294967280
        data = glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE)
        decal = len(data) - w * h * 3
        if decal == h * 2:
            data = data[3:]
        image = Image.frombytes('RGB', (w, h), data)
        image = image.transpose(Image.FLIP_TOP_BOTTOM)
        image = image.resize((44, 44))
        return image

    def SetMatForUnproj(self):
        glMatrixMode(GL_TEXTURE)
        glLoadIdentity()
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        size = self.size = self.glCanvas2D.GetClientSize()
        if self.panel == 3:
            w = self.size[0] // 2
            s = w
        elif self.panel == 2:
            w = self.size[0]
            s = 0
        else:
            return None
        h = self.size[1]
        valW = w * 20.0 / 400.0
        valH = h * 20.0 / 400.0
        glViewport(int(s), 0, int(w), int(h))
        glOrtho(-valW, valW, -valH, valH, 40000, -40000)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        zoom = self.zoom
        scaling = LotEditorWin.zoomScale[zoom] * self.viewScale
        glScalef(scaling, -scaling, scaling)
        rot2D = -self.rotation * 90.0
        glTranslate(-self.posx, -self.posy, -self.posz)
        glRotatef(rot2D, 0, 0, 1)
        return None

    def OnKeyMove(self, evt):
        if self.modeEdit not in [MODE_EDIT_PROP, MODE_EDIT_FLORA, MODE_EDIT_BUILDING]:
            return
        if self.selected:
            self._push_undo()
        dx = 0
        dy = 0
        dz = 0
        rot = self.rotation
        amount = [
         -0.1, 0, 0.1, 0, -0.1, 0, 0.1, 0]
        if evt.GetKeyCode() == 314:
            dx = amount[rot]
            dy = amount[rot + 3]
        if evt.GetKeyCode() == 315:
            if evt.ControlDown():
                dz = 1
            else:
                dy = amount[rot]
                dx = amount[rot + 1]
        if evt.GetKeyCode() == 316:
            dx = amount[rot + 2]
            dy = amount[rot + 1]
        if evt.GetKeyCode() == 317:
            if evt.ControlDown():
                dz = -1
            else:
                dy = amount[rot + 2]
                dx = amount[rot + 3]
        if evt.ShiftDown():
            dx *= 10.0
            dy *= 10.0
            dz *= 10
        self.MoveByAmount(dx, dy, dz)
        self.OnMouseUp(None)
        return

    def FindSnapingPos(self, boxes, snapSize):

        def Distance(p1, p2):
            dx = abs(p1[0] - p2[0])
            dy = abs(p1[1] - p2[1])
            return math.sqrt(dx * dx + dy * dy)

        def Delta(p1, p2):
            return (
             (p1[0] - p2[0]) / 10.0, (p1[1] - p2[1]) / 10.0)

        xCenter = boxes[0] * 10
        yCenter = boxes[2] * 10
        xmin = boxes[3] * 10
        ymin = boxes[4] * 10
        xmax = boxes[5] * 10
        ymax = boxes[6] * 10
        snapSize *= 10
        snapxCenter = round(xCenter / snapSize) * snapSize
        snapyCenter = round(yCenter / snapSize) * snapSize
        left = round(xmin / snapSize) * snapSize
        right = round(xmax / snapSize) * snapSize
        top = round(ymin / snapSize) * snapSize
        bottom = round(ymax / snapSize) * snapSize
        centerPointSnap = (
         snapxCenter, snapyCenter)
        leftTopPointSnap = (left, top)
        leftBottomPointSnap = (left, bottom)
        rightTopPointSnap = (right, top)
        rightBottomPointSnap = (right, bottom)
        centerPoint = (
         xCenter, yCenter)
        leftTopPoint = (xmin, ymin)
        leftBottomPoint = (xmin, ymax)
        rightTopPoint = (xmax, ymin)
        rightBottomPoint = (xmax, ymax)
        distCenter = Distance(centerPointSnap, centerPoint)
        distLT = Distance(leftTopPointSnap, leftTopPoint)
        distLB = Distance(leftBottomPointSnap, leftBottomPoint)
        distRT = Distance(rightTopPointSnap, rightTopPoint)
        distRB = Distance(rightBottomPointSnap, rightBottomPoint)
        dist = min(distCenter, distLT, distLB, distRT, distRB)
        if dist == distCenter:
            return Delta(centerPointSnap, centerPoint)
        if dist == distLT:
            return Delta(leftTopPointSnap, leftTopPoint)
        if dist == distLB:
            return Delta(leftBottomPointSnap, leftBottomPoint)
        if dist == distRT:
            return Delta(rightTopPointSnap, rightTopPoint)
        if dist == distRB:
            return Delta(rightBottomPointSnap, rightBottomPoint)

    def GroupBBox(self):
        xCenter = 0
        yCenter = 0
        xMin = None
        yMin = None
        xMax = None
        yMax = None
        for id, q in zip(self.selected, self.quadSelected):
            for lcp in range(2297284864, 2297286144):
                values = self.exemplar.GetProp(lcp)
                if values is None:
                    break
                if values[11] == id:
                    if xMin is None:
                        xMin = ToCoord(values[6])
                    else:
                        xMin = min(xMin, ToCoord(values[6]))
                    if xMax is None:
                        xMax = ToCoord(values[8])
                    else:
                        xMax = max(xMax, ToCoord(values[8]))
                    if yMin is None:
                        yMin = ToCoord(values[7])
                    else:
                        yMin = min(yMin, ToCoord(values[7]))
                    if yMax is None:
                        yMax = ToCoord(values[9])
                    else:
                        yMax = max(yMax, ToCoord(values[9]))
                    break

        xCenter = (xMin + xMax) / 2
        yCenter = (yMin + yMax) / 2
        return [
         xCenter, 0, yCenter, xMin, yMin, xMax, yMax]

    def MoveByAmount(self, dx, dy, dz):
        lotSizeXOver = self.exemplar.GetProp(2297284496)[0]
        lotSizeYOver = self.exemplar.GetProp(2297284496)[1]
        bbox = []
        dSx = 0
        dSy = 0
        if self.snapSize != 0:
            if self.modeEdit in [MODE_EDIT_BUILDING, MODE_EDIT_PROP, MODE_EDIT_FLORA]:
                bbox = self.GroupBBox()
                bbox[0] += dx
                bbox[2] += dy
                bbox[3] += dx
                bbox[4] += dy
                bbox[5] += dx
                bbox[6] += dy
                dSx, dSy = self.FindSnapingPos(bbox, self.snapSize)
        for id, q in zip(self.selected, self.quadSelected):
            oldq = q[:]
            if self.modeEdit == MODE_EDIT_BASETEX or self.modeEdit == MODE_EDIT_OVERTEX:
                pass
            else:
                q[0] += dx
                q[2] += dx
                q[1] += dy
                q[3] += dy
            for lcp in range(2297284864, 2297286144):
                values = self.exemplar.GetProp(lcp)
                if values is None:
                    break
                if values[11] == id:
                    oldValues = values[:]
                    if dz > 0:
                        values[4] = ToUnsigned(values[4]) + dz * 6553
                    if dz < 0:
                        values[4] = ToUnsigned(values[4]) + dz * 6553
                        if ToCoord(values[4]) < 0:
                            values[4] = 0
                    values[3] = ToUnsigned(int((ToCoord(values[3]) + dx) * 65536))
                    values[5] = ToUnsigned(int((ToCoord(values[5]) + dy) * 65536))
                    values[6] = ToUnsigned(int((ToCoord(values[6]) + dx) * 65536))
                    values[7] = ToUnsigned(int((ToCoord(values[7]) + dy) * 65536))
                    values[8] = ToUnsigned(int((ToCoord(values[8]) + dx) * 65536))
                    values[9] = ToUnsigned(int((ToCoord(values[9]) + dy) * 65536))
                    if values[0] == 0:
                        if ToTile(values[6]) < 0:
                            values[:] = oldValues
                            q[:] = oldq
                        if ToTile(values[7]) < 0:
                            values[:] = oldValues
                            q[:] = oldq
                        if ToTile(values[8]) > lotSizeXOver:
                            values[:] = oldValues
                            q[:] = oldq
                        if ToTile(values[9]) > lotSizeYOver:
                            values[:] = oldValues
                            q[:] = oldq
                        self.building[:-1] = values[:]
                        if self.snapSize != 0:
                            q[0] = ToCoord(values[6]) + dSx
                            q[1] = ToCoord(values[7]) + dSy
                            q[2] = ToCoord(values[8]) + dSx
                            q[3] = ToCoord(values[9]) + dSy
                            v = values[:]
                            v[3] = ToUnsigned((q[0] + q[2]) / 2 * 65536)
                            v[5] = ToUnsigned((q[1] + q[3]) / 2 * 65536)
                            v[6] = ToUnsigned(q[0] * 65536)
                            v[7] = ToUnsigned(q[1] * 65536)
                            v[8] = ToUnsigned(q[2] * 65536)
                            v[9] = ToUnsigned(q[3] * 65536)
                            self.building[:-1] = v[:]
                    elif values[0] == 1 or values[0] == 4:
                        if ToTile(values[3]) < 0:
                            values[:] = oldValues
                            q[:] = oldq
                        if ToTile(values[5]) < 0:
                            values[:] = oldValues
                            q[:] = oldq
                        if ToTile(values[3]) > lotSizeXOver:
                            values[:] = oldValues
                            q[:] = oldq
                        if ToTile(values[5]) > lotSizeYOver:
                            values[:] = oldValues
                            q[:] = oldq
                        what = self.props
                        if values[0] == 4:
                            what = self.floras
                        for prop in what:
                            if prop[11] == id:
                                prop[:13] = values
                                break

                        if self.snapSize != 0:
                            q[0] = ToCoord(values[6]) + dSx
                            q[1] = ToCoord(values[7]) + dSy
                            q[2] = ToCoord(values[8]) + dSx
                            q[3] = ToCoord(values[9]) + dSy
                            v = values[:]
                            v[3] = ToUnsigned((q[0] + q[2]) / 2 * 65536)
                            v[5] = ToUnsigned((q[1] + q[3]) / 2 * 65536)
                            v[6] = ToUnsigned(q[0] * 65536)
                            v[7] = ToUnsigned(q[1] * 65536)
                            v[8] = ToUnsigned(q[2] * 65536)
                            v[9] = ToUnsigned(q[3] * 65536)
                            for prop in what:
                                if prop[11] == id:
                                    prop[:13] = v
                                    break

                    elif values[0] == 2:
                        # Base/overlay textures are 1x1 tiles and must stay
                        # aligned to the 16m grid: snap the (already moved)
                        # centre to the centre of the tile it now sits in and
                        # rebuild the 16x16m bounding box from it.
                        cx = (math.floor(ToCoord(values[3]) / 16.0) + 0.5) * 16.0
                        cy = (math.floor(ToCoord(values[5]) / 16.0) + 0.5) * 16.0
                        values[3] = ToUnsigned(int(cx * 65536))
                        values[5] = ToUnsigned(int(cy * 65536))
                        values[6] = ToUnsigned(int((cx - 8.0) * 65536))
                        values[7] = ToUnsigned(int((cy - 8.0) * 65536))
                        values[8] = ToUnsigned(int((cx + 8.0) * 65536))
                        values[9] = ToUnsigned(int((cy + 8.0) * 65536))

                        def UpdateTexData(what):
                            for texData in what:
                                if texData[4] == id:
                                    texData[0] = ToTileOrigin(values[3])
                                    texData[1] = ToTileOrigin(values[5])
                                    minx = texData[0] * 16
                                    miny = texData[1] * 16
                                    maxx = texData[0] * 16 + 16
                                    maxy = texData[1] * 16 + 16
                                    what.remove(texData)
                                    what.append(texData)
                                    return [
                                     minx, miny, maxx, maxy]

                            return None

                        z = UpdateTexData(self.texBases)
                        if z is None:
                            q[0], q[1], q[2], q[3] = UpdateTexData(self.texOverlays)
                        else:
                            q[0], q[1], q[2], q[3] = z
                    elif values[0] == TRANSIT_OBJECT_TYPE:
                        cx = (math.floor(ToCoord(values[3]) / 16.0) + 0.5) * 16.0
                        cy = (math.floor(ToCoord(values[5]) / 16.0) + 0.5) * 16.0
                        tile_x = int(math.floor(cx / 16.0))
                        tile_y = int(math.floor(cy / 16.0))
                        if tile_x < 0 or tile_y < 0 or tile_x >= lotSizeXOver or tile_y >= lotSizeYOver:
                            values[:] = oldValues
                            q[:] = oldq
                        else:
                            ensure_transit_values(values)
                            values[3] = ToUnsigned(int(cx * 65536))
                            values[5] = ToUnsigned(int(cy * 65536))
                            values[6] = ToUnsigned(int((cx - 8.0) * 65536))
                            values[7] = ToUnsigned(int((cy - 8.0) * 65536))
                            values[8] = ToUnsigned(int((cx + 8.0) * 65536))
                            values[9] = ToUnsigned(int((cy + 8.0) * 65536))
                            q[:] = quad_for_values(values)
                            update_cached_transit(self.te, values)
                    break

        return

    def OnMouseMotion(self, evt):
        self.glCanvas2D.on_mouse_motion(evt)
        if evt.ControlDown() and not self.dragSelect:
            return
        if evt.Dragging() and evt.LeftIsDown():
            if evt.ShiftDown() and self.modeEdit == MODE_EDIT_PAN:
                if self.panel == 3:
                    if self.glCanvas2D.click_x > self.glCanvas2D.GetClientSize()[0] // 2:
                        pass
                    else:
                        self.bBackAligned = True
                        self.BackPosx -= self.glCanvas2D.dx * 0.25
                        self.BackPosy -= self.glCanvas2D.dy * 0.25
                if self.panel == 1:
                    self.bBackAligned = True
                    self.BackPosx -= self.glCanvas2D.dx * 0.25
                    self.BackPosy -= self.glCanvas2D.dy * 0.25
                self.glCanvas2D.dx = 0
                self.glCanvas2D.dy = 0
                self.on_draw()
                return
            if self.modeEdit not in [MODE_EDIT_BASETEX, MODE_EDIT_OVERTEX, MODE_EDIT_PROP, MODE_EDIT_FLORA, MODE_EDIT_BUILDING, MODE_EDIT_TRANSIT]:
                return
            self.SetMatForUnproj()
            h = self.size[1]
            lx, ly = self.glCanvas2D.last_x, self.glCanvas2D.last_y
            cx, cy = self.glCanvas2D.x, self.glCanvas2D.y
            lx, ly, dz = gluUnProject(lx, h - ly, 0)
            cx, cy, dz = gluUnProject(cx, h - cy, 0)
            dx = cx - lx
            dy = cy - ly
            if self.dragSelect:
                self.dragQuad[2] = cx + self.lotSizeXOffset
                self.dragQuad[3] = cy + self.lotSizeYOffset
            elif self.modeEdit in [MODE_EDIT_BASETEX, MODE_EDIT_OVERTEX, MODE_EDIT_TRANSIT]:
                # Textures live on whole 16m tiles: snap the cursor to a tile
                # first, then move the selection by whole-tile steps so a slow
                # drag still tracks the pointer instead of being swallowed.
                tileX = math.floor((cx + self.lotSizeXOffset) / 16.0)
                tileY = math.floor((cy + self.lotSizeYOffset) / 16.0)
                if self._texDragTile is None:
                    self._texDragTile = (tileX, tileY)
                dTileX = tileX - self._texDragTile[0]
                dTileY = tileY - self._texDragTile[1]
                if dTileX or dTileY:
                    self._texDragTile = (tileX, tileY)
                    if not self._drag_undo_pending:
                        self._push_undo()
                        self._drag_undo_pending = True
                    self.MoveByAmount(dTileX * 16.0, dTileY * 16.0, 0)
            else:
                if not self._drag_undo_pending:
                    self._push_undo()
                    self._drag_undo_pending = True
                self.MoveByAmount(dx, dy, 0)
        self.on_draw()

    def OnMouseDown(self, evt):
        self.glCanvas2D.on_mouse_down(evt)
        self._texDragTile = None
        self._drag_undo_pending = False
        Xclic, Yclick = self.glCanvas2D.mouseX, self.glCanvas2D.mouseY
        self.SetMatForUnproj()
        h = self.size[1]
        px, py, pz = gluUnProject(Xclic, h - Yclick, 0)
        px += self.lotSizeXOffset
        py += self.lotSizeYOffset
        if self.modeEdit == MODE_EDIT_TRANSIT and self.highlighted == []:
            tile_x = int(math.floor(px / 16.0))
            tile_y = int(math.floor(py / 16.0))
            lot_size = self.exemplar.GetProp(2297284496)
            if 0 <= tile_x < lot_size[0] and 0 <= tile_y < lot_size[1]:
                self.PlaceTransitNode(tile_x, tile_y)
                return
        if self.modeEdit == MODE_EDIT_CONSTRAINT and self.highlighted == []:
            tile_x = int(math.floor(px / 16.0))
            tile_y = int(math.floor(py / 16.0))
            lot_size = self.exemplar.GetProp(2297284496)
            if 0 <= tile_x < lot_size[0] and 0 <= tile_y < lot_size[1]:
                # Plain click places a water tile, Shift+click places land.
                self.PlaceConstraint(tile_x, tile_y, 6 if evt.ShiftDown() else 5)
                return
        if not evt.ControlDown():
            for quad in self.quadSelected:
                if px >= quad[0] and px <= quad[2] and py >= quad[1] and py <= quad[3]:
                    self.on_draw()
                    return

            self.selected = []
            self.quadSelected = []
        id2remove = None
        if self.highlighted == []:
            self.dragSelect = True
            self.dragQuad = [px, py, px, py]
        else:
            self.dragSelect = False
            self.dragQuad = None
            for id, quad in zip(self.highlighted, self.quadHighs):
                if px >= quad[0] and px <= quad[2] and py >= quad[1] and py <= quad[3]:
                    if id not in self.selected:
                        self.selected.append(id)
                        self.quadSelected.append(quad)
                    else:
                        id2remove = self.selected.index(id)

            if id2remove is not None:
                self.selected = self.selected[:id2remove] + self.selected[id2remove + 1:]
                self.quadSelected = self.quadSelected[:id2remove] + self.quadSelected[id2remove + 1:]
        self.on_draw()
        self.UpdateSelectionInspector()
        return

    def OnMouseUp(self, evt):
        self.newIds = []
        self._drag_undo_pending = False
        self.glCanvas2D.on_mouse_up(evt)
        if self.dragSelect:
            self.dragSelect = False
            self.dragQuad = None
            if not evt.ControlDown():
                self.quadSelected = []
                self.selected = []
            for id, quad in zip(self.highlighted, self.quadHighs):
                if id not in self.selected:
                    self.quadSelected.append(quad)
                    self.selected.append(id)

        elif self.modeEdit in [MODE_EDIT_BUILDING, MODE_EDIT_FLORA, MODE_EDIT_PROP]:
            for id, q in zip(self.selected, self.quadSelected):
                for lcp in range(2297284864, 2297286144):
                    values = self.exemplar.GetProp(lcp)
                    if values is None:
                        break
                    if values[11] == id:
                        values[3] = ToUnsigned((q[0] + q[2]) / 2 * 65536)
                        values[5] = ToUnsigned((q[1] + q[3]) / 2 * 65536)
                        values[6] = ToUnsigned(q[0] * 65536)
                        values[7] = ToUnsigned(q[1] * 65536)
                        values[8] = ToUnsigned(q[2] * 65536)
                        values[9] = ToUnsigned(q[3] * 65536)
                        if values[0] == 0:
                            self.building[:-1] = values[:]
                        else:
                            what = self.props
                            if values[0] == 4:
                                what = self.floras
                            for prop in what:
                                if prop[11] == id:
                                    prop[:13] = values
                                    break

        elif self.modeEdit in [MODE_EDIT_BASETEX, MODE_EDIT_OVERTEX]:
            for id, q in zip(self.selected, self.quadSelected):
                objectIds = []
                prop2Remove = []
                if self.modeEdit == MODE_EDIT_BASETEX:
                    for texData in self.texBases:
                        if texData[4] != id:
                            minx = texData[0] * 16
                            miny = texData[1] * 16
                            maxx = texData[0] * 16 + 16
                            maxy = texData[1] * 16 + 16
                            if q == [minx, miny, maxx, maxy]:
                                self.texBases.remove(texData)
                                objectIds.append(texData[4])

                for lcp in range(2297284864, 2297286144):
                    values = self.exemplar.GetProp(lcp)
                    if values is None:
                        break
                    if values[11] in objectIds:
                        prop2Remove.append(lcp)
                    if values[11] == id:
                        values[3] = ToUnsigned((q[0] + q[2]) / 2 * 65536)
                        values[5] = ToUnsigned((q[1] + q[3]) / 2 * 65536)
                        values[6] = ToUnsigned(q[0] * 65536)
                        values[7] = ToUnsigned(q[1] * 65536)
                        values[8] = ToUnsigned(q[2] * 65536)
                        values[9] = ToUnsigned(q[3] * 65536)

                for id in prop2Remove:
                    self.exemplar.RemoveProp(id)

                self.exemplar.ReindexLotConfig()

            self.UpdatePIM()
        elif self.modeEdit == MODE_EDIT_TRANSIT:
            self.UpdatePIM()
        self.on_draw()
        self.UpdateSelectionInspector()
        return

    def UpdatePIM(self):
        self.descPage.listProperties.Freeze()
        self.descPage.listProperties.DeleteAllItems()
        self.descPage.FillTheList()
        self.descPage.listProperties.Thaw()


class LotCreatorDlg(sc.SizedDialog):

    def __init__(self, parent, exemplar, virtualDAT, bGrowable, bRebuild=False, sizeLot=(0, 0)):
        sc.SizedDialog.__init__(self, parent, -1, title=LotCreationDlgMsg, style=wx.DEFAULT_DIALOG_STYLE)
        self.exemplar = exemplar
        self.virtualDAT = virtualDAT
        self.bGrowable = bGrowable
        pane = self.GetContentsPane()
        pane.SetSizerType('form')
        w, d = self.ComputeMinDimension()
        if bRebuild:
            w = sizeLot[0]
            d = sizeLot[1]
        if self.bGrowable:
            s = self.ComputeStage(w, d)
        if not bRebuild:
            wx.StaticText(pane, -1, LotCreationDlgWidth)
            self.widthCtrl = wx.ComboBox(pane, -1, str(w), style=wx.CB_DROPDOWN | wx.CB_READONLY, choices=[ str(v) for v in range(w, 32) ])
            wx.StaticText(pane, -1, LotCreationDlgHeight)
            self.depthCtrl = wx.ComboBox(pane, -1, str(d), style=wx.CB_DROPDOWN | wx.CB_READONLY, choices=[ str(v) for v in range(d, 32) ])
        if self.bGrowable:
            wx.StaticText(pane, -1, LotCreationDlgStage)
            self.stageCtrl = wx.ComboBox(pane, -1, str(s), style=wx.CB_DROPDOWN | wx.CB_READONLY, choices=[ str(v) for v in range(max(1, s - 1), min(s + 2, 16)) ])
        self.SetButtonSizer(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        self.Fit()
        self.SetMinSize(self.GetSize())
        if not bRebuild:
            self.Bind(wx.EVT_COMBOBOX, self.EvtComboBox, self.widthCtrl)
            self.Bind(wx.EVT_COMBOBOX, self.EvtComboBox, self.depthCtrl)

    def EvtComboBox(self, event):
        w = int(self.widthCtrl.GetValue())
        d = int(self.depthCtrl.GetValue())
        if self.bGrowable:
            s = self.ComputeStage(w, d)
            self.stageCtrl.Clear()
            stageChoice = [ str(v) for v in range(max(1, s - 1), min(s + 2, 16)) ]
            for stage in stageChoice:
                self.stageCtrl.Append(stage)

            self.stageCtrl.SetValue(str(s))

    def ComputeMinDimension(self):
        minx = 1 + int(self.exemplar.GetProp(662775824)[0]) // 16
        minz = 1 + int(self.exemplar.GetProp(662775824)[2]) // 16
        return (
         minx, minz)

    def ComputeStage(self, width, depth):
        minx = width
        minz = depth
        purpose = 'IR'
        wealth = 0
        if self.exemplar.GetProp(2854081430) is not None:
            if 4096 in self.exemplar.GetProp(2854081430):
                purpose = 'R'
            if 69648 in self.exemplar.GetProp(2854081430):
                purpose = 'R'
                wealth = 0
            if 69664 in self.exemplar.GetProp(2854081430):
                purpose = 'R'
                wealth = 1
            if 69680 in self.exemplar.GetProp(2854081430):
                purpose = 'R'
                wealth = 2
            if 4097 in self.exemplar.GetProp(2854081430):
                purpose = 'C'
            if 78096 in self.exemplar.GetProp(2854081430):
                purpose = 'CS'
                wealth = 0
            if 78112 in self.exemplar.GetProp(2854081430):
                purpose = 'CS'
                wealth = 1
            if 78128 in self.exemplar.GetProp(2854081430):
                purpose = 'CS'
                wealth = 2
            if 78624 in self.exemplar.GetProp(2854081430):
                purpose = 'CO'
                wealth = 1
            if 78640 in self.exemplar.GetProp(2854081430):
                purpose = 'CO'
                wealth = 2
            if 4098 in self.exemplar.GetProp(2854081430):
                purpose = 'I'
            if 82176 in self.exemplar.GetProp(2854081430):
                purpose = 'IR'
                wealth = 0
            if 82432 in self.exemplar.GetProp(2854081430):
                purpose = 'ID'
                wealth = 1
            if 82688 in self.exemplar.GetProp(2854081430):
                purpose = 'IM'
                wealth = 1
            if 82944 in self.exemplar.GetProp(2854081430):
                purpose = 'IHT'
                wealth = 2
        else:
            purpose = 'IR'
            wealth = 0
            self.purpose = purpose
            self.wealth = wealth
            return 1
        tiles = minx * minz

        def getKeyedValue(cont, key):
            try:
                idx = cont.index(key)
                return cont[idx + 1]
            except AttributeError:
                logger.exception('Capacity container has no index() method: %r (%s), key=%r',
                                 cont, type(cont).__name__, key)
                raise
            except KeyError:
                logger.exception('Capacity key lookup failed: %r (%s), key=%r',
                                 cont, type(cont).__name__, key)
                raise

        capacities = {('R', 0): 4112,('R', 1): 4128,('R', 2): 4144,('CS', 0): 12560,('CS', 1): 12576,('CS', 2): 12592,('CO', 1): 13088,('CO', 2): 13104,('IR', 0): 16640,('ID', 1): 16896,('IM', 1): 17152,('IHT', 2): 17408}
        capacity = getKeyedValue(self.exemplar.GetProp(662775860), capacities[purpose, wealth])
        ratios = self.virtualDAT.lotStages[purpose, wealth]
        ratio = capacity / tiles
        if purpose == 'IR':
            ratio = capacity
        stage = 1
        for i, r in enumerate(ratios):
            if ratio >= r:
                stage = i + 2

        self.purpose = purpose
        self.wealth = wealth
        return stage


def ComputeStagePurposeWealth(capacitySatisfied, occupantGroup, width, depth):
    minx = width
    minz = depth
    purpose = 'N'
    wealth = -1
    if 4096 in occupantGroup:
        purpose = 'R'
    if 69648 in occupantGroup:
        purpose = 'R'
        wealth = 0
    if 69664 in occupantGroup:
        purpose = 'R'
        wealth = 1
    if 69680 in occupantGroup:
        purpose = 'R'
        wealth = 2
    if 4097 in occupantGroup:
        purpose = 'C'
    if 78096 in occupantGroup:
        purpose = 'CS'
        wealth = 0
    if 78112 in occupantGroup:
        purpose = 'CS'
        wealth = 1
    if 78128 in occupantGroup:
        purpose = 'CS'
        wealth = 2
    if 78624 in occupantGroup:
        purpose = 'CO'
        wealth = 1
    if 78640 in occupantGroup:
        purpose = 'CO'
        wealth = 2
    if 4098 in occupantGroup:
        purpose = 'I'
    if 82176 in occupantGroup:
        purpose = 'IR'
        wealth = 0
    if 82432 in occupantGroup:
        purpose = 'ID'
        wealth = 1
    if 82688 in occupantGroup:
        purpose = 'IM'
        wealth = 1
    if 82944 in occupantGroup:
        purpose = 'IHT'
        wealth = 2
    tiles = minx * minz

    def getKeyedValue(cont, key):
        try:
            idx = cont.index(key)
            return cont[idx + 1]
        except AttributeError:
            logger.exception('Capacity container has no index() method: %r (%s), key=%r',
                             cont, type(cont).__name__, key)
            raise
        except KeyError:
            logger.exception('Capacity key lookup failed: %r (%s), key=%r',
                             cont, type(cont).__name__, key)
            raise

    capacities = {('R', 0): 4112,('R', 1): 4128,('R', 2): 4144,('CS', 0): 12560,('CS', 1): 12576,('CS', 2): 12592,('CO', 1): 13088,('CO', 2): 13104,('IR', 0): 16640,('ID', 1): 16896,('IM', 1): 17152,('IHT', 2): 17408}
    capacity = getKeyedValue(capacitySatisfied, capacities[purpose, wealth])
    ratios = VirtualDat.this.lotStages[purpose, wealth]
    ratio = capacity / tiles
    if purpose == 'IR':
        ratio = capacity
    stage = 1
    for i, r in enumerate(ratios):
        if ratio >= r:
            stage = i + 2

    return (stage, purpose, wealth)


class ImageDBBuilder(wx.Frame):

    def __init__(self, parent, ID, title, pos=wx.DefaultPosition, size=wx.DefaultSize, style=wx.DEFAULT_FRAME_STYLE | wx.STAY_ON_TOP):
        wx.Frame.__init__(self, parent, ID, title, pos, size, style)
        panel = wx.Panel(self, -1)
        self.glCanvas = MyCanvasBase(panel, size=(256, 256))
        self.glCanvas.displayer = self
        self.viewer = S3DViewer(None, self.glCanvas)
        sizer = wx.BoxSizer(wx.VERTICAL)
        hsizer = wx.BoxSizer(wx.HORIZONTAL)
        hsizer.Add(self.glCanvas, 1, wx.ALL | wx.EXPAND, 5)
        sizer.Add(hsizer, 1, wx.ALL | wx.EXPAND, 5)
        panel.SetSizer(sizer)
        sizer.Fit(self)
        return

    def Draw(self, sc4data):
        self.viewer.init_gl()
        glClearColor(0.5, 0.5, 0.5, 0.0)
        self.viewer.s3d_mesh = None
        self.viewer.refresh(False)
        self.viewer.use_best_fit = True
        self.viewer.drawAxis = False
        sc4data[1].sc4Model.draw(self.viewer, None, -1, 0)
        wx.Yield()
        self.viewer.drawAxis = False
        sc4data[1].sc4Model.draw(self.viewer, None, -1, 0)
        wx.Yield()
        size = self.viewer.openGLCanvas.GetClientSize()
        glReadBuffer(GL_FRONT)
        data = glReadPixels(0, 0, size[0], size[1], GL_RGB, GL_UNSIGNED_BYTE)
        image = Image.frombytes('RGB', (size[0], size[1]), data)
        image = image.transpose(Image.FLIP_TOP_BOTTOM)
        image.resize((128, 128)).save(os.path.join(os.path.split(sc4data[0])[0] + 'Large', os.path.split(sc4data[0])[1]))
        image = image.resize((64, 64))
        image.save(sc4data[0])
        del image
        del data
        del size
        self.viewer.s3d_mesh.FreeAll(self.viewer.s3d_textures_holder)
        return

