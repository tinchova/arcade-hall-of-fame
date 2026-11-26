"""Dirección de la página web en la red local, y su código QR.

La IP de la Mac cambia según la red (por ejemplo, si la máquina se lleva a otra
casa). Por eso se ofrecen dos direcciones:

* la IP actual en la red local, detectada al arrancar (``http://192.168.1.10:47474/``),
  que es la que va en el QR porque funciona en cualquier celular;
* el nombre Bonjour de la Mac (``http://<nombre>.local:47474/``), que no depende de
  la IP. En macOS sale de ``scutil --get LocalHostName`` (Preferencias del
  Sistema → Compartir → nombre del equipo). iPhone lo resuelve siempre; en
  Android depende de la versión y del navegador.

El QR se genera con ``vendor/qrcodegen.py`` (Project Nayuki, MIT), sin
dependencias externas.
"""

from __future__ import annotations

import socket
import subprocess
import sys
from typing import List, Optional

from .vendor.qrcodegen import QrCode


def local_ip() -> Optional[str]:
    """IPv4 privada de este equipo en la red local, o None si no hay red."""
    import ipaddress

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.168.255.255", 1))  # UDP sin enviar nada: solo elige la interfaz de salida
            address = s.getsockname()[0]
    except OSError:
        return None
    ip = ipaddress.ip_address(address)
    return address if ip.is_private and not ip.is_loopback and not ip.is_unspecified else None


def bonjour_name() -> Optional[str]:
    """Nombre ``.local`` del equipo (Bonjour/mDNS), o None si no se conoce."""
    if sys.platform == "darwin":
        try:
            name = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True,
                                  timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            name = ""
        return f"{name}.local" if name else None
    if sys.platform.startswith("linux"):
        name = socket.gethostname().split(".")[0]
        return f"{name}.local" if name and name != "localhost" else None
    return None


def page_urls(port: int) -> List[str]:
    """Direcciones para abrir la página: primero la IP actual (va en el QR) y después la ``.local``."""
    urls = []
    ip = local_ip()
    if ip:
        urls.append(f"http://{ip}:{port}/")
    name = bonjour_name()
    if name:
        urls.append(f"http://{name}:{port}/")
    return urls


def qr_matrix(text: str) -> List[List[bool]]:
    """Módulos del QR (True = oscuro), sin el margen blanco."""
    code = QrCode.encode_text(text, QrCode.Ecc.MEDIUM)
    return [[code.get_module(x, y) for x in range(code.get_size())] for y in range(code.get_size())]


def qr_svg(text: str, border: int = 4) -> str:
    """SVG en línea (blanco y negro, con margen) para mostrar en la página."""
    matrix = qr_matrix(text)
    size = len(matrix) + 2 * border
    path = "".join(f"M{x + border},{y + border}h1v1h-1z" for y, row in enumerate(matrix)
                   for x, dark in enumerate(row) if dark)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" shape-rendering="crispEdges" '
            f'role="img" aria-label="Código QR"><rect width="{size}" height="{size}" fill="#fff"/>'
            f'<path d="{path}" fill="#000"/></svg>')
