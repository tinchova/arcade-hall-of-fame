"""Tablas de fábrica publicadas por hi2txt-xml (``src/main/db_defaults``).

Sirven para reconocer entradas precargadas por el juego, que no otorgan crédito
a nadie. Se leen de la carpeta descargada por el usuario; no se distribuyen.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import FrozenSet, Optional, Tuple

from .definition import GAME_NAME_RE, sameas_target

FactoryRow = Tuple[str, str]  # (puntuación tal como se muestra, iniciales)


class FactoryTables:
    def __init__(self, directory: Optional[Path]):
        self.directory = Path(directory) if directory else None
        self._cache: dict = {}

    def rows(self, game: str) -> FrozenSet[FactoryRow]:
        """Pares (puntuación, iniciales) de la tabla de fábrica; vacío si no hay."""
        if game in self._cache:
            return self._cache[game]
        result: FrozenSet[FactoryRow] = frozenset()
        if self.directory is not None and GAME_NAME_RE.match(game):
            result = self._load(game, set())
        self._cache[game] = result
        return result

    def _load(self, game: str, seen: set) -> FrozenSet[FactoryRow]:
        path = self.directory / f"{game}.xml"
        if game in seen or not path.is_file():
            return frozenset()
        data = path.read_bytes()
        target = sameas_target(data)
        if target:
            return self._load(target, seen | {game})
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            return frozenset()
        for table in root.iter("table"):
            columns = [c.text or "" for c in table.findall("col")]
            if "SCORE" not in columns:
                continue
            score_at = columns.index("SCORE")
            name_at = columns.index("NAME") if "NAME" in columns else None
            rows = set()
            for row in table.findall("row"):
                cells = [c.text or "" for c in row.findall("cell")]
                if len(cells) != len(columns):
                    continue
                rows.add((cells[score_at], cells[name_at] if name_at is not None else ""))
            return frozenset(rows)
        return frozenset()
