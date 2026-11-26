"""Correspondencias opcionales entre iniciales y personas (``jugadores.json``).

Formato::

    {
      "jugadores": {
        "Ana": ["ANA", "A.N"],
        "Beto": ["BTO"]
      }
    }

Las iniciales que no figuran se muestran tal cual. La correspondencia se aplica
al consultar: cambiarla no reescribe el historial guardado.

Además del archivo hay alias guardados en la base (tabla ``player_aliases``),
que la página web deja agregar, cambiar y borrar: iniciales -> nombre para
mostrar, de hasta 12 caracteres. ``load_players`` junta los dos; si unas
iniciales están en ambos, gana la base. Se aplican a las iniciales que se ven
en cada fila: las del juego o, si la fila tiene un nombre puesto con
``nombrar``, ese nombre. Las iniciales se comparan sin distinguir mayúsculas.
"""

from __future__ import annotations

import json
from pathlib import Path
import unicodedata
from typing import Dict, Iterable, List, Optional

from .models import ConfigError, HighScoreError

MAX_ALIAS = 12  # caracteres del nombre para mostrar (entra en las columnas JUGADOR)
MAX_ALIAS_INITIALS = 12


class AliasError(HighScoreError):
    """Alias no válido."""


def check_printable(value: str, what: str) -> None:
    from .ui.pixelfont import normalize

    if any(unicodedata.category(c).startswith("C") for c in value):
        raise AliasError(f"{what}: hay caracteres no válidos")
    if "?" in normalize(value) and "?" not in value:
        raise AliasError(f"{what}: usar letras, números, espacio y signos simples (. , - ! ' &)")


def clean_alias_initials(text: str) -> str:
    value = " ".join(str(text).split()).upper()
    if not value:
        raise AliasError("faltan las iniciales")
    if len(value) > MAX_ALIAS_INITIALS:
        raise AliasError(f"las iniciales pueden tener hasta {MAX_ALIAS_INITIALS} caracteres")
    if value == "???":
        raise AliasError("iniciales no válidas")
    check_printable(value, "las iniciales")
    return value


def clean_alias_name(text: str) -> str:
    value = " ".join(str(text).split()).upper()
    if not value:
        raise AliasError("falta el nombre para mostrar")
    if len(value) > MAX_ALIAS:
        raise AliasError(f"el nombre para mostrar puede tener hasta {MAX_ALIAS} caracteres")
    if value == "???":
        raise AliasError("nombre no válido")
    check_printable(value, "el nombre")
    return value


class Players:
    def __init__(self, mapping: Optional[Dict[str, str]] = None):
        self.mapping = dict(mapping or {})

    @classmethod
    def from_data(cls, data) -> "Players":
        if not isinstance(data, dict) or not isinstance(data.get("jugadores", {}), dict):
            raise ConfigError('jugadores.json debe tener la forma {"jugadores": {"Nombre": ["INI", ...]}}')
        mapping: Dict[str, str] = {}
        for name, initials in data.get("jugadores", {}).items():
            if not isinstance(name, str) or not name.strip():
                raise ConfigError("jugadores.json: hay un nombre vacío")
            if not isinstance(initials, list) or not all(isinstance(i, str) and i.strip() for i in initials):
                raise ConfigError(f"jugadores.json: las iniciales de {name!r} deben ser una lista de textos")
            for item in initials:
                key = item.strip()
                if key in mapping and mapping[key] != name:
                    raise ConfigError(f"jugadores.json: {key!r} figura para {mapping[key]!r} y para {name!r}")
                mapping[key] = name.strip()
        return cls(mapping)

    @classmethod
    def load(cls, path: Optional[Path]) -> "Players":
        """Lee el archivo; si no existe, no hay correspondencias."""
        if path is None or not Path(path).is_file():
            return cls()
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ConfigError(f"jugadores.json no es JSON válido: {exc}") from exc
        return cls.from_data(data)

    def with_aliases(self, aliases: Dict[str, str]) -> "Players":
        """Copia con los alias de la base agregados (ganan sobre los del archivo)."""
        mapping = dict(self.mapping)
        mapping.update({k.strip(): v for k, v in aliases.items()})
        return Players(mapping)

    def name(self, initials: str) -> str:
        key = initials.strip()
        if key in self.mapping:
            return self.mapping[key]
        upper = key.upper()
        for candidate, name in self.mapping.items():
            if candidate.upper() == upper:
                return name
        return key

    def names(self, initials: Iterable[str]) -> List[str]:
        """Nombres finales, sin repetir (se comparan sin distinguir mayúsculas ni espacios)."""
        found: Dict[str, str] = {}
        for item in sorted(initials):
            name = " ".join(self.name(item).split())
            found.setdefault(name_key(name), name)
        return sorted(found.values())


def name_key(name: str) -> str:
    """Clave para agrupar nombres: sin espacios de más y en mayúsculas."""
    return " ".join(str(name).split()).upper()


def load_players(path: Optional[Path], db=None) -> Players:
    """``jugadores.json`` (si existe) más los alias guardados en la base."""
    players = Players.load(path)
    return players.with_aliases(db.aliases()) if db is not None else players
