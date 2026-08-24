"""
Aba — Borderôs de energia · Adicionar a uma planilha: complementa uma
planilha de borderôs já existente com novos PDFs processados (mesmo espírito
da aba "Adicionar a uma planilha" de faturas, mas para o esquema FIXO dos
borderôs — sem renomeação de colunas pelo usuário, então a checagem de
formato compara diretamente as colunas das 3 abas fixas: borderos/unidades/
resumo_valores — ver `core.borderos.divergencias`/`concatenar`).
"""
from __future__ import annotations

import os
import queue
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..core import borderos, hardcodes
from .widgets import PainelProgresso


class AbaBorderosConcatenar(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._fila: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self.base_dfs: dict | None = None
        self.caminho_base: str | None = None
        self.resultado_dfs: dict | None = None
        self._pasta: str | None = None

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
        self.entry_nome = ctk.CTkEntry(nome_frame, width=240, placeholder_text="borderos_energia")
        self.entry_nome.pack(side="left", padx=(8, 4))
        ctk.CTkLabel(nome_frame, text=".xlsx",
                     text_color=("gray45", "gray60")).pack(side="left")

        self.btn_salvar = ctk.CTkButton(self.rodape, text="💾  Salvar planilha final…",
                                        height=36, command=self._salvar, state="disabled")
        self.btn_salvar.grid(row=1, column=1, sticky="e")

        # ── Área principal (rolável, evita cortar conteúdo em janelas pequenas) ──
        self.main = ctk.CTkScrollableFrame(self, fg_color="transparent")
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

        # 2) Pasta com os novos borderôs
        ctk.CTkLabel(self.main, text="2. Pasta com os NOVOS borderôs",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=2, column=0, sticky="w", pady=(12, 4))
        sel = ctk.CTkFrame(self.main, fg_color=("gray92", "gray20"), corner_radius=8)
        sel.grid(row=3, column=0, sticky="ew")
        sel.grid_columnconfigure(0, weight=1)
        self.lbl_pasta = ctk.CTkLabel(sel, text="Nenhuma pasta selecionada.",
                                      anchor="w", text_color=("gray40", "gray65"))
        self.lbl_pasta.grid(row=0, column=0, sticky="ew", padx=12, pady=10)
        ctk.CTkButton(sel, text="📁  Escolher pasta…", width=150,
                      command=self._escolher_pasta).grid(row=0, column=1, padx=(0, 10), pady=8)

        # 3) Processar
        op = ctk.CTkFrame(self.main, fg_color="transparent")
        op.grid(row=4, column=0, sticky="ew", pady=(10, 2))
        op.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(op, text="3. Processar",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(row=0, column=0, sticky="w")
        self.btn_processar = ctk.CTkButton(op, text="▶  Processar e concatenar",
                                           height=36, command=self._processar)
        self.btn_processar.grid(row=0, column=1, sticky="e")

        self.progresso = PainelProgresso(self.main, on_cancelar=None)
        self.progresso.btn_cancelar.grid_remove()  # sem cancelamento (rápido)

    # ── base ─────────────────────────────────────────────────────────────
    def _selecionar_base(self):
        caminho = filedialog.askopenfilename(
            title="Selecione a planilha base de borderôs",
            filetypes=[("Planilha Excel", "*.xlsx *.xlsm")])
        if not caminho:
            return
        try:
            dfs = borderos.ler_planilha(caminho)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Não foi possível ler a planilha:\n{e}")
            return
        self.base_dfs = {k: v for k, v in dfs.items() if v is not None and not v.empty}
        self.caminho_base = caminho
        self.lbl_base.configure(
            text=f"{os.path.basename(caminho)} · {len(self.base_dfs)} aba(s).")

    # ── pasta ────────────────────────────────────────────────────────────
    def _escolher_pasta(self):
        caminho = filedialog.askdirectory(title="Selecione a pasta dos novos borderôs")
        if not caminho:
            return
        self._pasta = caminho
        n = len(borderos.listar_pdfs(caminho))
        self.lbl_pasta.configure(text=f"{caminho}\n{n} PDF(s) encontrado(s).")

    # ── processamento (thread) ────────────────────────────────────────────
    def _processar(self):
        if not self.base_dfs:
            messagebox.showwarning("Atenção", "Selecione a planilha base primeiro.")
            return
        if not self._pasta:
            messagebox.showwarning("Atenção", "Escolha a pasta dos novos borderôs.")
            return
        pdfs = borderos.listar_pdfs(self._pasta)
        if not pdfs:
            messagebox.showwarning("Atenção", "Nenhum PDF encontrado na pasta.")
            return

        divs = borderos.divergencias(self.base_dfs)
        if divs:
            messagebox.showerror(
                "Formatos diferentes",
                "A planilha base não tem o mesmo formato dos borderôs:\n\n"
                + "\n".join(f"• {d}" for d in divs))
            return

        self.progresso.grid(row=5, column=0, sticky="ew", pady=(8, 4))
        self.progresso.resetar(f"Iniciando… {len(pdfs)} borderô(s).")
        self.btn_processar.configure(state="disabled")
        self.btn_salvar.configure(state="disabled")
        self.resultado_dfs = None

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
                    self._concatenar(payload)
                    return
                elif tipo == "falha":
                    self.btn_processar.configure(state="normal")
                    messagebox.showerror("Erro", f"Falha no processamento:\n{payload}")
                    return
        except queue.Empty:
            pass
        if self._thread and self._thread.is_alive():
            self.after(120, self._poll)

    def _concatenar(self, resultado):
        bs, us, rs = resultado
        self.btn_processar.configure(state="normal")

        res_dfs, resumo = borderos.concatenar(self.base_dfs, bs, us, rs)
        # Hardcodes do usuário (domínio "borderos"): sempre por ÚLTIMO, sobre
        # o conjunto já completo (base + novos borderôs).
        rel_hc = hardcodes.aplicar_dfs(res_dfs, dominio="borderos")

        self.resultado_dfs = res_dfs

        cab = [f"✅ Concatenação concluída. {len(bs)} novo(s) borderô(s) processado(s).", ""]
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
            base = os.path.splitext(os.path.basename(self.caminho_base or "borderos_energia"))[0]
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
            borderos.escrever_dfs(self.resultado_dfs, caminho)
        except PermissionError:
            messagebox.showerror("Erro", "Não foi possível salvar. Feche o arquivo no Excel e tente de novo.")
            return
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Falha ao salvar:\n{e}")
            return
        # Sem pop-up de "deseja abrir agora?": o caminho vai para o log
        # da propria tela, que fica visivel, e o usuario abre quando quiser.
        self.progresso.escrever(f"OK  Planilha salva em: {caminho}")
