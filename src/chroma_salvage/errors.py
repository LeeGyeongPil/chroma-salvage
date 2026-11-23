"""Exceptions with stable message keys so the CLI can print them in either language."""
from __future__ import annotations

from typing import Any


class SalvageError(Exception):
    """Base class. ``key`` selects the message, ``params`` fill its placeholders."""

    exit_code = 1

    def __init__(self, key: str, **params: Any) -> None:
        self.key = key
        self.params = params
        super().__init__(key)

    def __str__(self) -> str:  # English text; the CLI renders its own language
        from .i18n import render

        return render("en", self.key, **self.params)


class InputError(SalvageError):
    """The user pointed at something that is not a usable Chroma folder (exit code 2)."""

    exit_code = 2


class UnsupportedFormatError(SalvageError):
    """The folder is a Chroma folder, but in a format that cannot be read safely (exit code 3)."""

    exit_code = 3


class UnsafePickleError(UnsupportedFormatError):
    """``index_metadata.pickle`` contains an opcode outside the allow-list (exit code 3)."""
