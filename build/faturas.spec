# -*- mode: python ; coding: utf-8 -*-
"""
Spec do PyInstaller para o Processador de Faturas de Energia.

Empacota (modo one-folder):
  - o pacote `faturas_app` (núcleo + interface CustomTkinter);
  - os dados do CustomTkinter (temas/fontes);
  - a pasta portátil `tesseract/` (motor de OCR + DLLs + tessdata),
    copiada para `_internal/tesseract/` — exatamente onde `core/ocr.py`
    procura quando o app está "congelado".

Gera `dist/FaturasDeEnergia/` (a pasta a ser compactada e distribuída).
"""
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "src")
TESS = os.path.join(ROOT, "tesseract")

# ── dados ────────────────────────────────────────────────────────────────────
datas = []
datas += collect_data_files("customtkinter")

# ícone da janela (também usado pelo EXE) -> _internal/app.ico
_ico = os.path.join(ROOT, "build", "app.ico")
if os.path.exists(_ico):
    datas.append((_ico, "."))

# recursos de dados do app (glossário de itens, correções pontuais de extração,
# carimbo de atualização)
_resdir = os.path.join("faturas_app", "resources")
for _r in ("glossario_itens.json", "correcoes.json", "build_info.txt"):
    _p = os.path.join(SRC, "faturas_app", "resources", _r)
    if os.path.exists(_p):
        datas.append((_p, _resdir))

# pasta tesseract portátil -> preserva a subestrutura (tesseract/, tesseract/tessdata/)
if os.path.isdir(TESS):
    for dirpath, _dirs, files in os.walk(TESS):
        rel = os.path.relpath(dirpath, ROOT)   # "tesseract" ou "tesseract\tessdata"
        for f in files:
            datas.append((os.path.join(dirpath, f), rel))
else:
    raise SystemExit(
        "Pasta 'tesseract/' não encontrada. Rode build\\fetch_tesseract.ps1 antes do build."
    )

# ── imports ocultos ──────────────────────────────────────────────────────────
hiddenimports = []
hiddenimports += collect_submodules("customtkinter")
hiddenimports += ["PIL._tkinter_finder"]

block_cipher = None

a = Analysis(
    [os.path.join(SRC, "faturas_app", "__main__.py")],
    pathex=[SRC],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter.test", "test", "pytest", "matplotlib", "scipy"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FaturasDeEnergia",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,            # app de janela (sem console)
    disable_windowed_traceback=False,
    icon=os.path.join(ROOT, "build", "app.ico") if os.path.exists(
        os.path.join(ROOT, "build", "app.ico")) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FaturasDeEnergia",
)
