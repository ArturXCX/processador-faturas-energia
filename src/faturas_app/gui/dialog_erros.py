"""
Tela que lista os PDFs que NÃO entraram na planilha: falharam na extração ou
tiveram a fatura descartada por não ter itens legíveis (ex.: digitalização
ruim). Aberta a partir do botão "Ver arquivos ignorados" na aba Processar.
"""
from __future__ import annotations

import customtkinter as ctk

from ..core.controller import ErroProcessamento


class DialogoErros(ctk.CTkToplevel):
    def __init__(self, master, erros: list[ErroProcessamento]):
        super().__init__(master)
        self.title("Arquivos ignorados na extração")
        self.geometry("720x480")
        self.minsize(520, 320)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        ctk.CTkLabel(cab, text=f"{len(erros)} arquivo(s) não entraram na planilha",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(cab, justify="left", text_color=("gray40", "gray65"),
                     text=("Esses PDFs tiveram erro na extração ou foram descartados por "
                           "não terem itens legíveis (ex.: digitalização ruim/ilegível)."),
                     wraplength=680, anchor="w").pack(anchor="w", pady=(2, 0))

        scroll = ctk.CTkScrollableFrame(self, fg_color=("gray96", "gray14"))
        scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        scroll.grid_columnconfigure(0, weight=1)

        if not erros:
            ctk.CTkLabel(scroll, text="Nenhum arquivo com erro.",
                         text_color=("gray50", "gray55")).grid(row=0, column=0, pady=30)

        for i, e in enumerate(erros):
            linha = ctk.CTkFrame(scroll, fg_color=("gray92", "gray20"), corner_radius=8)
            linha.grid(row=i, column=0, sticky="ew", pady=4, padx=2)
            linha.grid_columnconfigure(0, weight=1)

            topo = ctk.CTkFrame(linha, fg_color="transparent")
            topo.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
            topo.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(topo, text=e.arquivo, font=ctk.CTkFont(size=13, weight="bold"),
                         anchor="w").grid(row=0, column=0, sticky="ew")
            ctk.CTkLabel(topo, text=e.fornecedor, text_color=("gray40", "gray60")).grid(
                row=0, column=1, sticky="e", padx=(8, 0))

            ctk.CTkLabel(linha, text=e.mensagem, text_color=("gray35", "gray70"),
                         anchor="w", justify="left", wraplength=640,
                         font=ctk.CTkFont(size=11)).grid(
                row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(2, 8))

        rod = ctk.CTkFrame(self, fg_color="transparent")
        rod.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 14))
        rod.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(rod, text="Fechar", width=120, command=self._fechar).grid(
            row=0, column=1)

        self.transient(master)
        self.after(50, self._focar)

    def _focar(self):
        self.grab_set()
        self.focus_force()

    def _fechar(self):
        self.grab_release()
        self.destroy()
