"""S3D textures holder for OpenGL rendering."""
from SC4OpenGL import *
import struct
import wx
from PIL import Image
from PIL import ImageChops
import FSHConverter

class S3DTexturesHolder(object):
    __module__ = __name__

    def __init__(self, glCanvas):
        self.textures = {}
        self.glCanvas = glCanvas

    def Free(self):
        self.glCanvas.SetCurrent()
        for texID, texture in self.textures.items():
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
        except Exception:
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
            for layerIdx in range(nbrLayers):
                imBmp = Image.frombytes('RGB', size, img[nbOfBytes * 3 * layerIdx:nbOfBytes * 3 * (layerIdx + 1)])
                imAlpha = Image.frombytes('L', size, alpha[nbOfBytes * layerIdx:nbOfBytes * (layerIdx + 1)])
                im = Image.merge('RGBA', imBmp.split() + imAlpha.split())
                im = im.tobytes('raw', 'RGBA')
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
