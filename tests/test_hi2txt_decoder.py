import unittest

from arcade_hall_of_fame.hi2txt import ScoreRow, decode, parse_definition
from arcade_hall_of_fame.hi2txt.formats import render
from arcade_hall_of_fame.models import FormatError

from .synthetic import DEMO_BCD, DEMO_BCD_BYTES, DEMO_ROWS, DEMO_ROWS_BYTES, xml


def replace(data: bytes, offset: int, new: bytes) -> bytes:
    return data[:offset] + new + data[offset + len(new):]


class BcdDefinitionTest(unittest.TestCase):
    def setUp(self):
        self.definition = parse_definition("demo", DEMO_BCD)

    def test_filas_puntuacion_e_iniciales(self):
        result = decode(self.definition, DEMO_BCD_BYTES)
        self.assertEqual(
            result.score_rows(),
            (ScoreRow(1, 345, "A."), ScoreRow(2, 20, " Z"), ScoreRow(3, 7, "MC")),
        )
        self.assertEqual(result.field("TOP SCORE"), 345)

    def test_tabla_completa_con_columnas(self):
        table = decode(self.definition, DEMO_BCD_BYTES).main_table()
        self.assertEqual(table.columns, ("RANK", "SCORE", "NAME"))
        self.assertEqual(table.rows[0], (1, 345, "A."))

    def test_largo_incorrecto(self):
        for size in (0, 17, 19):
            with self.subTest(size=size):
                with self.assertRaisesRegex(FormatError, "no coincide con ningún tamaño"):
                    decode(self.definition, (DEMO_BCD_BYTES * 2)[:size])

    def test_bcd_invalido(self):
        data = replace(DEMO_BCD_BYTES, 0, bytes([0x0A]))  # nibble A no es decimal
        with self.assertRaisesRegex(FormatError, "BCD"):
            decode(self.definition, data)

    def test_puntuacion_vacia(self):
        data = replace(DEMO_BCD_BYTES, 3, bytes([0x24, 0x24, 0x24]))
        with self.assertRaisesRegex(FormatError, "vacío"):
            decode(self.definition, data)

    def test_caracter_no_imprimible(self):
        # 0x60 + 55 = 0x97, un control C1: no se adivina una letra.
        data = replace(DEMO_BCD_BYTES, 9, bytes([0x60]))
        with self.assertRaisesRegex(FormatError, "carácter desconocido 0x60"):
            decode(self.definition, data)

    def test_tipo_incorrecto(self):
        with self.assertRaises(TypeError):
            decode(self.definition, "texto")

    def test_archivo_que_no_corresponde_a_la_estructura(self):
        with self.assertRaises(FormatError):
            decode(self.definition, DEMO_BCD_BYTES, file_name="nvram")


class RowsDefinitionTest(unittest.TestCase):
    def test_filas_intercaladas_y_formatos(self):
        result = decode(parse_definition("demo2", DEMO_ROWS), DEMO_ROWS_BYTES)
        table = result.main_table()
        self.assertEqual(table.id, "TOP")
        self.assertEqual(
            table.rows,
            ((1, 40080, "A", 5), (2, 30000, "B", 32), (3, 12500, ".", 1)),
        )
        self.assertEqual(result.score_rows()[0], ScoreRow(1, 40080, "A"))


