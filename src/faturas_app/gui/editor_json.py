"""
Editor de JSON embutido no app.

Os três parâmetros do sistema — mapa de UCs, hardcodes e normalização de itens —
são persistidos em JSON. Esta janela abre esse JSON para edição manual e, ao
salvar, regrava o arquivo com as alterações, de modo que o app passa a usar a
versão editada na hora seguinte.

O salvamento é DEFENSIVO: o conteúdo é validado como JSON antes de tocar no
arquivo, e o arquivo anterior é preservado como `.bak`. Um parâmetro corrompido
por um erro de digitação faria o app processar milhares de faturas com o
cadastro errado — recuperar precisa ser trivial.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk


class EditorJson(ctk.CTkToplevel):
    def __init__(self, master, titulo: str, caminho, ao_salvar=None):
        super().__init__(master)
        self.title(f"Editar — {titulo}")
        self.geometry("900x640")
        self._caminho = Path(caminho)
        self._ao_salvar = ao_salvar

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        ctk.CTkLabel(cab, text=titulo,
                     font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(cab, text=str(self._caminho), anchor="w",
                     font=ctk.CTkFont(size=11),
                     text_color=("gray45", "gray60")).pack(anchor="w")

        self.texto = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=12),
                                    wrap="none")
        self.texto.grid(row=1, column=0, sticky="nsew", padx=14, pady=6)

        rod = ctk.CTkFrame(self, fg_color="transparent")
        rod.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 12))
        rod.grid_columnconfigure(0, weight=1)
        self.lbl = ctk.CTkLabel(rod, text="", anchor="w",
                                text_color=("gray35", "gray70"))
        self.lbl.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(rod, text="Verificar", width=110, fg_color="transparent",
                      border_width=1, text_color=("gray30", "gray80"),
                      command=self._verificar).grid(row=0, column=1, padx=(8, 8))
        ctk.CTkButton(rod, text="Fechar", width=100, fg_color="transparent",
                      border_width=1, text_color=("gray30", "gray80"),
                      command=self.destroy).grid(row=0, column=2, padx=(0, 8))
        ctk.CTkButton(rod, text="💾  Salvar", width=130, height=36,
                      command=self._salvar).grid(row=0, column=3)

        self._carregar()
        self.transient(master)

    # ── ações ────────────────────────────────────────────────────────────
    def _carregar(self):
        try:
            bruto = self._caminho.read_text(encoding="utf-8")
        except FileNotFoundError:
            bruto = "[]"
            self.lbl.configure(text="arquivo ainda não existe — será criado ao salvar.")
        except Exception as e:  # noqa: BLE001
            bruto = ""
            self.lbl.configure(text=f"⚠ não consegui ler: {e}")
        self.texto.delete("1.0", "end")
        self.texto.insert("1.0", bruto)

    def _analisar(self):
        """Devolve (dados, None) ou (None, mensagem_de_erro)."""
        try:
            return json.loads(self.texto.get("1.0", "end")), None
        except json.JSONDecodeError as e:
            return None, f"linha {e.lineno}, coluna {e.colno}: {e.msg}"

    def _verificar(self):
        dados, erro = self._analisar()
        if erro:
            self.lbl.configure(text=f"⚠ JSON inválido — {erro}")
            return False
        n = len(dados) if isinstance(dados, (list, dict)) else 1
        self.lbl.configure(text=f"✅ JSON válido ({n} item(ns) no nível de cima).")
        return True

    def _salvar(self):
        dados, erro = self._analisar()
        if erro:
            self.lbl.configure(text=f"⚠ JSON inválido — {erro}")
            messagebox.showerror(
                "JSON inválido",
                f"O conteúdo não é um JSON válido e por isso NÃO foi salvo:\n\n{erro}")
            return
        try:
            if self._caminho.exists():
                shutil.copy(self._caminho, self._caminho.with_suffix(
                    self._caminho.suffix + ".bak"))
            self._caminho.parent.mkdir(parents=True, exist_ok=True)
            self._caminho.write_text(
                json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Não foi possível salvar:\n{e}")
            return
        self.lbl.configure(text="✅ salvo (cópia do anterior em .bak).")
        if self._ao_salvar:
            try:
                self._ao_salvar()
            except Exception:  # noqa: BLE001
                pass
