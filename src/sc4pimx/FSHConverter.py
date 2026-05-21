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
        - nbrLayers: Number of equal-sized texture layers concatenated in img/alpha
        - trueAlpha: Whether alpha channel is meaningful (not just opaque)
        - img: Raw RGB image data as bytes (nbrLayers layers concatenated)
        - alpha: Raw alpha channel data as bytes (nbrLayers layers concatenated)
        - size: Tuple of (width, height)

    Raises:
        ValueError: If FSH decoding fails

    Note:
        An FSH file's directory may hold several entries. For animated
        textures (ATC) each entry is one full-size frame/plane, indexed by
        the AVP "plane" value. Consumers (S3DTexturesHolder) expect all
        layers to share the same dimensions and to be concatenated here, so
        only the highest-resolution bitmap of each entry is used (the rest
        are mipmaps) and entries whose size differs from the first are
        dropped.
    """
    # Parse the FSH file
    record = FSHReader.parse(buffer)

    if not record.entries:
        raise ValueError("FSH file contains no entries")

    width = height = None
    layers = []
    for entry in record.entries:
        if not entry.bitmaps:
            continue
        # The first bitmap is the highest-resolution image; the rest are mipmaps.
        bitmap = entry.bitmaps[0]
        if width is None:
            width, height = bitmap.width, bitmap.height
        elif (bitmap.width, bitmap.height) != (width, height):
            # Layers must share dimensions to be concatenated; stop here.
            break
        layers.append(FSHReader.convert_to_rgba8(bitmap))

    if not layers:
        raise ValueError("FSH entry contains no bitmaps")

    # Split each layer into RGB and Alpha, concatenated layer after layer.
    pixel_count = width * height
    img_data = bytearray(pixel_count * 3 * len(layers))
    alpha_data = bytearray(pixel_count * len(layers))

    true_alpha = False

    for layer_idx, rgba_data in enumerate(layers):
        rgb_base = pixel_count * 3 * layer_idx
        alpha_base = pixel_count * layer_idx
        for i in range(pixel_count):
            rgba_offset = i * 4
            rgb_offset = rgb_base + i * 3

            img_data[rgb_offset] = rgba_data[rgba_offset]
            img_data[rgb_offset + 1] = rgba_data[rgba_offset + 1]
            img_data[rgb_offset + 2] = rgba_data[rgba_offset + 2]

            alpha = rgba_data[rgba_offset + 3]
            alpha_data[alpha_base + i] = alpha

            # Check if we have real alpha (not just opaque)
            if alpha < 255:
                true_alpha = True

    return (
        len(layers),          # Number of equal-sized texture layers
        true_alpha,           # Has meaningful alpha channel
        bytes(img_data),      # RGB image data (all layers concatenated)
        bytes(alpha_data),    # Alpha data (all layers concatenated)
        (width, height),      # Size
    )
