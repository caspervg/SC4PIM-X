"""ATC (Animated Texture Catalog) file reader for SC4."""

import struct
import time

from OpenGL.GL import (
    GL_BLEND,
    GL_ONE_MINUS_SRC_ALPHA,
    GL_SRC_ALPHA,
    glBlendFunc,
    glEnable,
)

from sc4pimx import SC4Matrix
from sc4pimx.S3DTexturesHolder import S3DTexturesHolder
from sc4pimx.SC4DatTools import SC4Entry
from sc4pimx.SC4VirtualDat import VirtualDat


class ATC(object):
    def __init__(self, entry: SC4Entry, virtual_dat: VirtualDat):
        self.entry = entry
        if entry is None:
            return
        self.tgi = entry.tgi
        self.virtual_dat = virtual_dat
        self.current_frame = 0
        self._lastFrameTime = None
        self.type = self.fsh_tgi = self.avp_tid = self.avp_gid = self.avp_iids = self.num_frames = self.hotspot = None

    def read_file(self):
        if self.fsh_tgi is not None:
            return
        if self.entry is None:
            return
        entry = self.entry
        entry.read_file(None, True, True)
        buffer = entry.content
        self.type = struct.unpack("I", buffer[0:4])[0]
        self.fsh_tgi = struct.unpack("III", buffer[4:16])
        self.avp_tid = struct.unpack("I", buffer[16:20])[0]
        self.avp_gid = struct.unpack("I", buffer[20:24])[0]
        self.avp_iids = struct.unpack("IIIII", buffer[24:44])
        self.num_frames = struct.unpack("I", buffer[44:48])[0]

        del buffer
        entry.content = None
        entry.rawContent = None
        return

    def free_3d(self, s3d_textures_holder: S3DTexturesHolder):
        s3d_textures_holder.Free()

    def initialize(self, virtual_dat, viewer):
        self.PreLoad(virtual_dat, viewer.s3d_textures_holder)

    def PreLoad(self, virtual_dat, s3d_textures_holder):
        self.read_file()
        if self.fsh_tgi is None:
            return
        fsh_entry = virtual_dat.getEntry(self.fsh_tgi[0], self.fsh_tgi[1], self.fsh_tgi[2])
        s3d_textures_holder.PrecacheTex((self.fsh_tgi[1], self.fsh_tgi[2]), fsh_entry)
        if fsh_entry:
            self.avps = []
            for avp_iid in self.avp_iids:
                if avp_iid == 0:
                    self.avps.append(None)
                else:
                    self.avps.append(AVP(virtual_dat.getEntry(self.avp_tid, self.avp_gid, avp_iid), 256))

    def draw(self, viewer, static_file_name, zoom, rot, state=0):
        if zoom == -1:
            viewer.use_best_fit = True
            zoom = 4
        else:
            viewer.use_best_fit = False
        if "avps" not in self.__dict__:
            self.initialize(self.virtual_dat, viewer)
        if "avps" not in self.__dict__:
            return None
        if self.draw_le(zoom, rot):
            viewer.s3d_mesh = self
            viewer.reinitialize()
            viewer.refresh(False)
        return None

    def draw_le(self, zoom, rot):
        self.hotspot = (0, 0)
        if zoom == -1:
            zoom = 4
        if "avps" not in self.__dict__:
            return False
        if self.avps[zoom] is None:
            return False
        if self.avps[zoom].num_view_point == 8:
            rot *= 2
        if rot >= len(self.avps[zoom].chunks):
            return False
        # Advance current_frame based on elapsed time. ATC headers don't carry
        # a frame rate; default to 10 fps to match the viewer/LE tick.
        total = max(1, getattr(self, "num_frames", 1) or 1)
        if total > 1:
            interval = 1.0 / 10.0
            now = time.monotonic()
            if self._lastFrameTime is None:
                self._lastFrameTime = now
            else:
                elapsed = now - self._lastFrameTime
                steps = int(elapsed / interval)
                if steps > 0:
                    self._lastFrameTime += steps * interval
                    self.current_frame = (self.current_frame + steps) % total
        avp_data = self.avps[zoom].chunks[rot]
        self.hotspot = avp_data[3]
        self.current_layer = avp_data[0]
        size = (256, 256)
        self.quad_uvs_frame0 = [
            avp_data[1][0],
            avp_data[1][1],
            avp_data[1][0] + avp_data[2][0],
            avp_data[1][1] + avp_data[2][1],
        ]
        # Copy: the loop below mutates quad_uvs in place.
        self.quad_uvs = list(self.quad_uvs_frame0)
        for frame in range(self.current_frame):
            self.quad_uvs[0] += avp_data[2][0]
            self.quad_uvs[2] += avp_data[2][0]
            if self.quad_uvs[2] > size[0]:
                self.quad_uvs[0] = 0
                self.quad_uvs[2] = avp_data[2][0]
                self.quad_uvs[1] += avp_data[2][1]
                self.quad_uvs[3] += avp_data[2][1]
                if self.quad_uvs[3] > size[1]:
                    self.quad_uvs[1] = 0
                    self.quad_uvs[3] = avp_data[2][1]
                    self.current_layer += 1

        self.size = avp_data[2]
        self.quad_uvs = [
            float(self.quad_uvs[0]) / size[0],
            float(self.quad_uvs[1]) / size[1],
            float(self.quad_uvs[2]) / size[0],
            float(self.quad_uvs[3]) / size[1],
        ]
        return True

    def DrawGL(self, s3d_textures_holder: S3DTexturesHolder, renderer, projection, model):
        binding = s3d_textures_holder.SetCurrentTex(
            (self.fsh_tgi[1], self.fsh_tgi[2]), self.current_layer,
        )
        if not binding:
            return
        texture, sampler = binding
        if max(1, getattr(self, "num_frames", 1) or 1) > 1:
            s3d_textures_holder.glCanvas.request_animation(100)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        model = model @ SC4Matrix.translate(self.hotspot[0], -self.hotspot[1], 0)
        renderer.primitives.quad(
            (
                (-self.size[0] / 2, -self.size[1] / 2, 1),
                (-self.size[0] / 2, self.size[1] / 2, 1),
                (self.size[0] / 2, self.size[1] / 2, 1),
                (self.size[0] / 2, -self.size[1] / 2, 1),
            ),
            projection @ model,
            uvs=(
                (self.quad_uvs[0], self.quad_uvs[3]),
                (self.quad_uvs[0], self.quad_uvs[1]),
                (self.quad_uvs[2], self.quad_uvs[1]),
                (self.quad_uvs[2], self.quad_uvs[3]),
            ),
            texture=texture,
            sampler=sampler,
        )


