"""Descarga las definiciones de hi2txt-xml en una carpeta local, fuera de Git.

Las definiciones son de GreatStoneEx y colaboradores (licencia GPL v2). Este
proyecto no las redistribuye: cada usuario las descarga con este comando, fijado
a una revisión concreta y verificado con SHA-256.

Uso, desde la raíz del repositorio::

    python -m arcade_hall_of_fame.hi2txt.fetch            # definiciones
    python -m arcade_hall_of_fame.hi2txt.fetch --pruebas  # además, casos de prueba

Resultado: ``local/hi2txt-xml/<revisión>/`` con ``src/main/db`` (definiciones y
``hi2txt.dtd``), ``src/main/db_defaults`` (tablas de fábrica), ``LICENSE`` y
``README.md``; con ``--pruebas``, también ``src/test``. ``/local/`` está
excluido en ``.gitignore``.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

REPOSITORY = "https://github.com/GreatStoneEx/hi2txt-xml"
REVISION = "990fca26edb8cd9e37ab0b569d5d59b06e31f0e0"
ARCHIVE_SHA256 = "a9111f53acebfa71f4de4bbede08782f77a0e8d2bf4e7ae5c2614899d528cfb0"
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_MEMBER = 8 * 1024 * 1024

BASE_PATHS = ("src/main/db/", "src/main/db_defaults/", "LICENSE", "README.md")
TEST_PATHS = ("src/test/",)


def archive_url(revision: str = REVISION) -> str:
    return f"{REPOSITORY}/archive/{revision}.zip"


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "arcade-hall-of-fame"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(MAX_ARCHIVE + 1)
    if len(data) > MAX_ARCHIVE:
        raise RuntimeError("el archivo descargado es demasiado grande")
    return data


def extract(archive: bytes, destination: Path, include_tests: bool) -> int:
    """Extrae solo las rutas admitidas, sin seguir rutas absolutas ni '..'."""
    wanted = BASE_PATHS + (TEST_PATHS if include_tests else ())
    count = 0
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = PurePosixPath(info.filename).parts
            if len(parts) < 2:
                continue
            relative = PurePosixPath(*parts[1:])  # quitar la carpeta raíz del zip
            text = relative.as_posix()
            if not any(text == w or text.startswith(w) for w in wanted):
                continue
            if relative.is_absolute() or ".." in relative.parts or info.file_size > MAX_MEMBER:
                raise RuntimeError(f"entrada no admitida en el archivo: {info.filename!r}")
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(info))
            count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Descarga las definiciones de hi2txt-xml.")
    parser.add_argument("--destino", default="local/hi2txt-xml", help="carpeta base (por defecto local/hi2txt-xml)")
    parser.add_argument("--pruebas", action="store_true", help="incluir src/test (entradas y salidas esperadas)")
    parser.add_argument("--archivo", help="usar un .zip ya descargado en vez de descargarlo")
    args = parser.parse_args(argv)

    if args.archivo:
        archive = Path(args.archivo).read_bytes()
    else:
        print(f"Descargando {archive_url()}")
        archive = download(archive_url())
    digest = hashlib.sha256(archive).hexdigest()
    if digest != ARCHIVE_SHA256:
        print(
            "El SHA-256 del archivo no coincide con el esperado.\n"
            f"  esperado: {ARCHIVE_SHA256}\n  obtenido: {digest}\n"
            "No se extrajo nada. Si GitHub regeneró el .zip de la misma revisión,"
            " revisar el contenido antes de actualizar el hash en fetch.py.",
            file=sys.stderr,
        )
        return 1
    destination = Path(args.destino) / REVISION
    if destination.exists():
        shutil.rmtree(destination)
    count = extract(archive, destination, args.pruebas)
    print(f"{count} archivos en {destination}")
    print(f"Definiciones: {destination / 'src' / 'main' / 'db'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
