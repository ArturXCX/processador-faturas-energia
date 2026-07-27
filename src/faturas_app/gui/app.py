"""Janela principal do aplicativo."""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from .. import APP_NAME, __version__
from ..core import ocr, build_info
from .tab_processar import AbaProcessar
from .tab_concatenar import AbaConcatenar
from .tab_parametros import AbaParametros
from .tab_hardcodes import AbaHardcodes
from .tab_borderos import AbaBorderos


def _caminho_icone() -> str | None:
    """Localiza o app.ico (empacotado em _internal/ ou em build/ no dev)."""
    if getattr(sys, "frozen", False):
        cand = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "app.ico"
    else:
        cand = Path(__file__).resolve().parents[3] / "build" / "app.ico"
    return str(cand) if cand.exists() else None


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  v{__version__}")
        self.geometry("1040x760")
        self.minsize(900, 640)

        ico = _caminho_icone()
        if ico:
            try:
                self.iconbitmap(ico)
            except Exception:
                pass

        # Falhas em callbacks do Tk não devem sumir em silêncio (app sem console).
        self.report_callback_exception = self._erro_inesperado

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._cabecalho()
        self._seletor_conjunto()
        self._conjuntos()

    def _seletor_conjunto(self):
        seletor = ctk.CTkSegmentedButton(
            self, values=["Faturas de energia", "Borderôs"],
            command=self._trocar_conjunto)
        seletor.set("Faturas de energia")
        seletor.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))

    def _conjuntos(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 12))
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        self._tab_energia = ctk.CTkTabview(container)
        self._tab_energia.grid(row=0, column=0, sticky="nsew")
        self._tab_energia.add("Processar faturas")
        self._tab_energia.add("Adicionar a uma planilha")
        self._tab_energia.add("Parâmetros")
        self._tab_energia.add("Hardcodes")

        self._tab_borderos = ctk.CTkTabview(container)
        self._tab_borderos.grid(row=0, column=0, sticky="nsew")
        self._tab_borderos.add("Borderôs de energia")

        proc = AbaProcessar(self._tab_energia.tab("Processar faturas"))
        proc.pack(fill="both", expand=True, padx=4, pady=4)
        conc = AbaConcatenar(self._tab_energia.tab("Adicionar a uma planilha"))
        conc.pack(fill="both", expand=True, padx=4, pady=4)
        param = AbaParametros(self._tab_energia.tab("Parâmetros"))
        param.pack(fill="both", expand=True, padx=4, pady=4)
        hard = AbaHardcodes(self._tab_energia.tab("Hardcodes"))
        hard.pack(fill="both", expand=True, padx=4, pady=4)
        bord = AbaBorderos(self._tab_borderos.tab("Borderôs de energia"))
        bord.pack(fill="both", expand=True, padx=4, pady=4)

        self._tab_energia.tkraise()

    def _trocar_conjunto(self, valor: str):
        if valor == "Borderôs":
            self._tab_borderos.tkraise()
        else:
            self._tab_energia.tkraise()

    def _erro_inesperado(self, exc, val, tb):
        detalhe = "".join(traceback.format_exception(exc, val, tb))
        caminho_log = os.path.join(os.path.expanduser("~"), "faturas_erro.log")
        try:
            with open(caminho_log, "a", encoding="utf-8") as f:
                f.write(detalhe + "\n" + ("-" * 60) + "\n")
        except Exception:
            caminho_log = "(não foi possível gravar o log)"
        try:
            messagebox.showerror(
                "Ocorreu um erro",
                f"{val}\n\nUm registro técnico foi salvo em:\n{caminho_log}")
        except Exception:
            pass

    def _cabecalho(self):
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        topo.grid_columnconfigure(0, weight=1)

        titulos = ctk.CTkFrame(topo, fg_color="transparent")
        titulos.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(titulos, text=APP_NAME,
                     font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(titulos, text="Faturas (Equatorial · CHESP) e Borderôs  —  PDFs → planilha Excel",
                     text_color=("gray40", "gray65")).pack(anchor="w")
        atualizado = build_info.data_atualizacao()
        if atualizado:
            ctk.CTkLabel(titulos, text=f"Versão {__version__} · atualizado em {atualizado}",
                         text_color=("gray50", "gray55"),
                         font=ctk.CTkFont(size=11)).pack(anchor="w")

        direita = ctk.CTkFrame(topo, fg_color="transparent")
        direita.grid(row=0, column=1, sticky="e")

        # Indicador de OCR (faturas CHESP escaneadas).
        ok_ocr = ocr.ocr_disponivel()
        cor = ("#1a7f37", "#3fb950") if ok_ocr else ("#9a6700", "#d29922")
        txt = "OCR pronto" if ok_ocr else "OCR indisponível"
        ctk.CTkLabel(direita, text=f"● {txt}", text_color=cor,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(direita, text="Tema:").pack(side="left")
        self.var_tema = ctk.StringVar(value="System")
        ctk.CTkOptionMenu(direita, width=110, variable=self.var_tema,
                          values=["System", "Light", "Dark"],
                          command=ctk.set_appearance_mode).pack(side="left", padx=(6, 0))


def main():
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
