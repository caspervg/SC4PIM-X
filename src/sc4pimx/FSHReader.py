"""FSH (Maxis Texture) file reader for SC4PIM.

This module handles reading and parsing of FSH texture files used in SimCity 4.
Based on the C++ implementation in FSHReader.cpp.
"""

import struct
from dataclasses import dataclass
from typing import List, NamedTuple, Tuple

import numpy as np

from . import QFS


class Bitmap(NamedTuple):
    """Represents a single bitmap/mipmap level in an FSH entry."""

    code: int
    width: int
    height: int
    mip_level: int
    data: bytes


@dataclass
class Entry:
    """Represents a single entry (texture) in an FSH file."""

    name: str
    format_code: int
    width: int
    height: int
    mip_count: int
    bitmaps: List[Bitmap]
    label: str = ""


@dataclass
class FileHeader:
    """FSH file header."""

    magic: int
    size: int
    num_entries: int
    dir_id: int

    def is_valid(self) -> bool:
        """Check if header is valid."""
        return self.magic in {
            0x49504853,  # 'SHPI'
            0x34363247,  # 'G264'
            0x36363247,  # 'G266'
            0x34353347,  # 'G354'
        }


@dataclass
class Record:
    """Represents a complete FSH file."""

    header: FileHeader
    entries: List[Entry]


