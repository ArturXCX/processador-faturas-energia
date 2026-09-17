"""
Abas — Água: processa PDFs de faturas de água de TODAS as concessionárias (Saneago borderô/analítica, SAE Catalão,
DEMAEs, SAAEs, SANESC, São Simão, Ipameri, Buriti Alegre, CODEGO) no MESMO modelo de planilha, com mapa de contas,
validação e a opção de complementar uma planilha já existente.
"""
from __future__ import annotations

import os
import queue
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..core.agua import controller_agua, mapa_conta
from ..core.agua import schema_agua as S
from .widgets import PainelProgresso, SeletorLink


class SeletorPastasAgua(ctk.CTkFrame):
    """Lista simples de pastas (sem fornecedora: a concessionária é reconhecida pelo conteúdo do PDF)."""

    def __init__(self, master, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.grid_columnconfigure(0, weight=1)
        self.pastas: list[str] = []
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        barra.grid_columnconfigure(0, weight=1)
        self.var_sub = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(barra, text="Incluir subpastas (anos)", variable=self.var_sub).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(barra, text="➕  Adicionar pasta", command=self.adicionar).grid(row=0, column=1, sticky="e")
        self.lista = ctk.CTkScrollableFrame(self, fg_color=("gray96", "gray14"), height=120)
        self.lista.grid(row=1, column=0, sticky="ew")
        self.lista.grid_columnconfigure(0, weight=1)
        self._linhas: list[ctk.CTkFrame] = []
        self.vazio = ctk.CTkLabel(self.lista, text="Nenhuma pasta adicionada. Pode ser a pasta-mãe do acervo (todas as "
                                                   "concessionárias) ou uma pasta por concessionária.",
                                  text_color=("gray50", "gray55"), wraplength=700)
        self.vazio.grid(row=0, column=0, pady=20)

    def adicionar(self, caminho: str | None = None):
        caminho = caminho or filedialog.askdirectory(title="Selecione uma pasta com PDFs de água")
        if not caminho or caminho in self.pastas:
            return
        self.vazio.grid_remove()
        n = len(controller_agua.listar_pdfs(caminho, self.var_sub.get()))
        fr = ctk.CTkFrame(self.lista, fg_color=("gray92", "gray20"), corner_radius=8)
        fr.grid(row=len(self.pastas), column=0, sticky="ew", pady=3, padx=4)
        fr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(fr, text=f"{caminho}   ·   {n} PDF(s)", anchor="w").grid(row=0, column=0, sticky="ew", padx=10, pady=6)
        ctk.CTkButton(fr, text="Remover", width=80, fg_color="transparent", border_width=1,
                      text_color=("gray30", "gray80"), command=lambda: self._remover(caminho, fr)).grid(row=0, column=1, padx=8)
        self.pastas.append(caminho)
        self._linhas.append(fr)

    def _remover(self, caminho, fr):
        fr.destroy()
        i = self.pastas.index(caminho)
        self.pastas.pop(i)
        self._linhas.pop(i)
        for k, l in enumerate(self._linhas):
            l.grid_configure(row=k)
        if not self.pastas:
            self.vazio.grid()

    def total_pdfs(self) -> int:
        return controller_agua.contar_pdfs(self.pastas, self.var_sub.get())


class PainelMapaContas(ctk.CTkFrame):
    """Estado do mapa de contas + importar / gerar do resultado / limpar."""

    def __init__(self, master, obter_resultado=None, **kw):
        super().__init__(master, fg_color=("gray92", "gray20"), corner_radius=8, **kw)
        self._obter_resultado = obter_resultado
        self.grid_columnconfigure(0, weight=1)
        self.lbl = ctk.CTkLabel(self, text="", anchor="w", justify="left", wraplength=640)
        self.lbl.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 4))
        botoes = ctk.CTkFrame(self, fg_color="transparent")
        botoes.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 8))
        ctk.CTkButton(botoes, text="📂  Importar mapa (contas.json / xlsx / csv)…", command=self._importar).pack(side="left", padx=(0, 6))
        self.btn_gerar = ctk.CTkButton(botoes, text="🧭  Gerar do resultado", command=self._gerar, state="disabled")
        self.btn_gerar.pack(side="left", padx=(0, 6))
        ctk.CTkButton(botoes, text="Limpar", width=80, fg_color="transparent", border_width=1,
                      text_color=("gray30", "gray80"), command=self._limpar).pack(side="left")
        self.atualizar()

    def atualizar(self):
        if mapa_conta.ativo():
            m = mapa_conta.metadados()
            self.lbl.configure(text=f"Mapa de contas ATIVO: {m['total_contas']} conta(s) · origem: {m['origem']} · {m['arquivo']}")
        else:
            self.lbl.configure(text="Sem mapa de contas: a planilha sai com conta_canonica = dígitos da conta e sem unidade "
                                    "institucional. Importe o contas.json do projeto original ou gere um mapa do resultado.")

    def _importar(self):
        caminho = filedialog.askopenfilename(title="Importar mapa de contas",
                                             filetypes=[("Mapa de contas", "*.json *.xlsx *.xls *.csv")])
        if not caminho:
            return
        try:
            m = mapa_conta.importar(caminho)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Não foi possível importar o mapa:\n{e}")
            return
        self.atualizar()
        messagebox.showinfo("Mapa de contas", f"{m['total_contas']} conta(s) importada(s).")

    def _gerar(self):
        res = self._obter_resultado() if self._obter_resultado else None
        if not res:
            messagebox.showwarning("Atenção", "Processe as faturas antes de gerar o mapa.")
            return
        m = controller_agua.salvar_mapa_da_extracao(res)
        self.atualizar()
        messagebox.showinfo("Mapa de contas", f"Mapa gerado com {m['total_contas']} conta(s). Processe de novo para "
                                              "preencher conta_canonica/unidade e a validação com o mapa.")

    def _limpar(self):
        if messagebox.askyesno("Mapa de contas", "Remover o mapa de contas ativo?"):
            mapa_conta.limpar()
            self.atualizar()


