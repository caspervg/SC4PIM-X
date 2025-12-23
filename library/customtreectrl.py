"""Custom tree control for SC4PIM with checkbox and icon support."""
import wx
import zlib
import io
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

def GetFlaggedData():
    return zlib.decompress('x\xda\x012\x02\xcd\xfd\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\r\x00\x00\x00\r\x08\x06\x00\x00\x00r\xeb\xe4|\x00\x00\x00\x04sBIT\x08\x08\x08\x08|\x08d\x88\x00\x00\x01\xe9IDAT(\x91u\x92\xd1K\xd3a\x14\x86\x9f\xef|J2J\xc3%\x85\x8e\x1cb\x93Hl\xd9,\x06F]4\x10\tD3\x83\x88\xc8\xbf\xc0\xb4\xaeBP1\xe9\xa2(\xec\xaan\xc3\x82pD\xa1\x84\xb0\x88@3\x8c\xc9\xa2bT\xa2^\x8c\x81V3\xb6\xb5\x9f\xce9\xbe.j\xb20\xdf\xeb\xf7\xe19\x07^\xa5D\x93\x9f\x9ea\xbf\t\x04\xbf\x12\x8b[\xd8Kl\xf8<.\xeet\xb5\xab\xfc\x8e\xca\x87*ZzM\xf3\xb1j|G\xab\xf0\xd4\x94\x13\x9a_&0\xbb\xc8\xd8\xf4g\xa2\xcfo\xa8-P\xc7\xf5\x07\xa6\xedD\r\x8d\xb5\xfb\x11\x11\xb4\xd6\x88h\xb4\xd6L}\x8a\xf0\xe4\xd5G\x1e\rt*\x00\xc9\x19\xb6\x03D4\xa7\xdcU\\8\xed\xa6\xa2\xa5\xd7\x00\xe8\xab\xf7\x9e\x9a\xca\xb2\x9d\\\xf2\xd5!"dT\x86\xc9\xe4\x14\x83s\x83HF\xe3\xdc\xe5\xa4\xa8\xb0\x88\xaa\xf2=D\x7f$il>\xdf\xafSe\xf5\xfd\x9dM\x87\xa9\xdc\xb7\x1b\xad5\x93\xc9)\xfc\xe9Q\x12\xe9\x04\x13\x0b\x13\x94\xaaR\xdc{\x8f "\xec(,\xe0\xfe\xb3\xb7H,a\xe1\xa9)\xdf<e$2Ble\x85\x94e\xb1\x96\xcep\xfb\xdd-D\x04\xa5\x14\xdeZ\'\xb1\x84\x85\xd8\x8bm\x84\xe6\x977\x7f8kog)\xba\xc4\xb7\xe5\xef$\xe2?\xe9\xa9\xbf\x86R\n\x11a&\x1c\xc1^lC|\r.\x02\xb3\x8b\x9b\xa6&G\x13W\xaa\xbb\x91_\x05\x0c\x1d\xbfI\xc7\xa1\x8e\xbf&a|:\x8c\xaf\xc1\x05J4\x8e\xd6>36\x192\xc9d\xdc\xa4RI\xb3\xbaj\x99tz\xcd\xac\xaf\xa7\xcd\xc6F\xc6d\xb3Y\xf32\xf8\xc58Z\xfb\x8c\x12\xfd\x07R\xa2\xb98\xf0\xd0\xbcx\xf3a[\xe0\xf2\xd0c\x93\xebnYD\xdb\xc9:\xcex\x0f\xe2\xadu2\x13\x8e0>\x1d\xc6\xff\xfa\xfd\xff\x17\x91K\xf7\xf0\xa8\t\x04\xe7X\x89[\x94\x96\xd8\xf0y\x0ep\xb7\xeb\xdc?\xdb\xfb\r|\xd0\xd1]\x98\xbdm\xdc\x00\x00\x00\x00IEND\xaeB`\x82\x91\xe2\x08\x8f')


def GetFlaggedBitmap():
    return wx.BitmapFromImage(GetFlaggedImage())


def GetFlaggedImage():
    stream = io.BytesIO(GetFlaggedData())
    return wx.ImageFromStream(stream)


def GetNotFlaggedData():
    return zlib.decompress('x\xda\x01\xad\x01R\xfe\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\r\x00\x00\x00\r\x08\x06\x00\x00\x00r\xeb\xe4|\x00\x00\x00\x04sBIT\x08\x08\x08\x08|\x08d\x88\x00\x00\x01dIDAT(\x91\x95\xd21K\x82a\x14\x86\xe1\xe7=\xef798\xb8\x89\x0e"|Cd\x94\x88\x83\x065\x88\x108\x88Q\x8b-\xd1\x1f\x88\x9a\n\x04\x11j\x8eh\x08\xdaZ\x84(\x82\xc2 0\xc1 $\xb4P\xa1\x10\x11D\xb061\xd4\xd4\xcc\xe44\x84 \xa8Hg~.\xcer\x0bA\x12\x83\xb7ux\xce\xd1T\x01\xd5z\x0b:\xad\x06n\xbb\x8a\x83\xcdU1\xb8\x11\x83\xc8\xe0\r\xf0\x92\xdd\x0c\x97\xd5\x04\x9b\xaaG\xb6XA,]B\xe41\x8f\xf7\xab=1\x84Vv\x8e\xd97\xaf\xc29m\x04\x91\x84\x94\n\xa4\x94P\x14\x05\x89\xd77\x9c\xc5_\x10\x0em\x08\x00\xa0\xfe\x87q@J\x89\xc593\xfc\xaeY\x18\xbc\x01\x06\x00\xb1}t\xc9\xf5F\x03\x01\xbfs$ \x92 "\x10I\xec\x9e\xdcBQ\x08\x14M\x15\xe0\xb2\x9a&\x02"\x82\xc71\x85h\xaa\x00\xaa\xd6[\xb0\xa9\xfa\x89\x80\x88\xe0\xb0\x98P\xad\xb7@:\xad\x06\xd9be" "$se\xe8\xb4\x1a\x90\xdb\xae"\x96.M\x04D\x84H"\x07\xb7]\x05\x04I\x18}A\xbe\xbe\x7f\xe6Z\xed\x83\x1b\x8d\x1a7\x9b\x9f\xdcn\xb7\xb8\xd3\xf9\xe2n\xf7\x9b{\xbd\x1f\xbe{\xca\xb3\xd1\x17dA\xf2\x0f\t\x92X\x0b\x9d\xf2\xcdCf,X\xdf\x0fs\x7f;T\xc4\xf2\xc2\x0c<\x8e)8,&$seD\x129\\\xc43\xa3\x8b\xf8O{\xbf\xf1\xb5\xa5\x990\x0co\xd6\x00\x00\x00\x00IEND\xaeB`\x82&\x11\xab!')


def GetNotFlaggedBitmap():
    return wx.BitmapFromImage(GetNotFlaggedImage())


def GetNotFlaggedImage():
    stream = io.BytesIO(GetNotFlaggedData())
    return wx.ImageFromStream(stream)


def GetCheckedData():
    return zlib.decompress("x\xda\xeb\x0c\xf0s\xe7\xe5\x92\xe2b``\xe0\xf5\xf4p\t\x02\xd1 \xcc\xc1\x06$\x8b^?\xa9\x01R,\xc5N\x9e!\x1c@P\xc3\x91\xd2\x01\xe4\xaf\xf4tq\x0c\xd1\x98\x98<\x853\xe7\xc7y\x07\xa5\x84\xc4\x84\x84\x04\x0b3C1\xbd\x03'N\x1c9p\x84\xe5\xe0\x993gx||\xce\x14\xcc\xea\xec\xect4^7\xbf\x91\xf3&\x8b\x93\xd4\x8c\x19\n\xa7fv\\L\xd8p\x90C\xebx\xcf\x05\x17\x0ff \xb8c\xb6Cm\x06\xdb\xea\xd8\xb2\x08\xd3\x03W\x0c\x8c\x8c\x16e%\xa5\xb5E\xe4\xee\xba\xca\xe4|\xb8\xb7\xe35OOO\xcf\n\xb3\x83>m\x8c1R\x12\x92\x81s\xd8\x0b/\xb56\x14k|l\\\xc7x\xb4\xf2\xc4\xc1*\xd5'B~\xbc\x19uNG\x98\x85\x85\x8d\xe3x%\x16\xb2_\xee\xf1\x07\x99\xcb\xacl\x99\xc9\xcf\xb0\xc0_.\x87+\xff\x99\x05\xd0\xd1\x0c\x9e\xae~.\xeb\x9c\x12\x9a\x00\x92\xccS\x9f")


def GetCheckedBitmap():
    return wx.BitmapFromImage(GetCheckedImage())


def GetCheckedImage():
    stream = io.BytesIO(GetCheckedData())
    return wx.ImageFromStream(stream)


def GetNotCheckedData():
    return zlib.decompress("x\xda\xeb\x0c\xf0s\xe7\xe5\x92\xe2b``\xe0\xf5\xf4p\t\x02\xd1 \xcc\xc1\x06$\x8b^?\xa9\x01R,\xc5N\x9e!\x1c@P\xc3\x91\xd2\x01\xe4\xe7z\xba8\x86hL\x9c{\xe9 o\x83\x01\x07\xeb\x85\xf3\xed\x86w\x0ed\xdaT\x96\x8a\xbc\x9fw\xe7\xc4\xd9/\x01\x8b\x97\x8a\xd7\xab*\xfar\xf0Ob\x93^\xf6\xd5%\x9d\x85A\xe6\xf6\x1f\x11\x8f{/\x0b\xf8wX+\x9d\xf2\xb6:\x96\xca\xfe\x9a3\xbeA\xe7\xed\x1b\xc6%\xfb=X3'sI-il\t\xb9\xa0\xc0;#\xd4\x835m\x9a\xf9J\x85\xda\x16.\x86\x03\xff\xee\xdcc\xdd\xc0\xce\xf9\xc8\xcc(\xbe\x1bh1\x83\xa7\xab\x9f\xcb:\xa7\x84&\x00\x87S=\xbe")


