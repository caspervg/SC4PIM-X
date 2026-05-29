"""QFS / EA RefPack compression for SimCity 4 DBPF entries.

This module is a clean-room implementation from ``QFS_SPEC.md``.  The public
boundary is deliberately exception-safe: malformed streams or encoder failures
return ``None``.
"""

from __future__ import annotations

import logging
from array import array
from typing import Callable

logger = logging.getLogger(__name__)

# Optional native accelerator (sc4pimx._qfs, built by hatch_build.py on Windows
# when an MSVC toolchain is available).  It mirrors the pure-Python codec below
# byte-for-byte; when absent we transparently fall back to it.  Bind the two
# entry points to typed callables so the rest of the module is backend-agnostic.
_Codec = Callable[[bytes], "bytes | None"]
_native_decode: _Codec | None
_native_encode: _Codec | None
try:
    from . import _qfs  # type: ignore[attr-defined]

    _native_decode = _qfs.decode
    _native_encode = _qfs.encode
except ImportError:
    _native_decode = None
    _native_encode = None

# Log the active backend exactly once, at import, rather than on every call.
if _native_decode is not None:
    logger.info("QFS: native accelerator enabled (sc4pimx._qfs).")
else:
    logger.debug("QFS: native accelerator unavailable; using pure-Python codec.")

_MAGIC0 = 0x10
_MAGIC1 = 0xFB
_MAGIC = (_MAGIC0 << 8) | _MAGIC1
_MAX_SIZE = 0xFFFFFF
_MAX_OFFSET = 131072
_MAX_COPY = 1028
_MIN_MATCH = 3

_HASH_BITS = 16
_HASH_SIZE = 1 << _HASH_BITS
_HASH_MASK = _HASH_SIZE - 1
_MAX_CHAIN = 96
_NICE_MATCH = 256
_MATCH_INSERT_LIMIT = 64


def is_qfs_compressed(buffer: bytes) -> bool:
    """Return True when *buffer* starts with a QFS magic header."""

    return len(buffer) >= 2 and (((buffer[0] & 0xFE) << 8) | buffer[1]) == _MAGIC


def decode(buffer: bytes) -> bytes | None:
    """Decompress a QFS / RefPack stream, returning ``None`` on invalid input."""

    try:
        if _native_decode is not None:
            return _native_decode(buffer)
        return _decode(buffer)
    except Exception:
        return None


def encode(buffer: bytes) -> bytes | None:
    """Compress *buffer* as a QFS / RefPack stream.

    The result intentionally does not include the DBPF container's 4-byte
    compressed-size prefix; callers add that wrapper themselves.
    """

    try:
        if _native_encode is not None:
            return _native_encode(buffer)
        return _encode(buffer)
    except Exception:
        return None


