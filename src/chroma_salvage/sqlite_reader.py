"""Read ``chroma.sqlite3`` without chromadb and without ever writing to the folder.

The database is opened with ``mode=ro``. If it is in SQLite WAL journal mode (or has a
``-wal`` file next to it) even a read-only open would create ``-shm``/``-wal`` files in
the source folder, so in that case the files are copied to a temporary folder first.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import struct
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .errors import InputError, UnsupportedFormatError

DB_NAME = "chroma.sqlite3"
OPERATIONS = {0: "ADD", 1: "UPDATE", 2: "UPSERT", 3: "DELETE"}
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# band thresholds, measured with chromadb 0.4.24, 0.5.23, 0.6.3 and 1.5.9
# (sysdb, metadb, embeddings_queue) maxima: 4/3/1, 9/4/2, 9/4/2, 10/6/2
KNOWN_MAX = {"sysdb": 10, "metadb": 6, "embeddings_queue": 2}


@dataclass
class CollectionInfo:
    id: str
    name: str
    dimension: int | None
    space: str
    space_source: str  # "metadata" | "schema_str" | "default"
    vector_segment: str | None
    metadata_segment: str | None
    topic: str | None = None


@dataclass
class WalRow:
    seq_id: int
    operation: str
    id: str
    vector: tuple[float, ...] | None
    metadata: dict[str, Any] | None


@dataclass
class Record:
    document: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


class SourceDB:
    """A read-only view of one Chroma persistent folder."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._tmp: tempfile.TemporaryDirectory[str] | None = None
        self.db_path = root / DB_NAME
        self.conn = self._open()
        self._columns: dict[str, list[str]] = {}

    # -- lifecycle ---------------------------------------------------------
    def _open(self) -> sqlite3.Connection:
        db_path = self.db_path
        wal_path = db_path.with_name(DB_NAME + "-wal")
        if _is_wal_mode(db_path) or wal_path.exists():
            self._tmp = tempfile.TemporaryDirectory(prefix="chroma-salvage-")
            copy = Path(self._tmp.name) / DB_NAME
            shutil.copyfile(db_path, copy)
            if wal_path.exists():
                shutil.copyfile(wal_path, copy.with_name(DB_NAME + "-wal"))
            return _connect(f"{copy.as_uri()}?mode=rw", copy)
        return _connect(f"{db_path.resolve().as_uri()}?mode=ro", db_path)

    def close(self) -> None:
        self.conn.close()
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None

    def __enter__(self) -> "SourceDB":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- helpers -----------------------------------------------------------
    def columns(self, table: str) -> list[str]:
        if table not in self._columns:
            self._columns[table] = [r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")]
        return self._columns[table]

    def has_table(self, table: str) -> bool:
        return bool(self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())

    def sha256(self) -> str:
        digest = hashlib.sha256()
        with open(self.db_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    # -- version band ------------------------------------------------------
    def migrations(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT dir, MAX(version) FROM migrations GROUP BY dir").fetchall()
        found = {d: v for d, v in rows}
        return {k: int(found.get(k, 0)) for k in ("sysdb", "metadb", "embeddings_queue")}

    def band(self) -> str:
        m = self.migrations()
        if any(m[k] > KNOWN_MAX[k] for k in KNOWN_MAX):
            return "unknown-newer"
        if m["sysdb"] >= 10 or m["metadb"] >= 5:
            return "1.x"
        if m["sysdb"] >= 5:
            return "0.5.x-0.6.x"
        return "0.4.x"

    # -- collections -------------------------------------------------------
    def collections(self) -> list[CollectionInfo]:
        cols = self.columns("collections")
        want = [c for c in ("id", "name", "dimension", "topic", "schema_str") if c in cols]
        rows = self.conn.execute(f"SELECT {', '.join(want)} FROM collections ORDER BY name").fetchall()
        result = []
        for row in rows:
            rec = dict(zip(want, row))
            segments = {
                scope: sid for sid, scope in self.conn.execute(
                    "SELECT id, scope FROM segments WHERE collection=?", (rec["id"],))
            }
            space, source = self._space(rec["id"], rec.get("schema_str"))
            result.append(CollectionInfo(
                id=rec["id"], name=rec["name"], dimension=rec.get("dimension"), space=space,
                space_source=source, vector_segment=segments.get("VECTOR"),
                metadata_segment=segments.get("METADATA"), topic=rec.get("topic")))
        return result

    def _space(self, collection_id: str, schema_str: str | None) -> tuple[str, str]:
        if self.has_table("collection_metadata"):
            value_col = "str_value" if "str_value" in self.columns("collection_metadata") else "string_value"
            row = self.conn.execute(
                f"SELECT {value_col} FROM collection_metadata WHERE collection_id=? AND key='hnsw:space'",
                (collection_id,)).fetchone()
            if row and row[0]:
                return row[0], "metadata"
        if schema_str:
            try:
                schema = json.loads(schema_str)
                space = schema["keys"]["#embedding"]["float_list"]["vector_index"]["config"]["space"]
                if space:
                    return space, "schema_str"
            except (ValueError, KeyError, TypeError):
                pass
        return "l2", "default"  # Chroma's documented default

    def watermark(self, segment_id: str | None) -> int | None:
        """Last WAL ``seq_id`` the segment has applied (BLOB big-endian in 0.x, INTEGER in 1.x)."""
        if segment_id is None or not self.has_table("max_seq_id"):
            return None
        row = self.conn.execute("SELECT seq_id FROM max_seq_id WHERE segment_id=?", (segment_id,)).fetchone()
        if row is None or row[0] is None:
            return None
        value = row[0]
        return int.from_bytes(value, "big") if isinstance(value, (bytes, bytearray)) else int(value)

    def segment_ids(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT id FROM segments")}

    def orphan_segment_dirs(self) -> list[str]:
        known = self.segment_ids()
        return sorted(
            p.name for p in self.root.iterdir()
            if p.is_dir() and UUID_RE.match(p.name) and p.name not in known)

    # -- write-ahead log ---------------------------------------------------
    def wal_rows(self, collection: CollectionInfo, after: int) -> Iterator[WalRow]:
        if not self.has_table("embeddings_queue"):
            return
        sql = "SELECT seq_id, operation, id, vector, encoding, metadata FROM embeddings_queue WHERE seq_id > ?"
        args: list[Any] = [after]
        if "topic" in self.columns("embeddings_queue"):
            sql += " AND topic LIKE ?"
            args.append("%" + collection.id)
        sql += " ORDER BY seq_id"
        for seq, op, eid, blob, encoding, meta in self.conn.execute(sql, args):
            vector = None
            if blob is not None:
                if encoding not in (None, "FLOAT32"):
                    raise UnsupportedFormatError("err.wal_encoding", encoding=encoding, seq=seq)
                if len(blob) % 4:
                    raise UnsupportedFormatError("err.wal_vector_size", seq=seq, size=len(blob))
                vector = struct.unpack(f"<{len(blob) // 4}f", blob)
            metadata = json.loads(meta) if meta else None
            yield WalRow(seq, OPERATIONS.get(op, f"OP{op}"), eid, vector, metadata)

    # -- documents and metadata -------------------------------------------
    def records(self, segment_id: str | None) -> dict[str, Record]:
        """Documents and metadata stored in the SQLite METADATA segment."""
        if segment_id is None:
            return {}
        rows = self.conn.execute(
            "SELECT id, embedding_id FROM embeddings WHERE segment_id=?", (segment_id,)).fetchall()
        by_row = {rid: eid for rid, eid in rows}
        records = {eid: Record(None) for eid in by_row.values()}
        value_cols = [c for c in ("string_value", "int_value", "float_value", "bool_value")
                      if c in self.columns("embedding_metadata")]
        query = (f"SELECT m.id, m.key, {', '.join('m.' + c for c in value_cols)} FROM embedding_metadata m "
                 "JOIN embeddings e ON e.id = m.id WHERE e.segment_id=?")
        for row in self.conn.execute(query, (segment_id,)):
            rid, key = row[0], row[1]
            value = _pick_value(dict(zip(value_cols, row[2:])))
            rec = records[by_row[rid]]
            if key == "chroma:document":
                rec.document = value
            else:
                rec.metadata[key] = value
        if self.has_table("embedding_metadata_array"):
            array_cols = [c for c in value_cols if c in self.columns("embedding_metadata_array")]
            query = (f"SELECT a.id, a.key, {', '.join('a.' + c for c in array_cols)} "
                     "FROM embedding_metadata_array a JOIN embeddings e ON e.id = a.id "
                     "WHERE e.segment_id=? ORDER BY a.rowid")
            for row in self.conn.execute(query, (segment_id,)):
                value = _pick_value(dict(zip(array_cols, row[2:])))
                records[by_row[row[0]]].metadata.setdefault(row[1], []).append(value)
        return records


def _pick_value(values: dict[str, Any]) -> Any:
    """Exactly one value column is set per row; booleans live in ``bool_value``."""
    if values.get("bool_value") is not None:
        return bool(values["bool_value"])
    for col in ("int_value", "float_value", "string_value"):
        if values.get(col) is not None:
            return values[col]
    return None


def _is_wal_mode(db_path: Path) -> bool:
    """SQLite file header bytes 18/19 are 2 when the database uses WAL journal mode."""
    try:
        with open(db_path, "rb") as fh:
            head = fh.read(20)
    except OSError:
        return False
    return len(head) == 20 and head[18] == 2 and head[19] == 2


def _connect(uri: str, path: Path) -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
    except sqlite3.DatabaseError as exc:
        raise InputError("err.not_sqlite", path=str(path), detail=str(exc)) from exc
    return conn


def open_source(path: str | Path) -> SourceDB:
    """Open ``path`` (a Chroma persist directory) read-only; raise :class:`InputError` if unusable."""
    root = Path(path)
    if not root.exists():
        raise InputError("err.path_missing", path=str(root))
    if not root.is_dir():
        raise InputError("err.not_a_directory", path=str(root))
    if not (root / DB_NAME).is_file():
        raise InputError("err.no_sqlite", path=str(root), name=DB_NAME)
    source = SourceDB(root)
    if not source.has_table("migrations"):
        source.close()
        raise InputError("err.no_migrations", path=str(root / DB_NAME))
    return source
