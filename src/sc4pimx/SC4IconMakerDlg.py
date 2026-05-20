"""Icon maker dialog for creating SC4 building icons."""
import wx
import wx.lib.filebrowsebutton as filebrowse
from PIL import Image
from PIL.Image import Resampling

from .paths import asset_path
from .translation import IconDlgPicture, IconDlgTitle


class IconDlg(wx.Dialog):

    def __init__(self, parent, img):
        wx.Dialog.__init__(self, parent, -1, IconDlgTitle, size=wx.Size(456, 157), style=wx.CAPTION)
        box_sizer1 = wx.BoxSizer(wx.VERTICAL)
        file_browse = filebrowse.FileBrowseButton(self, -1, changeCallback=self.fbb_callback, labelText=IconDlgPicture)
        box_sizer1.Add(file_browse, 0, wx.EXPAND, 5)
        self.bitmap1 = wx.StaticBitmap(self, wx.ID_ANY, wx.BitmapBundle(wx.Bitmap('IconTpl.png')))
        box_sizer1.Add(self.bitmap1, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 5)
        static_line1 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        box_sizer1.Add(static_line1, 0, wx.ALL | wx.EXPAND, 5)
        sdb_sizer1 = wx.StdDialogButtonSizer()
        sdb_sizer1_ok = wx.Button(self, wx.ID_OK)
        sdb_sizer1.AddButton(sdb_sizer1_ok)
        sdb_sizer1_cancel = wx.Button(self, wx.ID_CANCEL)
        sdb_sizer1.AddButton(sdb_sizer1_cancel)
        sdb_sizer1.Realize()
        box_sizer1.Add(sdb_sizer1, 0, wx.EXPAND, 5)
        self.SetSizer(box_sizer1)
        self.Layout()
        self.image = img
        if img is not None:
            self.replace_img(img)
        return

    def replace_img(self, icon_image):
        wx_image = wx.Image(44 * 4, 44)
        wx_image.SetData(icon_image.convert('RGB').tobytes())
        self.bitmap1.SetBitmap(wx_image.ConvertToBitmap())

    def fbb_callback(self, event):
        file_name = event.GetString()
        try:
            image = Image.open(file_name)
        except Exception:
            return

        image = image.resize((44, 44), Resampling.BICUBIC)
        template = Image.open(asset_path('templates', 'IconTpl.png'))
        mask = Image.open(asset_path('templates', 'IconMaskTpl.png')).convert('L')
        icon_image = Image.new('RGBA', (44 * 4, 44))
        icon_image.paste(image, (0, 0))
        icon_image.paste(image, (44, 0))
        icon_image.paste(image, (88, 0))
        icon_image.paste(image, (44 * 3, 0))
        icon_image = Image.composite(icon_image, template, mask)
        self.image = icon_image
        self.replace_img(icon_image)