class _BaseAgua(ctk.CTkFrame):
    """Fluxo comum: pastas → processar em thread → resultado → salvar."""

    NOME_PADRAO = "faturas_agua"

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._fila: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._cancelar = False
        self.lote: controller_agua.ResultadoLote | None = None
        self.resultado_dfs: dict | None = None

    # ── rodapé ────────────────────────────────────────────────────────────
    def _rodape(self, placeholder: str, texto_botao: str):
        self.rodape = ctk.CTkFrame(self, fg_color="transparent")
        self.rodape.pack(side="bottom", fill="x", pady=(8, 2))
        self.rodape.grid_columnconfigure(0, weight=1)
        self.lbl_resumo = ctk.CTkLabel(self.rodape, text="", anchor="w", justify="left", wraplength=900,
                                       text_color=("gray35", "gray70"))
        self.lbl_resumo.grid(row=0, column=0, columnspan=2, sticky="w")
        nome_frame = ctk.CTkFrame(self.rodape, fg_color="transparent")
        nome_frame.grid(row=1, column=0, sticky="w", pady=(4, 0))
        ctk.CTkLabel(nome_frame, text="Nome do arquivo:").pack(side="left")
        self.entry_nome = ctk.CTkEntry(nome_frame, width=240, placeholder_text=placeholder)
        self.entry_nome.pack(side="left", padx=(8, 4))
        ctk.CTkLabel(nome_frame, text=".xlsx", text_color=("gray45", "gray60")).pack(side="left")
        self.btn_salvar = ctk.CTkButton(self.rodape, text=texto_botao, height=36, command=self._salvar, state="disabled")
        self.btn_salvar.grid(row=1, column=1, sticky="e")

    def _nome_arquivo(self) -> str:
        nome = (self.entry_nome.get() or "").strip() or self.NOME_PADRAO
        if nome.lower().endswith(".xlsx"):
            nome = nome[:-5]
        return nome + ".xlsx"

    # ── processamento ─────────────────────────────────────────────────────
    def _iniciar(self, pastas: list[str], subpastas: bool, ocr: bool, modo_link: str, template: str | None):
        total = controller_agua.contar_pdfs(pastas, subpastas)
        if not total:
            messagebox.showwarning("Atenção", "Nenhum PDF encontrado nas pastas.")
            return False
        self.progresso.resetar(f"Iniciando… {total} PDF(s). PDFs digitalizados passam por OCR (mais lentos).")
        self.progresso.habilitar_cancelar(True)
        self.btn_processar.configure(state="disabled")
        self.btn_salvar.configure(state="disabled")
        self._cancelar = False
        self.lote = None
        self.resultado_dfs = None
        cache = os.path.join(mapa_conta._dir_usuario(), "cache_agua")

        def worker():
            try:
                def prog(i, n, nome):
                    self._fila.put(("progresso", (i, n, nome)))
                lote = controller_agua.processar_pastas(pastas, prog, lambda: self._cancelar, cache_dir=cache, ocr=ocr,
                                                        subpastas=subpastas, modo_link=modo_link, template=template)
                self._fila.put(("concluido", lote))
            except Exception as e:  # noqa: BLE001
                self._fila.put(("falha", f"{type(e).__name__}: {e}"))

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()
        self.after(100, self._poll)
        return True

    def _pedir_cancelamento(self):
        self._cancelar = True
        self.progresso.escrever("Cancelando… (termina o PDF em andamento)")

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

    def _relatar(self, lote: controller_agua.ResultadoLote):
        self.progresso.progresso(1, 1, "Concluído." if not lote.cancelado else "Cancelado.")
        self.progresso.escrever(lote.resumo())
        r = lote.resultado
        if r.borderos:
            self.progresso.escrever("Borderôs Saneago (soma das contas × total impresso):")
            for b in r.borderos:
                marca = {"SIM": "✔", "N/A": "○", "NÃO": "✗"}.get(b.get("bate_total"), "?")
                self.progresso.escrever(f"  {marca} {b.get('competencia')} fatura {b.get('numero_fatura')}  contas={b.get('quantidade_contas_extraidas')}"
                                        f"  final={b.get('valor_final')}" + (f"  — {b['observacao']}" if b.get("observacao") else ""))
        por_forn: dict[str, int] = {}
        for f in r.faturas:
            por_forn[f.get("fornecedor") or "?"] = por_forn.get(f.get("fornecedor") or "?", 0) + 1
        if por_forn:
            self.progresso.escrever("Faturas por concessionária: " + ", ".join(f"{k} {v}" for k, v in sorted(por_forn.items())))
        erros = [v for v in lote.validacao if v["gravidade"] == "erro"]
        if erros:
            self.progresso.escrever(f"Validação — {len(erros)} erro(s) (aba '{S.ABA_VALIDACAO}'); primeiros:")
            for v in erros[:8]:
                self.progresso.escrever(f"  ✗ {v['regra']} · {v['id']} · {v['detalhe']}")
        for e in lote.erros[:10]:
            self.progresso.escrever(f"  ! {e.arquivo}: {e.mensagem}")
        if len(lote.erros) > 10:
            self.progresso.escrever(f"  … e mais {len(lote.erros) - 10} PDF(s) com falha.")
        self.lbl_resumo.configure(text=lote.resumo())

    def _salvar(self):
        if not self.resultado_dfs:
            messagebox.showwarning("Atenção", "Processe as faturas antes de salvar.")
            return
        caminho = filedialog.asksaveasfilename(title="Salvar planilha", defaultextension=".xlsx",
                                               initialfile=self._nome_arquivo(), filetypes=[("Planilha Excel", "*.xlsx")])
        if not caminho:
            return
        try:
            controller_agua.escrever_planilha(self.resultado_dfs, caminho)
        except PermissionError:
            messagebox.showerror("Erro", "Não foi possível salvar. Feche o arquivo no Excel e tente de novo.")
            return
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Falha ao salvar:\n{e}")
            return
        self.progresso.escrever(f"OK  Planilha salva em: {caminho}")


