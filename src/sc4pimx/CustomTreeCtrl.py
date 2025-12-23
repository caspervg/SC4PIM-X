"""Custom tree control for SC4PIM with checkbox and icon support."""
from typing import Tuple, Any

import wx
import zlib
import io

from wx import Size, Image

_NO_IMAGE = -1
_PIXELS_PER_UNIT = 10
_DELAY = 500
TreeItemIcon_Normal = 0
TreeItemIcon_Selected = 1
TreeItemIcon_Expanded = 2
TreeItemIcon_SelectedExpanded = 3
TreeItemIcon_Checked = 0
TreeItemIcon_NotChecked = 1
TreeItemIcon_Flagged = 2
TreeItemIcon_NotFlagged = 3
TR_NO_BUTTONS = wx.TR_NO_BUTTONS
TR_HAS_BUTTONS = wx.TR_HAS_BUTTONS
TR_NO_LINES = wx.TR_NO_LINES
TR_LINES_AT_ROOT = wx.TR_LINES_AT_ROOT
TR_TWIST_BUTTONS = wx.TR_TWIST_BUTTONS
TR_SINGLE = wx.TR_SINGLE
TR_MULTIPLE = wx.TR_MULTIPLE
TR_EXTENDED = wx.TR_EXTENDED
TR_HAS_VARIABLE_ROW_HEIGHT = wx.TR_HAS_VARIABLE_ROW_HEIGHT
TR_EDIT_LABELS = wx.TR_EDIT_LABELS
TR_ROW_LINES = wx.TR_ROW_LINES
TR_HIDE_ROOT = wx.TR_HIDE_ROOT
TR_FULL_ROW_HIGHLIGHT = wx.TR_FULL_ROW_HIGHLIGHT
TR_AUTO_CHECK_CHILD = 16384
TR_AUTO_TOGGLE_CHILD = 32768
TR_AUTO_CHECK_PARENT = 65536
TR_DEFAULT_STYLE = wx.TR_DEFAULT_STYLE
TREE_HITTEST_ABOVE = wx.TREE_HITTEST_ABOVE
TREE_HITTEST_BELOW = wx.TREE_HITTEST_BELOW
TREE_HITTEST_NOWHERE = wx.TREE_HITTEST_NOWHERE
TREE_HITTEST_ONITEMBUTTON = wx.TREE_HITTEST_ONITEMBUTTON
TREE_HITTEST_ONITEMICON = wx.TREE_HITTEST_ONITEMICON
TREE_HITTEST_ONITEMINDENT = wx.TREE_HITTEST_ONITEMINDENT
TREE_HITTEST_ONITEMLABEL = wx.TREE_HITTEST_ONITEMLABEL
TREE_HITTEST_ONITEMRIGHT = wx.TREE_HITTEST_ONITEMRIGHT
TREE_HITTEST_ONITEMSTATEICON = wx.TREE_HITTEST_ONITEMSTATEICON
TREE_HITTEST_TOLEFT = wx.TREE_HITTEST_TOLEFT
TREE_HITTEST_TORIGHT = wx.TREE_HITTEST_TORIGHT
TREE_HITTEST_ONITEMUPPERPART = wx.TREE_HITTEST_ONITEMUPPERPART
TREE_HITTEST_ONITEMLOWERPART = wx.TREE_HITTEST_ONITEMLOWERPART
TREE_HITTEST_ONITEMCHECKICON = 16384
TREE_HITTEST_ONITEM = TREE_HITTEST_ONITEMICON | TREE_HITTEST_ONITEMLABEL | TREE_HITTEST_ONITEMCHECKICON
_StyleTile = 0
_StyleStretch = 1
_rgbSelectOuter = wx.Colour(170, 200, 245)
_rgbSelectInner = wx.Colour(230, 250, 250)
_rgbSelectTop = wx.Colour(210, 240, 250)
_rgbSelectBottom = wx.Colour(185, 215, 250)
_rgbNoFocusTop = wx.Colour(250, 250, 250)
_rgbNoFocusBottom = wx.Colour(235, 235, 235)
_rgbNoFocusOuter = wx.Colour(220, 220, 220)
_rgbNoFocusInner = wx.Colour(245, 245, 245)
_CONTROL_EXPANDED = 8
_CONTROL_CURRENT = 16
__version__ = '0.8'
wxEVT_TREE_BEGIN_DRAG = wx.wxEVT_COMMAND_TREE_BEGIN_DRAG
wxEVT_TREE_BEGIN_RDRAG = wx.wxEVT_COMMAND_TREE_BEGIN_RDRAG
wxEVT_TREE_BEGIN_LABEL_EDIT = wx.wxEVT_COMMAND_TREE_BEGIN_LABEL_EDIT
wxEVT_TREE_END_LABEL_EDIT = wx.wxEVT_COMMAND_TREE_END_LABEL_EDIT
wxEVT_TREE_DELETE_ITEM = wx.wxEVT_COMMAND_TREE_DELETE_ITEM
wxEVT_TREE_GET_INFO = wx.wxEVT_COMMAND_TREE_GET_INFO
wxEVT_TREE_SET_INFO = wx.wxEVT_COMMAND_TREE_SET_INFO
wxEVT_TREE_ITEM_EXPANDED = wx.wxEVT_COMMAND_TREE_ITEM_EXPANDED
wxEVT_TREE_ITEM_EXPANDING = wx.wxEVT_COMMAND_TREE_ITEM_EXPANDING
wxEVT_TREE_ITEM_COLLAPSED = wx.wxEVT_COMMAND_TREE_ITEM_COLLAPSED
wxEVT_TREE_ITEM_COLLAPSING = wx.wxEVT_COMMAND_TREE_ITEM_COLLAPSING
wxEVT_TREE_SEL_CHANGED = wx.wxEVT_COMMAND_TREE_SEL_CHANGED
wxEVT_TREE_SEL_CHANGING = wx.wxEVT_COMMAND_TREE_SEL_CHANGING
wxEVT_TREE_KEY_DOWN = wx.wxEVT_COMMAND_TREE_KEY_DOWN
wxEVT_TREE_ITEM_ACTIVATED = wx.wxEVT_COMMAND_TREE_ITEM_ACTIVATED
wxEVT_TREE_ITEM_RIGHT_CLICK = wx.wxEVT_COMMAND_TREE_ITEM_RIGHT_CLICK
wxEVT_TREE_ITEM_MIDDLE_CLICK = wx.wxEVT_COMMAND_TREE_ITEM_MIDDLE_CLICK
wxEVT_TREE_END_DRAG = wx.wxEVT_COMMAND_TREE_END_DRAG
wxEVT_TREE_STATE_IMAGE_CLICK = wx.wxEVT_COMMAND_TREE_STATE_IMAGE_CLICK
wxEVT_TREE_ITEM_GETTOOLTIP = wx.wxEVT_COMMAND_TREE_ITEM_GETTOOLTIP
wxEVT_TREE_ITEM_MENU = wx.wxEVT_COMMAND_TREE_ITEM_MENU
wxEVT_TREE_ITEM_CHECKING = wx.NewEventType()
wxEVT_TREE_ITEM_CHECKED = wx.NewEventType()
wxEVT_TREE_ITEM_HYPERLINK = wx.NewEventType()
EVT_TREE_BEGIN_DRAG = wx.EVT_TREE_BEGIN_DRAG
EVT_TREE_BEGIN_RDRAG = wx.EVT_TREE_BEGIN_RDRAG
EVT_TREE_BEGIN_LABEL_EDIT = wx.EVT_TREE_BEGIN_LABEL_EDIT
EVT_TREE_END_LABEL_EDIT = wx.EVT_TREE_END_LABEL_EDIT
EVT_TREE_DELETE_ITEM = wx.EVT_TREE_DELETE_ITEM
EVT_TREE_GET_INFO = wx.EVT_TREE_GET_INFO
EVT_TREE_SET_INFO = wx.EVT_TREE_SET_INFO
EVT_TREE_ITEM_EXPANDED = wx.EVT_TREE_ITEM_EXPANDED
EVT_TREE_ITEM_EXPANDING = wx.EVT_TREE_ITEM_EXPANDING
EVT_TREE_ITEM_COLLAPSED = wx.EVT_TREE_ITEM_COLLAPSED
EVT_TREE_ITEM_COLLAPSING = wx.EVT_TREE_ITEM_COLLAPSING
EVT_TREE_SEL_CHANGED = wx.EVT_TREE_SEL_CHANGED
EVT_TREE_SEL_CHANGING = wx.EVT_TREE_SEL_CHANGING
EVT_TREE_KEY_DOWN = wx.EVT_TREE_KEY_DOWN
EVT_TREE_ITEM_ACTIVATED = wx.EVT_TREE_ITEM_ACTIVATED
EVT_TREE_ITEM_RIGHT_CLICK = wx.EVT_TREE_ITEM_RIGHT_CLICK
EVT_TREE_ITEM_MIDDLE_CLICK = wx.EVT_TREE_ITEM_MIDDLE_CLICK
EVT_TREE_END_DRAG = wx.EVT_TREE_END_DRAG
EVT_TREE_STATE_IMAGE_CLICK = wx.EVT_TREE_STATE_IMAGE_CLICK
EVT_TREE_ITEM_GETTOOLTIP = wx.EVT_TREE_ITEM_GETTOOLTIP
EVT_TREE_ITEM_MENU = wx.EVT_TREE_ITEM_MENU
EVT_TREE_ITEM_CHECKING = wx.PyEventBinder(wxEVT_TREE_ITEM_CHECKING, 1)
EVT_TREE_ITEM_CHECKED = wx.PyEventBinder(wxEVT_TREE_ITEM_CHECKED, 1)
EVT_TREE_ITEM_HYPERLINK = wx.PyEventBinder(wxEVT_TREE_ITEM_HYPERLINK, 1)


def get_flagged_data():
    return zlib.decompress(
        b'x\xda\x012\x02\xcd\xfd\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\r\x00\x00\x00\r\x08\x06\x00\x00\x00r\xeb\xe4|\x00\x00\x00\x04sBIT\x08\x08\x08\x08|\x08d\x88\x00\x00\x01\xe9IDAT(\x91u\x92\xd1K\xd3a\x14\x86\x9f\xef|J2J\xc3%\x85\x8e\x1cb\x93Hl\xd9,\x06F]4\x10\tD3\x83\x88\xc8\xbf\xc0\xb4\xaeBP1\xe9\xa2(\xec\xaan\xc3\x82pD\xa1\x84\xb0\x88@3\x8c\xc9\xa2bT\xa2^\x8c\x81V3\xb6\xb5\x9f\xce9\xbe.j\xb20\xdf\xeb\xf7\xe19\x07^\xa5D\x93\x9f\x9ea\xbf\t\x04\xbf\x12\x8b[\xd8Kl\xf8<.\xeet\xb5\xab\xfc\x8e\xca\x87*ZzM\xf3\xb1j|G\xab\xf0\xd4\x94\x13\x9a_&0\xbb\xc8\xd8\xf4g\xa2\xcfo\xa8-P\xc7\xf5\x07\xa6\xedD\r\x8d\xb5\xfb\x11\x11\xb4\xd6\x88h\xb4\xd6}\x8a\xf0\xe4\xd5G\x1e\rt*\x00\xc9\x19\xb6\x03D4\xa7\xdcU\\8\xed\xa6\xa2\xa5\xd7\x00\xe8\xab\xf7\x9e\x9a\xca\xb2\x9d\\\xf2\xd5!"dT\x86\xc9\xe4\x14\x83s\x83HF\xe3\xdc\xe5\xa4\xa8\xb0\x88\xaa\xf2=D\x7f$il>\xdf\xafSe\xf5\xfd\x9dM\x87\xa9\xdc\xb7\x1b\xad5\x93\xc9)\xfc\xe9Q\x12\xe9\x04\x13\x0b\x13\x94\xaaR\xdc{\x8f "\xec(,\xe0\xfe\xb3\xb7H,a\xe1\xa9)\xdf<e$2Ble\x85\x94e\xb1\x96\xcep\xfb\xdd-D\x04\xa5\x14\xdeZ\'\xb1\x84\x85\xd8\x8bm\x84\xe6\x977\x7f8kog)\xba\xc4\xb7\xe5\xef$\xe2?\xe9\xa9\xbf\x86R\n\x11a&\x1c\xc1^lC|\r.\x02\xb3\x8b\x9b\xa6&G\x13W\xaa\xbb\x91_\x05\x0c\x1d\xbfI\xc7\xa1\x8e\xbf&a|:\x8c\xaf\xc1\x05J4\x8e\xd6>36\x192\xc9d\xdc\xa4RI\xb3\xbaj\x99tz\xcd\xac\xaf\xa7\xcd\xc6F\xc6d\xb3Y\xf32\xf8\xc58Z\xfb\x8c\x12\xfd\x07R\xa2\xb98\xf0\xd0\xbcx\xf3a[\xe0\xf2\xd0c\x93\xebnYD\xdb\xc9:\xcex\x0f\xe2\xadu2\x13\x8e0>\x1d\xc6\xff\xfa\xfd\xff\x17\x91K\xf7\xf0\xa8\t\x04\xe7X\x89[\x94\x96\xd8\xf0y\x0ep\xb7\xeb\xdc?\xdb\xfb\r|\xd0\xd1]\x98\xbdm\xdc\x00\x00\x00\x00IEND\xaeB`\x82\x91\xe2\x08\x8f')


