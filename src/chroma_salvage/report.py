"""Build the ``inspect`` report (a language-neutral dict) and render it as text."""
from __future__ import annotations

import unicodedata
from typing import Any, Callable

from . import __version__
from .compat import compat_for
from .i18n import render
from .reconstruct import CollectionState, Warning_
from .sqlite_reader import SourceDB

Translate = Callable[..., str]


def warnings_to_json(warnings: list[Warning_], lang: str) -> list[dict[str, Any]]:
    return [{"code": code, "params": params, "message": render(lang, code, **params)}
            for code, params in warnings]


def collection_report(state: CollectionState, lang: str) -> dict[str, Any]:
    header = state.header
    return {
        "name": state.info.name,
        "id": state.info.id,
        "dim": state.dim,
        "space": state.info.space,
        "space_source": state.info.space_source,
        "vector_segment": state.info.vector_segment,
        "metadata_segment": state.info.metadata_segment,
        "hnsw": {
            "present": state.hnsw_present,
            "header": None if header is None else {
                "persist_version": header.persist_version,
                "cur_element_count": header.cur_element_count,
                "max_elements": header.max_elements,
                "size_data_per_element": header.size_data_per_element,
                "m": header.m,
                "ef_construction": header.ef_construction,
            },
            "total_elements": state.hnsw_total,
            "snapshot_count": state.hnsw_live,
            "deleted_marked": state.deleted_marked,
            "pickle": state.pickle,
            "pickle_class": state.pickle_class,
        },
        "wal": {
            "vector_watermark": state.vector_watermark,
            "metadata_watermark": state.metadata_watermark,
            "pending": state.wal_pending,
        },
        "final_count": len(state.final_ids),
        "from_hnsw": state.from_hnsw,
        "from_wal": state.from_wal,
        "warnings": warnings_to_json(state.warnings, lang),
    }


def build_report(source: SourceDB, states: list[CollectionState], lang: str) -> dict[str, Any]:
    band = source.band()
    folder_warnings: list[Warning_] = []
    if band == "unknown-newer":
        folder_warnings.append(("warn.unknown_newer", {}))
    return {
        "tool_version": __version__,
        "path": str(source.root),
        "band": band,
        "migrations": source.migrations(),
        "compat": compat_for(band),
        "collections": [collection_report(s, lang) for s in states],
        "orphan_segments": source.orphan_segment_dirs(),
        "warnings": warnings_to_json(folder_warnings, lang),
    }


# -- text rendering ------------------------------------------------------------

def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * (width - _width(text))


def format_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    widths = [max(_width(h), *(_width(r[i]) for r in rows)) if rows else _width(h)
              for i, h in enumerate(headers)]
    lines = ["  ".join(_pad(h, w) for h, w in zip(headers, widths)),
             "  ".join("-" * w for w in widths)]
    lines += ["  ".join(_pad(c, w) for c, w in zip(r, widths)) for r in rows]
    return lines


def render_text(report: dict[str, Any], t: Translate) -> str:
    out: list[str] = []
    mig = report["migrations"]
    out.append(t("insp.folder", path=report["path"]))
    out.append(t("insp.band", band=report["band"], sysdb=mig["sysdb"], metadb=mig["metadb"],
                 queue=mig["embeddings_queue"]))
    out.append("")
    out.append(t("insp.opens_title"))
    compat = report["compat"]
    if compat["opens"]:
        out.append("  - " + t("insp.opens_ok", band=compat["opens"]))
    else:
        out.append("  - " + t("insp.opens_unknown"))
    for band in compat["migrates_irreversibly"]:
        out.append("  - " + t("insp.opens_migrates", band=band))
    for fail in compat["fails_on"]:
        out.append("  - " + t("insp.opens_fails", band=fail["client"], error=fail["error"]))
    out.append("")
    out.append(t("insp.collections", n=len(report["collections"])))
    headers = [t("col.name"), t("col.dim"), t("col.space"), t("col.snapshot"), t("col.deleted"),
               t("col.wal"), t("col.pickle"), t("col.final")]
    rows = []
    for c in report["collections"]:
        h, w = c["hnsw"], c["wal"]["pending"]
        rows.append([
            c["name"], str(c["dim"]), c["space"], str(h["snapshot_count"]), str(h["deleted_marked"]),
            f"{w['ADD']}/{w['UPDATE']}/{w['UPSERT']}/{w['DELETE']}",
            t("pickle." + h["pickle"]), str(c["final_count"])])
    out += ["  " + line for line in format_table(headers, rows)]
    out.append("  " + t("insp.wal_legend"))
    for c in report["collections"]:
        for w in c["warnings"]:
            out.append(f"  [{c['name']}] {w['message']}")
        if c["space_source"] == "schema_str":
            out.append("  " + t("insp.space_from_schema", name=c["name"], space=c["space"]))
    if report["orphan_segments"]:
        out.append("")
        out.append(t("insp.orphans", n=len(report["orphan_segments"])))
        out += ["  - " + name for name in report["orphan_segments"]]
    for w in report["warnings"]:
        out.append(w["message"])
    return "\n".join(out) + "\n"
