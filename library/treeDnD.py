# uncompyle6 version 2.11.5
# Python bytecode 2.4 (62061)
# Decompiled from: Python 2.7.18 (default, Oct 15 2023, 16:43:11) 
# [GCC 11.4.0]
# Embedded file name: treeDnD.pyo
# Compiled at: 2008-04-01 08:42:54
import cPickle as pickle
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
            except:
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
# okay decompiling treeDnD.pyo
