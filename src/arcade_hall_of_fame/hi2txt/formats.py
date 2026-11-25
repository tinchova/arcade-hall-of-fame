"""Operaciones de formato de hi2txt (``<format>`` y formatos implícitos).

Implementación propia a partir de la referencia pública del formato
(https://greatstoneex.github.io/hi2txt-doc/doc/xml.html). Las operaciones que no
están implementadas se detectan al cargar la definición, no al leer un archivo.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Callable, Union

from ..models import FormatError

Value = Union[int, float, str, None]


# --- Modelo -----------------------------------------------------------------


@dataclass(frozen=True)
class SubColumn:
    """``<column>``, ``<field>`` o ``<txt>`` dentro de una operación."""

    kind: str  # "column", "field" o "txt"
    source: str | None  # atributo src, o id si no hay src
    formats: tuple[str, ...]
    content: str | None


@dataclass(frozen=True)
class Operation:
    kind: str
    text: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: tuple[SubColumn, ...] = ()


@dataclass(frozen=True)
class NamedFormat:
    id: str
    operations: tuple[Operation, ...]
    apply_to_char: bool = False
    subcolumns_input: bool = False


SIMPLE_OPERATIONS = {
    "add", "substract", "multiply", "divide", "divide_trunc", "divide_round",
    "remainder", "trunc", "round", "prefix", "suffix", "pad", "trim", "replace",
    "case", "uppercase", "lowercase", "capitalize",
}
AGGREGATE_OPERATIONS = {"concat", "sum", "min", "max"}
SUPPORTED_OPERATIONS = SIMPLE_OPERATIONS | AGGREGATE_OPERATIONS


# --- Conversión de valores ----------------------------------------------------


def render(value: Value) -> str:
    """Texto de un valor tal como se muestra en una tabla."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return repr(value)
    if isinstance(value, str):
        return _CONTROL.sub(" ", value)
    return str(value)


_CONTROL = re.compile("[\x00-\x1f\x7f]")


_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def to_number(value: Value) -> int | float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    text = render(value).strip()  # como String.trim de Java: quita blancos y controles
    if not _NUMBER.match(text):
        raise FormatError(f"se esperaba un número y se obtuvo {text!r}")
    return float(text) if "." in text else int(text)


def _normalize(number: int | float) -> int | float:
    if isinstance(number, float) and number.is_integer():
        return int(number)
    return number


def parse_literal(text: str) -> int | str:
    """Interpreta ``0x..`` o un entero decimal; si no, devuelve el texto."""
    stripped = text.strip()
    if re.fullmatch(r"0[xX][0-9a-fA-F]+", stripped):
        return int(stripped, 16)
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    return text


def _round_half_up(number: float) -> int:
    return math.floor(number + 0.5)


def _divide(a: int | float, b: int | float) -> int | float:
    if b == 0:
        raise FormatError("división por cero en un formato")
    return _normalize(a / b)


_ARITHMETIC: dict[str, Callable[[int | float, int | float], int | float]] = {
    "add": lambda a, b: a + b,
    "substract": lambda a, b: a - b,
    "multiply": lambda a, b: a * b,
    "divide": _divide,
    "divide_trunc": lambda a, b: int(_divide(a, b)),
    "divide_round": lambda a, b: _round_half_up(_divide(a, b)),
    "remainder": lambda a, b: _normalize(math.fmod(a, b)) if b else _divide(a, b),
}

_COMPARE = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    ">=": lambda a, b: a >= b,
}


def compare(value: Value, operator: str, reference: int | str) -> bool:
    if operator not in _COMPARE:
        raise FormatError(f"operador de comparación desconocido {operator!r}")
    if isinstance(reference, int):
        if isinstance(value, str) and len(value) == 1 and not value.isdigit():
            return _COMPARE[operator](ord(value), reference)
        try:
            return _COMPARE[operator](to_number(value), reference)
        except FormatError:
            return operator == "!="
    return _COMPARE[operator](render(value), reference)


# --- Formatos implícitos ------------------------------------------------------

_IMPLICIT_NUMERIC = {
    "+": "add", "-": "substract", "*": "multiply", "/": "divide",
    "d": "divide_trunc", "D": "divide_round", "%": "remainder",
}
_IMPLICIT_NUMERIC_RE = re.compile(r"^([+\-*/dD%])(-?\d+(?:\.\d+)?)$")
_IMPLICIT_WORDS = {
    "LC": "lowercase", "Lowercase": "lowercase",
    "UC": "uppercase", "Uppercase": "uppercase",
    "Capitalize": "capitalize",
    "R": "round", "Round": "round",
    "T": "trunc", "Trunc": "trunc",
}


