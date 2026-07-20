"""
Data/hora da última atualização do app.

O carimbo é gravado em `resources/build_info.txt` pelo script de build
(build.ps1) a cada empacotamento. `data_atualizacao()` lê esse arquivo tanto em
desenvolvimento quanto no app empacotado (PyInstaller).
"""
from __future__ import annotations

import sys
from pathlib import Path


def _res_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base / "faturas_app" / "resources"
    return Path(__file__).resolve().parent.parent / "resources"


def data_atualizacao() -> str | None:
    """Devolve a data/hora da última atualização (string) ou None se ausente."""
    try:
        # utf-8-sig remove o BOM que o PowerShell adiciona ao gravar o arquivo.
        txt = (_res_dir() / "build_info.txt").read_text(encoding="utf-8-sig").strip()
        return txt or None
    except Exception:
        return None
