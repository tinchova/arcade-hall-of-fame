import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from arcade_hall_of_fame.hi2txt import DefinitionLibrary, decode, parse_definition
from arcade_hall_of_fame.hi2txt.fetch import extract
from arcade_hall_of_fame.hi2txt.hiscore_dat import expected_size, parse_hiscore_dat
from arcade_hall_of_fame.models import DefinitionError, UnsupportedDefinition

from .synthetic import DEMO_BCD, xml

MINIMAL = """
  <structure file=".hi"><check><size>1</size></check>{elt}</structure>
  <output><table><column id="A"/></table></output>{extra}"""


def minimal(elt='<elt size="1" type="int" id="A"/>', extra=""):
    return xml(MINIMAL.format(elt=elt, extra=extra))


class UnsupportedTest(unittest.TestCase):
    def assert_unsupported(self, data: bytes, feature: str):
        with self.assertRaises(UnsupportedDefinition) as ctx:
            parse_definition("demo", data)
        self.assertIn(feature, ctx.exception.features)

    def test_base_no_implementada(self):
        self.assert_unsupported(minimal('<elt size="1" type="int" id="A" base="7"/>'), "elt@base=7")

    def test_atributo_desconocido(self):
        self.assert_unsupported(minimal('<elt size="1" type="int" id="A" magic="1"/>'), "elt@magic")

    def test_formatter_y_operacion_desconocida(self):
        extra = '<format id="f" formatter="%d-%d"><divide>100</divide></format>'
        self.assert_unsupported(minimal(extra=extra), "format@formatter=%d-%d")
        extra = '<format id="f" formatter="%tY"/>'
        self.assert_unsupported(minimal(extra=extra), "format@formatter=%tY")
        extra = '<format id="f"><shift>2</shift></format>'
        self.assert_unsupported(minimal(extra=extra), "format <shift>")

    def test_formato_inexistente(self):
        data = xml("""<structure file=".hi"><check><size>1</size></check><elt size="1" type="int" id="A"/></structure>
          <output><table><column id="A" format="nada"/></table></output>""")
        self.assert_unsupported(data, "format desconocido 'nada'")

    def test_charset_predefinido_desconocido(self):
        self.assert_unsupported(
            minimal('<elt size="1" type="text" id="A" charset="CS_LETTER"/>'), "charset predefinido CS_LETTER"
        )

    def test_el_mensaje_enumera_las_operaciones(self):
        with self.assertRaisesRegex(UnsupportedDefinition, "elt@base=7"):
            parse_definition("demo", minimal('<elt size="1" type="int" id="A" base="7"/>'))


class DefinitionErrorTest(unittest.TestCase):
    def test_xml_invalido(self):
        with self.assertRaises(DefinitionError):
            parse_definition("demo", b"<hi2txt><structure>")

    def test_charset_inexistente(self):
        with self.assertRaisesRegex(DefinitionError, "charset inexistente"):
            parse_definition("demo", minimal('<elt size="1" type="text" id="A" charset="nada"/>'))

    def test_entidad_sin_dtd(self):
        data = minimal('<elt size="1" type="text" id="A" charset="c"/>',
                       '<charset id="c"><char src="0x01" dst="&corazon;"/></charset>')
        with self.assertRaisesRegex(DefinitionError, "entidad desconocida"):
            parse_definition("demo", data)

    def test_entidad_con_dtd(self):
        data = minimal('<elt size="1" type="text" id="A" charset="c"/>',
                       '<charset id="c"><char src="0x01" dst="&corazon;"/></charset>')
        definition = parse_definition("demo", data, {"corazon": "&#9829;"})
        self.assertEqual(decode(definition, b"\x01").tables[0].rows, (("♥",),))


class LibraryTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        (self.dir / "demo.xml").write_bytes(DEMO_BCD)
        (self.dir / "democlon.xml").write_bytes(xml('<sameas id="demo"/>'))
        (self.dir / "ciclo1.xml").write_bytes(xml('<sameas id="ciclo2"/>'))
        (self.dir / "ciclo2.xml").write_bytes(xml('<sameas id="ciclo1"/>'))
        (self.dir / "huerfano.xml").write_bytes(xml('<sameas id="noexiste"/>'))
        (self.dir / "hi2txt.dtd").write_text('<!ENTITY corazon "&#9829;">\n', encoding="utf-8")
        self.library = DefinitionLibrary(self.dir)

    def test_alias_sameas(self):
        definition = self.library.load("democlon")
        self.assertEqual(definition.game, "democlon")
        self.assertEqual(len(definition.structures), 1)

    def test_ciclo_y_destino_inexistente(self):
        with self.assertRaisesRegex(DefinitionError, "ciclo"):
            self.library.load("ciclo1")
        with self.assertRaisesRegex(DefinitionError, "noexiste"):
            self.library.load("huerfano")

    def test_juego_sin_definicion_y_nombre_invalido(self):
        with self.assertRaisesRegex(DefinitionError, "no hay definición"):
            self.library.load("otro")
        with self.assertRaisesRegex(DefinitionError, "inválido"):
            self.library.load("../demo")

    def test_entidades_del_dtd_local(self):
        self.assertEqual(self.library.entities, {"corazon": "&#9829;"})


class HiscoreDatTest(unittest.TestCase):
    def test_formatos_y_grupos(self):
        text = """; comentario
juegoa:
juegob:  ; clon
@:maincpu,program,8a20,2d,00,18
@:maincpu,program,83ed,6,00,24,00

juegoc,soft:
@:maincpu,program,1,1,0,0
juegod:
0:e654:23:00:48
"""
        entries = parse_hiscore_dat(text)
        self.assertEqual(entries["juegoa"], ((0x8A20, 0x2D, 0, 0x18), (0x83ED, 6, 0, 0x24)))
        self.assertEqual(entries["juegob"], entries["juegoa"])
        self.assertEqual(expected_size(entries["juegoa"]), 51)
        self.assertEqual(entries["juegod"], ((0xE654, 0x23, 0, 0x48),))
        self.assertNotIn("juegoc", entries)


class FetchExtractTest(unittest.TestCase):
    def archive(self, names):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            for name in names:
                zf.writestr(name, "x")
        return buffer.getvalue()

    def test_extrae_solo_rutas_admitidas(self):
        data = self.archive(["r/src/main/db/a.xml", "r/LICENSE", "r/build.gradle", "r/src/test/x.hi"])
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(extract(data, Path(tmp), include_tests=False), 2)
            self.assertTrue((Path(tmp) / "src" / "main" / "db" / "a.xml").is_file())
            self.assertFalse((Path(tmp) / "build.gradle").exists())

    def test_rechaza_rutas_peligrosas(self):
        data = self.archive(["r/src/main/db/../../../../fuera.xml"])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                extract(data, Path(tmp), include_tests=False)


if __name__ == "__main__":
    unittest.main()
