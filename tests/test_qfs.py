import random

import pytest

from sc4pimx import QFS


def qfs_header(size: int, extended: bool = False) -> bytearray:
    first = 0x11 if extended else 0x10
    header = bytearray((first, 0xFB, (size >> 16) & 0xFF, (size >> 8) & 0xFF, size & 0xFF))
    if extended:
        header.extend(b"\x00\x00\x00")
    return header


def test_decode_manual_packet_classes():
    stream = qfs_header(140)
    stream.extend([0xEF])
    stream.extend(b"A" * 64)
    stream.extend([0x1F, 0x42])
    stream.extend(b"BCD")
    stream.extend([0x80, 0x00, 0x0C])
    stream.extend([0xC0, 0x00, 0x50, 0x00])
    stream.extend([0xFC])

    expected = b"A" * 64 + b"BCD" + b"A" * 10 + b"BCDA" + b"A" * 5
    assert len(expected) == 86

    stream[2] = 0
    stream[3] = 0
    stream[4] = len(expected)
    assert QFS.decode(bytes(stream)) == expected


def test_decode_extended_header():
    stream = qfs_header(3, extended=True)
    stream.extend([0xFF])
    stream.extend(b"SC4")

    assert QFS.decode(bytes(stream)) == b"SC4"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"x", id="one-byte"),
        pytest.param(b"xy", id="two-bytes"),
        pytest.param(b"xyz", id="three-bytes"),
        pytest.param(b"wxyz", id="four-bytes"),
        pytest.param(b"A" * 2048, id="identical"),
        pytest.param(b"SC4PIM-X" * 4096, id="text-like"),
        pytest.param(bytes(range(256)) * 128, id="periodic-bytes"),
        pytest.param((b"lotConfigProperty" + bytes(range(16))) * 2048, id="structured"),
    ],
)
def test_encode_round_trips_representative_payloads(payload):
    encoded = QFS.encode(payload)

    assert encoded is not None
    assert encoded[:2] == b"\x10\xfb"
    assert (((encoded[0] & 0xFE) << 8) | encoded[1]) == 0x10FB
    assert (encoded[2] << 16) | (encoded[3] << 8) | encoded[4] == len(payload)
    assert QFS.decode(encoded) == payload


def test_encode_round_trips_boundaries_and_large_payloads():
    payloads = [
        bytes((i * 17) & 0xFF for i in range(1023)),
        bytes((i * 17) & 0xFF for i in range(1024)),
        bytes((i * 17) & 0xFF for i in range(1025)),
        (b"0123456789ABCDEF" * 1025)[:16383],
        (b"0123456789ABCDEF" * 1025)[:16384],
        (b"0123456789ABCDEF" * 1025)[:16385],
        (b"long-window-" * 12000)[:131071],
        (b"long-window-" * 12000)[:131072],
        (b"long-window-" * 12000)[:131073],
        (b"multi-window:" + bytes(range(64))) * 16000,
    ]

    for payload in payloads:
        encoded = QFS.encode(payload)
        assert encoded is not None
        assert QFS.decode(encoded) == payload


def test_encode_compresses_repetitive_payload():
    payload = (b"ABCDEFGH" * 8192) + (b"Z" * 4096)
    encoded = QFS.encode(payload)

    assert encoded is not None
    assert QFS.decode(encoded) == payload
    assert len(encoded) < len(payload) // 8


def test_seeded_random_round_trips():
    rng = random.Random(0x5C4)

    for size in [0, 1, 2, 3, 4, 5, 31, 111, 112, 113, 1024, 4096, 32768]:
        payload = bytes(rng.randrange(256) for _ in range(size))
        encoded = QFS.encode(payload)
        assert encoded is not None
        assert QFS.decode(encoded) == payload


def test_seeded_random_fuzz_round_trips():
    rng = random.Random(12345)

    for _ in range(200):
        size = rng.randrange(0, 4096)
        payload = bytes(rng.randrange(256) for _ in range(size))
        encoded = QFS.encode(payload)
        assert encoded is not None
        assert QFS.decode(encoded) == payload


@pytest.mark.parametrize(
    "stream",
    [
        b"",
        b"\x10",
        b"\x10\xfa\x00\x00\x00\xfc",
        b"\x10\xfb\x00\x00\x01",
        b"\x10\xfb\x00\x00\x04\xe0abc",
        b"\x10\xfb\x00\x00\x04\x00\x00\xfc",
        b"\x10\xfb\x00\x00\x04\xfc",
        b"\x11\xfb\x00\x00\x00\x00\x00",
    ],
)
def test_malformed_streams_return_none(stream):
    assert QFS.decode(stream) is None


def test_oversized_input_returns_none():
    assert QFS.encode(b"\x00" * 0x1000000) is None
