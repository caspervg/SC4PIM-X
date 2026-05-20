"""QFS (Refpack) decompression module for SC4PIM.

This module handles decompression of QFS-compressed data used in SimCity 4 files.
Based on the C++ implementation in QFSDecompressor.cpp.
"""


class QFSDecompressor:
    """Handles QFS (Refpack) compression/decompression."""

    # QFS/RefPack signature: byte 0 is {0x10, 0x11, ...} (bit 0 masked off),
    # byte 1 is 0xFB -> ((b0 & 0xFE) << 8) | b1 == 0x10FB.
    MAGIC_COMPRESSED = 0x10FB

    @staticmethod
    def is_qfs_compressed(buffer: bytes) -> bool:
        """Check if buffer is QFS compressed.

        Args:
            buffer: Data to check

        Returns:
            True if buffer appears to be QFS compressed
        """
        if len(buffer) < 2:
            return False
        magic = ((buffer[0] & 0xFE) << 8) | buffer[1]
        return magic == QFSDecompressor.MAGIC_COMPRESSED

    @staticmethod
    def get_uncompressed_size(buffer: bytes) -> int:
        """Get the uncompressed size from QFS header.

        Args:
            buffer: QFS compressed data

        Returns:
            Uncompressed size, or 0 if not QFS data
        """
        if not QFSDecompressor.is_qfs_compressed(buffer):
            return 0
        return QFSDecompressor._read_24be(buffer, 0)

    @staticmethod
    def decompress(buffer: bytes) -> bytes:
        """Decompress QFS data.

        Args:
            buffer: QFS compressed data

        Returns:
            Decompressed data

        Raises:
            ValueError: If decompression fails
        """
        if len(buffer) < 5:
            raise ValueError(f"QFS payload too small ({len(buffer)} bytes)")

        if not QFSDecompressor.is_qfs_compressed(buffer):
            raise ValueError(
                f"QFS magic mismatch: expected 0x{QFSDecompressor.MAGIC_COMPRESSED:04X}, "
                f"got 0x{((buffer[0] & 0xFE) << 8) | buffer[1]:04X}"
            )

        uncompressed_size = QFSDecompressor._read_24be(buffer, 0)
        if uncompressed_size == 0:
            return bytes()

        output = bytearray(uncompressed_size)
        QFSDecompressor._decompress_internal(buffer, output)
        return bytes(output)

    @staticmethod
    def _read_24be(data: bytes, offset: int) -> int:
        """Read a 24-bit big-endian integer."""
        return (data[offset + 2] << 16) | (data[offset + 3] << 8) | data[offset + 4]

    @staticmethod
    def _copy_literal(src: bytes, src_pos: int, dst: bytearray, dst_pos: int, length: int) -> None:
        """Copy literal data."""
        if length == 0:
            return
        dst[dst_pos : dst_pos + length] = src[src_pos : src_pos + length]

    @staticmethod
    def _offset_copy(buffer: bytearray, dest_pos: int, offset: int, length: int) -> None:
        """Copy data from earlier position in buffer."""
        if offset <= 0 or offset > dest_pos:
            raise ValueError(f"Invalid QFS offset {offset} at dest {dest_pos}")

        src_pos = dest_pos - offset
        for i in range(length):
            buffer[dest_pos + i] = buffer[src_pos + i]

    @staticmethod
    def _decompress_internal(input_data: bytes, output: bytearray) -> None:
        """Internal decompression implementation."""
        in_pos = 8 if (input_data[0] & 0x01) else 5
        out_pos = 0
        control1 = 0

        input_size = len(input_data)
        output_size = len(output)

        while in_pos < input_size and control1 < 0xFC:
            if in_pos >= input_size:
                raise ValueError("QFS truncated while reading control byte")

            control1 = input_data[in_pos] & 0xFF
            in_pos += 1

            if control1 <= 0x7F:
                # Short block
                if in_pos >= input_size:
                    raise ValueError("QFS truncated in control1<=0x7F block")

                control2 = input_data[in_pos] & 0xFF
                in_pos += 1

                literal_len = control1 & 0x03
                if in_pos + literal_len > input_size:
                    raise ValueError("QFS literal overruns input (short block)")
                if out_pos + literal_len > output_size:
                    raise ValueError("QFS literal overruns output (short block)")

                QFSDecompressor._copy_literal(input_data, in_pos, output, out_pos, literal_len)
                out_pos += literal_len
                in_pos += literal_len

                offset = ((control1 & 0x60) << 3) + control2 + 1
                copy_len = ((control1 & 0x1C) >> 2) + 3
                if out_pos + copy_len > output_size:
                    raise ValueError("QFS copy overruns output (short block)")

                QFSDecompressor._offset_copy(output, out_pos, offset, copy_len)
                out_pos += copy_len

            elif control1 <= 0xBF:
                # Mid block
                if in_pos + 1 >= input_size:
                    raise ValueError("QFS truncated in control1<=0xBF block")

                control2 = input_data[in_pos] & 0xFF
                in_pos += 1
                control3 = input_data[in_pos] & 0xFF
                in_pos += 1

                literal_len = (control2 >> 6) & 0x03
                if in_pos + literal_len > input_size:
                    raise ValueError("QFS literal overruns input (mid block)")
                if out_pos + literal_len > output_size:
                    raise ValueError("QFS literal overruns output (mid block)")

                QFSDecompressor._copy_literal(input_data, in_pos, output, out_pos, literal_len)
                out_pos += literal_len
                in_pos += literal_len

                offset = ((control2 & 0x3F) << 8) + control3 + 1
                copy_len = (control1 & 0x3F) + 4
                if out_pos + copy_len > output_size:
                    raise ValueError("QFS copy overruns output (mid block)")

                QFSDecompressor._offset_copy(output, out_pos, offset, copy_len)
                out_pos += copy_len

            elif control1 <= 0xDF:
                # Long block
                if in_pos + 2 >= input_size:
                    raise ValueError("QFS truncated in control1<=0xDF block")

                control2 = input_data[in_pos] & 0xFF
                in_pos += 1
                control3 = input_data[in_pos] & 0xFF
                in_pos += 1
                control4 = input_data[in_pos] & 0xFF
                in_pos += 1

                literal_len = control1 & 0x03
                if in_pos + literal_len > input_size:
                    raise ValueError("QFS literal overruns input (long block)")
                if out_pos + literal_len > output_size:
                    raise ValueError("QFS literal overruns output (long block)")

                QFSDecompressor._copy_literal(input_data, in_pos, output, out_pos, literal_len)
                out_pos += literal_len
                in_pos += literal_len

                offset = ((control1 & 0x10) << 12) + (control2 << 8) + control3 + 1
                copy_len = ((control1 & 0x0C) << 6) + control4 + 5
                if out_pos + copy_len > output_size:
                    raise ValueError("QFS copy overruns output (long block)")

                QFSDecompressor._offset_copy(output, out_pos, offset, copy_len)
                out_pos += copy_len

            elif control1 <= 0xFB:
                # Raw block
                literal_len = ((control1 & 0x1F) << 2) + 4
                if in_pos + literal_len > input_size:
                    raise ValueError("QFS literal overruns input (raw block)")
                if out_pos + literal_len > output_size:
                    raise ValueError("QFS literal overruns output (raw block)")

                QFSDecompressor._copy_literal(input_data, in_pos, output, out_pos, literal_len)
                out_pos += literal_len
                in_pos += literal_len

            else:
                # Terminator block
                literal_len = control1 & 0x03
                if in_pos + literal_len > input_size:
                    raise ValueError("QFS literal overruns input (terminator block)")
                if out_pos + literal_len > output_size:
                    raise ValueError("QFS literal overruns output (terminator block)")

                QFSDecompressor._copy_literal(input_data, in_pos, output, out_pos, literal_len)
                out_pos += literal_len
                in_pos += literal_len
                break

        if out_pos != output_size:
            raise ValueError(
                f"QFS decompression wrote {out_pos} bytes but expected {output_size}"
            )

