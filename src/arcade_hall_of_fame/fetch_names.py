"""Descarga los DAT de FinalBurn Neo (nombres de los juegos) a una carpeta local.

Los DAT son de FinalBurn Neo (https://github.com/libretro/FBNeo); este proyecto
no los redistribuye. Se descargan en una revisión fija, se verifican con
SHA-256 y quedan en ``local/`` (excluido de Git)::

    python -m arcade_hall_of_fame.fetch_names
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPOSITORY_RAW = "https://raw.githubusercontent.com/libretro/FBNeo"
REVISION = "d25b21e733fd4ee07980a65268abb5706fc3549d"  # FBNeo 1.0.0.03
FILES = {
    "FinalBurn Neo (ClrMame Pro XML, Arcade only).dat":
        "30c362e4c37636b2cfbd6dc0c79db87eec0896eb474262c065cde050de9c1037",
    "FinalBurn Neo (ClrMame Pro XML, Neogeo only).dat":
        "4d9e8a8524f95005e25f4348e0c3e817a313a1ac1cdf4438ac8f57000513d95b",
}
MAX_SIZE = 64 * 1024 * 1024
DEFAULT_DIR = Path("local") / "fbneo-dats" / REVISION


def url_for(name: str) -> str:
    return f"{REPOSITORY_RAW}/{REVISION}/dats/{urllib.parse.quote(name)}"


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "arcade-hall-of-fame"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read(MAX_SIZE + 1)
    if len(data) > MAX_SIZE:
        raise RuntimeError("archivo demasiado grande")
    return data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Descarga los DAT de FinalBurn Neo.")
    parser.add_argument("--destino", default=str(DEFAULT_DIR))
    parser.add_argument("--desde", help="carpeta con los .dat ya descargados (no descarga)")
    args = parser.parse_args(argv)
    destination = Path(args.destino)
    destination.mkdir(parents=True, exist_ok=True)
    for name, expected in FILES.items():
        data = (Path(args.desde) / name).read_bytes() if args.desde else download(url_for(name))
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected:
            print(f"{name}: SHA-256 distinto al esperado ({digest}); no se guardó.", file=sys.stderr)
            return 1
        (destination / name).write_bytes(data)
        print(f"{name}: {len(data)} bytes")
    print(f"DAT de FBNeo en {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