class StructureFeaturesTest(unittest.TestCase):
    def table(self, body: str, data: bytes):
        return decode(parse_definition("demo", xml(body)), data).tables[0]

    def test_indice_inverso_y_fijo(self):
        body = """
          <structure file=".hi"><check><size>4</size></check>
            <loop count="3"><elt size="1" type="int" id="SCORE" table-index="loop_reverse_index"/></loop>
            <elt size="1" type="int" id="SCORE" table-index="5"/>
          </structure>
          <output><table><column id="SCORE"/></table></output>"""
        self.assertEqual(self.table(body, bytes([1, 2, 3, 9])).rows, ((3,), (2,), (1,), (9,)))

    def test_puntero_de_rango(self):
        body = """
          <structure file=".hi"><check><size>6</size></check>
            <loop count="3"><elt size="1" type="int" id="PTR"/></loop>
            <loop count="3"><elt size="1" type="int" id="SCORE" table-index="PTR:index_from_value"/></loop>
          </structure>
          <output><table><column id="RANK" src="index" format="+1"/><column id="SCORE"/></table></output>"""
        # La fila 0 apunta al paso 2, la 1 al 0 y la 2 al 1.
        data = bytes([2, 0, 1, 10, 20, 30])
        self.assertEqual(self.table(body, data).rows, ((1, 30), (2, 10), (3, 20)))

    def test_byte_skip_nibble_skip_y_byte_swap(self):
        body = """
          <structure file=".hi"><check><size>4</size></check>
            <elt size="4" type="int" id="A" byte-skip="odd" base="16"/>
          </structure>
          <output><table><column id="A"/></table></output>"""
        self.assertEqual(self.table(body, bytes([0xFF, 0x12, 0xFF, 0x34])).rows, ((1234,),))
        body = body.replace('byte-skip="odd" base="16"', 'nibble-skip="odd" base="16"')
        self.assertEqual(self.table(body, bytes([0x01, 0x02, 0x03, 0x04])).rows, ((1234,),))
        body = body.replace('nibble-skip="odd" base="16"', 'byte-swap="2" base="16"')
        self.assertEqual(self.table(body, bytes([0x12, 0x00, 0x34, 0x00])).rows, ((120034,),))

    def test_archivo_mas_corto_deja_celda_vacia(self):
        body = """
          <structure file=".hi"><check><size>3</size></check>
            <loop count="2"><elt size="2" type="int" id="SCORE"/></loop>
          </structure>
          <output><table><column id="RANK" src="index" format="+1"/><column id="SCORE"/></table></output>"""
        # El segundo elemento existe solo a medias: se usa el byte disponible.
        self.assertEqual(self.table(body, bytes([0, 5, 7])).rows, ((1, 5), (2, 7)))

    def test_lineas_ignoradas_maximo_y_orden(self):
        body = """
          <structure file=".hi"><check><size>4</size></check>
            <loop count="4"><elt size="1" type="int" id="SCORE"/></loop>
          </structure>
          <output><table line-ignore="SCORE:0" sort="SCORE" sort-order="desc" lines-max="2">
            <column id="RANK" src="index" format="+1"/><column id="SCORE"/>
          </table></output>"""
        self.assertEqual(self.table(body, bytes([5, 0, 9, 7])).rows, ((1, 9), (2, 7)))

    def test_control_se_muestra_como_blanco(self):
        body = """
          <structure file=".hi"><check><size>3</size></check>
            <elt size="3" type="text" id="NAME"/>
          </structure>
          <output><table><column id="NAME"/></table></output>"""
        value = self.table(body, b"A\x00B").rows[0][0]
        self.assertEqual(value, "A\x00B")  # se conserva para <case>
        self.assertEqual(render(value), "A B")

    def test_base_40(self):
        body = """
          <structure file=".hi"><check><size>2</size></check>
            <elt size="2" type="text" id="NAME" decoding-profile="base-40"/>
          </structure>
          <output><table><column id="NAME"/></table></output>"""
        # (1 * 40 + 2) * 40 + 3 = 1683 = 0x0693 -> códigos 1, 2, 3 -> "ABC"
        self.assertEqual(self.table(body, bytes([0x06, 0x93])).rows, (("ABC",),))

    def test_base_256_un_digito_por_byte(self):
        body = """
          <structure file=".hi"><check><size>4</size></check>
            <elt size="4" type="int" id="SCORE" base="256"/>
          </structure>
          <output><table><column id="SCORE"/></table></output>"""
        self.assertEqual(self.table(body, bytes([0, 2, 7, 3])).rows, ((273,),))
        with self.assertRaisesRegex(FormatError, "base 256"):
            self.table(body, bytes([0, 2, 0x0A, 3]))

    def test_charset_predefinido_cs_number(self):
        body = """
          <structure file=".hi"><check><size>4</size></check>
            <elt size="4" type="text" id="NAME" charset="CS_NUMBER[{cs}];demo" ascii-offset="65" ascii-step="{step}"/>
          </structure>
          <output><table><column id="NAME"/></table></output>
          <charset id="demo"><char src="FE" dst="."/></charset>"""
        # Cifras desde el código 1 (0 = A por ascii-offset); FE sin 0x es hexadecimal.
        self.assertEqual(self.table(body.format(cs="-47", step="1"), bytes([1, 10, 0, 0xFE])).rows, (("09A.",),))
        # Con delta 1 las cifras van de dos en dos, como las letras con ascii-step=2.
        self.assertEqual(self.table(body.format(cs="4,1", step="2"), bytes([0x34, 0x46, 2, 0xFE])).rows,
                         (("09B.",),))

    def test_line_ignore_sin_valor_omite_filas_vacias(self):
        body = """
          <structure file=".hi"><check><size>4</size></check>
            <loop count="3"><elt size="1" type="int" id="SCORE"/></loop>
            <loop count="1"><elt size="1" type="text" id="NAME"/></loop>
          </structure>
          <output><table line-ignore="NAME">
            <column id="RANK" src="index" format="+1"/><column id="SCORE"/><column id="NAME"/>
          </table></output>"""
        self.assertEqual(self.table(body, b"	A").rows, ((1, 9, "A"),))

    def test_seleccion_por_regiones(self):
        body = """
          <structure file=".hi"><check><definition>0:1000:2:00:00</definition><size>2</size></check>
            <elt size="2" type="int" id="SCORE"/></structure>
          <structure file=".hi"><check><definition>@:maincpu,program,2000,2,00,00</definition><size>2</size></check>
            <elt size="2" type="int" id="SCORE" endianness="little_endian"/></structure>
          <output><table><column id="SCORE"/></table></output>"""
        definition = parse_definition("demo", xml(body))
        data = bytes([0x01, 0x00])
        self.assertEqual(decode(definition, data).tables[0].rows, ((256,),))
        result = decode(definition, data, regions=((0x2000, 2, 0, 0),))
        self.assertEqual((result.structure_index, result.tables[0].rows), (1, ((1,),)))
        with self.assertRaisesRegex(FormatError, "regiones"):
            decode(definition, data, regions=((0x3000, 2, 0, 0),))


if __name__ == "__main__":
    unittest.main()
