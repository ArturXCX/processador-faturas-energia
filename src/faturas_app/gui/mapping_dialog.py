"""
Tela de mapeamento de colunas, usada na concatenação quando a planilha enviada
NÃO tem metadados embutidos (ex.: foi gerada fora deste app ou teve a aba de
metadados removida). O usuário confirma, para cada coluna da planilha enviada,
a qual campo canônico ela corresponde — ou se deve ser mantida como "extra".
"""
from __future__ import annotations

import customtkinter as ctk

from ..core import concat, schema

OPCAO_EXTRA = "(manter como coluna extra)"


class DialogoMapeamento(ctk.CTkToplevel):
    def __init__(self, master, uploaded_dfs, sugestoes):
        super().__init__(master)
        self.title("Mapear colunas da planilha enviada")
        self.geometry("760x620")
        self.resultado: dict | None = None
        self._uploaded = uploaded_dfs
        self._combos: dict[str, dict] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        ctk.CTkLabel(cab, text="Confirme a correspondência das colunas",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(cab, justify="left", text_color=("gray40", "gray65"),
                     text=("Sua planilha não traz os metadados deste app. Confirme abaixo "
                           "a qual campo cada coluna corresponde para que as novas faturas "
                           "sejam encaixadas corretamente. As sugestões já vêm preenchidas."),
                     wraplength=700, anchor="w").pack(anchor="w", pady=(2, 0))

        tabs = ctk.CTkTabview(self)
        tabs.grid(row=1, column=0, sticky="nsew", padx=16, pady=8)

        for aba, df in uploaded_dfs.items():
            if df is None or df.empty:
                continue
            canon = schema.all_canonical(aba)
            opcoes = [OPCAO_EXTRA] + canon
            tabs.add(aba)
            frame = tabs.tab(aba)
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(0, weight=1)
            scroll = ctk.CTkScrollableFrame(frame, fg_color=("gray96", "gray14"))
            scroll.grid(row=0, column=0, sticky="nsew")
            scroll.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(scroll, text="Coluna na sua planilha",
                         font=ctk.CTkFont(size=11, weight="bold"), anchor="w").grid(
                row=0, column=0, sticky="w", padx=6, pady=(2, 6))
            ctk.CTkLabel(scroll, text="Corresponde ao campo",
                         font=ctk.CTkFont(size=11, weight="bold"), anchor="w").grid(
                row=0, column=1, sticky="w", padx=6, pady=(2, 6))

            sug_aba = sugestoes.get(aba, {})
            combos = {}
            for i, col in enumerate(df.columns, start=1):
                ctk.CTkLabel(scroll, text=str(col), anchor="w").grid(
                    row=i, column=0, sticky="ew", padx=6, pady=2)
                combo = ctk.CTkOptionMenu(scroll, values=opcoes, width=300)
                sugerido = sug_aba.get(col)
                combo.set(sugerido if sugerido in canon else OPCAO_EXTRA)
                combo.grid(row=i, column=1, sticky="w", padx=6, pady=2)
                combos[col] = combo
            self._combos[aba] = combos

        rod = ctk.CTkFrame(self, fg_color="transparent")
        rod.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 14))
        rod.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(rod, text="Cancelar", width=120, fg_color="transparent",
                      border_width=1, text_color=("gray30", "gray80"),
                      command=self._cancelar).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(rod, text="Confirmar", width=140,
                      command=self._confirmar).grid(row=0, column=2)

        self.transient(master)
        self.after(50, self._focar)

    def _focar(self):
        self.grab_set()
        self.focus_force()

    def _cancelar(self):
        self.resultado = None
        self.grab_release()
        self.destroy()

    def _confirmar(self):
        mapeamentos: dict[str, dict[str, str | None]] = {}
        for aba, combos in self._combos.items():
            mapa = {}
            for col, combo in combos.items():
                val = combo.get()
                mapa[col] = None if val == OPCAO_EXTRA else val
            mapeamentos[aba] = mapa
        self.resultado = mapeamentos
        self.grab_release()
        self.destroy()


def construir_sugestoes(uploaded_dfs, meta) -> dict:
    """Pré-mapa por aba: metadados embutidos (se houver) ou auto-sugestão."""
    sug = {}
    for aba, df in uploaded_dfs.items():
        if df is None or df.empty:
            continue
        m = concat.mapeamento_de_meta(meta, aba)
        if m is None:
            m = concat.sugerir_mapeamento(aba, list(df.columns))
        sug[aba] = m
    return sug
