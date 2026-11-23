"""AC-8 and AC-9: English and Korean output, language precedence, start command."""
import json
import re
import string
import subprocess
import sys

import pytest

from chroma_salvage.i18n import MESSAGES, resolve_lang
from conftest import FIXTURES

HANGUL = re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏]")


def placeholders(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def shape(value):
    """JSON structure without the values: keys only."""
    if isinstance(value, dict):
        return {k: shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return None


def test_message_tables_have_the_same_keys_and_placeholders():
    assert set(MESSAGES["en"]) == set(MESSAGES["ko"])
    for key in MESSAGES["en"]:
        assert placeholders(MESSAGES["en"][key]) == placeholders(MESSAGES["ko"][key]), key


def test_english_has_no_hangul():
    assert not any(HANGUL.search(v) for v in MESSAGES["en"].values())
    assert all(HANGUL.search(v) for k, v in MESSAGES["ko"].items() if k.startswith(("help.description", "insp.band")))


@pytest.mark.parametrize("args", [
    ("--help",),
    ("inspect", "--help"),
    ("export", "--help"),
    ("inspect", str(FIXTURES / "v1")),
    ("inspect", str(FIXTURES / "nope")),
    ("export", str(FIXTURES / "v1")),  # missing -o: usage error
])
def test_each_language_output(args, cli):
    _, out_en, err_en = cli(*args, "--lang", "en")
    _, out_ko, err_ko = cli(*args, "--lang", "ko")
    assert not HANGUL.search(out_en + err_en)
    assert HANGUL.search(out_ko + err_ko)
    assert out_en + err_en != out_ko + err_ko


def test_inspect_table_headers(cli):
    _, en, _ = cli("inspect", str(FIXTURES / "v1"), "--lang", "en")
    _, ko, _ = cli("inspect", str(FIXTURES / "v1"), "--lang", "ko")
    assert "HNSW snapshot" in en and "WAL pending" in en
    assert "HNSW 스냅숏" in ko and "WAL 대기" in ko


def test_language_precedence(cli):
    path = str(FIXTURES / "v1")

    def lang_of(*extra, env):
        out = cli("inspect", path, *extra, env=env)[1]
        return "ko" if HANGUL.search(out) else "en"

    assert lang_of(env={}) == "en"
    assert lang_of(env={"LANG": "ko_KR.UTF-8"}) == "ko"
    assert lang_of(env={"LANG": "de_DE.UTF-8"}) == "en"  # not Korean -> English
    assert lang_of(env={"LC_MESSAGES": "ko_KR.UTF-8", "LANG": "en_US.UTF-8"}) == "ko"
    assert lang_of(env={"LC_ALL": "en_US.UTF-8", "LC_MESSAGES": "ko_KR.UTF-8"}) == "en"
    assert lang_of(env={"CHROMA_SALVAGE_LANG": "ko", "LANG": "en_US.UTF-8"}) == "ko"
    assert lang_of(env={"CHROMA_SALVAGE_LANG": "en", "LC_ALL": "ko_KR.UTF-8"}) == "en"
    assert lang_of("--lang", "ko", env={"CHROMA_SALVAGE_LANG": "en"}) == "ko"
    assert lang_of("--lang", "en", env={"CHROMA_SALVAGE_LANG": "ko", "LANG": "ko_KR"}) == "en"


def test_resolve_lang_unit():
    assert resolve_lang(None, {}) == "en"
    assert resolve_lang("ko", {"CHROMA_SALVAGE_LANG": "en"}) == "ko"
    assert resolve_lang(None, {"LANG": "KO_KR.UTF-8"}) == "ko"


def test_json_keys_do_not_depend_on_language(cli):
    for name in ("v1", "v04_multi", "v1_cfg"):
        en = json.loads(cli("inspect", str(FIXTURES / name), "--json", "--lang", "en")[1])
        ko = json.loads(cli("inspect", str(FIXTURES / name), "--json", "--lang", "ko")[1])
        assert shape(en) == shape(ko)


def test_start_command_on_bundled_sample():
    """AC-9: the command from the README works on the committed 1.x sample folder."""
    proc = subprocess.run(
        [sys.executable, "-m", "chroma_salvage", "inspect", str(FIXTURES / "v1"), "--lang", "en"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "1.x" in proc.stdout
    assert "probe" in proc.stdout
    assert "can be opened by" in proc.stdout


@pytest.mark.parametrize("lang,prefix", [("en", "usage:"), ("ko", "사용법:")])
def test_usage_prefix_appears_once(cli, lang, prefix):
    _, out, _ = cli("export", "--help", "--lang", lang)
    assert out.count(prefix) == 1
    code, _, err = cli("export", str(FIXTURES / "v1"), "--lang", lang)
    assert code == 2 and err.count(prefix) == 1


@pytest.mark.parametrize("argv", [
    ["export", str(FIXTURES / "v1")],
    ["bogus"],
    ["inspect"],
    ["inspect", "a", "b"],
    ["export", str(FIXTURES / "v1"), "-o"],
])
def test_korean_usage_errors_have_no_english_sentence(cli, argv):
    code, _, err = cli(*argv, "--lang", "ko")
    assert code == 2
    message = next(ln for ln in err.splitlines() if ln.startswith("오류"))
    assert HANGUL.search(message)
    assert not re.search(r"\b(the|following|required|invalid|choice|expected|unrecognized|choose)\b", message)


@pytest.mark.parametrize("lang", ["en", "ko"])
def test_manifest_normalized_is_partial_when_length_file_is_missing(copy_fixture, cli, tmp_path, lang):
    """v1 has 100 index vectors (no norm -> unit length) and 50 log vectors (original length).
    The flag is "partial" in both languages and the warning is shown in the chosen language."""
    src = copy_fixture("v1")
    for f in src.rglob("length.bin"):
        f.unlink()
    out = tmp_path / "out"
    code, stdout, _ = cli("export", str(src), "-o", str(out), "--lang", lang)
    assert code == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["collections"][0]
    assert entry["space"] == "cosine"
    assert entry["normalized"] == "partial"  # index vectors unit length, log vectors original length
    assert any(w["code"] == "warn.length_missing" for w in entry["warnings"])
    warning_line = next(ln for ln in stdout.splitlines() if "length.bin" in ln)
    assert bool(HANGUL.search(warning_line)) is (lang == "ko")