def GetNotCheckedBitmap():
    return wx.BitmapFromImage(GetNotCheckedImage())


def GetNotCheckedImage():
    stream = io.BytesIO(GetNotCheckedData())
    return wx.ImageFromStream(stream)


def GrayOut(anImage):
    factor = 0.7
    if anImage.HasMask():
        maskColor = (
         anImage.GetMaskRed(), anImage.GetMaskGreen(), anImage.GetMaskBlue())
    else:
        maskColor = None
    data = map(ord, list(anImage.GetData()))
    for i in range(0, len(data), 3):
        pixel = (
         data[i], data[i + 1], data[i + 2])
        pixel = MakeGray(pixel, factor, maskColor)
        for x in range(3):
            data[i + x] = pixel[x]

    anImage.SetData(''.join(map(chr, data)))
    return anImage


def MakeGray((r, g, b), factor, maskColor):
    if (
     r, g, b) != maskColor:
        return map(lambda x: int((230 - x) * factor) + x, (r, g, b))
    else:
        return (
         r, g, b)


def DrawTreeItemButton(win, dc, rect, flags):
    dc.SetPen(wx.GREY_PEN)
    dc.SetBrush(wx.WHITE_BRUSH)
    dc.DrawRectangleRect(rect)
    xMiddle = rect.x + rect.width / 2
    yMiddle = rect.y + rect.height / 2
    halfWidth = rect.width / 2 - 2
    dc.SetPen(wx.BLACK_PEN)
    dc.DrawLine(xMiddle - halfWidth, yMiddle, xMiddle + halfWidth + 1, yMiddle)
    if not flags & _CONTROL_EXPANDED:
        halfHeight = rect.height / 2 - 2
        dc.DrawLine(xMiddle, yMiddle - halfHeight, xMiddle, yMiddle + halfHeight + 1)


class DragImage(wx.DragImage):

    def __init__(self, treeCtrl, item):
        text = item.GetText()
        font = item.Attr().GetFont()
        colour = item.Attr().GetTextColour()
        if not colour:
            colour = wx.BLACK
        if not font:
            font = treeCtrl._normalFont
        backcolour = treeCtrl.GetBackgroundColour()
        r, g, b = int(backcolour.Red()), int(backcolour.Green()), int(backcolour.Blue())
        backcolour = ((r >> 1) + 20, (g >> 1) + 20, (b >> 1) + 20)
        backcolour = wx.Colour(backcolour[0], backcolour[1], backcolour[2])
        self._backgroundColour = backcolour
        tempdc = wx.ClientDC(treeCtrl)
        tempdc.SetFont(font)
        width, height, dummy = tempdc.GetMultiLineTextExtent(text + 'M')
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
            if treeCtrl._imageListNormal:
                image_w, image_h = treeCtrl._imageListNormal.GetSize(image)
                image_w += 4
                itemimage = treeCtrl._imageListNormal.GetBitmap(image)
        checkimage = item.GetCurrentCheckedImage()
        if checkimage is not None:
            if treeCtrl._imageListCheck:
                wcheck, hcheck = treeCtrl._imageListCheck.GetSize(checkimage)
                wcheck += 4
                itemcheck = treeCtrl._imageListCheck.GetBitmap(checkimage)
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
        memory.SetTextBackground(self._backgroundColour)
        memory.SetBackground(wx.Brush(self._backgroundColour))
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

    def __init__(self, colText=wx.NullColour, colBack=wx.NullColour, font=wx.NullFont):
        self._colText = colText
        self._colBack = colBack
        self._font = font

    def SetTextColour(self, colText):
        self._colText = colText

    def SetBackgroundColour(self, colBack):
        self._colBack = colBack

    def SetFont(self, font):
        self._font = font

    def HasTextColour(self):
        return self._colText != wx.NullColour

    def HasBackgroundColour(self):
        return self._colBack != wx.NullColour

    def HasFont(self):
        return self._font != wx.NullFont

    def GetTextColour(self):
        return self._colText

    def GetBackgroundColour(self):
        return self._colBack

    def GetFont(self):
        return self._font


class CommandTreeEvent(wx.PyCommandEvent):

    def __init__(self, type, id, item=None, evtKey=None, point=None, label=None, **kwargs):
        wx.PyCommandEvent.__init__(self, type, id, **kwargs)
        self._item = item
        self._evtKey = evtKey
        self._pointDrag = point
        self._label = label

    def GetItem(self):
        return self._item

    def SetItem(self, item):
        self._item = item

    def GetOldItem(self):
        return self._itemOld

    def SetOldItem(self, item):
        self._itemOld = item

    def GetPoint(self):
        return self._pointDrag

    def SetPoint(self, pt):
        self._pointDrag = pt

    def GetKeyEvent(self):
        return self._evtKey

    def GetKeyCode(self):
        return self._evtKey.GetKeyCode()

    def SetKeyEvent(self, evt):
        self._evtKey = evt

    def GetLabel(self):
        return self._label

    def SetLabel(self, label):
        self._label = label

    def IsEditCancelled(self):
        return self._editCancelled

    def SetEditCanceled(self, editCancelled):
        self._editCancelled = editCancelled

    def SetToolTip(self, toolTip):
        self._label = toolTip

    def GetToolTip(self):
        return self._label


class TreeEvent(CommandTreeEvent):

    def __init__(self, type, id, item=None, evtKey=None, point=None, label=None, **kwargs):
        CommandTreeEvent.__init__(self, type, id, item, evtKey, point, label, **kwargs)
        self.notify = wx.NotifyEvent(type, id)

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
            if self._owner._imageListNormal:
                image_w, image_h = self._owner._imageListNormal.GetSize(image)
                image_w += 4
            else:
                raise Exception('\n ERROR: You Must Create An Image List To Use Images!')
        checkimage = item.GetCurrentCheckedImage()
        if checkimage is not None:
            wcheck, hcheck = self._owner._imageListCheck.GetSize(checkimage)
            wcheck += 4
        else:
            wcheck = 0
        if wnd:
            h = max(hcheck, image_h)
            dc = wx.ClientDC(self._owner)
            h = max(h, dc.GetTextExtent('Aq')[1])
            h = h + 2
        x += image_w + wcheck
        w -= image_w + 4 + wcheck
        wx.TextCtrl.__init__(self, self._owner, wx.ID_ANY, self._startValue, wx.Point(x - 4, y), wx.Size(w + 15, h))
        if wx.Platform == '__WXMAC__':
            self.SetFont(owner.GetFont())
            bs = self.GetBestSize()
            self.SetSize((-1, bs.height))
        self.Bind(wx.EVT_CHAR, self.OnChar)
        self.Bind(wx.EVT_KEY_UP, self.OnKeyUp)
        self.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        return

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
            parentSize = self._owner.GetSize()
            myPos = self.GetPosition()
            mySize = self.GetSize()
            sx, sy = self.GetTextExtent(self.GetValue() + 'M')
            if myPos.x + sx > parentSize.x:
                sx = parentSize.x - myPos.x
            if mySize.x > sx:
                sx = mySize.x
            self.SetSize((sx, -1))
        event.Skip()

    def OnKillFocus(self, event):
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
        self._owner._findPrefix = ''


