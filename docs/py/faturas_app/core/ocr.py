"""
Localização do motor de OCR (Tesseract).

Estratégia de busca, nesta ordem:
  1. Variável de ambiente FATURAS_TESSERACT (override manual).
  2. Tesseract embutido no pacote (PyInstaller copia para <base>/tesseract/).
  3. Caminhos usuais de instalação no Windows.
  4. 'tesseract' no PATH do sistema.

Quando embutido, o idioma português (por.traineddata) vai em
<base>/tesseract/tessdata/ e apontamos TESSDATA_PREFIX para lá.
"""
from __future__ import annotations

import os
import sys
import shutil
from pathlib import Path
from functools import lru_cache


def _base_dir() -> Path:
    """Raiz dos recursos (difere entre 'rodando do .py' e '.exe do PyInstaller')."""
    if getattr(sys, "frozen", False):
        # Empacotado: recursos ficam em sys._MEIPASS (onefile) ou ao lado do exe.
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    # Em desenvolvimento, procura uma pasta 'tesseract' staged ao lado do projeto.
    return Path(__file__).resolve().parents[3]


def _candidatos_exe() -> list[Path]:
    base = _base_dir()
    cands: list[Path] = []
    env = os.environ.get("FATURAS_TESSERACT")
    if env:
        cands.append(Path(env))
    # Embutido no pacote.
    cands.append(base / "tesseract" / "tesseract.exe")
    cands.append(base / "tesseract" / "tesseract")
    # Instalações comuns no Windows.
    cands.append(Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"))
    cands.append(Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"))
    return cands


@lru_cache(maxsize=1)
def localizar_tesseract() -> str | None:
    """Devolve o caminho do executável do Tesseract, ou None se indisponível."""
    for c in _candidatos_exe():
        try:
            if c.is_file():
                return str(c)
        except OSError:
            continue
    # Por último, PATH do sistema.
    found = shutil.which("tesseract")
    return found


@lru_cache(maxsize=1)
def configurar_ocr() -> bool:
    """
    Configura pytesseract para usar o Tesseract localizado. Define também
    TESSDATA_PREFIX se houver tessdata embutido. Devolve True se OCR está pronto.
    """
    exe = localizar_tesseract()
    if not exe:
        return False
    try:
        import pytesseract
    except Exception:
        return False
    pytesseract.pytesseract.tesseract_cmd = exe

    # tessdata: ao lado do executável ou no _base_dir/tesseract/tessdata.
    exe_path = Path(exe)
    for td in (exe_path.parent / "tessdata",
               _base_dir() / "tesseract" / "tessdata"):
        if td.is_dir():
            os.environ["TESSDATA_PREFIX"] = str(td)
            break
    return True


def ocr_disponivel() -> bool:
    return configurar_ocr()
