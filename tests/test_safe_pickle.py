"""AC-6: the pickle side file is walked, never loaded."""
import pickle

import pytest

from chroma_salvage.errors import UnsafePickleError
from chroma_salvage.safe_pickle import parse_index_metadata
from conftest import FIXTURES


class Payload:
    """Would run a shell command if somebody called pickle.load on its dump."""

    def __init__(self, marker):
        self.marker = marker

    def __reduce__(self):
        import os

        return (os.system, (f"touch {self.marker}",))


@pytest.mark.parametrize("protocol,opcode", [(0, "GLOBAL"), (2, "GLOBAL"), (4, "REDUCE"), (5, "REDUCE")])
def test_rejects_reduce_payload(protocol, opcode, tmp_path):
    marker = tmp_path / "pwned"
    raw = pickle.dumps(Payload(marker), protocol=protocol)
    with pytest.raises(UnsafePickleError) as info:
        parse_index_metadata(raw)
    assert opcode in str(info.value)
    assert info.value.exit_code == 3
    assert not marker.exists()


@pytest.mark.parametrize("name", ["v04", "v05", "v06", "v1"])
def test_accepts_real_pickles(name):
    path = next((FIXTURES / name).glob("*/index_metadata.pickle"))
    state, cls = parse_index_metadata(path.read_bytes())
    assert state["label_to_id"]
    assert all(isinstance(v, str) for v in state["label_to_id"].values())
    assert (cls is None) == (name == "v1")  # 0.x pickles an object, 1.x a plain dict


def test_plain_data_is_fine():
    state, cls = parse_index_metadata(pickle.dumps({"a": 1, "b": [1, 2], "c": (3, None)}, protocol=5))
    assert state == {"a": 1, "b": [1, 2], "c": (3, None)} and cls is None


def test_garbage_is_rejected_not_crashing():
    with pytest.raises(UnsafePickleError):
        parse_index_metadata(b"\x80\x05N.")  # a bare None is not a state dict
