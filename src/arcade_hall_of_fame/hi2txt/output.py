"""Construcción de tablas y campos a partir de los valores decodificados."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import FormatError
from .definition import Column, Definition, Structure, Table
from .formats import Context, Value, compare, parse_literal, render, to_number


@dataclass(frozen=True)
class DecodedTable:
    id: str | None
    display: str
    columns: tuple[str, ...]
    column_display: tuple[str, ...]
    rows: tuple[tuple[Value, ...], ...]

    def column(self, name: str) -> int | None:
        try:
            return self.columns.index(name)
        except ValueError:
            return None


@dataclass(frozen=True)
class DecodedField:
    id: str | None
    display: str
    value: Value


@dataclass(frozen=True)
class ScoreRow:
    """Fila normalizada: posición, puntuación e iniciales tal como las guarda el juego.

    Las iniciales no identifican a una persona; la atribución se configura aparte.
    """

    position: int
    score: Value
    initials: str | None


@dataclass(frozen=True)
class Result:
    game: str
    structure_index: int
    tables: tuple[DecodedTable, ...]
    fields: tuple[DecodedField, ...]

    def main_table(self) -> DecodedTable:
        """Primera tabla visible con columna SCORE (convención de hi2txt)."""
        for table in self.tables:
            if table.display == "always" and table.column("SCORE") is not None:
                return table
        raise FormatError(f"{self.game}: la salida no tiene una tabla con columna SCORE")

    def score_rows(self) -> tuple[ScoreRow, ...]:
        table = self.main_table()
        rank_col, score_col, name_col = table.column("RANK"), table.column("SCORE"), table.column("NAME")
        rows = []
        for position, row in enumerate(table.rows, start=1):
            rank = position
            if rank_col is not None:
                rank = int(to_number(row[rank_col]))
            name = None if name_col is None else render(row[name_col])
            rows.append(ScoreRow(rank, row[score_col], name))
        return tuple(rows)

    def field(self, name: str) -> Value:
        for f in self.fields:
            if f.id == name:
                return f.value
        raise KeyError(name)


def _format_references(definition: Definition, refs, seen=None) -> set[str]:
    seen = seen or set()
    found: set[str] = set()
    for ref in refs:
        fmt = definition.formats.get(ref)
        if fmt is None or ref in seen:
            continue
        for op in fmt.operations:
            for child in op.children:
                if child.source and child.kind != "txt":
                    found.add(child.source)
                found |= _format_references(definition, child.formats, seen | {ref})
    return found


def _build_table(definition: Definition, table: Table, values: dict[str, dict[int, Value]]) -> DecodedTable:
    engine = definition.engine
    sources: set[str] = set()
    for column in table.columns:
        if column.source and column.source not in ("index", "unsorted_index") and not column.content:
            sources.add(column.source)
        sources |= _format_references(definition, column.formats)
    indices = sorted({i for s in sources if s in values for i in values[s]})

    def lookup_for(index):
        return lambda name: values.get(name, {}).get(index)

    def cell(column: Column, index: int, position: int | None) -> Value:
        ctx = Context(lookup=lookup_for(index))
        if column.content:
            base: Value = column.content
        elif column.source == "index":
            base = index if position is None else position
        elif column.source == "unsorted_index":
            base = index
        elif column.source is None:
            base = None
        else:
            base = ctx.lookup(column.source)
        return engine.apply(base, column.formats, ctx)

    entries = [(index, [cell(c, index, None) for c in table.columns]) for index in indices]

    if table.line_ignore:
        name, reference = table.line_ignore
        position = next((k for k, c in enumerate(table.columns) if c.id == name or c.source == name), None)
        kept = []
        for index, row in entries:
            probe = row[position] if position is not None else values.get(name, {}).get(index)
            if not compare(probe, table.line_ignore_operator, parse_literal(reference)):
                kept.append((index, row))
        entries = kept

    if table.sort:
        position = next((k for k, c in enumerate(table.columns) if c.id == table.sort), None)

        def sort_value(entry):
            index, row = entry
            raw = row[position] if position is not None else values.get(table.sort, {}).get(index)
            return engine.apply(raw, table.sort_formats, Context(lookup=lookup_for(index)))

        keys = [sort_value(e) for e in entries]
        try:
            numeric = [to_number(k) for k in keys]
            order = sorted(range(len(entries)), key=lambda k: numeric[k], reverse=table.sort_desc)
        except FormatError:
            order = sorted(range(len(entries)), key=lambda k: render(keys[k]), reverse=table.sort_desc)
        entries = [entries[k] for k in order]
        entries = [
            (index, [cell(c, index, pos) if c.source == "index" and not c.content else row[k]
                     for k, c in enumerate(table.columns)])
            for pos, (index, row) in enumerate(entries)
        ]

    if table.lines_max is not None:
        entries = entries[: table.lines_max]

    return DecodedTable(
        id=table.id,
        display=table.display,
        columns=tuple(c.id or c.src or "" for c in table.columns),
        column_display=tuple(c.display for c in table.columns),
        rows=tuple(tuple(row) for _, row in entries),
    )


def _build_field(definition: Definition, column: Column, values: dict[str, dict[int, Value]]) -> DecodedField:
    if column.content:
        base: Value = column.content
        index = 0
    elif column.source in values:
        entries = values[column.source]
        index = 0 if 0 in entries else min(entries)
        base = entries[index]
    else:
        index = 0
        base = None
    ctx = Context(lookup=lambda name: values.get(name, {}).get(index))
    return DecodedField(column.id, column.display, definition.engine.apply(base, column.formats, ctx))


def build_result(definition: Definition, structure: Structure, structure_index: int,
                 values: dict[str, dict[int, Value]]) -> Result:
    output = definition.output_for(structure)
    return Result(
        game=definition.game,
        structure_index=structure_index,
        tables=tuple(_build_table(definition, t, values) for t in output.tables),
        fields=tuple(_build_field(definition, f, values) for f in output.fields),
    )
