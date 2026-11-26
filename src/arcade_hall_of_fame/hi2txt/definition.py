"""Carga de una definición hi2txt (XML) a un modelo propio y validación estática.

Se usa ``xml.etree.ElementTree`` de la biblioteca estándar. Las definiciones no
se incluyen en el repositorio: se leen de una carpeta local descargada por el
usuario (ver ``fetch.py``).

La validación es por lista blanca: cualquier elemento, atributo o valor que el
intérprete no implemente se informa como ``UnsupportedDefinition`` al cargar,
antes de leer ningún archivo de puntuaciones.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from ..models import DefinitionError, MissingDefinition, UnsupportedDefinition
from .formats import (
    SUPPORTED_OPERATIONS,
    FormatEngine,
    NamedFormat,
    Operation,
    SubColumn,
    formatter_problem,
    is_true,
    parse_literal,
    split_refs,
)

# --- Modelo -------------------------------------------------------------------


@dataclass(frozen=True)
class Elt:
    id: str
    size: int
    type: str  # "int", "text" o "raw"
    attrs: dict[str, str]
    formats: tuple[str, ...] = ()


@dataclass(frozen=True)
class Loop:
    count: int
    start: int
    step: int
    skip_first_bytes: int
    skip_last_bytes: int
    elts: tuple[Elt, ...]


@dataclass(frozen=True)
class Structure:
    file: str
    output_id: str | None
    byte_swap: int | None
    sizes: tuple[int, ...]
    regions: tuple[tuple[tuple[int, int, int, int], ...], ...]
    items: tuple[Elt | Loop, ...]

    def matches_file(self, file_name: str) -> bool:
        if file_name == self.file:
            return True
        extension = self.file[1:] if self.file.startswith(".") else self.file
        return "." in file_name and file_name.rsplit(".", 1)[1] == extension


@dataclass(frozen=True)
class Column:
    id: str | None
    src: str | None
    formats: tuple[str, ...]
    display: str
    content: str | None

    @property
    def source(self) -> str | None:
        return self.src or self.id


@dataclass(frozen=True)
class Table:
    id: str | None
    columns: tuple[Column, ...]
    display: str
    line_ignore: tuple[str, str] | None
    line_ignore_operator: str
    sort: str | None
    sort_desc: bool
    sort_formats: tuple[str, ...]
    lines_max: int | None


@dataclass(frozen=True)
class Output:
    id: str | None
    tables: tuple[Table, ...]
    fields: tuple[Column, ...]


@dataclass(frozen=True)
class Charset:
    mapping: dict[int, str]
    default: str | None


_PREDEFINED_CHARSET = re.compile(r"^CS_NUMBER(?:\[(-?\d+)(?:,(-?\d+))?\])?$")


def parse_predefined_charset(name: str) -> Charset | None:
    """Charset predefinido de hi2txt, o ``None`` si no se conoce.

    ``CS_NUMBER`` son las cifras 0 a 9 con sus códigos ASCII (0x30 a 0x39).
    ``CS_NUMBER[desplazamiento]`` suma el desplazamiento a cada código, y
    ``CS_NUMBER[desplazamiento,delta]`` además separa cifras consecutivas en
    ``1 + delta`` códigos: con ``[4,1]``, el 0 es 0x34, el 1 es 0x36...
    """
    match = _PREDEFINED_CHARSET.match(name)
    if not match:
        return None
    offset = int(match.group(1) or 0)
    delta = int(match.group(2) or 0)
    mapping = {ord("0") + digit + offset + digit * delta: str(digit) for digit in range(10)}
    return Charset(mapping=mapping, default=None)


@dataclass(frozen=True)
class Bitmask:
    masks: tuple[str, ...]
    byte_completion: bool


@dataclass
class Definition:
    game: str
    label: str | None
    structures: tuple[Structure, ...]
    outputs: tuple[Output, ...]
    formats: dict[str, NamedFormat]
    charsets: dict[str, Charset]
    bitmasks: dict[str, Bitmask]
    engine: FormatEngine = field(init=False)

    def __post_init__(self):
        self.engine = FormatEngine(self.formats)

    def output_for(self, structure: Structure) -> Output:
        for output in self.outputs:
            if output.id == structure.output_id:
                return output
        if structure.output_id is None and self.outputs:
            return self.outputs[0]
        raise DefinitionError(f"{self.game}: no existe la salida {structure.output_id!r}")


# --- Listas blancas -----------------------------------------------------------

DISPLAY_VALUES = {"always", "extra", "debug"}
ELT_ATTRIBUTES = {
    "id", "size", "type", "charset", "base", "table-index", "decoding-profile",
    "ascii-offset", "ascii-step", "endianness", "byte-skip", "byte-trim",
    "byte-trunc", "nibble-skip", "nibble-trim", "byte-swap", "bit-swap",
    "table-index-format", "bitmask", "src-unit-size", "dst-unit-size", "format",
}
DECODING_PROFILES = {
    "bcd": {"nibble-skip": "odd", "base": "16"},
    "bcd-le": {"endianness": "little_endian", "nibble-skip": "odd", "base": "16"},
    "base-40": {"src-unit-size": "16", "base": "40", "dst-unit-size": "3", "ascii-offset": "64"},
    "base-32": {"src-unit-size": "16", "base": "32", "dst-unit-size": "3", "ascii-offset": "64"},
}
TABLE_INDEX_RE = re.compile(r"^(loop_index|loop_reverse_index|itself|last|\d+|[^:]+:index_from_value)$")
COMPARE_OPERATORS = {"<", "==", ">", ">=", "<=", "!="}


def _int(text: str | None, what: str) -> int:
    value = parse_literal(text or "")
    if not isinstance(value, int):
        raise DefinitionError(f"{what}: se esperaba un entero y se encontró {text!r}")
    return value


def _hex_tuple(parts: list[str]) -> tuple[int, int, int, int]:
    return tuple(int(part, 16) for part in parts)  # type: ignore[return-value]


def parse_region_line(line: str) -> tuple[int, int, int, int] | None:
    """Normaliza una línea de ``hiscore.dat`` a (dirección, largo, inicio, fin).

    Acepta el formato antiguo ``cpu:dir:largo:inicio:fin`` y el nuevo
    ``@:cpu,espacio,dir,largo,inicio,fin``.
    """
    line = line.split(";", 1)[0].strip()
    if not line:
        return None
    try:
        if line.startswith("@:"):
            parts = line[2:].split(",")
            if len(parts) not in (6, 7):  # el séptimo campo opcional es el relleno
                return None
            return _hex_tuple(parts[2:6])
        parts = line.split(":")
        if len(parts) != 5:
            return None
        return _hex_tuple(parts[1:5])
    except ValueError:
        return None


# --- Lectura --------------------------------------------------------------------


class _Parser:
    def __init__(self, game: str):
        self.game = game
        self.problems: list[str] = []

    def unsupported(self, feature: str) -> None:
        self.problems.append(feature)

    def check_attrs(self, el: ET.Element, allowed: set[str]) -> None:
        for name in el.attrib:
            if name not in allowed:
                self.unsupported(f"{el.tag}@{name}")

    def check_display(self, value: str) -> str:
        if value not in DISPLAY_VALUES:
            self.unsupported(f"display={value}")
        return value

    def parse(self, root: ET.Element) -> Definition:
        if root.tag != "hi2txt":
            raise DefinitionError(f"{self.game}: la raíz no es <hi2txt>")
        self.check_attrs(root, {"label", "ingame-score"})
        structures, outputs = [], []
        formats: dict[str, NamedFormat] = {}
        charsets: dict[str, Charset] = {}
        bitmasks: dict[str, Bitmask] = {}
        for child in root:
            if not isinstance(child.tag, str):
                continue
            if child.tag == "structure":
                structures.append(self.structure(child))
            elif child.tag == "output":
                outputs.append(self.output(child))
            elif child.tag == "format":
                fmt = self.format(child)
                formats[fmt.id] = fmt
            elif child.tag == "charset":
                charsets[child.get("id", "")] = self.charset(child)
            elif child.tag == "bitmask":
                bitmasks[child.get("id", "")] = self.bitmask(child)
            elif child.tag == "sameas":
                raise DefinitionError(f"{self.game}: <sameas> debe resolverse antes de interpretar")
            else:
                self.unsupported(f"<{child.tag}>")
        if not structures:
            raise DefinitionError(f"{self.game}: la definición no tiene <structure>")
        definition = Definition(
            game=self.game,
            label=root.get("label"),
            structures=tuple(structures),
            outputs=tuple(outputs),
            formats=formats,
            charsets=charsets,
            bitmasks=bitmasks,
        )
        self.cross_check(definition)
        if self.problems:
            raise UnsupportedDefinition(self.game, self.problems)
        return definition

    def structure(self, el: ET.Element) -> Structure:
        self.check_attrs(el, {"file", "output", "byte-swap"})
        sizes: list[int] = []
        regions: list[tuple[tuple[int, int, int, int], ...]] = []
        items: list[Elt | Loop] = []
        for child in el:
            if not isinstance(child.tag, str):
                continue
            if child.tag == "check":
                for check in child:
                    if not isinstance(check.tag, str):
                        continue
                    if check.tag == "size":
                        sizes.append(_int(check.text, f"{self.game}: check/size"))
                    elif check.tag == "definition":
                        lines = [parse_region_line(line) for line in (check.text or "").splitlines()]
                        regions.append(tuple(r for r in lines if r is not None))
                    else:
                        self.unsupported(f"<check/{check.tag}>")
            elif child.tag == "elt":
                items.append(self.elt(child, in_loop=False))
            elif child.tag == "loop":
                items.append(self.loop(child))
            else:
                self.unsupported(f"<structure/{child.tag}>")
        byte_swap = el.get("byte-swap")
        return Structure(
            file=el.get("file", ""),
            output_id=el.get("output"),
            byte_swap=_int(byte_swap, "structure@byte-swap") if byte_swap else None,
            sizes=tuple(sizes),
            regions=tuple(regions),
            items=tuple(items),
        )

    def loop(self, el: ET.Element) -> Loop:
        self.check_attrs(el, {"count", "start", "step", "skip-first-bytes", "skip-last-bytes"})
        elts = tuple(self.elt(child, in_loop=True) for child in el if child.tag == "elt")
        for child in el:
            if isinstance(child.tag, str) and child.tag != "elt":
                self.unsupported(f"<loop/{child.tag}>")
        return Loop(
            count=_int(el.get("count"), "loop@count"),
            start=_int(el.get("start", "0"), "loop@start"),
            step=_int(el.get("step", "1"), "loop@step"),
            skip_first_bytes=_int(el.get("skip-first-bytes", "0"), "loop@skip-first-bytes"),
            skip_last_bytes=_int(el.get("skip-last-bytes", "0"), "loop@skip-last-bytes"),
            elts=elts,
        )

    def elt(self, el: ET.Element, in_loop: bool) -> Elt:
        self.check_attrs(el, ELT_ATTRIBUTES)
        attrs = dict(el.attrib)
        profile = attrs.pop("decoding-profile", None)
        if profile and profile != "null":
            if profile not in DECODING_PROFILES:
                self.unsupported(f"decoding-profile={profile}")
            else:
                for key, value in DECODING_PROFILES[profile].items():
                    attrs.setdefault(key, value)
        elt_type = attrs.get("type", "raw")
        if elt_type not in ("int", "text", "raw"):
            self.unsupported(f"elt@type={elt_type}")
        self.check_elt_values(attrs, elt_type, in_loop)
        return Elt(
            id=attrs.get("id", ""),
            size=_int(attrs.get("size"), "elt@size"),
            type=elt_type,
            attrs=attrs,
            formats=split_refs(attrs.get("format")),
        )

    def check_elt_values(self, attrs: dict[str, str], elt_type: str, in_loop: bool) -> None:
        def bad(name):
            self.unsupported(f"elt@{name}={attrs[name]}")

        base = attrs.get("base")
        if base is not None:
            allowed = {"10", "16", "256"} if elt_type == "int" else {"10", "16", "32", "40"}
            if base not in allowed:
                bad("base")
        if attrs.get("endianness", "default") not in ("big_endian", "little_endian", "default"):
            bad("endianness")
        skip = attrs.get("byte-skip")
        if skip is not None and not (
            skip in ("odd", "even") or re.fullmatch(r"0x[0-9a-fA-F]{2}", skip) or re.fullmatch(r"[01]+", skip)
        ):
            bad("byte-skip")
        for name in ("byte-trim", "byte-trunc"):
            if name in attrs and not re.fullmatch(r"0x[0-9a-fA-F]{2}", attrs[name]):
                bad(name)
        if attrs.get("nibble-skip", "null") not in ("odd", "even", "null"):
            bad("nibble-skip")
        if "nibble-trim" in attrs and not re.fullmatch(r"0x[0-9a-fA-F]", attrs["nibble-trim"]):
            bad("nibble-trim")
        for name in ("byte-swap", "ascii-offset", "ascii-step", "src-unit-size", "dst-unit-size"):
            if name in attrs and not re.fullmatch(r"-?\d+", attrs[name]):
                bad(name)
        if attrs.get("bit-swap", "0").lower() not in ("0", "no", "false", "1", "yes", "true"):
            bad("bit-swap")
        if elt_type != "text":
            for name in ("charset", "ascii-offset", "ascii-step", "dst-unit-size"):
                if name in attrs:
                    self.unsupported(f"elt@{name} en tipo {elt_type}")
            if "src-unit-size" in attrs:
                self.unsupported(f"elt@src-unit-size en tipo {elt_type}")
        else:
            unit = int(attrs.get("src-unit-size", "8"))
            if unit not in (4, 8, 16, 24, 32):
                bad("src-unit-size")
            if attrs.get("base") in ("32", "40") and "dst-unit-size" not in attrs:
                self.unsupported("elt@base sin dst-unit-size")
            if "dst-unit-size" in attrs and attrs.get("base") not in ("32", "40"):
                self.unsupported("elt@dst-unit-size sin base 32/40")
            for name in attrs.get("charset", "").split(";"):
                if name.startswith("CS_") and parse_predefined_charset(name) is None:
                    self.unsupported(f"charset predefinido {name}")
        index = attrs.get("table-index")
        if index is not None:
            if not TABLE_INDEX_RE.match(index):
                bad("table-index")
            elif not in_loop and not index.isdigit():
                self.unsupported(f"elt@table-index={index} fuera de un bucle")

    def output(self, el: ET.Element) -> Output:
        self.check_attrs(el, {"id"})
        tables, fields = [], []
        for child in el:
            if not isinstance(child.tag, str):
                continue
            if child.tag == "table":
                tables.append(self.table(child))
            elif child.tag == "field":
                fields.append(self.column(child))
            else:
                self.unsupported(f"<output/{child.tag}>")
        return Output(id=el.get("id"), tables=tuple(tables), fields=tuple(fields))

    def table(self, el: ET.Element) -> Table:
        self.check_attrs(el, {"id", "line-ignore", "line-ignore-operator", "sort", "sort-order", "sort-format", "lines-max", "display"})
        columns = []
        for child in el:
            if not isinstance(child.tag, str):
                continue
            if child.tag in ("column", "field"):
                columns.append(self.column(child))
            else:
                self.unsupported(f"<table/{child.tag}>")
        ignore = el.get("line-ignore")
        line_ignore = None
        if ignore is not None:
            column, sep, value = ignore.partition(":")
            # Sin ":valor" se omiten las filas en que esa columna está vacía.
            line_ignore = (column, value)
        operator = el.get("line-ignore-operator", "==")
        if operator not in COMPARE_OPERATORS:
            self.unsupported(f"table@line-ignore-operator={operator}")
        lines_max = el.get("lines-max")
        return Table(
            id=el.get("id"),
            columns=tuple(columns),
            display=self.check_display(el.get("display", "always")),
            line_ignore=line_ignore,
            line_ignore_operator=operator,
            sort=el.get("sort"),
            sort_desc=el.get("sort-order", "asc") == "desc",
            sort_formats=split_refs(el.get("sort-format")),
            lines_max=_int(lines_max, "table@lines-max") if lines_max else None,
        )

    def column(self, el: ET.Element) -> Column:
        self.check_attrs(el, {"id", "src", "format", "display"})
        for child in el:
            if isinstance(child.tag, str):
                self.unsupported(f"<{el.tag}/{child.tag}>")
        content = (el.text or "").strip() or None
        return Column(
            id=el.get("id"),
            src=el.get("src"),
            formats=split_refs(el.get("format")),
            display=self.check_display(el.get("display", "always")),
            content=content,
        )

    def format(self, el: ET.Element) -> NamedFormat:
        self.check_attrs(el, {"id", "apply-to", "input-as-subcolumns-input", "formatter"})
        formatter = el.get("formatter")
        if formatter is not None:
            problem = formatter_problem(formatter)
            if problem:
                self.unsupported(f"format@{problem}")
        apply_to = el.get("apply-to", "value")
        if apply_to not in ("value", "char"):
            self.unsupported(f"format@apply-to={apply_to}")
        operations = []
        for child in el:
            if not isinstance(child.tag, str):
                continue
            if child.tag not in SUPPORTED_OPERATIONS:
                self.unsupported(f"format <{child.tag}>")
                continue
            allowed = {
                "prefix": {"empty", "consume"}, "suffix": {"empty", "consume"},
                "pad": {"direction", "max"}, "trim": {"direction"},
                "replace": {"src", "dst"},
                "case": {"src", "dst", "default", "operator", "operator-format", "format"},
            }.get(child.tag, set())
            self.check_attrs(child, allowed)
            subcolumns = []
            for sub in child:
                if not isinstance(sub.tag, str):
                    continue
                if sub.tag not in ("column", "field", "txt"):
                    self.unsupported(f"<{child.tag}/{sub.tag}>")
                    continue
                self.check_attrs(sub, {"id", "src", "format"} if sub.tag != "txt" else set())
                subcolumns.append(
                    SubColumn(
                        kind=sub.tag,
                        source=sub.get("src") or sub.get("id"),
                        formats=split_refs(sub.get("format")),
                        content=sub.text if sub.tag == "txt" else ((sub.text or "").strip() or None),
                    )
                )
            if child.tag == "pad" and "max" not in child.attrib:
                self.unsupported("format <pad> sin max")
            text = child.text or ""
            if child.tag not in ("prefix", "suffix", "pad", "trim"):
                text = text.strip()
            operations.append(Operation(child.tag, text, dict(child.attrib), tuple(subcolumns)))
        return NamedFormat(
            id=el.get("id", ""),
            operations=tuple(operations),
            apply_to_char=apply_to == "char",
            subcolumns_input=is_true(el.get("input-as-subcolumns-input")),
            formatter=formatter,
        )

    def charset(self, el: ET.Element) -> Charset:
        self.check_attrs(el, {"id"})
        mapping: dict[int, str] = {}
        default = None
        for char in el:
            if not isinstance(char.tag, str):
                continue
            if char.tag != "char":
                self.unsupported(f"<charset/{char.tag}>")
                continue
            self.check_attrs(char, {"src", "dst", "default"})
            raw_src = char.get("src", "").strip()
            src = parse_literal(raw_src)
            if not isinstance(src, int) and re.fullmatch(r"[0-9a-fA-F]{1,2}", raw_src):
                src = int(raw_src, 16)  # hexadecimal sin 0x ("2D", "FE"): no puede ser decimal
            if not isinstance(src, int):
                self.unsupported(f"char@src={char.get('src')}")
                continue
            dst = char.get("dst", "")
            mapping[src] = dst
            if is_true(char.get("default")):
                default = dst
        return Charset(mapping=mapping, default=default)

    def bitmask(self, el: ET.Element) -> Bitmask:
        self.check_attrs(el, {"id", "byte-completion"})
        masks = []
        for char in el:
            if not isinstance(char.tag, str):
                continue
            if char.tag != "character":
                self.unsupported(f"<bitmask/{char.tag}>")
                continue
            mask = re.sub(r"\s+", "", char.get("mask", ""))
            if not re.fullmatch(r"[01]+", mask):
                self.unsupported("bitmask con máscara inválida")
            masks.append(mask)
        completion = el.get("byte-completion")
        return Bitmask(masks=tuple(masks), byte_completion=completion is None or is_true(completion))

    def cross_check(self, d: Definition) -> None:
        """Comprueba referencias entre partes de la definición."""
        engine = FormatEngine(d.formats)
        for structure in d.structures:
            elts = [i for i in structure.items if isinstance(i, Elt)]
            for loop in (i for i in structure.items if isinstance(i, Loop)):
                elts.extend(loop.elts)
                total = sum(e.size for e in loop.elts)
                if loop.skip_first_bytes + loop.skip_last_bytes > total * loop.count:
                    self.unsupported("loop@skip-* mayor que el bucle")
            for e in elts:
                for name in e.attrs.get("charset", "").split(";"):
                    if name and not name.startswith("CS_") and name not in d.charsets:
                        raise DefinitionError(f"{self.game}: charset inexistente {name!r}")
                if "bitmask" in e.attrs:
                    if e.attrs["bitmask"] not in d.bitmasks:
                        raise DefinitionError(f"{self.game}: bitmask inexistente {e.attrs['bitmask']!r}")
                self.problems.extend(engine.unsupported(e.formats, allow_loop_index=True))
                self.problems.extend(engine.unsupported(split_refs(e.attrs.get("table-index-format"))))
            if structure.output_id is not None or d.outputs:
                try:
                    d.output_for(structure)
                except DefinitionError:
                    raise
        for output in d.outputs:
            for table in output.tables:
                self.problems.extend(engine.unsupported(table.sort_formats))
                for column in table.columns:
                    self.problems.extend(engine.unsupported(column.formats))
            for fld in output.fields:
                self.problems.extend(engine.unsupported(fld.formats))
        if not d.outputs:
            raise DefinitionError(f"{self.game}: la definición no tiene <output>")


XML_ENTITIES = {"lt", "gt", "amp", "quot", "apos"}
_ENTITY_REF = re.compile(rb"&([A-Za-z_][A-Za-z0-9._-]*);")
_ENTITY_DECL = re.compile(r'<!ENTITY\s+([A-Za-z_][A-Za-z0-9._-]*)\s+"([^"]*)"\s*>')


def load_entities(dtd_path: str | Path) -> dict[str, str]:
    """Lee las entidades con nombre (``&black-heart;``...) del DTD local de hi2txt."""
    text = Path(dtd_path).read_text(encoding="utf-8", errors="replace")
    return {name: value for name, value in _ENTITY_DECL.findall(text)}


def expand_entities(game: str, xml_bytes: bytes, entities: dict[str, str] | None) -> bytes:
    """Sustituye entidades con nombre por su valor antes de interpretar el XML.

    Sin esto, el analizador descarta en silencio las entidades de los atributos
    (por ejemplo ``dst="&black-heart;"``), lo que cambiaría las iniciales.
    """

    def replace(match: re.Match[bytes]) -> bytes:
        name = match.group(1).decode("ascii")
        if name in XML_ENTITIES:
            return match.group(0)
        if entities is None or name not in entities:
            raise DefinitionError(f"{game}: entidad desconocida &{name}; (falta hi2txt.dtd o no la define)")
        value = entities[name]
        if "&" in re.sub(r"&#(x[0-9A-Fa-f]+|\d+);", "", value):
            raise DefinitionError(f"{game}: entidad &{name}; con valor no admitido")
        return value.encode("utf-8")

    return _ENTITY_REF.sub(replace, xml_bytes)


def parse_definition(game: str, xml_bytes: bytes, entities: dict[str, str] | None = None) -> Definition:
    """Construye una ``Definition`` a partir del texto XML de una definición."""
    xml_bytes = expand_entities(game, xml_bytes, entities)
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise DefinitionError(f"{game}: XML inválido ({exc})") from exc
    return _Parser(game).parse(root)


def sameas_target(xml_bytes: bytes) -> str | None:
    """Devuelve el juego al que remite un ``<sameas id="...">``, si lo hay."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    node = root.find("sameas")
    return node.get("id") if node is not None else None


