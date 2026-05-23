"""S3D textures holder for OpenGL rendering."""
from OpenGL.GL import (
    GL_CLAMP_TO_EDGE,
    GL_LINEAR,
    GL_NEAREST,
    GL_RGBA,
    GL_TEXTURE_2D,
    GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_MIN_FILTER,
    GL_TEXTURE_WRAP_S,
    GL_TEXTURE_WRAP_T,
    GL_UNPACK_ALIGNMENT,
    GL_UNSIGNED_BYTE,
    glBindTexture,
    glColor3f,
    glDeleteTextures,
    glDisable,
    glEnable,
    glGenTextures,
    glPixelStorei,
    glTexParameterf,
    glTexImage2D,
)
from PIL import Image

from . import FSHConverter


def _texture_name(value):
    return int(value)


def _delete_texture(value):
    glDeleteTextures([_texture_name(value)])


class S3DTexturesHolder(object):
    __module__ = __name__

    def __init__(self, glCanvas):
        self.textures = {}
        self.glCanvas = glCanvas

    def Free(self):
        self.glCanvas.SetCurrent()
        for texID, texture in self.textures.items():
            if texture[1] is not None:
                for layer in texture[1]:
                    _delete_texture(layer)

                texture[1] = None

        return

    def PrecacheTex(self, textureID, entry):
        try:
            self.glCanvas.SetCurrent()
            texture = self.textures[textureID]
            if texture[1] is not None:
                for layer in texture[1]:
                    _delete_texture(layer)

            texture[0] = None
            texture[1] = None
        except Exception:
            pass

        self.textures[textureID] = [
         entry, None]
        return

    def SetCurrentTex(self, textureID, layer=0, min_filter=None, mag_filter=None):
        glEnable(GL_TEXTURE_2D)
        if textureID not in self.textures:
            glDisable(GL_TEXTURE_2D)
            return
        self.glCanvas.SetCurrent()
        texture = self.textures[textureID]
        if texture[0] is None:
            glColor3f(1, 0, 0)
            glDisable(GL_TEXTURE_2D)
            return
        if texture[1] is None:
            try:
                texture[0].read_file(None, True, True)
                nbrLayers, trueAlpha, img, alpha, size = FSHConverter.decodeFSH(texture[0].content)
            except Exception:
                texture[0].content = None
                texture[0].rawContent = None
                glDisable(GL_TEXTURE_2D)
                return
            nbOfBytes = size[0] * size[1]
            expected_img = nbOfBytes * 3 * nbrLayers
            expected_alpha = nbOfBytes * nbrLayers
            if len(img) < expected_img or len(alpha) < expected_alpha:
                nbrLayers = 1
            texture[0].content = None
            texture[0].rawContent = None
            texture[1] = []
            for layerIdx in range(nbrLayers):
                try:
                    start_rgb = nbOfBytes * 3 * layerIdx
                    end_rgb = nbOfBytes * 3 * (layerIdx + 1)
                    start_a = nbOfBytes * layerIdx
                    end_a = nbOfBytes * (layerIdx + 1)
                    imBmp = Image.frombytes('RGB', size, img[start_rgb:end_rgb])
                    imAlpha = Image.frombytes('L', size, alpha[start_a:end_a])
                    im = Image.merge('RGBA', imBmp.split() + imAlpha.split())
                    im = im.tobytes('raw', 'RGBA')
                    texName = _texture_name(glGenTextures(1))
                    texture[1].append(texName)
                    glBindTexture(GL_TEXTURE_2D, texName)
                    glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
                    # S3D buildings are often split across several FSH tiles.
                    # Per-tile mipmaps can average dark padding into tile edges.
                    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size[0], size[1],
                                 0, GL_RGBA, GL_UNSIGNED_BYTE, im)
                    glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                    glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
                    glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                    glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                except Exception:
                    continue

        if texture[1] == []:
            glDisable(GL_TEXTURE_2D)
            glColor3f(1, 1, 1)
            return
        # The requested layer (e.g. an ATC animation plane) can run past the
        # number of decoded layers; clamp instead of raising IndexError.
        if layer >= len(texture[1]):
            layer = len(texture[1]) - 1
        elif layer < 0:
            layer = 0
        texName = texture[1][layer]
        glBindTexture(GL_TEXTURE_2D, texName)
        # Maxis default per S3D Mats wiki is NEAREST; bilinear is the special
        # case (mainly road textures). Caller passes 0 for nearest, >0 for
        # linear; None preserves the upload-time default.
        if min_filter is not None:
            glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER,
                            GL_LINEAR if min_filter > 0 else GL_NEAREST)
        if mag_filter is not None:
            glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER,
                            GL_LINEAR if mag_filter > 0 else GL_NEAREST)
        return
