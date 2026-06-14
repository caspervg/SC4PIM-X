import codecs


def decode_sc4_text(data: bytes) -> str:
    """Decode an SC4 text payload to a string, never raising.

    LTEXT / UVNK / IDK payloads are normally UTF-16-LE. Some legacy or
    corrupt entries are not (odd length, illegal surrogates, 8-bit text).
    Rather than crashing the caller, fall back to Latin-1 -- which maps every
    byte -- so a malformed string is shown as best-effort text instead.
    """
    try:
        return data.decode("utf-16-le")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


def encode_sc4_text(text: str) -> bytes:
    return text.encode("utf-16-le")


def decode_sc4_string_prop(value) -> str:
    """Decode an 8-bit exemplar String property payload to text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("latin-1", errors="replace")
    return str(value)


def decode_unicode_escape(value: str) -> str:
    return codecs.decode(value, "unicode_escape")


def encode_unicode_escape(value: str) -> str:
    return codecs.encode(value, "unicode_escape").decode("ascii")
