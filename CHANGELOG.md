# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-11-24

### Changed
- CI workflow: current action versions, pinned uv, managed Python only. No change to the tool itself.

## [0.1.0] - 2026-11-24

### Added
- `inspect`: detect the version band (0.4.x, 0.5.x-0.6.x, 1.x) from the `migrations` table, list which chromadb versions can open the folder, and report per-collection HNSW snapshot, deleted marks, pending write-ahead-log rows, pickle presence and final count.
- `export`: write each collection as JSONL (id, document, metadata, embedding) plus `manifest.json` with sha256 hashes, without chromadb and without modifying the source folder.
- HNSW snapshot and write-ahead log are merged to the latest state; cosine vectors get their original length back from `length.bin` (`--normalized` keeps unit vectors).
- Collections without `index_metadata.pickle` (small 1.x collections) are rebuilt from the write-ahead log alone.
- `index_metadata.pickle` is read by an opcode allow-list walk and never unpickled.
- English and Korean output (`--lang`, `CHROMA_SALVAGE_LANG`, locale variables).
