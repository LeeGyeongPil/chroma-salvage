"""Shared helpers. The fixtures are real folders written by chromadb 0.4.24, 0.5.23, 0.6.3 and 1.5.9."""
from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path

import pytest

from chroma_salvage.cli import main

FIXTURES = Path(__file__).parent / "fixtures"
ALL_FIXTURES = [
    "v04", "v05", "v06", "v1", "v04_l2", "v1_l2", "v04_del", "v1_del", "v1_cfg", "v04_multi", "v1_multi",
]
EXPECTED_BAND = {
    "v04": ("0.4.x", (4, 3, 1)),
    "v05": ("0.5.x-0.6.x", (9, 4, 2)),
    "v06": ("0.5.x-0.6.x", (9, 4, 2)),
    "v1": ("1.x", (10, 6, 2)),
}


def band_for(name: str) -> tuple[str, tuple[int, int, int]]:
    key = name.split("_")[0]
    return EXPECTED_BAND[key]


def load_truth(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.truth.json").read_text())["collections"]


def f32(values) -> list[float]:
    """Round to float32, the precision Chroma stores."""
    return list(struct.unpack(f"<{len(values)}f", struct.pack(f"<{len(values)}f", *values)))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def copy_fixture(tmp_path):
    """Copy a fixture folder so a test may alter it."""
    def _copy(name: str) -> Path:
        dest = tmp_path / "copy" / name
        shutil.copytree(FIXTURES / name, dest)
        return dest
    return _copy


@pytest.fixture
def cli(capsys):
    """Run the CLI in-process with an empty environment (so the language is English unless set)."""
    def _run(*args: str, env: dict | None = None):
        code = main(list(args), env={} if env is None else env)
        out = capsys.readouterr()
        return code, out.out, out.err
    return _run
