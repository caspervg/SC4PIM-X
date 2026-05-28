"""Persistent SQLite cache of parsed DBPF entry lists.

Parsing 27k plugin DAT files on every startup is the dominant cost in
:func:`SC4VirtualDat.VirtualDat.load_files_parallel`. This module stores the
parsed ``DatFile.entries`` list (including the eagerly-loaded cohort, exemplar
and LTEXT bodies) keyed by ``(path, mtime, size)`` so warm starts skip parsing
entirely. The cache lives in a single SQLite file under the per-user data
directory so 27k cached files cost one ``open()``, not 27k.

Cache blobs use a tight little-endian binary format rather than ``pickle``:

  File header
    4B  magic 'DBPC'
    1B  format byte (== :data:`CACHE_VERSION`)
    4B  dateLastAccess (uint32, source file mtime as seconds)
    2B  source fileName length (uint16)
    N   source fileName bytes (UTF-8)
    4B  entry count (uint32)

  Per entry
    20B raw directory record (already-packed t,g,i,fileLocation,filesize)
    4B  order (uint32)
    4B  lenContent (int32 -- negative is sentinel from compressed-before-decode)
    4B  body length (uint32, 0 if body not cached)
    M   body bytes (DECOMPRESSED -- see note below)

Note on compression: SC4Entry.read_file() decodes QFS-compressed bodies into
``content`` and leaves ``rawContent`` holding the raw on-disk bytes (compressed
or not). QFS decoding is pure Python, so re-decoding on every cache hit
would dominate warm-start time. The cache therefore stores the *decompressed*
bytes and restores entries with ``compressed=False``; the (rare) re-save path
will write uncompressed entries unless explicitly recompressed via
``WriteADat(..., bRecompress=True)``.

Bump :data:`CACHE_VERSION` on any layout change that would make existing
blobs unsafe to load -- the table query filters by it, so stale rows are
simply re-parsed.
"""

import logging
import os
import sqlite3
import struct
from typing import Optional

from .paths import ensure_user_data_dir

logger = logging.getLogger(__name__)

# Bump on any change to the binary format below or to SC4Entry attributes
# that consumers rely on.
CACHE_VERSION = 2

