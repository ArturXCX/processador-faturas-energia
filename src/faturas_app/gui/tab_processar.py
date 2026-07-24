"""
Aba 1 — Processar faturas: seleciona pastas (cada uma com sua fornecedora),
processa os PDFs com barra de progresso, deixa ajustar colunas/abas e salva.

Layout: o rodapé (botão Salvar) fica fixo no fundo com pack(side="bottom"),
garantindo que ele esteja SEMPRE visível; o restante preenche a área acima e o
editor de colunas rola internamente quando há muitas colunas.
"""
from __future__ import annotations

import os
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..core import excel_io, links, glossario, derivados, hardcodes
from ..core.dataset import Dataset
from ..core.profile import Perfil
from .columns_editor import EditorColunas
from .widgets import SeletorPastas, PainelProgresso, SeletorLink
from .worker import ProcessWorker


class AbaProcessar(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.worker: ProcessWorker | None = None
        self.dfs_canon: dict | None = None
        self.perfil: Perfil | None = None
        self._erros = []

        # ── Rodapé FIXO no fundo (sempre visível) ─────────────────────────
        self.rodape = ctk.CTkFrame(self, fg_color="transparent")
        self.rodape.pack(side="bottom", fill="x", pady=(8, 2))
        self.rodape.grid_columnconfigure(0, weight=1)
        self.lbl_resumo = ctk.CTkLabel(self.rodape, text="", anchor="w",
                                       text_color=("gray35", "gray70"))
        self.lbl_resumo.grid(row=0, column=0, columnspan=2, sticky="w")

        nome_frame = ctk.CTkFrame(self.rodape, fg_color="transparent")
        nome_frame.grid(row=1, column=0, sticky="w", pady=(4, 0))
        ctk.CTkLabel(nome_frame, text="Nome do arquivo:").pack(side="left")
        self.entry_nome = ctk.CTkEntry(nome_frame, width=240, placeholder_text="faturas_energia")
        self.entry_nome.pack(side="left", padx=(8, 4))
        ctk.CTkLabel(nome_frame, text=".xlsx",
                     text_color=("gray45", "gray60")).pack(side="left")

        self.btn_salvar = ctk.CTkButton(self.rodape, text="💾  Salvar planilha…",
                                        height=36, command=self._salvar, state="disabled")
        self.btn_salvar.grid(row=1, column=1, sticky="e")

        # ── Área principal (preenche o restante) ──────────────────────────
        self.main = ctk.CTkFrame(self, fg_color="transparent")
        self.main.pack(side="top", fill="both", expand=True)
        self.main.grid_columnconfigure(0, weight=1)

        # 1) Pastas
        ctk.CTkLabel(self.main, text="1. Selecione as pastas de PDFs",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, sticky="w", pady=(4, 4))
        self.seletor = SeletorPastas(self.main)
        self.seletor.grid(row=1, column=0, sticky="nsew")
        self.seletor.configure(height=160)

        # 2) Processar + progresso
        barra = ctk.CTkFrame(self.main, fg_color="transparent")
        barra.grid(row=2, column=0, sticky="ew", pady=(10, 2))
        barra.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(barra, text="2. Processar",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, sticky="w")
        self.btn_processar = ctk.CTkButton(barra, text="▶  Processar PDFs",
                                           height=36, command=self._processar)
        self.btn_processar.grid(row=0, column=1, sticky="e")
        self.seletor_link = SeletorLink(barra)
        self.seletor_link.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        self.progresso = PainelProgresso(self.main, on_cancelar=self._cancelar)
        # (mostrado só durante/após o processamento)

        # 3) Editor de colunas (oculto até processar)
        self.lbl_editor = ctk.CTkLabel(self.main, text="3. Ajuste colunas e abas",
                                       font=ctk.CTkFont(size=15, weight="bold"))
        self.editor = EditorColunas(self.main)

    # ── processamento ────────────────────────────────────────────────────
    def _processar(self):
        jobs = self.seletor.jobs()
        if not jobs:
            messagebox.showwarning("Atenção", "Adicione ao menos uma pasta.")
            return
        total = self.seletor.total_pdfs()
        if total == 0:
            messagebox.showwarning("Atenção", "Nenhum PDF encontrado nas pastas selecionadas.")
            return

        # esconde etapas posteriores e mostra progresso
        self.lbl_editor.grid_forget()
        self.editor.grid_forget()
        self.main.grid_rowconfigure(5, weight=0)
        self.progresso.grid(row=3, column=0, sticky="ew", pady=(6, 4))
        self.progresso.resetar(f"Iniciando… {total} PDF(s).")
        self.progresso.habilitar_cancelar(True)
        self.btn_processar.configure(state="disabled")
        self.btn_salvar.configure(state="disabled")
        self._erros = []

        self.worker = ProcessWorker(jobs)
        self.worker.iniciar()
        self.after(100, self._poll)

    def _cancelar(self):
        if self.worker:
            self.worker.cancelar()
            self.progresso.escrever("Cancelando…")

    def _poll(self):
        if not self.worker:
            return
        for tipo, payload in self.worker.eventos():
            if tipo == "progresso":
                feito, total, nome, forn, ok, msg = payload
                self.progresso.progresso(feito, total, f"{feito}/{total} — {nome}")
                if not ok:
                    self.progresso.escrever(f"⚠ ERRO [{forn}] {nome}: {msg}")
            elif tipo == "concluido":
                self._concluir(payload)
                return
            elif tipo == "falha":
                self.btn_processar.configure(state="normal")
                self.progresso.habilitar_cancelar(False)
                messagebox.showerror("Erro", f"Falha no processamento:\n{payload}")
                return
        if self.worker.ativo():
            self.after(120, self._poll)

    def _concluir(self, resultado):
        self.btn_processar.configure(state="normal")
        self.progresso.habilitar_cancelar(False)
        self._erros = resultado.erros
        ds: Dataset = resultado.dataset
        self.dfs_canon = ds.to_dataframes()
        # Gera a coluna link_pdf conforme o modo escolhido (caminho/busca/modelo).
        modo, template = self.seletor_link.config()
        self.dfs_canon["fatura"] = links.aplicar_link(self.dfs_canon["fatura"], modo, template)

        # Colunas derivadas (ex.: cliente.ultima_competencia/ultima_fatura).
        derivados.aplicar(self.dfs_canon)

        # Hardcodes do usuário: sempre por ÚLTIMO, sobre os dados já completos.
        rel_hc = hardcodes.aplicar_dfs(self.dfs_canon)

        self.perfil = Perfil.padrao_de_dataframes(self.dfs_canon)

        n_fat = ds.total_faturas()
        n_err = len(resultado.erros)
        status = f"✅ Concluído: {n_fat} fatura(s) processada(s)."
        if n_err:
            status += f"  ⚠ {n_err} arquivo(s) com erro (veja o log)."
        if resultado.cancelado:
            status = "⏹ Processamento cancelado.  " + status
        self.progresso.progresso(resultado.processados, max(resultado.total, 1), status)
        if rel_hc:
            self.progresso.escrever("Hardcodes aplicados:")
            for linha in rel_hc:
                self.progresso.escrever(f"  {linha}")

        # mostra editor + habilita salvar
        self.lbl_editor.grid(row=4, column=0, sticky="w", pady=(12, 4))
        self.editor.grid(row=5, column=0, sticky="nsew", pady=(0, 4))
        self.main.grid_rowconfigure(5, weight=1, minsize=150)
        self.editor.carregar(self.perfil)
        self.lbl_resumo.configure(text=status)
        self.btn_salvar.configure(state="normal")

    def _nome_arquivo(self) -> str:
        nome = (self.entry_nome.get() or "").strip() or "faturas_energia"
        if nome.lower().endswith(".xlsx"):
            nome = nome[:-5]
        return nome + ".xlsx"

    # ── salvar ───────────────────────────────────────────────────────────
    def _salvar(self):
        if not self.dfs_canon or not self.editor.tem_perfil():
            messagebox.showwarning("Atenção", "Processe os PDFs antes de salvar.")
            return
        perfil = self.editor.coletar()
        if not any(a.incluida for a in perfil.abas):
            messagebox.showwarning("Atenção", "Selecione ao menos uma aba para incluir.")
            return
        caminho = filedialog.asksaveasfilename(
            title="Salvar planilha", defaultextension=".xlsx",
            initialfile=self._nome_arquivo(),
            filetypes=[("Planilha Excel", "*.xlsx")])
        if not caminho:
            return
        try:
            display = perfil.aplicar(self.dfs_canon)
            display = glossario.garantir_glossario(display)   # sempre inclui a aba glossário
            excel_io.escrever_workbook(display, perfil.to_meta(), caminho)
        except PermissionError:
            messagebox.showerror("Erro", "Não foi possível salvar. Feche o arquivo no Excel e tente de novo.")
            return
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Falha ao salvar:\n{e}")
            return
        self._oferecer_abrir(caminho)

    def _oferecer_abrir(self, caminho):
        if messagebox.askyesno("Pronto", f"Planilha salva em:\n{caminho}\n\nDeseja abrir agora?"):
            try:
                os.startfile(caminho)  # type: ignore[attr-defined]
            except Exception:
                pass
