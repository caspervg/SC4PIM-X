from .QFSDecompressor import QFSDecompressor


def decode(buffer: bytes) -> bytes | None:
    try:
        return QFSDecompressor.decompress(buffer)
    except ValueError:
        return None


def encode(buffer: bytes) -> bytes | None:
    return None