def implicit_operation(identifier: str) -> Operation | None:
    """Traduce un formato implícito (``*10``, ``PadL20``...) a una operación."""
    if identifier in ("0x", "hexadecimal_string"):
        return Operation("hex", "")
    match = _IMPLICIT_NUMERIC_RE.match(identifier)
    if match:
        return Operation(_IMPLICIT_NUMERIC[match.group(1)], match.group(2))
    if identifier in _IMPLICIT_WORDS:
        return Operation(_IMPLICIT_WORDS[identifier], "")
    for prefix, direction in (("TrimL", "left"), ("TrimR", "right"), ("Trim", "both")):
        if identifier.startswith(prefix) and len(identifier) > len(prefix):
            return Operation("trim", identifier[len(prefix):], {"direction": direction})
    match = re.fullmatch(r"Pad([LR])(\d+?)(.)", identifier)
    if match:
        direction = "left" if match.group(1) == "L" else "right"
        return Operation("pad", match.group(3), {"direction": direction, "max": match.group(2)})
    for prefix, kind in (("Suffix", "suffix"), ("Prefix", "prefix")):
        if identifier.startswith(prefix) and len(identifier) > len(prefix):
            return Operation(kind, identifier[len(prefix):])
    return None


# --- Motor --------------------------------------------------------------------


@dataclass
class Context:
    """Datos disponibles al formatear: valores de la misma fila e índice de bucle."""

    lookup: Callable[[str], Value] = lambda _id: None
    loop_index: int | None = None