class GenericTreeItem():

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
        self._checkedimages = [
         None, None, None, None]
        self._x = 0
        self._y = 0
        self._width = 0
        self._height = 0
        self._isCollapsed = True
        self._hasHilight = False
        self._hasPlus = False
        self._isBold = False
        self._isItalic = False
        self._ownsAttr = False
        self._type = ct_type
        self._checked = False
        self._enabled = True
        self._hypertext = False
        self._visited = False
        if self._type > 0:
            self._checkedimages[TreeItemIcon_Checked] = 0
            self._checkedimages[TreeItemIcon_NotChecked] = 1
            self._checkedimages[TreeItemIcon_Flagged] = 2
            self._checkedimages[TreeItemIcon_NotFlagged] = 3
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
            self._windowsize = size
            if self._isCollapsed:
                self._wnd.Show(False)
            self._wnd.Enable(self._enabled)
            self._windowenabled = self._enabled
        return

    def IsOk(self):
        return True

    def GetChildren(self):
        return self._children

    def GetText(self):
        return self._text

    def GetImage(self, which=TreeItemIcon_Normal):
        return self._images[which]

    def GetCheckedImage(self, which=TreeItemIcon_Checked):
        return self._checkedimages[which]

    def GetData(self):
        return self._data

    def SetImage(self, image, which):
        self._images[which] = image

    def SetData(self, data):
        self._data = data

    def SetHasPlus(self, has=True):
        self._hasPlus = has

    def SetBold(self, bold):
        self._isBold = bold

    def SetItalic(self, italic):
        self._isItalic = italic

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
        return self._windowenabled

    def SetWindowEnabled(self, enable=True):
        if not self._wnd:
            raise Exception('\nERROR: This Item Has No Window Associated')
        self._windowenabled = enable
        self._wnd.Enable(enable)

    def GetWindowSize(self):
        return self._windowsize

    def OnSetFocus(self, event):
        treectrl = self._wnd.GetParent()
        select = treectrl.GetSelection()
        if select != self:
            treectrl._hasFocus = False
        else:
            treectrl._hasFocus = True
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
        self._isCollapsed = False

    def Collapse(self):
        self._isCollapsed = True

    def SetHilight(self, set=True):
        self._hasHilight = set

    def HasChildren(self):
        return len(self._children) > 0

    def IsSelected(self):
        return self._hasHilight != 0

    def IsExpanded(self):
        return not self._isCollapsed

    def IsChecked(self):
        return self._checked

    def Check(self, checked=True):
        self._checked = checked

    def HasPlus(self):
        return self._hasPlus or self.HasChildren()

    def IsBold(self):
        return self._isBold != 0

    def IsItalic(self):
        return self._isItalic != 0

    def Enable(self, enable=True):
        self._enabled = enable

    def IsEnabled(self):
        return self._enabled

    def GetAttributes(self):
        return self._attr

    def Attr(self):
        if not self._attr:
            self._attr = TreeItemAttr()
            self._ownsAttr = True
        return self._attr

    def SetAttributes(self, attr):
        if self._ownsAttr:
            del self._attr
        self._attr = attr
        self._ownsAttr = False

    def AssignAttributes(self, attr):
        self.SetAttributes(attr)
        self._ownsAttr = True

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
            if child in tree._itemWithWindow:
                tree._itemWithWindow.remove(child)
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
        for n in xrange(count):
            total += self._children[n].GetChildrenCount()

        return total

    def GetSize(self, x, y, theButton):
        bottomY = self._y + theButton.GetLineHeight(self)
        if y < bottomY:
            y = bottomY
        width = self._x + self._width
        if x < width:
            x = width
        if self.IsExpanded():
            for child in self._children:
                x, y = child.GetSize(x, y, theButton)

        return (x, y)

    def HitTest(self, point, theCtrl, flags=0, level=0):
        if not (level == 0 and theCtrl.HasFlag(TR_HIDE_ROOT)):
            h = theCtrl.GetLineHeight(self)
            if point.y > self._y and point.y < self._y + h:
                y_mid = self._y + h / 2
                if point.y < y_mid:
                    flags |= TREE_HITTEST_ONITEMUPPERPART
                else:
                    flags |= TREE_HITTEST_ONITEMLOWERPART
                xCross = self._x - theCtrl.GetSpacing()
                if wx.Platform == '__WXMAC__':
                    if point.x > xCross - 4 and point.x < xCross + 10 and point.y > y_mid - 4 and point.y < y_mid + 10 and self.HasPlus() and theCtrl.HasButtons():
                        flags |= TREE_HITTEST_ONITEMBUTTON
                        return (
                         self, flags)
                elif point.x > xCross - 6 and point.x < xCross + 6 and point.y > y_mid - 6 and point.y < y_mid + 6 and self.HasPlus() and theCtrl.HasButtons():
                    flags |= TREE_HITTEST_ONITEMBUTTON
                    return (
                     self, flags)
                if point.x >= self._x and point.x <= self._x + self._width:
                    image_w = -1
                    wcheck = 0
                    if self.GetImage() != _NO_IMAGE and theCtrl._imageListNormal:
                        image_w, image_h = theCtrl._imageListNormal.GetSize(self.GetImage())
                    if self.GetCheckedImage() is not None:
                        wcheck, hcheck = theCtrl._imageListCheck.GetSize(self.GetCheckedImage())
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
            if self._isCollapsed:
                return (None, 0)
        for child in self._children:
            res, flags = child.HitTest(point, theCtrl, flags, level + 1)
            if res != None:
                return (res, flags)

        return (None, 0)

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
                return self._checkedimages[TreeItemIcon_Checked]
            else:
                return self._checkedimages[TreeItemIcon_Flagged]
        elif self._type == 1:
            return self._checkedimages[TreeItemIcon_NotChecked]
        else:
            return self._checkedimages[TreeItemIcon_NotFlagged]
        return None


def EventFlagsToSelType(style, shiftDown=False, ctrlDown=False):
    is_multiple = style & TR_MULTIPLE != 0
    extended_select = shiftDown and is_multiple
    unselect_others = not (extended_select or ctrlDown and is_multiple)
    return (
     is_multiple, extended_select, unselect_others)