GAME_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


class DefinitionLibrary:
    """Carpeta local con las definiciones de hi2txt-xml (``src/main/db``)."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        if not self.directory.is_dir():
            raise DefinitionError(f"no existe la carpeta de definiciones {self.directory.name!r}")
        dtd = self.directory / "hi2txt.dtd"
        self.entities = load_entities(dtd) if dtd.is_file() else None

    def path_for(self, game: str) -> Path:
        if not GAME_NAME_RE.match(game):
            raise DefinitionError(f"nombre de juego inválido {game!r}")
        return self.directory / f"{game}.xml"

    def games(self) -> list[str]:
        return sorted(p.stem for p in self.directory.glob("*.xml"))

    def resolve(self, game: str) -> tuple[str, bytes]:
        """Sigue las referencias ``sameas`` y devuelve (juego base, XML)."""
        seen = []
        current = game
        while True:
            path = self.path_for(current)
            try:
                data = path.read_bytes()
            except FileNotFoundError:
                if current == game:
                    raise MissingDefinition(f"no hay definición para {game!r}") from None
                raise DefinitionError(f"{game}: sameas apunta a {current!r}, que no existe") from None
            target = sameas_target(data)
            if target is None:
                return current, data
            seen.append(current)
            if target in seen or len(seen) > 10:
                raise DefinitionError(f"{game}: ciclo de sameas")
            current = target

    def load(self, game: str) -> Definition:
        base, data = self.resolve(game)
        definition = parse_definition(base, data, self.entities)
        definition.game = game
        return definition
