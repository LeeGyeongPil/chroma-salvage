"""AC-2, AC-3, AC-4: what comes out of ``export`` equals what was put into chromadb."""
import hashlib
import json
import math

import pytest

from conftest import ALL_FIXTURES, FIXTURES, band_for, f32, load_truth, read_jsonl


def _check_collection(rows, want):
    assert [r["id"] for r in rows] == sorted(want["ids"])  # id set equal, sorted
    by_id = {r["id"]: r for r in rows}
    max_rel = 0.0
    for i, eid in enumerate(want["ids"]):
        row = by_id[eid]
        assert row["document"] == want["documents"][i]
        assert row["metadata"] == (want["metadatas"][i] or {})
        expected = f32(want["embeddings"][i])
        if want["space"] == "cosine":
            for got, exp in zip(row["embedding"], expected):
                max_rel = max(max_rel, abs(got - exp) / abs(exp) if exp else abs(got))
        else:
            assert f32(row["embedding"]) == expected  # bit-exact float32
            assert row["embedding"] == expected
    if want["space"] == "cosine":
        assert max_rel <= 2e-7, max_rel


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_export_matches_truth(name, cli, tmp_path):
    out = tmp_path / "out"
    code, stdout, _ = cli("export", str(FIXTURES / name), "-o", str(out))
    assert code == 0, stdout
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["format"] == "chroma-salvage/1"
    assert manifest["source"]["band"] == band_for(name)[0]
    truth = load_truth(name)
    assert sorted(c["name"] for c in manifest["collections"]) == sorted(truth)
    for entry in manifest["collections"]:
        path = out / entry["file"]
        rows = read_jsonl(path)
        assert entry["count"] == len(rows) == len(truth[entry["name"]]["ids"])
        assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert entry["dim"] == truth[entry["name"]]["dim"]
        assert entry["space"] == truth[entry["name"]]["space"]
        assert entry["from_hnsw"] + entry["from_wal"] == entry["count"]
        _check_collection(rows, truth[entry["name"]])


def test_wal_only_configuration_collection(cli, tmp_path):
    """1.x collection made with configuration=: no pickle, empty HNSW file, space only in schema_str."""
    code, out, _ = cli("inspect", str(FIXTURES / "v1_cfg"), "--json")
    assert code == 0
    col = json.loads(out)["collections"][0]
    assert col["hnsw"]["pickle"] == "missing"
    assert col["hnsw"]["total_elements"] == 0
    assert col["space"] == "ip"
    assert col["space_source"] == "schema_str"

    dest = tmp_path / "out"
    code, _, _ = cli("export", str(FIXTURES / "v1_cfg"), "-o", str(dest))
    assert code == 0
    rows = read_jsonl(dest / "cfg.jsonl")
    want = load_truth("v1_cfg")["cfg"]
    assert len(rows) == 50
    assert {r["id"]: r["embedding"] for r in rows} == {
        i: f32(e) for i, e in zip(want["ids"], want["embeddings"])}
    assert json.loads((dest / "manifest.json").read_text())["collections"][0]["from_wal"] == 50


@pytest.mark.parametrize("name", ["v04_multi", "v1_multi"])
def test_multi_collection_isolation(name, cli, tmp_path):
    truth = load_truth(name)
    out = tmp_path / "all"
    assert cli("export", str(FIXTURES / name), "-o", str(out))[0] == 0
    files = sorted(p.name for p in out.glob("*.jsonl"))
    assert files == ["alpha.jsonl", "beta.jsonl"]
    sets = {n: {r["id"] for r in read_jsonl(out / f"{n}.jsonl")} for n in ("alpha", "beta")}
    for n in sets:
        assert sets[n] == set(truth[n]["ids"])
    assert not sets["alpha"] & sets["beta"]

    one = tmp_path / "one"
    assert cli("export", str(FIXTURES / name), "-o", str(one), "--collection", "beta")[0] == 0
    assert sorted(p.name for p in one.glob("*.jsonl")) == ["beta.jsonl"]
    assert [c["name"] for c in json.loads((one / "manifest.json").read_text())["collections"]] == ["beta"]