class FSHReader:
    """Reader for FSH (Maxis Texture) files."""

    # Format codes
    CODE_32BIT = 0x7D
    CODE_24BIT = 0x7F
    CODE_4444 = 0x6D
    CODE_0565 = 0x78
    CODE_1555 = 0x7E
    CODE_DXT1 = 0x60
    CODE_DXT3 = 0x61
    CODE_DXT5 = 0x62

    @staticmethod
    def parse(buffer: bytes) -> Record:
        """Parse an FSH file.

        Args:
            buffer: Raw FSH file data (may be QFS compressed)

        Returns:
            Record object containing parsed FSH data

        Raises:
            ValueError: If parsing fails
        """
        if len(buffer) < 16:
            raise ValueError("Buffer too small for FSH header")

        # Decompress if needed
        file_span = buffer
        if QFS.is_qfs_compressed(buffer):
            try:
                file_span = QFS.decode(buffer)
                if file_span is None:
                    raise ValueError("Invalid QFS stream")
            except ValueError as e:
                raise ValueError(f"Failed to decompress FSH payload: {e}") from e

        reader = _SpanReader(file_span)

        # Read header
        magic = reader.read_le_u32()
        size = reader.read_le_u32()
        num_entries = reader.read_le_u32()
        dir_id = reader.read_le_u32()

        header = FileHeader(magic=magic, size=size, num_entries=num_entries, dir_id=dir_id)

        if not header.is_valid():
            raise ValueError("Invalid FSH header")

        # Read directory entries
        directory: List[Tuple[str, int]] = []
        for i in range(num_entries):
            name_bytes = reader.read_bytes(4)
            name = _make_name(name_bytes)
            offset = reader.read_le_u32()
            directory.append((name, offset))

        # Parse entries
        entries: List[Entry] = []
        for i in range(num_entries):
            name, offset = directory[i]
            next_offset = (
                directory[i + 1][1] if i + 1 < len(directory) else len(file_span)
            )

            if offset >= len(file_span) or offset >= next_offset:
                raise ValueError("Invalid FSH directory offsets")

            entry_data = file_span[offset:next_offset]
            entry_reader = _SpanReader(entry_data)

            entry = Entry(
                name=name, format_code=0, width=0, height=0, mip_count=0, bitmaps=[]
            )

            record_byte = entry_reader.read_u8()
            block_size = _read_u24le(entry_reader)

            width = entry_reader.read_le_u16()
            height = entry_reader.read_le_u16()
            _x_center = entry_reader.read_le_u16()
            _y_center = entry_reader.read_le_u16()
            _x_offset = entry_reader.read_le_u16()
            y_offset = entry_reader.read_le_u16()

            entry.format_code = record_byte & 0x7F
            entry.width = width
            entry.height = height
            entry.mip_count = (y_offset >> 12) & 0x0F

            # Read bitmaps/mipmaps
            for mip in range(entry.mip_count + 1):
                mip_width = max(1, width >> mip)
                mip_height = max(1, height >> mip)

                # Skip if DXT and dimensions not multiple of 4
                if (
                    entry.format_code in (FSHReader.CODE_DXT1, FSHReader.CODE_DXT3)
                    and (mip_width % 4 != 0 or mip_height % 4 != 0)
                ):
                    break

                bitmap = Bitmap(
                    code=entry.format_code,
                    width=mip_width,
                    height=mip_height,
                    mip_level=mip,
                    data=b"",
                )

                data_size = FSHReader._expected_data_size(bitmap.code, bitmap.width, bitmap.height)
                bitmap_data = entry_reader.read_bytes(data_size)
                bitmap = Bitmap(
                    code=bitmap.code,
                    width=bitmap.width,
                    height=bitmap.height,
                    mip_level=bitmap.mip_level,
                    data=bitmap_data,
                )
                entry.bitmaps.append(bitmap)

            # Read label if present
            if block_size != 0:
                attachment_offset = offset + block_size
                if attachment_offset + 4 < next_offset:
                    attachment_data = file_span[attachment_offset : next_offset]
                    if len(attachment_data) >= 5 and attachment_data[0] == 0x70:
                        label_start = 4
                        label_end = attachment_data.find(b"\x00", label_start)
                        if label_end == -1:
                            label_end = len(attachment_data)
                        entry.label = attachment_data[label_start:label_end].decode(
                            "utf-8", errors="ignore"
                        )

            entries.append(entry)

        return Record(header=header, entries=entries)

    @staticmethod
    def convert_to_rgba8(bitmap: Bitmap) -> bytes:
        """Convert bitmap to RGBA8 format.

        Args:
            bitmap: Bitmap to convert

        Returns:
            RGBA8 pixel data (4 bytes per pixel)

        Raises:
            ValueError: If conversion fails
        """
        if bitmap.width == 0 or bitmap.height == 0:
            raise ValueError("Invalid bitmap dimensions")

        expected_size = FSHReader._expected_data_size(
            bitmap.code, bitmap.width, bitmap.height
        )
        if expected_size == 0:
            raise ValueError(f"Unsupported format code: {bitmap.code}")
        if len(bitmap.data) != expected_size:
            raise ValueError(
                f"Bitmap data size mismatch (expected {expected_size}, got {len(bitmap.data)})"
            )

        code = bitmap.code
        if code in (FSHReader.CODE_DXT1, FSHReader.CODE_DXT3, FSHReader.CODE_DXT5):
            if bitmap.width % 4 != 0 or bitmap.height % 4 != 0:
                raise ValueError("DXT dimensions must be multiple of 4")
            return FSHReader._convert_dxt(bitmap)
        if code == FSHReader.CODE_32BIT:
            return FSHReader._convert_32bit(bitmap.data)
        if code == FSHReader.CODE_24BIT:
            return FSHReader._convert_24bit(bitmap.data)
        if code == FSHReader.CODE_4444:
            return FSHReader._convert_4444(bitmap.data)
        if code == FSHReader.CODE_0565:
            return FSHReader._convert_0565(bitmap.data)
        if code == FSHReader.CODE_1555:
            return FSHReader._convert_1555(bitmap.data)
        raise ValueError(f"Unsupported format code: {code}")

    # The conversions below are vectorised with numpy: the previous
    # pure-Python per-pixel loops cost ~10-20 ms per 256x256 texture, which
    # dominated preview/ImageDB generation. numpy brings that to well under
    # 1 ms while producing byte-identical output.

    @staticmethod
    def _convert_32bit(src: bytes) -> bytes:
        """Convert 32-bit BGRA to RGBA8."""
        arr = np.frombuffer(src, dtype=np.uint8).reshape(-1, 4)
        return np.ascontiguousarray(arr[:, [2, 1, 0, 3]]).tobytes()

    @staticmethod
    def _convert_24bit(src: bytes) -> bytes:
        """Convert 24-bit BGR to RGBA8."""
        arr = np.frombuffer(src, dtype=np.uint8).reshape(-1, 3)
        out = np.empty((arr.shape[0], 4), dtype=np.uint8)
        out[:, 0] = arr[:, 2]
        out[:, 1] = arr[:, 1]
        out[:, 2] = arr[:, 0]
        out[:, 3] = 255
        return out.tobytes()

    @staticmethod
    def _convert_4444(src: bytes) -> bytes:
        """Convert ARGB4444 to RGBA8."""
        v = np.frombuffer(src, dtype="<u2").astype(np.uint32)
        out = np.empty((v.shape[0], 4), dtype=np.uint8)
        a = (v >> 12) & 0xF
        r = (v >> 8) & 0xF
        g = (v >> 4) & 0xF
        b = v & 0xF
        out[:, 0] = (r << 4) | r
        out[:, 1] = (g << 4) | g
        out[:, 2] = (b << 4) | b
        out[:, 3] = (a << 4) | a
        return out.tobytes()

    @staticmethod
    def _convert_0565(src: bytes) -> bytes:
        """Convert RGB565 to RGBA8."""
        v = np.frombuffer(src, dtype="<u2").astype(np.uint32)
        out = np.empty((v.shape[0], 4), dtype=np.uint8)
        r = (v >> 11) & 0x1F
        g = (v >> 5) & 0x3F
        b = v & 0x1F
        out[:, 0] = (r << 3) | (r >> 2)
        out[:, 1] = (g << 2) | (g >> 4)
        out[:, 2] = (b << 3) | (b >> 2)
        out[:, 3] = 255
        return out.tobytes()

    @staticmethod
    def _convert_1555(src: bytes) -> bytes:
        """Convert ARGB1555 to RGBA8."""
        v = np.frombuffer(src, dtype="<u2").astype(np.uint32)
        out = np.empty((v.shape[0], 4), dtype=np.uint8)
        a = (v >> 15) & 0x1
        r = (v >> 10) & 0x1F
        g = (v >> 5) & 0x1F
        b = v & 0x1F
        out[:, 0] = (r << 3) | (r >> 2)
        out[:, 1] = (g << 3) | (g >> 2)
        out[:, 2] = (b << 3) | (b >> 2)
        out[:, 3] = np.where(a == 1, 255, 0)
        return out.tobytes()

    @staticmethod
    def _convert_dxt(bitmap: Bitmap) -> bytes:
        """Convert DXT1/DXT3/DXT5 compressed data to RGBA8 (vectorised)."""
        code = bitmap.code
        expected_size = FSHReader._expected_data_size(code, bitmap.width, bitmap.height)
        if len(bitmap.data) != expected_size:
            raise ValueError(
                f"DXT data size mismatch (expected {expected_size}, got {len(bitmap.data)})"
            )

        w, h = bitmap.width, bitmap.height
        bw, bh = w // 4, h // 4
        nblocks = bw * bh
        block_size = 8 if code == FSHReader.CODE_DXT1 else 16
        blocks = np.frombuffer(bitmap.data, dtype=np.uint8).reshape(nblocks, block_size)
        # For DXT3/DXT5 the colour block follows the 8-byte alpha block.
        color_block = blocks if code == FSHReader.CODE_DXT1 else blocks[:, 8:]
        idx = np.arange(nblocks)

        c0 = color_block[:, 0].astype(np.uint16) | (color_block[:, 1].astype(np.uint16) << 8)
        c1 = color_block[:, 2].astype(np.uint16) | (color_block[:, 3].astype(np.uint16) << 8)
        codes = (
            color_block[:, 4].astype(np.uint32)
            | (color_block[:, 5].astype(np.uint32) << 8)
            | (color_block[:, 6].astype(np.uint32) << 16)
            | (color_block[:, 7].astype(np.uint32) << 24)
        )

        def rgb565(c: np.ndarray) -> np.ndarray:
            c = c.astype(np.int32)
            r = (c >> 11) & 0x1F
            g = (c >> 5) & 0x3F
            b = c & 0x1F
            return np.stack(
                [(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], axis=1
            )

        rgb0 = rgb565(c0)  # (nblocks, 3)
        rgb1 = rgb565(c1)
        # palette: (nblocks, 4 colours, RGBA)
        palette = np.zeros((nblocks, 4, 4), dtype=np.int32)
        palette[:, 0, :3] = rgb0
        palette[:, 1, :3] = rgb1
        palette[:, 0:2, 3] = 255
        four = (code != FSHReader.CODE_DXT1) | (c0.astype(np.int32) > c1.astype(np.int32))
        fm = four[:, None]
        palette[:, 2, :3] = np.where(fm, (2 * rgb0 + rgb1) // 3, (rgb0 + rgb1) // 2)
        palette[:, 2, 3] = 255
        palette[:, 3, :3] = np.where(fm, (rgb0 + 2 * rgb1) // 3, 0)
        palette[:, 3, 3] = np.where(four, 255, 0)

        rgba = np.empty((nblocks, 16, 4), dtype=np.int32)
        for i in range(16):
            sel = (codes >> (2 * i)) & 0x03
            rgba[:, i, :] = palette[idx, sel]

        if code == FSHReader.CODE_DXT3:
            ab = blocks[:, :8].astype(np.uint16)
            nib = np.empty((nblocks, 16), dtype=np.uint16)
            nib[:, 0::2] = ab & 0x0F
            nib[:, 1::2] = (ab >> 4) & 0x0F
            rgba[:, :, 3] = nib * 17
        elif code == FSHReader.CODE_DXT5:
            ablk = blocks[:, :8]
            a0 = ablk[:, 0].astype(np.int32)
            a1 = ablk[:, 1].astype(np.int32)
            pal = np.zeros((nblocks, 8), dtype=np.int32)
            pal[:, 0] = a0
            pal[:, 1] = a1
            gt = a0 > a1
            gt_vals = [
                (6 * a0 + a1) // 7, (5 * a0 + 2 * a1) // 7, (4 * a0 + 3 * a1) // 7,
                (3 * a0 + 4 * a1) // 7, (2 * a0 + 5 * a1) // 7, (a0 + 6 * a1) // 7,
            ]
            le_vals = [
                (4 * a0 + a1) // 5, (3 * a0 + 2 * a1) // 5, (2 * a0 + 3 * a1) // 5,
                (a0 + 4 * a1) // 5, np.zeros_like(a0), np.full_like(a0, 255),
            ]
            for k in range(6):
                pal[:, 2 + k] = np.where(gt, gt_vals[k], le_vals[k])
            bits = np.zeros(nblocks, dtype=np.uint64)
            for k in range(6):
                bits |= ablk[:, 2 + k].astype(np.uint64) << np.uint64(8 * k)
            for i in range(16):
                sel = ((bits >> np.uint64(3 * i)) & np.uint64(0x07)).astype(np.intp)
                rgba[:, i, 3] = pal[idx, sel]

        # (nblocks,16,4) -> (bh,bw,4,4,4) -> (h,w,4)
        img = rgba.reshape(bh, bw, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(h, w, 4)
        return img.astype(np.uint8).tobytes()

    @staticmethod
    def _expected_data_size(format_code: int, width: int, height: int) -> int:
        """Calculate expected data size for a bitmap."""
        if format_code == FSHReader.CODE_32BIT:
            return width * height * 4
        elif format_code == FSHReader.CODE_24BIT:
            return width * height * 3
        elif format_code in (
            FSHReader.CODE_4444,
            FSHReader.CODE_0565,
            FSHReader.CODE_1555,
        ):
            return width * height * 2
        elif format_code == FSHReader.CODE_DXT1:
            return ((width + 3) // 4) * ((height + 3) // 4) * 8
        elif format_code in (FSHReader.CODE_DXT3, FSHReader.CODE_DXT5):
            return ((width + 3) // 4) * ((height + 3) // 4) * 16
        else:
            return 0


def _make_name(name_bytes: bytes) -> str:
    """Convert 4-byte name field to string."""
    name_str = name_bytes.decode("utf-8", errors="ignore")
    null_pos = name_str.find("\x00")
    if null_pos != -1:
        name_str = name_str[:null_pos]
    return name_str


def _read_u24le(reader: "_SpanReader") -> int:
    """Read a 24-bit FSH block size."""
    byte0 = reader.read_u8()
    byte1 = reader.read_u8()
    byte2 = reader.read_u8()
    return (byte0 << 16) | (byte1 << 8) | byte2


class _SpanReader:
    """Helper class for reading binary data."""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read_u8(self) -> int:
        """Read unsigned 8-bit integer."""
        if self.pos >= len(self.data):
            raise ValueError("Read past end of buffer")
        val = self.data[self.pos]
        self.pos += 1
        return val

    def read_le_u16(self) -> int:
        """Read little-endian unsigned 16-bit integer."""
        if self.pos + 2 > len(self.data):
            raise ValueError("Read past end of buffer")
        val = struct.unpack("<H", self.data[self.pos : self.pos + 2])[0]
        self.pos += 2
        return val

    def read_le_u32(self) -> int:
        """Read little-endian unsigned 32-bit integer."""
        if self.pos + 4 > len(self.data):
            raise ValueError("Read past end of buffer")
        val = struct.unpack("<I", self.data[self.pos : self.pos + 4])[0]
        self.pos += 4
        return val

    def read_bytes(self, count: int) -> bytes:
        """Read raw bytes."""
        if self.pos + count > len(self.data):
            raise ValueError("Read past end of buffer")
        val = self.data[self.pos : self.pos + count]
        self.pos += count
        return val

    def peek_bytes(self, count: int) -> bytes:
        """Peek at bytes without advancing position."""
        if self.pos + count > len(self.data):
            raise ValueError("Read past end of buffer")
        return self.data[self.pos : self.pos + count]

    def skip(self, count: int) -> None:
        """Skip bytes."""
        if self.pos + count > len(self.data):
            raise ValueError("Skip past end of buffer")
        self.pos += count

