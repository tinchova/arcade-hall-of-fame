import unittest

from arcade_hall_of_fame.hi2txt.formats import (
    Context,
    FormatEngine,
    NamedFormat,
    Operation,
    SubColumn,
    render,
)
from arcade_hall_of_fame.models import FormatError


class ImplicitFormatsTest(unittest.TestCase):
    def setUp(self):
        self.engine = FormatEngine({})

    def apply(self, value, *refs):
        return self.engine.apply(value, refs, Context())

    def test_aritmetica(self):
        self.assertEqual(self.apply(4008, "*10"), 40080)
        self.assertEqual(self.apply(4, "+1"), 5)
        self.assertEqual(self.apply(10, "-3"), 7)
        self.assertEqual(self.apply(5800, "d60"), 96)
        self.assertEqual(self.apply(5800, "D60"), 97)
        self.assertEqual(self.apply(125, "%60"), 5)
        self.assertEqual(self.apply(100, "/4"), 25)
        self.assertEqual(self.apply(7, "*2", "+1"), 15)

    def test_texto(self):
        self.assertEqual(self.apply("abc", "UC"), "ABC")
        self.assertEqual(self.apply("ABC", "LC"), "abc")
        self.assertEqual(self.apply("5", "PadL20"), "05")
        self.assertEqual(self.apply("0050", "TrimL0"), "50")
        self.assertEqual(self.apply("12", "Suffix%"), "12%")
        self.assertEqual(self.apply("", "Suffix%"), "")
        self.assertEqual(self.apply(255, "0x"), "0xFF")

    def test_celda_vacia_en_aritmetica(self):
        self.assertEqual(self.apply(None, "+1"), 1)  # comportamiento de hi2txt

    def test_texto_no_numerico(self):
        with self.assertRaises(FormatError):
            self.apply("ABC", "*10")

    def test_formato_desconocido(self):
        with self.assertRaises(FormatError):
            self.apply(1, "nada")
        self.assertEqual(self.engine.unsupported(("nada",)), ["format desconocido 'nada'"])


class NamedFormatsTest(unittest.TestCase):
    def test_casos_con_default_y_operador(self):
        fmt = NamedFormat("nivel", (
            Operation("case", "", {"src": "0", "dst": "FACIL", "default": "yes"}),
            Operation("case", "", {"src": "1", "dst": "NORMAL"}),
            Operation("case", "", {"src": "10", "operator": ">=", "dst": "EXPERTO"}),
        ))
        engine = FormatEngine({"nivel": fmt})
        apply = lambda v: engine.apply(v, ("nivel",), Context())
        self.assertEqual([apply(0), apply(1), apply(12), apply(5)], ["FACIL", "NORMAL", "EXPERTO", "FACIL"])

    def test_case_por_caracter_con_codigo_hexadecimal(self):
        fmt = NamedFormat("c", (Operation("case", "", {"src": "0x40", "dst": "."}),), apply_to_char=True)
        engine = FormatEngine({"c": fmt})
        self.assertEqual(engine.apply("A@B", ("c",), Context()), "A.B")

    def test_concat_y_sum_con_columnas(self):
        values = {"MIN": 3, "SEC": 7, "A": 100, "B": 5}
        ctx = Context(lookup=values.get)
        concat = NamedFormat("t", (Operation("concat", "", {}, (
            SubColumn("column", "MIN", (), None),
            SubColumn("txt", None, (), ":"),
            SubColumn("column", "SEC", ("PadL20",), None),
        )),))
        total = NamedFormat("s", (Operation("sum", "", {}, (
            SubColumn("column", "A", ("*10",), None),
            SubColumn("column", "B", (), None),
        )),))
        engine = FormatEngine({"t": concat, "s": total})
        self.assertEqual(engine.apply(None, ("t",), ctx), "3:07")
        self.assertEqual(engine.apply(None, ("s",), ctx), 1005)

    def test_entrada_como_subcolumna(self):
        fmt = NamedFormat("pct", (Operation("concat", "", {}, (
            SubColumn("column", None, ("d100",), None),
            SubColumn("txt", None, (), "."),
            SubColumn("column", None, ("%100", "PadL20"), None),
        )),), subcolumns_input=True)
        engine = FormatEngine({"pct": fmt})
        self.assertEqual(engine.apply(1234, ("pct",), Context()), "12.34")

    def test_prefijo_con_vacio_consumido(self):
        fmt = NamedFormat("m", (Operation("prefix", "AC", {"empty": "0", "consume": "yes"}),))
        engine = FormatEngine({"m": fmt})
        self.assertEqual(engine.apply(0, ("m",), Context()), "")
        self.assertEqual(engine.apply(3, ("m",), Context()), "AC3")

    def test_render(self):
        self.assertEqual(render(None), "")
        self.assertEqual(render(2.0), "2")
        self.assertEqual(render("A\x01"), "A ")


if __name__ == "__main__":
    unittest.main()
