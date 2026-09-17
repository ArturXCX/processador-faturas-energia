"""Janela principal do aplicativo."""
from __future__ import annotations

import os
import queue
import sys
import threading
import traceback
import webbrowser
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from .. import APP_NAME, __version__
from ..core import ocr, build_info, atualizacao
from .tab_processar import AbaProcessar
from .tab_concatenar import AbaConcatenar
from .tab_parametros import AbaParametros
from .tab_hardcodes import AbaHardcodes
from .tab_borderos import AbaBorderos
from .tab_borderos_concatenar import AbaBorderosConcatenar
from .tab_agua import AbaAgua, AbaAguaConcatenar


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
        self.grid_rowconfigure(1, weight=1)

        self._cabecalho()
        self._nivel_dominio()
        self._janela_atualizacao = None
        self.after(400, self._verificar_atualizacao)

    def _nivel_dominio(self):
        """
        Nível de abas mais alto: "Energia Elétrica" (faturas + borderôs) e "Água"
        (todas as concessionárias no mesmo modelo de planilha).
        """
        tabs = ctk.CTkTabview(self)
        tabs.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        tabs.add("Energia Elétrica")
        tabs.add("Água")
        aba = tabs.tab("Energia Elétrica")
        aba.grid_columnconfigure(0, weight=1)
        aba.grid_rowconfigure(1, weight=1)

        self._seletor_conjunto(aba)
        self._conjuntos(aba)
        self._dominio_agua(tabs.tab("Água"))

    def _dominio_agua(self, master):
        master.grid_columnconfigure(0, weight=1)
        master.grid_rowconfigure(0, weight=1)
        self._tab_agua = ctk.CTkTabview(master)
        self._tab_agua.grid(row=0, column=0, sticky="nsew")
        self._tab_agua.add("Processar faturas de água")
        self._tab_agua.add("Adicionar a uma planilha")
        AbaAgua(self._tab_agua.tab("Processar faturas de água")).pack(fill="both", expand=True, padx=4, pady=4)
        AbaAguaConcatenar(self._tab_agua.tab("Adicionar a uma planilha")).pack(fill="both", expand=True, padx=4, pady=4)

    # ── atualização obrigatória (GitHub Releases) ─────────────────────────
    def _verificar_atualizacao(self):
        """Consulta a última release em segundo plano; online e desatualizado → aviso bloqueante. Offline → segue."""
        fila: queue.Queue = queue.Queue()

        def worker():
            try:
                fila.put(atualizacao.verificar())
            except Exception:  # noqa: BLE001 — nunca derruba o app
                fila.put(None)

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            try:
                rel = fila.get_nowait()
            except queue.Empty:
                self.after(300, poll)
                return
            if rel:
                self._exigir_atualizacao(rel)

        self.after(300, poll)

    def _exigir_atualizacao(self, rel: dict):
        top = ctk.CTkToplevel(self)
        top.title("Atualização obrigatória")
        top.geometry("560x330")
        top.resizable(False, False)
        top.transient(self)
        top.protocol("WM_DELETE_WINDOW", lambda: None)   # não fecha: a atualização é obrigatória
        ctk.CTkLabel(top, text="Nova versão disponível", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(22, 8))
        ctk.CTkLabel(top, justify="center", wraplength=500,
                     text=(f"Você está usando a versão {__version__}.\n"
                           f"A versão {rel.get('tag')} ({rel.get('publicada') or 'publicada no GitHub'}) já está disponível.\n\n"
                           "Para continuar usando o aplicativo é preciso baixar e instalar a nova versão.\n"
                           "Sem internet o aplicativo continua funcionando normalmente.")).pack(pady=(0, 14))
        botoes = ctk.CTkFrame(top, fg_color="transparent")
        botoes.pack(pady=6)
        alvo = rel.get("instalador") or rel.get("zip") or rel.get("url") or atualizacao.URL_RELEASES
        ctk.CTkButton(botoes, text="Baixar nova versão", height=38, width=200,
                      command=lambda: webbrowser.open(alvo)).pack(side="left", padx=6)
        ctk.CTkButton(botoes, text="Ver no GitHub", height=38, width=140, fg_color="transparent", border_width=1,
                      text_color=("gray30", "gray80"),
                      command=lambda: webbrowser.open(rel.get("url") or atualizacao.URL_RELEASES)).pack(side="left", padx=6)
        ctk.CTkButton(top, text="Sair do aplicativo", height=32, width=160, fg_color=("#9a3b3b", "#7a2e2e"),
                      command=self.destroy).pack(pady=(10, 0))
        self._janela_atualizacao = top

        def travar():
            try:
                top.grab_set()
                top.focus_force()
            except Exception:
                pass
        top.after(150, travar)

    def _seletor_conjunto(self, master):
        seletor = ctk.CTkSegmentedButton(
            master, values=["Faturas de Energia", "Borderôs de Energia"],
            command=self._trocar_conjunto)
        seletor.set("Faturas de Energia")
        seletor.grid(row=0, column=0, sticky="w", pady=(8, 8))

    def _conjuntos(self, master):
        container = ctk.CTkFrame(master, fg_color="transparent")
        container.grid(row=1, column=0, sticky="nsew")
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
        self._tab_borderos.add("Processar Borderôs")
        self._tab_borderos.add("Adicionar a uma planilha")
        self._tab_borderos.add("Hardcodes")

        proc = AbaProcessar(self._tab_energia.tab("Processar faturas"))
        proc.pack(fill="both", expand=True, padx=4, pady=4)
        conc = AbaConcatenar(self._tab_energia.tab("Adicionar a uma planilha"))
        conc.pack(fill="both", expand=True, padx=4, pady=4)
        param = AbaParametros(self._tab_energia.tab("Parâmetros"))
        param.pack(fill="both", expand=True, padx=4, pady=4)
        hard = AbaHardcodes(self._tab_energia.tab("Hardcodes"))
        hard.pack(fill="both", expand=True, padx=4, pady=4)

        bproc = AbaBorderos(self._tab_borderos.tab("Processar Borderôs"))
        bproc.pack(fill="both", expand=True, padx=4, pady=4)
        bconc = AbaBorderosConcatenar(self._tab_borderos.tab("Adicionar a uma planilha"))
        bconc.pack(fill="both", expand=True, padx=4, pady=4)
        bhard = AbaHardcodes(self._tab_borderos.tab("Hardcodes"), dominio="borderos")
        bhard.pack(fill="both", expand=True, padx=4, pady=4)

        self._tab_energia.tkraise()

    def _trocar_conjunto(self, valor: str):
        if valor == "Borderôs de Energia":
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
        ctk.CTkLabel(titulos, text="Energia (Equatorial · CHESP · borderôs) e Água (Saneago · SAAEs · DEMAEs · SAE · "
                                   "SANESC…)  —  PDFs → planilha Excel",
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
