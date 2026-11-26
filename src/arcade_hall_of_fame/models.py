"""Errores compartidos por el lector y el intérprete de definiciones."""

from __future__ import annotations


class HighScoreError(Exception):
    """Error base de lectura o interpretación de tablas de puntuaciones."""


class SourceReadError(HighScoreError):
    """El archivo de origen no se pudo leer o no tiene un tamaño admisible."""


class DefinitionError(HighScoreError):
    """La definición de un juego falta, está mal formada o es incoherente."""


class MissingDefinition(DefinitionError):
    """No hay definición para el juego (ni propia ni por ``sameas``)."""


class UnsupportedDefinition(DefinitionError):
    """La definición usa operaciones que el intérprete todavía no implementa.

    ``features`` enumera cada operación no soportada, para poder medir y
    priorizar qué implementar después.
    """

    def __init__(self, game: str, features: list[str] | tuple[str, ...]):
        self.game = game
        self.features = tuple(sorted(set(features)))
        super().__init__(
            f"{game}: la definición usa operaciones no soportadas: "
            + ", ".join(self.features)
        )


class FormatError(HighScoreError):
    """Los bytes no se pueden interpretar con la definición elegida."""


class IncompatibleFile(FormatError):
    """El archivo no corresponde a lo que describe la definición.

    Tamaño, regiones de memoria o tipo de archivo distintos: el problema es de la
    definición para este emulador, no de una lectura puntual.
    """


class ConfigError(HighScoreError):
    """La configuración local (por ejemplo, jugadores.json) no es válida."""
