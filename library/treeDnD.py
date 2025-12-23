"""Drag and drop support for tree controls in SC4PIM."""
import pickle
import wx

class DropData(wx.CustomDataObject):

    def __init__(self):
        wx.CustomDataObject.__init__(self, wx.CustomDataFormat('SC4FilterDropData'))
        self.setObject(None)
        return

    def setObject(self, obj):
        self.SetData(pickle.dumps(obj))

    def getObject(self):
        return pickle.loads(self.GetData())


class DropTarget(wx.PyDropTarget):

    def __init__(self, tree, callbackItem, callbackFile):
        wx.PyDropTarget.__init__(self)
        self._makeObjects()
        self.tree = tree
        self.selections = []
        self.callbackItem = callbackItem
        self.callbackFile = callbackFile

    def _makeObjects(self):
        self.data = DropData()
        self.fileObject = wx.FileDataObject()
        comp = wx.DataObjectComposite()
        comp.Add(self.data)
        comp.Add(self.fileObject)
        self.comp = comp
        self.SetDataObject(comp)

    def _saveSelection(self):
        self.selections = self.tree.GetSelections()
        self.tree.UnselectAll()

    def _restoreSelection(self):
        self.tree.UnselectAll()
        for i in self.selections:
            self.tree.SelectItem(i)

        self.selections = []

    def OnEnter(self, x, y, d):
        self._saveSelection()
        return d

    def OnLeave(self):
        self._restoreSelection()

    def OnDrop(self, x, y):
        self.item, self.flags = self.tree.HitTest((x, y))
        self._restoreSelection()
        return True

    def OnDragOver(self, x, y, d):
        item, flags = self.tree.HitTest((x, y))
        if item:
            self.tree.EnsureVisible(item)
            try:
                data = self.tree.GetPyData(item)
            except Exception:
                data = None

            if data:
                if data.__class__.__name__ == 'DictWrapper':
                    if len(data.childs) == 0:
                        return d
        return wx.DragNone

    def OnData(self, x, y, d):
        if self.GetData():
            filenames = self.fileObject.GetFilenames()
            data = self.data.getObject()
            if filenames and self.callbackFile != None:
                self.callbackFile(filenames, self.item)
            elif data is not None and self.callbackItem != None:
                self.callbackItem(data, self.item)
            self._makeObjects()
        return d
