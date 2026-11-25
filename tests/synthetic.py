"""Definiciones y bytes sintéticos para las pruebas.

Todo lo de este archivo se escribió para estas pruebas a partir de la
referencia pública del formato. No son definiciones de hi2txt-xml ni volcados
de partidas reales; los juegos "demo*" no existen.
"""

from __future__ import annotations


def xml(body: str) -> bytes:
    return f'<?xml version="1.0" encoding="utf-8"?>\n<hi2txt>{body}</hi2txt>'.encode("utf-8")


# Tres puntuaciones BCD de 3 bytes (menor peso primero, 0x24 = blanco),
# tres nombres de 2 códigos (letras desde 0x0A, 0x24 = espacio, 0x2A = punto)
# y un máximo separado.
DEMO_BCD = xml("""
  <structure file=".hi">
    <check><size>18</size></check>
    <loop count="3"><elt size="3" type="int" id="SCORE" decoding-profile="bcd-le" byte-trim="0x24"/></loop>
    <loop count="3"><elt size="2" type="text" id="NAME" charset="demo" ascii-offset="55"/></loop>
    <elt size="3" type="int" id="TOP SCORE" decoding-profile="bcd-le" byte-trim="0x24"/>
  </structure>
  <output>
    <table>
      <column id="RANK" src="index" format="+1"/>
      <column id="SCORE"/>
      <column id="NAME"/>
    </table>
    <field id="TOP SCORE" display="extra"/>
  </output>
  <charset id="demo">
    <char src="0x24" dst=" "/>
    <char src="0x2A" dst="."/>
  </charset>
""")

DEMO_BCD_BYTES = bytes([
    0x05, 0x04, 0x03,  # 345
    0x00, 0x02, 0x24,  # 20
    0x07, 0x24, 0x24,  # 7
    0x0A, 0x2A,        # "A."
    0x24, 0x23,        # " Z"
    0x16, 0x0C,        # "MC"
    0x05, 0x04, 0x03,  # máximo 345
])

# Filas de 5 bytes: puntuación de 3 bytes en base 16 little endian (se muestra
# por diez), etapa (se muestra más uno) y una letra ASCII.
DEMO_ROWS = xml("""
  <structure file=".hi">
    <check><size>15</size></check>
    <loop count="3">
      <elt size="3" type="int" id="SCORE" endianness="little_endian" base="16"/>
      <elt size="1" type="int" id="STAGE"/>
      <elt size="1" type="text" id="NAME"/>
    </loop>
  </structure>
  <output>
    <table id="TOP">
      <column id="RANK" src="index" format="+1"/>
      <column id="SCORE" format="*10"/>
      <column id="NAME"/>
      <column id="STAGE" format="+1"/>
    </table>
  </output>
""")

DEMO_ROWS_BYTES = bytes([
    0x08, 0x40, 0x00, 0x04, 0x41,  # 4008 -> 40080, etapa 5, "A"
    0x00, 0x30, 0x00, 0x1F, 0x42,  # 3000 -> 30000, etapa 32, "B"
    0x50, 0x12, 0x00, 0x00, 0x2E,  # 1250 -> 12500, etapa 1, "."
])