class AVP(object):
    def __init__(self, entry, img_width):
        self.entry = entry
        if entry is None:
            return
        self.tgi = entry.tgi
        self._read_file(img_width)

    def _read_file(self, img_width):
        if self.entry is None:
            return
        entry = self.entry
        entry.read_file(None, True, True)
        buffer = entry.content
        self.magic = struct.unpack("I", buffer[0:4])[0]
        self.num_view_point = struct.unpack("I", buffer[4:8])[0]
        self.major_version = struct.unpack("I", buffer[8:12])[0]
        self.minor_version = struct.unpack("I", buffer[12:16])[0]
        self.reserved = struct.unpack("IIII", buffer[16:32])
        self.count = struct.unpack("I", buffer[32:36])[0]
        self.chunks = []
        buffer = buffer[36:]
        for x in range(self.count):
            plane = struct.unpack("B", buffer[0:1])[0]
            struct.unpack("B", buffer[1:2])[0]
            offset = struct.unpack("H", buffer[2:4])[0]
            x_start = offset % img_width
            y_start = offset // img_width
            width = struct.unpack("B", buffer[4:5])[0]
            height = struct.unpack("B", buffer[5:6])[0]
            hot_spot_x = width // 2 - struct.unpack("B", buffer[6:7])[0]
            hot_spot_y = height // 2 - struct.unpack("B", buffer[7:8])[0]
            self.chunks.append([plane, (x_start, y_start), (width, height), (hot_spot_x, hot_spot_y)])
            buffer = buffer[8:]

        del buffer
        entry.content = None
        entry.rawContent = None
