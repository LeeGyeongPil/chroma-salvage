"""AC-6 (exit code 3 for a malicious pickle) and AC-7 (input errors)."""
import pickle
import sqlite3
import struct

from conftest import FIXTURES
from test_safe_pickle import Payload


def test_malicious_pickle_exit_3(copy_fixture, cli, tmp_path):
    folder = copy_fixture("v04")
    marker = tmp_path / "pwned"
    target = next(folder.glob("*/index_metadata.pickle"))
    target.write_bytes(pickle.dumps(Payload(marker), protocol=5))
    for args in (("inspect", str(folder)), ("export", str(folder), "-o", str(tmp_path / "out"))):
        code, _, err = cli(*args)
        assert code == 3
        assert "REDUCE" in err
    assert not marker.exists()


def test_missing_path_exit_2(cli, tmp_path):
    code, out, err = cli("inspect", str(tmp_path / "nope"))
    assert code == 2 and out == ""
    assert "not found" in err


def test_folder_without_sqlite_exit_2(cli, tmp_path):
    code, _, err = cli("inspect", str(tmp_path))
    assert code == 2
    assert "chroma.sqlite3" in err


def test_sqlite_without_migrations_exit_2(cli, tmp_path):
    conn = sqlite3.connect(tmp_path / "chroma.sqlite3")
    conn.execute("CREATE TABLE other (x)")
    conn.commit()
    conn.close()
    code, _, err = cli("export", str(tmp_path), "-o", str(tmp_path / "out"))
    assert code == 2
    assert "migrations" in err


def test_non_empty_output_needs_force(cli, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_text("mine")
    code, _, err = cli("export", str(FIXTURES / "v1"), "-o", str(out))
    assert code == 2
    assert "--force" in err
    assert [p.name for p in out.iterdir()] == ["keep.txt"]
    assert (out / "keep.txt").read_text() == "mine"
    assert cli("export", str(FIXTURES / "v1"), "-o", str(out), "--force")[0] == 0
    assert (out / "keep.txt").read_text() == "mine"  # --force never deletes


def test_unknown_collection_exit_2(cli, tmp_path):
    out = tmp_path / "out"
    code, _, err = cli("export", str(FIXTURES / "v1"), "-o", str(out), "--collection", "nope")
    assert code == 2
    assert "nope" in err and "probe" in err
    assert not out.exists()


def test_unsupported_persist_version_exit_3(copy_fixture, cli):
    folder = copy_fixture("v1")
    header = next(folder.glob("*/header.bin"))
    raw = bytearray(header.read_bytes())
    raw[0:4] = struct.pack("<i", 2)
    header.write_bytes(bytes(raw))
    code, _, err = cli("inspect", str(folder))
    assert code == 3
    assert "persist_version" in err


def test_truncated_index_file_exit_3(copy_fixture, cli):
    folder = copy_fixture("v04")
    data = next(folder.glob("*/data_level0.bin"))
    data.write_bytes(data.read_bytes()[:100])
    assert cli("inspect", str(folder))[0] == 3
