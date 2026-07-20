"""
Aba 3 — Parâmetros do sistema: tabela de equivalências de itens.

Tabela editável (criar/editar/excluir) com as colunas 'item' e 'item_normalizado',
salva dentro do sistema (%APPDATA%/FaturasEnergia/). Preenche a coluna
`item_normalizado` da aba `itens_fatura`: se o item existir aqui, usa o valor
normalizado; senão, mantém o próprio item.
"""
from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from ..core import equivalencias


class AbaParametros(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.linhas: list[tuple] = []   # (frame, entry_item, entry_norm)

        # rodapé fixo (ações)
        rod = ctk.CTkFrame(self, fg_color="transparent")
        rod.pack(side="bottom", fill="x", pady=(8, 2))
        rod.grid_columnconfigure(0, weight=1)
        self.lbl_status = ctk.CTkLabel(rod, text="", anchor="w",
                                       text_color=("gray35", "gray70"))
        self.lbl_status.grid(row=0, column=0, sticky="w")
        ctk.CTkButton(rod, text="➕  Adicionar equivalência", command=self._add_linha).grid(
            row=0, column=1, padx=(0, 8))
        ctk.CTkButton(rod, text="💾  Salvar tabela", height=36, command=self._salvar).grid(
            row=0, column=2)

        # cabeçalho / explicação
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(side="top", fill="x")
        ctk.CTkLabel(top, text="Tabela de equivalências de itens",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", pady=(2, 2))
        ctk.CTkLabel(top, justify="left", text_color=("gray40", "gray65"), wraplength=760,
                     text=("Na aba 'itens_fatura', a coluna 'item_normalizado' recebe o valor "
                           "abaixo quando o 'item' estiver listado aqui; caso contrário, fica "
                           "igual ao próprio 'item'. A tabela fica salva no aplicativo.")).pack(
            anchor="w")

        # grade rolável
        self.lista = ctk.CTkScrollableFrame(self, fg_color=("gray96", "gray14"))
        self.lista.pack(side="top", fill="both", expand=True, pady=(8, 0))
        self.lista.grid_columnconfigure(0, weight=1)
        self.lista.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.lista, text="item", font=ctk.CTkFont(size=11, weight="bold"),
                     anchor="w").grid(row=0, column=0, sticky="w", padx=6, pady=(2, 4))
        ctk.CTkLabel(self.lista, text="item_normalizado", font=ctk.CTkFont(size=11, weight="bold"),
                     anchor="w").grid(row=0, column=1, sticky="w", padx=6, pady=(2, 4))

        self._carregar()

    def _carregar(self):
        for l in equivalencias.carregar():
            self._add_linha(l.get("item", ""), l.get("item_normalizado", ""))
        if not self.linhas:
            self._add_linha()

    def _add_linha(self, item="", norm=""):
        i = len(self.linhas) + 1
        frame = ctk.CTkFrame(self.lista, fg_color="transparent")
        frame.grid(row=i, column=0, columnspan=3, sticky="ew", pady=2)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        e_item = ctk.CTkEntry(frame)
        e_item.insert(0, item or "")
        e_item.grid(row=0, column=0, sticky="ew", padx=(4, 4))
        e_norm = ctk.CTkEntry(frame)
        e_norm.insert(0, norm or "")
        e_norm.grid(row=0, column=1, sticky="ew", padx=(4, 4))
        reg = (frame, e_item, e_norm)
        ctk.CTkButton(frame, text="✕", width=30, fg_color="transparent", border_width=1,
                      text_color=("gray30", "gray80"),
                      command=lambda: self._remover(reg)).grid(row=0, column=2, padx=(0, 4))
        self.linhas.append(reg)

    def _remover(self, reg):
        frame, _, _ = reg
        frame.destroy()
        if reg in self.linhas:
            self.linhas.remove(reg)

    def _salvar(self):
        dados = []
        for _frame, e_item, e_norm in self.linhas:
            item = e_item.get().strip()
            if not item:
                continue
            dados.append({"item": item, "item_normalizado": e_norm.get().strip()})
        try:
            equivalencias.salvar(dados)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Não foi possível salvar as equivalências:\n{e}")
            return
        self.lbl_status.configure(text=f"✅ {len(dados)} equivalência(s) salva(s).")
