"""Command line: ``chroma-salvage inspect|export``."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Mapping, Sequence

from . import __version__
from .errors import SalvageError
from .export import export, select_collections
from .i18n import LANGS, render, resolve_lang, translator
from .reconstruct import load_collection
from .report import build_report, render_text
from .sqlite_reader import open_source


_ARGPARSE_PATTERNS = (
    (re.compile(r"^the following arguments are required: (?P<names>.+)$"), "cli.arg_required"),
    (re.compile(r"^argument (?P<arg>.+?): invalid choice: (?P<value>.+?) \(choose from (?P<choices>.+)\)$"),
     "cli.arg_invalid_choice"),
    (re.compile(r"^argument (?P<arg>.+?): invalid choice: (?P<value>.+)$"), "cli.arg_invalid_choice_short"),
    (re.compile(r"^argument (?P<arg>.+?): expected one argument$"), "cli.arg_expected_one"),
    (re.compile(r"^unrecognized arguments: (?P<names>.+)$"), "cli.arg_unrecognized"),
    (re.compile(r"^ambiguous option: (?P<name>\S+).*$"), "cli.arg_ambiguous"),
)


def _localize_argparse(message: str, t) -> str:  # type: ignore[no-untyped-def]
    """Map argparse's English messages to the message table (unknown messages stay as they are)."""
    for pattern, key in _ARGPARSE_PATTERNS:
        m = pattern.match(message)
        if m:
            return t(key, **m.groupdict())
    return message


def build_parser(lang: str) -> argparse.ArgumentParser:
    """Build the parser with help text in ``lang`` (argparse fixes help text at build time)."""
    t = translator(lang)

    class Formatter(argparse.HelpFormatter):
        def add_usage(self, usage, actions, groups, prefix=None):  # type: ignore[no-untyped-def]
            if prefix is None:  # subparsers pass prefix="" to build their prog; keep that empty
                prefix = t("help.usage")
            super().add_usage(usage, actions, groups, prefix=prefix)

    class Parser(argparse.ArgumentParser):
        def error(self, message: str):  # type: ignore[no-untyped-def]
            self.print_usage(sys.stderr)
            detail = _localize_argparse(message, t)
            sys.stderr.write(t("cli.error", message=t("cli.usage_error", detail=detail)) + "\n")
            raise SystemExit(2)

    def make(parent=None, **kwargs):  # type: ignore[no-untyped-def]
        factory = parent.add_parser if parent else Parser
        p = factory(add_help=False, formatter_class=Formatter, **kwargs)
        p._positionals.title = t("help.positionals")
        p._optionals.title = t("help.options")
        p.add_argument("-h", "--help", action="help", help=t("help.help"))
        return p

    parser = make(prog="chroma-salvage", description=t("help.description"), epilog=t("help.exit_codes"))
    parser.add_argument("--version", action="version", version=f"chroma-salvage {__version__}",
                        help=t("help.version"))
    parser.add_argument("--lang", choices=LANGS, help=t("help.lang"))
    sub = parser.add_subparsers(dest="command", metavar="{inspect,export}", title=t("help.commands"),
                                parser_class=Parser)
    sub.required = True

    p_inspect = make(sub, name="inspect", help=t("help.inspect"), description=t("help.inspect"))
    p_inspect.add_argument("path", help=t("help.path"))
    p_inspect.add_argument("--json", action="store_true", help=t("help.json"))
    p_inspect.add_argument("--lang", choices=LANGS, default=argparse.SUPPRESS, help=t("help.lang"))

    p_export = make(sub, name="export", help=t("help.export"), description=t("help.export"))
    p_export.add_argument("path", help=t("help.path"))
    p_export.add_argument("-o", "--out", required=True, help=t("help.out"))
    p_export.add_argument("--collection", action="append", metavar="NAME", help=t("help.collection"))
    p_export.add_argument("--normalized", action="store_true", help=t("help.normalized"))
    p_export.add_argument("--force", action="store_true", help=t("help.force"))
    p_export.add_argument("--lang", choices=LANGS, default=argparse.SUPPRESS, help=t("help.lang"))
    return parser


def _early_lang(argv: Sequence[str], env: Mapping[str, str]) -> str:
    """Find ``--lang`` before the real parse, so even ``--help`` and usage errors are localised."""
    value = None
    for i, arg in enumerate(argv):
        if arg == "--lang" and i + 1 < len(argv):
            value = argv[i + 1]
        elif arg.startswith("--lang="):
            value = arg.split("=", 1)[1]
    return resolve_lang(value, env)


def run_inspect(args: argparse.Namespace, lang: str) -> str:
    t = translator(lang)
    with open_source(args.path) as source:
        states = [load_collection(source, info) for info in source.collections()]
        report = build_report(source, states, lang)
    if args.json:
        return json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    return render_text(report, t)


def run_export(args: argparse.Namespace, lang: str) -> str:
    t = translator(lang)
    out_dir = Path(args.out)
    with open_source(args.path) as source:
        select_collections(source, args.collection)  # fail early on a wrong name
        manifest = export(source, out_dir, args.collection, keep_normalized=args.normalized,
                          force=args.force)
    lines = [t("export.title", n=len(manifest["collections"]), out=str(out_dir))]
    for c in manifest["collections"]:
        lines.append(t("export.row", name=c["name"], count=c["count"], hnsw=c["from_hnsw"],
                       wal=c["from_wal"], file=c["file"]))
        for w in c["warnings"]:
            lines.append(t("export.warning", name=c["name"], message=render(lang, w["code"], **w["params"])))
    lines.append(t("export.manifest", path=str(out_dir / "manifest.json")))
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    import os

    argv = list(sys.argv[1:] if argv is None else argv)
    env = os.environ if env is None else env
    lang = _early_lang(argv, env)
    parser = build_parser(lang)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    lang = resolve_lang(getattr(args, "lang", None) or None, env)
    t = translator(lang)
    try:
        text = run_inspect(args, lang) if args.command == "inspect" else run_export(args, lang)
    except SalvageError as exc:
        sys.stderr.write(t("cli.error", message=render(lang, exc.key, **exc.params)) + "\n")
        return exc.exit_code
    except OSError as exc:
        sys.stderr.write(t("cli.error", message=t("err.os_error", detail=str(exc))) + "\n")
        return 2
    sys.stdout.write(text)
    return 0
