"""AC-1: version band, migration levels and counts agree with what chromadb was given."""
import json

import pytest

from conftest import ALL_FIXTURES, band_for, load_truth


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_band_and_counts(name, cli):
    from conftest import FIXTURES

    code, out, _ = cli("inspect", str(FIXTURES / name), "--json")
    assert code == 0
    report = json.loads(out)
    band, (sysdb, metadb, queue) = band_for(name)
    assert report["band"] == band
    assert report["migrations"] == {"sysdb": sysdb, "metadb": metadb, "embeddings_queue": queue}
    truth = load_truth(name)
    assert [c["name"] for c in report["collections"]] == sorted(truth)
    for col in report["collections"]:
        want = truth[col["name"]]
        assert col["final_count"] == want["count"] == len(want["ids"])
        assert col["dim"] == want["dim"]
        assert col["space"] == want["space"]
        if name.endswith("_del"):
            assert col["hnsw"]["deleted_marked"] == 10
        if name in ("v04", "v05", "v06", "v1", "v04_l2", "v1_l2"):
            pending = col["wal"]["pending"]
            assert pending["ADD"] > 0  # newest rows exist only in the log
            assert pending["DELETE"] == 10
            assert col["hnsw"]["snapshot_count"] < col["final_count"]  # HNSW alone would miss data
