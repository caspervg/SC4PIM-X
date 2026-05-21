"""FSH Converter for SC4PIM.

This module provides FSH texture file decoding functionality.
Pure Python implementation replacing the original FSHConverter.pyd binary extension.
"""

from typing import Tuple

import numpy as np

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
    # Vectorised with numpy (the old per-pixel loop cost ~18 ms per
    # 256x256 layer); concatenating in layer order preserves the expected
    # "all layers, pixel-major RGB" / "all layers alpha" byte layout.
    stacked = np.concatenate(
        [np.frombuffer(layer, dtype=np.uint8).reshape(-1, 4) for layer in layers],
        axis=0,
    )
    img_data = np.ascontiguousarray(stacked[:, :3]).tobytes()
    alpha_arr = stacked[:, 3]
    alpha_data = alpha_arr.tobytes()
    true_alpha = bool(np.any(alpha_arr < 255))

    return (
        len(layers),          # Number of equal-sized texture layers
        true_alpha,           # Has meaningful alpha channel
        img_data,             # RGB image data (all layers concatenated)
        alpha_data,           # Alpha data (all layers concatenated)
        (width, height),      # Size
    )