class FormatEngine:
    def __init__(self, formats: dict[str, NamedFormat]):
        self.formats = formats

    # Validación estática -----------------------------------------------------

    def unsupported(self, refs: tuple[str, ...], allow_loop_index: bool = False) -> list[str]:
        problems: list[str] = []
        self._check_refs(refs, allow_loop_index, problems, set())
        return problems

    def _check_refs(self, refs, allow_loop_index, problems, seen):
        for ref in refs:
            if ref in self.formats:
                if ref in seen:
                    problems.append(f"format recursivo '{ref}'")
                    continue
                self._check_named(self.formats[ref], allow_loop_index, problems, seen | {ref})
            elif ref == "LoopIndex":
                if not allow_loop_index:
                    problems.append("format LoopIndex fuera de un elt")
            elif implicit_operation(ref) is None:
                problems.append(f"format desconocido '{ref}'")

    def _check_named(self, fmt: NamedFormat, allow_loop_index, problems, seen):
        for op in fmt.operations:
            if op.kind not in SUPPORTED_OPERATIONS:
                problems.append(f"format <{op.kind}>")
                continue
            if op.kind in SIMPLE_OPERATIONS and op.children:
                problems.append(f"format <{op.kind}> con columnas")
            if op.kind in _ARITHMETIC and not op.children:
                try:
                    to_number(op.text)
                except FormatError:
                    problems.append(f"format <{op.kind}> con valor {op.text!r}")
            if op.kind == "case":
                for key in ("format", "operator-format"):
                    if key in op.attrs:
                        self._check_refs(_split(op.attrs[key]), allow_loop_index, problems, seen)
                if op.attrs.get("operator", "==") not in _COMPARE:
                    problems.append(f"case@operator={op.attrs['operator']}")
            if op.kind == "prefix" or op.kind == "suffix":
                pass
            for child in op.children:
                self._check_refs(child.formats, allow_loop_index, problems, seen)

    # Aplicación --------------------------------------------------------------

    def apply(self, value: Value, refs: tuple[str, ...], ctx: Context) -> Value:
        for ref in refs:
            value = self._apply_ref(value, ref, ctx)
        return value

    def _apply_ref(self, value: Value, ref: str, ctx: Context) -> Value:
        named = self.formats.get(ref)
        if named is not None:
            return self._apply_named(value, named, ctx)
        if ref == "LoopIndex":
            if ctx.loop_index is None:
                raise FormatError("LoopIndex usado fuera de un bucle")
            return ctx.loop_index
        op = implicit_operation(ref)
        if op is None:
            raise FormatError(f"formato desconocido {ref!r}")
        return self._apply_operations(value, (op,), ctx, subcolumns_input=False)

    def _apply_named(self, value: Value, fmt: NamedFormat, ctx: Context) -> Value:
        if fmt.apply_to_char:
            return "".join(
                render(self._apply_operations(char, fmt.operations, ctx, fmt.subcolumns_input))
                for char in render(value)
            )
        return self._apply_operations(value, fmt.operations, ctx, fmt.subcolumns_input)

    def _apply_operations(self, value, operations, ctx, subcolumns_input) -> Value:
        index = 0
        while index < len(operations):
            op = operations[index]
            if op.kind == "case":
                group = []
                while index < len(operations) and operations[index].kind == "case":
                    group.append(operations[index])
                    index += 1
                value = self._apply_cases(value, group, ctx)
                continue
            value = self._apply_operation(value, op, ctx, subcolumns_input)
            index += 1
        return value

    def _apply_cases(self, value, cases, ctx) -> Value:
        chosen = None
        for case in cases:
            probe = value
            if "operator-format" in case.attrs:
                probe = self.apply(value, _split(case.attrs["operator-format"]), ctx)
            if compare(probe, case.attrs.get("operator", "=="), parse_literal(case.attrs["src"])):
                chosen = case
                break
        if chosen is None:
            chosen = next((c for c in cases if _is_true(c.attrs.get("default"))), None)
        if chosen is None:
            return value
        if "dst" in chosen.attrs:
            return chosen.attrs["dst"]
        if "format" in chosen.attrs:
            return self.apply(value, _split(chosen.attrs["format"]), ctx)
        return value

    def _apply_operation(self, value, op: Operation, ctx, subcolumns_input) -> Value:
        kind = op.kind
        if kind in _ARITHMETIC or kind in ("trunc", "round"):
            if value is None or render(value).strip() == "":
                value = 0  # hi2txt opera una celda vacía como cero
        if kind in _ARITHMETIC:
            return _normalize(_ARITHMETIC[kind](to_number(value), to_number(op.text)))
        if kind == "hex":
            if isinstance(value, int) and not isinstance(value, bool):
                return f"0x{value:X}"
            text = render(value)
            return "0x" + text if text else text
        if kind == "trunc":
            return int(to_number(value))
        if kind == "round":
            return _round_half_up(to_number(value))
        if kind in ("prefix", "suffix"):
            text = render(value)
            empty = op.attrs.get("empty", "")
            if text == empty:
                return "" if _is_true(op.attrs.get("consume")) else value
            return op.text + text if kind == "prefix" else text + op.text
        if kind == "pad":
            text = render(value)
            width = int(op.attrs["max"])
            if not op.text or len(text) >= width:
                return text
            padding = (op.text * width)[: width - len(text)]
            return padding + text if op.attrs.get("direction", "right") == "left" else text + padding
        if kind == "trim":
            return _trim(render(value), op.text, op.attrs.get("direction", "right"))
        if kind == "replace":
            return render(value).replace(op.attrs["src"], op.attrs["dst"])
        if kind == "uppercase":
            return render(value).upper()
        if kind == "lowercase":
            return render(value).lower()
        if kind == "capitalize":
            text = render(value)
            return text[:1].upper() + text[1:]
        if kind in AGGREGATE_OPERATIONS:
            parts = [self._subcolumn(value, child, ctx, subcolumns_input) for child in op.children]
            if kind == "concat":
                return "".join(render(part) for part in parts)
            numbers = [to_number(part) for part in parts]
            if not numbers:
                raise FormatError(f"<{kind}> sin columnas")
            if kind == "sum":
                return _normalize(sum(numbers))
            return min(numbers) if kind == "min" else max(numbers)
        raise FormatError(f"operación de formato no soportada <{kind}>")

    def _subcolumn(self, value, child: SubColumn, ctx, subcolumns_input) -> Value:
        if child.kind == "txt":
            return child.content or ""
        if child.content:
            base: Value = child.content
        elif child.source is None:
            base = value if subcolumns_input else None
        else:
            base = ctx.lookup(child.source)
        return self.apply(base, child.formats, ctx)


def _trim(text: str, token: str, direction: str) -> str:
    if not token:
        return text
    if direction in ("left", "both"):
        while text.startswith(token):
            text = text[len(token):]
    if direction in ("right", "both"):
        while text.endswith(token):
            text = text[: -len(token)]
    return text


def _split(refs: str | None) -> tuple[str, ...]:
    if not refs:
        return ()
    return tuple(part for part in refs.split(";") if part)


def _is_true(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "yes", "true")


split_refs = _split
is_true = _is_true
