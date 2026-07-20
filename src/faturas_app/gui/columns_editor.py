"""
Editor de colunas e abas: o usuário escolhe quais abas e colunas mantém e pode
renomear as colunas. Opera sobre um objeto Perfil (camada de exibição).
"""
from __future__ import annotations

import customtkinter as ctk

from ..core.profile import Perfil


class EditorColunas(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.tabview: ctk.CTkTabview | None = None
        self._perfil: Perfil | None = None
        # widgets por aba: {aba: {"incluir": var, "colunas": [(coluna_perfil, var_inc, entry)]}}
        # (NÃO usar o nome `_w`: é reservado pelo Tkinter para o caminho da janela.)
        self._widgets: dict[str, dict] = {}

    def carregar(self, perfil: Perfil):
        """(Re)constrói o editor a partir de um perfil."""
        self._perfil = perfil
        self._widgets = {}
        if self.tabview is not None:
            self.tabview.destroy()
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=0, sticky="nsew")

        for aba in perfil.abas:
            n_cols = len(aba.colunas)
            titulo = f"{aba.nome} ({n_cols})"
            self.tabview.add(titulo)
            frame = self.tabview.tab(titulo)
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(1, weight=1)

            topo = ctk.CTkFrame(frame, fg_color="transparent")
            topo.grid(row=0, column=0, sticky="ew", pady=(2, 6))
            var_aba = ctk.BooleanVar(value=aba.incluida)
            ctk.CTkCheckBox(topo, text="Incluir esta aba na planilha",
                            variable=var_aba,
                            font=ctk.CTkFont(weight="bold")).pack(side="left")
            ctk.CTkLabel(topo, text="Renomeie as colunas no campo de texto · "
                                    "desmarque para remover",
                         text_color=("gray45", "gray60")).pack(side="right")

            scroll = ctk.CTkScrollableFrame(frame, fg_color=("gray96", "gray14"))
            scroll.grid(row=1, column=0, sticky="nsew")
            scroll.grid_columnconfigure(1, weight=1)

            # cabeçalho da grade
            ctk.CTkLabel(scroll, text="Incluir", width=60,
                         font=ctk.CTkFont(size=11, weight="bold")).grid(
                row=0, column=0, padx=(6, 4), pady=(2, 4))
            ctk.CTkLabel(scroll, text="Nome exibido (editável)",
                         font=ctk.CTkFont(size=11, weight="bold"), anchor="w").grid(
                row=0, column=1, sticky="w", pady=(2, 4))
            ctk.CTkLabel(scroll, text="Campo original",
                         font=ctk.CTkFont(size=11, weight="bold"), anchor="w").grid(
                row=0, column=2, sticky="w", padx=(8, 6), pady=(2, 4))

            linhas = []
            for i, col in enumerate(aba.colunas, start=1):
                var_inc = ctk.BooleanVar(value=col.incluida)
                ctk.CTkCheckBox(scroll, text="", width=40, variable=var_inc).grid(
                    row=i, column=0, padx=(14, 4), pady=2)
                entry = ctk.CTkEntry(scroll)
                entry.insert(0, col.exibido)
                entry.grid(row=i, column=1, sticky="ew", pady=2)
                ctk.CTkLabel(scroll, text=col.canonico or "(extra)",
                             text_color=("gray50", "gray55"), anchor="w").grid(
                    row=i, column=2, sticky="w", padx=(8, 6))
                linhas.append((col, var_inc, entry))

            self._widgets[aba.nome] = {"incluir": var_aba, "colunas": linhas}

    def coletar(self) -> Perfil:
        """Lê os widgets de volta para o perfil e o devolve."""
        if self._perfil is None:
            raise RuntimeError("Editor sem perfil carregado.")
        for aba in self._perfil.abas:
            w = self._widgets.get(aba.nome)
            if not w:
                continue
            aba.incluida = bool(w["incluir"].get())
            for col, var_inc, entry in w["colunas"]:
                col.incluida = bool(var_inc.get())
                novo = entry.get().strip()
                col.exibido = novo if novo else (col.canonico or col.exibido)
        return self._perfil

    def tem_perfil(self) -> bool:
        return self._perfil is not None
