"""
Copia o NÚCLEO do app (src/faturas_app) para docs/py/, que é o que a versão web
(GitHub Pages) carrega dentro do Pyodide.

O GitHub Pages serve arquivos estáticos, então o código Python precisa estar
publicado como arquivo. Este script mantém docs/py/ em dia com src/ — rode-o
sempre que mexer no núcleo, senão a versão web fica atrasada em relação ao app
desktop.

    python build/sync_web.py
"""
from __future__ import annotations

import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORIGEM = RAIZ / "src" / "faturas_app"
DESTINO = RAIZ / "docs" / "py" / "faturas_app"

# A GUI não vai para a web (Tkinter não roda no navegador) e `borderos.py`
# depende do PyMuPDF, que não tem build WebAssembly.
IGNORAR = shutil.ignore_patterns("__pycache__", "*.pyc", "gui", "borderos.py")


def main() -> int:
    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ORIGEM, DESTINO, ignore=IGNORAR)

    arquivos = sorted(p.relative_to(DESTINO).as_posix()
                      for p in DESTINO.rglob("*") if p.is_file())
    (DESTINO.parent / "manifesto.json").write_text(
        __import__("json").dumps(arquivos, indent=1), encoding="utf-8")
    print(f"{len(arquivos)} arquivo(s) -> {DESTINO}")
    print(f"manifesto: {DESTINO.parent / 'manifesto.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
