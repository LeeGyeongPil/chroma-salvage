"""Create the test fixtures: small Chroma folders written by a REAL chromadb.

This script needs chromadb, so it is only for maintainers. The generated folders
are committed, which is why the test suite itself runs without chromadb.
Run it once per chromadb version (see tools/README.md):

    uv run --no-project --python 3.12 --with chromadb==1.5.9 \
        python tools/make_fixtures.py v1 tests/fixtures

Data is synthetic and deterministic (random.Random(42), dim 8).
Each fixture <name> produces a folder <name>/ and a <name>.truth.json that holds
exactly what was given to chromadb plus its own count(), so tests can compare.
"""
from __future__ import annotations

import json
import random
import shutil
import sys
from pathlib import Path

import chromadb

# Small values so that a part of the data sits in the HNSW snapshot and the rest
# only in the write-ahead log (embeddings_queue).
SMALL = {"hnsw:batch_size": 50, "hnsw:sync_threshold": 100}
BATCH = 50


def make_data(rng: random.Random, start: int, n: int, dim: int, with_meta: bool = True):
    ids = [f"doc-{i:05d}" for i in range(start, start + n)]
    embs = [[round(rng.uniform(-1, 1), 6) for _ in range(dim)] for _ in range(n)]
    docs = [f"document number {i}" for i in range(start, start + n)]
    metas = None
    if with_meta:
        metas = [
            {"i": i, "even": i % 2 == 0, "tag": f"t{i % 3}", "score": round(i / 7, 4)}
            for i in range(start, start + n)
        ]
    return ids, embs, docs, metas


def add_all(col, ids, embs, docs, metas):
    for s in range(0, len(ids), BATCH):
        kwargs = dict(ids=ids[s:s + BATCH], embeddings=embs[s:s + BATCH], documents=docs[s:s + BATCH])
        if metas is not None:
            kwargs["metadatas"] = metas[s:s + BATCH]
        col.add(**kwargs)


class Truth:
    """Collects what was stored, per collection."""

    def __init__(self) -> None:
        self.cols: dict[str, dict] = {}

    def start(self, name: str, space: str, dim: int) -> None:
        self.cols[name] = {"space": space, "dim": dim, "ids": [], "embeddings": [],
                           "documents": [], "metadatas": []}

    def add(self, name, ids, embs, docs, metas) -> None:
        c = self.cols[name]
        c["ids"] += ids
        c["embeddings"] += embs
        c["documents"] += docs
        c["metadatas"] += metas if metas is not None else [None] * len(ids)

    def delete(self, name, k: int) -> None:
        c = self.cols[name]
        for key in ("ids", "embeddings", "documents", "metadatas"):
            c[key] = c[key][k:]

    def dump(self, path: Path, collections: dict) -> None:
        for name, col in collections.items():
            self.cols[name]["count"] = col.count()
        path.write_text(json.dumps({"chromadb": chromadb.__version__, "collections": self.cols}))


def new_client(out: Path):
    if out.exists():
        shutil.rmtree(out)
    return chromadb.PersistentClient(path=str(out))


def simple(root: Path, name: str, space: str, delete: int, extra: int) -> None:
    rng = random.Random(42)
    client = new_client(root / name)
    col = client.get_or_create_collection(
        "probe", metadata={"hnsw:space": space, **SMALL}, embedding_function=None)
    t = Truth()
    t.start("probe", space, 8)
    data = make_data(rng, 0, 150, 8)
    add_all(col, *data)
    t.add("probe", *data)
    if delete:
        col.delete(ids=data[0][:delete])
        t.delete("probe", delete)
    if extra:  # more adds after the delete, so a later sync writes the delete mark
        more = make_data(rng, 150, extra, 8)
        add_all(col, *more)
        t.add("probe", *more)
    t.dump(root / f"{name}.truth.json", {"probe": col})


def multi(root: Path, name: str) -> None:
    rng = random.Random(42)
    client = new_client(root / name)
    a = client.get_or_create_collection(
        "alpha", metadata={"hnsw:space": "cosine", **SMALL}, embedding_function=None)
    b = client.get_or_create_collection(
        "beta", metadata={"hnsw:space": "l2", **SMALL}, embedding_function=None)
    t = Truth()
    t.start("alpha", "cosine", 8)
    t.start("beta", "l2", 6)
    da = make_data(rng, 0, 130, 8)
    db = make_data(rng, 1000, 120, 6, with_meta=False)
    # interleave writes so the two collections share the write-ahead log
    for s in range(0, 130, BATCH):
        sl = slice(s, s + BATCH)
        a.add(ids=da[0][sl], embeddings=da[1][sl], documents=da[2][sl], metadatas=da[3][sl])
        sb = slice(s, min(s + BATCH, 120))
        if sb.start < 120:
            b.add(ids=db[0][sb], embeddings=db[1][sb], documents=db[2][sb])
    t.add("alpha", *da)
    t.add("beta", *db)
    t.dump(root / f"{name}.truth.json", {"alpha": a, "beta": b})


def configured(root: Path, name: str) -> None:
    """1.x only: collection made with `configuration=` (no hnsw: metadata)."""
    rng = random.Random(7)
    client = new_client(root / name)
    col = client.get_or_create_collection(
        "cfg", configuration={"hnsw": {"space": "ip", "ef_construction": 64, "max_neighbors": 12}},
        embedding_function=None)
    ids = [f"c{i}" for i in range(50)]
    embs = [[round(rng.uniform(-1, 1), 6) for _ in range(4)] for _ in range(50)]
    docs = [f"cfg document {i}" for i in range(50)]
    metas = [{"i": i} for i in range(50)]
    col.add(ids=ids, embeddings=embs, documents=docs, metadatas=metas)
    t = Truth()
    t.start("cfg", "ip", 4)
    t.add("cfg", ids, embs, docs, metas)
    t.dump(root / f"{name}.truth.json", {"cfg": col})


def main() -> None:
    tag, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    simple(out, tag, "cosine", delete=10, extra=0)
    if tag in ("v04", "v1"):
        simple(out, f"{tag}_l2", "l2", delete=10, extra=0)
        simple(out, f"{tag}_del", "cosine", delete=10, extra=120)
        multi(out, f"{tag}_multi")
    if tag == "v1":
        configured(out, "v1_cfg")
    print("chromadb", chromadb.__version__, "->", tag)


if __name__ == "__main__":
    main()
