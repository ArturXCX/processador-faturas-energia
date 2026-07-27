"""
Aba — Borderôs de energia: seleciona a pasta com os borderôs (faturas
AGRUPADAS), processa todos os PDFs (poucos por ano) com barra de progresso,
mostra a conferência (soma das UCs × total impresso) e salva a planilha com as
abas `borderos`, `unidades` e `resumo_valores`.

Fluxo mais simples que a aba de faturas: um borderô já é um documento
consolidado, então não há editor de colunas nem escolha de fornecedora — a
distribuidora (ENEL/EQUATORIAL) e o layout são detectados automaticamente.
"""
from __future__ import annotations

import os
import queue
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..core import borderos
from .widgets import PainelProgresso


class AbaBorderos(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._fila: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._resultado = None  # (borderos, unidades, resumo)

        # ── Rodapé FIXO (sempre visível) ──────────────────────────────────
        self.rodape = ctk.CTkFrame(self, fg_color="transparent")
        self.rodape.pack(side="bottom", fill="x", pady=(8, 2))
        self.rodape.grid_columnconfigure(0, weight=1)
        self.lbl_resumo = ctk.CTkLabel(self.rodape, text="", anchor="w",
                                       text_color=("gray35", "gray70"))
        self.lbl_resumo.grid(row=0, column=0, columnspan=2, sticky="w")

        nome_frame = ctk.CTkFrame(self.rodape, fg_color="transparent")
        nome_frame.grid(row=1, column=0, sticky="w", pady=(4, 0))
        ctk.CTkLabel(nome_frame, text="Nome do arquivo:").pack(side="left")
        self.entry_nome = ctk.CTkEntry(nome_frame, width=240,
                                       placeholder_text="borderos_energia")
        self.entry_nome.pack(side="left", padx=(8, 4))
        ctk.CTkLabel(nome_frame, text=".xlsx",
                     text_color=("gray45", "gray60")).pack(side="left")

        self.btn_salvar = ctk.CTkButton(self.rodape, text="💾  Salvar planilha…",
                                        height=36, command=self._salvar, state="disabled")
        self.btn_salvar.grid(row=1, column=1, sticky="e")

        # ── Área principal ────────────────────────────────────────────────
        self.main = ctk.CTkFrame(self, fg_color="transparent")
        self.main.pack(side="top", fill="both", expand=True)
        self.main.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.main, text="1. Selecione a pasta dos borderôs",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, sticky="w", pady=(4, 4))
        ctk.CTkLabel(
            self.main,
            text="Pasta com os PDFs de faturas agrupadas (ENEL/CELG ou "
                 "EQUATORIAL). Subpastas por ano são lidas automaticamente.",
            text_color=("gray45", "gray60"), anchor="w", justify="left").grid(
            row=1, column=0, sticky="w", pady=(0, 6))

        sel = ctk.CTkFrame(self.main, fg_color=("gray92", "gray20"), corner_radius=8)
        sel.grid(row=2, column=0, sticky="ew")
        sel.grid_columnconfigure(0, weight=1)
        self.lbl_pasta = ctk.CTkLabel(sel, text="Nenhuma pasta selecionada.",
                                      anchor="w", text_color=("gray40", "gray65"))
        self.lbl_pasta.grid(row=0, column=0, sticky="ew", padx=12, pady=10)
        ctk.CTkButton(sel, text="📁  Escolher pasta…", width=150,
                      command=self._escolher).grid(row=0, column=1, padx=(0, 10), pady=8)
        self._pasta: str | None = None

        barra = ctk.CTkFrame(self.main, fg_color="transparent")
        barra.grid(row=3, column=0, sticky="ew", pady=(12, 2))
        barra.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(barra, text="2. Processar",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, sticky="w")
        self.btn_processar = ctk.CTkButton(barra, text="▶  Processar borderôs",
                                           height=36, command=self._processar)
        self.btn_processar.grid(row=0, column=1, sticky="e")

        self.progresso = PainelProgresso(self.main, on_cancelar=None)
        self.progresso.btn_cancelar.grid_remove()  # sem cancelamento (rápido)

        # Tenta pré-selecionar a pasta padrão de borderôs, se existir.
        self._pre_selecionar_padrao()

    # ── seleção de pasta ──────────────────────────────────────────────────
    def _pre_selecionar_padrao(self):
        for cand in ("pdfs/borderos_energia_tjgo", "../pdfs/borderos_energia_tjgo"):
            if os.path.isdir(cand):
                self._definir_pasta(os.path.abspath(cand))
                return

    def _escolher(self):
        caminho = filedialog.askdirectory(title="Selecione a pasta dos borderôs")
        if caminho:
            self._definir_pasta(caminho)

    def _definir_pasta(self, caminho):
        self._pasta = caminho
        n = len(borderos.listar_pdfs(caminho))
        self.lbl_pasta.configure(
            text=f"{caminho}\n{n} PDF(s) encontrado(s).")

    # ── processamento (thread) ────────────────────────────────────────────
    def _processar(self):
        if not self._pasta:
            messagebox.showwarning("Atenção", "Escolha a pasta dos borderôs.")
            return
        pdfs = borderos.listar_pdfs(self._pasta)
        if not pdfs:
            messagebox.showwarning("Atenção", "Nenhum PDF encontrado na pasta.")
            return

        self.progresso.grid(row=4, column=0, sticky="ew", pady=(8, 4))
        self.progresso.resetar(f"Iniciando… {len(pdfs)} borderô(s).")
        self.btn_processar.configure(state="disabled")
        self.btn_salvar.configure(state="disabled")
        self._resultado = None

        pasta = self._pasta

        def worker():
            try:
                def prog(i, n, nome):
                    self._fila.put(("progresso", (i, n, nome)))
                res = borderos.processar_pasta(pasta, prog)
                self._fila.put(("concluido", res))
            except Exception as e:  # noqa: BLE001
                self._fila.put(("falha", str(e)))

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()
        self.after(100, self._poll)

    def _poll(self):
        try:
            while True:
                tipo, payload = self._fila.get_nowait()
                if tipo == "progresso":
                    i, n, nome = payload
                    self.progresso.progresso(i, n, f"{i}/{n} — {nome}")
                elif tipo == "concluido":
                    self._concluir(payload)
                    return
                elif tipo == "falha":
                    self.btn_processar.configure(state="normal")
                    messagebox.showerror("Erro", f"Falha no processamento:\n{payload}")
                    return
        except queue.Empty:
            pass
        if self._thread and self._thread.is_alive():
            self.after(120, self._poll)

    def _concluir(self, resultado):
        bs, us, rs = resultado
        self._resultado = resultado
        self.btn_processar.configure(state="normal")
        self.btn_salvar.configure(state="normal")

        ok = sum(1 for b in bs if b["bate_total"] == "SIM")
        na = sum(1 for b in bs if b["bate_total"] == "N/A")
        nao = sum(1 for b in bs if b["bate_total"] == "NÃO")

        status = (f"✅ {len(bs)} borderô(s) · {len(us)} unidade(s) · "
                  f"{len(rs)} rubrica(s).  Conferência do total: {ok} ok"
                  + (f", {na} escaneado(s)" if na else "")
                  + (f", {nao} divergente(s)" if nao else "") + ".")
        self.progresso.progresso(1, 1, status)
        self.lbl_resumo.configure(text=status)

        self.progresso.escrever("Conferência (soma das UCs × total impresso):")
        for b in bs:
            marca = {"SIM": "✔", "N/A": "○", "NÃO": "✗"}.get(b["bate_total"], "?")
            linha = (f"  {marca} {b['competencia']} {b['distribuidora']:10} "
                     f"contas={b['quantidade_contas_extraidas']:>4}  "
                     f"total={b['valor_total']}")
            if b["observacao"]:
                linha += f"  — {b['observacao']}"
            self.progresso.escrever(linha)

    # ── salvar ────────────────────────────────────────────────────────────
    def _nome_arquivo(self) -> str:
        nome = (self.entry_nome.get() or "").strip() or "borderos_energia"
        if nome.lower().endswith(".xlsx"):
            nome = nome[:-5]
        return nome + ".xlsx"

    def _salvar(self):
        if not self._resultado:
            messagebox.showwarning("Atenção", "Processe os borderôs antes de salvar.")
            return
        caminho = filedialog.asksaveasfilename(
            title="Salvar planilha", defaultextension=".xlsx",
            initialfile=self._nome_arquivo(),
            filetypes=[("Planilha Excel", "*.xlsx")])
        if not caminho:
            return
        bs, us, rs = self._resultado
        try:
            borderos.escrever_planilha(bs, us, rs, caminho)
        except PermissionError:
            messagebox.showerror(
                "Erro", "Não foi possível salvar. Feche o arquivo no Excel e tente de novo.")
            return
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Falha ao salvar:\n{e}")
            return
        if messagebox.askyesno("Pronto", f"Planilha salva em:\n{caminho}\n\nDeseja abrir agora?"):
            try:
                os.startfile(caminho)  # type: ignore[attr-defined]
            except Exception:
                pass
