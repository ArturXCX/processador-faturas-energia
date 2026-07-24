"""
Aba 2 — Adicionar a uma planilha existente: faz upload de uma planilha (que pode
ter colunas renomeadas/excluídas), processa novas faturas e concatena tudo,
remapeando colunas pelos metadados embutidos ou por uma tela de mapeamento.

Layout: o rodapé (resumo + botão Salvar) fica fixo no fundo com pack(side="bottom"),
garantindo que o botão Salvar esteja SEMPRE visível.
"""
from __future__ import annotations

import os
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..core import excel_io, concat, links, glossario, derivados, hardcodes
from ..core.dataset import Dataset
from .mapping_dialog import DialogoMapeamento, construir_sugestoes
from .widgets import SeletorPastas, PainelProgresso, SeletorLink
from .worker import ProcessWorker


class AbaConcatenar(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.worker: ProcessWorker | None = None
        self.uploaded_dfs: dict | None = None
        self.uploaded_meta: dict | None = None
        self.caminho_base: str | None = None
        self.resultado_dfs: dict | None = None
        self.resultado_meta: dict | None = None

        # ── Rodapé FIXO no fundo (resumo + salvar, sempre visível) ────────
        self.rodape = ctk.CTkFrame(self, fg_color="transparent")
        self.rodape.pack(side="bottom", fill="x", pady=(8, 2))
        self.rodape.grid_columnconfigure(0, weight=1)
        self.txt_resumo = ctk.CTkTextbox(self.rodape, height=96, font=ctk.CTkFont(size=12))
        self.txt_resumo.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.txt_resumo.insert("end", "O resumo da concatenação aparecerá aqui.")
        self.txt_resumo.configure(state="disabled")

        nome_frame = ctk.CTkFrame(self.rodape, fg_color="transparent")
        nome_frame.grid(row=1, column=0, sticky="w")
        ctk.CTkLabel(nome_frame, text="Nome do arquivo:").pack(side="left")
        self.entry_nome = ctk.CTkEntry(nome_frame, width=240, placeholder_text="faturas_energia")
        self.entry_nome.pack(side="left", padx=(8, 4))
        ctk.CTkLabel(nome_frame, text=".xlsx",
                     text_color=("gray45", "gray60")).pack(side="left")

        self.btn_salvar = ctk.CTkButton(self.rodape, text="💾  Salvar planilha final…",
                                        height=36, command=self._salvar, state="disabled")
        self.btn_salvar.grid(row=1, column=1, sticky="e")

        # ── Área principal ────────────────────────────────────────────────
        self.main = ctk.CTkFrame(self, fg_color="transparent")
        self.main.pack(side="top", fill="both", expand=True)
        self.main.grid_columnconfigure(0, weight=1)

        # 1) Planilha base
        ctk.CTkLabel(self.main, text="1. Planilha base (a que será complementada)",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, sticky="w", pady=(4, 4))
        linha = ctk.CTkFrame(self.main, fg_color="transparent")
        linha.grid(row=1, column=0, sticky="ew")
        linha.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(linha, text="📂  Selecionar planilha…", width=190,
                      command=self._selecionar_base).grid(row=0, column=0)
        self.lbl_base = ctk.CTkLabel(linha, text="Nenhuma planilha selecionada.",
                                     anchor="w", text_color=("gray40", "gray65"))
        self.lbl_base.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        # 2) Pastas com novas faturas
        ctk.CTkLabel(self.main, text="2. Pastas com as NOVAS faturas",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=2, column=0, sticky="w", pady=(12, 4))
        self.seletor = SeletorPastas(self.main)
        self.seletor.grid(row=3, column=0, sticky="nsew")
        self.seletor.configure(height=150)
        self.main.grid_rowconfigure(3, weight=1, minsize=140)

        # 3) Opções + ação
        op = ctk.CTkFrame(self.main, fg_color="transparent")
        op.grid(row=4, column=0, sticky="ew", pady=(10, 2))
        op.grid_columnconfigure(0, weight=1)
        self.var_addcols = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(op, text="Adicionar à planilha as colunas novas que ela não possui",
                        variable=self.var_addcols).grid(row=0, column=0, sticky="w")
        self.btn_processar = ctk.CTkButton(op, text="▶  Processar e concatenar",
                                           height=36, command=self._processar)
        self.btn_processar.grid(row=0, column=1, sticky="e")
        self.seletor_link = SeletorLink(op)
        self.seletor_link.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        self.progresso = PainelProgresso(self.main, on_cancelar=self._cancelar)

    # ── base ─────────────────────────────────────────────────────────────
    def _selecionar_base(self):
        caminho = filedialog.askopenfilename(
            title="Selecione a planilha base",
            filetypes=[("Planilha Excel", "*.xlsx *.xlsm")])
        if not caminho:
            return
        try:
            dfs, meta = excel_io.ler_workbook(caminho)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Não foi possível ler a planilha:\n{e}")
            return
        self.uploaded_dfs = {k: v for k, v in dfs.items() if v is not None and not v.empty}
        self.uploaded_meta = meta
        self.caminho_base = caminho
        n_abas = len(self.uploaded_dfs)
        origem = "com metadados deste app" if meta else "sem metadados (usará mapeamento)"
        self.lbl_base.configure(
            text=f"{os.path.basename(caminho)} · {n_abas} aba(s) · {origem}")

    # ── processamento ────────────────────────────────────────────────────
    def _processar(self):
        if not self.uploaded_dfs:
            messagebox.showwarning("Atenção", "Selecione a planilha base primeiro.")
            return
        jobs = self.seletor.jobs()
        if not jobs or self.seletor.total_pdfs() == 0:
            messagebox.showwarning("Atenção", "Adicione pastas com PDFs de novas faturas.")
            return
        total = self.seletor.total_pdfs()
        self.progresso.grid(row=5, column=0, sticky="ew", pady=(6, 4))
        self.progresso.resetar(f"Processando {total} nova(s) fatura(s)…")
        self.progresso.habilitar_cancelar(True)
        self.btn_processar.configure(state="disabled")
        self.btn_salvar.configure(state="disabled")

        self.worker = ProcessWorker(jobs)
        self.worker.iniciar()
        self.after(100, self._poll)

    def _cancelar(self):
        if self.worker:
            self.worker.cancelar()

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
                self._concatenar(payload)
                return
            elif tipo == "falha":
                self.btn_processar.configure(state="normal")
                self.progresso.habilitar_cancelar(False)
                messagebox.showerror("Erro", f"Falha no processamento:\n{payload}")
                return
        if self.worker.ativo():
            self.after(120, self._poll)

    def _concatenar(self, resultado):
        self.btn_processar.configure(state="normal")
        self.progresso.habilitar_cancelar(False)
        ds: Dataset = resultado.dataset
        novos = ds.to_dataframes()
        # Gera link_pdf das novas faturas conforme o modo escolhido.
        modo, template = self.seletor_link.config()
        novos["fatura"] = links.aplicar_link(novos["fatura"], modo, template)

        # Define o mapeamento: metadados embutidos (direto) ou tela de mapeamento.
        if self.uploaded_meta:
            mapeamentos = {}
            for aba, df in self.uploaded_dfs.items():
                m = concat.mapeamento_de_meta(self.uploaded_meta, aba)
                if m is None:
                    m = concat.sugerir_mapeamento(aba, list(df.columns))
                mapeamentos[aba] = m
        else:
            sug = construir_sugestoes(self.uploaded_dfs, self.uploaded_meta)
            dlg = DialogoMapeamento(self.winfo_toplevel(), self.uploaded_dfs, sug)
            self.wait_window(dlg)
            if dlg.resultado is None:
                self.progresso.escrever("Concatenação cancelada (mapeamento).")
                return
            mapeamentos = dlg.resultado

        try:
            res_dfs, meta, resumo = concat.concatenar(
                self.uploaded_dfs, mapeamentos, novos,
                adicionar_novas_colunas=self.var_addcols.get())
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Falha na concatenação:\n{e}")
            return

        # Recalcula colunas derivadas do zero (antigos + novos).
        derivados.aplicar_concat(res_dfs, meta)

        # Hardcodes do usuário: sempre por ÚLTIMO, sobre o conjunto já completo.
        rel_hc = hardcodes.aplicar_dfs(res_dfs)

        self.resultado_dfs = res_dfs
        self.resultado_meta = meta

        n_err = len(resultado.erros)
        cab = [f"✅ Concatenação concluída. {ds.total_faturas()} nova(s) fatura(s) processada(s)."]
        if n_err:
            cab.append(f"⚠ {n_err} arquivo(s) com erro (veja o log acima).")
        cab.append("")
        if rel_hc:
            resumo = resumo + ["", "Hardcodes aplicados:"] + [f"  {l}" for l in rel_hc]
        texto = "\n".join(cab + resumo)
        self.progresso.progresso(1, 1, "Concluído.")
        self.txt_resumo.configure(state="normal")
        self.txt_resumo.delete("1.0", "end")
        self.txt_resumo.insert("end", texto)
        self.txt_resumo.configure(state="disabled")
        self.btn_salvar.configure(state="normal")

    def _nome_arquivo(self) -> str:
        nome = (self.entry_nome.get() or "").strip()
        if not nome:
            base = os.path.splitext(os.path.basename(self.caminho_base or "faturas_energia"))[0]
            nome = f"{base}_atualizada"
        if nome.lower().endswith(".xlsx"):
            nome = nome[:-5]
        return nome + ".xlsx"

    # ── salvar ───────────────────────────────────────────────────────────
    def _salvar(self):
        if not self.resultado_dfs:
            messagebox.showwarning("Atenção", "Processe e concatene antes de salvar.")
            return
        caminho = filedialog.asksaveasfilename(
            title="Salvar planilha final", defaultextension=".xlsx",
            initialfile=self._nome_arquivo(),
            filetypes=[("Planilha Excel", "*.xlsx")])
        if not caminho:
            return
        try:
            # acrescenta a aba glossário se a planilha base ainda não a tiver
            dfs_final = glossario.garantir_glossario(self.resultado_dfs)
            excel_io.escrever_workbook(dfs_final, self.resultado_meta, caminho)
        except PermissionError:
            messagebox.showerror("Erro", "Não foi possível salvar. Feche o arquivo no Excel e tente de novo.")
            return
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Falha ao salvar:\n{e}")
            return
        if messagebox.askyesno("Pronto", f"Planilha salva em:\n{caminho}\n\nDeseja abrir agora?"):
            try:
                os.startfile(caminho)  # type: ignore[attr-defined]
            except Exception:
                pass
