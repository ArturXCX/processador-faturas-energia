"""Ponto de entrada: `python -m faturas_app`.

Modos:
  - sem argumentos: abre a interface;
  - `--cli …`: processa pastas de PDFs sem interface (ver faturas_app/cli.py);
  - env FATURAS_SELFCHECK=<arquivo>: autoverificação do executável empacotado —
    não abre janela, escreve um relatório de diagnóstico no arquivo e encerra.
"""
import os
import sys


def _selfcheck(destino: str) -> int:
    linhas = []
    rc = 0

    def reg(nome, ok, extra=""):
        nonlocal rc
        linhas.append(f"{'OK ' if ok else 'ERRO'} {nome} {extra}".rstrip())
        if not ok:
            rc = 1

    reg("frozen", getattr(sys, "frozen", False), str(getattr(sys, "_MEIPASS", "")))
    try:
        import customtkinter  # noqa: F401
        reg("customtkinter", True)
    except Exception as e:  # noqa: BLE001
        reg("customtkinter", False, repr(e))
    for mod in ("pdfplumber", "fitz", "pytesseract", "openpyxl", "pandas", "PIL"):
        try:
            __import__(mod)
            reg(mod, True)
        except Exception as e:  # noqa: BLE001
            reg(mod, False, repr(e))
    try:
        from faturas_app.core import ocr
        exe = ocr.localizar_tesseract()
        ok = ocr.ocr_disponivel()
        reg("ocr.tesseract", bool(exe), str(exe))
        reg("ocr.disponivel", ok, os.environ.get("TESSDATA_PREFIX", ""))
    except Exception as e:  # noqa: BLE001
        reg("ocr", False, repr(e))
    try:
        from faturas_app.core import glossario
        n = len(glossario.construir_glossario_df())
        reg("glossario", n > 50, f"{n} termos")
    except Exception as e:  # noqa: BLE001
        reg("glossario", False, repr(e))
    try:
        from faturas_app.core.agua import extrator, glossario_agua  # noqa: F401
        n = len(glossario_agua.construir_glossario_df())
        reg("agua", n > 30, f"{n} termos")
    except Exception as e:  # noqa: BLE001
        reg("agua", False, repr(e))

    with open(destino, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + f"\n\nRESULTADO: {'OK' if rc == 0 else 'FALHA'}\n")
    return rc


def main():
    # Obrigatório no exe empacotado: o modo CLI usa um pool de processos, e no
    # Windows cada processo filho reexecuta este mesmo exe.
    import multiprocessing
    multiprocessing.freeze_support()

    destino = os.environ.get("FATURAS_SELFCHECK")
    if destino:
        sys.exit(_selfcheck(destino))
    argv = sys.argv[1:]
    if argv and argv[0] in ("--cli", "cli"):
        from faturas_app.cli import main as cli_main
        sys.exit(cli_main(argv[1:]))
    from faturas_app.gui.app import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