class CustomTreeCtrl(wx.PyScrolledWindow):

    def __init__(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition, size=wx.DefaultSize, style=TR_DEFAULT_STYLE, ctstyle=0, validator=wx.DefaultValidator, name='CustomTreeCtrl'):
        style = style | ctstyle
        self._current = self._key_current = self._anchor = self._select_me = None
        self._hasFocus = False
        self._dirty = False
        self._lineHeight = 10
        self._indent = 15
        self._spacing = 18
        self._hilightBrush = wx.Brush(wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHT))
        btnshadow = wx.SystemSettings_GetColour(wx.SYS_COLOUR_BTNSHADOW)
        self._hilightUnfocusedBrush = wx.Brush(btnshadow)
        r, g, b = btnshadow.Red(), btnshadow.Green(), btnshadow.Blue()
        backcolour = (max((r >> 1) - 20, 0), max((g >> 1) - 20, 0), max((b >> 1) - 20, 0))
        backcolour = wx.Colour(backcolour[0], backcolour[1], backcolour[2])
        self._hilightUnfocusedBrush2 = wx.Brush(backcolour)
        self._imageListNormal = self._imageListButtons = self._imageListState = self._imageListCheck = None
        self._ownsImageListNormal = self._ownsImageListButtons = self._ownsImageListState = False
        self._dragCount = 0
        self._countDrag = 0
        self._isDragging = False
        self._dropTarget = self._oldSelection = None
        self._dragImage = None
        self._underMouse = None
        self._textCtrl = None
        self._renameTimer = None
        self._freezeCount = 0
        self._findPrefix = ''
        self._findTimer = None
        self._dropEffectAboveItem = False
        self._lastOnSame = False
        self._hasFont = True
        self._normalFont = wx.SystemSettings_GetFont(wx.SYS_DEFAULT_GUI_FONT)
        self._boldFont = wx.Font(self._normalFont.GetPointSize(), self._normalFont.GetFamily(), self._normalFont.GetStyle(), wx.BOLD, self._normalFont.GetUnderlined(), self._normalFont.GetFaceName(), self._normalFont.GetEncoding())
        self._hypertextfont = wx.Font(self._normalFont.GetPointSize(), self._normalFont.GetFamily(), self._normalFont.GetStyle(), wx.NORMAL, True, self._normalFont.GetFaceName(), self._normalFont.GetEncoding())
        self._hypertextnewcolour = wx.BLUE
        self._hypertextvisitedcolour = wx.Colour(200, 47, 200)
        self._isonhyperlink = False
        self._backgroundColour = wx.WHITE
        self._backgroundImage = None
        self._imageStretchStyle = _StyleTile
        self._disabledColour = wx.Colour(180, 180, 180)
        self._firstcolour = color = wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        self._secondcolour = wx.WHITE
        self._usegradients = False
        self._gradientstyle = 0
        self._vistaselection = False
        if wx.Platform != '__WXMAC__':
            self._dottedPen = wx.Pen('grey', 1, wx.USER_DASH)
            self._dottedPen.SetDashes([1, 1])
            self._dottedPen.SetCap(wx.CAP_BUTT)
        else:
            self._dottedPen = wx.Pen('grey', 1)
        self._borderPen = wx.BLACK_PEN
        self._cursor = wx.StockCursor(wx.CURSOR_ARROW)
        self._hasWindows = False
        self._itemWithWindow = []
        if wx.Platform == '__WXMAC__':
            style &= ~TR_LINES_AT_ROOT
            style |= TR_NO_LINES
            platform, major, minor = wx.GetOsVersion()
            if major < 10:
                style |= TR_ROW_LINES
        self._windowStyle = style
        self.SetImageListCheck(13, 13)
        if wx.VERSION_STRING < '2.6.2.1':
            self._drawingfunction = DrawTreeItemButton
        else:
            self._drawingfunction = wx.RendererNative.Get().DrawTreeItemButton
        wx.PyScrolledWindow.__init__(self, parent, id, pos, size, style | wx.HSCROLL | wx.VSCROLL, name)
        if not self.HasButtons() and not self.HasFlag(TR_NO_LINES):
            self._indent = 10
            self._spacing = 10
        self.SetValidator(validator)
        attr = self.GetDefaultAttributes()
        self.SetOwnForegroundColour(attr.colFg)
        self.SetOwnBackgroundColour(wx.WHITE)
        if not self._hasFont:
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

    def AcceptsFocus(self):
        return True

    def OnDestroy(self, event):
        if self._renameTimer and self._renameTimer.IsRunning():
            self._renameTimer.Stop()
            del self._renameTimer
        if self._findTimer and self._findTimer.IsRunning():
            self._findTimer.Stop()
            del self._findTimer
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
        torefresh = False
        if item.IsExpanded():
            torefresh = True
        if item.GetType() == 2 and enable and not item.IsChecked():
            return
        child, cookie = self.GetFirstChild(item)
        while child:
            self.EnableItem(child, enable, torefresh=torefresh)
            if child.GetType != 2 or child.GetType() == 2 and item.IsChecked():
                self.EnableChildren(child, enable)
            child, cookie = self.GetNextChild(item, cookie)

    def EnableItem(self, item, enable=True, torefresh=True):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        if item.IsEnabled() == enable:
            return
        if not enable and item.IsSelected():
            self.SelectItem(item, False)
        item.Enable(enable)
        wnd = item.GetWindow()
        if wnd:
            wndenable = item.GetWindowEnabled()
            if enable:
                if wndenable:
                    wnd.Enable(enable)
            else:
                wnd.Enable(enable)
        if torefresh:
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

    def CheckItem2(self, item, checked=True, torefresh=False):
        if item.GetType() == 0:
            return
        item.Check(checked)
        if torefresh:
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
            ischeck = self.IsItemChecked(item)
            self.AutoCheckChild(item, ischeck)
        if self._windowStyle & TR_AUTO_CHECK_PARENT:
            ischeck = self.IsItemChecked(item)
            self.AutoCheckParent(item, ischeck)
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
        torefresh = False
        if item.IsExpanded():
            torefresh = True
        while child:
            if child.GetType() == 1 and child.IsEnabled():
                self.CheckItem2(child, not child.IsChecked(), torefresh=torefresh)
            self.AutoToggleChild(child)
            child, cookie = self.GetNextChild(item, cookie)

    def AutoCheckChild(self, item, checked):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        child, cookie = self.GetFirstChild(item)
        torefresh = False
        if item.IsExpanded():
            torefresh = True
        while child:
            if child.GetType() == 1 and child.IsEnabled():
                self.CheckItem2(child, checked, torefresh=torefresh)
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

        self.CheckItem2(parent, checked, torefresh=True)
        self.AutoCheckParent(parent, checked)

    def CheckChilds(self, item, checked=True):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        if checked == None:
            self.AutoToggleChild(item)
        else:
            self.AutoCheckChild(item, checked)
        return

    def CheckSameLevel(self, item, checked=False):
        parent = item.GetParent()
        if not parent:
            return
        torefresh = False
        if parent.IsExpanded():
            torefresh = True
        child, cookie = self.GetFirstChild(parent)
        while child:
            if child.GetType() == 2 and child != item:
                self.CheckItem2(child, checked, torefresh=torefresh)
                if child.GetType != 2 or child.GetType() == 2 and child.IsChecked():
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

    def HasChildren(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return len(item.GetChildren()) > 0

    def GetChildrenCount(self, item, recursively=True):
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

    def GetItemText(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.GetText()

    def GetItemImage(self, item, which=TreeItemIcon_Normal):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.GetImage(which)

    def GetPyData(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.GetData()

    GetItemPyData = GetPyData

    def GetItemTextColour(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.Attr().GetTextColour()

    def GetItemBackgroundColour(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.Attr().GetBackgroundColour()

    def GetItemFont(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.Attr().GetFont()

    def IsItemHyperText(self, item):
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
            bg = wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHT)
            fg = wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT)
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
        self._normalFont = font
        self._boldFont = wx.Font(self._normalFont.GetPointSize(), self._normalFont.GetFamily(), self._normalFont.GetStyle(), wx.BOLD, self._normalFont.GetUnderlined(), self._normalFont.GetFaceName(), self._normalFont.GetEncoding())
        return True

    def GetHyperTextFont(self):
        return self._hypertextfont

    def SetHyperTextFont(self, font):
        self._hypertextfont = font
        self._dirty = True

    def SetHyperTextNewColour(self, colour):
        self._hypertextnewcolour = colour
        self._dirty = True

    def GetHyperTextNewColour(self):
        return self._hypertextnewcolour

    def SetHyperTextVisitedColour(self, colour):
        self._hypertextvisitedcolour = colour
        self._dirty = True

    def GetHyperTextVisitedColour(self):
        return self._hypertextvisitedcolour

    def SetItemVisited(self, item, visited=True):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        item.SetVisited(visited)
        self.RefreshLine(item)

    def GetItemVisited(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.GetVisited()

    def SetHilightFocusColour(self, colour):
        self._hilightBrush = wx.Brush(colour)
        self.RefreshSelected()

    def SetHilightNonFocusColour(self, colour):
        self._hilightUnfocusedBrush = wx.Brush(colour)
        self.RefreshSelected()

    def GetHilightFocusColour(self):
        return self._hilightBrush.GetColour()

    def GetHilightNonFocusColour(self):
        return self._hilightUnfocusedBrush.GetColour()

    def SetFirstGradientColour(self, colour=None):
        if colour is None:
            colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        self._firstcolour = colour
        if self._usegradients:
            self.RefreshSelected()
        return

    def SetSecondGradientColour(self, colour=None):
        if colour is None:
            color = self.GetBackgroundColour()
            r, g, b = int(color.Red()), int(color.Green()), int(color.Blue())
            color = ((r >> 1) + 20, (g >> 1) + 20, (b >> 1) + 20)
            colour = wx.Colour(color[0], color[1], color[2])
        self._secondcolour = colour
        if self._usegradients:
            self.RefreshSelected()
        return

    def GetFirstGradientColour(self):
        return self._firstcolour

    def GetSecondGradientColour(self):
        return self._secondcolour

    def EnableSelectionGradient(self, enable=True):
        self._usegradients = enable
        self._vistaselection = False
        self.RefreshSelected()

    def SetGradientStyle(self, vertical=0):
        self._gradientstyle = vertical
        if self._usegradients:
            self.RefreshSelected()

    def GetGradientStyle(self):
        return self._gradientstyle

    def EnableSelectionVista(self, enable=True):
        self._usegradients = False
        self._vistaselection = enable
        self.RefreshSelected()

    def SetBorderPen(self, pen):
        self._borderPen = pen
        self.RefreshSelected()

    def GetBorderPen(self):
        return self._borderPen

    def SetConnectionPen(self, pen):
        self._dottedPen = pen
        self._dirty = True

    def GetConnectionPen(self):
        return self._dottedPen

    def SetBackgroundImage(self, image):
        self._backgroundImage = image
        self.Refresh()

    def GetBackgroundImage(self):
        return self._backgroundImage

    def GetItemWindow(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Item')
        return item.GetWindow()

    def GetItemWindowEnabled(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Item')
        return item.GetWindowEnabled()

    def SetItemWindowEnabled(self, item, enable=True):
        if not item:
            raise Exception('\nERROR: Invalid Item')
        item.SetWindowEnabled(enable)

    def GetItemType(self, item):
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

    def ItemHasChildren(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.HasPlus()

    def IsExpanded(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.IsExpanded()

    def IsSelected(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.IsSelected()

    def IsBold(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.IsBold()

    def IsItalic(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.IsItalic()

    def GetItemParent(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        return item.GetParent()

    def GetFirstChild(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        cookie = 0
        return self.GetNextChild(item, cookie)

    def GetNextChild(self, item, cookie):
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

    def GetLastChild(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        children = item.GetChildren()
        return (len(children) == 0 and [None] or [children[-1]])[0]

    def GetNextSibling(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        i = item
        parent = i.GetParent()
        if parent == None:
            return
        siblings = parent.GetChildren()
        index = siblings.index(i)
        n = index + 1
        return (n == len(siblings) and [None] or [siblings[n]])[0]

    def GetPrevSibling(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        i = item
        parent = i.GetParent()
        if parent == None:
            return
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
        return

    def GetFirstVisibleItem(self):
        id = self.GetRootItem()
        if not id:
            return id
        while id:
            if self.IsVisible(id):
                return id
            id = self.GetNext(id)

        return None

    def GetNextVisible(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        id = item
        while id:
            id = self.GetNext(id)
            if id and self.IsVisible(id):
                return id

        return None

    def GetPrevVisible(self, item):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        raise Exception('\nERROR: Not Implemented')
        return None

    def ResetTextControl(self):
        self._textCtrl.Destroy()
        self._textCtrl = None
        return

    def FindItem(self, idParent, prefixOrig):
        prefix = prefixOrig.lower()
        id = idParent
        if len(prefix) == 1:
            id = self.GetNext(id)
        while id and not self.GetItemText(id).lower().startswith(prefix):
            id = self.GetNext(id)

        if not id:
            id = self.GetRootItem()
            if self.HasFlag(TR_HIDE_ROOT):
                id = self.GetNext(id)
            while id != idParent and not self.GetItemText(id).lower().startswith(prefix):
                id = self.GetNext(id)

        return id

    def DoInsertItem(self, parentId, previous, text, ct_type=0, wnd=None, image=-1, selImage=-1, data=None):
        if wnd is not None and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception('\nERROR: In Order To Append/Insert Controls You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if text.find('\n') >= 0 and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception('\nERROR: In Order To Append/Insert A MultiLine Text You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if ct_type < 0 or ct_type > 2:
            raise Exception('\nERROR: Item Type Should Be 0 (Normal), 1 (CheckBox) or 2 (RadioButton). ')
        parent = parentId
        if not parent:
            return self.AddRoot(text, ct_type, wnd, image, selImage, data)
        self._dirty = True
        item = GenericTreeItem(parent, text, ct_type, wnd, image, selImage, data)
        if wnd is not None:
            self._hasWindows = True
            self._itemWithWindow.append(item)
        parent.Insert(item, previous)
        return item

    def AddRoot(self, text, ct_type=0, wnd=None, image=-1, selImage=-1, data=None):
        if self._anchor:
            raise Exception('\nERROR: Tree Can Have Only One Root')
        if wnd is not None and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception('\nERROR: In Order To Append/Insert Controls You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if text.find('\n') >= 0 and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception('\nERROR: In Order To Append/Insert A MultiLine Text You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if ct_type < 0 or ct_type > 2:
            raise Exception('\nERROR: Item Type Should Be 0 (Normal), 1 (CheckBox) or 2 (RadioButton). ')
        self._dirty = True
        self._anchor = GenericTreeItem(None, text, ct_type, wnd, image, selImage, data)
        if wnd is not None:
            self._hasWindows = True
            self._itemWithWindow.append(self._anchor)
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
            raise Exception('\nERROR: In Order To Append/Insert Controls You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if text.find('\n') >= 0 and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception('\nERROR: In Order To Append/Insert A MultiLine Text You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        return self.DoInsertItem(parent, 0, text, ct_type, wnd, image, selImage, data)

    def InsertItemByItem(self, parentId, idPrevious, text, ct_type=0, wnd=None, image=-1, selImage=-1, data=None):
        if wnd is not None and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception('\nERROR: In Order To Append/Insert Controls You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if text.find('\n') >= 0 and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception('\nERROR: In Order To Append/Insert A MultiLine Text You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
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
            raise Exception('\nERROR: In Order To Append/Insert Controls You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if text.find('\n') >= 0 and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception('\nERROR: In Order To Append/Insert A MultiLine Text You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        parent = parentId
        if not parent:
            return self.AddRoot(text, ct_type, wnd, image, selImage, data)
        return self.DoInsertItem(parentId, before, text, ct_type, wnd, image, selImage, data)

    def InsertItem(self, parentId, input, text, ct_type=0, wnd=None, image=-1, selImage=-1, data=None):
        if wnd is not None and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception('\nERROR: In Order To Append/Insert Controls You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if text.find('\n') >= 0 and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception('\nERROR: In Order To Append/Insert A MultiLine Text You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if type(input) == type(1):
            return self.InsertItemByIndex(parentId, input, text, ct_type, wnd, image, selImage, data)
        else:
            return self.InsertItemByItem(parentId, input, text, ct_type, wnd, image, selImage, data)
        return

    def AppendItem(self, parentId, text, ct_type=0, wnd=None, image=-1, selImage=-1, data=None):
        if wnd is not None and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception('\nERROR: In Order To Append/Insert Controls You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        if text.find('\n') >= 0 and not self._windowStyle & TR_HAS_VARIABLE_ROW_HEIGHT:
            raise Exception('\nERROR: In Order To Append/Insert A MultiLine Text You Have To Use The Style TR_HAS_VARIABLE_ROW_HEIGHT')
        parent = parentId
        if not parent:
            return self.AddRoot(text, ct_type, wnd, image, selImage, data)
        return self.DoInsertItem(parent, len(parent.GetChildren()), text, ct_type, wnd, image, selImage, data)

    def SendDeleteEvent(self, item):
        event = TreeEvent(wxEVT_TREE_DELETE_ITEM, self.GetId())
        event._item = item
        event.SetEventObject(self)
        self.ProcessEvent(event)

    def IsDescendantOf(self, parent, item):
        while item:
            if item == parent:
                return True
            item = item.GetParent()

        return False

    def ChildrenClosing(self, item):
        if self._textCtrl != None and item != self._textCtrl.item() and self.IsDescendantOf(item, self._textCtrl.item()):
            self._textCtrl.StopEditing()
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
        if self._textCtrl != None and self.IsDescendantOf(item, self._textCtrl.item()):
            self._textCtrl.StopEditing()
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
        if item in self._itemWithWindow:
            wnd = item.GetWindow()
            wnd.Hide()
            wnd.Destroy()
            item._wnd = None
            self._itemWithWindow.remove(item)
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
        for child in self._itemWithWindow:
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
        if parent == None:
            return self.TagAllChildrenUntilLast(crt_item, last_item, select)
        children = parent.GetChildren()
        index = children.index(crt_item)
        count = len(children)
        for n in xrange(index + 1, count):
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
        event._itemOld = self._current
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

    def FillArray(self, item, array=[]):
        if not array:
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
            self.SetScrollbars(_PIXELS_PER_UNIT, _PIXELS_PER_UNIT, x / _PIXELS_PER_UNIT, y / _PIXELS_PER_UNIT, x_pos, item_y / _PIXELS_PER_UNIT)
        elif item_y + self.GetLineHeight(item) > start_y + client_h:
            x, y = self._anchor.GetSize(x, y, self)
            y += _PIXELS_PER_UNIT + 2
            x += _PIXELS_PER_UNIT + 2
            item_y += _PIXELS_PER_UNIT + 2
            x_pos = self.GetScrollPos(wx.HORIZONTAL)
            self.SetScrollbars(_PIXELS_PER_UNIT, _PIXELS_PER_UNIT, x / _PIXELS_PER_UNIT, y / _PIXELS_PER_UNIT, x_pos, (item_y + self.GetLineHeight(item) - client_h) / _PIXELS_PER_UNIT)

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
        return self._imageListNormal

    def GetButtonsImageList(self):
        return self._imageListButtons

    def GetStateImageList(self):
        return self._imageListState

    def GetImageListCheck(self):
        return self._imageListCheck

    def CalculateLineHeight(self):
        dc = wx.ClientDC(self)
        self._lineHeight = dc.GetCharHeight()
        if self._imageListNormal:
            n = self._imageListNormal.GetImageCount()
            for i in xrange(n):
                width, height = self._imageListNormal.GetSize(i)
                if height > self._lineHeight:
                    self._lineHeight = height

        if self._imageListButtons:
            n = self._imageListButtons.GetImageCount()
            for i in xrange(n):
                width, height = self._imageListButtons.GetSize(i)
                if height > self._lineHeight:
                    self._lineHeight = height

        if self._imageListCheck:
            n = self._imageListCheck.GetImageCount()
            for i in xrange(n):
                width, height = self._imageListCheck.GetSize(i)
                if height > self._lineHeight:
                    self._lineHeight = height

        if self._lineHeight < 30:
            self._lineHeight += 2
        else:
            self._lineHeight += self._lineHeight / 10

    def SetImageList(self, imageList):
        if self._ownsImageListNormal:
            del self._imageListNormal
        self._imageListNormal = imageList
        self._ownsImageListNormal = False
        self._dirty = True
        if imageList:
            self.CalculateLineHeight()
            sz = imageList.GetSize(0)
            self._grayedImageList = wx.ImageList(sz[0], sz[1], True, 0)
            for ii in xrange(imageList.GetImageCount()):
                bmp = imageList.GetBitmap(ii)
                image = wx.ImageFromBitmap(bmp)
                image = GrayOut(image)
                newbmp = wx.BitmapFromImage(image)
                self._grayedImageList.Add(newbmp)

    def SetStateImageList(self, imageList):
        if self._ownsImageListState:
            del self._imageListState
        self._imageListState = imageList
        self._ownsImageListState = False

    def SetButtonsImageList(self, imageList):
        if self._ownsImageListButtons:
            del self._imageListButtons
        self._imageListButtons = imageList
        self._ownsImageListButtons = False
        self._dirty = True
        self.CalculateLineHeight()

    def SetImageListCheck(self, sizex, sizey, imglist=None):
        if imglist is None:
            self._imageListCheck = wx.ImageList(sizex, sizey)
            self._imageListCheck.Add(GetCheckedBitmap())
            self._imageListCheck.Add(GetNotCheckedBitmap())
            self._imageListCheck.Add(GetFlaggedBitmap())
            self._imageListCheck.Add(GetNotFlaggedBitmap())
        else:
            sizex, sizey = imglist.GetSize(0)
            self._imageListCheck = imglist
        self._grayedCheckList = wx.ImageList(sizex, sizey, True, 0)
        for ii in xrange(self._imageListCheck.GetImageCount()):
            bmp = self._imageListCheck.GetBitmap(ii)
            image = wx.ImageFromBitmap(bmp)
            image = GrayOut(image)
            newbmp = wx.BitmapFromImage(image)
            self._grayedCheckList.Add(newbmp)

        self._dirty = True
        if imglist:
            self.CalculateLineHeight()
        return

    def AssignImageList(self, imageList):
        self.SetImageList(imageList)
        self._ownsImageListNormal = True

    def AssignStateImageList(self, imageList):
        self.SetStateImageList(imageList)
        self._ownsImageListState = True

    def AssignButtonsImageList(self, imageList):
        self.SetButtonsImageList(imageList)
        self._ownsImageListButtons = True

    def AdjustMyScrollbars(self):
        if self._anchor:
            x, y = self._anchor.GetSize(0, 0, self)
            y += _PIXELS_PER_UNIT + 2
            x += _PIXELS_PER_UNIT + 2
            x_pos = self.GetScrollPos(wx.HORIZONTAL)
            y_pos = self.GetScrollPos(wx.VERTICAL)
            self.SetScrollbars(_PIXELS_PER_UNIT, _PIXELS_PER_UNIT, x / _PIXELS_PER_UNIT, y / _PIXELS_PER_UNIT, x_pos, y_pos)
        else:
            self.SetScrollbars(0, 0, 0, 0)

    def GetLineHeight(self, item):
        if self.GetTreeStyle() & TR_HAS_VARIABLE_ROW_HEIGHT:
            return item.GetHeight()
        else:
            return self._lineHeight

    def DrawVerticalGradient(self, dc, rect, hasfocus):
        oldpen = dc.GetPen()
        oldbrush = dc.GetBrush()
        dc.SetPen(wx.TRANSPARENT_PEN)
        if hasfocus:
            col2 = self._secondcolour
            col1 = self._firstcolour
        else:
            col2 = self._hilightUnfocusedBrush.GetColour()
            col1 = self._hilightUnfocusedBrush2.GetColour()
        r1, g1, b1 = int(col1.Red()), int(col1.Green()), int(col1.Blue())
        r2, g2, b2 = int(col2.Red()), int(col2.Green()), int(col2.Blue())
        flrect = float(rect.height)
        rstep = float(r2 - r1) / flrect
        gstep = float(g2 - g1) / flrect
        bstep = float(b2 - b1) / flrect
        rf, gf, bf = (0, 0, 0)
        for y in xrange(rect.y, rect.y + rect.height):
            currCol = (r1 + rf, g1 + gf, b1 + bf)
            dc.SetBrush(wx.Brush(currCol, wx.SOLID))
            dc.DrawRectangle(rect.x, y, rect.width, 1)
            rf = rf + rstep
            gf = gf + gstep
            bf = bf + bstep

        dc.SetPen(oldpen)
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.DrawRectangleRect(rect)
        dc.SetBrush(oldbrush)

    def DrawHorizontalGradient(self, dc, rect, hasfocus):
        oldpen = dc.GetPen()
        oldbrush = dc.GetBrush()
        dc.SetPen(wx.TRANSPARENT_PEN)
        if hasfocus:
            col2 = self._secondcolour
            col1 = self._firstcolour
        else:
            col2 = self._hilightUnfocusedBrush.GetColour()
            col1 = self._hilightUnfocusedBrush2.GetColour()
        r1, g1, b1 = int(col1.Red()), int(col1.Green()), int(col1.Blue())
        r2, g2, b2 = int(col2.Red()), int(col2.Green()), int(col2.Blue())
        flrect = float(rect.width)
        rstep = float(r2 - r1) / flrect
        gstep = float(g2 - g1) / flrect
        bstep = float(b2 - b1) / flrect
        rf, gf, bf = (0, 0, 0)
        for x in xrange(rect.x, rect.x + rect.width):
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
        for y in xrange(filRect.y, filRect.y + filRect.height):
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
                dc.SetFont(self._boldFont)
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
                if self._imageListNormal:
                    image_w, image_h = self._imageListNormal.GetSize(image)
                    image_w += 4
                else:
                    image = _NO_IMAGE
            if item.GetType() != 0:
                wcheck, hcheck = self._imageListCheck.GetSize(item.GetType())
                wcheck += 4
            else:
                wcheck, hcheck = (0, 0)
            total_h = self.GetLineHeight(item)
            drawItemBackground = False
            if item.IsSelected():
                if wx.Platform == '__WXMAC__':
                    self._hasFocus or dc.SetBrush(wx.TRANSPARENT_BRUSH)
                    dc.SetPen(wx.Pen(wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHT), 1, wx.SOLID))
                else:
                    dc.SetBrush(self._hilightBrush)
            else:
                dc.SetBrush((self._hasFocus and [self._hilightBrush] or [self._hilightUnfocusedBrush])[0])
                drawItemBackground = True
        else:
            if attr and attr.HasBackgroundColour():
                drawItemBackground = True
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
                if self._usegradients:
                    if self._gradientstyle == 0:
                        self.DrawHorizontalGradient(dc, itemrect, self._hasFocus)
                    else:
                        self.DrawVerticalGradient(dc, itemrect, self._hasFocus)
                elif self._vistaselection:
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
                wndx = 0
                if wnd:
                    wndx, wndy = item.GetWindowSize()
                itemrect = wx.Rect(item.GetX() + wcheck + image_w - 2, item.GetY() + offset, item.GetWidth() - image_w - wcheck + 2 - wndx, total_h - offset)
                if self._usegradients:
                    if self._gradientstyle == 0:
                        self.DrawHorizontalGradient(dc, itemrect, self._hasFocus)
                    else:
                        self.DrawVerticalGradient(dc, itemrect, self._hasFocus)
                elif self._vistaselection:
                    self.DrawVistaRectangle(dc, itemrect, self._hasFocus)
                elif wx.Platform in ['__WXGTK2__', '__WXMAC__']:
                    flags = wx.CONTROL_SELECTED
                    if self._hasFocus:
                        flags = flags | wx.CONTROL_FOCUSED
                    wx.RendererNative.Get().DrawItemSelectionRect(self, dc, itemrect, flags)
                else:
                    dc.DrawRectangleRect(itemrect)
            elif drawItemBackground:
                minusicon = wcheck + image_w - 2
                itemrect = wx.Rect(item.GetX() + minusicon, item.GetY() + offset, item.GetWidth() - minusicon, total_h - offset)
                if self._usegradients and self._hasFocus:
                    if self._gradientstyle == 0:
                        self.DrawHorizontalGradient(dc, itemrect, self._hasFocus)
                    else:
                        self.DrawVerticalGradient(dc, itemrect, self._hasFocus)
                else:
                    dc.DrawRectangleRect(itemrect)
            if image != _NO_IMAGE:
                dc.SetClippingRegion(item.GetX(), item.GetY(), wcheck + image_w - 2, total_h)
                if item.IsEnabled():
                    imglist = self._imageListNormal
                else:
                    imglist = self._grayedImageList
                imglist.Draw(image, dc, item.GetX() + wcheck, item.GetY() + (total_h > image_h and [(total_h - image_h) / 2] or [0])[0], wx.IMAGELIST_DRAW_TRANSPARENT)
                dc.DestroyClippingRegion()
            if wcheck:
                if item.IsEnabled():
                    imglist = self._imageListCheck
                else:
                    imglist = self._grayedCheckList
                imglist.Draw(checkimage, dc, item.GetX(), item.GetY() + (total_h > hcheck and [(total_h - hcheck) / 2] or [0])[0], wx.IMAGELIST_DRAW_TRANSPARENT)
            dc.SetBackgroundMode(wx.TRANSPARENT)
            extraH = (total_h > text_h and [(total_h - text_h) / 2] or [0])[0]
            textrect = wx.Rect(wcheck + image_w + item.GetX(), item.GetY() + extraH, text_w, text_h)
            if not item.IsEnabled():
                foreground = dc.GetTextForeground()
                dc.SetTextForeground(self._disabledColour)
                dc.DrawLabel(item.GetText(), textrect)
                dc.SetTextForeground(foreground)
            else:
                if wx.Platform == '__WXMAC__' and item.IsSelected() and self._hasFocus:
                    dc.SetTextForeground(wx.WHITE)
                dc.DrawLabel(item.GetText(), textrect)
            wnd = item.GetWindow()
            if wnd:
                wndx = wcheck + image_w + item.GetX() + text_w + 4
                wndx = self.GetVirtualSize()[0] - (wnd.GetSize()[0] + 4)
                xa, ya = self.CalcScrolledPosition((0, item.GetY()))
                if not wnd.IsShown():
                    wnd.Show()
                if wnd.GetPosition() != (wndx, ya):
                    wnd.SetPosition((wndx, ya))
        dc.SetFont(self._normalFont)

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
            pen = (wx.Platform == '__WXMAC__' and (item.IsSelected() and self._hasFocus and [self._borderPen] or [wx.TRANSPARENT_PEN]))[0]
        else:
            pen = self._borderPen
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
                if self._vistaselection:
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
                    dc.SetPen(self._dottedPen)
                    x_start = x
                    if x > self._indent:
                        x_start -= self._indent
                    elif self.HasFlag(TR_LINES_AT_ROOT):
                        x_start = 3
                    dc.DrawLine(x_start, y_mid, x + self._spacing, y_mid)
                    dc.SetPen(oldpen)
                if item.HasPlus() and self.HasButtons():
                    if self._imageListButtons:
                        image_h = 0
                        image_w = 0
                        image = (item.IsExpanded() and [TreeItemIcon_Expanded] or [TreeItemIcon_Normal])[0]
                        if item.IsSelected():
                            image += TreeItemIcon_Selected - TreeItemIcon_Normal
                        image_w, image_h = self._imageListButtons.GetSize(image)
                        xx = x - image_w / 2
                        yy = y_mid - image_h / 2
                        dc.SetClippingRegion(xx, yy, image_w, image_h)
                        self._imageListButtons.Draw(image, dc, xx, yy, wx.IMAGELIST_DRAW_TRANSPARENT)
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
                        if item == self._underMouse:
                            flag |= _CONTROL_CURRENT
                        self._drawingfunction(self, dc, wx.Rect(x - wImage / 2, y_mid - hImage / 2, wImage, hImage), flag)
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
                            dc.SetPen(self._dottedPen)
                            dc.DrawLine(x, y_mid, x, oldY)
        return y

    def OnPaint(self, event):
        dc = wx.PaintDC(self)
        self.PrepareDC(dc)
        if not self._anchor:
            return
        dc.SetFont(self._normalFont)
        dc.SetPen(self._dottedPen)
        y = 2
        self.PaintLevel(self._anchor, dc, 0, y)

    def OnEraseBackground(self, event):
        if not self._backgroundImage:
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
        w = self._backgroundImage.GetWidth()
        h = self._backgroundImage.GetHeight()
        x = 0
        while x < sz.width:
            y = 0
            while y < sz.height:
                dc.DrawBitmap(self._backgroundImage, x, y, True)
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
        te._evtKey = event
        te.SetEventObject(self)
        if self.GetEventHandler().ProcessEvent(te):
            return
        if self._current is None or self._key_current is None:
            event.Skip()
            return
        is_multiple, extended_select, unselect_others = EventFlagsToSelType(self.GetTreeStyle(), event.ShiftDown(), event.CmdDown())
        keyCode = event.GetKeyCode()
        if keyCode in [ord('+'), wx.WXK_ADD]:
            if self._current.HasPlus() and not self.IsExpanded(self._current) and self.IsEnabled(self._current):
                self.Expand(self._current)
        if keyCode in [ord('*'), wx.WXK_MULTIPLY]:
            if not self.IsExpanded(self._current) and self.IsEnabled(self._current):
                self.ExpandAll(self._current)
        if keyCode in [ord('-'), wx.WXK_SUBTRACT]:
            if self.IsExpanded(self._current):
                self.Collapse(self._current)
        elif keyCode == wx.WXK_MENU:
            itemRect = self.GetBoundingRect(self._current, True)
            event = TreeEvent(wxEVT_TREE_ITEM_MENU, self.GetId())
            event._item = self._current
            event._pointDrag = wx.Point(ItemRect.GetX(), ItemRect.GetY() + ItemRect.GetHeight() / 2)
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
        elif not event.HasModifiers() and (keyCode >= ord('0') and keyCode <= ord('9') or keyCode >= ord('a') and keyCode <= ord('z') or keyCode >= ord('A') and keyCode <= ord('Z')):
            ch = chr(keyCode)
            id = self.FindItem(self._current, self._findPrefix + ch)
            if not id:
                return
            if self.IsEnabled(id):
                self.SelectItem(id)
            self._findPrefix += ch
            if not self._findTimer:
                self._findTimer = TreeFindTimer(self)
            self._findTimer.Start(_DELAY, wx.TIMER_ONE_SHOT)
        else:
            event.Skip()
        return

    def GetNextActiveItem--- This code section failed: ---

4956       0  LOAD_FAST             2  'down'
           3  JUMP_IF_FALSE        13  'to 19'
           6  POP_TOP          

4957       7  LOAD_FAST             0  'self'
          10  LOAD_ATTR             2  'GetNextSibling'
          13  STORE_FAST            3  'sibling'
          16  JUMP_FORWARD         10  'to 29'
        19_0  COME_FROM                '3'
          19  POP_TOP          

4959      20  LOAD_FAST             0  'self'
          23  LOAD_ATTR             4  'GetPrevSibling'
          26  STORE_FAST            3  'sibling'
        29_0  COME_FROM                '16'

4961      29  LOAD_FAST             0  'self'
          32  LOAD_ATTR             5  'GetItemType'
          35  LOAD_FAST             1  'item'
          38  CALL_FUNCTION_1       1 
          41  LOAD_CONST            1  2
          44  COMPARE_OP            2  '=='
          47  JUMP_IF_FALSE        89  'to 139'
          50  POP_TOP          
          51  LOAD_FAST             0  'self'
          54  LOAD_ATTR             7  'IsItemChecked'
          57  LOAD_FAST             1  'item'
          60  CALL_FUNCTION_1       1 
          63  UNARY_NOT        
          64  JUMP_IF_FALSE        72  'to 139'
          67  POP_TOP          

4964      68  LOAD_CONST            2  ''
          71  STORE_FAST            6  'found'

4966      74  SETUP_LOOP          140  'to 217'

4967      77  LOAD_FAST             3  'sibling'
          80  LOAD_FAST             1  'item'
          83  CALL_FUNCTION_1       1 
          86  STORE_FAST            5  'child'

4968      89  LOAD_FAST             5  'child'
          92  JUMP_IF_FALSE        16  'to 111'
          95  POP_TOP          
          96  LOAD_FAST             0  'self'
          99  LOAD_ATTR            10  'IsEnabled'
         102  LOAD_FAST             5  'child'
         105  CALL_FUNCTION_1       1 
       108_0  COME_FROM                '92'
         108  JUMP_IF_TRUE          8  'to 119'
         111  POP_TOP          
         112  LOAD_FAST             5  'child'
         115  UNARY_NOT        
       116_0  COME_FROM                '108'
         116  JUMP_IF_FALSE         5  'to 124'
       119_0  THEN                     125
         119  POP_TOP          

4969     120  BREAK_LOOP       
         121  JUMP_FORWARD          1  'to 125'
       124_0  COME_FROM                '116'
         124  POP_TOP          
       125_0  COME_FROM                '121'

4970     125  LOAD_FAST             5  'child'
         128  STORE_FAST            1  'item'
         131  JUMP_BACK            77  'to 77'
         134  POP_TOP          
         135  POP_BLOCK        
         136  JUMP_FORWARD         78  'to 217'
       139_0  COME_FROM                '64'
       139_1  COME_FROM                '47'
         139  POP_TOP          

4975     140  LOAD_FAST             0  'self'
         143  LOAD_ATTR            11  'GetFirstChild'
         146  LOAD_FAST             1  'item'
         149  CALL_FUNCTION_1       1 
         152  UNPACK_SEQUENCE_2     2 
         155  STORE_FAST            5  'child'
         158  STORE_FAST            4  'cookie'

4976     161  SETUP_LOOP           53  'to 217'
         164  LOAD_FAST             5  'child'
         167  JUMP_IF_FALSE        45  'to 215'
         170  POP_TOP          
         171  LOAD_FAST             0  'self'
         174  LOAD_ATTR            10  'IsEnabled'
         177  LOAD_FAST             5  'child'
         180  CALL_FUNCTION_1       1 
         183  UNARY_NOT        
       184_0  COME_FROM                '167'
         184  JUMP_IF_FALSE        28  'to 215'
         187  POP_TOP          

4977     188  LOAD_FAST             0  'self'
         191  LOAD_ATTR            13  'GetNextChild'
         194  LOAD_FAST             1  'item'
         197  LOAD_FAST             4  'cookie'
         200  CALL_FUNCTION_2       2 
         203  UNPACK_SEQUENCE_2     2 
         206  STORE_FAST            5  'child'
         209  STORE_FAST            4  'cookie'
         212  JUMP_BACK           164  'to 164'
         215  POP_TOP          
         216  POP_BLOCK        
       217_0  COME_FROM                '161'
       217_1  COME_FROM                '74'

4979     217  LOAD_FAST             5  'child'
         220  JUMP_IF_FALSE        24  'to 247'
         223  POP_TOP          
         224  LOAD_FAST             0  'self'
         227  LOAD_ATTR            10  'IsEnabled'
         230  LOAD_FAST             5  'child'
         233  CALL_FUNCTION_1       1 
         236  JUMP_IF_FALSE         8  'to 247'
       239_0  THEN                     248
         239  POP_TOP          

4980     240  LOAD_FAST             5  'child'
         243  RETURN_VALUE     
         244  JUMP_FORWARD          1  'to 248'
       247_0  COME_FROM                '236'
       247_1  COME_FROM                '220'
         247  POP_TOP          
       248_0  COME_FROM                '244'

4982     248  LOAD_CONST            0  ''
         251  RETURN_VALUE     

Parse error at or near `JUMP_FORWARD' instruction at offset 136

    def HitTest(self, point, flags=0):
        w, h = self.GetSize()
        flags = 0
        if point.x < 0:
            flags |= TREE_HITTEST_TOLEFT
        if point.x > w:
            flags |= TREE_HITTEST_TORIGHT
        if point.y < 0:
            flags |= TREE_HITTEST_ABOVE
        if point.y > h:
            flags |= TREE_HITTEST_BELOW
        if flags:
            return (None, flags)
        if self._anchor == None:
            flags = TREE_HITTEST_NOWHERE
            return (
             None, flags)
        hit, flags = self._anchor.HitTest(self.CalcUnscrolledPosition(point), self, flags, 0)
        if hit == None:
            flags = TREE_HITTEST_NOWHERE
            return (
             None, flags)
        if not self.IsEnabled(hit):
            return (None, flags)
        return (
         hit, flags)

    def GetBoundingRect(self, item, textOnly=False):
        if not item:
            raise Exception('\nERROR: Invalid Tree Item. ')
        i = item
        startX, startY = self.GetViewStart()
        rect = wx.Rect()
        rect.x = i.GetX() - startX * _PIXELS_PER_UNIT
        rect.y = i.GetY() - startY * _PIXELS_PER_UNIT
        rect.width = i.GetWidth()
        rect.height = self.GetLineHeight(i)
        return rect

    def Edit(self, item):
        te = TreeEvent(wxEVT_TREE_BEGIN_LABEL_EDIT, self.GetId())
        te._item = item
        te.SetEventObject(self)
        if self.GetEventHandler().ProcessEvent(te) and not te.IsAllowed():
            return
        if self._dirty:
            if wx.Platform in ['__WXMSW__', '__WXMAC__']:
                self.Update()
            else:
                wx.YieldIfNeeded()
        if self._textCtrl != None and item != self._textCtrl.item():
            self._textCtrl.StopEditing()
        self._textCtrl = TreeTextCtrl(self, item=item)
        self._textCtrl.SetFocus()
        return

    def GetEditControl(self):
        return self._textCtrl

    def OnRenameAccept(self, item, value):
        le = TreeEvent(wxEVT_TREE_END_LABEL_EDIT, self.GetId())
        le._item = item
        le.SetEventObject(self)
        le._label = value
        le._editCancelled = False
        return not self.GetEventHandler().ProcessEvent(le) or le.IsAllowed()

    def OnRenameCancelled(self, item):
        le = TreeEvent(wxEVT_TREE_END_LABEL_EDIT, self.GetId())
        le._item = item
        le.SetEventObject(self)
        le._label = ''
        le._editCancelled = True
        self.GetEventHandler().ProcessEvent(le)

    def OnRenameTimer(self):
        self.Edit(self._current)

    def OnMouse(self, event):
        if not self._anchor:
            return
        pt = self.CalcUnscrolledPosition(event.GetPosition())
        flags = 0
        thisItem, flags = self._anchor.HitTest(pt, self, flags, 0)
        underMouse = thisItem
        underMouseChanged = underMouse != self._underMouse
        if underMouse:
            if flags & TREE_HITTEST_ONITEM and not event.LeftIsDown() and not self._isDragging and (not self._renameTimer or not self._renameTimer.IsRunning()):
                underMouse = underMouse
            else:
                underMouse = None
            if underMouse != self._underMouse:
                if self._underMouse:
                    self._underMouse = None
                self._underMouse = underMouse
            hoverItem = thisItem
            if underMouseChanged and not self._isDragging and (not self._renameTimer or not self._renameTimer.IsRunning()):
                if hoverItem is not None:
                    hevent = TreeEvent(wxEVT_TREE_ITEM_GETTOOLTIP, self.GetId())
                    hevent._item = hoverItem
                    hevent.SetEventObject(self)
                    if self.GetEventHandler().ProcessEvent(hevent) and hevent.IsAllowed():
                        self.SetToolTip(hevent._label)
                    if hoverItem.IsHyperText() and flags & TREE_HITTEST_ONITEMLABEL and hoverItem.IsEnabled():
                        self.SetCursor(wx.StockCursor(wx.CURSOR_HAND))
                        self._isonhyperlink = True
                    elif self._isonhyperlink:
                        self.SetCursor(wx.StockCursor(wx.CURSOR_ARROW))
                        self._isonhyperlink = False
            if not (event.LeftDown() or event.LeftUp() or event.RightDown() or event.LeftDClick() or event.Dragging() or (event.Moving() or event.RightUp()) and self._isDragging):
                event.Skip()
                return
            flags = 0
            item, flags = self._anchor.HitTest(pt, self, flags, 0)
            if event.Dragging() and not self._isDragging and (flags & TREE_HITTEST_ONITEMICON or flags & TREE_HITTEST_ONITEMLABEL):
                if self._dragCount == 0:
                    self._dragStart = pt
                self._countDrag = 0
                self._dragCount = self._dragCount + 1
                if self._dragCount != 3:
                    return
                command = (event.RightIsDown() and [wxEVT_TREE_BEGIN_RDRAG] or [wxEVT_TREE_BEGIN_DRAG])[0]
                nevent = TreeEvent(command, self.GetId())
                nevent._item = self._current
                nevent.SetEventObject(self)
                newpt = self.CalcScrolledPosition(pt)
                nevent.SetPoint(newpt)
                nevent.Veto()
                if self.GetEventHandler().ProcessEvent(nevent) and nevent.IsAllowed():
                    self._isDragging = True
                    self._oldCursor = self._cursor
                    self._oldSelection = self.GetTreeStyle() & TR_MULTIPLE or self.GetSelection()
                    if self._oldSelection:
                        self._oldSelection.SetHilight(False)
                        self.RefreshLine(self._oldSelection)
                else:
                    selections = self.GetSelections()
                    if len(selections) == 1:
                        self._oldSelection = selections[0]
                        self._oldSelection.SetHilight(False)
                        self.RefreshLine(self._oldSelection)
                if self._dragImage:
                    del self._dragImage
                self._dragImage = DragImage(self, self._current)
                self._dragImage.BeginDrag(wx.Point(0, 0), self)
                self._dragImage.Show()
                self._dragImage.Move(self.CalcScrolledPosition(pt))
        elif event.Dragging() and self._isDragging:
            self._dragImage.Move(self.CalcScrolledPosition(pt))
            if self._countDrag == 0 and item:
                self._oldItem = item
            if item != self._dropTarget:
                if self._dropTarget:
                    self._dropTarget.SetHilight(False)
                    self.RefreshLine(self._dropTarget)
                if item:
                    item.SetHilight(True)
                    self.RefreshLine(item)
                    self._countDrag = self._countDrag + 1
                self._dropTarget = item
                self.Update()
            if self._countDrag >= 3:
                self.RefreshLine(self._oldItem)
                self._countDrag = 0
        elif (event.LeftUp() or event.RightUp()) and self._isDragging:
            if self._dragImage:
                self._dragImage.EndDrag()
            if self._dropTarget:
                self._dropTarget.SetHilight(False)
            if self._oldSelection:
                self._oldSelection.SetHilight(True)
                self.RefreshLine(self._oldSelection)
                self._oldSelection = None
            event = TreeEvent(wxEVT_TREE_END_DRAG, self.GetId())
            event._item = item
            event._pointDrag = self.CalcScrolledPosition(pt)
            event.SetEventObject(self)
            self.GetEventHandler().ProcessEvent(event)
            self._isDragging = False
            self._dropTarget = None
            self.SetCursor(self._oldCursor)
            if wx.Platform in ['__WXMSW__', '__WXMAC__']:
                self.Refresh()
            else:
                wx.YieldIfNeeded()
        else:
            if event.LeftDown():
                self._hasFocus = True
                self.SetFocusIgnoringChildren()
                event.Skip()
            self._dragCount = 0
            if item == None:
                if self._textCtrl != None and item != self._textCtrl.item():
                    self._textCtrl.StopEditing()
                return
            if event.RightDown():
                if self._textCtrl != None and item != self._textCtrl.item():
                    self._textCtrl.StopEditing()
                self._hasFocus = True
                self.SetFocusIgnoringChildren()
                if not self.IsSelected(item):
                    self.DoSelectItem(item, True, False)
                nevent = TreeEvent(wxEVT_TREE_ITEM_RIGHT_CLICK, self.GetId())
                nevent._item = item
                nevent._pointDrag = self.CalcScrolledPosition(pt)
                nevent.SetEventObject(self)
                event.Skip(not self.GetEventHandler().ProcessEvent(nevent))
                nevent2 = TreeEvent(wxEVT_TREE_ITEM_MENU, self.GetId())
                nevent2._item = item
                nevent2._pointDrag = self.CalcScrolledPosition(pt)
                nevent2.SetEventObject(self)
                self.GetEventHandler().ProcessEvent(nevent2)
            elif event.LeftUp():
                if self.HasFlag(TR_MULTIPLE):
                    selections = self.GetSelections()
                    if len(selections) > 1 and not event.CmdDown() and not event.ShiftDown():
                        self.DoSelectItem(item, True, False)
                if self._lastOnSame:
                    if item == self._current and flags & TREE_HITTEST_ONITEMLABEL and self.HasFlag(TR_EDIT_LABELS):
                        if self._renameTimer:
                            if self._renameTimer.IsRunning():
                                self._renameTimer.Stop()
                        else:
                            self._renameTimer = TreeRenameTimer(self)
                        self._renameTimer.Start(_DELAY, True)
                    self._lastOnSame = False
            else:
                if not item or not item.IsEnabled():
                    if self._textCtrl != None and item != self._textCtrl.item():
                        self._textCtrl.StopEditing()
                    return
                if self._textCtrl != None and item != self._textCtrl.item():
                    self._textCtrl.StopEditing()
                self._hasFocus = True
                self.SetFocusIgnoringChildren()
                if event.LeftDown():
                    self._lastOnSame = item == self._current
                if flags & TREE_HITTEST_ONITEMBUTTON:
                    if event.LeftDown():
                        self.Toggle(item)
                    return
                if item.GetType() > 0 and flags & TREE_HITTEST_ONITEMCHECKICON:
                    if event.LeftDown():
                        self.CheckItem(item, not self.IsItemChecked(item))
                    return
                if not self.IsSelected(item) or event.CmdDown():
                    if flags & TREE_HITTEST_ONITEM:
                        if item.IsHyperText():
                            self.SetItemVisited(item, True)
                        is_multiple, extended_select, unselect_others = EventFlagsToSelType(self.GetTreeStyle(), event.ShiftDown(), event.CmdDown())
                        self.DoSelectItem(item, unselect_others, extended_select)
                if event.LeftDClick():
                    if self._renameTimer:
                        self._renameTimer.Stop()
                    self._lastOnSame = False
                    nevent = TreeEvent(wxEVT_TREE_ITEM_ACTIVATED, self.GetId())
                    nevent._item = item
                    nevent._pointDrag = self.CalcScrolledPosition(pt)
                    nevent.SetEventObject(self)
                    if not self.GetEventHandler().ProcessEvent(nevent):
                        self.Toggle(item)
        return

    def OnInternalIdle(self):
        if not self.HasFlag(TR_MULTIPLE) and not self.GetSelection():
            if self._select_me:
                self.SelectItem(self._select_me)
            elif self.GetRootItem():
                self.SelectItem(self.GetRootItem())
        if not self._dirty:
            return
        if self._freezeCount:
            return
        self._dirty = False
        self.CalculatePositions()
        self.Refresh()
        self.AdjustMyScrollbars()

    def CalculateSize(self, item, dc):
        attr = item.GetAttributes()
        if attr and attr.HasFont():
            dc.SetFont(attr.GetFont())
        else:
            if item.IsBold():
                dc.SetFont(self._boldFont)
            else:
                dc.SetFont(self._normalFont)
            text_w, text_h, dummy = dc.GetMultiLineTextExtent(item.GetText())
            text_h += 2
            dc.SetFont(self._normalFont)
            image_w, image_h = (0, 0)
            image = item.GetCurrentImage()
            if image != _NO_IMAGE:
                if self._imageListNormal:
                    image_w, image_h = self._imageListNormal.GetSize(image)
                    image_w += 4
            total_h = (image_h > text_h and [image_h] or [text_h])[0]
            checkimage = item.GetCurrentCheckedImage()
            if checkimage is not None:
                wcheck, hcheck = self._imageListCheck.GetSize(checkimage)
                wcheck += 4
            else:
                wcheck = 0
            if total_h < 30:
                total_h += 2
            else:
                total_h += total_h / 10
            if total_h > self._lineHeight:
                self._lineHeight = total_h
            if not item.GetWindow():
                item.SetWidth(image_w + text_w + wcheck + 2)
                item.SetHeight(total_h)
            item.SetWidth(item.GetWindowSize()[0] + image_w + text_w + wcheck + 2)
        return

    def CalculateLevel(self, item, dc, level, y):
        x = level * self._indent
        if not self.HasFlag(TR_HIDE_ROOT):
            x += self._indent
        elif level == 0:
            children = item.GetChildren()
            count = len(children)
            level = level + 1
            for n in xrange(count):
                y = self.CalculateLevel(children[n], dc, level, y)

            return y
        self.CalculateSize(item, dc)
        item.SetX(x + self._spacing)
        item.SetY(y)
        y += self.GetLineHeight(item)
        if not item.IsExpanded():
            return y
        children = item.GetChildren()
        count = len(children)
        level = level + 1
        for n in xrange(count):
            y = self.CalculateLevel(children[n], dc, level, y)

        return y

    def CalculatePositions(self):
        if not self._anchor:
            return
        dc = wx.ClientDC(self)
        self.PrepareDC(dc)
        dc.SetFont(self._normalFont)
        dc.SetPen(self._dottedPen)
        y = 2
        y = self.CalculateLevel(self._anchor, dc, 0, y)

    def RefreshSubtree(self, item):
        if self._dirty:
            return
        if self._freezeCount:
            return
        client = self.GetClientSize()
        rect = wx.Rect()
        x, rect.y = self.CalcScrolledPosition(0, item.GetY())
        rect.width = client.x
        rect.height = client.y
        self.Refresh(True, rect)
        self.AdjustMyScrollbars()

    def RefreshLine(self, item):
        if self._dirty:
            return
        if self._freezeCount:
            return
        rect = wx.Rect()
        x, rect.y = self.CalcScrolledPosition(0, item.GetY())
        rect.width = self.GetClientSize().x
        rect.height = self.GetLineHeight(item)
        self.Refresh(True, rect)

    def RefreshSelected(self):
        if self._freezeCount:
            return
        if self._anchor:
            self.RefreshSelectedUnder(self._anchor)

    def RefreshSelectedUnder(self, item):
        if self._freezeCount:
            return
        if item.IsSelected():
            self.RefreshLine(item)
        children = item.GetChildren()
        for child in children:
            self.RefreshSelectedUnder(child)

    def Freeze(self):
        self._freezeCount = self._freezeCount + 1

    def Thaw(self):
        if self._freezeCount == 0:
            raise Exception('\nERROR: Thawing Unfrozen Tree Control?')
        self._freezeCount = self._freezeCount - 1
        if not self._freezeCount:
            self.Refresh()

    def SetBackgroundColour(self, colour):
        if not wx.Window.SetBackgroundColour(self, colour):
            return False
        if self._freezeCount:
            return True
        self.Refresh()
        return True

    def SetForegroundColour(self, colour):
        if not wx.Window.SetForegroundColour(self, colour):
            return False
        if self._freezeCount:
            return True
        self.Refresh()
        return True

    def OnGetToolTip(self, event):
        event.Veto()

    def DoGetBestSize(self):
        return wx.Size(100, 80)

    def GetClassDefaultAttributes(self):
        attr = wx.VisualAttributes()
        attr.colFg = wx.SystemSettings_GetColour(wx.SYS_COLOUR_WINDOWTEXT)
        attr.colBg = wx.SystemSettings_GetColour(wx.SYS_COLOUR_LISTBOX)
        attr.font = wx.SystemSettings_GetFont(wx.SYS_DEFAULT_GUI_FONT)
        return attr

    GetClassDefaultAttributes = classmethod(GetClassDefaultAttributes)
