"""Read ``index_metadata.pickle`` WITHOUT unpickling it.

A pickle file can run arbitrary code when loaded, so this module never calls
``pickle.load``. It walks the opcode stream with :mod:`pickletools`, accepts only
the small set of opcodes that Chroma's own files use (dicts, tuples, strings,
integers, memo references and one plain object), and refuses everything else.
Class names are recorded as plain strings and never imported.
"""
from __future__ import annotations

import pickletools
from typing import Any

from .errors import UnsafePickleError

ALLOWED_OPCODES = frozenset(
    {
        "PROTO", "FRAME", "STOP",
        # containers
        "EMPTY_DICT", "EMPTY_LIST", "EMPTY_TUPLE", "MARK", "SETITEM", "SETITEMS",
        "APPEND", "APPENDS", "TUPLE", "TUPLE1", "TUPLE2", "TUPLE3",
        # scalars
        "SHORT_BINUNICODE", "BINUNICODE", "BINUNICODE8", "BININT", "BININT1", "BININT2",
        "LONG1", "BINFLOAT", "NONE", "NEWTRUE", "NEWFALSE",
        # memo
        "MEMOIZE", "BINPUT", "LONG_BINPUT", "BINGET", "LONG_BINGET",
        # a plain object: the class name is only recorded, never imported
        "STACK_GLOBAL", "NEWOBJ", "BUILD",
    }
)

_SCALARS = {
    "SHORT_BINUNICODE", "BINUNICODE", "BINUNICODE8", "BININT", "BININT1", "BININT2",
    "LONG1", "BINFLOAT",
}


class _Obj:
    """Stand-in for the object Chroma pickles (``PersistentData``): a name plus its state."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.state: Any = None


def parse_index_metadata(raw: bytes) -> tuple[dict[str, Any], str | None]:
    """Return ``(state, class_name)``; ``class_name`` is ``None`` for a plain dict.

    Raises :class:`UnsafePickleError` naming the first opcode outside the allow-list.
    """
    stack: list[Any] = []
    marks: list[int] = []
    memo: dict[int, Any] = {}
    try:
        for op, arg, _pos in pickletools.genops(raw):
            name = op.name
            if name not in ALLOWED_OPCODES:
                raise UnsafePickleError("err.unsafe_pickle", opcode=name)
            if name in ("PROTO", "FRAME"):
                continue
            if name in _SCALARS:
                stack.append(arg)
            elif name == "NONE":
                stack.append(None)
            elif name in ("NEWTRUE", "NEWFALSE"):
                stack.append(name == "NEWTRUE")
            elif name == "EMPTY_DICT":
                stack.append({})
            elif name == "EMPTY_LIST":
                stack.append([])
            elif name == "EMPTY_TUPLE":
                stack.append(())
            elif name == "MARK":
                marks.append(len(stack))
            elif name == "SETITEMS":
                start = marks.pop()
                items = stack[start:]
                del stack[start:]
                target = stack[-1]
                for i in range(0, len(items), 2):
                    target[items[i]] = items[i + 1]
            elif name == "SETITEM":
                value = stack.pop()
                key = stack.pop()
                stack[-1][key] = value
            elif name == "APPEND":
                value = stack.pop()
                stack[-1].append(value)
            elif name == "APPENDS":
                start = marks.pop()
                items = stack[start:]
                del stack[start:]
                stack[-1].extend(items)
            elif name == "TUPLE":
                start = marks.pop()
                items = tuple(stack[start:])
                del stack[start:]
                stack.append(items)
            elif name in ("TUPLE1", "TUPLE2", "TUPLE3"):
                count = int(name[-1])
                items = tuple(stack[-count:])
                del stack[-count:]
                stack.append(items)
            elif name == "MEMOIZE":
                memo[len(memo)] = stack[-1]
            elif name in ("BINPUT", "LONG_BINPUT"):
                memo[arg] = stack[-1]
            elif name in ("BINGET", "LONG_BINGET"):
                stack.append(memo[arg])
            elif name == "STACK_GLOBAL":
                attr = stack.pop()
                module = stack.pop()
                stack.append(("GLOBAL", module, attr))  # recorded only, never imported
            elif name == "NEWOBJ":
                stack.pop()  # constructor arguments
                cls = stack.pop()
                stack.append(_Obj(f"{cls[1]}.{cls[2]}"))
            elif name == "BUILD":
                state = stack.pop()
                stack[-1].state = state
            elif name == "STOP":
                break
    except UnsafePickleError:
        raise
    except (IndexError, KeyError, TypeError, AttributeError, ValueError) as exc:
        raise UnsafePickleError("err.pickle_malformed", detail=str(exc)) from exc
    if not stack:
        raise UnsafePickleError("err.pickle_malformed", detail="empty stack")
    top = stack[-1]
    if isinstance(top, _Obj):
        state = top.state
        if not isinstance(state, dict):
            raise UnsafePickleError("err.pickle_malformed", detail="object without dict state")
        return state, top.name
    if not isinstance(top, dict):
        raise UnsafePickleError("err.pickle_malformed", detail="top level is not a dict")
    return top, None
