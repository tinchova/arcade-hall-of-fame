"""Comprobación local opcional contra copias privadas de archivos reales.

Ni las muestras ni las definiciones entran al repositorio. Cada prueba se
saltea si falta su variable de entorno; saltearla no acredita compatibilidad.

Variables:

* ``ARCADE_HOF_HI2TXT_DB``: carpeta ``src/main/db`` descargada con ``fetch``.
* ``ARCADE_HOF_GALAGA_SAMPLE`` / ``ARCADE_HOF_BUBLBOBL_SAMPLE``: copias de los ``.hi``.
* ``ARCADE_HOF_GALAGA_EXPECTED`` / ``ARCADE_HOF_BUBLBOBL_EXPECTED``: filas que se
  ven en pantalla, como ``"20000 N.N;20000 A.A;..."`` (puntuación, espacio e
  iniciales; las iniciales pueden tener espacios). Sin ellas solo se comprueba
  que el archivo se decodifica y no cambia.
"""

import hashlib
import os
import unittest
from pathlib import Path

from arcade_hall_of_fame.hi2txt import DefinitionLibrary, read_file

DB_ENV = "ARCADE_HOF_HI2TXT_DB"


def parse_expected(text: str):
    rows = []
    for part in text.split(";"):
        score, _, initials = part.lstrip().partition(" ")
        rows.append((int(score), initials))
    return rows


class RealSampleTest(unittest.TestCase):
    def check(self, game: str, sample_env: str, expected_env: str):
        if not os.environ.get(DB_ENV) or not os.environ.get(sample_env):
            self.skipTest(f"definir {DB_ENV} y {sample_env}")
        library = DefinitionLibrary(os.environ[DB_ENV])
        path = Path(os.environ[sample_env])
        before = (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).digest())
        result = read_file(library.load(game), path)
        after = (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).digest())
        self.assertEqual(before, after, "la lectura modificó el original")
        rows = [(row.score, row.initials) for row in result.score_rows()]
        self.assertEqual(len(rows), 5)
        expected = os.environ.get(expected_env)
        if expected:
            self.assertEqual(rows, parse_expected(expected))

    def test_galaga(self):
        self.check("galaga", "ARCADE_HOF_GALAGA_SAMPLE", "ARCADE_HOF_GALAGA_EXPECTED")

    def test_bublbobl(self):
        self.check("bublbobl", "ARCADE_HOF_BUBLBOBL_SAMPLE", "ARCADE_HOF_BUBLBOBL_EXPECTED")


if __name__ == "__main__":
    unittest.main()
