"""Which chromadb versions can open a folder of a given version band.

Measured by opening copies of real folders (chromadb 0.4.24, 0.6.3 and 1.5.9; see
tools/README.md). The band is decided from the ``migrations`` table, not from release
notes, because the documented and the observed schema changes differ.
"""
from __future__ import annotations

from typing import Any

BANDS = ("0.4.x", "0.5.x-0.6.x", "1.x", "unknown-newer")

_TOPIC = "no such column: collections.topic"

COMPAT: dict[str, dict[str, Any]] = {
    "0.4.x": {
        "opens": "0.4.x",
        "migrates_irreversibly": ["0.5.x-0.6.x", "1.x"],
        "fails_on": [],
    },
    "0.5.x-0.6.x": {
        "opens": "0.5.x-0.6.x",
        "migrates_irreversibly": ["1.x"],
        "fails_on": [{"client": "0.4.x", "error": _TOPIC}],
    },
    "1.x": {
        "opens": "1.x",
        "migrates_irreversibly": [],
        "fails_on": [
            {"client": "0.4.x", "error": _TOPIC},
            {"client": "0.5.x-0.6.x", "error": "KeyError: '_type'"},
        ],
    },
    "unknown-newer": {"opens": None, "migrates_irreversibly": [], "fails_on": []},
}


def compat_for(band: str) -> dict[str, Any]:
    return COMPAT[band]
