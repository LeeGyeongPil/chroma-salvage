"""Rebuild the latest state of a collection: HNSW snapshot + write-ahead log.

Chroma writes every add/update/delete to a log table (``embeddings_queue``) first and
copies it into the HNSW files only every ``sync_threshold`` operations. The files alone
therefore miss the newest data (and may still hold deleted vectors), so the final state
is ``HNSW snapshot`` followed by a replay of the log rows after the segment's watermark.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import hnsw
from .errors import UnsupportedFormatError
from .safe_pickle import parse_index_metadata
from .sqlite_reader import CollectionInfo, Record, SourceDB

Warning_ = tuple[str, dict[str, Any]]  # (message code, parameters)


@dataclass
class CollectionState:
    info: CollectionInfo
    dim: int | None
    hnsw_present: bool
    pickle: str  # "present" | "missing" | "n/a"
    pickle_class: str | None
    header: hnsw.Header | None
    hnsw_total: int  # cur_element_count (live + deleted)
    hnsw_live: int  # elements without DELETE_MARK that map to an id
    deleted_marked: int
    vector_watermark: int
    metadata_watermark: int
    wal_pending: dict[str, int]  # operations after the vector watermark
    vectors: dict[str, tuple[float, ...]] = field(default_factory=dict)
    vector_source: dict[str, str] = field(default_factory=dict)  # id -> "hnsw" | "wal"
    records: dict[str, Record] = field(default_factory=dict)
    warnings: list[Warning_] = field(default_factory=list)
    # cosine only: ids whose exported vector is unit length (normalised), tracked per final vector
    unit_ids: set[str] = field(default_factory=set)

    @property
    def final_ids(self) -> list[str]:
        return sorted(set(self.vectors) | set(self.records))

    @property
    def unit_count(self) -> int:
        return len(self.unit_ids)

    @property
    def from_hnsw(self) -> int:
        return sum(1 for s in self.vector_source.values() if s == "hnsw")

    @property
    def from_wal(self) -> int:
        return sum(1 for s in self.vector_source.values() if s == "wal")


def load_collection(source: SourceDB, info: CollectionInfo, keep_normalized: bool = False) -> CollectionState:
    warnings: list[Warning_] = []
    segment_dir = source.root / info.vector_segment if info.vector_segment else None
    header: hnsw.Header | None = None
    elements: list[hnsw.Element] = []
    label_to_id: dict[int, str] = {}
    pickle_state = "n/a"
    pickle_class: str | None = None
    pickle_wm: int | None = None

    if segment_dir is not None and (segment_dir / "header.bin").exists():
        header = hnsw.read_header(segment_dir)
        elements, w = hnsw.read_elements(segment_dir, header)
        # length.bin 은 cosine 에서만 쓰인다 — l2/ip 에서는 값에 영향이 없으니 경고하지 않는다
        warnings += [x for x in w if info.space == "cosine" or not x[0].startswith("warn.length_")]
        pickle_path = segment_dir / "index_metadata.pickle"
        if pickle_path.exists():
            pickle_state = "present"
            state, pickle_class = parse_index_metadata(pickle_path.read_bytes())
            label_to_id = {int(k): v for k, v in (state.get("label_to_id") or {}).items()}
            wm = state.get("max_seq_id")
            pickle_wm = int(wm) if isinstance(wm, int) else None
        else:
            pickle_state = "missing"
            if elements:
                raise UnsupportedFormatError(
                    "err.pickle_missing", file=str(pickle_path), count=len(elements))
    elif segment_dir is not None:
        pickle_state = "missing"
        warnings.append(("warn.no_hnsw_files", {"segment": info.vector_segment}))

    dim = info.dimension or (header.dim if header else None)
    if header and info.dimension and header.dim != info.dimension:
        raise UnsupportedFormatError("err.dim_mismatch", header=header.dim, db=info.dimension)

    vector_wm = pickle_wm if pickle_wm is not None else (source.watermark(info.vector_segment) or 0)
    metadata_wm = source.watermark(info.metadata_segment) or 0

    # 1. HNSW snapshot
    vectors: dict[str, tuple[float, ...]] = {}
    origin: dict[str, str] = {}
    unit: set[str] = set()  # cosine: ids whose vector we export at unit length
    cosine = info.space == "cosine"
    deleted = unmapped = 0
    norm_missing = False
    for el in elements:
        if el.deleted:
            deleted += 1
            continue
        eid = label_to_id.get(el.label)
        if eid is None:
            unmapped += 1
            continue
        vec = el.vector  # cosine: Chroma already stored it at unit length
        if cosine:
            if keep_normalized:
                unit.add(eid)
            elif el.norm is None:
                norm_missing = True  # no length.bin value: cannot restore, stays unit length
                unit.add(eid)
            else:
                vec = hnsw.restore_norm(vec, el.norm)
                unit.discard(eid)
        vectors[eid] = vec
        origin[eid] = "hnsw"
    if unmapped:
        warnings.append(("warn.unmapped_labels", {"count": unmapped}))
    if norm_missing:
        warnings.append(("warn.norm_missing", {}))
    live = len(vectors)

    # 2. replay the log after the vector watermark
    pending = {"ADD": 0, "UPDATE": 0, "UPSERT": 0, "DELETE": 0}
    for row in source.wal_rows(info, vector_wm):
        if row.operation in pending:
            pending[row.operation] += 1
        if row.operation == "DELETE":
            vectors.pop(row.id, None)
            origin.pop(row.id, None)
            unit.discard(row.id)
        elif row.vector is None:
            continue  # metadata-only update
        elif row.operation == "ADD" and row.id in vectors:
            continue  # Chroma ignores a duplicate add
        elif row.operation == "UPDATE" and row.id not in vectors:
            continue
        else:
            # 로그의 벡터는 사용자가 넣은 원래 길이 그대로다(Chroma 가 아직 정규화하지 않음).
            # --normalized 면 HNSW 출처와 같은 상태(단위 길이)로 맞춘다.
            if cosine and keep_normalized:
                vectors[row.id] = hnsw.normalize(row.vector)
                unit.add(row.id)
            else:
                vectors[row.id] = row.vector
                unit.discard(row.id)  # replaces a unit-length HNSW vector with the original one
            origin[row.id] = "wal"

    # 3. documents and metadata: SQLite METADATA segment + log after its watermark
    records = source.records(info.metadata_segment)
    for row in source.wal_rows(info, metadata_wm):
        if row.operation == "DELETE":
            records.pop(row.id, None)
            continue
        meta = dict(row.metadata or {})
        has_doc = "chroma:document" in meta
        doc = meta.pop("chroma:document", None)
        existing = records.get(row.id)
        if existing is None:
            if row.operation == "UPDATE":
                continue
            records[row.id] = Record(doc, {k: v for k, v in meta.items() if v is not None})
        elif row.operation != "ADD":
            if has_doc:
                existing.document = doc
            for k, v in meta.items():
                if v is None:
                    existing.metadata.pop(k, None)
                else:
                    existing.metadata[k] = v

    only_vector = sorted(set(vectors) - set(records))
    only_record = sorted(set(records) - set(vectors))
    if only_vector:
        warnings.append(("warn.vector_without_record", {"count": len(only_vector)}))
    if only_record:
        warnings.append(("warn.record_without_vector", {"count": len(only_record)}))
    if dim is None and vectors:
        dim = len(next(iter(vectors.values())))

    return CollectionState(
        info=info, dim=dim, hnsw_present=header is not None, pickle=pickle_state,
        pickle_class=pickle_class, header=header, hnsw_total=header.cur_element_count if header else 0,
        hnsw_live=live, deleted_marked=deleted, vector_watermark=vector_wm,
        metadata_watermark=metadata_wm, wal_pending=pending, vectors=vectors,
        vector_source=origin, records=records, warnings=warnings,
        unit_ids=unit & set(vectors))