class AbaAgua(_BaseAgua):
    """Processar faturas de água → planilha nova."""

    def __init__(self, master):
        super().__init__(master)
        self._rodape("faturas_agua", "💾  Salvar planilha…")

        self.main = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main.pack(side="top", fill="both", expand=True)
        self.main.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.main, text="1. Pastas com os PDFs de água", font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, sticky="w", pady=(4, 2))
        ctk.CTkLabel(self.main, text="A concessionária e o tipo (fatura, borderô ou analítica da Saneago) são reconhecidos pelo "
                                     "conteúdo de cada PDF. Todas saem nas mesmas abas, diferenciadas pela coluna 'fornecedor'.",
                     text_color=("gray45", "gray60"), anchor="w", justify="left", wraplength=900).grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.seletor = SeletorPastasAgua(self.main)
        self.seletor.grid(row=2, column=0, sticky="ew")

        ctk.CTkLabel(self.main, text="2. Mapa de contas (opcional)", font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=3, column=0, sticky="w", pady=(12, 4))
        self.painel_mapa = PainelMapaContas(self.main, obter_resultado=lambda: self.lote.resultado if self.lote else None)
        self.painel_mapa.grid(row=4, column=0, sticky="ew")

        ctk.CTkLabel(self.main, text="3. Opções", font=ctk.CTkFont(size=15, weight="bold")).grid(row=5, column=0, sticky="w", pady=(12, 4))
        op = ctk.CTkFrame(self.main, fg_color="transparent")
        op.grid(row=6, column=0, sticky="ew")
        op.grid_columnconfigure(1, weight=1)
        self.var_ocr = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(op, text="OCR nos PDFs digitalizados (Saneago 2021–2023, DEMAE Panamá, Abadiânia 2021…)",
                        variable=self.var_ocr).grid(row=0, column=0, columnspan=2, sticky="w")
        self.sel_link = SeletorLink(op)
        self.sel_link.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        barra = ctk.CTkFrame(self.main, fg_color="transparent")
        barra.grid(row=7, column=0, sticky="ew", pady=(12, 2))
        barra.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(barra, text="4. Processar", font=ctk.CTkFont(size=15, weight="bold")).grid(row=0, column=0, sticky="w")
        self.btn_processar = ctk.CTkButton(barra, text="▶  Processar faturas de água", height=36, command=self._processar)
        self.btn_processar.grid(row=0, column=1, sticky="e")
        self.progresso = PainelProgresso(self.main, on_cancelar=self._pedir_cancelamento)
        self.progresso.grid(row=8, column=0, sticky="ew", pady=(8, 4))

    def _processar(self):
        if not self.seletor.pastas:
            messagebox.showwarning("Atenção", "Adicione pelo menos uma pasta.")
            return
        modo, template = self.sel_link.config()
        self._iniciar(list(self.seletor.pastas), self.seletor.var_sub.get(), self.var_ocr.get(), modo, template)

    def _concluir(self, lote):
        self.lote = lote
        self.btn_processar.configure(state="normal")
        self.painel_mapa.btn_gerar.configure(state="normal")
        self.resultado_dfs = controller_agua.dataframes(lote)
        self.btn_salvar.configure(state="normal")
        self._relatar(lote)


