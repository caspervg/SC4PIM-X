"""SC4 lot preview and editor with 2D/3D rendering."""
import logging
import math
import os

import numpy
import wx
import wx.lib.sized_controls as sc
from OpenGL.GL import (
    GL_BLEND,
    GL_CLAMP_TO_EDGE,
    GL_COLOR_BUFFER_BIT,
    GL_CULL_FACE,
    GL_DEPTH_BUFFER_BIT,
    GL_DEPTH_TEST,
    GL_FALSE,
    GL_FRAMEBUFFER,
    GL_LEQUAL,
    GL_LINEAR,
    GL_LINES,
    GL_MULTISAMPLE,
    GL_NEAREST,
    GL_ONE,
    GL_ONE_MINUS_SRC_ALPHA,
    GL_POLYGON_OFFSET_FILL,
    GL_REPEAT,
    GL_SRC_ALPHA,
    GL_TRUE,
    glBindFramebuffer,
    glBlendFunc,
    glClear,
    glClearColor,
    glClearDepth,
    glDeleteTextures,
    glDepthFunc,
    glDepthMask,
    glDisable,
    glEnable,
    glPolygonOffset,
    glViewport,
)
from PIL import Image

from . import FSHConverter, SC4IconMakerDlg, SC4Matrix, treeDnD
from .ATCReader import ATC
from .config import load_lot_editor, save_lot_editor
from .paths import background_path, background_set_dir, background_sets
from .S3DShaders import (
    DAY_PRESET,
    NIGHT_PRESET,
    SC4LightingProgram,
    SC4ShadowProgram,
    approximate_model_light,
)
from .S3DTexturesHolder import S3DTexturesHolder
from .S3DViewer import S3DViewer
from .SC4Data import *
from .SC4DataFunctions import ToCoord, ToTile, ToUnsigned, model_is_prelit, night_state_for
from .SC4LightingProfiles import lighting_profile, lighting_profiles
from .SC4LETools import *
from .SC4OpenGL import MyCanvasBase
from .SC4PathReader import (
    SC4PATH_GIDS,
    SC4PATH_TYPE,
    SC4PathParseError,
    parse_sc4path,
)
from .SC4PropTiming import (
    clamp_date,
    is_night,
    prop_temporal_state,
    timer_hides_prop,
    timer_state_index,
)
from .SC4Renderer import RenderTarget, TransformStack, create_texture_2d
from .SC4TransitLotTools import (
    DEFAULT_TRANSIT_SETTINGS,
    TRANSIT_OBJECT_TYPE,
    TransitInspectorPanel,
    cached_transit,
    draw_sc4path_overlay_2d,
    draw_sc4path_overlay_3d,
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
    transit_path_status,
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
LAYER_SC4PATHS = 'sc4_paths'
LAYER_ROAD_EDGES = 'road_edges'
LAYER_BUILDING = 'building'
LAYER_PROPS = 'props'
LAYER_FLORA = 'flora'
LAYER_SNAP_GRID = 'snap_grid'
LAYER_SELECTION = 'selection'
LAYER_MISSING = 'missing_markers'
LAYER_CARDINALS = 'cardinal_labels'
LAYER_BACKGROUND = 'terrain_background'
LAYER_SHADOWS = 'shadows'
LAYER_SPECS = [
    (LAYER_BASE, LEXLayerBaseTextures),
    (LAYER_OVERLAY, LEXLayerOverlayTextures),
    (LAYER_WATER, LEXLayerWaterConstraints),
    (LAYER_LAND, LEXLayerLandConstraints),
    (LAYER_TRANSIT, LEXLayerTransit),
    (LAYER_SC4PATHS, LEXLayerSC4Paths),
    (LAYER_ROAD_EDGES, LEXLayerRoadEdges),
    (LAYER_BUILDING, LEXLayerBuilding),
    (LAYER_PROPS, LEXLayerProps),
    (LAYER_FLORA, LEXLayerFlora),
    (LAYER_SHADOWS, LEXLayerShadows),
    (LAYER_SNAP_GRID, LEXLayerSnapGrid),
    (LAYER_SELECTION, LEXLayerSelection),
    (LAYER_MISSING, LEXLayerMissingMarkers),
    (LAYER_CARDINALS, LEXLayerCardinalLabels),
    (LAYER_BACKGROUND, LEXLayerTerrainBackground),
]
# Layers that only make sense in the 3D preview; hidden from the 2D submenu.
LAYER_3D_ONLY = {LAYER_SHADOWS}
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
        px, py, pz = self.frame.UnProject(x, y)
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
            posX, posY, pz = self.frame.UnProject(x, y)
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
        self._family_members = []
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
        family_box = wx.StaticBox(self, -1, 'Family variations')
        family_fields = wx.StaticBoxSizer(family_box, wx.VERTICAL)
        self.familyGrid = wx.ScrolledWindow(self, -1, style=wx.BORDER_NONE | wx.VSCROLL)
        self.familyGrid.SetBackgroundColour(wx.Colour(250, 251, 252))
        self.familyGrid.SetScrollRate(0, 12)
        self.familySizer = wx.WrapSizer(wx.HORIZONTAL)
        self.familyGrid.SetSizer(self.familySizer)
        family_fields.Add(self.familyGrid, 1, wx.EXPAND | wx.ALL, 4)
        sizer.Add(self.text, 1, wx.EXPAND | wx.ALL, 6)
        sizer.Add(fields, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        sizer.Add(self.transitPanel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        sizer.Add(family_fields, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.SetSizer(sizer)
        self._outer = sizer
        self._fields = fields
        self._transit = self.transitPanel
        self._family_fields = family_fields
        self.HideFields()
        self.HideTransit()
        self.HideFamilyVariations()

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
        self.HideFamilyVariations()
        self._transit.ShowFor(values_list, defaults)
        self._outer.Show(self._transit, True, recursive=True)
        self.Layout()

    def HideTransit(self):
        self._outer.Show(self._transit, False, recursive=True)
        self.Layout()

    def ShowFamilyVariations(self, family_id, members, selected_tgi):
        self._family_members = list(members)
        self.familySizer.Clear(True)
        for idx, desc in enumerate(self._family_members):
            bmp = self._family_member_bitmap(desc)
            item = wx.Panel(self.familyGrid, -1)
            item_sizer = wx.BoxSizer(wx.VERTICAL)
            btn = wx.BitmapToggleButton(item, -1, bmp, size=(58, 58))
            btn.SetValue(desc.exemplar.entry.tgi == selected_tgi)
            btn.SetToolTip('%s\n%s' % (desc.name, hex2str(desc.exemplar.entry.tgi[2])))
            btn.Bind(wx.EVT_TOGGLEBUTTON, lambda evt, i=idx: self.OnFamilyVariation(i))
            label = wx.StaticText(item, -1, hex2str(desc.exemplar.entry.tgi[2])[-4:])
            label.SetFont(wx.Font(7, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
            item_sizer.Add(btn, 0, wx.ALIGN_CENTER)
            item_sizer.Add(label, 0, wx.ALIGN_CENTER | wx.TOP, 1)
            item.SetSizer(item_sizer)
            self.familySizer.Add(item, 0, wx.ALL, 2)
        self.familyGrid.FitInside()
        self.familyGrid.SetMinSize((-1, 76 if len(self._family_members) <= 4 else 136))
        self._outer.Show(self._family_fields, True, recursive=True)
        self.Layout()

    def HideFamilyVariations(self):
        self._family_members = []
        self.familySizer.Clear(True)
        self._outer.Show(self._family_fields, False, recursive=True)
        self.Layout()

    def _family_member_bitmap(self, desc):
        try:
            image = BuildImagesForPropStates(desc.exemplar, 52)[0]
            return BitmapFromPIL(image)
        except Exception:
            bmp = wx.Bitmap(52, 52)
            dc = wx.MemoryDC(bmp)
            dc.SetBackground(wx.Brush(wx.Colour(232, 235, 238)))
            dc.Clear()
            dc.SetTextForeground(wx.Colour(98, 108, 118))
            dc.DrawLabel('!', wx.Rect(0, 0, 52, 52), wx.ALIGN_CENTER)
            dc.SelectObject(wx.NullBitmap)
            return bmp

    def OnFamilyVariation(self, idx):
        if idx < 0 or idx >= len(self._family_members):
            return
        desc = self._family_members[idx]
        self.editor.SetFamilyVariation(desc)

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
        self.lotEffectDescs = []
        self.lotFamiliesPropID = []
        self.lotFloraDescs = []
        self.familyVariations = {}
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
        self.s3d_shadow_program = None
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
        self._sc4path_cache = {}
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
        self.previewDate = clamp_date(
            settings.get('PreviewMonth', 1),
            settings.get('PreviewDay', 1),
        )
        self.previewMinutes = max(0, min(1439, int(settings.get('PreviewMinutes', 720))))
        self.showInactiveProps = bool(settings.get('ShowInactiveProps', False))
        self.lightingProfiles = lighting_profiles()
        self.lightingProfile = lighting_profile(settings.get('LightingProfile', 'maxis'))
        self.lightingProfileId = self.lightingProfile.profile_id
        # SC4 shadows are view-locked (sun azimuth fixed on screen); default on.
        self.shadowLockToView = bool(settings.get('ShadowLockToView', True))
        self.nightBegin = self.lightingProfile.night_begin_hour
        self.nightEnd = self.lightingProfile.night_end_hour
        self.clockNightMode = is_night(self.previewMinutes, self.nightBegin, self.nightEnd)
        self.nightMode = self.lightingProfile.is_graphical_night(
            self.previewMinutes, self.previewDate.month,
        )
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
        self.viewportPanel = viewport_panel
        self.glCanvas2D.Reparent(viewport_panel)
        viewport_sizer = wx.BoxSizer(wx.VERTICAL)
        self.temporalBar = self._build_temporal_bar(viewport_panel)
        viewport_sizer.Add(self.temporalBar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 6)
        viewport_sizer.Add(self.glCanvas2D, 1, wx.EXPAND | wx.ALL, 6)
        viewport_panel.SetSizer(viewport_sizer)
        self.inspector = LEInspectorPanel(self.rightSplitter, self)
        inspector_width = int(settings.get('InspectorWidth', 280))
        self.rightSplitter.SplitVertically(viewport_panel, self.inspector, -inspector_width)
        self.rightSplitter.SetMinimumPaneSize(220)
        self.rightSplitter.SetSashGravity(1.0)
        browser_width = int(settings.get('BrowserWidth', 330))
        self.mainSplitter.SplitVertically(self.assetBrowser, self.rightSplitter, browser_width)
        self.mainSplitter.SetMinimumPaneSize(260)
        root.Add(self.mainSplitter, 1, wx.EXPAND)
        panel.SetSizer(root)
        self._sync_mode_buttons()
        # The constructor size is only the "restore" size; the lot editor is
        # cramped at 800x600, so open it maximized.
        self.Maximize(True)

    def _build_temporal_bar(self, parent):
        bar = wx.Panel(parent, -1)
        bar.SetBackgroundColour(wx.Colour(244, 246, 248))
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(bar, -1, LEXTemporalPreview), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 8)

        row.Add(wx.StaticText(bar, -1, LEXLightingProfile), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.lightingProfileCtrl = wx.Choice(
            bar, -1, choices=[profile.display_name for profile in self.lightingProfiles],
        )
        self._lightingProfileIds = [profile.profile_id for profile in self.lightingProfiles]
        self.lightingProfileCtrl.SetSelection(
            self._lightingProfileIds.index(self.lightingProfileId)
        )
        row.Add(self.lightingProfileCtrl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)

        row.Add(wx.StaticText(bar, -1, LEXTemporalDayField), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.previewDayCtrl = wx.SpinCtrl(bar, -1, min=1, max=31,
                                          initial=self.previewDate.day,
                                          size=(56, -1))
        row.Add(self.previewDayCtrl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        row.Add(wx.StaticText(bar, -1, LEXTemporalMonthField), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.previewMonthCtrl = wx.Choice(bar, -1, choices=[
            LEXMonthJan, LEXMonthFeb, LEXMonthMar, LEXMonthApr,
            LEXMonthMay, LEXMonthJun, LEXMonthJul, LEXMonthAug,
            LEXMonthSep, LEXMonthOct, LEXMonthNov, LEXMonthDec,
        ])
        self.previewMonthCtrl.SetSelection(self.previewDate.month - 1)
        row.Add(self.previewMonthCtrl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)

        self.previewTimeSlider = wx.Slider(
            bar, -1, self.previewMinutes, 0, 1439, size=(320, -1),
        )
        row.Add(self.previewTimeSlider, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.previewPlayButton = wx.Button(bar, -1, LEXTemporalPlay,
                                           size=(84, -1))
        row.Add(self.previewPlayButton, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.previewLoopModeCtrl = wx.Choice(bar, -1, choices=[
            LEXLoopTime, LEXLoopDate, LEXLoopTimeDate,
        ])
        self.previewLoopModeCtrl.SetSelection(0)
        self.previewLoopModeCtrl.SetToolTip(LEXTemporalLoop)
        row.Add(self.previewLoopModeCtrl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.previewTimeLabel = wx.StaticText(bar, -1, '')
        self.previewTimeLabel.SetMinSize((88, -1))
        row.Add(self.previewTimeLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)
        self.showInactiveCheck = wx.CheckBox(bar, -1, LEXTemporalShowInactive)
        self.showInactiveCheck.SetValue(self.showInactiveProps)
        row.Add(self.showInactiveCheck, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        bar.SetSizer(row)

        self._updatingTemporalControls = False
        self.previewMonthCtrl.Bind(wx.EVT_CHOICE, self.OnTemporalChange)
        self.previewDayCtrl.Bind(wx.EVT_SPINCTRL, self.OnTemporalChange)
        self.previewDayCtrl.Bind(wx.EVT_TEXT, self.OnTemporalChange)
        self.previewTimeSlider.Bind(wx.EVT_SLIDER, self.OnTemporalChange)
        self.showInactiveCheck.Bind(wx.EVT_CHECKBOX, self.OnTemporalChange)
        self.lightingProfileCtrl.Bind(wx.EVT_CHOICE, self.OnLightingProfileChange)
        self.previewPlayButton.Bind(wx.EVT_BUTTON, self.OnTogglePlayback)
        self.previewPlayTimer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnPlaybackTick, self.previewPlayTimer)
        self._update_temporal_controls()
        return bar

    # Every PLAYBACK_INTERVAL_MS, the loop advances by one step. The step size
    # depends on the loop mode (see the previewLoopModeCtrl dropdown):
    #   Time        -> +PLAYBACK_STEP_MINUTES of clock time, wrap at midnight.
    #   Date        -> +1 calendar day, clock held fixed.
    #   Time + Date -> +PLAYBACK_STEP_BOTH_MINUTES (faster), and each midnight
    #                  wrap bumps the date forward one day.
    PLAYBACK_STEP_MINUTES = 5
    PLAYBACK_STEP_BOTH_MINUTES = 60
    PLAYBACK_INTERVAL_MS = 25
    LOOP_MODE_TIME = 0
    LOOP_MODE_DATE = 1
    LOOP_MODE_BOTH = 2

    def OnTogglePlayback(self, event=None):
        if self.previewPlayTimer.IsRunning():
            self._stop_playback()
        else:
            self.previewPlayButton.SetLabel(LEXTemporalPause)
            self.previewPlayTimer.Start(self.PLAYBACK_INTERVAL_MS)

    def _stop_playback(self):
        if self.previewPlayTimer.IsRunning():
            self.previewPlayTimer.Stop()
        self.previewPlayButton.SetLabel(LEXTemporalPlay)

    def OnPlaybackTick(self, event=None):
        mode = self.previewLoopModeCtrl.GetSelection()
        if mode == self.LOOP_MODE_DATE:
            self._advance_date(1)
            return
        step = (self.PLAYBACK_STEP_BOTH_MINUTES if mode == self.LOOP_MODE_BOTH
                else self.PLAYBACK_STEP_MINUTES)
        # Snap to the step grid, advance one step, wrap at midnight.
        minutes = self.previewMinutes - (self.previewMinutes % step) + step
        wrapped = minutes >= 1440
        self.previewMinutes = minutes % 1440
        self.previewTimeSlider.SetValue(self.previewMinutes)
        if mode == self.LOOP_MODE_BOTH and wrapped:
            # _advance_date syncs the date controls and triggers the redraw.
            self._advance_date(1)
        else:
            self.OnTemporalChange()

    def _advance_date(self, days=1):
        """Roll the preview date forward, wrapping Dec 31 -> Jan 1.

        Syncs the month/day controls then routes through OnTemporalChange so the
        redraw, night-mode and inspector updates all run as if edited by hand.
        """
        import calendar
        month, day = self.previewDate.month, self.previewDate.day + days
        while True:
            last = calendar.monthrange(1, month)[1]
            if day <= last:
                break
            day -= last
            month = month % 12 + 1
        self._updatingTemporalControls = True
        try:
            self.previewMonthCtrl.SetSelection(month - 1)
            self.previewDayCtrl.SetRange(1, calendar.monthrange(1, month)[1])
            self.previewDayCtrl.SetValue(day)
        finally:
            self._updatingTemporalControls = False
        self.OnTemporalChange()

    def _update_temporal_controls(self):
        if not hasattr(self, 'previewTimeLabel'):
            return
        hours, minutes = divmod(self.previewMinutes, 60)
        suffix = '  %s' % (LEXTemporalNight if self.nightMode else LEXTemporalDay)
        self.previewTimeLabel.SetLabel('%02d:%02d%s' % (hours, minutes, suffix))
        self.previewDayCtrl.SetRange(1, self._days_in_preview_month())

    def _days_in_preview_month(self):
        import calendar
        return calendar.monthrange(self.previewDate.year, self.previewDate.month)[1]

    def OnTemporalChange(self, event=None):
        if getattr(self, '_updatingTemporalControls', False):
            return
        self._updatingTemporalControls = True
        try:
            month = self.previewMonthCtrl.GetSelection() + 1
            day = self.previewDayCtrl.GetValue()
            self.previewDate = clamp_date(month, day)
            if day != self.previewDate.day:
                self.previewDayCtrl.SetValue(self.previewDate.day)
            self.previewMinutes = self.previewTimeSlider.GetValue()
            self.showInactiveProps = self.showInactiveCheck.GetValue()
            self._apply_preview_night_mode()
            self._update_temporal_controls()
            self.SaveEditorState()
            self.UpdateSelectionInspector()
            self._request_draw()
        finally:
            self._updatingTemporalControls = False

    def OnLightingProfileChange(self, event=None):
        selection = self.lightingProfileCtrl.GetSelection()
        if selection < 0 or selection >= len(self._lightingProfileIds):
            return
        self.lightingProfile = lighting_profile(self._lightingProfileIds[selection])
        self.lightingProfileId = self.lightingProfile.profile_id
        self.nightBegin = self.lightingProfile.night_begin_hour
        self.nightEnd = self.lightingProfile.night_end_hour
        self._apply_preview_night_mode()
        self._update_temporal_controls()
        self.SaveEditorState()
        self._request_draw()

    def _apply_preview_night_mode(self):
        self.clockNightMode = is_night(self.previewMinutes, self.nightBegin, self.nightEnd)
        profile = getattr(self, 'lightingProfile', None)
        if profile is not None:
            night = profile.is_graphical_night(self.previewMinutes, self.previewDate.month)
        else:
            night = self.clockNightMode
        self.nightMode = night
        if getattr(self, 's3DTexturesHolder', None) is not None:
            self.s3DTexturesHolder.SetNightMode(night)

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
        state['PreviewMonth'] = int(self.previewDate.month)
        state['PreviewDay'] = int(self.previewDate.day)
        state['PreviewMinutes'] = int(self.previewMinutes)
        state['ShowInactiveProps'] = bool(self.showInactiveProps)
        state['ShadowLockToView'] = bool(getattr(self, 'shadowLockToView', True))
        state['LightingProfile'] = str(getattr(self, 'lightingProfileId', 'maxis'))
        return state

    def _default_visible_layers(self):
        # Shadows are an opt-in extra; everything else defaults on.
        return {key: (key != LAYER_SHADOWS) for key, _label in LAYER_SPECS}

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
        source = getattr(item, 'source', None)
        exemplar = getattr(source, 'exemplar', None)
        state_count = getattr(source, 'stateCount',
                              len(getattr(source, 'viewingData', None) or [])) or 1
        lines.extend(self._temporal_status_lines(exemplar, state_count))
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

    def _temporal_state_for_exemplar(self, exemplar):
        return prop_temporal_state(exemplar, self.previewDate, self.previewMinutes)

    def _temporal_status_lines(self, exemplar, state_count=1):
        if exemplar is None:
            return []
        state = self._temporal_state_for_exemplar(exemplar)
        lines = []
        if state.has_time_rule or state.has_date_rule:
            if state.active:
                lines.append(LEXTemporalVisible)
            elif state_count >= 2:
                # Two-state prop: it swaps to its other model rather than hiding.
                if not state.time_active:
                    lines.append(LEXTemporalAltTime)
                if not state.date_active:
                    lines.append(LEXTemporalAltDate)
            else:
                if not state.time_active:
                    lines.append(LEXTemporalInactiveTime)
                if not state.date_active:
                    lines.append(LEXTemporalInactiveDate)
        if state.random_chance is not None and state.random_chance < 100:
            lines.append('%s: %d%%. %s.' % (
                LEXTooltipSpawnChance, state.random_chance,
                LEXTemporalRandomNotSimulated,
            ))
        return lines

    def _viewer_for_lot_values(self, values):
        if not values or values[0] not in (1, 4):
            return None
        records = self.props if values[0] == 1 else self.floras
        viewers = self.propViewers if values[0] == 1 else self.floraViewers
        for record, viewer in zip(records, viewers):
            if len(record) > 11 and record[11] == values[11]:
                return viewer
        return None

    def _viewer_is_temporally_active(self, viewer):
        if self.showInactiveProps or viewer is None:
            return True
        # A two-state ("semiseasonal") prop switches to its dormant state 1
        # model when out of season rather than disappearing, so it is always
        # rendered; only single-state timed props vanish when inactive.
        state_count = getattr(viewer, 'stateCount',
                              len(getattr(viewer, 'viewingData', None) or []))
        exemplar = getattr(viewer, 'lighting_exemplar', None)
        state = self._temporal_state_for_exemplar(exemplar)
        return not timer_hides_prop(state, state_count)

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
            if self._family_members(values[12]):
                return LEXAssetTypeFamily
            if self._is_effect_ref(values[12]):
                return LEXAssetTypeEffect
            return LEXAssetTypeProp
        if values[0] == 2:
            tex_id = values[12]
            for tex in getattr(self, 'texOverlays', []):
                if tex[4] == values[11] and tex[3] == tex_id:
                    return LEXAssetTypeOverlayTexture
            return LEXAssetTypeBaseTexture
        if values[0] == 4:
            if self._family_members(values[12]):
                return LEXAssetTypeFamily
            return LEXAssetTypeFlora
        if values[0] == 5:
            return LEXConstraintWater
        if values[0] == 6:
            return LEXConstraintLand
        if values[0] == 7:
            return LEXAssetTypeTransit
        return LEXInspectorSelection

    def _is_effect_ref(self, prop_id):
        effect_category = self.virtualDAT.categories.get(EFFECT_CATEGORY_ID)
        if effect_category is None:
            return False
        for desc in effect_category.descriptors:
            if desc.exemplar.entry.tgi[2] == prop_id and IsEffectDesc(desc):
                return True
        return False

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
        effect_count = len(getattr(self, 'effects', []))
        prop_count = max(0, len(getattr(self, 'props', [])) - effect_count)
        lines.extend([
            '%s: %d' % (LEXAssetTypeProp, prop_count),
            '%s: %d' % (LEXAssetTypeEffect, effect_count),
            '%s: %d' % (LEXAssetTypeFlora, len(getattr(self, 'floras', []))),
            '%s: %d' % (LEXAssetTypeBaseTexture, len(getattr(self, 'texBases', []))),
            '%s: %d' % (LEXAssetTypeOverlayTexture, len(getattr(self, 'texOverlays', []))),
            '%s: %d' % (LEXAssetTypeTransit, len(getattr(self, 'te', []))),
            '',
            LEXInspectorNoSelection,
        ])
        return '\n'.join(lines)

    def _family_members(self, family_id):
        if not hasattr(self, 'virtualDAT') or family_id not in self.virtualDAT.categories:
            return []
        members = []
        for desc in self.virtualDAT.categories[family_id].descriptors:
            try:
                if desc.exemplar.entry.tgi[0] != 1697917002:
                    continue
                if desc.exemplar.GetProp(16)[0] in (15, 30):
                    members.append(desc)
            except Exception:
                pass
        members.sort(key=lambda n: n.name.upper())
        return members

    def _selected_family_desc(self, family_id):
        members = self._family_members(family_id)
        if not members:
            return None
        selected_tgi = self.familyVariations.get(family_id)
        if selected_tgi is not None:
            for desc in members:
                if desc.exemplar.entry.tgi == selected_tgi:
                    return desc
        return members[0]

    def SetFamilyVariation(self, desc):
        family_id = None
        selected_id = self.selected[0] if len(self.selected) == 1 else None
        if selected_id is not None:
            values = self._lot_config_for_selection(selected_id)
            if values is not None and values[0] in (1, 4):
                family_id = values[12]
        if family_id is None:
            return
        self.familyVariations[family_id] = desc.exemplar.entry.tgi
        self._rebuild_scene()
        self.UpdateSelectionInspector()
        self.on_draw()

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
                self.inspector.HideFamilyVariations()
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
                for tex_data in getattr(self, 'te', []):
                    if len(tex_data) > 5 and tex_data[5] == values[11]:
                        path_status = transit_path_status(tex_data)
                        if path_status:
                            lines.append('%s: %s' % (LEXLayerSC4Paths, path_status))
                        path_info = tex_data[8] if len(tex_data) > 8 else None
                        path_file = path_info.get("path_file") if path_info else None
                        if path_file is not None and path_file.warnings:
                            lines.append('%s: %s' % (LEXInspectorWarnings, path_file.warnings[0]))
                        break
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
        family_members = []
        family_id = None
        selected_family_tgi = None
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
                    if values[0] in (1, 4):
                        family_members = self._family_members(values[12])
                        if family_members:
                            family_id = values[12]
                            desc = self._selected_family_desc(family_id)
                            if desc is not None:
                                selected_family_tgi = desc.exemplar.entry.tgi
                                lines.append('Variation: %s' % desc.name)
                viewer = self._viewer_for_lot_values(values)
                lines.extend(self._temporal_status_lines(
                    getattr(viewer, 'lighting_exemplar', None),
                    getattr(viewer, 'stateCount',
                            len(getattr(viewer, 'viewingData', None) or [])) or 1,
                ))
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
        if family_members:
            self.inspector.ShowFamilyVariations(family_id, family_members, selected_family_tgi)
        else:
            self.inspector.HideFamilyVariations()

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
            self._update_cached_transit(values)
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
        if hasattr(self, 'temporalBar'):
            self.temporalBar.Show(self.panel != 2)
            self.viewportPanel.Layout()
        self.glCanvas2D.Refresh(False)

    def SetZoom(self, zoom):
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
                        self._update_cached_transit(ensure_transit_values(values))
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
                        self._update_cached_transit(ensure_transit_values(values))
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
        self.lotFamiliesPropID = []
        self.lotPropDescs = []
        self.lotEffectDescs = []
        self.lotFloraDescs = []
        self.props = []
        self.effects = []
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
                        for effect in list(self.effects):
                            if effect[11] == id:
                                self.effects.remove(effect)
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
            self._request_draw()
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
        img = self.Save()
        self.descPage.OnUpdateIcon(img)
        self.UpdatePIM()
        self.RebuildVars()

    def OnPreviewIcon(self, event=None):
        """Show the icon the lot would generate, with an option to apply it."""
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
            if key in LAYER_3D_ONLY and view_key != '3d':
                continue
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
        shadow_lock_id = wx.NewIdRef()
        shadow_lock_item = menu.AppendCheckItem(shadow_lock_id, LEXShadowLockView)
        shadow_lock_item.Check(bool(getattr(self, 'shadowLockToView', True)))
        menu.Bind(wx.EVT_MENU, self.OnToggleShadowLockView, id=shadow_lock_id)
        menu.AppendSeparator()
        self._append_background_menu(menu)
        if event is not None and hasattr(event.GetEventObject(), 'PopupMenu'):
            event.GetEventObject().PopupMenu(menu)
        else:
            self.PopupMenu(menu)
        menu.Destroy()

    def _ensure_s3d_shader_program(self):
        if self.s3d_shader_program is None:
            self.s3d_shader_program = self.glCanvas2D.renderer.register(SC4LightingProgram())
        return self.s3d_shader_program

    def _ensure_shadow_program(self):
        if self.s3d_shadow_program is None:
            self.s3d_shadow_program = self.glCanvas2D.renderer.register(SC4ShadowProgram())
        return self.s3d_shadow_program

    # Authoritative SC4 shadow params, from the VANILLA type-0x13 graphics
    # exemplar 6534284A-A9189CF0-00000001 in SimCity_1.dat ("Shadow colour" /
    # "Shadow strength" / "Sun direction" / "Sun pitch"; see
    # .claude/docs/sc4-shadow-rendering.md). NOTE: vanilla shadow colour is a
    # dark blue-purple, not black -- Gizmo's Day-Night mod flattens it to black.
    # "Model terrain shadow amount" (0.4) is the building/prop value and matches
    # "Shadow strength".
    SHADOW_COLOR = (0.08, 0.06, 0.23)     # "Shadow colour" (vanilla)
    SHADOW_STRENGTH = 0.4                 # "Shadow strength" / "Model terrain shadow amount"
    SHADOW_SUN_AZIMUTH = 67.5             # "Sun direction" (degrees)
    SHADOW_SUN_PITCH = 45.0               # "Sun pitch" (degrees); shadow length = cot(pitch)
    # On-screen shadow angle. The shadow lives in the lot ground plane at
    # lot-azimuth `az`; the camera then yaws by `ry = rot2D - 22.5` and tilts
    # about X. The X-tilt leaves lot-X alone and foreshortens lot-Z into the
    # screen-vertical, so a shadow runs horizontal across the monitor only when
    # its post-yaw Z component vanishes: az + ry = 90 deg. With the view-lock
    # already removing rotation*90, az = (67.5 + offset) - rot2D, which solves to
    # offset = 45 -> shadows lie flat (matching SC4, whose shadows are ~horizontal
    # on screen). The old +90 left a large lot-Z share, so shadows climbed
    # up-screen. Nudge +/-10 to taste.
    SHADOW_AZIMUTH_OFFSET = 45.0

    def _shadow_light_dir(self):
        """Lot-space sun direction (points from sun toward ground; -y is down).

        SC4's shadow is view-locked: the sun azimuth is fixed on screen, so when
        locked we counter-rotate the lot-space azimuth by the camera yaw (the
        ``-viewYaw`` term in cSC4ModelMaker::CreateOccupantShadow). When unlocked
        the azimuth is world-fixed and shadows rotate with the lot."""
        pitch = math.radians(self.SHADOW_SUN_PITCH)
        length = 1.0 / max(math.tan(pitch), 1.0e-3)   # cot(pitch): horizontal per unit height
        azimuth = self.SHADOW_SUN_AZIMUTH + self.SHADOW_AZIMUTH_OFFSET
        if getattr(self, 'shadowLockToView', True):
            # Counter-rotate by the 90-degree view steps only. The camera's fixed
            # -22.5 iso tilt applies equally to world mode (which looks correct),
            # so it must NOT enter the lock: including it lands the lock on
            # degenerate pure-axis shears (lot azimuth 90/0/...) that warp the
            # silhouette. Stepping by rotation*90 keeps the shadow on the same
            # off-axis lattice world mode uses, held at its reference appearance.
            azimuth = azimuth - self.rotation * 90.0
        az = math.radians(azimuth)
        return (length * math.sin(az), -1.0, length * math.cos(az))

    def _shadow_flatten_matrix(self):
        """Planar projection that collapses lot-space geometry onto the y=0
        ground plane along the sun direction (row-major, matches the renderer's
        GL_TRUE upload). Mirrors SC4's projective shadow decal, but using the
        model's real S3D geometry instead of fixed-function texgen."""
        dx, dy, dz = self._shadow_light_dir()
        if abs(dy) < 1.0e-4:
            dy = -1.0
        return numpy.array([
            [1.0, -dx / dy, 0.0, 0.0],
            [0.0,  0.0,     0.0, 0.0],
            [0.0, -dz / dy, 1.0, 0.0],
            [0.0,  0.0,     0.0, 1.0],
        ], dtype=numpy.float64)

    def _lot_lighting_state(self, exemplar, lighting_kind='model'):
        state = dict(NIGHT_PRESET if self.nightMode else DAY_PRESET)
        profile = getattr(self, 'lightingProfile', None)
        if profile is not None:
            state['global_color'] = profile.sample_global_light(
                self.previewMinutes, self.previewDate.month,
            )
            state['terrain_shadow_amount'] = (
                profile.flora_shadow_amount
                if lighting_kind == 'flora'
                else profile.model_shadow_amount
            )
            environment_color = profile.sample_environment_color(
                state['terrain_normal'],
            )
            state['use_environment_map'] = environment_color is not None
            if environment_color is not None:
                state['environment_color'] = environment_color
        state['prelit'] = model_is_prelit(exemplar)
        return state

    def _lot_environment_light(self):
        state = self._lot_lighting_state(None)
        profile = getattr(self, 'lightingProfile', None)
        if profile is not None:
            state['terrain_shadow_amount'] = profile.terrain_shadow_amount
        return approximate_model_light(state)

    def OnToggleLayerVisibility(self, event):
        view_key, layer_key = self._layer_menu_ids.get(event.GetId(), (None, None))
        if view_key is None:
            return
        layers = self.visibleLayers3D if view_key == '3d' else self.visibleLayers2D
        layers[layer_key] = not bool(layers.get(layer_key, True))
        self.SaveEditorState()
        self.on_draw()

    def OnToggleShadowLockView(self, event):
        self.shadowLockToView = not bool(getattr(self, 'shadowLockToView', True))
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
            self.snapGrids = numpy.asarray(snapGrids, dtype=numpy.float32)
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
        if hasattr(self, 'previewPlayTimer') and self.previewPlayTimer.IsRunning():
            self.previewPlayTimer.Stop()
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
        for texture in getattr(self, 'BackTextures', ()):
            if texture:
                delete_gl_texture(texture)

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
        return create_texture_2d(
            size[0], size[1], im, channels=4 if bAlpha else 3,
            srgb=getattr(self.glCanvas2D, 'srgb', False),
        )

    def Preload_Background_Tex2(self):
        texs = [
         'Back01.jpg', 'Back02.jpg', 'Back03.jpg', 'Back04.jpg', 'Back05.jpg']
        for texture in getattr(self, 'BackTextures', ()):
            if texture:
                delete_gl_texture(texture)
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

    def _resolve_lot_desc(self, type_flag, propID, families_seen):
        """Resolve a lot prop/flora object to its descriptor.

        Returns None when the object should be skipped (unknown, or a family
        with no members). type_flag is the lot-config object type (1=prop,
        4=flora). families_seen tracks which family IIDs were already recorded
        in lotFamiliesPropID so that side effect runs once per family.
        """
        if propID in self.virtualDAT.categories:
            if not self._family_members(propID):
                return None
            if propID not in families_seen:
                families_seen.add(propID)
                self.lotFamiliesPropID.append(propID)
            return self._selected_family_desc(propID)
        cat = 210746660 if type_flag == 1 else 1830116951
        category = self.virtualDAT.categories.get(cat)
        if category is not None:
            for desc in category.descriptors:
                if desc.exemplar.entry.tgi[2] == propID:
                    return desc
        if type_flag == 1:
            effect_category = self.virtualDAT.categories.get(EFFECT_CATEGORY_ID)
            if effect_category is not None:
                for desc in effect_category.descriptors:
                    if desc.exemplar.entry.tgi[2] == propID:
                        return desc
        return None

    def RebuildVars(self):
        self.lotFamiliesPropID = []
        self.lotPropDescs = []
        self.lotEffectDescs = []
        self.lotFloraDescs = []
        # Drop stale layer entries whose tile no longer exists. Rebuild the
        # lists rather than removing in place: mutating a list while iterating
        # it skips elements (the old code's bug), and the membership test is a
        # set lookup instead of an O(n) list scan per element.
        base_ids = {tex[3] for tex in self.texBases}
        self.lotBaseTextures = [t for t in self.lotBaseTextures if (t - 3) in base_ids]
        over_ids = {tex[3] for tex in self.texOverlays}
        self.lotOverTextures = [t for t in self.lotOverTextures if (t - 3) in over_ids]

        # A lot repeats the same prop/flora model many times. Resolve each
        # (type, model) to its descriptor once, and dedup the output lists with
        # parallel sets so membership is O(1) instead of an O(n) list scan.
        families_seen = set()
        desc_memo = {}
        effect_seen, prop_seen, flora_seen = set(), set(), set()
        lcp_props = self.exemplar.GetPropRange(2297284864, 2297286144)
        for lcp in range(2297284864, 2297286144):
            values = lcp_props.get(lcp)
            if values is None:
                break
            type_flag = values[0]
            if type_flag != 1 and type_flag != 4:
                continue
            propID = values[12]
            memo_key = (type_flag, propID)
            if memo_key in desc_memo:
                selectedDesc = desc_memo[memo_key]
            else:
                selectedDesc = self._resolve_lot_desc(type_flag, propID, families_seen)
                desc_memo[memo_key] = selectedDesc
            if selectedDesc is None:
                continue
            if type_flag == 1 and IsEffectDesc(selectedDesc):
                if selectedDesc not in effect_seen:
                    effect_seen.add(selectedDesc)
                    self.lotEffectDescs.append(selectedDesc)
            elif type_flag == 1:
                if selectedDesc not in prop_seen:
                    prop_seen.add(selectedDesc)
                    self.lotPropDescs.append(selectedDesc)
            elif selectedDesc not in flora_seen:
                flora_seen.add(selectedDesc)
                self.lotFloraDescs.append(selectedDesc)

        if self.LETools:
            self.LETools.ReBuildLot()
        self.RefreshAssetBrowser()
        return

    def LoadPropModel(self, propID):
        selectedDesc = None
        if propID in self.virtualDAT.categories:
            selectedDesc = self._selected_family_desc(propID)
            if selectedDesc is not None:
                name = self.virtualDAT.categories[propID].Name
                if propID not in self.lotFamiliesPropID:
                    self.lotFamiliesPropID.append(propID)
            else:
                return (None, 'not found')
        if selectedDesc is None:
            possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == propID, self.virtualDAT.categories[210746660].descriptors)
            for desc in possibles:
                selectedDesc = desc
                name = selectedDesc.name
                break
        if selectedDesc is None:
            effect_category = self.virtualDAT.categories.get(EFFECT_CATEGORY_ID)
            if effect_category is not None:
                possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == propID, effect_category.descriptors)
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
        rkt5 = selectedDesc.exemplar.GetProp(662775845)
        if IsEffectDesc(selectedDesc):
            if selectedDesc not in self.lotEffectDescs:
                self.lotEffectDescs.append(selectedDesc)
        elif selectedDesc not in self.lotPropDescs:
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
        if propID in self.virtualDAT.categories:
            selectedDesc = self._selected_family_desc(propID)
            if selectedDesc is not None:
                name = self.virtualDAT.categories[propID].Name
                if propID not in self.lotFamiliesPropID:
                    self.lotFamiliesPropID.append(propID)
            else:
                return (None, 'not found')
        if selectedDesc is None:
            possibles = filter(lambda desc: desc.exemplar.entry.tgi[2] == propID, self.virtualDAT.categories[1830116951].descriptors)
            for desc in possibles:
                selectedDesc = desc
                name = selectedDesc.name
                break

        if selectedDesc is None:
            return (None, 'not found')
        if selectedDesc not in self.lotFloraDescs:
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
            propViewer.lighting_kind = 'flora'
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

    def _collect_effect_model_ids(self):
        """Model IIDs in the effect category, resolved once per PreCache."""
        ids = set()
        effect_category = self.virtualDAT.categories.get(EFFECT_CATEGORY_ID)
        if effect_category is not None:
            for desc in effect_category.descriptors:
                if IsEffectDesc(desc):
                    ids.add(desc.exemplar.entry.tgi[2])
        return ids

    def PreCacheObject(self, values):
        if values[0] == 0:
            self.building = values
            self.building.append(self.LoadBuildingModel(values[12]))
        if values[0] == 1:
            is_effect = values[12] in self._effectModelIds
            cached = self._propViewerByModel.get(values[12])
            if cached is not None:
                viewer, name = cached
            else:
                viewer, name = self.LoadPropModel(values[12])
                self._propViewerByModel[values[12]] = (viewer, name)
            values.append(name)
            self.props.append(values)
            self.propViewers.append(viewer)
            if is_effect:
                self.effects.append(values)
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
            cached = self._floraViewerByModel.get(values[12])
            if cached is not None:
                viewer, name = cached
            else:
                viewer, name = self.LoadFloraModel(values[12])
                self._floraViewerByModel[values[12]] = (viewer, name)
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
            self.te.append(self._cached_transit_with_path(values))

    def PreCache(self):
        self.glCanvas2D.SetCurrent()
        self.LEAnimMissing = ResourceViewer(662775840, (698733036, 707025145, 743768064), self.virtualDAT, None)
        self.LEAnimMissing.PreLoad(self.virtualDAT, self.s3DTexturesHolder)
        self.textures = {}
        self.texBases = []
        self.texOverlays = []
        self.building = None
        self.buildingViewer = []
        self.lotFamiliesPropID = []
        self.lotPropDescs = []
        self.lotEffectDescs = []
        self.lotFloraDescs = []
        self.props = []
        self.effects = []
        self.propViewers = []
        self.floras = []
        self.floraViewers = []
        self.waters = []
        self.lands = []
        self.te = []
        self._sc4path_cache = {}
        # Dedup: a lot can repeat the same prop/flora model hundreds of times.
        # Map model IID -> (viewer, name) so each unique model is loaded once
        # instead of rescanning the growing prop/flora list per object (O(n^2)).
        self._propViewerByModel = {}
        self._floraViewerByModel = {}
        # Effect membership is a fixed set of model IIDs; resolve it once rather
        # than rescanning the effect category's descriptors for every prop.
        self._effectModelIds = self._collect_effect_model_ids()
        base, roadTex = self.GetTextures(641146880)
        self.textures[641146880] = [roadTex, base]
        base, waterLandTex = self.GetTexturesLE(3412818905, 1802442183)
        self.textures[1802442183] = [waterLandTex, base]
        self.lotOverTextures = []
        self.lotBaseTextures = []
        self.Preload_TE_Tex()
        self.Preload_Background_Tex2()
        lcp_props = self.exemplar.GetPropRange(2297284864, 2297286144)
        for lcp in range(2297284864, 2297286144):
            values = lcp_props.get(lcp)
            if values is None:
                break
            values = values[:]
            self.PreCacheObject(values)

        return

    def _cached_transit_with_path(self, values):
        values = ensure_transit_values(values[:])
        data = cached_transit(values)
        data.append(self._resolve_sc4path_info(values[15]))
        return data

    def _update_cached_transit(self, values):
        replacement = self._cached_transit_with_path(values)
        for idx, item in enumerate(self.te):
            if len(item) > 5 and item[5] == values[11]:
                self.te[idx] = replacement
                return
        self.te.append(replacement)

    def _resolve_sc4path_info(self, iid):
        iid = int(iid) & 0xFFFFFFFF
        if iid == 0:
            return {"iid": 0, "path_file": None, "entry": None, "error": ""}
        cached = self._sc4path_cache.get(iid)
        if cached is not None:
            return cached
        info = {"iid": iid, "path_file": None, "entry": None, "error": "missing"}
        entry = self._find_sc4path_entry(iid)
        if entry is not None:
            info["entry"] = entry
            try:
                entry.read_file(None, True, True)
                info["path_file"] = parse_sc4path(entry.content)
                info["error"] = ""
            except SC4PathParseError as exc:
                info["error"] = "parse error: %s" % exc
            except Exception as exc:
                logger.exception("Failed to load SC4Path 0x%08X", iid)
                info["error"] = "load error: %s" % exc
            finally:
                entry.rawContent = None
                entry.content = None
        self._sc4path_cache[iid] = info
        return info

    def _find_sc4path_entry(self, iid):
        for gid in SC4PATH_GIDS:
            entry = self.virtualDAT.getEntry(SC4PATH_TYPE, gid, iid)
            if entry is not None:
                return entry
        return None

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
        self._apply_preview_night_mode()
        self._update_temporal_controls()
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
        glEnable(GL_MULTISAMPLE)  # anti-aliased edges when an MSAA buffer exists
        glDisable(GL_CULL_FACE)

    def _request_draw(self):
        """Queue a frame and let wx coalesce bursts of UI events.

        Rendering both lot views synchronously from mouse/key handlers blocks
        delivery of subsequent input.  During drags it also duplicates work:
        MyCanvasBase already invalidates the canvas, so the direct draw was
        followed by another EVT_PAINT frame.  Invalidating here keeps updates
        responsive while guaranteeing at most one pending paint per canvas.
        """
        canvas = self.glCanvas2D
        if canvas:
            canvas.Refresh(False)

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
        if os.environ.get('SC4PIM_GL_DEBUG') and getattr(self, '_gl_dbg_panel', None) != self.panel:
            self._gl_dbg_panel = self.panel
            logger.debug('lot on_draw: panel=%s ClientSize=%s ContentScaleFactor=%s',
                         self.panel, tuple(canvas.GetClientSize()),
                         canvas.GetContentScaleFactor())
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

    def DrawQuad(self, x, y, flag, texID, bAlpha, bHighlighted=False,
                 tint=(1.0, 1.0, 1.0, 1.0)):
        zoom = self.zoom
        if zoom == 5:
            zoom = 4
        try:
            texture = self.textures[texID][0][zoom]
        except Exception:
            texture = None
        if bAlpha:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        else:
            glDisable(GL_BLEND)
        offsetX = x * 16 - self.lotSizeXOffset
        offsetY = y * 16 - self.lotSizeYOffset
        tex_coords = texture_coords_for_flag(flag)
        primitives = self.glCanvas2D.renderer.primitives
        points = (
            (offsetX, offsetY + 16, 0), (offsetX, offsetY, 0),
            (offsetX + 16, offsetY, 0), (offsetX + 16, offsetY + 16, 0),
        )
        if texture is not None:
            sampler = self.glCanvas2D.renderer.samplers.get(
                GL_NEAREST, GL_NEAREST, GL_REPEAT, GL_REPEAT,
            )
            primitives.quad(points, self._render_context.mvp, color=tint,
                            uvs=tex_coords, texture=texture, sampler=sampler)
        if bHighlighted:
            glEnable(GL_BLEND)
            glBlendFunc(GL_ONE, GL_ONE)
            primitives.quad(points, self._render_context.mvp, color=(1, 0, 0, 1))
            glDisable(GL_BLEND)

    def DrawQuads(self, records, bAlpha, tint=(1.0, 1.0, 1.0, 1.0)):
        """Batch 2D lot tiles by texture when their order is interchangeable."""
        self._draw_tile_batches(records, bAlpha, tint, three_d=False)

    def DrawQuads3D(self, records, bAlpha):
        """Batch coplanar 3D lot tiles by texture."""
        self._draw_tile_batches(records, bAlpha, (*self._lot_environment_light(), 1.0),
                                three_d=True)

    def _draw_tile_batches(self, records, bAlpha, tint, three_d):
        if not records:
            return
        zoom = min(self.zoom, 4)
        sampler = self.glCanvas2D.renderer.samplers.get(
            GL_NEAREST, GL_NEAREST, GL_REPEAT, GL_REPEAT,
        )
        # Reordering opaque tiles is always safe. Alpha tiles are safe when no
        # two occupy the same cell; overlapping overlays retain source order.
        cells = [(record[0], record[1]) for record in records]
        can_reorder = not bAlpha or len(cells) == len(set(cells))
        groups = []
        by_texture = {}
        for record in records:
            x, y, flag, tex_id = record[:4]
            try:
                texture = self.textures[tex_id][0][zoom]
            except Exception:
                continue
            key = gl_texture_name(texture)
            if can_reorder:
                group = by_texture.get(key)
                if group is None:
                    group = [texture, [], []]
                    by_texture[key] = group
                    groups.append(group)
            elif groups and gl_texture_name(groups[-1][0]) == key:
                group = groups[-1]
            else:
                group = [texture, [], []]
                groups.append(group)
            offset_x = x * 16 - self.lotSizeXOffset
            offset_y = y * 16 - self.lotSizeYOffset
            if three_d:
                points = (
                    (offset_x, 0, offset_y + 16), (offset_x, 0, offset_y),
                    (offset_x + 16, 0, offset_y), (offset_x + 16, 0, offset_y + 16),
                )
            else:
                points = (
                    (offset_x, offset_y + 16, 0), (offset_x, offset_y, 0),
                    (offset_x + 16, offset_y, 0), (offset_x + 16, offset_y + 16, 0),
                )
            group[1].append(points)
            group[2].append(texture_coords_for_flag(flag))
        if bAlpha:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        else:
            glDisable(GL_BLEND)
        for texture, quads, uv_quads in groups:
            self.glCanvas2D.renderer.primitives.quad_batch(
                quads, self._render_context.mvp, color=tint,
                uv_quads=uv_quads, texture=texture, sampler=sampler,
            )

    def DrawHighLight(self, minx, miny, maxx, maxy, color=(1, 0, 0)):
        offsetX = -self.lotSizeXOffset
        offsetY = -self.lotSizeYOffset
        glDisable(GL_BLEND)
        self.glCanvas2D.renderer.primitives.rect(
            minx + offsetX, miny + offsetY, maxx + offsetX, maxy + offsetY,
            self._render_context.mvp, color=(*color, 1.0), filled=False,
        )

    def DrawQuadsHighLight(self, quads, color=(1, 0, 0)):
        offsetX = -self.lotSizeXOffset
        offsetY = -self.lotSizeYOffset
        glDisable(GL_BLEND)
        for quad in quads:
            self.glCanvas2D.renderer.primitives.rect(
                quad[0] + offsetX, quad[1] + offsetY,
                quad[2] + offsetX, quad[3] + offsetY,
                self._render_context.mvp, color=(*color, 1.0), filled=False,
            )

    def DrawQuadColor(self, flag, minx, miny, maxx, maxy, color, bMissing):
        offsetX = -self.lotSizeXOffset
        offsetY = -self.lotSizeYOffset
        minx, maxx = minx + offsetX, maxx + offsetX
        miny, maxy = miny + offsetY, maxy + offsetY
        primitives = self.glCanvas2D.renderer.primitives
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        primitives.rect(minx, miny, maxx, maxy, self._render_context.mvp, color=color)
        glDisable(GL_BLEND)
        primitives.rect(
            minx, miny, maxx, maxy, self._render_context.mvp,
            color=(color[0], color[1], color[2], 1.0), filled=False,
        )
        try:
            texture = self.textures[1802442183][0][0]
        except Exception:
            texture = None
        if texture is not None:
            points = ((minx, maxy, 0), (minx, miny, 0),
                      (maxx, miny, 0), (maxx, maxy, 0))
            sampler = self.glCanvas2D.renderer.samplers.get(
                GL_NEAREST, GL_NEAREST, GL_REPEAT, GL_REPEAT,
            )
            glEnable(GL_BLEND)
            primitives.quad(
                points, self._render_context.mvp,
                uvs=texture_coords_for_flag(flag), texture=texture, sampler=sampler,
            )
            glDisable(GL_BLEND)
        if bMissing:
            self.missingLines.extend(((minx, miny), (maxx, maxy),
                                      (minx, maxy), (maxx, miny)))

    def Draw2D(self):
        self.missingLines = []
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        self.size = self.glCanvas2D.GetClientSize()
        scale = self.glCanvas2D.GetContentScaleFactor()
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
        viewport = (int(s * scale), 0, int(w * scale), int(h * scale))
        glViewport(*viewport)
        projection = SC4Matrix.ortho(-valW, valW, -valH, valH, 40000, -40000)
        zoom = self.zoom
        scaling = LotEditorWin.zoomScale[zoom] * self.viewScale
        rot2D = -self.rotation * 90.0
        model = SC4Matrix.scale(scaling, -scaling, scaling)
        model = model @ SC4Matrix.translate(-self.posx, -self.posy, -self.posz)
        model = model @ SC4Matrix.rotate_z(rot2D)
        self._render_context = TransformStack(projection, model)
        self._render_viewport = viewport
        px, py, pz = self.UnProject(self.glCanvas2D.mouseX, self.glCanvas2D.mouseY)
        lx = self.lotSizeXOffset
        ly = self.lotSizeYOffset
        px += lx
        py += ly
        bUnderMouse = False
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
            self.DrawQuads(self.texBases, False)

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
            self.DrawQuads(self.texOverlays, True)

        if self.modeDisplay & MODE_CONSTRAINT_ONLY:
            constraint_layers = (
                (True, self.waters, LAYER_WATER),
                (False, self.lands, LAYER_LAND),
            )
            for is_water, constraints, layer_key in constraint_layers:
                if not self._is_layer_visible('2d', layer_key):
                    continue
                tint = (0.2, 0.2, 0.8, 1.0) if is_water else (0.8, 0.5, 0.2, 1.0)
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
                records = [(item[0], item[1], item[2], 1802442183) for item in constraints]
                self.DrawQuads(records, True, tint=tint)

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
                        status = '%s %s' % (network_label(texData[3][0]), mask_label(texData[4]))
                        path_status = transit_path_status(texData)
                        if path_status and path_status != "No SC4Path ID":
                            status = '%s - %s' % (status, path_status)
                        self.SetStatusText(status, 5)
                        self.highlighted = [texData[5]]
                        self.quadHighs = [[minx, miny, maxx, maxy]]
                draw_transit_overlay(self, texData, self.modeEdit == MODE_EDIT_TRANSIT, rot2D, scaling)

        if self.modeDisplay & MODE_TE_ONLY and self._is_layer_visible('2d', LAYER_SC4PATHS):
            for texData in self.te:
                draw_sc4path_overlay_2d(self, texData, self.modeEdit == MODE_EDIT_TRANSIT)

        if self._is_layer_visible('2d', LAYER_ROAD_EDGES):
            road_edges = []
            if self.exemplar.GetProp(1246398704)[0] & 8:
                for x in range(self.exemplar.GetProp(2297284496)[0]):
                    road_edges.append((x, self.exemplar.GetProp(2297284496)[1], 1, 641146880))

            if self.exemplar.GetProp(1246398704)[0] & 1:
                for y in range(self.exemplar.GetProp(2297284496)[1]):
                    road_edges.append((-1, y, 0, 641146880))

            if self.exemplar.GetProp(1246398704)[0] & 4:
                for y in range(self.exemplar.GetProp(2297284496)[1]):
                    road_edges.append((self.exemplar.GetProp(2297284496)[0], y, 0, 641146880))
            self.DrawQuads(road_edges, True)

        if self.snapSize != 0 and self._is_layer_visible('2d', LAYER_SNAP_GRID):
            positions = self.snapGrids + numpy.array(
                (-self.lotSizeXOffset, -self.lotSizeYOffset), dtype=numpy.float32,
            )
            self.glCanvas2D.renderer.primitives.draw(
                GL_LINES, positions, self._render_context.mvp,
                color=(0.5, 0, 0.2, 1),
            )
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
                    self._draw_text(ToCoord(self.building[3]) - lx, ToCoord(self.building[5]) - ly,
                                    '%.02f' % ToCoord(self.building[4]), rot2D)
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
                    self._draw_text(ToCoord(prop[3]) - lx, ToCoord(prop[5]) - ly,
                                    '%.02f' % ToCoord(prop[4]), rot2D)

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
                    self._draw_text(ToCoord(prop[3]) - lx, ToCoord(prop[5]) - ly,
                                    '%.02f' % ToCoord(prop[4]), rot2D)

        if self._is_layer_visible('2d', LAYER_SELECTION):
            self.DrawQuadsHighLight(self.quadHighs)
            self.DrawQuadsHighLight(self.quadSelected, (1, 1, 1))
            if self.dragQuad is not None:
                self.DrawHighLight(self.dragQuad[0], self.dragQuad[1], self.dragQuad[2], self.dragQuad[3], (1,
                                                                                                            1,
                                                                                                            1))
        if self._is_layer_visible('2d', LAYER_MISSING):
            positions = numpy.asarray(self.missingLines, dtype=numpy.float32)
            if len(positions):
                self.glCanvas2D.renderer.primitives.draw(
                    GL_LINES, positions, self._render_context.mvp, color=(1, 0, 0, 1),
                )
        if self._is_layer_visible('2d', LAYER_CARDINALS):
            self.DrawCardinalLabels(rot2D, scaling)
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
        for label, lx, ly in (
            (LEXFacingNorth, -1.0, y + margin),
            (LEXFacingSouth, -1.0, -y - margin),
            (LEXFacingEast, x + margin, -1.0),
            (LEXFacingWest, -x - margin, -1.0),
        ):
            self._draw_text(lx, ly, label, rot2D, color=(1.0, 0.85, 0.2, 1.0), scale=0.3)

    def _draw_text(self, x, y, text, rot2D, color=(1.0, 1.0, 1.0, 1.0), scale=0.18):
        # flip_y keeps text upright: the 2D model matrix negates Y (see Draw2D),
        # which would otherwise render every glyph vertically mirrored.
        self.glCanvas2D.renderer.primitives.text(
            x, y, text, self._render_context.mvp,
            color=color, scale=scale, rotation=-rot2D, flip_y=True,
        )

    def DrawBackGround2(self, x=0, y=0):
        if not getattr(self, 'BackTextures', None):
            return
        zoom = self.zoom
        LotEditorWin.zoomScale3D[zoom]
        if zoom == 5:
            zoom = 4
        if self.BackTextures[zoom] is not None and self.BackTextureSizes[zoom] is not None:
            glDisable(GL_DEPTH_TEST)
            glDisable(GL_BLEND)
            offsetX = x - self.lotSizeXOffset
            offsetY = y - self.lotSizeYOffset
            env_light = self._lot_environment_light()
            scales = [9.2, 4.6, 2.3, 1.0, 1.0 / 2.0]
            local = SC4Matrix.rotate_y(-self.ry) @ SC4Matrix.rotate_x(self.rx)
            local = local @ SC4Matrix.scale(scales[zoom], scales[zoom], -scales[zoom])
            local = local @ SC4Matrix.translate(offsetX, 0, offsetY)
            w = self.BackTextureSizes[zoom][0] / 3.5
            h = self.BackTextureSizes[zoom][1] / 3.5
            sampler = self.glCanvas2D.renderer.samplers.get(
                GL_NEAREST, GL_NEAREST, GL_REPEAT, GL_REPEAT,
            )
            self.glCanvas2D.renderer.primitives.quad(
                ((0, -0.1, 0), (0, -0.1, h), (w, -0.1, h), (w, -0.1, 0)),
                self._render_context.projection @ self._render_context.model @ local,
                color=(*env_light, 1.0),
                uvs=((0, 1), (0, 0), (1, 0), (1, 1)),
                texture=self.BackTextures[zoom], sampler=sampler,
            )
        return

    def DrawQuad3D(self, x, y, flag, texID, bAlpha):
        zoom = self.zoom
        if zoom == 5:
            zoom = 4
        try:
            texture = self.textures[texID][0][zoom]
        except Exception:
            return

        if bAlpha:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        else:
            glDisable(GL_BLEND)
        offsetX = x * 16 - self.lotSizeXOffset
        offsetY = y * 16 - self.lotSizeYOffset
        tex_coords = texture_coords_for_flag(flag)
        env_light = self._lot_environment_light()
        sampler = self.glCanvas2D.renderer.samplers.get(
            GL_NEAREST, GL_NEAREST, GL_REPEAT, GL_REPEAT,
        )
        self.glCanvas2D.renderer.primitives.quad(
            ((offsetX, 0, offsetY + 16), (offsetX, 0, offsetY),
             (offsetX + 16, 0, offsetY), (offsetX + 16, 0, offsetY + 16)),
            self._render_context.mvp, color=(*env_light, 1.0),
            uvs=tex_coords, texture=texture, sampler=sampler,
        )

    def _flush_model_batches(self, batches):
        if not batches:
            return
        for (mesh, _prelit), batch in list(batches.items()):
            lighting_state, mvps, normals = batch
            for start in range(0, len(mvps), 32):
                mesh.draw_instanced(
                    self.s3DTexturesHolder, self._ensure_s3d_shader_program(), lighting_state,
                    mvps[start:start + 32], normals[start:start + 32],
                )
        batches.clear()

    def _submit_s3d_model(self, mesh, shader_program, lighting_state, batches,
                          shadow=False):
        if shadow:
            # Shadow casters are flattened per-draw; never batch (each has its
            # own MVP) and route through the shadow GL state path.
            mesh.draw(
                self.s3DTexturesHolder, shader_program, lighting_state,
                self._render_context.mvp, self._render_context.normal_matrix,
                shadow=True,
            )
            return
        # Blended meshes depend on source order. Treat them as barriers while
        # batching opaque and alpha-tested repetitions around them.
        batchable = batches is not None and not any(
            material.get('flags', 0) & 16 for material in getattr(mesh, 'matBlocks', ())
        )
        if batchable:
            key = (mesh, bool(lighting_state.get('prelit')))
            batch = batches.get(key)
            if batch is None:
                batch = [lighting_state, [], []]
                batches[key] = batch
            batch[1].append(self._render_context.mvp.copy())
            batch[2].append(self._render_context.normal_matrix.copy())
            return
        if batches is not None:
            self._flush_model_batches(batches)
        mesh.draw(
            self.s3DTexturesHolder, shader_program, lighting_state,
            self._render_context.mvp, self._render_context.normal_matrix,
        )

    def DrawModel(self, rtk, resource, rot2D, rot, rotFlag, zoom, viewZoom=None,
                  model_batches=None, shadow=False):
        if viewZoom is None:
            viewZoom = zoom
        if resource is None:
            return
        if resource.viewingData == []:
            return
        # Props with exemplar property 0x49C9C93C ("Nighttime State Change")
        # render a different model state at night. The property's value is the
        # destination state index; fall through to state 0 if it points out
        # of range (e.g. an RKT0/1 prop with only one viewing entry).
        state_count = getattr(resource, 'stateCount', len(resource.viewingData))
        state_idx = 0
        if getattr(self, 'nightMode', False):
            night_state = int(getattr(resource, 'night_state', 0) or 0)
            if 0 < night_state < state_count:
                state_idx = night_state
        # Two-state props with a Prop Time of Day / simulator-date schedule swap
        # to their dormant state 1 model when out of window, matching the game's
        # cSC4PropOccupant timer mask, instead of disappearing.
        if state_idx == 0:
            temporal = self._temporal_state_for_exemplar(
                getattr(resource, 'lighting_exemplar', None))
            state_idx = timer_state_index(temporal, state_count)
        shader_program = (
            self._ensure_shadow_program() if shadow else self._ensure_s3d_shader_program()
        )
        lighting_state = self._lot_lighting_state(
            getattr(resource, 'lighting_exemplar', None),
            getattr(resource, 'lighting_kind', 'model'),
        )
        # A state can contain more than one model (e.g. a lamppost's night state
        # is the pole plus its light cone). Draw every model of the state, each
        # at its own per-record offset; props without grouped states fall back
        # to the single representative model and the caller's rtk offset.
        state_models = getattr(resource, 'stateModels', None)
        if state_models is not None and state_idx < len(state_models):
            members = state_models[state_idx]
        else:
            members = [(resource.viewingData[state_idx], None)]
        for model, raw_offset in members:
            if raw_offset is None:
                offset = rtk
            else:
                offset = (ToCoord(raw_offset[0]), ToCoord(raw_offset[1]),
                          ToCoord(raw_offset[2]))
            self._draw_state_member(model, offset, rot2D, rot, rotFlag, zoom,
                                    shader_program, lighting_state, model_batches,
                                    shadow=shadow)
        return

    def _draw_state_member(self, what, offset, rot2D, rot, rotFlag, zoom,
                           shader_program, lighting_state, model_batches, shadow=False):
        render = self._render_context
        if what.__class__ == SC4Model:
            rotMapping = [180, -90, 0, 90]
            with render.pushed():
                render.rotate(-rotMapping[rotFlag], 0, 1, 0)
                render.translate(offset[0], offset[1], offset[2])
                render.rotate(rotMapping[rotFlag], 0, 1, 0)
                render.rotate(-rot2D, 0, 1, 0)
                self._submit_s3d_model(
                    what.s3dMeshes[zoom][rot], shader_program, lighting_state, model_batches,
                    shadow=shadow,
                )
        elif what.__class__ == SC4Model1MeshPerZoom:
            self._submit_s3d_model(
                what.s3dMeshes[zoom], shader_program, lighting_state, model_batches,
                shadow=shadow,
            )
        elif what.__class__ == SC4ModelMesh:
            rotMapping = [180, -90, 0, 90]
            with render.pushed():
                render.rotate(rotMapping[rotFlag], 0, 1, 0)
                render.translate(offset[0], offset[1], offset[2])
                self._submit_s3d_model(
                    what.mainMesh, shader_program, lighting_state, model_batches,
                    shadow=shadow,
                )
        elif what.__class__ == ATC:
            # ATC billboards are screen-facing animated sprites; skip them as
            # shadow casters (no meaningful planar silhouette).
            if shadow:
                return
            if model_batches is not None:
                self._flush_model_batches(model_batches)
            glDisable(GL_DEPTH_TEST)
            rotMapping = [1, 0, 3, 2]
            if what.draw_le(zoom, rotMapping[rot]):
                billboard = render.model.copy()
                billboard[0:3, 0:3] = numpy.diag((1.0, 1.0, -1.0))
                billboard = billboard @ SC4Matrix.scale(1 / 14.0, 1 / 14.0, 1 / 14.0)
                what.DrawGL(
                    self.s3DTexturesHolder, self.glCanvas2D.renderer,
                    render.projection, billboard,
                )
            glEnable(GL_DEPTH_TEST)
        return

    def _draw_shadow_pass(self, rot2D, rotation, rotMapping, assetZoom, viewZoom,
                          lotSizeXOver, lotSizeYOver):
        """Render building/prop/flora shadows as planar-projected, alpha-masked
        decals on the ground. Mirrors SC4's projective shadow decal using the
        models' real S3D geometry + texture alpha; see
        .claude/docs/sc4-shadow-rendering.md."""
        prog = self._ensure_shadow_program()
        profile = getattr(self, 'lightingProfile', None)
        prog.shadow_color = profile.shadow_color if profile is not None else self.SHADOW_COLOR
        prog.shadow_strength = (
            profile.shadow_strength if profile is not None else self.SHADOW_STRENGTH
        )
        flatten = self._shadow_flatten_matrix()
        render = self._render_context

        def cast(record, viewer):
            with render.pushed():
                offsetX = ToCoord(record[3]) - lotSizeXOver / 2
                offsetZ = ToCoord(record[5]) - lotSizeYOver / 2
                rtk4 = self.rtk4Offsets.get(record[12], (0, 0, 0))
                # Flatten in lot space (after the camera, before placement), then
                # place the caster; the flatten collapses it onto the y=0 ground.
                render.model = render.model @ flatten
                render.translate(offsetX, ToCoord(record[4]), offsetZ)
                self.DrawModel(rtk4, viewer, rot2D,
                               (rotation + rotMapping[record[2]]) % 4, record[2],
                               assetZoom, viewZoom, shadow=True)

        # Shadows write depth (GL_LESS, set per-mesh in S3DReader) so overlapping
        # faces/casters darken each pixel once instead of multiply-stacking.
        # Polygon offset pulls the y=0 shadow plane just in front of the coplanar
        # ground so it wins without z-fighting.
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_TRUE)
        glEnable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(-1.0, -1.0)
        try:
            if self._is_layer_visible('3d', LAYER_BUILDING):
                try:
                    if self.buildingViewer[self.currentBuilding] is not None:
                        cast(self.building, self.buildingViewer[self.currentBuilding])
                except IndexError:
                    pass
            if self._is_layer_visible('3d', LAYER_PROPS):
                for prop, propViewer in zip(self.props, self.propViewers):
                    if propViewer is None or propViewer.viewingData == []:
                        continue
                    if not self._viewer_is_temporally_active(propViewer):
                        continue
                    if propViewer.viewingData[0].__class__ == ATC:
                        continue
                    cast(prop, propViewer)
            if self._is_layer_visible('3d', LAYER_FLORA):
                for flora, floraViewer in zip(self.floras, self.floraViewers):
                    if floraViewer is None or floraViewer.viewingData == []:
                        continue
                    if not self._viewer_is_temporally_active(floraViewer):
                        continue
                    if floraViewer.viewingData[0].__class__ == ATC:
                        continue
                    cast(flora, floraViewer)
        finally:
            glPolygonOffset(0.0, 0.0)
            glDisable(GL_POLYGON_OFFSET_FILL)
            glDepthFunc(GL_LEQUAL)   # restore default for later draws
            glDepthMask(GL_TRUE)
            glDisable(GL_BLEND)

    def Draw3DBackdrop(self, valW, valH):
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        env_light = self._lot_environment_light()
        low = (0.15 * env_light[0], 0.17 * env_light[1], 0.20 * env_light[2], 1)
        high = (0.36 * env_light[0], 0.39 * env_light[1], 0.42 * env_light[2], 1)
        self.glCanvas2D.renderer.primitives.quad(
            ((-valW, -valH, 0), (valW, -valH, 0),
             (valW, valH, 0), (-valW, valH, 0)),
            self._render_context.projection,
            colors=(low, low, high, high),
        )

    def Draw3D(self):
        viewZoom = self.zoom
        assetZoom = min(viewZoom, 4)
        if assetZoom == 4 or assetZoom == 3:
            angleX = 45
        elif assetZoom == 2:
            angleX = 40
        elif assetZoom == 1:
            angleX = 35
        else:
            angleX = 30
        self.size = self.glCanvas2D.GetClientSize()
        scale = self.glCanvas2D.GetContentScaleFactor()
        full_w = self.size[0]
        if self.panel == 3:
            w = self.size[0] // 2
        elif self.panel == 1:
            w = self.size[0]
        else:
            return
        h = self.size[1]
        # Frame the 3D view by the FULL canvas width so a split panel shows the
        # same world span as the single-pane view -- it's just rendered into
        # half the pixels. Without this the half-width panel keeps the single-
        # pane zoom but only shows ~half the tiles, so tall iso-projected models
        # (which spread their height sideways) overflow the narrow strip. valH
        # is derived from the viewport aspect so pixels stay square. In single-
        # pane view full_w == w, so this is identical to the old formula.
        valW = full_w * 2.0 / 60.0
        valH = valW * h / w
        viewport = (0, 0, int(w * scale), int(h * scale))
        glViewport(*viewport)
        projection = SC4Matrix.ortho(-valW, valW, -valH, valH, 40000, -40000)
        self._render_context = TransformStack(projection)
        self._render_viewport = viewport
        if os.environ.get('SC4PIM_GL_DEBUG') and getattr(self, '_gl_dbg_3d', None) != self.panel:
            self._gl_dbg_3d = self.panel
            from OpenGL.GL import GL_VIEWPORT, glGetIntegerv
            vp = tuple(glGetIntegerv(GL_VIEWPORT))
            logger.debug('Draw3D: panel=%s w=%s h=%s scale=%s valW=%.3f valH=%.3f '
                         'GL_VIEWPORT=%s px/unit_x=%.3f px/unit_y=%.3f',
                         self.panel, w, h, scale, valW, valH, vp,
                         vp[2] / (2 * valW) if valW else 0,
                         vp[3] / (2 * valH) if valH else 0)
        self.Draw3DBackdrop(valW, valH)
        rotation = self.rotation
        rot2D = rotation * 90.0
        self.rx = angleX
        self.ry = rot2D - 22.5
        self.rz = 0
        scaling = LotEditorWin.zoomScale3D[viewZoom]
        model = SC4Matrix.scale(scaling, scaling, -scaling)
        model = model @ SC4Matrix.translate(-self.pos3Dx, -self.pos3Dy, -self.pos3Dz)
        model = model @ SC4Matrix.rotate_x(self.rx)
        model = model @ SC4Matrix.rotate_y(self.ry)
        self._render_context.model = model
        # Draw the optional ground background (offset by the user's Shift+drag
        # position), then re-enable depth testing -- DrawBackGround2 disables
        # it -- for the lot's own texture quads.
        background_drawn = self._is_layer_visible('3d', LAYER_BACKGROUND)
        if background_drawn:
            self.DrawBackGround2(self.BackPosx, self.BackPosy)
        glEnable(GL_DEPTH_TEST)
        if self._is_layer_visible('3d', LAYER_BASE):
            self.DrawQuads3D(self.texBases, False)

        if self._is_layer_visible('3d', LAYER_OVERLAY):
            self.DrawQuads3D(self.texOverlays, True)

        # Road edge overlays clash with a custom ground background, so skip
        # drawing them while background mode is on.
        if self._is_layer_visible('3d', LAYER_ROAD_EDGES) and not background_drawn:
            road_edges = []
            if self.exemplar.GetProp(1246398704)[0] & 8:
                for x in range(self.exemplar.GetProp(2297284496)[0]):
                    road_edges.append((x, self.exemplar.GetProp(2297284496)[1], 1, 641146880))

            if self.exemplar.GetProp(1246398704)[0] & 1:
                for y in range(self.exemplar.GetProp(2297284496)[1]):
                    road_edges.append((-1, y, 0, 641146880))

            if self.exemplar.GetProp(1246398704)[0] & 4:
                for y in range(self.exemplar.GetProp(2297284496)[1]):
                    road_edges.append((self.exemplar.GetProp(2297284496)[0], y, 0, 641146880))
            self.DrawQuads3D(road_edges, True)

        glEnable(GL_DEPTH_TEST)
        rotMapping = [2, 1, 0, 3]
        lotSizeXOver = self.lotSizeXOver
        lotSizeYOver = self.lotSizeYOver
        # Cast shadows onto the ground before the models so the models occlude
        # their own shadows. Optional, driven by the 3D "Shadows" layer toggle.
        if self._is_layer_visible('3d', LAYER_SHADOWS):
            self._draw_shadow_pass(rot2D, rotation, rotMapping, assetZoom, viewZoom,
                                   lotSizeXOver, lotSizeYOver)
        model_batches = {}
        if self._is_layer_visible('3d', LAYER_BUILDING):
            try:
                if self.buildingViewer[self.currentBuilding] is not None:
                    with self._render_context.pushed():
                        offsetX = ToCoord(self.building[3]) - lotSizeXOver / 2
                        offsetZ = ToCoord(self.building[5]) - lotSizeYOver / 2
                        offsetY = 0
                        if self.building[12] in self.rtk4Offsets.keys():
                            rtk4 = self.rtk4Offsets[self.building[12]]
                        else:
                            rtk4 = (0, 0, 0)
                        self._render_context.translate(
                            offsetX, offsetY + ToCoord(self.building[4]), offsetZ,
                        )
                        self.DrawModel(rtk4, self.buildingViewer[self.currentBuilding], rot2D, (rotation + rotMapping[self.building[2]]) % 4, self.building[2], assetZoom, viewZoom, model_batches)
            except IndexError:
                pass

        afters = []
        afterViewers = []
        if self._is_layer_visible('3d', LAYER_PROPS):
            for prop, propViewer in zip(self.props, self.propViewers):
                if not self._viewer_is_temporally_active(propViewer):
                    continue
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
                        with self._render_context.pushed():
                            offsetX = ToCoord(prop[3]) - lotSizeXOver / 2
                            offsetZ = ToCoord(prop[5]) - lotSizeYOver / 2
                            offsetY = 0
                            if prop[12] in self.rtk4Offsets.keys():
                                rtk4 = self.rtk4Offsets[prop[12]]
                            else:
                                rtk4 = (0, 0, 0)
                            self._render_context.translate(
                                offsetX, offsetY + ToCoord(prop[4]), offsetZ,
                            )
                            self.DrawModel(rtk4, tempViewer, rot2D, (rotation + rotMapping[prop[2]]) % 4, prop[2], assetZoom, viewZoom, model_batches)

        if self._is_layer_visible('3d', LAYER_FLORA):
            for prop, propViewer in zip(self.floras, self.floraViewers):
                if not self._viewer_is_temporally_active(propViewer):
                    continue
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
                        with self._render_context.pushed():
                            offsetX = ToCoord(prop[3]) - lotSizeXOver / 2
                            offsetZ = ToCoord(prop[5]) - lotSizeYOver / 2
                            offsetY = 0
                            if prop[12] in self.rtk4Offsets.keys():
                                rtk4 = self.rtk4Offsets[prop[12]]
                            else:
                                rtk4 = (0, 0, 0)
                            self._render_context.translate(
                                offsetX, offsetY + ToCoord(prop[4]), offsetZ,
                            )
                            self.DrawModel(rtk4, tempViewer, rot2D, (rotation + rotMapping[prop[2]]) % 4, prop[2], assetZoom, viewZoom, model_batches)

        self._flush_model_batches(model_batches)
        for prop, propViewer in zip(afters, afterViewers):
            with self._render_context.pushed():
                offsetX = ToCoord(prop[3]) - lotSizeXOver / 2
                offsetZ = ToCoord(prop[5]) - lotSizeYOver / 2
                offsetY = 0
                if prop[12] in self.rtk4Offsets.keys():
                    rtk4 = self.rtk4Offsets[prop[12]]
                else:
                    rtk4 = (0, 0, 0)
                self._render_context.translate(offsetX, offsetY + ToCoord(prop[4]), offsetZ)
                self.DrawModel(rtk4, propViewer, rot2D, (rotation + rotMapping[prop[2]]) % 4, prop[2], assetZoom, viewZoom)

        if self.modeDisplay & MODE_TE_ONLY and self._is_layer_visible('3d', LAYER_SC4PATHS):
            # Final overlay pass: keep the rendered scene, but discard its
            # depth so SC4Path lines remain readable over models and props.
            glClear(GL_DEPTH_BUFFER_BIT)
            for texData in self.te:
                draw_sc4path_overlay_3d(self, texData, self.modeEdit == MODE_EDIT_TRANSIT)

        return

    def Save(self):
        pw, ph = self.glCanvas2D.GetPhysicalSize()
        self.glCanvas2D.SetCurrent()
        # Register any not-yet-seen lot textures, then block until their async
        # decode + GL upload completes so the capture is never of an untextured
        # (red) model. See S3DTexturesHolder.flush_pending.
        self.Draw3D()
        self.s3DTexturesHolder.flush_pending()
        target = RenderTarget(pw, ph, srgb=getattr(self.glCanvas2D, 'srgb', False))
        try:
            with target.bound():
                glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                self.Draw3D()
                w, h = pw // 2 if self.panel == 3 else pw, ph
                data = target.read_rgb(0, 0, w, h)
        finally:
            target.release_gl()
        image = Image.frombytes('RGB', (w, h), data)
        image = image.transpose(Image.FLIP_TOP_BOTTOM)
        image = image.resize((44, 44))
        return image

    def SetMatForUnproj(self):
        self.size = self.glCanvas2D.GetClientSize()
        scale = self.glCanvas2D.GetContentScaleFactor()
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
        viewport = (int(s * scale), 0, int(w * scale), int(h * scale))
        zoom = self.zoom
        scaling = LotEditorWin.zoomScale[zoom] * self.viewScale
        rot2D = -self.rotation * 90.0
        projection = SC4Matrix.ortho(-valW, valW, -valH, valH, 40000, -40000)
        model = SC4Matrix.scale(scaling, -scaling, scaling)
        model = model @ SC4Matrix.translate(-self.posx, -self.posy, -self.posz)
        model = model @ SC4Matrix.rotate_z(rot2D)
        self._render_context = TransformStack(projection, model)
        self._render_viewport = viewport
        return None

    def UnProject(self, x, y):
        """World coords under a logical (top-left origin) window point.

        Picking uses the same explicit CPU matrices as rendering. Window
        coordinates are converted to device pixels for HiDPI framebuffers.
        Mouse and drop events arrive in *logical* pixels, so scale them up and
        flip Y against the device-pixel framebuffer height before unprojecting.
        The caller must have set the matrices (Draw2D / SetMatForUnproj) first.
        """
        scale = self.glCanvas2D.GetContentScaleFactor()
        h = self.size[1]
        return self._render_context.unproject(
            x * scale, (h - y) * scale, 0, self._render_viewport,
        )

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
                            self._update_cached_transit(values)
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
                self._request_draw()
                return
            if self.modeEdit not in [MODE_EDIT_BASETEX, MODE_EDIT_OVERTEX, MODE_EDIT_PROP, MODE_EDIT_FLORA, MODE_EDIT_BUILDING, MODE_EDIT_TRANSIT]:
                return
            self.SetMatForUnproj()
            lx, ly = self.glCanvas2D.last_x, self.glCanvas2D.last_y
            cx, cy = self.glCanvas2D.x, self.glCanvas2D.y
            lx, ly, dz = self.UnProject(lx, ly)
            cx, cy, dz = self.UnProject(cx, cy)
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
        self._request_draw()

    def OnMouseDown(self, evt):
        self.glCanvas2D.on_mouse_down(evt)
        self._texDragTile = None
        self._drag_undo_pending = False
        Xclic, Yclick = self.glCanvas2D.mouseX, self.glCanvas2D.mouseY
        self.SetMatForUnproj()
        px, py, pz = self.UnProject(Xclic, Yclick)
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
        # Batch thumbnail prerender: each model texture is uploaded, rendered
        # once into a tiny downscaled capture and freed, so mipmap generation +
        # anisotropic filtering are wasted work. Skip them for this dedicated
        # (never interactively shown) holder to speed up large plugin folders.
        self.viewer.s3d_textures_holder.mipmaps = False
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
        # First draw registers the model's textures (kicks off async FSH
        # decode); flush_pending then blocks until they are decoded and
        # uploaded so the capture below is never of an untextured (red) model.
        sc4data[1].sc4Model.draw(self.viewer, None, -1, 0)
        self.viewer.s3d_textures_holder.flush_pending()
        w, h = self.viewer.openGLCanvas.GetPhysicalSize()
        self.viewer.openGLCanvas.SetCurrent()
        target = RenderTarget(w, h, srgb=getattr(self.viewer.openGLCanvas, 'srgb', False))
        try:
            with target.bound():
                self.viewer.render_frame()
                data = target.read_rgb()
            # Mirror the just-captured thumbnail into the on-screen preview so
            # the window shows live progress instead of staying blank. read_rgb
            # already resolved MSAA into target.color; a single textured quad is
            # near-free, so batch throughput is unaffected.
            self._present_thumbnail(target.color)
        finally:
            target.release_gl()
        image = Image.frombytes('RGB', (w, h), data)
        image = image.transpose(Image.FLIP_TOP_BOTTOM)
        image.resize((128, 128)).save(os.path.join(os.path.split(sc4data[0])[0] + 'Large', os.path.split(sc4data[0])[1]))
        image = image.resize((64, 64))
        image.save(sc4data[0])
        del image
        del data
        self.viewer.s3d_mesh.FreeAll(self.viewer.s3d_textures_holder)
        return

    def _present_thumbnail(self, color_texture):
        """Blit a captured thumbnail texture to the on-screen preview canvas.

        Drawn as one textured fullscreen quad (not glBlitFramebuffer, which
        rejects a single-sample source into the canvas's multisampled default
        framebuffer). Identity MVP maps the quad to the full viewport; the
        texture's bottom-left GL origin lines up with clip-space (-1, -1), so
        no vertical flip is needed here (unlike the saved PIL image).
        """
        canvas = self.viewer.openGLCanvas
        cw, ch = canvas.GetPhysicalSize()
        if cw <= 0 or ch <= 0:
            return
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glViewport(0, 0, cw, ch)
        glDisable(GL_DEPTH_TEST)
        glClearColor(0.5, 0.5, 0.5, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        sampler = canvas.renderer.samplers.get(
            GL_LINEAR, GL_LINEAR, GL_CLAMP_TO_EDGE, GL_CLAMP_TO_EDGE,
        )
        canvas.renderer.primitives.quad(
            ((-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (-1.0, 1.0, 0.0)),
            SC4Matrix.identity(),
            uvs=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
            texture=color_texture, sampler=sampler,
        )
        canvas.SwapBuffers()