_MAGIC = b'DBPC'
_HEADER_FMT = struct.Struct('<4sBIH')        # magic, version, dateLastAccess, fn_len
_COUNT_FMT = struct.Struct('<I')             # entry count (after fileName)
_ENTRY_FMT = struct.Struct('<20sIiI')        # buffer, order, lenContent, body_len

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dat_cache (
    path          TEXT PRIMARY KEY,
    mtime_ns      INTEGER NOT NULL,
    size          INTEGER NOT NULL,
    cache_version INTEGER NOT NULL,
    blob          BLOB    NOT NULL
)
"""


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


class DatFileCache:
    """Bulk-loaded read cache + batched writer for parsed ``DatFile.entries``.

    Usage:

        with DatFileCache.open_default() as cache:
            entries = cache.lookup(path)         # None on miss / stale / corrupt
            if entries is None:
                entries = DatFile(path, ...).entries
                cache.queue_store(path, entries)
        # writes flushed on context exit
    """

    def __init__(self, db_path: str, stat_cache: Optional[dict] = None):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        # path -> (mtime_ns, size, blob) snapshot taken once at open()
        self._index: dict = {}
        self._pending: list = []  # (path, mtime_ns, size, blob)
        self._hits = 0
        self._misses = 0
        self._corrupt = 0
        # Optional pre-stat cache: normcased abs path -> (mtime_ns, size).
        # Populated upstream during the directory walk (where the DirEntry
        # already carries the stat result) so lookups don't pay another
        # os.stat -- which is tens of ms per call on OneDrive-shimmed paths.
        self._stat_cache: dict = stat_cache or {}

    @classmethod
    def open_default(cls, stat_cache: Optional[dict] = None) -> "DatFileCache":
        ensure_user_data_dir()
        return cls(str(ensure_user_data_dir() / "dat_cache.sqlite"),
                   stat_cache=stat_cache).open()

    def open(self) -> "DatFileCache":
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        # WAL keeps readers fast; durability isn't critical -- a torn cache
        # just re-parses on the next start.
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.DatabaseError:
            logger.warning("Could not set SQLite pragmas on %s", self.db_path)
        self._conn.execute(_SCHEMA)
        self._load_index()
        return self

    def _load_index(self) -> None:
        assert self._conn is not None
        cur = self._conn.execute(
            "SELECT path, mtime_ns, size, blob FROM dat_cache "
            "WHERE cache_version = ?",
            (CACHE_VERSION,),
        )
        self._index = {row[0]: (row[1], row[2], row[3]) for row in cur}
        logger.debug("DBPF parse cache loaded: %d entries from %s",
                     len(self._index), self.db_path)

    def lookup(self, path: str):
        """Return cached ``entries`` for *path*, or None on miss/stale/corrupt.

        Thread-safe: only reads from the pre-loaded in-memory snapshot and
        the filesystem; no SQLite calls.
        """
        key = _norm(path)
        cached = self._index.get(key)
        if cached is None:
            self._misses += 1
            return None
        mtime_ns, size, blob = cached
        pre = self._stat_cache.get(key)
        if pre is not None:
            cur_mtime_ns, cur_size = pre
        else:
            try:
                st = os.stat(path)
            except OSError:
                self._misses += 1
                return None
            cur_mtime_ns, cur_size = st.st_mtime_ns, st.st_size
        if cur_mtime_ns != mtime_ns or cur_size != size:
            self._misses += 1
            return None
        try:
            entries = deserialize_entries(blob)
        except Exception:
            # Stale layout despite matching CACHE_VERSION, or genuinely
            # corrupt -- treat as a miss and let the caller re-parse.
            self._corrupt += 1
            return None
        self._hits += 1
        return entries

    def queue_store(self, path: str, blob: bytes) -> None:
        """Queue a pre-serialized *blob* for write on the next :meth:`flush`.

        The caller must serialize ``entries`` via :func:`serialize_entries`
        *before* merging into ``VirtualDat`` -- the merge attaches a
        ``virtual_dat`` back-reference and other runtime state we'd rather
        not snapshot.

        Thread-safe under the GIL for append; flush happens single-threaded.
        """
        key = _norm(path)
        pre = self._stat_cache.get(key)
        if pre is not None:
            mtime_ns, size = pre
        else:
            try:
                st = os.stat(path)
            except OSError:
                return
            mtime_ns, size = st.st_mtime_ns, st.st_size
        self._pending.append((key, mtime_ns, size, blob))

    def flush(self) -> None:
        if not self._pending or self._conn is None:
            return
        rows = self._pending
        self._pending = []
        try:
            with self._conn:
                self._conn.executemany(
                    "INSERT OR REPLACE INTO dat_cache "
                    "(path, mtime_ns, size, cache_version, blob) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [(p, m, s, CACHE_VERSION, b) for (p, m, s, b) in rows],
                )
        except sqlite3.DatabaseError:
            logger.exception("Failed to flush %d cache rows", len(rows))

    def stats(self) -> tuple:
        return (self._hits, self._misses, self._corrupt)

    def close(self) -> None:
        try:
            self.flush()
        finally:
            if self._conn is not None:
                try:
                    self._conn.close()
                except sqlite3.DatabaseError:
                    pass
                self._conn = None

    def __enter__(self) -> "DatFileCache":
        if self._conn is None:
            self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def serialize_entries(entries) -> Optional[bytes]:
    """Pack a freshly-parsed ``DatFile.entries`` list into the cache format.

    Returns ``None`` (and logs a warning) on any failure. Must be called
    *before* the entries are merged into ``VirtualDat`` (the merge attaches a
    ``virtual_dat`` back-reference that we don't want to serialize anyway).
    """
    if not entries:
        return None
    try:
        first = entries[0]
        file_name = first.fileName
        date_last_access = int(getattr(first, 'dateUpdated', 0)) & 0xFFFFFFFF
        fn_bytes = file_name.encode('utf-8')
        if len(fn_bytes) > 0xFFFF:
            logger.warning("Source filename too long to cache: %s", file_name)
            return None
        parts = [_HEADER_FMT.pack(_MAGIC, CACHE_VERSION,
                                  date_last_access, len(fn_bytes)),
                 fn_bytes,
                 _COUNT_FMT.pack(len(entries))]
        for e in entries:
            # ``content`` is the decoded form set by read_file; for non-eagerly-
            # read entries it's absent and we cache no body (lookup re-reads
            # from the source DAT on first access via SC4Entry.read_file).
            body = getattr(e, 'content', None)
            if body is None:
                body_bytes = b''
            elif isinstance(body, bytes):
                body_bytes = body
            else:
                body_bytes = bytes(body)
            len_content = e.lenContent if e.lenContent is not None else -1
            # Clamp to int32 range; lenContent can be -1 sentinel.
            if len_content < -0x80000000 or len_content > 0x7FFFFFFF:
                len_content = len(body_bytes)
            parts.append(_ENTRY_FMT.pack(e.buffer, e.order, len_content,
                                         len(body_bytes)))
            if body_bytes:
                parts.append(body_bytes)
        return b''.join(parts)
    except Exception:
        logger.warning("Could not serialize DatFile entries", exc_info=True)
        return None


def deserialize_entries(blob: bytes) -> list:
    """Reconstruct an entry list from the cache blob.

    Constructs ``SC4Entry`` objects via ``__new__`` (bypassing ``__init__``)
    and populates their attributes directly. The returned list is shaped
    exactly as a fresh ``DatFile.entries`` would be after ``ReadEntries``,
    except cached bodies are pre-decompressed (``compressed=False``).
    """
    # Local import: dat_cache is imported by SC4VirtualDat at module load,
    # but SC4DatTools doesn't import dat_cache. Importing SC4Entry at module
    # top level would be cleaner but currently risks reload-order issues.
    from .SC4DatTools import SC4Entry
    mv = memoryview(blob)
    magic, version, date_last_access, fn_len = _HEADER_FMT.unpack_from(mv, 0)
    if magic != _MAGIC or version != CACHE_VERSION:
        raise ValueError(f"bad cache header magic={magic!r} version={version}")
    pos = _HEADER_FMT.size
    file_name = bytes(mv[pos:pos + fn_len]).decode('utf-8')
    pos += fn_len
    (count,) = _COUNT_FMT.unpack_from(mv, pos)
    pos += _COUNT_FMT.size

    entries = [None] * count
    entry_size = _ENTRY_FMT.size
    new_entry = SC4Entry.__new__
    for i in range(count):
        buffer, order, len_content, body_len = _ENTRY_FMT.unpack_from(mv, pos)
        pos += entry_size
        if body_len:
            body = bytes(mv[pos:pos + body_len])
            pos += body_len
        else:
            body = None
        # Parse the 5 uint32s out of the 20-byte directory record.
        t, g, i_id, file_location, file_size = struct.unpack_from('<IIIII',
                                                                  buffer, 0)
        e = new_entry(SC4Entry)
        e.buffer = buffer
        e.fileName = file_name
        e.order = order
        e.TGI = {'t': t, 'g': g, 'i': i_id}
        e.tgi = (t, g, i_id)
        e.fileLocation = file_location
        e.initialFileLocation = file_location
        e.filesize = file_size
        e.lenContent = len_content
        # Bodies were stored decompressed; mark accordingly so consumers and
        # read_file() see a coherent state. read_file() returns early when
        # rawContent is not None, so cached entries skip disk re-reads.
        e.compressed = False
        e.rawContent = body
        e.content = body
        e.dateCreated = date_last_access
        e.dateUpdated = date_last_access
        entries[i] = e
    return entries


def clear_cache() -> None:
    """Delete the on-disk cache file (used by a future 'Clear cache' button)."""
    path = ensure_user_data_dir() / "dat_cache.sqlite"
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(str(path) + suffix)
        except FileNotFoundError:
            pass
        except OSError:
            logger.warning("Could not remove cache file %s%s", path, suffix,
                           exc_info=True)