def _norm(vec) -> float:
    return math.sqrt(sum(x * x for x in vec))


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_normalized_option_makes_every_cosine_vector_unit_length(name, cli, tmp_path):
    """--normalized: every exported cosine vector (from HNSW *and* from the log) has norm 1,
    and the manifest flag says so. l2/ip collections are written unchanged with flag false."""
    plain, unit = tmp_path / "plain", tmp_path / "unit"
    assert cli("export", str(FIXTURES / name), "-o", str(plain))[0] == 0
    assert cli("export", str(FIXTURES / name), "-o", str(unit), "--normalized")[0] == 0
    plain_entries = {c["name"]: c for c in json.loads((plain / "manifest.json").read_text())["collections"]}
    for entry in json.loads((unit / "manifest.json").read_text())["collections"]:
        rows = read_jsonl(unit / entry["file"])
        if entry["space"] == "cosine":
            assert entry["from_wal"] > 0 or name == "v1_cfg"  # the log case is really exercised
            bad = [r["id"] for r in rows if abs(_norm(r["embedding"]) - 1.0) >= 1e-5]
            assert bad == [], f"{len(bad)} of {len(rows)} vectors are not unit length"
            assert entry["normalized"] is True
        else:
            assert entry["normalized"] is False
            assert rows == read_jsonl(plain / entry["file"])
        assert plain_entries[entry["name"]]["normalized"] is False  # default: original length


def test_normalized_log_vector_points_the_same_way(cli, tmp_path):
    """A vector replayed from the log is scaled, not changed: v / |v| of the added vector."""
    out = tmp_path / "out"
    assert cli("export", str(FIXTURES / "v1"), "-o", str(out), "--normalized")[0] == 0
    want = load_truth("v1")["probe"]
    added = dict(zip(want["ids"], want["embeddings"]))
    manifest = json.loads((out / "manifest.json").read_text())["collections"][0]
    rows = read_jsonl(out / "probe.jsonl")
    assert len(rows) == manifest["count"]
    for row in rows:
        orig = added[row["id"]]
        n = _norm(orig)
        for got, exp in zip(row["embedding"], orig):
            assert got == pytest.approx(exp / n, rel=1e-6, abs=1e-7)


def test_length_file_missing_gives_partial_flag(copy_fixture, cli, tmp_path):
    """Without length.bin, index vectors stay unit length but log vectors keep their length:
    the manifest must say "partial" and the unit count must equal the surviving HNSW vectors."""
    src = copy_fixture("v1")
    for f in src.rglob("length.bin"):
        f.unlink()
    out = tmp_path / "out"
    assert cli("export", str(src), "-o", str(out))[0] == 0
    entry = json.loads((out / "manifest.json").read_text(encoding="utf-8"))["collections"][0]
    assert entry["space"] == "cosine"
    assert any(w["code"] == "warn.length_missing" for w in entry["warnings"])
    assert entry["normalized"] == "partial"
    rows = read_jsonl(out / entry["file"])
    unit = [r for r in rows if abs(_norm(r["embedding"]) - 1.0) < 1e-5]
    assert len(unit) == entry["from_hnsw"] > 0
    assert len(rows) - len(unit) == entry["from_wal"] > 0
    # the log vectors are still exactly what was added
    want = load_truth("v1")["probe"]
    added = {i: f32(e) for i, e in zip(want["ids"], want["embeddings"])}
    unit_ids = {r["id"] for r in unit}
    for r in rows:
        if r["id"] not in unit_ids:
            assert r["embedding"] == added[r["id"]]

    # with --normalized the same folder is fully unit length again
    out2 = tmp_path / "out2"
    assert cli("export", str(src), "-o", str(out2), "--normalized")[0] == 0
    entry2 = json.loads((out2 / "manifest.json").read_text(encoding="utf-8"))["collections"][0]
    assert entry2["normalized"] is True
    assert all(abs(_norm(r["embedding"]) - 1.0) < 1e-5 for r in read_jsonl(out2 / entry2["file"]))


def test_length_file_missing_is_not_a_warning_for_l2(copy_fixture, cli, tmp_path):
    src = copy_fixture("v1_l2")
    for f in src.rglob("length.bin"):
        f.unlink()
    out = tmp_path / "out"
    assert cli("export", str(src), "-o", str(out))[0] == 0
    entry = json.loads((out / "manifest.json").read_text(encoding="utf-8"))["collections"][0]
    assert entry["normalized"] is False
    assert not any(w["code"].startswith("warn.length_") for w in entry["warnings"])
    _check_collection(read_jsonl(out / entry["file"]), load_truth("v1_l2")[entry["name"]])
