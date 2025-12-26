"""FSH (Maxis Texture) file reader for SC4PIM.

This module handles reading and parsing of FSH texture files used in SimCity 4.
Based on the C++ implementation in FSHReader.cpp.
"""

from typing import Tuple, List, NamedTuple
from dataclasses import dataclass
import struct

from QFSDecompressor import QFSDecompressor


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
        return self.magic == 0x00324853  # "SH2" in little-endian


@dataclass
class Record:
    """Represents a complete FSH file."""

    header: FileHeader
    entries: List[Entry]


class FSHReader:
    """Reader for FSH (Maxis Texture) files."""

    # Format codes
    CODE_32BIT = 0x07
    CODE_24BIT = 0x06
    CODE_4444 = 0x04
    CODE_0565 = 0x02
    CODE_1555 = 0x03
    CODE_DXT1 = 0x61
    CODE_DXT3 = 0x60
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
        try:
            import squish
        except ImportError:
            raise ValueError(
                "DXT decompression requires 'squish' library. Install with: pip install squish"
            )

        if bitmap.code == FSHReader.CODE_DXT1:
            flags = squish.DXT1
        elif bitmap.code == FSHReader.CODE_DXT3:
            flags = squish.DXT3
        elif bitmap.code == FSHReader.CODE_DXT5:
            flags = squish.DXT5
        else:
            raise ValueError(f"Invalid DXT format code: {bitmap.code}")

        decompressed = squish.DecompressImage(
            bitmap.data, bitmap.width, bitmap.height, flags
        )
        dst[:] = bytearray(decompressed)

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
    """Read a 24-bit little-endian integer."""
    byte0 = reader.read_u8()
    byte1 = reader.read_u8()
    byte2 = reader.read_u8()
    return (byte2 << 16) | (byte1 << 8) | byte0


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

