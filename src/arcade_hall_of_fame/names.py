"""Nombres legibles de los juegos ("Bubble Bobble" en lugar de "bublbobl").

Fuentes, en orden de prioridad, todas leídas en modo lectura:

1. ``gamelist.xml`` de ES-DE (``<game><path>./bublbobl.zip</path><name>…``);
2. un DAT de FBNeo en formato XML de ClrMame Pro (``<game name="bublbobl"><description>…``);
3. el atributo ``label`` de la definición propia del juego en hi2txt-xml (no el
   de un alias ``sameas``, que sería el nombre de otro juego);
4. el nombre del zip, solo si no hay otra opción.

Se quitan los paréntesis de región o versión ("Bubble Bobble (Japan, Ver 0.1)" se
muestra como "Bubble Bobble"). Si dos juegos mostrados juntos quedan con el mismo
nombre, se muestra el nombre completo, y si aun así coinciden, el set entre corchetes.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, Optional

_GROUP = re.compile(r"\s*[\(\[][^\(\)\[\]]*[\)\]]")


def clean(name: str) -> str:
    """Quita los paréntesis y corchetes (región, versión, set), también anidados."""
    text = " ".join(name.split())
    while True:
        shorter = _GROUP.sub("", text).strip()
        if shorter == text or not shorter:
            return " ".join(text.split())
        text = shorter


def _stem(path_text: str) -> str:
    name = PurePosixPath(path_text.replace("\\", "/")).name
    return name.rsplit(".", 1)[0] if "." in name else name


def load_gamelist(path: Path) -> Dict[str, str]:
    """ES-DE: ruta del juego → nombre."""
    names: Dict[str, str] = {}
    root = ET.parse(str(path)).getroot()
    for game in root.iter("game"):
        stem, name = _stem(game.findtext("path", "")), (game.findtext("name") or "").strip()
        if stem and name:
            names[stem] = name
    return names


def load_dat(path: Path) -> Dict[str, str]:
    """DAT XML de ClrMame Pro (FBNeo, MAME): set → descripción."""
    names: Dict[str, str] = {}
    for _event, element in ET.iterparse(str(path)):
        if element.tag in ("game", "machine"):
            set_name, description = element.get("name"), (element.findtext("description") or "").strip()
            if set_name and description:
                names[set_name] = description
            element.clear()
    return names


def load_labels(definitions_dir: Optional[Path], games: Iterable[str]) -> Dict[str, str]:
    """``label`` de la definición propia de cada juego en hi2txt-xml."""
    names: Dict[str, str] = {}
    if definitions_dir is None:
        return names
    for game in games:
        path = Path(definitions_dir) / f"{game}.xml"
        if not re.fullmatch(r"[A-Za-z0-9_]+", game) or not path.is_file():
            continue
        try:
            root = ET.fromstring(re.sub(rb"&(?!(?:amp|lt|gt|quot|apos);)[A-Za-z][\w.-]*;", b"?", path.read_bytes()))
        except ET.ParseError:
            continue
        if root.find("sameas") is None and root.get("label"):
            names[game] = root.get("label")
    return names


class GameNames:
    def __init__(self, *sources: Dict[str, str]):
        self.sources = [s for s in sources if s]
        self.games: Iterable[str] = ()
        self._cache: Dict[str, str] = {}

    def full(self, game: str) -> Optional[str]:
        for source in self.sources:
            if game in source:
                return " ".join(source[game].split())
        return None

    def set_games(self, games: Iterable[str]) -> None:
        """Juegos que se muestran juntos: los nombres repetidos se desambiguan."""
        self.games = tuple(sorted(set(games)))
        self._cache = {}
        short = {g: clean(self.full(g) or g) for g in self.games}
        counts: Dict[str, int] = {}
        for name in short.values():
            counts[name] = counts.get(name, 0) + 1
        resolved = {}
        for game, name in short.items():
            if counts[name] > 1:
                name = self.full(game) or game  # muestra región o versión
            resolved[game] = name
        counts = {}
        for name in resolved.values():
            counts[name] = counts.get(name, 0) + 1
        for game, name in resolved.items():
            self._cache[game] = f"{name} [{game}]" if counts[name] > 1 else name

    def name(self, game: str) -> str:
        if game in self._cache:
            return self._cache[game]
        full = self.full(game)
        return clean(full) if full else game

    def known(self, game: str) -> bool:
        return self.full(game) is not None


def from_files(gamelist: Optional[str], dats: Iterable[Path], definitions_dir: Optional[Path],
               games: Iterable[str]) -> GameNames:
    """Arma los nombres con los archivos indicados; uno ausente o ilegible se omite.

    ``dats`` puede incluir archivos o carpetas (se leen todos sus ``.dat``).
    """
    games = list(games)
    sources = []
    if gamelist and Path(gamelist).is_file():
        try:
            sources.append(load_gamelist(Path(gamelist)))
        except (ET.ParseError, OSError):
            pass
    merged: Dict[str, str] = {}
    for item in dats:
        paths = sorted(Path(item).glob("*.dat")) if Path(item).is_dir() else [Path(item)]
        for path in paths:
            if path.is_file():
                try:
                    merged.update(load_dat(path))
                except (ET.ParseError, OSError):
                    pass
    sources.append(merged)
    sources.append(load_labels(definitions_dir, games))
    names = GameNames(*sources)
    names.set_games(games)
    return names