class AbaAguaConcatenar(_BaseAgua):
    """Adicionar novos PDFs de água a uma planilha de água já existente."""

    NOME_PADRAO = "faturas_agua_atualizada"

    def __init__(self, master):
        super().__init__(master)
        self.base_dfs: dict | None = None
        self.caminho_base: str | None = None
        self._rodape("faturas_agua_atualizada", "💾  Salvar planilha final…")

        self.main = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main.pack(side="top", fill="both", expand=True)
        self.main.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.main, text="1. Planilha base (a que será complementada)", font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, sticky="w", pady=(4, 4))
        linha = ctk.CTkFrame(self.main, fg_color="transparent")
        linha.grid(row=1, column=0, sticky="ew")
        linha.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(linha, text="📂  Selecionar planilha…", width=190, command=self._selecionar_base).grid(row=0, column=0)
        self.lbl_base = ctk.CTkLabel(linha, text="Nenhuma planilha selecionada.", anchor="w", text_color=("gray40", "gray65"))
        self.lbl_base.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        ctk.CTkLabel(self.main, text="2. Pastas com os NOVOS PDFs", font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=2, column=0, sticky="w", pady=(12, 4))
        self.seletor = SeletorPastasAgua(self.main)
        self.seletor.grid(row=3, column=0, sticky="ew")

        op = ctk.CTkFrame(self.main, fg_color="transparent")
        op.grid(row=4, column=0, sticky="ew", pady=(10, 2))
        op.grid_columnconfigure(0, weight=1)
        self.var_ocr = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(op, text="OCR nos PDFs digitalizados", variable=self.var_ocr).grid(row=0, column=0, sticky="w")
        self.sel_link = SeletorLink(op)
        self.sel_link.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ctk.CTkLabel(op, text="3. Processar e concatenar", font=ctk.CTkFont(size=15, weight="bold")).grid(row=2, column=0, sticky="w", pady=(12, 0))
        self.btn_processar = ctk.CTkButton(op, text="▶  Processar e concatenar", height=36, command=self._processar)
        self.btn_processar.grid(row=2, column=1, sticky="e", pady=(12, 0))
        self.progresso = PainelProgresso(self.main, on_cancelar=self._pedir_cancelamento)
        self.progresso.grid(row=5, column=0, sticky="ew", pady=(8, 4))

    def _selecionar_base(self):
        caminho = filedialog.askopenfilename(title="Selecione a planilha base de água", filetypes=[("Planilha Excel", "*.xlsx *.xlsm")])
        if not caminho:
            return
        try:
            dfs = controller_agua.ler_planilha(caminho)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Não foi possível ler a planilha:\n{e}")
            return
        self.base_dfs = {k: v for k, v in dfs.items() if v is not None and not v.empty}
        self.caminho_base = caminho
        self.lbl_base.configure(text=f"{os.path.basename(caminho)} · {len(self.base_dfs)} aba(s).")

    def _processar(self):
        if not self.base_dfs:
            messagebox.showwarning("Atenção", "Selecione a planilha base primeiro.")
            return
        divs = controller_agua.divergencias(self.base_dfs)
        if divs:
            messagebox.showerror("Formatos diferentes", "A planilha base não tem o formato das faturas de água:\n\n" + "\n".join(f"• {d}" for d in divs))
            return
        if not self.seletor.pastas:
            messagebox.showwarning("Atenção", "Adicione pelo menos uma pasta com os novos PDFs.")
            return
        modo, template = self.sel_link.config()
        self._iniciar(list(self.seletor.pastas), self.seletor.var_sub.get(), self.var_ocr.get(), modo, template)

    def _concluir(self, lote):
        self.lote = lote
        self.btn_processar.configure(state="normal")
        novos = controller_agua.dataframes(lote)
        self.resultado_dfs, resumo = controller_agua.concatenar(self.base_dfs, novos)
        self.btn_salvar.configure(state="normal")
        self._relatar(lote)
        for l in resumo:
            self.progresso.escrever(l)

    def _nome_arquivo(self) -> str:
        nome = (self.entry_nome.get() or "").strip()
        if not nome and self.caminho_base:
            nome = os.path.splitext(os.path.basename(self.caminho_base))[0] + "_atualizada"
        nome = nome or self.NOME_PADRAO
        if nome.lower().endswith(".xlsx"):
            nome = nome[:-5]
        return nome + ".xlsx"
