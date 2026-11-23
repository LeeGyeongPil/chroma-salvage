"""All user-visible text lives here, in English and Korean with identical keys."""
from __future__ import annotations

import os
from typing import Callable, Mapping

LANGS = ("en", "ko")
ENV_VAR = "CHROMA_SALVAGE_LANG"

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        # errors (exit code 2 = input problem, 3 = unsupported or unsafe format)
        "err.path_missing": "Path not found: {path}. Pass the folder you gave to chromadb.PersistentClient(path=...).",
        "err.not_a_directory": "{path} is not a folder. Pass the Chroma persist folder, not a single file.",
        "err.no_sqlite": "No {name} in {path}. This is not a Chroma persist folder (or the wrong level - look one folder deeper).",
        "err.not_sqlite": "{path} cannot be read as a SQLite database ({detail}).",
        "err.no_migrations": "{path} has no 'migrations' table, so it was not written by chromadb. Nothing was read.",
        "err.unknown_collection": "No collection named '{name}'. Collections in this folder: {known}.",
        "err.out_not_dir": "Output path {path} exists and is not a folder. Choose another -o path.",
        "err.out_not_empty": "Output folder {path} is not empty. Choose an empty folder or add --force; existing files were left untouched.",
        "err.unsafe_pickle": "index_metadata.pickle uses opcode {opcode}, which is not on the allow-list. Refusing to read it; nothing was executed. If you trust the file, inspect it with pickletools instead.",
        "err.pickle_malformed": "index_metadata.pickle is not in the expected shape ({detail}). Refusing to guess.",
        "err.pickle_missing": "{file} is missing but the HNSW files hold {count} elements, so ids cannot be mapped. The folder looks damaged; restore index_metadata.pickle from a backup.",
        "err.hnsw_file_missing": "HNSW file not found: {file}. The folder looks incomplete.",
        "err.hnsw_header_size": "{file} has {size} bytes, expected {expected}. This is not a chroma-hnswlib header; refusing to read.",
        "err.hnsw_persist_version": "{file} declares persist_version {version}, this tool reads version {supported}. A newer format needs a newer chroma-salvage.",
        "err.hnsw_header_inconsistent": "{file} has inconsistent offsets; refusing to read.",
        "err.hnsw_data_size": "{file} has {size} bytes but {count} elements need {expected}. The index file is truncated; refusing to export wrong values.",
        "err.wal_encoding": "Write-ahead log row {seq} uses vector encoding {encoding}; only FLOAT32 is supported.",
        "err.wal_vector_size": "Write-ahead log row {seq} has a vector of {size} bytes, not a multiple of 4.",
        "err.dim_mismatch": "HNSW header says dimension {header} but the collection says {db}. Refusing to read.",
        "err.usage": "{detail}",
        # warnings
        "warn.length_short": "{file} is shorter than the element count; cosine vectors read from the index file stay normalised (unit length).",
        "warn.length_missing": "{file} is missing; cosine vectors read from the index file stay normalised (unit length).",
        "warn.no_hnsw_files": "Vector segment {segment} has no HNSW files; using the write-ahead log only.",
        "warn.unmapped_labels": "{count} HNSW elements have no id in index_metadata.pickle and were skipped.",
        "warn.norm_missing": "Some cosine elements have no stored norm; they stay normalised.",
        "warn.vector_without_record": "{count} ids have a vector but no document/metadata row; exported with document null.",
        "warn.record_without_vector": "{count} ids have a document/metadata row but no vector; exported with embedding null.",
        "warn.unknown_newer": "This folder is newer than any layout this tool was tested with. Results are best-effort; verify them.",
        # inspect
        "insp.folder": "Chroma folder: {path}",
        "insp.band": "Version band: {band}  (migrations: sysdb {sysdb}, metadb {metadb}, embeddings_queue {queue})",
        "insp.opens_title": "Folder can be opened by:",
        "insp.opens_ok": "chromadb {band} as is",
        "insp.opens_unknown": "unknown - the layout is newer than this tool knows",
        "insp.opens_migrates": "chromadb {band} opens it too but migrates it irreversibly - export first",
        "insp.opens_fails": "chromadb {band} fails with: {error}",
        "insp.collections": "Collections: {n}",
        "insp.wal_legend": "WAL = log rows not yet in the HNSW files (ADD/UPDATE/UPSERT/DELETE).",
        "insp.space_from_schema": "[{name}] distance function '{space}' was read from collections.schema_str.",
        "insp.orphans": "Folders not referenced by the segments table: {n}",
        "col.name": "name",
        "col.dim": "dim",
        "col.space": "space",
        "col.snapshot": "HNSW snapshot",
        "col.deleted": "deleted",
        "col.wal": "WAL pending",
        "col.pickle": "pickle",
        "col.final": "final",
        "pickle.present": "present",
        "pickle.missing": "missing",
        "pickle.n/a": "n/a",
        # export
        "export.title": "Exported {n} collection(s) to {out}",
        "export.row": "  {name}: {count} records ({hnsw} from HNSW, {wal} from WAL) -> {file}",
        "export.manifest": "Manifest: {path}",
        "export.warning": "  warning [{name}]: {message}",
        # command line
        "help.usage": "usage: ",
        "help.description": "Read a Chroma persist folder without chromadb: show which version wrote it and export ids, documents, metadata and embeddings as JSONL. The folder is never modified.",
        "help.positionals": "arguments",
        "help.options": "options",
        "help.commands": "commands",
        "help.help": "show this help and exit",
        "help.version": "show the version and exit",
        "help.lang": "output language (default: CHROMA_SALVAGE_LANG, then LC_ALL/LC_MESSAGES/LANG, else en)",
        "help.inspect": "show the version band, openable chromadb versions and per-collection counts",
        "help.export": "write each collection as JSONL plus manifest.json",
        "help.path": "Chroma persist folder (the one containing chroma.sqlite3)",
        "help.json": "print the report as JSON",
        "help.out": "output folder (must be empty unless --force)",
        "help.collection": "export only this collection (repeatable)",
        "help.normalized": "keep cosine vectors normalised instead of restoring their original length",
        "help.force": "allow a non-empty output folder (files with the same name are overwritten)",
        "help.exit_codes": "exit codes: 0 ok, 2 bad input, 3 unsupported or unsafe format",
        "cli.usage_error": "Invalid command line: {detail}",
        "cli.arg_required": "the following arguments are required: {names}",
        "cli.arg_invalid_choice": "argument {arg}: invalid choice: {value} (choose from {choices})",
        "cli.arg_invalid_choice_short": "argument {arg}: invalid choice: {value}",
        "cli.arg_expected_one": "argument {arg}: expected one argument",
        "cli.arg_unrecognized": "unrecognized arguments: {names}",
        "cli.arg_ambiguous": "ambiguous option: {name}",
        "cli.error": "error: {message}",
        "err.os_error": "A file operation failed: {detail}. Check the paths and permissions.",
    },
    "ko": {
        "err.path_missing": "경로를 찾을 수 없습니다: {path}. chromadb.PersistentClient(path=...) 에 넘긴 폴더를 지정하세요.",
        "err.not_a_directory": "{path} 은(는) 폴더가 아닙니다. 파일이 아니라 Chroma 저장 폴더를 지정하세요.",
        "err.no_sqlite": "{path} 에 {name} 이(가) 없습니다. Chroma 저장 폴더가 아니거나 한 단계 위입니다 - 한 폴더 아래를 확인하세요.",
        "err.not_sqlite": "{path} 을(를) SQLite 데이터베이스로 읽을 수 없습니다 ({detail}).",
        "err.no_migrations": "{path} 에 'migrations' 표가 없어 chromadb 가 쓴 파일이 아닙니다. 아무것도 읽지 않았습니다.",
        "err.unknown_collection": "'{name}' 이름의 컬렉션이 없습니다. 이 폴더의 컬렉션: {known}.",
        "err.out_not_dir": "출력 경로 {path} 이(가) 이미 있고 폴더가 아닙니다. 다른 -o 경로를 고르세요.",
        "err.out_not_empty": "출력 폴더 {path} 이(가) 비어 있지 않습니다. 빈 폴더를 쓰거나 --force 를 붙이세요. 기존 파일은 건드리지 않았습니다.",
        "err.unsafe_pickle": "index_metadata.pickle 이 허용 목록에 없는 opcode {opcode} 를 씁니다. 읽기를 거부했고 아무것도 실행하지 않았습니다. 파일을 신뢰한다면 pickletools 로 직접 살펴보세요.",
        "err.pickle_malformed": "index_metadata.pickle 이 예상한 모양이 아닙니다 ({detail}). 추측하지 않고 거부합니다.",
        "err.pickle_missing": "{file} 이(가) 없는데 HNSW 파일에는 원소가 {count}개 있어 id 를 연결할 수 없습니다. 폴더가 손상된 듯합니다. 백업에서 index_metadata.pickle 을 복원하세요.",
        "err.hnsw_file_missing": "HNSW 파일을 찾을 수 없습니다: {file}. 폴더가 불완전해 보입니다.",
        "err.hnsw_header_size": "{file} 은(는) {size} 바이트이며 {expected} 바이트여야 합니다. chroma-hnswlib 헤더가 아니어서 읽기를 거부합니다.",
        "err.hnsw_persist_version": "{file} 의 persist_version 은 {version} 이고 이 도구는 버전 {supported} 만 읽습니다. 더 새로운 형식은 더 새로운 chroma-salvage 가 필요합니다.",
        "err.hnsw_header_inconsistent": "{file} 의 오프셋이 서로 맞지 않아 읽기를 거부합니다.",
        "err.hnsw_data_size": "{file} 은(는) {size} 바이트인데 원소 {count}개에는 {expected} 바이트가 필요합니다. 색인 파일이 잘렸습니다. 틀린 값을 내보내지 않기 위해 거부합니다.",
        "err.wal_encoding": "쓰기 로그 {seq} 행의 벡터 인코딩 {encoding} 은 지원하지 않습니다. FLOAT32 만 지원합니다.",
        "err.wal_vector_size": "쓰기 로그 {seq} 행의 벡터가 {size} 바이트로 4의 배수가 아닙니다.",
        "err.dim_mismatch": "HNSW 헤더는 차원 {header}, 컬렉션은 {db} 입니다. 읽기를 거부합니다.",
        "err.usage": "{detail}",
        "warn.length_short": "{file} 이(가) 원소 수보다 짧아 색인 파일에서 읽은 cosine 벡터는 정규화(길이 1)된 채로 둡니다.",
        "warn.length_missing": "{file} 이(가) 없어 색인 파일에서 읽은 cosine 벡터는 정규화(길이 1)된 채로 둡니다.",
        "warn.no_hnsw_files": "벡터 세그먼트 {segment} 에 HNSW 파일이 없어 쓰기 로그만 사용합니다.",
        "warn.unmapped_labels": "HNSW 원소 {count}개가 index_metadata.pickle 에 id 가 없어 건너뛰었습니다.",
        "warn.norm_missing": "일부 cosine 원소에 저장된 노름이 없어 정규화된 채로 둡니다.",
        "warn.vector_without_record": "벡터는 있지만 문서·메타데이터 행이 없는 id 가 {count}개 있어 document 를 null 로 내보냅니다.",
        "warn.record_without_vector": "문서·메타데이터 행은 있지만 벡터가 없는 id 가 {count}개 있어 embedding 을 null 로 내보냅니다.",
        "warn.unknown_newer": "이 도구가 시험한 어떤 형식보다 새로운 폴더입니다. 결과는 최선 추정이니 직접 확인하세요.",
        "insp.folder": "Chroma 폴더: {path}",
        "insp.band": "버전대: {band}  (migrations: sysdb {sysdb}, metadb {metadb}, embeddings_queue {queue})",
        "insp.opens_title": "열 수 있는 chromadb:",
        "insp.opens_ok": "chromadb {band} 로 그대로 열림",
        "insp.opens_unknown": "알 수 없음 - 이 도구가 아는 것보다 새로운 형식",
        "insp.opens_migrates": "chromadb {band} 로도 열리지만 되돌릴 수 없게 이전됨 - 먼저 export",
        "insp.opens_fails": "chromadb {band} 는 다음 오류로 실패: {error}",
        "insp.collections": "컬렉션: {n}개",
        "insp.wal_legend": "WAL = 아직 HNSW 파일에 반영되지 않은 로그 행 (ADD/UPDATE/UPSERT/DELETE).",
        "insp.space_from_schema": "[{name}] 거리 함수 '{space}' 는 collections.schema_str 에서 읽었습니다.",
        "insp.orphans": "segments 표가 가리키지 않는 폴더: {n}개",
        "col.name": "이름",
        "col.dim": "차원",
        "col.space": "거리",
        "col.snapshot": "HNSW 스냅숏",
        "col.deleted": "삭제표시",
        "col.wal": "WAL 대기",
        "col.pickle": "pickle",
        "col.final": "최종",
        "pickle.present": "있음",
        "pickle.missing": "없음",
        "pickle.n/a": "해당 없음",
        "export.title": "컬렉션 {n}개를 {out} 에 내보냈습니다",
        "export.row": "  {name}: {count}건 (HNSW {hnsw}, WAL {wal}) -> {file}",
        "export.manifest": "매니페스트: {path}",
        "export.warning": "  경고 [{name}]: {message}",
        "help.usage": "사용법: ",
        "help.description": "chromadb 없이 Chroma 저장 폴더를 읽어, 어느 버전이 썼는지 보여 주고 id·문서·메타데이터·임베딩을 JSONL 로 내보냅니다. 폴더는 절대 수정하지 않습니다.",
        "help.positionals": "인자",
        "help.options": "옵션",
        "help.commands": "명령",
        "help.help": "도움말을 보여 주고 종료",
        "help.version": "버전을 보여 주고 종료",
        "help.lang": "출력 언어 (기본: CHROMA_SALVAGE_LANG, 다음 LC_ALL/LC_MESSAGES/LANG, 아니면 en)",
        "help.inspect": "버전대, 열 수 있는 chromadb 버전, 컬렉션별 개수를 보여 줌",
        "help.export": "컬렉션마다 JSONL 과 manifest.json 을 씀",
        "help.path": "Chroma 저장 폴더 (chroma.sqlite3 가 들어 있는 폴더)",
        "help.json": "보고서를 JSON 으로 출력",
        "help.out": "출력 폴더 (--force 가 없으면 비어 있어야 함)",
        "help.collection": "이 컬렉션만 내보냄 (여러 번 지정 가능)",
        "help.normalized": "cosine 벡터를 원래 길이로 복원하지 않고 정규화된 채로 둠",
        "help.force": "비어 있지 않은 출력 폴더 허용 (같은 이름 파일은 덮어씀)",
        "help.exit_codes": "종료 코드: 0 성공, 2 입력 오류, 3 지원하지 않거나 안전하지 않은 형식",
        "cli.usage_error": "명령줄이 올바르지 않습니다: {detail}",
        "cli.arg_required": "다음 인자가 필요합니다: {names}",
        "cli.arg_invalid_choice": "인자 {arg}: 올바르지 않은 선택입니다: {value} (선택 가능: {choices})",
        "cli.arg_invalid_choice_short": "인자 {arg}: 올바르지 않은 선택입니다: {value}",
        "cli.arg_expected_one": "인자 {arg}: 값이 하나 필요합니다",
        "cli.arg_unrecognized": "알 수 없는 인자입니다: {names}",
        "cli.arg_ambiguous": "모호한 옵션입니다: {name}",
        "cli.error": "오류: {message}",
        "err.os_error": "파일 작업에 실패했습니다: {detail}. 경로와 권한을 확인하세요.",
    },
}


def render(lang: str, key: str, **params: object) -> str:
    return MESSAGES[lang][key].format(**params)


def translator(lang: str) -> Callable[..., str]:
    def t(key: str, **params: object) -> str:
        return render(lang, key, **params)

    return t


def _from_locale(value: str) -> str:
    return "ko" if value.strip().lower().startswith("ko") else "en"


def resolve_lang(cli_value: str | None = None, env: Mapping[str, str] | None = None) -> str:
    """``--lang`` > CHROMA_SALVAGE_LANG > LC_ALL > LC_MESSAGES > LANG; anything not Korean is English."""
    env = os.environ if env is None else env
    if cli_value in LANGS:
        return cli_value  # type: ignore[return-value]
    for name in (ENV_VAR, "LC_ALL", "LC_MESSAGES", "LANG"):
        value = env.get(name, "")
        if value.strip():
            return _from_locale(value)
    return "en"