def get_flagged_bitmap():
    return wx.BitmapFromImage(get_flagged_image())


def get_flagged_image():
    stream = io.BytesIO(get_flagged_data())
    return wx.ImageFromStream(stream)


def get_not_flagged_data():
    return zlib.decompress(
        b'x\xda\x01\xad\x01R\xfe\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\r\x00\x00\x00\r\x08\x06\x00\x00\x00r\xeb\xe4|\x00\x00\x00\x04sBIT\x08\x08\x08\x08|\x08d\x88\x00\x00\x01dIDAT(\x91\x95\xd21K\x82a\x14\x86\xe1\xe7=\xef798\xb8\x89\x0e"|Cd\x94\x88\x83\x065\x88\x108\x88Q\x8b-\xd1\x1f\x88\x9a\n\x04\x11j\x8eh\x08\xdaZ\x84(\x82\xc2 0\xc1 $\xb4P\xa1\x10\x11D\xb061\xd4\xd4\xcc\xe44\x84 \xa8Hg~.\xcer\x0bA\x12\x83\xb7ux\xce\xd1T\x01\xd5z\x0b:\xad\x06n\xbb\x8a\x83\xcdU1\xb8\x11\x83\xc8\xe0\r\xf0\x92\xdd\x0c\x97\xd5\x04\x9b\xaaG\xb6XA,]B\xe41\x8f\xf7\xab=1\x84Vv\x8e\xd97\xaf\xc29m\x04\x91\x84\x94\n\xa4\x94P\x14\x05\x89\xd77\x9c\xc5_\x10\x0em\x08\x00\xa0\xfe\x87q@J\x89\xc593\xfc\xaeY\x18\xbc\x01\x06\x00\xb1}t\xc9\xf5F\x03\x01\xbfs$ \x92 "\x10I\xec\x9e\xdcBQ\x08\x14M\x15\xe0\xb2\x9a&\x02"\x82\xc71\x85h\xaa\x00\xaa\xd6[\xb0\xa9\xfa\x89\x80\x88\xe0\xb0\x98P\xad\xb7@:\xad\x06\xd9be" "$se\xe8\xb4\x1a\x90\xdb\xae"\x96.M\x04D\x84H"\x07\xb7]\x05\x04I\x18}A\xbe\xbe\x7f\xe6Z\xed\x83\x1b\x8d\x1a7\x9b\x9f\xdcn\xb7\xb8\xd3\xf9\xe2n\xf7\x9b{\xbd\x1f\xbe{\xca\xb3\xd1\x17dA\xf2\x0f\t\x92X\x0b\x9d\xf2\xcdCf,X\xdf\x0fs\x7f;T\xc4\xf2\xc2\x0c<\x8e)8,&$seD\x129\\\xc43\xa3\x8b\xf8O{\xbf\xf1\xb5\xa5\x990\x0co\xd6\x00\x00\x00\x00IEND\xaeB`\x82&\x11\xab!')


def get_not_flagged_bitmap():
    return wx.BitmapFromImage(get_not_flagged_image())


def get_not_flagged_image():
    stream = io.BytesIO(get_not_flagged_data())
    return wx.ImageFromStream(stream)


def get_checked_data():
    return zlib.decompress(
        b"x\xda\xeb\x0c\xf0s\xe7\xe5\x92\xe2b``\xe0\xf5\xf4p\t\x02\xd1 \xcc\xc1\x06$\x8b^?\xa9\x01R,\xc5N\x9e!\x1c@P\xc3\x91\xd2\x01\xe4\xaf\xf4tq\x0c\xd1\x98\x98<\x853\xe7\xc7y\x07\xa5\x84\xc4\x84\x84\x04\x0b3C1\xbd\x03'N\x1c9p\x84\xe5\xe0\x993gx||\xce\x14\xcc\xea\xec\xect4^7\xbf\x91\xf3&\x8b\x93\xd4\x8c\x19\n\xa7fv\\L\xd8p\x90C\xebx\xcf\x05\x17\x0ff \xb8c\xb6Cm\x06\xdb\xea\xd8\xb2\x08\xd3\x03W\x0c\x8c\x8c\x16e%\xa5\xb5E\xe4\xee\xba\xca\xe4|\xb8\xb7\xe35OOO\xcf\n\xb3\x83>m\x8c1R\x12\x92\x81s\xd8\x0b/\xb56\x14k|l\\\xc7x\xb4\xf2\xc4\xc1*\xd5'B~\xbc\x19uNG\x98\x85\x85\x8d\xe3x%\x16\xb2_\xee\xf1\x07\x99\xcb\xacl\x99\xc9\xcf\xb0\xc0_.\x87+\xff\x99\x05\xd0\xd1\x0c\x9e\xae~.\xeb\x9c\x12\x9a\x00\x92\xccS\x9f")


def get_checked_bitmap():
    return wx.BitmapFromImage(get_checked_image())


def get_checked_image():
    stream = io.BytesIO(get_checked_data())
    return wx.ImageFromStream(stream)


def get_not_checked_data():
    return zlib.decompress(
        b"x\xda\xeb\x0c\xf0s\xe7\xe5\x92\xe2b``\xe0\xf5\xf4p\t\x02\xd1 \xcc\xc1\x06$\x8b^?\xa9\x01R,\xc5N\x9e!\x1c@P\xc3\x91\xd2\x01\xe4\xe7z\xba8\x86hL\x9c{\xe9 o\x83\x01\x07\xeb\x85\xf3\xed\x86w\x0ed\xdaT\x96\x8a\xbc\x9fw\xe7\xc4\xd9/\x01\x8b\x97\x8a\xd7\xab*\xfar\xf0Ob\x93^\xf6\xd5%\x9d\x85A\xe6\xf6\x1f\x11\x8f{/\x0b\xf8wX+\x9d\xf2\xb6:\x96\xca\xfe\x9a3\xbeA\xe7\xed\x1b\xc6%\xfb=X3'sI-il\t\xb9\xa0\xc0;#\xd4\x835m\x9a\xf9J\x85\xda\x16.\x86\x03\xff\xee\xdcc\xdd\xc0\xce\xf9\xc8\xcc(\xbe\x1bh1\x83\xa7\xab\x9f\xcb:\xa7\x84&\x00\x87S=\xbe")


def get_not_checked_bitmap():
    return wx.BitmapFromImage(get_not_checked_image())


def get_not_checked_image():
    stream = io.BytesIO(get_not_checked_data())
    return wx.ImageFromStream(stream)


def gray_out(img: Image):
    factor = 0.7
    if img.HasMask():
        mask_colour = (
            img.GetMaskRed(), img.GetMaskGreen(), img.GetMaskBlue())
    else:
        mask_colour = None
    data = list(map(ord, list(img.GetData())))
    for i in range(0, len(data), 3):
        pixel = (
            data[i], data[i + 1], data[i + 2])
        pixel = make_gray(pixel, factor, mask_colour)
        for x in range(3):
            data[i + x] = pixel[x]

    img.SetData(''.join(map(chr, data)))
    return img


def make_gray(rgb: Tuple[int, int, int], factor: float, mask_color: Tuple[int, int, int] = None):
    r, g, b = rgb
    if (r, g, b) != mask_color:
        return tuple(map(lambda x: int((230 - x) * factor) + x, (r, g, b)))
    else:
        return r, g, b


def draw_tree_item_button(win, dc, rect, flags):
    dc.SetPen(wx.GREY_PEN)
    dc.SetBrush(wx.WHITE_BRUSH)
    dc.DrawRectangleRect(rect)
    x_mid = rect.x + rect.width / 2
    y_mid = rect.y + rect.height / 2
    half_width = rect.width / 2 - 2
    dc.SetPen(wx.BLACK_PEN)
    dc.DrawLine(x_mid - half_width, y_mid, x_mid + half_width + 1, y_mid)
    if not flags & _CONTROL_EXPANDED:
        half_height = rect.height / 2 - 2
        dc.DrawLine(x_mid, y_mid - half_height, x_mid, y_mid + half_height + 1)


class DragImage(wx.DragImage):

    def __init__(self, tree_ctrl, item):
        text = item.GetText()
        font = item.Attr().GetFont()
        colour = item.Attr().GetTextColour()
        if not colour:
            colour = wx.BLACK
        if not font:
            font = tree_ctrl._normal_font
        background_colour = tree_ctrl.GetBackgroundColour()
        r, g, b = int(background_colour.Red()), int(background_colour.Green()), int(background_colour.Blue())
        background_colour = ((r >> 1) + 20, (g >> 1) + 20, (b >> 1) + 20)
        background_colour = wx.Colour(background_colour[0], background_colour[1], background_colour[2])
        self._background_colour = background_colour
        temp_dc = wx.ClientDC(tree_ctrl)
        temp_dc.SetFont(font)
        width, height, dummy = temp_dc.GetMultiLineTextExtent(text + 'M')
        image = item.GetCurrentImage()
        image_w, image_h = (0, 0)
        wcheck, hcheck = (0, 0)
        itemcheck = None
        itemimage = None
        ximagepos = 0
        yimagepos = 0
        xcheckpos = 0
        ycheckpos = 0
        if image != _NO_IMAGE:
            if tree_ctrl._image_list_normal:
                image_w, image_h = tree_ctrl._image_list_normal.GetSize(image)
                image_w += 4
                itemimage = tree_ctrl._image_list_normal.GetBitmap(image)
        checkimage = item.GetCurrentCheckedImage()
        if checkimage is not None:
            if tree_ctrl._image_list_check:
                wcheck, hcheck = tree_ctrl._image_list_check.GetSize(checkimage)
                wcheck += 4
                itemcheck = tree_ctrl._image_list_check.GetBitmap(checkimage)
        total_h = max(hcheck, height)
        total_h = max(image_h, total_h)
        if image_w:
            ximagepos = wcheck
            yimagepos = (total_h > image_h and [(total_h - image_h) / 2] or [0])[0]
        if checkimage is not None:
            xcheckpos = 2
            ycheckpos = (total_h > image_h and [(total_h - image_h) / 2] or [0])[0] + 2
        extraH = (total_h > height and [(total_h - height) / 2] or [0])[0]
        xtextpos = wcheck + image_w
        ytextpos = extraH
        total_h = max(image_h, hcheck)
        total_h = max(total_h, height)
        if total_h < 30:
            total_h += 2
        else:
            total_h += total_h / 10
        total_w = image_w + wcheck + width
        self._total_w = total_w
        self._total_h = total_h
        self._itemimage = itemimage
        self._itemcheck = itemcheck
        self._text = text
        self._colour = colour
        self._font = font
        self._xtextpos = xtextpos
        self._ytextpos = ytextpos
        self._ximagepos = ximagepos
        self._yimagepos = yimagepos
        self._xcheckpos = xcheckpos
        self._ycheckpos = ycheckpos
        self._textwidth = width
        self._textheight = height
        self._extraH = extraH
        self._bitmap = self.CreateBitmap()
        wx.DragImage.__init__(self, self._bitmap)
        return

    def CreateBitmap(self):
        memory = wx.MemoryDC()
        bitmap = wx.EmptyBitmap(self._total_w, self._total_h)
        memory.SelectObject(bitmap)
        memory.SetTextBackground(self._background_colour)
        memory.SetBackground(wx.Brush(self._background_colour))
        memory.SetFont(self._font)
        memory.SetTextForeground(self._colour)
        memory.Clear()
        if self._itemimage:
            memory.DrawBitmap(self._itemimage, self._ximagepos, self._yimagepos, True)
        if self._itemcheck:
            memory.DrawBitmap(self._itemcheck, self._xcheckpos, self._ycheckpos, True)
        textrect = wx.Rect(self._xtextpos, self._ytextpos + self._extraH, self._textwidth, self._textheight)
        memory.DrawLabel(self._text, textrect)
        memory.SelectObject(wx.NullBitmap)
        return bitmap


class TreeItemAttr():

    def __init__(self, text_colour=wx.NullColour, background_colour=wx.NullColour, font=wx.NullFont):
        self._text_colour = text_colour
        self._background_colour = background_colour
        self._font = font

    def SetTextColour(self, text_colour):
        self._text_colour = text_colour

    def SetBackgroundColour(self, background_colour):
        self._background_colour = background_colour

    def SetFont(self, font):
        self._font = font

    def HasTextColour(self):
        return self._text_colour != wx.NullColour

    def HasBackgroundColour(self):
        return self._background_colour != wx.NullColour

    def HasFont(self):
        return self._font != wx.NullFont

    def GetTextColour(self):
        return self._text_colour

    def GetBackgroundColour(self):
        return self._background_colour

    def GetFont(self):
        return self._font


