"""FSH (Maxis Texture) file reader for SC4PIM.

This module handles reading and parsing of FSH texture files used in SimCity 4.
Based on the C++ implementation in FSHReader.cpp.
"""

import struct
from dataclasses import dataclass
from typing import List, NamedTuple, Tuple

from .QFSDecompressor import QFSDecompressor


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
        if QFSDecompressor.is_qfs_compressed(buffer):
            try:
                file_span = QFSDecompressor.decompress(buffer)
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
            x_center = entry_reader.read_le_u16()
            y_center = entry_reader.read_le_u16()
            x_offset = entry_reader.read_le_u16()
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

        pixel_count = bitmap.width * bitmap.height
        rgba = bytearray(pixel_count * 4)

        if bitmap.code in (FSHReader.CODE_DXT1, FSHReader.CODE_DXT3, FSHReader.CODE_DXT5):
            if bitmap.width % 4 != 0 or bitmap.height % 4 != 0:
                raise ValueError("DXT dimensions must be multiple of 4")

        if bitmap.code == FSHReader.CODE_32BIT:
            FSHReader._convert_32bit(bitmap.data, rgba)
        elif bitmap.code == FSHReader.CODE_24BIT:
            FSHReader._convert_24bit(bitmap.data, rgba)
        elif bitmap.code == FSHReader.CODE_4444:
            FSHReader._convert_4444(bitmap.data, rgba)
        elif bitmap.code == FSHReader.CODE_0565:
            FSHReader._convert_0565(bitmap.data, rgba)
        elif bitmap.code == FSHReader.CODE_1555:
            FSHReader._convert_1555(bitmap.data, rgba)
        elif bitmap.code in (FSHReader.CODE_DXT1, FSHReader.CODE_DXT3, FSHReader.CODE_DXT5):
            FSHReader._convert_dxt(bitmap, rgba)
        else:
            raise ValueError(f"Unsupported format code: {bitmap.code}")

        return bytes(rgba)

    @staticmethod
    def _convert_32bit(src: bytes, dst: bytearray) -> None:
        """Convert 32-bit BGRA to RGBA."""
        for i in range(0, len(src), 4):
            b = src[i]
            g = src[i + 1]
            r = src[i + 2]
            a = src[i + 3]
            dst[i] = r
            dst[i + 1] = g
            dst[i + 2] = b
            dst[i + 3] = a

    @staticmethod
    def _convert_24bit(src: bytes, dst: bytearray) -> None:
        """Convert 24-bit BGR to RGBA."""
        dst_idx = 0
        for i in range(0, len(src), 3):
            b = src[i]
            g = src[i + 1]
            r = src[i + 2]
            dst[dst_idx] = r
            dst[dst_idx + 1] = g
            dst[dst_idx + 2] = b
            dst[dst_idx + 3] = 255
            dst_idx += 4

    @staticmethod
    def _convert_4444(src: bytes, dst: bytearray) -> None:
        """Convert ARGB4444 to RGBA8."""
        dst_idx = 0
        for i in range(0, len(src), 2):
            color = struct.unpack("<H", src[i : i + 2])[0]
            FSHReader._argb4444_to_rgba8(color, dst, dst_idx)
            dst_idx += 4

    @staticmethod
    def _convert_0565(src: bytes, dst: bytearray) -> None:
        """Convert RGB565 to RGBA8."""
        dst_idx = 0
        for i in range(0, len(src), 2):
            color = struct.unpack("<H", src[i : i + 2])[0]
            FSHReader._rgb565_to_rgba8(color, dst, dst_idx)
            dst_idx += 4

    @staticmethod
    def _convert_1555(src: bytes, dst: bytearray) -> None:
        """Convert ARGB1555 to RGBA8."""
        dst_idx = 0
        for i in range(0, len(src), 2):
            color = struct.unpack("<H", src[i : i + 2])[0]
            FSHReader._argb1555_to_rgba8(color, dst, dst_idx)
            dst_idx += 4

    @staticmethod
    def _convert_dxt(bitmap: Bitmap, dst: bytearray) -> None:
        """Convert DXT compressed format to RGBA8."""
        if bitmap.code not in (FSHReader.CODE_DXT1, FSHReader.CODE_DXT3, FSHReader.CODE_DXT5):
            raise ValueError(f"Invalid DXT format code: {bitmap.code}")

        expected_size = FSHReader._expected_data_size(
            bitmap.code, bitmap.width, bitmap.height
        )
        if len(bitmap.data) != expected_size:
            raise ValueError(
                f"DXT data size mismatch (expected {expected_size}, got {len(bitmap.data)})"
            )

        src = bitmap.data
        src_pos = 0
        blocks_wide = (bitmap.width + 3) // 4
        blocks_high = (bitmap.height + 3) // 4
        for block_y in range(blocks_high):
            for block_x in range(blocks_wide):
                if bitmap.code == FSHReader.CODE_DXT1:
                    colors = FSHReader._decode_dxt_color_block(src[src_pos:src_pos + 8], False)
                    src_pos += 8
                    alphas = None
                elif bitmap.code == FSHReader.CODE_DXT3:
                    alphas = FSHReader._decode_dxt3_alpha(src[src_pos:src_pos + 8])
                    src_pos += 8
                    colors = FSHReader._decode_dxt_color_block(src[src_pos:src_pos + 8], True)
                    src_pos += 8
                else:
                    alphas = FSHReader._decode_dxt5_alpha(src[src_pos:src_pos + 8])
                    src_pos += 8
                    colors = FSHReader._decode_dxt_color_block(src[src_pos:src_pos + 8], True)
                    src_pos += 8

                codes = struct.unpack("<I", src[src_pos - 4:src_pos])[0]
                for py in range(4):
                    for px in range(4):
                        x = block_x * 4 + px
                        y = block_y * 4 + py
                        if x >= bitmap.width or y >= bitmap.height:
                            continue
                        color = colors[(codes >> (2 * (py * 4 + px))) & 0x03]
                        dst_idx = (y * bitmap.width + x) * 4
                        dst[dst_idx] = color[0]
                        dst[dst_idx + 1] = color[1]
                        dst[dst_idx + 2] = color[2]
                        dst[dst_idx + 3] = color[3] if alphas is None else alphas[py * 4 + px]

    @staticmethod
    def _decode_dxt_color_block(block: bytes, force_four_color: bool) -> list[tuple[int, int, int, int]]:
        color0, color1 = struct.unpack("<HH", block[:4])
        r0, g0, b0 = FSHReader._rgb565_components(color0)
        r1, g1, b1 = FSHReader._rgb565_components(color1)
        colors = [
            (r0, g0, b0, 255),
            (r1, g1, b1, 255),
        ]
        if force_four_color or color0 > color1:
            colors.append(((2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3, 255))
            colors.append(((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3, 255))
        else:
            colors.append(((r0 + r1) // 2, (g0 + g1) // 2, (b0 + b1) // 2, 255))
            colors.append((0, 0, 0, 0))
        return colors

    @staticmethod
    def _decode_dxt3_alpha(block: bytes) -> list[int]:
        value = int.from_bytes(block, "little")
        return [(((value >> (4 * i)) & 0xF) * 17) for i in range(16)]

    @staticmethod
    def _decode_dxt5_alpha(block: bytes) -> list[int]:
        alpha0 = block[0]
        alpha1 = block[1]
        palette = [alpha0, alpha1]
        if alpha0 > alpha1:
            palette.extend([
                (6 * alpha0 + alpha1) // 7,
                (5 * alpha0 + 2 * alpha1) // 7,
                (4 * alpha0 + 3 * alpha1) // 7,
                (3 * alpha0 + 4 * alpha1) // 7,
                (2 * alpha0 + 5 * alpha1) // 7,
                (alpha0 + 6 * alpha1) // 7,
            ])
        else:
            palette.extend([
                (4 * alpha0 + alpha1) // 5,
                (3 * alpha0 + 2 * alpha1) // 5,
                (2 * alpha0 + 3 * alpha1) // 5,
                (alpha0 + 4 * alpha1) // 5,
                0,
                255,
            ])
        bits = int.from_bytes(block[2:8], "little")
        return [palette[(bits >> (3 * i)) & 0x07] for i in range(16)]

    @staticmethod
    def _rgb565_components(color: int) -> tuple[int, int, int]:
        r = (color >> 11) & 0x1F
        g = (color >> 5) & 0x3F
        b = color & 0x1F
        return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)

    @staticmethod
    def _argb4444_to_rgba8(color: int, rgba: bytearray, offset: int) -> None:
        """Convert single ARGB4444 color to RGBA8."""
        a = (color >> 12) & 0xF
        r = (color >> 8) & 0xF
        g = (color >> 4) & 0xF
        b = color & 0xF
        rgba[offset] = (r << 4) | r
        rgba[offset + 1] = (g << 4) | g
        rgba[offset + 2] = (b << 4) | b
        rgba[offset + 3] = (a << 4) | a

    @staticmethod
    def _rgb565_to_rgba8(color: int, rgba: bytearray, offset: int) -> None:
        """Convert single RGB565 color to RGBA8."""
        r = (color >> 11) & 0x1F
        g = (color >> 5) & 0x3F
        b = color & 0x1F
        rgba[offset] = (r << 3) | (r >> 2)
        rgba[offset + 1] = (g << 2) | (g >> 4)
        rgba[offset + 2] = (b << 3) | (b >> 2)
        rgba[offset + 3] = 255

    @staticmethod
    def _argb1555_to_rgba8(color: int, rgba: bytearray, offset: int) -> None:
        """Convert single ARGB1555 color to RGBA8."""
        a = (color >> 15) & 0x1
        r = (color >> 10) & 0x1F
        g = (color >> 5) & 0x1F
        b = color & 0x1F
        rgba[offset] = (r << 3) | (r >> 2)
        rgba[offset + 1] = (g << 3) | (g >> 2)
        rgba[offset + 2] = (b << 3) | (b >> 2)
        rgba[offset + 3] = 255 if a else 0

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

