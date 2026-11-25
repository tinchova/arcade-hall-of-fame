"""Correspondencias opcionales entre iniciales y personas (``jugadores.json``).

Formato::

    {
      "jugadores": {
        "Ana": ["NIC", "N.C"],
        "Ana": ["ANA"]
      }
    }

Las iniciales que no figuran se muestran tal cual. La correspondencia se aplica
al consultar: cambiarla no reescribe el historial guardado.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .models import ConfigError


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

    def name(self, initials: str) -> str:
        key = initials.strip()
        return self.mapping.get(key, key)

    def names(self, initials: Iterable[str]) -> List[str]:
        return sorted({self.name(i) for i in initials})
