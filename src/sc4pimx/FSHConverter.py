"""FSH Converter for SC4PIM.

This module provides FSH texture file decoding functionality.
Pure Python implementation replacing the original FSHConverter.pyd binary extension.
"""

from typing import Tuple

from .FSHReader import FSHReader


def decodeFSH(buffer: bytes) -> Tuple[int, bool, bytes, bytes, Tuple[int, int]]:
    """Decode an FSH texture file.

    This function maintains API compatibility with the original FSHConverter.pyd module.

    Args:
        buffer: Raw FSH file data (may be QFS compressed)

    Returns:
        Tuple of:
        - nbrLayers: Number of mipmap layers
        - trueAlpha: Whether alpha channel is meaningful (not just opaque)
        - img: Raw RGB image data as bytes
        - alpha: Raw alpha channel data as bytes
        - size: Tuple of (width, height)

    Raises:
        ValueError: If FSH decoding fails
    """
    # Parse the FSH file
    record = FSHReader.parse(buffer)

    if not record.entries:
        raise ValueError("FSH file contains no entries")

    # Use the first entry
    entry = record.entries[0]

    if not entry.bitmaps:
        raise ValueError("FSH entry contains no bitmaps")

    # Use the first (highest resolution) bitmap
    bitmap = entry.bitmaps[0]

    # Convert to RGBA8
    rgba_data = FSHReader.convert_to_rgba8(bitmap)

    # Split into RGB and Alpha
    pixel_count = bitmap.width * bitmap.height
    img_data = bytearray(pixel_count * 3)
    alpha_data = bytearray(pixel_count)

    true_alpha = False

    for i in range(pixel_count):
        rgba_offset = i * 4
        rgb_offset = i * 3

        img_data[rgb_offset] = rgba_data[rgba_offset]
        img_data[rgb_offset + 1] = rgba_data[rgba_offset + 1]
        img_data[rgb_offset + 2] = rgba_data[rgba_offset + 2]

        alpha = rgba_data[rgba_offset + 3]
        alpha_data[i] = alpha

        # Check if we have real alpha (not just opaque)
        if alpha < 255:
            true_alpha = True

    return (
        len(entry.bitmaps),  # Number of layers/mipmaps
        true_alpha,           # Has meaningful alpha channel
        bytes(img_data),      # RGB image data
        bytes(alpha_data),    # Alpha data
        (bitmap.width, bitmap.height),  # Size
    )
