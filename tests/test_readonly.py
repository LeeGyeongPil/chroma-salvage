"""AC-5: the source folder is never modified and chromadb is never imported."""
import hashlib
import shutil
import sqlite3
import sys

from conftest import FIXTURES, load_truth, read_jsonl


def snapshot(folder):
    """Relative path -> sha256 of every file (a new file shows up as a new key)."""
    return {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*")) if p.is_file()
    }


def run_both(cli, folder, out):
    assert cli("inspect", str(folder))[0] == 0
    assert cli("inspect", str(folder), "--json")[0] == 0
    assert cli("export", str(folder), "-o", str(out))[0] == 0


def test_source_unchanged(copy_fixture, cli, tmp_path):
    folder = copy_fixture("v04_multi")
    before = snapshot(folder)
    run_both(cli, folder, tmp_path / "out")
    assert snapshot(folder) == before  # same hashes, no -journal/-shm/-wal appeared
    assert "chromadb" not in sys.modules


def _make_wal_copy(source, dest, keep_wal):
    """Copy a fixture and switch its database to journal_mode=WAL."""
    shutil.copytree(source, dest)
    conn = sqlite3.connect(dest / "chroma.sqlite3")
    assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    conn.execute("CREATE TABLE scratch (x)")  # a write, so that a -wal file exists
    conn.commit()
    if keep_wal:  # simulate a folder copied while another process had it open
        assert (dest / "chroma.sqlite3-wal").exists()
        hold = tmp_copy = dest.parent / (dest.name + "-live")
        shutil.copytree(dest, tmp_copy, ignore=shutil.ignore_patterns("chroma.sqlite3-shm"))
        conn.close()
        shutil.rmtree(dest)
        shutil.move(hold, dest)
    else:
        conn.close()
    shm = dest / "chroma.sqlite3-shm"
    if shm.exists():
        shm.unlink()


def test_wal_journal_source_unchanged(cli, tmp_path):
    for keep_wal in (True, False):
        folder = tmp_path / f"wal-{keep_wal}" / "v1"
        _make_wal_copy(FIXTURES / "v1", folder, keep_wal)
        assert (folder / "chroma.sqlite3-wal").exists() == keep_wal
        before = snapshot(folder)
        out = tmp_path / f"out-{keep_wal}"
        run_both(cli, folder, out)
        assert snapshot(folder) == before
        assert not (folder / "chroma.sqlite3-shm").exists()
        want = load_truth("v1")["probe"]
        assert {r["id"] for r in read_jsonl(out / "probe.jsonl")} == set(want["ids"])
    assert "chromadb" not in sys.modules
