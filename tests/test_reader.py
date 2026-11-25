import tempfile
import unittest
from pathlib import Path

from arcade_hall_of_fame.models import SourceReadError
from arcade_hall_of_fame.reader import read_source


class ReadSourceTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "datos.bin"

    def test_lee_hasta_el_maximo(self):
        self.path.write_bytes(b"\x01\x02\x03")
        self.assertEqual(read_source(self.path, max_size=3), b"\x01\x02\x03")

    def test_archivo_vacio(self):
        self.path.write_bytes(b"")
        self.assertEqual(read_source(self.path, max_size=3), b"")

    def test_rechaza_archivo_mayor(self):
        self.path.write_bytes(b"\x00" * 4)
        with self.assertRaises(SourceReadError):
            read_source(self.path, max_size=3)

    def test_error_no_expone_la_ruta_completa(self):
        with self.assertRaises(SourceReadError) as ctx:
            read_source(self.path, max_size=3)
        self.assertNotIn(str(self.path.parent), str(ctx.exception))

    def test_max_size_negativo(self):
        with self.assertRaises(ValueError):
            read_source(self.path, max_size=-1)


if __name__ == "__main__":
    unittest.main()
