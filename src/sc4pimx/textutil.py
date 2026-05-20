import codecs


def decode_sc4_text(data: bytes) -> str:
    return data.decode("utf-16-le")


def encode_sc4_text(text: str) -> bytes:
    return text.encode("utf-16-le")


def decode_unicode_escape(value: str) -> str:
    return codecs.decode(value, "unicode_escape")


def encode_unicode_escape(value: str) -> str:
    return codecs.encode(value, "unicode_escape").decode("ascii")
