"""Write collections as version-neutral JSONL plus a ``manifest.json``."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from . import __version__
from .errors import InputError
from .i18n import render
from .reconstruct import CollectionState, load_collection
from .sqlite_reader import SourceDB

FORMAT = "chroma-salvage/1"
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def select_collections(source: SourceDB, names: list[str] | None):
    infos = source.collections()
    if not names:
        return infos
    known = {i.name: i for i in infos}
    missing = [n for n in names if n not in known]
    if missing:
        raise InputError("err.unknown_collection", name=missing[0], known=", ".join(sorted(known)) or "-")
    return [known[n] for n in dict.fromkeys(names)]


def prepare_output(out_dir: Path, force: bool) -> None:
    if out_dir.exists() and not out_dir.is_dir():
        raise InputError("err.out_not_dir", path=str(out_dir))
    if out_dir.is_dir() and any(out_dir.iterdir()) and not force:
        raise InputError("err.out_not_empty", path=str(out_dir))


def _file_name(name: str, used: set[str], collection_id: str) -> str:
    base = _UNSAFE.sub("_", name) or "collection"
    if base in used:
        base = f"{base}-{collection_id[:8]}"
    used.add(base)
    return base + ".jsonl"


def _normalized_flag(state: CollectionState) -> bool | str:
    """Describe the vectors actually written, counted per exported vector.

    True: every vector is unit length; False: every vector has its original length;
    "partial": a mix (e.g. length.bin missing, so index vectors stay unit length while
    vectors replayed from the log keep the length they were added with).
    """
    if state.info.space != "cosine" or state.unit_count == 0:
        return False
    return True if state.unit_count == len(state.vectors) else "partial"


def _lines(state: CollectionState):
    for eid in state.final_ids:
        rec = state.records.get(eid)
        vec = state.vectors.get(eid)
        yield {
            "id": eid,
            "document": rec.document if rec else None,
            "metadata": dict(rec.metadata) if rec else {},
            "embedding": list(vec) if vec is not None else None,
        }


def write_collection(state: CollectionState, path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    with open(path, "wb") as fh:
        for obj in _lines(state):
            line = (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
            fh.write(line)
            digest.update(line)
            count += 1
    return count, digest.hexdigest()


def export(source: SourceDB, out_dir: Path, names: list[str] | None = None,
           keep_normalized: bool = False, force: bool = False) -> dict[str, Any]:
    """Export and return the manifest dict (also written to ``out_dir/manifest.json``)."""
    infos = select_collections(source, names)
    prepare_output(out_dir, force)
    states = [load_collection(source, info, keep_normalized) for info in infos]  # read everything first
    out_dir.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    entries = []
    for state in states:
        file_name = _file_name(state.info.name, used, state.info.id)
        count, sha = write_collection(state, out_dir / file_name)
        entries.append({
            "name": state.info.name,
            "id": state.info.id,
            "dim": state.dim,
            "space": state.info.space,
            "normalized": _normalized_flag(state),
            "count": count,
            "file": file_name,
            "sha256": sha,
            "from_hnsw": state.from_hnsw,
            "from_wal": state.from_wal,
            "deleted_marked": state.deleted_marked,
            "warnings": [{"code": c, "params": p, "message": render("en", c, **p)}
                         for c, p in state.warnings],
        })
    manifest = {
        "format": FORMAT,
        "tool_version": __version__,
        "source": {
            "path": str(source.root),
            "band": source.band(),
            "migrations": source.migrations(),
            "sqlite_sha256": source.sha256(),
        },
        "collections": entries,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                           encoding="utf-8")
    return manifest