def _decode(buffer: bytes) -> bytes | None:
    # Decode is a forced-sequential state machine and already O(output size):
    # there is no algorithm/structure to improve, only per-packet constant
    # factors.  Index through ``bytes`` (faster element access in CPython than a
    # ``memoryview``), inline the back-copy, and keep the hot names local so the
    # loop stays tight -- this runs on the load path across thousands of entries.
    data = bytes(buffer)
    n = len(data)
    if n < 5 or (((data[0] & 0xFE) << 8) | data[1]) != _MAGIC:
        return None

    size = (data[2] << 16) | (data[3] << 8) | data[4]
    p = 8 if data[0] & 0x01 else 5
    if p > n:
        return None

    out = bytearray(size)
    out_pos = 0

    while True:
        if p >= n:
            return None

        c0 = data[p]
        p += 1

        if c0 >= 0xFC:
            num_literal = c0 & 0x03
            if p + num_literal > n or out_pos + num_literal > size:
                return None
            if num_literal:
                out[out_pos : out_pos + num_literal] = data[p : p + num_literal]
                out_pos += num_literal
            return bytes(out) if out_pos == size else None

        if c0 <= 0x7F:
            if p >= n:
                return None
            c1 = data[p]
            p += 1
            num_literal = c0 & 0x03
            copy_len = ((c0 >> 2) & 0x07) + 3
            copy_offset = ((c0 & 0x60) << 3) + c1 + 1
        elif c0 <= 0xBF:
            if p + 1 >= n:
                return None
            c1 = data[p]
            c2 = data[p + 1]
            p += 2
            num_literal = (c1 >> 6) & 0x03
            copy_len = (c0 & 0x3F) + 4
            copy_offset = ((c1 & 0x3F) << 8) + c2 + 1
        elif c0 <= 0xDF:
            if p + 2 >= n:
                return None
            c1 = data[p]
            c2 = data[p + 1]
            c3 = data[p + 2]
            p += 3
            num_literal = c0 & 0x03
            copy_len = ((c0 & 0x0C) << 6) + c3 + 5
            copy_offset = ((c0 & 0x10) << 12) + (c1 << 8) + c2 + 1
        else:
            num_literal = ((c0 & 0x1F) << 2) + 4
            if p + num_literal > n or out_pos + num_literal > size:
                return None
            out[out_pos : out_pos + num_literal] = data[p : p + num_literal]
            p += num_literal
            out_pos += num_literal
            continue

        if p + num_literal > n:
            return None
        packet_len = num_literal + copy_len
        if copy_offset > out_pos + num_literal or out_pos + packet_len > size:
            return None

        if num_literal:
            out[out_pos : out_pos + num_literal] = data[p : p + num_literal]
            p += num_literal
            out_pos += num_literal

        # Back-copy, inlined.  Non-overlapping copies and the single-byte run
        # (offset == 1) are the common cases; the general overlap falls back to
        # tiling the source pattern in C rather than byte-by-byte.
        src = out_pos - copy_offset
        if copy_offset >= copy_len:
            out[out_pos : out_pos + copy_len] = out[src : src + copy_len]
        elif copy_offset == 1:
            out[out_pos : out_pos + copy_len] = bytes((out[src],)) * copy_len
        else:
            pattern = bytes(out[src:out_pos])
            out[out_pos : out_pos + copy_len] = (pattern * ((copy_len + copy_offset - 1) // copy_offset))[:copy_len]
        out_pos += copy_len


def _encode(buffer: bytes) -> bytes | None:
    n = len(buffer)
    if n > _MAX_SIZE:
        return None

    data = bytes(buffer)
    out = bytearray((_MAGIC0, _MAGIC1, (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF))

    if n == 0:
        out.append(0xFC)
        return bytes(out)

    prev = array("i", [-1]) * n
    head = array("i", [-1]) * _HASH_SIZE
    last_hash_pos = n - _MIN_MATCH

    # The match-finder and hash-chain bookkeeping are inlined into this single
    # loop on purpose: this runs on the file-save path over multi-KB..MB buffers
    # and per-position Python function-call overhead (one _find_match plus
    # several helper calls per byte) dominated the profile.  Hoist everything
    # the loop touches into locals so each iteration stays in the fast path.
    hash_mask = _HASH_MASK
    max_offset = _MAX_OFFSET
    max_copy = _MAX_COPY
    max_chain = _MAX_CHAIN
    nice_match = _NICE_MATCH
    insert_limit = _MATCH_INSERT_LIMIT

    pos = 0
    literal_start = 0

    while pos <= last_hash_pos:
        b0 = data[pos]
        b1 = data[pos + 1]
        b2 = data[pos + 2]
        h = ((b0 << 8) ^ (b1 << 4) ^ b2) & hash_mask
        candidate = head[h]

        best_len = 0
        best_offset = 0

        if candidate >= 0:
            max_len = n - pos
            if max_len > max_copy:
                max_len = max_copy
            if max_len >= _MIN_MATCH:
                min_candidate = pos - max_offset
                if min_candidate < 0:
                    min_candidate = 0
                best_score = 0
                steps = max_chain

                while candidate >= min_candidate and steps:
                    steps -= 1
                    if data[candidate] == b0 and data[candidate + 1] == b1 and data[candidate + 2] == b2:
                        offset = pos - candidate
                        # _minimum_match_length, inlined (offset <= max_offset here).
                        if offset <= 1024:
                            min_len = 3
                        elif offset <= 16384:
                            min_len = 4
                        else:
                            min_len = 5
                        if max_len >= min_len:
                            # _match_length, inlined.
                            length = _MIN_MATCH
                            while length < max_len and data[candidate + length] == data[pos + length]:
                                length += 1
                            if length >= min_len:
                                # _packet_control_size, inlined.
                                if length <= 10 and offset <= 1024:
                                    score = length - 2
                                elif length <= 67 and offset <= 16384:
                                    score = length - 3
                                else:
                                    score = length - 4
                                if score > best_score or (score == best_score and length > best_len):
                                    best_len = length
                                    best_offset = offset
                                    best_score = score
                                    if length == max_len or length >= nice_match:
                                        break
                    candidate = prev[candidate]

        if best_len:
            literal_start = _emit_pending_literals(out, data, literal_start, pos)
            literal_count = pos - literal_start
            _emit_copy_packet(out, data, literal_start, literal_count, best_len, best_offset)

            prev[pos] = head[h]
            head[h] = pos
            insert_end = pos + best_len
            if insert_end > last_hash_pos + 1:
                insert_end = last_hash_pos + 1
            if insert_end > pos + 1:
                insert_start = insert_end - insert_limit
                if insert_start < pos + 1:
                    insert_start = pos + 1
                for insert_pos in range(insert_start, insert_end):
                    hh = ((data[insert_pos] << 8) ^ (data[insert_pos + 1] << 4) ^ data[insert_pos + 2]) & hash_mask
                    prev[insert_pos] = head[hh]
                    head[hh] = insert_pos

            pos += best_len
            literal_start = pos
        else:
            prev[pos] = head[h]
            head[h] = pos
            pos += 1

    _emit_final_literals(out, data, literal_start, n)
    return bytes(out)


def _emit_pending_literals(out: bytearray, data: bytes, start: int, end: int) -> int:
    literal_len = end - start
    attached = literal_len & 0x03
    flush_end = end - attached
    _emit_literal_runs(out, data, start, flush_end)
    return flush_end


def _emit_final_literals(out: bytearray, data: bytes, start: int, end: int) -> None:
    literal_len = end - start
    terminal = literal_len & 0x03
    flush_end = end - terminal
    _emit_literal_runs(out, data, start, flush_end)
    out.append(0xFC | terminal)
    if terminal:
        out.extend(data[flush_end:end])


def _emit_literal_runs(out: bytearray, data: bytes, start: int, end: int) -> None:
    pos = start
    while pos < end:
        chunk = min(112, end - pos)
        out.append(0xE0 | ((chunk - 4) >> 2))
        out.extend(data[pos : pos + chunk])
        pos += chunk


def _emit_copy_packet(
    out: bytearray,
    data: bytes,
    literal_start: int,
    literal_count: int,
    copy_len: int,
    copy_offset: int,
) -> None:
    offset = copy_offset - 1

    if copy_offset <= 1024 and copy_len <= 10:
        out.append(((offset >> 8) << 5) | ((copy_len - 3) << 2) | literal_count)
        out.append(offset & 0xFF)
    elif copy_offset <= 16384 and copy_len <= 67:
        out.append(0x80 | (copy_len - 4))
        out.append((literal_count << 6) | ((offset >> 8) & 0x3F))
        out.append(offset & 0xFF)
    else:
        length = copy_len - 5
        out.append(0xC0 | literal_count | ((length >> 8) << 2) | ((offset >> 16) << 4))
        out.append((offset >> 8) & 0xFF)
        out.append(offset & 0xFF)
        out.append(length & 0xFF)

    if literal_count:
        out.extend(data[literal_start : literal_start + literal_count])