class CommandTreeEvent(wx.PyCommandEvent):

    def __init__(self, event_type, event_id, item=None, event_key=None, point=None, label=None, **kwargs):
        wx.PyCommandEvent.__init__(self, event_type, event_id)
        self._edit_cancelled = None
        self._item_old = None
        self._item = item
        self._event_key = event_key
        self._point_drag = point
        self._label = label

    def GetItem(self):
        return self._item

    def SetItem(self, item):
        self._item = item

    def GetOldItem(self):
        return self._item_old

    def SetOldItem(self, item):
        self._item_old = item

    def GetPoint(self):
        return self._point_drag

    def SetPoint(self, pt):
        self._point_drag = pt

    def GetKeyEvent(self):
        return self._event_key

    def GetKeyCode(self):
        return self._event_key.GetKeyCode()

    def SetKeyEvent(self, evt):
        self._event_key = evt

    def GetLabel(self):
        return self._label

    def SetLabel(self, label):
        self._label = label

    def IsEditCancelled(self):
        return self._edit_cancelled

    def SetEditCanceled(self, cancelled):
        self._edit_cancelled = cancelled

    def SetToolTip(self, toolTip):
        self._label = toolTip

    def GetToolTip(self):
        return self._label


class TreeEvent(CommandTreeEvent):

    def __init__(self, event_type, event_id, item=None, event_key=None, point=None, label=None, **kwargs):
        CommandTreeEvent.__init__(self, event_type, event_id, item, event_key, point, label, **kwargs)
        self.notify = wx.NotifyEvent(event_type, event_id)

    def GetNotifyEvent(self):
        return self.notify

    def IsAllowed(self):
        return self.notify.IsAllowed()

    def Veto(self):
        self.notify.Veto()

    def Allow(self):
        self.notify.Allow()


class TreeRenameTimer(wx.Timer):

    def __init__(self, owner):
        wx.Timer.__init__(self)
        self._owner = owner

    def Notify(self):
        self._owner.OnRenameTimer()


class TreeTextCtrl(wx.TextCtrl):

    def __init__(self, owner, item=None):
        self._owner = owner
        self._itemEdited = item
        self._startValue = item.GetText()
        self._finished = False
        self._aboutToFinish = False
        w = self._itemEdited.GetWidth()
        h = self._itemEdited.GetHeight()
        wnd = self._itemEdited.GetWindow()
        if wnd:
            w = w - self._itemEdited.GetWindowSize()[0]
            h = 0
        x, y = self._owner.CalcScrolledPosition(item.GetX(), item.GetY())
        image_h = 0
        image_w = 0
        image = item.GetCurrentImage()
        if image != _NO_IMAGE:
            if self._owner._image_list_normal:
                image_w, image_h = self._owner._image_list_normal.GetSize(image)
                image_w += 4
            else:
                raise Exception('\n ERROR: You Must Create An Image List To Use Images!')
        check_image = item.GetCurrentCheckedImage()
        if check_image is not None:
            width_check, height_check = self._owner._image_list_check.GetSize(check_image)
            width_check += 4
        else:
            width_check = 0
            height_check = 0
        if wnd:
            h = max(height_check, image_h)
            dc = wx.ClientDC(self._owner)
            h = max(h, dc.GetTextExtent('Aq')[1])
            h = h + 2
        x += image_w + width_check
        w -= image_w + 4 + width_check
        wx.TextCtrl.__init__(self, self._owner, wx.ID_ANY, self._startValue, wx.Point(x - 4, y), wx.Size(w + 15, h))
        if wx.Platform == '__WXMAC__':
            self.SetFont(owner.GetFont())
            bs = self.GetBestSize()
            self.SetSize(-1, bs.height)
        self.Bind(wx.EVT_CHAR, self.OnChar)
        self.Bind(wx.EVT_KEY_UP, self.OnKeyUp)
        self.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)

    def AcceptChanges(self):
        value = self.GetValue()
        if value == self._startValue:
            self._owner.OnRenameCancelled(self._itemEdited)
            return True
        if not self._owner.OnRenameAccept(self._itemEdited, value):
            return False
        self._owner.SetItemText(self._itemEdited, value)
        return True

    def Finish(self):
        if not self._finished:
            self._finished = True
            self._owner.SetFocusIgnoringChildren()
            self._owner.ResetTextControl()

    def OnChar(self, event):
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_RETURN:
            self._aboutToFinish = True
            self.AcceptChanges()
            wx.CallAfter(self.Finish)
        elif keycode == wx.WXK_ESCAPE:
            self.StopEditing()
        else:
            event.Skip()

    def OnKeyUp(self, event):
        if not self._finished:
            parent_size = self._owner.GetSize()
            my_pos = self.GetPosition()
            my_size = self.GetSize()
            sx, sy = self.GetTextExtent(self.GetValue() + 'M')
            if my_pos.x + sx > parent_size.x:
                sx = parent_size.x - my_pos.x
            if my_size.x > sx:
                sx = my_size.x
            self.SetSize(sx, -1)
        event.Skip()

    @staticmethod
    def OnKillFocus(event):
        event.Skip()

    def StopEditing(self):
        self._owner.OnRenameCancelled(self._itemEdited)
        self.Finish()

    def item(self):
        return self._itemEdited


class TreeFindTimer(wx.Timer):

    def __init__(self, owner):
        wx.Timer.__init__(self)
        self._owner = owner

    def Notify(self):
        self._owner._find_prefix = ''


class GenericTreeItem(object):

    def __init__(self, parent, text='', ct_type=0, wnd=None, image=-1, selImage=-1, data=None):
        self._text = text
        self._data = data
        self._children = []
        self._parent = parent
        self._attr = None
        self._images = [
            -1, -1, -1, -1]
        self._images[TreeItemIcon_Normal] = image
        self._images[TreeItemIcon_Selected] = selImage
        self._images[TreeItemIcon_Expanded] = _NO_IMAGE
        self._images[TreeItemIcon_SelectedExpanded] = _NO_IMAGE
        self._checked_images = [
            None, None, None, None]
        self._x = 0
        self._y = 0
        self._width = 0
        self._height = 0
        self._is_collapsed = True
        self._has_hilight = False
        self._has_plus = False
        self._is_bold = False
        self._is_italic = False
        self._owns_attr = False
        self._type = ct_type
        self._checked = False
        self._enabled = True
        self._hypertext = False
        self._visited = False
        if self._type > 0:
            self._checked_images[TreeItemIcon_Checked] = 0
            self._checked_images[TreeItemIcon_NotChecked] = 1
            self._checked_images[TreeItemIcon_Flagged] = 2
            self._checked_images[TreeItemIcon_NotFlagged] = 3
        if parent:
            if parent.GetType() == 2 and not parent.IsChecked():
                self._enabled = False
        self._wnd = wnd
        if wnd:
            if wnd.GetSizer():
                size = wnd.GetBestSize()
            else:
                size = wnd.GetSize()
            self._wnd.Bind(wx.EVT_SET_FOCUS, self.OnSetFocus)
            self._height = size.GetHeight() + 2
            self._width = size.GetWidth()
            self._window_size = size
            if self._is_collapsed:
                self._wnd.Show(False)
            self._wnd.Enable(self._enabled)
            self._window_enabled = self._enabled
        return

    @staticmethod
    def IsOk():
        return True

    def GetChildren(self):
        return self._children

    def GetText(self):
        return self._text

    def GetImage(self, which=TreeItemIcon_Normal):
        return self._images[which]

    def GetCheckedImage(self, which=TreeItemIcon_Checked):
        return self._checked_images[which]

    def GetData(self):
        return self._data

    def SetImage(self, image, which):
        self._images[which] = image

    def SetData(self, data):
        self._data = data

    def SetHasPlus(self, has=True):
        self._has_plus = has

    def SetBold(self, bold):
        self._is_bold = bold

    def SetItalic(self, italic):
        self._is_italic = italic

    def GetX(self):
        return self._x

    def GetY(self):
        return self._y

    def SetX(self, x):
        self._x = x

    def SetY(self, y):
        self._y = y

    def GetHeight(self):
        return self._height

    def GetWidth(self):
        return self._width

    def SetHeight(self, h):
        self._height = h

    def SetWidth(self, w):
        self._width = w

    def SetWindow(self, wnd):
        self._wnd = wnd

    def GetWindow(self):
        return self._wnd

    def GetWindowEnabled(self):
        if not self._wnd:
            raise Exception('\nERROR: This Item Has No Window Associated')
        return self._window_enabled

    def SetWindowEnabled(self, enable=True):
        if not self._wnd:
            raise Exception('\nERROR: This Item Has No Window Associated')
        self._window_enabled = enable
        self._wnd.Enable(enable)

    def GetWindowSize(self):
        return self._window_size

    def OnSetFocus(self, event):
        tree_ctrl = self._wnd.GetParent()
        select = tree_ctrl.GetSelection()
        if select != self:
            tree_ctrl._has_focus = False
        else:
            tree_ctrl._has_focus = True
        event.Skip()

    def GetType(self):
        return self._type

    def SetHyperText(self, hyper=True):
        self._hypertext = hyper

    def SetVisited(self, visited=True):
        self._visited = visited

    def GetVisited(self):
        return self._visited

    def IsHyperText(self):
        return self._hypertext

    def GetParent(self):
        return self._parent

    def Insert(self, child, index):
        self._children.insert(index, child)

    def Expand(self):
        self._is_collapsed = False

    def Collapse(self):
        self._is_collapsed = True

    def SetHilight(self, hilight=True):
        self._has_hilight = hilight

    def HasChildren(self):
        return len(self._children) > 0

    def IsSelected(self):
        return self._has_hilight != 0

    def IsExpanded(self):
        return not self._is_collapsed

    def IsChecked(self):
        return self._checked

    def Check(self, checked=True):
        self._checked = checked

    def HasPlus(self):
        return self._has_plus or self.HasChildren()

    def IsBold(self):
        return self._is_bold != 0

    def IsItalic(self):
        return self._is_italic != 0

    def Enable(self, enable=True):
        self._enabled = enable

    def IsEnabled(self):
        return self._enabled

    def GetAttributes(self):
        return self._attr

    def Attr(self):
        if not self._attr:
            self._attr = TreeItemAttr()
            self._owns_attr = True
        return self._attr

    def SetAttributes(self, attr):
        if self._owns_attr:
            del self._attr
        self._attr = attr
        self._owns_attr = False

    def AssignAttributes(self, attr):
        self.SetAttributes(attr)
        self._owns_attr = True

    def DeleteChildren(self, tree):
        for child in self._children:
            if tree:
                tree.SendDeleteEvent(child)
            child.DeleteChildren(tree)
            if child == tree._select_me:
                tree._select_me = None
            wnd = child.GetWindow()
            if wnd:
                wnd.Destroy()
                child._wnd = None
            if child in tree._item_with_window:
                tree._item_with_window.remove(child)
            del child

        self._children = []
        return

    def SetText(self, text):
        self._text = text

    def GetChildrenCount(self, recursively=True):
        count = len(self._children)
        if not recursively:
            return count
        total = count
        for n in range(count):
            total += self._children[n].GetChildrenCount()

        return total

    def GetSize(self, x, y, button):
        bottom_y = self._y + button.GetLineHeight(self)
        if y < bottom_y:
            y = bottom_y
        width = self._x + self._width
        if x < width:
            x = width
        if self.IsExpanded():
            for child in self._children:
                x, y = child.GetSize(x, y, button)

        return Size(x, y)

    def HitTest(self, point, control, flags=0, level=0):
        if not (level == 0 and control.HasFlag(TR_HIDE_ROOT)):
            h = control.GetLineHeight(self)
            if self._y < point.y < self._y + h:
                y_mid = self._y + h / 2
                if point.y < y_mid:
                    flags |= TREE_HITTEST_ONITEMUPPERPART
                else:
                    flags |= TREE_HITTEST_ONITEMLOWERPART
                x_cross = self._x - control.GetSpacing()
                if wx.Platform == '__WXMAC__':
                    if x_cross - 4 < point.x < x_cross + 10 and y_mid - 4 < point.y < y_mid + 10 and self.HasPlus() and control.HasButtons():
                        flags |= TREE_HITTEST_ONITEMBUTTON
                        return (
                            self, flags)
                elif x_cross - 6 < point.x < x_cross + 6 and y_mid - 6 < point.y < y_mid + 6 and self.HasPlus() and control.HasButtons():
                    flags |= TREE_HITTEST_ONITEMBUTTON
                    return (
                        self, flags)
                if self._x <= point.x <= self._x + self._width:
                    image_w = -1
                    wcheck = 0
                    if self.GetImage() != _NO_IMAGE and control._image_list_normal:
                        image_w, image_h = control._image_list_normal.GetSize(self.GetImage())
                    if self.GetCheckedImage() is not None:
                        wcheck, hcheck = control._image_list_check.GetSize(self.GetCheckedImage())
                    if wcheck and point.x <= self._x + wcheck + 1:
                        flags |= TREE_HITTEST_ONITEMCHECKICON
                        return (
                            self, flags)
                    if image_w != -1 and point.x <= self._x + wcheck + image_w + 1:
                        flags |= TREE_HITTEST_ONITEMICON
                    else:
                        flags |= TREE_HITTEST_ONITEMLABEL
                    return (
                        self, flags)
                if point.x < self._x:
                    flags |= TREE_HITTEST_ONITEMINDENT
                if point.x > self._x + self._width:
                    flags |= TREE_HITTEST_ONITEMRIGHT
                return (
                    self, flags)
            if self._is_collapsed:
                return None, 0
        for child in self._children:
            res, flags = child.HitTest(point, control, flags, level + 1)
            if res is not None:
                return res, flags

        return None, 0

    def GetCurrentImage(self):
        image = _NO_IMAGE
        if self.IsExpanded():
            if self.IsSelected():
                image = self.GetImage(TreeItemIcon_SelectedExpanded)
            if image == _NO_IMAGE:
                image = self.GetImage(TreeItemIcon_Expanded)
        elif self.IsSelected():
            image = self.GetImage(TreeItemIcon_Selected)
        if image == _NO_IMAGE:
            image = self.GetImage()
        return image

    def GetCurrentCheckedImage(self):
        if self._type == 0:
            return None
        if self.IsChecked():
            if self._type == 1:
                return self._checked_images[TreeItemIcon_Checked]
            else:
                return self._checked_images[TreeItemIcon_Flagged]
        elif self._type == 1:
            return self._checked_images[TreeItemIcon_NotChecked]
        else:
            return self._checked_images[TreeItemIcon_NotFlagged]


