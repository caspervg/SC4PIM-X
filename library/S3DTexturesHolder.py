# uncompyle6 version 2.11.5
# Python bytecode 2.4 (62061)
# Decompiled from: Python 2.7.18 (default, Oct 15 2023, 16:43:11) 
# [GCC 11.4.0]
# Embedded file name: S3DTexturesHolder.pyo
# Compiled at: 2008-04-07 22:32:26
from SC4OpenGL import *
import struct
import wx
import Image
import ImageChops
import FSHConverter

class S3DTexturesHolder(object):
    __module__ = __name__

    def __init__(self, glCanvas):
        self.textures = {}
        self.glCanvas = glCanvas

    def Free(self):
        self.glCanvas.SetCurrent()
        for texID, texture in self.textures.iteritems():
            if texture[1] != None:
                for layer in texture[1]:
                    glDeleteTextures(layer)

                texture[1] = None

        return

    def PrecacheTex(self, textureID, entry):
        try:
            self.glCanvas.SetCurrent()
            texture = self.textures[textureID]
            if texture[1] != None:
                for layer in texture[1]:
                    glDeleteTextures(layer)

            texture[0] = None
            texture[1] = None
        except:
            pass

        self.textures[textureID] = [
         entry, None]
        return

    def SetCurrentTex(self, textureID, layer=0):
        glEnable(GL_TEXTURE_2D)
        if textureID not in self.textures:
            glDisable(GL_TEXTURE_2D)
            return
        self.glCanvas.SetCurrent()
        texture = self.textures[textureID]
        if texture[0] == None:
            glColor3f(1, 0, 0)
            glDisable(GL_TEXTURE_2D)
            return
        if texture[1] == None:
            texture[0].ReadFile(None, True, True)
            nbrLayers, trueAlpa, img, alpha, size = FSHConverter.decodeFSH(texture[0].content)
            nbOfBytes = size[0] * size[1]
            texture[0].content = None
            texture[0].rawContent = None
            texture[1] = []
            for layerIdx in xrange(nbrLayers):
                imBmp = Image.fromstring('RGB', size, img[nbOfBytes * 3 * layerIdx:nbOfBytes * 3 * (layerIdx + 1)])
                imAlpha = Image.fromstring('L', size, alpha[nbOfBytes * layerIdx:nbOfBytes * (layerIdx + 1)])
                im = Image.merge('RGBA', imBmp.split() + imAlpha.split())
                im = im.tostring('raw', 'RGBA')
                texName = glGenTextures(1)
                texture[1].append(texName)
                glBindTexture(GL_TEXTURE_2D, texName)
                glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
                glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size[0], size[1], 0, GL_RGBA, GL_UNSIGNED_BYTE, im)
                glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP)
                glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP)
                glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)

        if texture[1] == []:
            glDisable(GL_TEXTURE_2D)
            glColor3f(1, 1, 1)
            return
        texName = texture[1][layer]
        glBindTexture(GL_TEXTURE_2D, texName)
        return
# okay decompiling S3DTexturesHolder.pyo
