"""Read the chroma-hnswlib files of one vector segment folder.

Layout (from chroma-hnswlib, ``hnswlib/hnswalg.h``,
https://github.com/chroma-core/hnswlib/blob/master/hnswlib/hnswalg.h):

* ``header.bin``       100 bytes, see ``HEADER_FORMAT``
* ``data_level0.bin``  one fixed-size record per element:
                       ``[link count 4 B][neighbours][vector dim*4 B][label 8 B]``
* ``length.bin``       one float32 per element: the ORIGINAL L2 norm of the vector
                       (cosine collections store unit vectors in ``data_level0.bin``)
* ``index_metadata.pickle``  string id <-> integer label (see ``safe_pickle``)

An element is deleted when the second byte of its link-count word has bit 0 set
(``DELETE_MARK``).
"""
from __future__ import annotations

import math
import os
import struct
from dataclasses import dataclass
from pathlib import Path

from .errors import UnsupportedFormatError

HEADER_FORMAT = "<iQQQQQQiIQQQdQ"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 100
HEADER_FIELDS = (
    "persist_version", "offset_level0", "max_elements", "cur_element_count",
    "size_data_per_element", "label_offset", "offset_data", "maxlevel", "enterpoint",
    "max_m", "max_m0", "m", "mult", "ef_construction",
)
SUPPORTED_PERSIST_VERSION = 1


@dataclass(frozen=True)
class Header:
    persist_version: int
    offset_level0: int
    max_elements: int
    cur_element_count: int
    size_data_per_element: int
    label_offset: int
    offset_data: int
    maxlevel: int
    enterpoint: int
    max_m: int
    max_m0: int
    m: int
    mult: float
    ef_construction: int

    @property
    def dim(self) -> int:
        return (self.label_offset - self.offset_data) // 4


@dataclass(frozen=True)
class Element:
    label: int
    vector: tuple[float, ...]  # exactly as stored (unit length for cosine)
    deleted: bool
    norm: float | None  # from length.bin, None when unavailable


def read_header(segment_dir: Path) -> Header:
    path = segment_dir / "header.bin"
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise UnsupportedFormatError("err.hnsw_file_missing", file=str(path)) from exc
    if len(raw) != HEADER_SIZE:
        raise UnsupportedFormatError("err.hnsw_header_size", file=str(path), size=len(raw), expected=HEADER_SIZE)
    header = Header(**dict(zip(HEADER_FIELDS, struct.unpack(HEADER_FORMAT, raw))))
    if header.persist_version != SUPPORTED_PERSIST_VERSION:
        raise UnsupportedFormatError(
            "err.hnsw_persist_version", file=str(path), version=header.persist_version,
            supported=SUPPORTED_PERSIST_VERSION)
    if header.dim <= 0 or header.size_data_per_element < header.label_offset + 8:
        raise UnsupportedFormatError("err.hnsw_header_inconsistent", file=str(path))
    return header


def read_elements(segment_dir: Path, header: Header) -> tuple[list[Element], list[tuple[str, dict]]]:
    """Return all elements in file order plus warnings ``[(code, params)]``."""
    warnings: list[tuple[str, dict]] = []
    count = header.cur_element_count
    if count == 0:
        return [], warnings
    data_path = segment_dir / "data_level0.bin"
    try:
        data = data_path.read_bytes()
    except OSError as exc:
        raise UnsupportedFormatError("err.hnsw_file_missing", file=str(data_path)) from exc
    need = count * header.size_data_per_element
    if len(data) < need:
        raise UnsupportedFormatError(
            "err.hnsw_data_size", file=str(data_path), size=len(data), expected=need, count=count)
    norms: tuple[float, ...] | None = None
    length_path = segment_dir / "length.bin"
    if os.path.exists(length_path):
        raw = length_path.read_bytes()
        if len(raw) >= count * 4:
            norms = struct.unpack(f"<{len(raw) // 4}f", raw)
        else:
            warnings.append(("warn.length_short", {"file": str(length_path)}))
    else:
        warnings.append(("warn.length_missing", {"file": str(length_path)}))
    dim = header.dim
    elements: list[Element] = []
    for i in range(count):
        base = i * header.size_data_per_element
        deleted = bool(data[base + 2] & 0x01)
        (label,) = struct.unpack_from("<Q", data, base + header.label_offset)
        vector = struct.unpack_from(f"<{dim}f", data, base + header.offset_data)
        elements.append(Element(label, vector, deleted, norms[i] if norms else None))
    return elements, warnings


def restore_norm(vector: tuple[float, ...], norm: float) -> tuple[float, ...]:
    """Undo the cosine normalisation, rounding every value back to float32."""
    return tuple(struct.unpack("<f", struct.pack("<f", x * norm))[0] for x in vector)


def normalize(vector: tuple[float, ...]) -> tuple[float, ...]:
    """Scale to unit length the way chroma-hnswlib does for cosine (``v * 1/(|v| + 1e-30)``).

    Used for vectors that come from the write-ahead log: Chroma has not normalised them yet.
    A zero vector stays zero. Every value is rounded to float32 like the stored vectors.
    """
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0.0:
        return tuple(vector)
    inv = 1.0 / (norm + 1e-30)
    return tuple(struct.unpack("<f", struct.pack("<f", x * inv))[0] for x in vector)