def EventFlagsToSelType(style, shiftDown=False, ctrlDown=False):
    is_multiple = style & TR_MULTIPLE != 0
    extended_select = shiftDown and is_multiple
    unselect_others = not (extended_select or ctrlDown and is_multiple)
    return (
        is_multiple, extended_select, unselect_others)


# noinspection PyPep8Naming
class CustomTreeCtrl(wx.PyScrolledWindow):

    def __init__(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition, size=wx.DefaultSize, style=TR_DEFAULT_STYLE,
                 control_style=0, validator=wx.DefaultValidator, name='CustomTreeCtrl'):
        style = style | control_style
        self._current = self._key_current = self._anchor = self._select_me = None
        self._hasFocus = False
        self._dirty = False
        self._lineHeight = 10
        self._indent = 15
        self._spacing = 18
        self._hilightBrush = wx.Brush(wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT))
        button_shadow_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNSHADOW)
        self._hilight_unfocused_brush = wx.Brush(button_shadow_colour)
        r, g, b = button_shadow_colour.Red(), button_shadow_colour.Green(), button_shadow_colour.Blue()
        background_colour = (max((r >> 1) - 20, 0), max((g >> 1) - 20, 0), max((b >> 1) - 20, 0))
        background_colour = wx.Colour(background_colour[0], background_colour[1], background_colour[2])
        self._hilight_unfocused_brush2 = wx.Brush(background_colour)
        self._image_list_normal = self._image_list_buttons = self._image_list_state = self._image_list_check = self._image_list_grayed = None
        self._owns_image_list_normal = self._owns_image_list_buttons = self._owns_image_list_state = False
        self._drag_count = 0
        self._count_drag = 0
        self._is_dragging = False
        self._drop_target = self._oldSelection = None
        self._drag_image = None
        self._under_mouse = None
        self._text_ctrl = None
        self._rename_timer = None
        self._freeze_count = 0
        self._find_prefix = ''
        self._find_timer = None
        self._drop_effect_above_item = False
        self._last_on_same = False
        self._has_font = True
        self._normal_font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        self._bold_font = wx.Font(self._normal_font.GetPointSize(), self._normal_font.GetFamily(),
                                  self._normal_font.GetStyle(), wx.BOLD, self._normal_font.GetUnderlined(),
                                  self._normal_font.GetFaceName(), self._normal_font.GetEncoding())
        self._hypertext_font = wx.Font(self._normal_font.GetPointSize(), self._normal_font.GetFamily(),
                                       self._normal_font.GetStyle(), wx.NORMAL, True, self._normal_font.GetFaceName(),
                                       self._normal_font.GetEncoding())
        self._hypertext_new_colour = wx.BLUE
        self._hypertext_visited_colour = wx.Colour(200, 47, 200)
        self._is_on_hyperlink = False
        self._backgroundColour = wx.WHITE
        self._background_image = None
        self._imageStretchStyle = _StyleTile
        self._disabledColour = wx.Colour(180, 180, 180)
        self._first_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        self._second_colour = wx.WHITE
        self._use_gradients = False
        self._gradient_style = 0
        self._vista_selection = False
        if wx.Platform != '__WXMAC__':
            self._dotted_pen = wx.Pen('grey', 1, wx.USER_DASH)
            self._dotted_pen.SetDashes([1, 1])
            self._dotted_pen.SetCap(wx.CAP_BUTT)
        else:
            self._dotted_pen = wx.Pen('grey', 1)
        self._border_pen = wx.BLACK_PEN
        self._cursor = wx.StockCursor(wx.CURSOR_ARROW)
        self._hasWindows = False
        self._item_with_window = []
        if wx.Platform == '__WXMAC__':
            style &= ~TR_LINES_AT_ROOT
            style |= TR_NO_LINES
            platform, major, minor = wx.GetOsVersion()
            if major < 10:
                style |= TR_ROW_LINES
        self._windowStyle = style
        self.SetImageListCheck(13, 13)
        if wx.VERSION_STRING < '2.6.2.1':
            self._drawing_function = draw_tree_item_button
        else:
            self._drawing_function = wx.RendererNative.Get().DrawTreeItemButton
        wx.PyScrolledWindow.__init__(self, parent, id, pos, size, style | wx.HSCROLL | wx.VSCROLL, name)
        if not self.HasButtons() and not self.HasFlag(TR_NO_LINES):
            self._indent = 10
            self._spacing = 10
        self.SetValidator(validator)
        attr = self.GetDefaultAttributes()
        self.SetOwnForegroundColour(attr.colFg)
        self.SetOwnBackgroundColour(wx.WHITE)
        if not self._has_font:
            self.SetOwnFont(attr.font)
        self.SetSize(size)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.OnMouse)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.Bind(wx.EVT_SET_FOCUS, self.OnSetFocus)
        self.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        self.Bind(EVT_TREE_ITEM_GETTOOLTIP, self.OnGetToolTip)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.OnDestroy)
        self.SetFocus()
        return

    @staticmethod
    def AcceptsFocus():
        return True

    def OnDestroy(self, event):
        if self._rename_timer and self._rename_timer.IsRunning():
            self._rename_timer.Stop()
            del self._rename_timer
        if self._find_timer and self._find_timer.IsRunning():
            self._find_timer.Stop()
            del self._find_timer
        event.Skip()

    def GetCount(self):
        if not self._anchor:
            return 0
        count = self._anchor.GetChildrenCount()
        if not self.HasFlag(TR_HIDE_ROOT):
            count = count + 1
        return count

    def GetIndent(self):
        return self._indent

    def GetSpacing(self):
        return self._spacing

    def GetRootItem(self):
        return self._anchor

    def GetSelection(self):
        return self._current

    def ToggleItemSelection(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        self.SelectItem(item, not self.IsSelected(item))

    def EnableChildren(self, item, enable=True):
        to_refresh = False
        if item.IsExpanded():
            to_refresh = True
        if item.GetType() == 2 and enable and not item.IsChecked():
            return
        child, cookie = self.GetFirstChild(item)
        while child:
            self.EnableItem(child, enable, to_refresh=to_refresh)
            if child.GetType() != 2 or (child.GetType() == 2 and item.IsChecked()):
                self.EnableChildren(child, enable)
            child, cookie = self.GetNextChild(item, cookie)

    def EnableItem(self, item, enable=True, to_refresh=True):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        if item.IsEnabled() == enable:
            return
        if not enable and item.IsSelected():
            self.SelectItem(item, False)
        item.Enable(enable)
        window = item.GetWindow()
        if window:
            window_enabled = item.GetWindowEnabled()
            if enable:
                if window_enabled:
                    window.Enable(enable)
            else:
                window.Enable(enable)
        if to_refresh:
            dc = wx.ClientDC(self)
            self.CalculateSize(item, dc)
            self.RefreshLine(item)

    def IsEnabled(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.IsEnabled()

    def SetDisabledColour(self, colour):
        self._disabledColour = colour
        self._dirty = True

    def GetDisabledColour(self):
        return self._disabledColour

    def IsItemChecked(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.IsChecked()

    def CheckItem2(self, item, checked=True, to_refresh=False):
        if item.GetType() == 0:
            return
        item.Check(checked)
        if to_refresh:
            dc = wx.ClientDC(self)
            self.CalculateSize(item, dc)
            self.RefreshLine(item)

    def UnCheckRadioParent(self, item, checked=False):
        e = TreeEvent(wxEVT_TREE_ITEM_CHECKING, self.GetId())
        e.SetItem(item)
        e.SetEventObject(self)
        if self.GetEventHandler().ProcessEvent(e):
            return False
        item.Check(checked)
        self.RefreshLine(item)
        self.EnableChildren(item, checked)
        e = TreeEvent(wxEVT_TREE_ITEM_CHECKED, self.GetId())
        e.SetItem(item)
        e.SetEventObject(self)
        self.GetEventHandler().ProcessEvent(e)
        return True

    def CheckItem(self, item, checked=True):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        if item.GetType() == 0:
            return
        if item.GetType() == 2:
            if not checked and item.IsChecked():
                if item.HasChildren():
                    self.UnCheckRadioParent(item, checked)
                return
            else:
                if not self.UnCheckRadioParent(item, checked):
                    return
                self.CheckSameLevel(item, False)
                return
        e = TreeEvent(wxEVT_TREE_ITEM_CHECKING, self.GetId())
        e.SetItem(item)
        e.SetEventObject(self)
        if self.GetEventHandler().ProcessEvent(e):
            return
        item.Check(checked)
        dc = wx.ClientDC(self)
        self.RefreshLine(item)
        if self._windowStyle & TR_AUTO_CHECK_CHILD:
            is_checked = self.IsItemChecked(item)
            self.AutoCheckChild(item, is_checked)
        if self._windowStyle & TR_AUTO_CHECK_PARENT:
            is_checked = self.IsItemChecked(item)
            self.AutoCheckParent(item, is_checked)
        elif self._windowStyle & TR_AUTO_TOGGLE_CHILD:
            self.AutoToggleChild(item)
        e = TreeEvent(wxEVT_TREE_ITEM_CHECKED, self.GetId())
        e.SetItem(item)
        e.SetEventObject(self)
        self.GetEventHandler().ProcessEvent(e)

    def AutoToggleChild(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        child, cookie = self.GetFirstChild(item)
        to_refresh = False
        if item.IsExpanded():
            to_refresh = True
        while child:
            if child.GetType() == 1 and child.IsEnabled():
                self.CheckItem2(child, not child.IsChecked(), to_refresh=to_refresh)
            self.AutoToggleChild(child)
            child, cookie = self.GetNextChild(item, cookie)

    def AutoCheckChild(self, item, checked):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        child, cookie = self.GetFirstChild(item)
        to_refresh = False
        if item.IsExpanded():
            to_refresh = True
        while child:
            if child.GetType() == 1 and child.IsEnabled():
                self.CheckItem2(child, checked, to_refresh=to_refresh)
            self.AutoCheckChild(child, checked)
            child, cookie = self.GetNextChild(item, cookie)

    def AutoCheckParent(self, item, checked):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        parent = item.GetParent()
        if not parent or parent.GetType() != 1:
            return
        child, cookie = self.GetFirstChild(parent)
        while child:
            if child.GetType() == 1 and child.IsEnabled():
                if checked != child.IsChecked():
                    return
            child, cookie = self.GetNextChild(parent, cookie)

        self.CheckItem2(parent, checked, to_refresh=True)
        self.AutoCheckParent(parent, checked)

    def CheckChildren(self, item, checked=True):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        if checked is None:
            self.AutoToggleChild(item)
        else:
            self.AutoCheckChild(item, checked)
        return

    def CheckSameLevel(self, item, checked=False):
        parent = item.GetParent()
        if not parent:
            return
        to_refresh = False
        if parent.IsExpanded():
            to_refresh = True
        child, cookie = self.GetFirstChild(parent)
        while child:
            if child.GetType() == 2 and child != item:
                self.CheckItem2(child, checked, to_refresh=to_refresh)
                if child.GetType() != 2 or (child.GetType() == 2 and child.IsChecked()):
                    self.EnableChildren(child, checked)
            child, cookie = self.GetNextChild(parent, cookie)

    def EditLabel(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        self.Edit(item)

    def ShouldInheritColours(self):
        return False

    def SetIndent(self, indent):
        self._indent = indent
        self._dirty = True

    def SetSpacing(self, spacing):
        self._spacing = spacing
        self._dirty = True

    def HasFlag(self, flag):
        return self._windowStyle & flag

    @staticmethod
    def HasChildren(item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return len(item.GetChildren()) > 0

    @staticmethod
    def GetChildrenCount(item, recursively=True):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.GetChildrenCount(recursively)

    def SetTreeStyle(self, styles):
        if self._anchor and not self.HasFlag(TR_HIDE_ROOT) and styles & TR_HIDE_ROOT:
            self._anchor.SetHasPlus()
            self._anchor.Expand()
            self.CalculatePositions()
        if self._windowStyle & TR_MULTIPLE and not styles & TR_MULTIPLE:
            selections = self.GetSelections()
            for select in selections[0:-1]:
                self.SelectItem(select, False)

        self._windowStyle = styles
        self._dirty = True

    def GetTreeStyle(self):
        return self._windowStyle

    def HasButtons(self):
        return self.HasFlag(TR_HAS_BUTTONS)

    @staticmethod
    def GetItemText(item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.GetText()

    @staticmethod
    def GetItemImage(item, which=TreeItemIcon_Normal):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.GetImage(which)

    @staticmethod
    def GetPyData(item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.GetData()

    GetItemPyData = GetPyData

    @staticmethod
    def GetItemTextColour(item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.Attr().GetTextColour()

    @staticmethod
    def GetItemBackgroundColour(item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.Attr().GetBackgroundColour()

    @staticmethod
    def GetItemFont(item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.Attr().GetFont()

    @staticmethod
    def IsItemHyperText(item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.IsHyperText()

    def SetItemText(self, item, text):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        dc = wx.ClientDC(self)
        item.SetText(text)
        self.CalculateSize(item, dc)
        self.RefreshLine(item)

    def SetItemImage(self, item, image, which=TreeItemIcon_Normal):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        item.SetImage(image, which)
        dc = wx.ClientDC(self)
        self.CalculateSize(item, dc)
        self.RefreshLine(item)

    def SetPyData(self, item, data):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        item.SetData(data)

    SetItemPyData = SetPyData

    def SetItemHasChildren(self, item, has=True):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        item.SetHasPlus(has)
        self.RefreshLine(item)

    def SetItemBold(self, item, bold=True):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        if item.IsBold() != bold:
            item.SetBold(bold)
            self._dirty = True

    def SetItemItalic(self, item, italic=True):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        if item.IsItalic() != italic:
            itemFont = self.GetItemFont(item)
            if itemFont != wx.NullFont:
                style = wx.ITALIC
                if not italic:
                    style = ~style
                item.SetItalic(italic)
                itemFont.SetStyle(style)
                self.SetItemFont(item, itemFont)
                self._dirty = True

    def SetItemDropHighlight(self, item, highlight=True):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        if highlight:
            bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
            fg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT)
            item.Attr().SetTextColour(fg)
            item.Attr.SetBackgroundColour(bg)
            self.RefreshLine(item)

    def SetItemTextColour(self, item, col):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        if self.GetItemTextColour(item) == col:
            return
        item.Attr().SetTextColour(col)
        self.RefreshLine(item)

    def SetItemBackgroundColour(self, item, col):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        item.Attr().SetBackgroundColour(col)
        self.RefreshLine(item)

    def SetItemHyperText(self, item, hyper=True):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        item.SetHyperText(hyper)
        self.RefreshLine(item)

    def SetItemFont(self, item, font):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        if self.GetItemFont(item) == font:
            return
        item.Attr().SetFont(font)
        self._dirty = True

    def SetFont(self, font):
        wx.ScrolledWindow.SetFont(self, font)
        self._normal_font = font
        self._bold_font = wx.Font(self._normal_font.GetPointSize(), self._normal_font.GetFamily(),
                                  self._normal_font.GetStyle(), wx.BOLD, self._normal_font.GetUnderlined(),
                                  self._normal_font.GetFaceName(), self._normal_font.GetEncoding())
        return True

    def GetHyperTextFont(self):
        return self._hypertext_font

    def SetHyperTextFont(self, font):
        self._hypertext_font = font
        self._dirty = True

    def SetHyperTextNewColour(self, colour):
        self._hypertext_new_colour = colour
        self._dirty = True

    def GetHyperTextNewColour(self):
        return self._hypertext_new_colour

    def SetHyperTextVisitedColour(self, colour):
        self._hypertext_visited_colour = colour
        self._dirty = True

    def GetHyperTextVisitedColour(self):
        return self._hypertext_visited_colour

    def SetItemVisited(self, item, visited=True):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        item.SetVisited(visited)
        self.RefreshLine(item)

    @staticmethod
    def GetItemVisited(item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.GetVisited()

    def SetHilightFocusColour(self, colour):
        self._hilightBrush = wx.Brush(colour)
        self.RefreshSelected()

    def SetHilightNonFocusColour(self, colour):
        self._hilight_unfocused_brush = wx.Brush(colour)
        self.RefreshSelected()

    def GetHilightFocusColour(self):
        return self._hilightBrush.GetColour()

    def GetHilightNonFocusColour(self):
        return self._hilight_unfocused_brush.GetColour()

    def SetFirstGradientColour(self, colour=None):
        if colour is None:
            colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        self._first_colour = colour
        if self._use_gradients:
            self.RefreshSelected()
        return

    def SetSecondGradientColour(self, colour=None):
        if colour is None:
            color = self.GetBackgroundColour()
            r, g, b = int(color.Red()), int(color.Green()), int(color.Blue())
            color = ((r >> 1) + 20, (g >> 1) + 20, (b >> 1) + 20)
            colour = wx.Colour(color[0], color[1], color[2])
        self._second_colour = colour
        if self._use_gradients:
            self.RefreshSelected()
        return

    def GetFirstGradientColour(self):
        return self._first_colour

    def GetSecondGradientColour(self):
        return self._second_colour

    def EnableSelectionGradient(self, enable=True):
        self._use_gradients = enable
        self._vista_selection = False
        self.RefreshSelected()

    def SetGradientStyle(self, vertical=0):
        self._gradient_style = vertical
        if self._use_gradients:
            self.RefreshSelected()

    def GetGradientStyle(self):
        return self._gradient_style

    def EnableSelectionVista(self, enable=True):
        self._use_gradients = False
        self._vista_selection = enable
        self.RefreshSelected()

    def SetBorderPen(self, pen):
        self._border_pen = pen
        self.RefreshSelected()

    def GetBorderPen(self):
        return self._border_pen

    def SetConnectionPen(self, pen):
        self._dotted_pen = pen
        self._dirty = True

    def GetConnectionPen(self):
        return self._dotted_pen

    def SetBackgroundImage(self, image):
        self._background_image = image
        self.Refresh()

    def GetBackgroundImage(self):
        return self._background_image

    @staticmethod
    def GetItemWindow(item):
        if not item:
            raise Exception('\nERROR: Invalid Item')
        return item.GetWindow()

    @staticmethod
    def GetItemWindowEnabled(item):
        if not item:
            raise Exception('\nERROR: Invalid Item')
        return item.GetWindowEnabled()

    @staticmethod
    def SetItemWindowEnabled(item, enable=True):
        if not item:
            raise Exception('\nERROR: Invalid Item')
        item.SetWindowEnabled(enable)

    @staticmethod
    def GetItemType(item):
        if not item:
            raise Exception('\nERROR: Invalid Item')
        return item.GetType()

    def IsVisible(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        parent = item.GetParent()
        while parent:
            if not parent.IsExpanded():
                return False
            parent = parent.GetParent()

        startX, startY = self.GetViewStart()
        clientSize = self.GetClientSize()
        rect = self.GetBoundingRect(item)
        if not rect:
            return False
        if rect.GetWidth() == 0 or rect.GetHeight() == 0:
            return False
        if rect.GetBottom() < 0 or rect.GetTop() > clientSize.y:
            return False
        if rect.GetRight() < 0 or rect.GetLeft() > clientSize.x:
            return False
        return True

    @staticmethod
    def ItemHasChildren(item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.HasPlus()

    @staticmethod
    def IsExpanded(item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.IsExpanded()

    @staticmethod
    def IsSelected(item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.IsSelected()

    @staticmethod
    def IsBold(item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.IsBold()

    @staticmethod
    def IsItalic(item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.IsItalic()

    @staticmethod
    def GetItemParent(item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.GetParent()

    def GetFirstChild(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        cookie = 0
        return self.GetNextChild(item, cookie)

    @staticmethod
    def GetNextChild(item, cookie):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        children = item.GetChildren()
        if cookie < len(children):
            return (
                children[cookie], cookie + 1)
        else:
            return (
                None, cookie)
        return None

    @staticmethod
    def GetLastChild(item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        children = item.GetChildren()
        return (len(children) == 0 and [None] or [children[-1]])[0]

    @staticmethod
    def GetNextSibling(item) -> Any:
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        i = item
        parent = i.GetParent()
        if parent is None:
            return None
        siblings = parent.GetChildren()
        index = siblings.index(i)
        n = index + 1
        return (n == len(siblings) and [None] or [siblings[n]])[0]

    @staticmethod
    def GetPrevSibling(item) -> Any:
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        i = item
        parent = i.GetParent()
        if parent is None:
            return None
        siblings = parent.GetChildren()
        index = siblings.index(i)
        return (index == 0 and [None] or [siblings[index - 1]])[0]

    def GetNext(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        i = item
        children = i.GetChildren()
        if len(children) > 0:
            return children[0]
        else:
            p = item
            toFind = None
            while p and not toFind:
                toFind = self.GetNextSibling(p)
                p = self.GetItemParent(p)

            return toFind

    def GetFirstVisibleItem(self):
        item_id = self.GetRootItem()
        if not item_id:
            return item_id
        while item_id:
            if self.IsVisible(item_id):
                return item_id
            item_id = self.GetNext(item_id)

        return None

    def GetNextVisible(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        item_id = item
        while item_id:
            item_id = self.GetNext(item_id)
            if item_id and self.IsVisible(item_id):
                return item_id

        return None

    @staticmethod
    def GetPrevVisible(item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        raise Exception('\nERROR: Not Implemented')

    def ResetTextControl(self):
        self._text_ctrl.Destroy()
        self._text_ctrl = None
        return

    def FindItem(self, id_parent, prefix_orig):
        prefix = prefix_orig.lower()
        parent_id = id_parent
        if len(prefix) == 1:
            parent_id = self.GetNext(parent_id)
        while parent_id and not self.GetItemText(parent_id).lower().startswith(prefix):
            parent_id = self.GetNext(parent_id)

        if not parent_id:
            parent_id = self.GetRootItem()
            if self.HasFlag(TR_HIDE_ROOT):
                parent_id = self.GetNext(parent_id)
            while parent_id != id_parent and not self.GetItemText(parent_id).lower().startswith(prefix):
                parent_id = self.GetNext(parent_id)

        return parent_id

    def DoInsertItem(self, parentId, previous, text, ct_type=0, wnd=None, image=-1, selImage=-1, data=None):
        if wnd is not None and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception(
                '\nERROR: In Order To Append/Insert Controls You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if text.find('\n') >= 0 and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception(
                '\nERROR: In Order To Append/Insert A MultiLine Text You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if ct_type < 0 or ct_type > 2:
            raise Exception('\nERROR: Item Type Should Be 0 (Normal), 1 (CheckBox) or 2 (RadioButton). ')
        parent = parentId
        if not parent:
            return self.AddRoot(text, ct_type, wnd, image, selImage, data)
        self._dirty = True
        item = GenericTreeItem(parent, text, ct_type, wnd, image, selImage, data)
        if wnd is not None:
            self._hasWindows = True
            self._item_with_window.append(item)
        parent.Insert(item, previous)
        return item

    def AddRoot(self, text, ct_type=0, wnd=None, image=-1, selImage=-1, data=None):
        if self._anchor:
            raise Exception('\nERROR: Tree Can Have Only One Root')
        if wnd is not None and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception(
                '\nERROR: In Order To Append/Insert Controls You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if text.find('\n') >= 0 and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception(
                '\nERROR: In Order To Append/Insert A MultiLine Text You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if ct_type < 0 or ct_type > 2:
            raise Exception('\nERROR: Item Type Should Be 0 (Normal), 1 (CheckBox) or 2 (RadioButton). ')
        self._dirty = True
        self._anchor = GenericTreeItem(None, text, ct_type, wnd, image, selImage, data)
        if wnd is not None:
            self._hasWindows = True
            self._item_with_window.append(self._anchor)
        if self.HasFlag(TR_HIDE_ROOT):
            self._anchor.SetHasPlus()
            self._anchor.Expand()
            self.CalculatePositions()
        if not self.HasFlag(TR_MULTIPLE):
            self._current = self._key_current = self._anchor
            self._current.SetHilight(True)
        return self._anchor

    def PrependItem(self, parent, text, ct_type=0, wnd=None, image=-1, selImage=-1, data=None):
        if wnd is not None and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception(
                '\nERROR: In Order To Append/Insert Controls You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if text.find('\n') >= 0 and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception(
                '\nERROR: In Order To Append/Insert A MultiLine Text You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        return self.DoInsertItem(parent, 0, text, ct_type, wnd, image, selImage, data)

    def InsertItemByItem(self, parentId, idPrevious, text, ct_type=0, wnd=None, image=-1, selImage=-1, data=None):
        if wnd is not None and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception(
                '\nERROR: In Order To Append/Insert Controls You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if text.find('\n') >= 0 and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception(
                '\nERROR: In Order To Append/Insert A MultiLine Text You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        parent = parentId
        if not parent:
            return self.AddRoot(text, ct_type, wnd, image, selImage, data)
        index = -1
        if idPrevious:
            try:
                index = parent.GetChildren().index(idPrevious)
            except:
                raise Exception('ERROR: Previous Item In CustomTreeCtrl.InsertItem() Is Not A Sibling')

        return self.DoInsertItem(parentId, index + 1, text, ct_type, wnd, image, selImage, data)

    def InsertItemByIndex(self, parentId, before, text, ct_type=0, wnd=None, image=-1, selImage=-1, data=None):
        if wnd is not None and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception(
                '\nERROR: In Order To Append/Insert Controls You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if text.find('\n') >= 0 and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception(
                '\nERROR: In Order To Append/Insert A MultiLine Text You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        parent = parentId
        if not parent:
            return self.AddRoot(text, ct_type, wnd, image, selImage, data)
        return self.DoInsertItem(parentId, before, text, ct_type, wnd, image, selImage, data)

    def InsertItem(self, parentId, input, text, ct_type=0, wnd=None, image=-1, selImage=-1, data=None):
        if wnd is not None and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception(
                '\nERROR: In Order To Append/Insert Controls You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if text.find('\n') >= 0 and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception(
                '\nERROR: In Order To Append/Insert A MultiLine Text You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if type(input) == type(1):
            return self.InsertItemByIndex(parentId, input, text, ct_type, wnd, image, selImage, data)
        else:
            return self.InsertItemByItem(parentId, input, text, ct_type, wnd, image, selImage, data)

    def AppendItem(self, parentId, text, ct_type=0, wnd=None, image=-1, selImage=-1, data=None):
        if wnd is not None and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception(
                '\nERROR: In Order To Append/Insert Controls You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if text.find('\n') >= 0 and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception(
                '\nERROR: In Order To Append/Insert A MultiLine Text You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        parent = parentId
        if not parent:
            return self.AddRoot(text, ct_type, wnd, image, selImage, data)
        return self.DoInsertItem(parent, len(parent.GetChildren()), text, ct_type, wnd, image, selImage, data)

    def SendDeleteEvent(self, item):
        event = TreeEvent(wxEVT_TREE_DELETE_ITEM, self.GetId())
        event._item = item
        event.SetEventObject(self)
        self.ProcessEvent(event)

    @staticmethod
    def IsDescendantOf(parent, item):
        while item:
            if item == parent:
                return True
            item = item.GetParent()

        return False

    def ChildrenClosing(self, item):
        if self._text_ctrl is not None and item != self._text_ctrl.item() and self.IsDescendantOf(item,
                                                                                                  self._text_ctrl.item()):
            self._text_ctrl.StopEditing()
        if item != self._key_current and self.IsDescendantOf(item, self._key_current):
            self._key_current = None
        if self.IsDescendantOf(item, self._select_me):
            self._select_me = item
        if item != self._current and self.IsDescendantOf(item, self._current):
            self._current.SetHilight(False)
            self._current = None
            self._select_me = item
        return

    def DeleteChildren(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        self._dirty = True
        self.ChildrenClosing(item)
        item.DeleteChildren(self)

    def Delete(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        self._dirty = True
        if self._text_ctrl is not None and self.IsDescendantOf(item, self._text_ctrl.item()):
            self._text_ctrl.StopEditing()
        parent = item.GetParent()
        if self.IsDescendantOf(item, self._key_current):
            self._key_current = None
        if self._select_me and self.IsDescendantOf(item, self._select_me):
            self._select_me = parent
        if self.IsDescendantOf(item, self._current):
            self._current = None
            self._select_me = parent
        if parent:
            parent.GetChildren().remove(item)
        else:
            self._anchor = None
        item.DeleteChildren(self)
        self.SendDeleteEvent(item)
        if item == self._select_me:
            self._select_me = None
        if item in self._item_with_window:
            wnd = item.GetWindow()
            wnd.Hide()
            wnd.Destroy()
            item._wnd = None
            self._item_with_window.remove(item)
        del item
        return

    def DeleteAllItems(self):
        if self._anchor:
            self.Delete(self._anchor)

    def Expand(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        if self.HasFlag(TR_HIDE_ROOT) and item == self.GetRootItem():
            raise Exception("\nERROR: Can't Expand An Hidden Root. ")
        if not item.HasPlus():
            return
        if item.IsExpanded():
            return
        event = TreeEvent(wxEVT_TREE_ITEM_EXPANDING, self.GetId())
        event._item = item
        event.SetEventObject(self)
        if self.ProcessEvent(event) and not event.IsAllowed():
            return
        item.Expand()
        self.CalculatePositions()
        self.RefreshSubtree(item)
        if self._hasWindows:
            self.HideWindows()
        event.SetEventType(wxEVT_TREE_ITEM_EXPANDED)
        self.ProcessEvent(event)

    def ExpandAllChildren(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        if not self.HasFlag(TR_HIDE_ROOT) or item != self.GetRootItem():
            self.Expand(item)
            if not self.IsExpanded(item):
                return
        child, cookie = self.GetFirstChild(item)
        while child:
            self.ExpandAllChildren(child)
            child, cookie = self.GetNextChild(item, cookie)

    def ExpandAll(self):
        if self._anchor:
            self.ExpandAllChildren(self._anchor)

    def Collapse(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        if self.HasFlag(TR_HIDE_ROOT) and item == self.GetRootItem():
            raise Exception("\nERROR: Can't Collapse An Hidden Root. ")
        if not item.IsExpanded():
            return
        event = TreeEvent(wxEVT_TREE_ITEM_COLLAPSING, self.GetId())
        event._item = item
        event.SetEventObject(self)
        if self.ProcessEvent(event) and not event.IsAllowed():
            return
        self.ChildrenClosing(item)
        item.Collapse()
        self.CalculatePositions()
        self.RefreshSubtree(item)
        if self._hasWindows:
            self.HideWindows()
        event.SetEventType(wxEVT_TREE_ITEM_COLLAPSED)
        self.ProcessEvent(event)

    def CollapseAndReset(self, item):
        self.Collapse(item)
        self.DeleteChildren(item)

    def Toggle(self, item):
        if item.IsExpanded():
            self.Collapse(item)
        else:
            self.Expand(item)

    def HideWindows(self):
        for child in self._item_with_window:
            if not self.IsVisible(child):
                wnd = child.GetWindow()
                wnd.Hide()

    def Unselect(self):
        if self._current:
            self._current.SetHilight(False)
            self.RefreshLine(self._current)
        self._current = None
        self._select_me = None
        return

    def UnselectAllChildren(self, item):
        if item.IsSelected():
            item.SetHilight(False)
            self.RefreshLine(item)
        if item.HasChildren():
            for child in item.GetChildren():
                self.UnselectAllChildren(child)

    def UnselectAll(self):
        rootItem = self.GetRootItem()
        if rootItem:
            self.UnselectAllChildren(rootItem)
        self.Unselect()

    def TagNextChildren(self, crt_item, last_item, select):
        parent = crt_item.GetParent()
        if parent is None:
            return self.TagAllChildrenUntilLast(crt_item, last_item, select)
        children = parent.GetChildren()
        index = children.index(crt_item)
        count = len(children)
        for n in range(index + 1, count):
            if self.TagAllChildrenUntilLast(children[n], last_item, select):
                return True

        return self.TagNextChildren(parent, last_item, select)

    def TagAllChildrenUntilLast(self, crt_item, last_item, select):
        crt_item.SetHilight(select)
        self.RefreshLine(crt_item)
        if crt_item == last_item:
            return True
        if crt_item.HasChildren():
            for child in crt_item.GetChildren():
                if self.TagAllChildrenUntilLast(child, last_item, select):
                    return True

        return False

    def SelectItemRange(self, item1, item2):
        self._select_me = None
        first = (item1.GetY() < item2.GetY() and [item1] or [item2])[0]
        last = (item1.GetY() < item2.GetY() and [item2] or [item1])[0]
        select = self._current.IsSelected()
        if self.TagAllChildrenUntilLast(first, last, select):
            return
        self.TagNextChildren(first, last, select)
        return

    def DoSelectItem(self, item, unselect_others=True, extended_select=False):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        self._select_me = None
        is_single = not self.GetTreeStyle() & TR_MULTIPLE
        if is_single:
            if item.IsSelected():
                return
            unselect_others = True
            extended_select = False
        elif unselect_others and item.IsSelected():
            if len(self.GetSelections()) == 1:
                return
        event = TreeEvent(wxEVT_TREE_SEL_CHANGING, self.GetId())
        event._item = item
        event._item_old = self._current
        event.SetEventObject(self)
        if self.GetEventHandler().ProcessEvent(event) and not event.IsAllowed():
            return
        parent = self.GetItemParent(item)
        while parent:
            if not self.IsExpanded(parent):
                self.Expand(parent)
            parent = self.GetItemParent(parent)

        if unselect_others:
            if is_single:
                self.Unselect()
            else:
                self.UnselectAll()
        if extended_select:
            if not self._current:
                self._current = self._key_current = self.GetRootItem()
            self.SelectItemRange(self._current, item)
        else:
            select = True
            if not unselect_others:
                select = not item.IsSelected()
            self._current = self._key_current = item
            self._current.SetHilight(select)
            self.RefreshLine(self._current)
        self.EnsureVisible(item)
        event.SetEventType(wxEVT_TREE_SEL_CHANGED)
        self.GetEventHandler().ProcessEvent(event)
        if self.IsItemHyperText(item):
            event = TreeEvent(wxEVT_TREE_ITEM_HYPERLINK, self.GetId())
            event._item = item
            self.GetEventHandler().ProcessEvent(event)
        return

    def SelectItem(self, item, select=True):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        if select:
            self.DoSelectItem(item, not self.HasFlag(TR_MULTIPLE))
        else:
            item.SetHilight(False)
            self.RefreshLine(item)

    def FillArray(self, item, array=None):
        if array is None:
            array = []
        if item.IsSelected():
            array.append(item)
        if item.HasChildren() and item.IsExpanded():
            for child in item.GetChildren():
                array = self.FillArray(child, array)

        return array

    def GetSelections(self):
        array = []
        idRoot = self.GetRootItem()
        if idRoot:
            array = self.FillArray(idRoot, array)
        return array

    def EnsureVisible(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        parent = item.GetParent()
        if self.HasFlag(TR_HIDE_ROOT):
            while parent and parent != self._anchor:
                self.Expand(parent)
                parent = parent.GetParent()

        else:
            while parent:
                self.Expand(parent)
                parent = parent.GetParent()

        self.ScrollTo(item)

    def ScrollTo(self, item):
        if not item:
            return
        if self._dirty:
            if wx.Platform in ['__WXMSW__', '__WXMAC__']:
                self.Update()
        else:
            wx.YieldIfNeeded()
        item_y = item.GetY()
        start_x, start_y = self.GetViewStart()
        start_y *= _PIXELS_PER_UNIT
        client_w, client_h = self.GetClientSize()
        x, y = (0, 0)
        if item_y < start_y + 3:
            x, y = self._anchor.GetSize(x, y, self)
            y += _PIXELS_PER_UNIT + 2
            x += _PIXELS_PER_UNIT + 2
            x_pos = self.GetScrollPos(wx.HORIZONTAL)
            self.SetScrollbars(_PIXELS_PER_UNIT, _PIXELS_PER_UNIT, x / _PIXELS_PER_UNIT, y / _PIXELS_PER_UNIT, x_pos,
                               item_y / _PIXELS_PER_UNIT)
        elif item_y + self.GetLineHeight(item) > start_y + client_h:
            x, y = self._anchor.GetSize(x, y, self)
            y += _PIXELS_PER_UNIT + 2
            x += _PIXELS_PER_UNIT + 2
            item_y += _PIXELS_PER_UNIT + 2
            x_pos = self.GetScrollPos(wx.HORIZONTAL)
            self.SetScrollbars(_PIXELS_PER_UNIT, _PIXELS_PER_UNIT, x / _PIXELS_PER_UNIT, y / _PIXELS_PER_UNIT, x_pos,
                               (item_y + self.GetLineHeight(item) - client_h) / _PIXELS_PER_UNIT)

    def OnCompareItems(self, item1, item2):
        return self.GetItemText(item1) == self.GetItemText(item2)

    def SortChildren(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        children = item.GetChildren()
        if len(children) > 1:
            self._dirty = True
            children.sort(self.OnCompareItems)

    def GetImageList(self):
        return self._image_list_normal

    def GetButtonsImageList(self):
        return self._image_list_buttons

    def GetStateImageList(self):
        return self._image_list_state

    def GetImageListCheck(self):
        return self._image_list_check

    def CalculateLineHeight(self):
        dc = wx.ClientDC(self)
        self._lineHeight = dc.GetCharHeight()
        if self._image_list_normal:
            n = self._image_list_normal.GetImageCount()
            for i in range(n):
                width, height = self._image_list_normal.GetSize(i)
                if height > self._lineHeight:
                    self._lineHeight = height

        if self._image_list_buttons:
            n = self._image_list_buttons.GetImageCount()
            for i in range(n):
                width, height = self._image_list_buttons.GetSize(i)
                if height > self._lineHeight:
                    self._lineHeight = height

        if self._image_list_check:
            n = self._image_list_check.GetImageCount()
            for i in range(n):
                width, height = self._image_list_check.GetSize(i)
                if height > self._lineHeight:
                    self._lineHeight = height

        if self._lineHeight < 30:
            self._lineHeight += 2
        else:
            self._lineHeight += self._lineHeight / 10

    def SetImageList(self, imageList):
        if self._owns_image_list_normal:
            del self._image_list_normal
        self._image_list_normal = imageList
        self._owns_image_list_normal = False
        self._dirty = True
        if imageList:
            self.CalculateLineHeight()
            sz = imageList.GetSize(0)
            self._image_list_grayed = wx.ImageList(sz[0], sz[1], True, 0)
            for ii in range(imageList.GetImageCount()):
                bmp = imageList.GetBitmap(ii)
                image = wx.ImageFromBitmap(bmp)
                image = gray_out(image)
                new_bitmap = wx.BitmapFromImage(image)
                self._image_list_grayed.Add(new_bitmap)

    def SetStateImageList(self, imageList):
        if self._owns_image_list_state:
            del self._image_list_state
        self._image_list_state = imageList
        self._owns_image_list_state = False

    def SetButtonsImageList(self, imageList):
        if self._owns_image_list_buttons:
            del self._image_list_buttons
        self._image_list_buttons = imageList
        self._owns_image_list_buttons = False
        self._dirty = True
        self.CalculateLineHeight()

    def SetImageListCheck(self, sizex, sizey, imglist=None):
        if imglist is None:
            self._image_list_check = wx.ImageList(sizex, sizey)
            self._image_list_check.Add(get_checked_bitmap())
            self._image_list_check.Add(get_not_checked_bitmap())
            self._image_list_check.Add(get_flagged_bitmap())
            self._image_list_check.Add(get_not_flagged_bitmap())
        else:
            sizex, sizey = imglist.GetSize(0)
            self._image_list_check = imglist
        self._grayedCheckList = wx.ImageList(sizex, sizey, True, 0)
        for ii in range(self._image_list_check.GetImageCount()):
            bmp = self._image_list_check.GetBitmap(ii)
            image = wx.ImageFromBitmap(bmp)
            image = gray_out(image)
            newbmp = wx.BitmapFromImage(image)
            self._grayedCheckList.Add(newbmp)

        self._dirty = True
        if imglist:
            self.CalculateLineHeight()
        return

    def AssignImageList(self, imageList):
        self.SetImageList(imageList)
        self._owns_image_list_normal = True

    def AssignStateImageList(self, imageList):
        self.SetStateImageList(imageList)
        self._owns_image_list_state = True

    def AssignButtonsImageList(self, imageList):
        self.SetButtonsImageList(imageList)
        self._owns_image_list_buttons = True

    def AdjustMyScrollbars(self):
        if self._anchor:
            x, y = self._anchor.GetSize(0, 0, self)
            y += _PIXELS_PER_UNIT + 2
            x += _PIXELS_PER_UNIT + 2
            x_pos = self.GetScrollPos(wx.HORIZONTAL)
            y_pos = self.GetScrollPos(wx.VERTICAL)
            self.SetScrollbars(_PIXELS_PER_UNIT, _PIXELS_PER_UNIT, x / _PIXELS_PER_UNIT, y / _PIXELS_PER_UNIT, x_pos,
                               y_pos)
        else:
            self.SetScrollbars(0, 0, 0, 0)

    def GetLineHeight(self, item):
        if self.GetTreeStyle() & TR_HAS_VARIABLE_ROW_HEIGHT:
            return item.GetHeight()
        else:
            return self._lineHeight

    def DrawVerticalGradient(self, dc, rect, has_focus: bool):
        old_pen = dc.GetPen()
        old_brush = dc.GetBrush()
        dc.SetPen(wx.TRANSPARENT_PEN)
        if has_focus:
            col2 = self._second_colour
            col1 = self._first_colour
        else:
            col2 = self._hilight_unfocused_brush.GetColour()
            col1 = self._hilight_unfocused_brush2.GetColour()
        r1, g1, b1 = int(col1.Red()), int(col1.Green()), int(col1.Blue())
        r2, g2, b2 = int(col2.Red()), int(col2.Green()), int(col2.Blue())
        rect_height = float(rect.height)
        r_step = float(r2 - r1) / rect_height
        g_step = float(g2 - g1) / rect_height
        b_step = float(b2 - b1) / rect_height
        rf, gf, bf = (0, 0, 0)
        for y in range(rect.y, rect.y + rect.height):
            currCol = (r1 + rf, g1 + gf, b1 + bf)
            dc.SetBrush(wx.Brush(currCol, wx.SOLID))
            dc.DrawRectangle(rect.x, y, rect.width, 1)
            rf = rf + r_step
            gf = gf + g_step
            bf = bf + b_step

        dc.SetPen(old_pen)
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.DrawRectangleRect(rect)
        dc.SetBrush(old_brush)

    def DrawHorizontalGradient(self, dc, rect, has_focus):
        oldpen = dc.GetPen()
        oldbrush = dc.GetBrush()
        dc.SetPen(wx.TRANSPARENT_PEN)
        if has_focus:
            col2 = self._second_colour
            col1 = self._first_colour
        else:
            col2 = self._hilight_unfocused_brush.GetColour()
            col1 = self._hilight_unfocused_brush2.GetColour()
        r1, g1, b1 = int(col1.Red()), int(col1.Green()), int(col1.Blue())
        r2, g2, b2 = int(col2.Red()), int(col2.Green()), int(col2.Blue())
        flrect = float(rect.width)
        rstep = float(r2 - r1) / flrect
        gstep = float(g2 - g1) / flrect
        bstep = float(b2 - b1) / flrect
        rf, gf, bf = (0, 0, 0)
        for x in range(rect.x, rect.x + rect.width):
            currCol = (int(r1 + rf), int(g1 + gf), int(b1 + bf))
            dc.SetBrush(wx.Brush(currCol, wx.SOLID))
            dc.DrawRectangle(x, rect.y, 1, rect.height)
            rf = rf + rstep
            gf = gf + gstep
            bf = bf + bstep

        dc.SetPen(oldpen)
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.DrawRectangleRect(rect)
        dc.SetBrush(oldbrush)

    def DrawVistaRectangle(self, dc, rect, hasfocus):
        if hasfocus:
            outer = _rgbSelectOuter
            inner = _rgbSelectInner
            top = _rgbSelectTop
            bottom = _rgbSelectBottom
        else:
            outer = _rgbNoFocusOuter
            inner = _rgbNoFocusInner
            top = _rgbNoFocusTop
            bottom = _rgbNoFocusBottom
        oldpen = dc.GetPen()
        oldbrush = dc.GetBrush()
        bdrRect = wx.Rect(*rect.Get())
        filRect = wx.Rect(*rect.Get())
        filRect.Deflate(1, 1)
        r1, g1, b1 = int(top.Red()), int(top.Green()), int(top.Blue())
        r2, g2, b2 = int(bottom.Red()), int(bottom.Green()), int(bottom.Blue())
        flrect = float(filRect.height)
        rstep = float(r2 - r1) / flrect
        gstep = float(g2 - g1) / flrect
        bstep = float(b2 - b1) / flrect
        rf, gf, bf = (0, 0, 0)
        dc.SetPen(wx.TRANSPARENT_PEN)
        for y in range(filRect.y, filRect.y + filRect.height):
            currCol = (r1 + rf, g1 + gf, b1 + bf)
            dc.SetBrush(wx.Brush(currCol, wx.SOLID))
            dc.DrawRectangle(filRect.x, y, filRect.width, 1)
            rf = rf + rstep
            gf = gf + gstep
            bf = bf + bstep

        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.SetPen(wx.Pen(outer))
        dc.DrawRoundedRectangleRect(bdrRect, 3)
        bdrRect.Deflate(1, 1)
        dc.SetPen(wx.Pen(inner))
        dc.DrawRoundedRectangleRect(bdrRect, 2)
        dc.SetPen(oldpen)
        dc.SetBrush(oldbrush)

    def PaintItem(self, item, dc):
        attr = item.GetAttributes()
        if attr:
            if attr.HasFont():
                dc.SetFont(attr.GetFont())
            elif item.IsBold():
                dc.SetFont(self._bold_font)
            if item.IsHyperText():
                dc.SetFont(self.GetHyperTextFont())
                if item.GetVisited():
                    dc.SetTextForeground(self.GetHyperTextVisitedColour())
                else:
                    dc.SetTextForeground(self.GetHyperTextNewColour())
            text_w, text_h, dummy = dc.GetMultiLineTextExtent(item.GetText())
            image = item.GetCurrentImage()
            checkimage = item.GetCurrentCheckedImage()
            image_w, image_h = (0, 0)
            if image != _NO_IMAGE:
                if self._image_list_normal:
                    image_w, image_h = self._image_list_normal.GetSize(image)
                    image_w += 4
                else:
                    image = _NO_IMAGE
            if item.GetType() != 0:
                width_check, hcheck = self._image_list_check.GetSize(item.GetType())
                width_check += 4
            else:
                width_check, hcheck = (0, 0)
            total_h = self.GetLineHeight(item)
            _draw_item_background = False
            if item.IsSelected():
                if wx.Platform == '__WXMAC__':
                    self._hasFocus or dc.SetBrush(wx.TRANSPARENT_BRUSH)
                    dc.SetPen(wx.Pen(wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHT), 1, wx.SOLID))
                else:
                    dc.SetBrush(self._hilightBrush)
            else:
                dc.SetBrush((self._hasFocus and [self._hilightBrush] or [self._hilight_unfocused_brush])[0])
                _draw_item_background = True
        else:
            if attr and attr.HasBackgroundColour():
                _draw_item_background = True
                colBg = attr.GetBackgroundColour()
            else:
                colBg = self._backgroundColour
            dc.SetBrush(wx.Brush(colBg, wx.SOLID))
            dc.SetPen(wx.TRANSPARENT_PEN)
        offset = (self.HasFlag(TR_ROW_LINES) and [1] or [0])[0]
        if self.HasFlag(TR_FULL_ROW_HIGHLIGHT):
            x = 0
            w, h = self.GetClientSize()
            itemrect = wx.Rect(x, item.GetY() + offset, w, total_h - offset)
            if item.IsSelected():
                if self._use_gradients:
                    if self._gradient_style == 0:
                        self.DrawHorizontalGradient(dc, itemrect, self._hasFocus)
                    else:
                        self.DrawVerticalGradient(dc, itemrect, self._hasFocus)
                elif self._vista_selection:
                    self.DrawVistaRectangle(dc, itemrect, self._hasFocus)
                elif wx.Platform in ['__WXGTK2__', '__WXMAC__']:
                    flags = wx.CONTROL_SELECTED
                    if self._hasFocus:
                        flags = flags | wx.CONTROL_FOCUSED
                    wx.RendererNative.Get().DrawItemSelectionRect(self, dc, itemrect, flags)
                else:
                    dc.DrawRectangleRect(itemrect)
        else:
            if item.IsSelected():
                wnd = item.GetWindow()
                window_x = 0
                if wnd:
                    window_x, wndy = item.GetWindowSize()
                itemrect = wx.Rect(item.GetX() + width_check + image_w - 2, item.GetY() + offset,
                                   item.GetWidth() - image_w - width_check + 2 - window_x, total_h - offset)
                if self._use_gradients:
                    if self._gradient_style == 0:
                        self.DrawHorizontalGradient(dc, itemrect, self._hasFocus)
                    else:
                        self.DrawVerticalGradient(dc, itemrect, self._hasFocus)
                elif self._vista_selection:
                    self.DrawVistaRectangle(dc, itemrect, self._hasFocus)
                elif wx.Platform in ['__WXGTK2__', '__WXMAC__']:
                    flags = wx.CONTROL_SELECTED
                    if self._hasFocus:
                        flags = flags | wx.CONTROL_FOCUSED
                    wx.RendererNative.Get().DrawItemSelectionRect(self, dc, itemrect, flags)
                else:
                    dc.DrawRectangleRect(itemrect)
            elif _draw_item_background:
                minusicon = width_check + image_w - 2
                itemrect = wx.Rect(item.GetX() + minusicon, item.GetY() + offset, item.GetWidth() - minusicon,
                                   total_h - offset)
                if self._use_gradients and self._hasFocus:
                    if self._gradient_style == 0:
                        self.DrawHorizontalGradient(dc, itemrect, self._hasFocus)
                    else:
                        self.DrawVerticalGradient(dc, itemrect, self._hasFocus)
                else:
                    dc.DrawRectangleRect(itemrect)
            if image != _NO_IMAGE:
                dc.SetClippingRegion(item.GetX(), item.GetY(), width_check + image_w - 2, total_h)
                if item.IsEnabled():
                    imglist = self._image_list_normal
                else:
                    imglist = self._image_list_grayed
                imglist.Draw(image, dc, item.GetX() + width_check,
                             item.GetY() + (total_h > image_h and [(total_h - image_h) / 2] or [0])[0],
                             wx.IMAGELIST_DRAW_TRANSPARENT)
                dc.DestroyClippingRegion()
            if width_check:
                if item.IsEnabled():
                    imglist = self._image_list_check
                else:
                    imglist = self._grayedCheckList
                imglist.Draw(checkimage, dc, item.GetX(),
                             item.GetY() + (total_h > hcheck and [(total_h - hcheck) / 2] or [0])[0],
                             wx.IMAGELIST_DRAW_TRANSPARENT)
            dc.SetBackgroundMode(wx.TRANSPARENT)
            extraH = (total_h > text_h and [(total_h - text_h) / 2] or [0])[0]
            texture_rect = wx.Rect(width_check + image_w + item.GetX(), item.GetY() + extraH, text_w, text_h)
            if not item.IsEnabled():
                foreground = dc.GetTextForeground()
                dc.SetTextForeground(self._disabledColour)
                dc.DrawLabel(item.GetText(), texture_rect)
                dc.SetTextForeground(foreground)
            else:
                if wx.Platform == '__WXMAC__' and item.IsSelected() and self._hasFocus:
                    dc.SetTextForeground(wx.WHITE)
                dc.DrawLabel(item.GetText(), texture_rect)
            wnd = item.GetWindow()
            if wnd:
                window_x = self.GetVirtualSize()[0] - (wnd.GetSize()[0] + 4)
                xa, ya = self.CalcScrolledPosition((0, item.GetY()))
                if not wnd.IsShown():
                    wnd.Show()
                if wnd.GetPosition() != (window_x, ya):
                    wnd.SetPosition((window_x, ya))
        dc.SetFont(self._normal_font)

    def PaintLevel(self, item, dc, level, y):
        x = level * self._indent
        if not self.HasFlag(TR_HIDE_ROOT):
            x += self._indent
        elif level == 0:
            origY = y
            children = item.GetChildren()
            count = len(children)
            if count > 0:
                n = 0
                while n < count:
                    oldY = y
                    y = self.PaintLevel(children[n], dc, 1, y)
                    n = n + 1

                if not self.HasFlag(TR_NO_LINES) and self.HasFlag(TR_LINES_AT_ROOT) and count > 0:
                    origY += self.GetLineHeight(children[0]) >> 1
                    oldY += self.GetLineHeight(children[n - 1]) >> 1
                    dc.DrawLine(3, origY, 3, oldY)
            return y
        item.SetX(x + self._spacing)
        item.SetY(y)
        h = self.GetLineHeight(item)
        y_top = y
        y_mid = y_top + (h >> 1)
        y += h
        exposed_x = dc.LogicalToDeviceX(0)
        exposed_y = dc.LogicalToDeviceY(y_top)
        if self.IsExposed(exposed_x, exposed_y, 10000, h):
            pen = (wx.Platform == '__WXMAC__' and (
                    item.IsSelected() and self._hasFocus and [self._border_pen] or [wx.TRANSPARENT_PEN]))[0]
        else:
            pen = self._border_pen
        if item.IsSelected():
            if wx.Platform == '__WXMAC__' and self._hasFocus:
                colText = wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT)
            else:
                colText = wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT)
        else:
            attr = item.GetAttributes()
            if attr:
                if attr.HasTextColour():
                    colText = attr.GetTextColour()
                else:
                    colText = self.GetForegroundColour()
                if self._vista_selection:
                    colText = wx.BLACK
                dc.SetTextForeground(colText)
                dc.SetPen(pen)
                oldpen = pen
                self.PaintItem(item, dc)
                if self.HasFlag(TR_ROW_LINES):
                    medium_grey = wx.Pen(wx.Colour(200, 200, 200))
                    dc.SetPen((self.GetBackgroundColour() == wx.WHITE and [medium_grey] or [wx.WHITE_PEN])[0])
                    dc.DrawLine(0, y_top, 10000, y_top)
                    dc.DrawLine(0, y, 10000, y)
                dc.SetBrush(wx.WHITE_BRUSH)
                dc.SetTextForeground(wx.BLACK)
                if not self.HasFlag(TR_NO_LINES):
                    dc.SetPen(self._dotted_pen)
                    x_start = x
                    if x > self._indent:
                        x_start -= self._indent
                    elif self.HasFlag(TR_LINES_AT_ROOT):
                        x_start = 3
                    dc.DrawLine(x_start, y_mid, x + self._spacing, y_mid)
                    dc.SetPen(oldpen)
                if item.HasPlus() and self.HasButtons():
                    if self._image_list_buttons:
                        image_h = 0
                        image_w = 0
                        image = (item.IsExpanded() and [TreeItemIcon_Expanded] or [TreeItemIcon_Normal])[0]
                        if item.IsSelected():
                            image += TreeItemIcon_Selected - TreeItemIcon_Normal
                        image_w, image_h = self._image_list_buttons.GetSize(image)
                        xx = x - image_w / 2
                        yy = y_mid - image_h / 2
                        dc.SetClippingRegion(xx, yy, image_w, image_h)
                        self._image_list_buttons.draw(image, dc, xx, yy, wx.IMAGELIST_DRAW_TRANSPARENT)
                        dc.DestroyClippingRegion()
                    elif self._windowStyle & TR_TWIST_BUTTONS:
                        dc.SetPen(wx.BLACK_PEN)
                        dc.SetBrush(self._hilightBrush)
                        button = [wx.Point(), wx.Point(), wx.Point()]
                        if item.IsExpanded():
                            button[0].x = x - 5
                            button[0].y = y_mid - 3
                            button[1].x = x + 5
                            button[1].y = button[0].y
                            button[2].x = x
                            button[2].y = button[0].y + 6
                        else:
                            button[0].x = x - 3
                            button[0].y = y_mid - 5
                            button[1].x = button[0].x
                            button[1].y = y_mid + 5
                            button[2].x = button[0].x + 5
                            button[2].y = y_mid
                        dc.DrawPolygon(button)
                    else:
                        wImage = 9
                        hImage = 9
                        flag = 0
                        if item.IsExpanded():
                            flag |= _CONTROL_EXPANDED
                        if item == self._under_mouse:
                            flag |= _CONTROL_CURRENT
                        self._drawing_function(self, dc, wx.Rect(x - wImage / 2, y_mid - hImage / 2, wImage, hImage),
                                               flag)
            if item.IsExpanded():
                children = item.GetChildren()
                count = len(children)
                if count > 0:
                    n = 0
                    level = level + 1
                    while n < count:
                        oldY = y
                        y = self.PaintLevel(children[n], dc, level, y)
                        n = n + 1

                    if not self.HasFlag(TR_NO_LINES) and count > 0:
                        oldY += self.GetLineHeight(children[n - 1]) >> 1
                        if self.HasButtons():
                            y_mid += 5
                        xOrigin, yOrigin = dc.GetDeviceOrigin()
                        yOrigin = abs(yOrigin)
                        width, height = self.GetClientSize()
                        if y_mid < yOrigin:
                            y_mid = yOrigin
                        if oldY > yOrigin + height:
                            oldY = yOrigin + height
                        if y_mid < oldY:
                            dc.SetPen(self._dotted_pen)
                            dc.DrawLine(x, y_mid, x, oldY)
        return y

    def OnPaint(self, event):
        dc = wx.PaintDC(self)
        self.PrepareDC(dc)
        if not self._anchor:
            return
        dc.SetFont(self._normal_font)
        dc.SetPen(self._dotted_pen)
        y = 2
        self.PaintLevel(self._anchor, dc, 0, y)

    def OnEraseBackground(self, event):
        if not self._background_image:
            event.Skip()
            return
        if self._imageStretchStyle == _StyleTile:
            dc = event.GetDC()
            if not dc:
                dc = wx.ClientDC(self)
                rect = self.GetUpdateRegion().GetBox()
                dc.SetClippingRect(rect)
            self.TileBackground(dc)

    def TileBackground(self, dc):
        sz = self.GetClientSize()
        w = self._background_image.GetWidth()
        h = self._background_image.GetHeight()
        x = 0
        while x < sz.width:
            y = 0
            while y < sz.height:
                dc.DrawBitmap(self._background_image, x, y, True)
                y = y + h

            x = x + w

    def OnSetFocus(self, event):
        self._hasFocus = True
        self.RefreshSelected()
        event.Skip()

    def OnKillFocus(self, event):
        self._hasFocus = False
        self.RefreshSelected()
        event.Skip()

    def OnKeyDown(self, event):
        te = TreeEvent(wxEVT_TREE_KEY_DOWN, self.GetId())
        te._event_key = event
        te.SetEventObject(self)
        if self.GetEventHandler().ProcessEvent(te):
            return
        if self._current is None or self._key_current is None:
            event.Skip()
            return
        is_multiple, extended_select, unselect_others = EventFlagsToSelType(self.GetTreeStyle(), event.ShiftDown(),
                                                                            event.CmdDown())
        keyCode = event.GetKeyCode()
        if keyCode in [ord('+'), wx.WXK_ADD]:
            if self._current.HasPlus() and not self.IsExpanded(self._current) and self.IsEnabled(self._current):
                self.Expand(self._current)
        if keyCode in [ord('*'), wx.WXK_MULTIPLY]:
            if not self.IsExpanded(self._current) and self.IsEnabled(self._current):
                self.ExpandAll()
        if keyCode in [ord('-'), wx.WXK_SUBTRACT]:
            if self.IsExpanded(self._current):
                self.Collapse(self._current)
        elif keyCode == wx.WXK_MENU:
            itemRect = self.GetBoundingRect(self._current, True)
            event = TreeEvent(wxEVT_TREE_ITEM_MENU, self.GetId())
            event._item = self._current
            event._point_drag = wx.Point(itemRect.GetX(), itemRect.GetY() + itemRect.GetHeight() / 2)
            event.SetEventObject(self)
            self.GetEventHandler().ProcessEvent(event)
        elif keyCode in [wx.WXK_RETURN, wx.WXK_SPACE]:
            if not self.IsEnabled(self._current):
                event.Skip()
                return
            if not event.HasModifiers():
                event = TreeEvent(wxEVT_TREE_ITEM_ACTIVATED, self.GetId())
                event._item = self._current
                event.SetEventObject(self)
                self.GetEventHandler().ProcessEvent(event)
                if keyCode == wx.WXK_SPACE and self.GetItemType(self._current) > 0:
                    checked = not self.IsItemChecked(self._current)
                    self.CheckItem(self._current, checked)
            event.Skip()
        elif keyCode == wx.WXK_UP:
            prev = self.GetPrevSibling(self._key_current)
            if not prev:
                prev = self.GetItemParent(self._key_current)
                if prev == self.GetRootItem() and self.HasFlag(TR_HIDE_ROOT):
                    return
                if prev:
                    current = self._key_current
                    if current == self.GetFirstChild(prev)[0] and self.IsEnabled(prev):
                        self.DoSelectItem(prev, unselect_others, extended_select)
                        self._key_current = prev
            else:
                current = self._key_current
                while self.IsExpanded(prev) and self.HasChildren(prev):
                    child = self.GetLastChild(prev)
                    if child:
                        prev = child
                        current = prev

                while prev and not self.IsEnabled(prev):
                    prev = self.GetPrevSibling(prev)

                if not prev:
                    prev = self.GetItemParent(current)
                    while prev and not self.IsEnabled(prev):
                        prev = self.GetItemParent(prev)

                if prev:
                    self.DoSelectItem(prev, unselect_others, extended_select)
                    self._key_current = prev
        elif keyCode == wx.WXK_LEFT:
            prev = self.GetItemParent(self._current)
            if prev == self.GetRootItem() and self.HasFlag(TR_HIDE_ROOT):
                prev = self.GetPrevSibling(self._current)
            if self.IsExpanded(self._current):
                self.Collapse(self._current)
            elif prev and self.IsEnabled(prev):
                self.DoSelectItem(prev, unselect_others, extended_select)
        elif keyCode == wx.WXK_RIGHT:
            if self.IsExpanded(self._current) and self.HasChildren(self._current):
                child, cookie = self.GetFirstChild(self._key_current)
                if self.IsEnabled(child):
                    self.DoSelectItem(child, unselect_others, extended_select)
                    self._key_current = child
            else:
                self.Expand(self._current)
        elif keyCode == wx.WXK_DOWN:
            if self.IsExpanded(self._key_current) and self.HasChildren(self._key_current):
                child = self.GetNextActiveItem(self._key_current)
                if child:
                    self.DoSelectItem(child, unselect_others, extended_select)
                    self._key_current = child
            else:
                next = self.GetNextSibling(self._key_current)
                if not next:
                    current = self._key_current
                    while current and not next:
                        current = self.GetItemParent(current)
                        if current:
                            next = self.GetNextSibling(current)
                            if not next or not self.IsEnabled(next):
                                next = None

                else:
                    while next and not self.IsEnabled(next):
                        next = self.GetNext(next)

                if next:
                    self.DoSelectItem(next, unselect_others, extended_select)
                    self._key_current = next
        elif keyCode == wx.WXK_END:
            last = self.GetRootItem()
            while last and self.IsExpanded(last):
                lastChild = self.GetLastChild(last)
                if not lastChild:
                    break
                last = lastChild

            if last and self.IsEnabled(last):
                self.DoSelectItem(last, unselect_others, extended_select)
        elif keyCode == wx.WXK_HOME:
            prev = self.GetRootItem()
            if not prev:
                return
            if self.HasFlag(TR_HIDE_ROOT):
                prev, cookie = self.GetFirstChild(prev)
                if not prev:
                    return
            if self.IsEnabled(prev):
                self.DoSelectItem(prev, unselect_others, extended_select)
        elif not event.HasModifiers() and (
                keyCode >= ord('0') and keyCode <= ord('9') or keyCode >= ord('a') and keyCode <= ord(
            'z') or keyCode >= ord('A') and keyCode <= ord('Z')):
            ch = chr(keyCode)
            id = self.FindItem(self._current, self._find_prefix + ch)
            if not id:
                return
            if self.IsEnabled(id):
                self.SelectItem(id)
            self._find_prefix += ch
            if not self._find_timer:
                self._find_timer = TreeFindTimer(self)
            self._find_timer.Start(_DELAY, wx.TIMER_ONE_SHOT)
        else:
            event.Skip()
        return
