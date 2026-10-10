"""A Picard-compatible subset of TaggerScript.

Syntax:
    %name%              variable (empty string when unset)
    $func(arg1,arg2)    function call; arguments are scripts themselves
    \\x                  literal x (escape $ % ( ) , \\), \\n newline, \\t tab
    anything else       literal text

Like Picard, an empty string is "false" and anything else is "true", and
``$if``/``$if2``/``$and``/``$or`` only evaluate the arguments they need.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass


class ScriptError(Exception):
    def __init__(self, message: str, pos: int | None = None) -> None:
        super().__init__(message if pos is None else f"{message} (at character {pos + 1})")
        self.pos = pos


# --------------------------------------------------------------------- AST
@dataclass
class Text:
    value: str


@dataclass
class Var:
    name: str


@dataclass
class Call:
    name: str
    args: list[list]   # each arg is a list of nodes
    pos: int


# ------------------------------------------------------------------ parser
_ESCAPES = {"n": "\n", "t": "\t"}
_NAME_RE = re.compile(r"[A-Za-z0-9_]+")


class _Parser:
    def __init__(self, src: str) -> None:
        self.src = src
        self.i = 0

    def parse(self) -> list:
        nodes = self._sequence(stop=())
        if self.i < len(self.src):  # stray ')' or ','
            raise ScriptError(f"Unexpected {self.src[self.i]!r}", self.i)
        return nodes

    def _sequence(self, stop: tuple[str, ...]) -> list:
        nodes: list = []
        buf: list[str] = []

        def flush():
            if buf:
                nodes.append(Text("".join(buf)))
                buf.clear()

        src = self.src
        while self.i < len(src):
            c = src[self.i]
            if c in stop:
                break
            if c == "\\":
                if self.i + 1 >= len(src):
                    raise ScriptError("Unfinished escape sequence", self.i)
                nxt = src[self.i + 1]
                buf.append(_ESCAPES.get(nxt, nxt))
                self.i += 2
            elif c == "%":
                end = src.find("%", self.i + 1)
                if end < 0:
                    raise ScriptError("Unclosed %variable%", self.i)
                name = src[self.i + 1:end]
                if not name:
                    raise ScriptError("Empty variable name %%", self.i)
                flush()
                nodes.append(Var(name.lower()))
                self.i = end + 1
            elif c == "$":
                m = _NAME_RE.match(src, self.i + 1)
                if not m or m.end() >= len(src) or src[m.end()] != "(":
                    raise ScriptError("Expected $function(…)", self.i)
                flush()
                start = self.i
                self.i = m.end() + 1
                args = []
                while True:
                    args.append(self._sequence(stop=(",", ")")))
                    if self.i >= len(src):
                        raise ScriptError(f"Missing ')' for ${m.group(0)}", start)
                    if src[self.i] == ")":
                        self.i += 1
                        break
                    self.i += 1  # ','
                if args == [[]]:
                    args = []
                nodes.append(Call(m.group(0).lower(), args, start))
            elif c in (",", ")") and not stop:
                buf.append(c)  # literal at top level
                self.i += 1
            else:
                buf.append(c)
                self.i += 1
        flush()
        return nodes


def parse(src: str) -> list:
    return _Parser(src).parse()


# --------------------------------------------------------------- evaluator
Thunk = Callable[[], str]


def _int(s: str, default: int = 0) -> int:
    try:
        return int(str(s).strip())
    except ValueError:
        try:
            return int(float(str(s).strip()))
        except ValueError:
            return default


def _bool(v: bool) -> str:
    return "1" if v else ""


def _title(text: str) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in text.split(" "))


def _first_alpha(text: str, nonalpha: str = "#") -> str:
    if not text:
        return nonalpha
    ch = unicodedata.normalize("NFKD", text)[0]
    return ch.upper() if ch.isalpha() else nonalpha


def _swapprefix(text: str, *prefixes: str) -> str:
    for p in prefixes or ("A", "The"):
        if text.lower().startswith(p.lower() + " "):
            return f"{text[len(p) + 1:]}, {text[:len(p)]}"
    return text


def _delprefix(text: str, *prefixes: str) -> str:
    for p in prefixes or ("A", "The"):
        if text.lower().startswith(p.lower() + " "):
            return text[len(p) + 1:]
    return text


def _cmp(op):
    def f(a: str, b: str) -> str:
        try:
            x, y = float(a), float(b)
        except ValueError:
            return ""
        return _bool(op(x, y))
    return f


def _arith(op):
    def f(*xs: str) -> str:
        if not xs:
            return ""
        try:
            acc = _int(xs[0])
            for x in xs[1:]:
                acc = op(acc, _int(x))
            return str(acc)
        except ZeroDivisionError:
            return ""
    return f


# Functions receiving already-evaluated string arguments.
STRICT: dict[str, Callable[..., str]] = {
    "noop": lambda *a: "",
    "left": lambda t, n: t[:max(_int(n), 0)],
    "right": lambda t, n: t[-_int(n):] if _int(n) > 0 else "",
    "lower": lambda t: t.lower(),
    "upper": lambda t: t.upper(),
    "title": _title,
    "num": lambda n, ln: str(_int(n)).zfill(_int(ln)),
    "pad": lambda t, ln, ch=" ": t.rjust(_int(ln), (ch or " ")[0]),
    "replace": lambda t, s, r="": t.replace(s, r) if s else t,
    "rreplace": lambda t, p, r="": re.sub(p, r, t),
    "rsearch": lambda t, p: (lambda m: (m.group(1) if m and m.groups() else
                                         (m.group(0) if m else "")))(re.search(p, t)),
    "trim": lambda t, ch=None: t.strip(ch) if ch else t.strip(),
    "strip": lambda t: " ".join(t.split()),
    "len": lambda t: str(len(t)),
    "truncate": lambda t, n: t[:max(_int(n), 0)].rstrip(),
    "firstwords": lambda t, n: (t if len(t) <= _int(n) else
                                t[:_int(n) + 1].rsplit(" ", 1)[0][:_int(n)]),
    "firstalphachar": _first_alpha,
    "initials": lambda t: "".join(w[0] for w in t.split() if w[:1].isalpha()),
    "swapprefix": _swapprefix,
    "delprefix": _delprefix,
    "eq": lambda a, b: _bool(a == b),
    "ne": lambda a, b: _bool(a != b),
    "not": lambda a: _bool(not a),
    "lt": _cmp(lambda a, b: a < b),
    "lte": _cmp(lambda a, b: a <= b),
    "gt": _cmp(lambda a, b: a > b),
    "gte": _cmp(lambda a, b: a >= b),
    "add": _arith(lambda a, b: a + b),
    "sub": _arith(lambda a, b: a - b),
    "mul": _arith(lambda a, b: a * b),
    "div": _arith(lambda a, b: a // b),
    "mod": _arith(lambda a, b: a % b),
    "in": lambda t, s: _bool(s in t),
    "startswith": lambda t, s: _bool(t.startswith(s)),
    "endswith": lambda t, s: _bool(t.endswith(s)),
    "reverse": lambda t: t[::-1],
    "repeat": lambda t, n: t * max(_int(n), 0),
}

ARITY = {  # (min, max) argument counts; None = unlimited
    "noop": (0, None), "left": (2, 2), "right": (2, 2), "lower": (1, 1), "upper": (1, 1),
    "title": (1, 1), "num": (2, 2), "pad": (2, 3), "replace": (2, 3), "rreplace": (2, 3),
    "rsearch": (2, 2), "trim": (1, 2), "strip": (1, 1), "len": (1, 1), "truncate": (2, 2),
    "firstwords": (2, 2), "firstalphachar": (1, 2), "initials": (1, 1),
    "swapprefix": (1, None), "delprefix": (1, None), "eq": (2, 2), "ne": (2, 2), "not": (1, 1),
    "lt": (2, 2), "lte": (2, 2), "gt": (2, 2), "gte": (2, 2), "add": (1, None),
    "sub": (1, None), "mul": (1, None), "div": (1, None), "mod": (1, None), "in": (2, 2),
    "startswith": (2, 2), "endswith": (2, 2), "reverse": (1, 1), "repeat": (2, 2),
    # lazy / variable functions
    "if": (2, 3), "if2": (1, None), "and": (1, None), "or": (1, None), "set": (2, 2),
    "get": (1, 1), "unset": (1, 1), "delete": (1, 1), "copy": (2, 2),
}

FUNCTIONS = sorted(ARITY)


class Evaluator:
    def __init__(self, variables: dict[str, str]) -> None:
        self.vars = {k.lower(): v for k, v in variables.items()}

    def run(self, nodes: list) -> str:
        return "".join(self._node(n) for n in nodes)

    def _node(self, n) -> str:
        if isinstance(n, Text):
            return n.value
        if isinstance(n, Var):
            return self.vars.get(n.name, "")
        return self._call(n)

    def _call(self, c: Call) -> str:
        if c.name not in ARITY:
            raise ScriptError(f"Unknown function ${c.name}", c.pos)
        lo, hi = ARITY[c.name]
        if len(c.args) < lo or (hi is not None and len(c.args) > hi):
            want = f"{lo}" if lo == hi else f"{lo}–{hi if hi is not None else '…'}"
            raise ScriptError(f"${c.name} takes {want} argument(s), got {len(c.args)}", c.pos)
        arg = [lambda a=a: self.run(a) for a in c.args]
        name = c.name
        if name == "if":
            return arg[1]() if arg[0]() else (arg[2]() if len(arg) > 2 else "")
        if name == "if2":
            for a in arg:
                v = a()
                if v:
                    return v
            return ""
        if name == "and":
            return _bool(all(a() for a in arg))
        if name == "or":
            return _bool(any(a() for a in arg))
        if name == "set":
            self.vars[arg[0]().lower()] = arg[1]()
            return ""
        if name == "get":
            return self.vars.get(arg[0]().lower(), "")
        if name in ("unset", "delete"):
            self.vars.pop(arg[0]().lower(), None)
            return ""
        if name == "copy":
            self.vars[arg[0]().lower()] = self.vars.get(arg[1]().lower(), "")
            return ""
        try:
            return STRICT[name](*(a() for a in arg))
        except re.error as e:
            raise ScriptError(f"${name}: invalid regular expression ({e})", c.pos) from e


def evaluate(src: str, variables: dict[str, str]) -> str:
    return Evaluator(variables).run(parse(src))
