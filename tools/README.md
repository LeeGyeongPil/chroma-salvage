# Regenerating the test fixtures

The folders in `tests/fixtures/` were written by real chromadb releases with synthetic
data (`random.Random(42)`, dimension 8). Only maintainers need chromadb for this; the
tests themselves do not. Run from the repository root:

```bash
uv run --no-project --python 3.11 --with chromadb==0.4.24 --with "numpy<2" \
    python tools/make_fixtures.py v04 tests/fixtures
uv run --no-project --python 3.12 --with chromadb==0.5.23 python tools/make_fixtures.py v05 tests/fixtures
uv run --no-project --python 3.12 --with chromadb==0.6.3  python tools/make_fixtures.py v06 tests/fixtures
uv run --no-project --python 3.12 --with chromadb==1.5.9  python tools/make_fixtures.py v1  tests/fixtures
```

Each run writes `<name>/` plus `<name>.truth.json` (the exact input and chromadb's own
`count()`), which the tests compare against. Chroma's index settings
`hnsw:batch_size=50` and `hnsw:sync_threshold=100` make small collections leave part of
their data only in the write-ahead log, which is the case the tool has to handle.
