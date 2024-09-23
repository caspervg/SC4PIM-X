# uncompyle6 version 2.11.5
# Python bytecode 2.4 (62061)
# Decompiled from: Python 2.7.18 (default, Oct 15 2023, 16:43:11) 
# [GCC 11.4.0]
# Embedded file name: SC4IconMakerDlg.pyo
# Compiled at: 2009-11-04 08:33:06
import wx
import wx.lib.sized_controls as sc
import wx.lib.filebrowsebutton as filebrowse
from translation import *
from SC4DatTools import *
from SC4Data import *
import Image

class IconDlg(wx.Dialog):

    def __init__(self, parent, img):
        wx.Dialog.__init__(self, parent, -1, IconDlgTitle, size=(456, 157), style=wx.CAPTION)
        bSizer1 = wx.BoxSizer(wx.VERTICAL)
        fileBrowse = filebrowse.FileBrowseButton(self, -1, changeCallback=self.fbbCallback, labelText=IconDlgPicture)
        bSizer1.Add(fileBrowse, 0, wx.EXPAND, 5)
        self.bitmap1 = wx.StaticBitmap(self, wx.ID_ANY, wx.Bitmap('IconTpl.png'))
        bSizer1.Add(self.bitmap1, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 5)
        staticline1 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        bSizer1.Add(staticline1, 0, wx.ALL | wx.EXPAND, 5)
        sdbSizer1 = wx.StdDialogButtonSizer()
        sdbSizer1OK = wx.Button(self, wx.ID_OK)
        sdbSizer1.AddButton(sdbSizer1OK)
        sdbSizer1Cancel = wx.Button(self, wx.ID_CANCEL)
        sdbSizer1.AddButton(sdbSizer1Cancel)
        sdbSizer1.Realize()
        bSizer1.Add(sdbSizer1, 0, wx.EXPAND, 5)
        self.SetSizer(bSizer1)
        self.Layout()
        self.image = img
        if img != None:
            self.ReplaceImg(img)
        return

    def ReplaceImg(self, iconImage):
        wximage = wx.EmptyImage(44 * 4, 44)
        wximage.SetData(iconImage.convert('RGB').tostring())
        self.bitmap1.SetBitmap(wximage.ConvertToBitmap())

    def fbbCallback(self, event):
        fileName = event.GetString()
        try:
            image = Image.open(fileName)
        except:
            return

        image = image.resize((44, 44), Image.BICUBIC)
        template = Image.open('IconTpl.png')
        mask = Image.open('IconMaskTpl.png').convert('L')
        iconImage = Image.new('RGBA', (44 * 4, 44))
        iconImage.paste(image, (0, 0))
        iconImage.paste(image, (44, 0))
        iconImage.paste(image, (88, 0))
        iconImage.paste(image, (44 * 3, 0))
        iconImage = Image.composite(iconImage, template, mask)
        self.image = iconImage
        self.ReplaceImg(iconImage)
# okay decompiling SC4IconMakerDlg.pyo
