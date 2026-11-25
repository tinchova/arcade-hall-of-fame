"""Aplicación de una definición hi2txt a los bytes de un archivo de puntuaciones.

Función pura: recibe bytes y una ``Definition`` ya validada; no abre archivos.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import FormatError
from .definition import Definition, Elt, Loop, Structure
from .formats import Context, Value, is_true, render
from .output import Result, build_result

# --- Operaciones sobre bytes, representados como texto hexadecimal -------------


def _byte_swap(h: str, n: int) -> str:
    if n <= 1:
        return h
    width = 2 * n
    if len(h) % width:
        raise FormatError(f"byte-swap={n} sobre {len(h) // 2} bytes")
    out = []
    for i in range(0, len(h), width):
        chunk = [h[j:j + 2] for j in range(i, i + width, 2)]
        out.extend(reversed(chunk))
    return "".join(out)


def _bit_swap(h: str) -> str:
    return "".join(f"{int(format(int(h[i:i + 2], 16), '08b')[::-1], 2):02X}" for i in range(0, len(h), 2))


def _byte_skip(h: str, rule: str) -> str:
    pairs = [h[i:i + 2] for i in range(0, len(h), 2)]
    if rule == "odd":  # posiciones 1, 3, 5... contando desde 1
        return "".join(pairs[1::2])
    if rule == "even":
        return "".join(pairs[0::2])
    if rule.startswith("0x"):
        target = rule[2:].upper()
        return "".join(p for p in pairs if p != target)
    pattern = rule  # máscara de bytes a conservar, p. ej. "0001"
    return "".join(p for i, p in enumerate(pairs) if pattern[i % len(pattern)] == "1")


def _byte_trunc(h: str, byte: str) -> str:
    target = byte[2:].upper()
    for i in range(0, len(h), 2):
        if h[i:i + 2] == target:
            return h[:i]
    return h


def _byte_trim(h: str, byte: str) -> str:
    target = byte[2:].upper()
    while h.startswith(target) and len(h) % 2 == 0:
        h = h[2:]
    return h


def _nibble_skip(h: str, rule: str) -> str:
    return h[1::2] if rule == "odd" else h[0::2]


def _nibble_trim(h: str, nibble: str) -> str:
    return h.lstrip(nibble[2:].upper())


def _bitmask(h: str, masks: tuple[str, ...], completion: bool) -> str:
    bits = "".join(format(int(c, 16), "04b") for c in h)
    out = []
    for mask in masks:
        if len(mask) != len(bits):
            raise FormatError(f"bitmask de {len(mask)} bits para {len(bits)} bits de datos")
        selected = "".join(b for b, m in zip(bits, mask) if m == "1")
        if completion and len(selected) < 8:
            selected = selected.rjust(8, "0")
        out.append(selected)
    joined = "".join(out)
    if not joined:
        return ""
    joined = joined.rjust(-(-len(joined) // 8) * 8, "0")
    return "".join(f"{int(joined[i:i + 4], 2):X}" for i in range(0, len(joined), 4))


def transform_bytes(elt: Elt, raw: bytes, definition: Definition) -> str:
    """Aplica las manipulaciones de bytes en el orden por defecto documentado."""
    a = elt.attrs
    h = raw.hex().upper()
    if "byte-swap" in a:
        h = _byte_swap(h, int(a["byte-swap"]))
    if is_true(a.get("bit-swap")):
        h = _bit_swap(h)
    if "byte-skip" in a:
        h = _byte_skip(h, a["byte-skip"])
    if a.get("endianness") == "little_endian":
        h = "".join(reversed([h[i:i + 2] for i in range(0, len(h), 2)]))
    if "byte-trunc" in a:
        h = _byte_trunc(h, a["byte-trunc"])
    if "byte-trim" in a:
        h = _byte_trim(h, a["byte-trim"])
    if a.get("nibble-skip") in ("odd", "even"):
        h = _nibble_skip(h, a["nibble-skip"])
    if "nibble-trim" in a:
        h = _nibble_trim(h, a["nibble-trim"])
    if "bitmask" in a:
        bm = definition.bitmasks[a["bitmask"]]
        h = _bitmask(h, bm.masks, bm.byte_completion)
    return h


# --- Conversión por tipo --------------------------------------------------------


def _to_int(elt: Elt, h: str) -> int:
    if not h:
        raise FormatError(f"{elt.id}: campo numérico vacío")
    value = int(h, 16)
    if elt.attrs.get("base") == "16":
        digits = f"{value:X}"
        if not digits.isdigit():
            raise FormatError(f"{elt.id}: 0x{digits} no es un número decimal codificado (BCD)")
        value = int(digits)
    return value


def _to_text(elt: Elt, h: str, definition: Definition) -> str:
    a = elt.attrs
    nibbles = int(a.get("src-unit-size", "8")) // 4
    if len(h) % nibbles:
        raise FormatError(f"{elt.id}: {len(h)} nibbles no forman unidades de {nibbles * 4} bits")
    units = [int(h[i:i + nibbles], 16) for i in range(0, len(h), nibbles)]
    base = int(a["base"]) if a.get("base") in ("32", "40") else None
    codes: list[int] = []
    if base:
        width = int(a["dst-unit-size"])
        for unit in units:
            digits = []
            for _ in range(width):
                digits.append(unit % base)
                unit //= base
            if unit:
                raise FormatError(f"{elt.id}: valor fuera de rango para base {base}")
            codes.extend(reversed(digits))
    else:
        codes = units
    charsets = [definition.charsets[n] for n in a.get("charset", "").split(";") if n]
    step = int(a.get("ascii-step", "1"))
    offset = int(a.get("ascii-offset", "0"))
    out = []
    for code in codes:
        mapped = None
        for cs in charsets:
            if code in cs.mapping:
                mapped = cs.mapping[code]
                break
        if mapped is None:
            mapped = next((cs.default for cs in charsets if cs.default is not None), None)
        if mapped is None:
            if step == 0 or code % step:
                raise FormatError(f"{elt.id}: código 0x{code:02X} no es múltiplo de ascii-step={step}")
            value = code // step + offset
            if 0 <= value < 0x20 or value == 0x7F:
                # Carácter de control: se conserva para formatos como <case> y
                # se muestra como blanco (ver formats.render). Nunca es una letra.
                mapped = chr(value)
            elif 0x20 <= value <= 0x10FFFF and chr(value).isprintable():
                mapped = chr(value)
            else:
                raise FormatError(f"{elt.id}: código de carácter desconocido 0x{code:02X}")
        out.append(mapped)
    return "".join(out)


def decode_elt(elt: Elt, raw: bytes, definition: Definition) -> Value:
    h = transform_bytes(elt, raw, definition)
    if elt.type == "int":
        return _to_int(elt, h)
    if elt.type == "text":
        return _to_text(elt, h, definition)
    return h


# --- Recorrido de la estructura ---------------------------------------------------


@dataclass
class _Store:
    values: dict[str, dict[int, Value]]
    steps: dict[str, list[Value]]

    def put(self, elt_id: str, index: int, value: Value) -> None:
        self.values.setdefault(elt_id, {})[index] = value


def select_structure(definition: Definition, data: bytes, file_name: str,
                     regions: tuple[tuple[int, int, int, int], ...] | None = None) -> int:
    candidates = [
        i for i, s in enumerate(definition.structures)
        if s.matches_file(file_name) and (not s.sizes or len(data) in s.sizes)
    ]
    if regions is not None:
        with_regions = [i for i in candidates if not definition.structures[i].regions
                        or tuple(regions) in definition.structures[i].regions]
        if not with_regions and candidates:
            raise FormatError(
                f"{definition.game}: las regiones de hiscore.dat no coinciden con la definición"
            )
        candidates = with_regions
    if not candidates:
        sizes = sorted({n for s in definition.structures if s.matches_file(file_name) for n in s.sizes})
        raise FormatError(
            f"{definition.game}: {len(data)} bytes no coincide con ningún tamaño admitido {sizes}"
        )
    return candidates[0]


def _apply_structure(definition: Definition, structure: Structure, data: bytes) -> _Store:
    if structure.byte_swap:
        data = bytes.fromhex(_byte_swap(data.hex().upper(), structure.byte_swap))
    store = _Store({}, {})
    engine = definition.engine
    cursor = 0

    # Un elemento que excede el final del archivo se lee con los bytes que
    # existen, y uno que empieza después queda sin valor (celda vacía), como
    # hace hi2txt con archivos más cortos que la definición.
    for item in structure.items:
        if isinstance(item, Elt):
            raw = data[cursor:cursor + item.size]
            cursor += item.size
            if not raw:
                continue
            value = decode_elt(item, raw, definition)
            value = engine.apply(value, item.formats, Context())
            index = int(item.attrs.get("table-index", "0"))
            store.put(item.id, index, value)
            store.steps.setdefault(item.id, []).append(value)
            continue
        loop: Loop = item
        stride = sum(e.size for e in loop.elts)
        end = loop.count * stride - loop.skip_last_bytes
        for i in range(loop.count):
            position = loop.start + i * loop.step
            reverse = loop.start + (loop.count - 1 - i) * loop.step
            last_index = None
            relative = 0
            for elt in loop.elts:
                absolute = i * stride + relative
                relative += elt.size
                if absolute + elt.size <= loop.skip_first_bytes or absolute >= end:
                    continue  # parte del bucle que no se guarda en el archivo
                if absolute < loop.skip_first_bytes or absolute + elt.size > end:
                    raise FormatError(f"{definition.game}: skip-*-bytes corta el elemento {elt.id}")
                offset = cursor + absolute - loop.skip_first_bytes
                if offset >= len(data):
                    continue
                raw_value = decode_elt(elt, data[offset:offset + elt.size], definition)
                rule = elt.attrs.get("table-index", "loop_index")
                if rule == "loop_index":
                    index = position
                elif rule == "loop_reverse_index":
                    index = reverse
                elif rule.isdigit():
                    index = int(rule)
                elif rule == "itself":
                    index = int(_as_int(raw_value, elt.id))
                elif rule == "last":
                    if last_index is None:
                        raise FormatError(f"{elt.id}: table-index=last sin elemento previo")
                    index = last_index
                else:
                    # X:index_from_value: la fila es aquella cuyo valor de X es
                    # igual a este paso del bucle (X es una tabla de punteros de rango).
                    source = rule.split(":", 1)[0]
                    matches = [k for k, v in store.values.get(source, {}).items()
                               if _as_int(v, source) == position]
                    if len(matches) != 1:
                        raise FormatError(
                            f"{elt.id}: {len(matches)} filas de {source} apuntan al paso {position}"
                        )
                    index = matches[0]
                if "table-index-format" in elt.attrs:
                    from .formats import split_refs
                    index = _as_int(engine.apply(index, split_refs(elt.attrs["table-index-format"]), Context()), elt.id)
                value = engine.apply(raw_value, elt.formats, Context(loop_index=position))
                store.put(elt.id, index, value)
                store.steps.setdefault(elt.id, []).append(value)
                last_index = index
        cursor += loop.count * stride - loop.skip_first_bytes - loop.skip_last_bytes
    return store


def _as_int(value: Value, name: str) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = render(value)
    if text.lstrip("-").isdigit():
        return int(text)
    raise FormatError(f"{name}: {text!r} no sirve como índice")


def decode(definition: Definition, data: bytes, file_name: str | None = None,
           regions: tuple[tuple[int, int, int, int], ...] | None = None) -> Result:
    """Interpreta ``data`` con ``definition`` y devuelve tablas y campos."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("decode espera bytes")
    data = bytes(data)
    name = file_name or f"{definition.game}.hi"
    index = select_structure(definition, data, name, regions)
    structure = definition.structures[index]
    store = _apply_structure(definition, structure, data)
    return build_result(definition, structure, index, store.values)
