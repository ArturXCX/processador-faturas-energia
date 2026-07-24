"""
Aba 4 — Hardcodes: regras "SE → ENTÃO" que consertam dados errados na ORIGEM
(erro da concessionária ao emitir a fatura, não do processador).

Cada regra é montada visualmente: grupos de condições (parênteses) ligados por E,
condições dentro do grupo ligadas por E ou OU, e uma ou mais ações de atribuição.
As regras ficam salvas no aplicativo (%APPDATA%/FaturasEnergia/hardcodes.json) e
são aplicadas automaticamente ao FINAL de todo processamento de PDFs. Esta aba
também aplica as regras sobre uma planilha já pronta, gerando uma cópia com o
sufixo '_hardcodes'.
"""
from __future__ import annotations

import os
import queue
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..core import hardcodes

_OP_ROTULOS = list(hardcodes.OPERADORES.values())
_OP_POR_ROTULO = {v: k for k, v in hardcodes.OPERADORES.items()}


class LinhaCondicao(ctk.CTkFrame):
    """Uma condição: [coluna] [operador] [valor] [✕]."""

    def __init__(self, master, cond: dict, colunas: list[str], on_remover):
        super().__init__(master, fg_color="transparent")
        self._on_remover = on_remover
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(2, weight=4)

        self.combo_col = ctk.CTkComboBox(self, values=colunas or [""], width=190)
        self.combo_col.set(cond.get("coluna", ""))
        self.combo_col.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.menu_op = ctk.CTkOptionMenu(self, values=_OP_ROTULOS, width=175,
                                         command=lambda _v: self._sincronizar_valor())
        self.menu_op.set(hardcodes.OPERADORES.get(cond.get("operador", "igual"),
                                                  hardcodes.OPERADORES["igual"]))
        self.menu_op.grid(row=0, column=1, sticky="w", padx=(0, 6))

        self.entry_valor = ctk.CTkEntry(self)
        self.entry_valor.insert(0, cond.get("valor", ""))
        self.entry_valor.grid(row=0, column=2, sticky="ew", padx=(0, 6))

        ctk.CTkButton(self, text="✕", width=28, fg_color="transparent", border_width=1,
                      text_color=("gray30", "gray80"),
                      command=lambda: self._on_remover(self)).grid(row=0, column=3)
        self._sincronizar_valor()

    def _sincronizar_valor(self):
        op = _OP_POR_ROTULO.get(self.menu_op.get(), "igual")
        if op in hardcodes.OPERADORES_SEM_VALOR:
            self.entry_valor.delete(0, "end")
            self.entry_valor.configure(state="disabled", placeholder_text="")
        else:
            self.entry_valor.configure(state="normal")
            dica = ("valores separados por ';' — ex.: 30;50;100"
                    if op in hardcodes.OPERADORES_LISTA else "valor")
            self.entry_valor.configure(placeholder_text=dica)

    def atualizar_colunas(self, colunas: list[str]):
        atual = self.combo_col.get()
        self.combo_col.configure(values=colunas or [""])
        self.combo_col.set(atual)

    def dados(self) -> dict:
        op = _OP_POR_ROTULO.get(self.menu_op.get(), "igual")
        valor = "" if op in hardcodes.OPERADORES_SEM_VALOR else self.entry_valor.get()
        return {"coluna": self.combo_col.get().strip(), "operador": op, "valor": valor}


class GrupoCondicoes(ctk.CTkFrame):
    """Um parêntese do SE: várias condições ligadas por E ou OU."""

    def __init__(self, master, grupo: dict, colunas: list[str], on_remover):
        super().__init__(master, fg_color=("gray92", "gray22"), corner_radius=8)
        self._on_remover = on_remover
        self.linhas: list[LinhaCondicao] = []
        self.grid_columnconfigure(0, weight=1)

        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 2))
        topo.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(topo, text="ligar condições por:",
                     font=ctk.CTkFont(size=11),
                     text_color=("gray40", "gray65")).grid(row=0, column=0, sticky="w")
        self.menu_lig = ctk.CTkOptionMenu(topo, values=hardcodes.LIGACOES, width=70)
        self.menu_lig.set(grupo.get("operador", "E"))
        self.menu_lig.grid(row=0, column=1, sticky="w", padx=(6, 0))
        ctk.CTkButton(topo, text="＋ condição", width=100, height=24,
                      font=ctk.CTkFont(size=11),
                      command=self.adicionar).grid(row=0, column=3, padx=(0, 6))
        ctk.CTkButton(topo, text="✕ grupo", width=76, height=24,
                      font=ctk.CTkFont(size=11), fg_color="transparent",
                      border_width=1, text_color=("gray30", "gray80"),
                      command=lambda: self._on_remover(self)).grid(row=0, column=4)

        self.corpo = ctk.CTkFrame(self, fg_color="transparent")
        self.corpo.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.corpo.grid_columnconfigure(0, weight=1)

        self._colunas = colunas
        for cond in grupo.get("condicoes") or [{}]:
            self.adicionar(cond)

    def adicionar(self, cond: dict | None = None):
        linha = LinhaCondicao(self.corpo, cond or {}, self._colunas, self._remover)
        linha.grid(row=len(self.linhas), column=0, sticky="ew", pady=2)
        self.linhas.append(linha)

    def _remover(self, linha: LinhaCondicao):
        linha.destroy()
        self.linhas.remove(linha)
        for i, l in enumerate(self.linhas):
            l.grid_configure(row=i)

    def atualizar_colunas(self, colunas: list[str]):
        self._colunas = colunas
        for l in self.linhas:
            l.atualizar_colunas(colunas)

    def dados(self) -> dict:
        return {"operador": self.menu_lig.get(),
                "condicoes": [l.dados() for l in self.linhas]}


class LinhaAcao(ctk.CTkFrame):
    """Uma atribuição do ENTÃO: [coluna] = [valor] [✕]."""

    def __init__(self, master, acao: dict, colunas: list[str], on_remover):
        super().__init__(master, fg_color="transparent")
        self._on_remover = on_remover
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(2, weight=4)

        self.combo_col = ctk.CTkComboBox(self, values=colunas or [""], width=190)
        self.combo_col.set(acao.get("coluna", ""))
        self.combo_col.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkLabel(self, text="recebe", font=ctk.CTkFont(size=12),
                     text_color=("gray40", "gray65")).grid(row=0, column=1, padx=(0, 6))
        self.entry_valor = ctk.CTkEntry(self, placeholder_text="novo valor (vazio = limpar)")
        self.entry_valor.insert(0, acao.get("valor", ""))
        self.entry_valor.grid(row=0, column=2, sticky="ew", padx=(0, 6))
        ctk.CTkButton(self, text="✕", width=28, fg_color="transparent", border_width=1,
                      text_color=("gray30", "gray80"),
                      command=lambda: self._on_remover(self)).grid(row=0, column=3)

    def atualizar_colunas(self, colunas: list[str]):
        atual = self.combo_col.get()
        self.combo_col.configure(values=colunas or [""])
        self.combo_col.set(atual)

    def dados(self) -> dict:
        return {"coluna": self.combo_col.get().strip(), "valor": self.entry_valor.get()}


class CartaoHardcode(ctk.CTkFrame):
    """Uma regra completa: cabeçalho + grupos do SE + ações do ENTÃO."""

    def __init__(self, master, regra: dict, on_remover):
        super().__init__(master, fg_color=("gray96", "gray17"), corner_radius=10,
                         border_width=1, border_color=("gray82", "gray28"))
        self._on_remover = on_remover
        self._id = regra.get("id", "")
        self.grupos: list[GrupoCondicoes] = []
        self.acoes: list[LinhaAcao] = []
        self.grid_columnconfigure(0, weight=1)

        # ── cabeçalho ────────────────────────────────────────────────────
        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        cab.grid_columnconfigure(1, weight=1)
        self.var_ativo = ctk.BooleanVar(value=regra.get("ativo", True))
        ctk.CTkCheckBox(cab, text="", width=24, variable=self.var_ativo).grid(
            row=0, column=0, padx=(0, 4))
        self.entry_nome = ctk.CTkEntry(cab, placeholder_text="nome do hardcode")
        self.entry_nome.insert(0, regra.get("nome", ""))
        self.entry_nome.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ctk.CTkLabel(cab, text="Aba:").grid(row=0, column=2, padx=(0, 4))
        self.menu_aba = ctk.CTkOptionMenu(cab, values=hardcodes.abas_disponiveis(),
                                          width=170, command=self._mudou_aba)
        aba = regra.get("aba") or hardcodes.abas_disponiveis()[0]
        if aba not in hardcodes.abas_disponiveis():
            self.menu_aba.configure(values=hardcodes.abas_disponiveis() + [aba])
        self.menu_aba.set(aba)
        self.menu_aba.grid(row=0, column=3, padx=(0, 8))
        ctk.CTkButton(cab, text="🗑 Excluir", width=88, fg_color="transparent",
                      border_width=1, text_color=("#a4262c", "#ff7b72"),
                      command=lambda: self._on_remover(self)).grid(row=0, column=4)

        # ── SE ───────────────────────────────────────────────────────────
        se = ctk.CTkFrame(self, fg_color="transparent")
        se.grid(row=1, column=0, sticky="ew", padx=10)
        se.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(se, text="SE", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, sticky="w")
        ctk.CTkLabel(se, text="(grupos ligados por E)", font=ctk.CTkFont(size=11),
                     text_color=("gray45", "gray60")).grid(row=0, column=1, sticky="w",
                                                           padx=(6, 0))
        ctk.CTkButton(se, text="＋ grupo", width=88, height=26,
                      font=ctk.CTkFont(size=11),
                      command=self._add_grupo).grid(row=0, column=2, sticky="e")

        self.cont_grupos = ctk.CTkFrame(self, fg_color="transparent")
        self.cont_grupos.grid(row=2, column=0, sticky="ew", padx=10, pady=(2, 6))
        self.cont_grupos.grid_columnconfigure(0, weight=1)

        # ── ENTÃO ────────────────────────────────────────────────────────
        ent = ctk.CTkFrame(self, fg_color="transparent")
        ent.grid(row=3, column=0, sticky="ew", padx=10)
        ent.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(ent, text="ENTÃO", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, sticky="w")
        ctk.CTkButton(ent, text="＋ ação", width=88, height=26,
                      font=ctk.CTkFont(size=11),
                      command=self._add_acao).grid(row=0, column=2, sticky="e")

        self.cont_acoes = ctk.CTkFrame(self, fg_color="transparent")
        self.cont_acoes.grid(row=4, column=0, sticky="ew", padx=10, pady=(2, 10))
        self.cont_acoes.grid_columnconfigure(0, weight=1)

        for g in regra.get("grupos") or [{}]:
            self._add_grupo(g)
        for a in regra.get("acoes") or [{}]:
            self._add_acao(a)

    # ── colunas sugeridas conforme a aba escolhida ───────────────────────
    def _colunas(self) -> list[str]:
        return hardcodes.colunas_da_aba(self.menu_aba.get())

    def _mudou_aba(self, _v=None):
        cols = self._colunas()
        for g in self.grupos:
            g.atualizar_colunas(cols)
        for a in self.acoes:
            a.atualizar_colunas(cols)

    # ── grupos ───────────────────────────────────────────────────────────
    def _add_grupo(self, grupo: dict | None = None):
        g = GrupoCondicoes(self.cont_grupos, grupo if isinstance(grupo, dict) else {},
                           self._colunas(), self._remover_grupo)
        g.grid(row=len(self.grupos) * 2, column=0, sticky="ew", pady=(0, 2))
        self.grupos.append(g)
        self._redesenhar_ligacoes()

    def _remover_grupo(self, grupo: GrupoCondicoes):
        if len(self.grupos) == 1:
            messagebox.showinfo("Hardcodes", "A regra precisa de ao menos um grupo.")
            return
        grupo.destroy()
        self.grupos.remove(grupo)
        self._redesenhar_ligacoes()

    def _redesenhar_ligacoes(self):
        """Reposiciona os grupos e desenha o 'E' que os liga."""
        for w in self.cont_grupos.grid_slaves():
            if isinstance(w, ctk.CTkLabel):
                w.destroy()
        for i, g in enumerate(self.grupos):
            g.grid_configure(row=i * 2)
            if i:
                ctk.CTkLabel(self.cont_grupos, text="E",
                             font=ctk.CTkFont(size=12, weight="bold"),
                             text_color=("gray35", "gray70")).grid(
                    row=i * 2 - 1, column=0, sticky="w", padx=8, pady=1)

    # ── ações ────────────────────────────────────────────────────────────
    def _add_acao(self, acao: dict | None = None):
        a = LinhaAcao(self.cont_acoes, acao if isinstance(acao, dict) else {},
                      self._colunas(), self._remover_acao)
        a.grid(row=len(self.acoes), column=0, sticky="ew", pady=2)
        self.acoes.append(a)

    def _remover_acao(self, acao: LinhaAcao):
        if len(self.acoes) == 1:
            messagebox.showinfo("Hardcodes", "A regra precisa de ao menos uma ação.")
            return
        acao.destroy()
        self.acoes.remove(acao)
        for i, a in enumerate(self.acoes):
            a.grid_configure(row=i)

    def dados(self) -> dict:
        return {
            "id": self._id,
            "nome": self.entry_nome.get().strip(),
            "aba": self.menu_aba.get(),
            "ativo": bool(self.var_ativo.get()),
            "grupos": [g.dados() for g in self.grupos],
            "acoes": [a.dados() for a in self.acoes],
        }


class AbaHardcodes(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.cartoes: list[CartaoHardcode] = []
        self._fila: queue.Queue = queue.Queue()

        # ── rodapé fixo (ações) ──────────────────────────────────────────
        rod = ctk.CTkFrame(self, fg_color="transparent")
        rod.pack(side="bottom", fill="x", pady=(8, 2))
        rod.grid_columnconfigure(0, weight=1)
        self.lbl_status = ctk.CTkLabel(rod, text="", anchor="w", justify="left",
                                       text_color=("gray35", "gray70"))
        self.lbl_status.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        self.btn_planilha = ctk.CTkButton(
            rod, text="📂  Aplicar sobre uma planilha…", width=230,
            command=self._aplicar_planilha)
        self.btn_planilha.grid(row=1, column=0, sticky="w")
        ctk.CTkButton(rod, text="➕  Novo hardcode", command=self._novo).grid(
            row=1, column=1, padx=(8, 8))
        ctk.CTkButton(rod, text="💾  Salvar hardcodes", height=36,
                      command=self._salvar).grid(row=1, column=2)

        # ── cabeçalho ────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(side="top", fill="x")
        ctk.CTkLabel(top, text="Hardcodes (correções de erro da concessionária)",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", pady=(2, 2))
        ctk.CTkLabel(
            top, justify="left", text_color=("gray40", "gray65"), wraplength=900,
            text=("Regras “SE → ENTÃO” aplicadas ao FINAL de todo processamento de PDFs, "
                  "para consertar dados que já vieram errados na fatura emitida. Dentro de "
                  "cada grupo as condições se ligam por E ou OU; os grupos entre si se "
                  "ligam sempre por E — ex.: SE (item = CONSUMO KWH) E (quantidade não é "
                  "nenhum de 30;50;100) ENTÃO item recebe CONSUMO. As regras ficam salvas "
                  "no aplicativo até serem excluídas.")).pack(anchor="w")

        # ── lista rolável de regras ──────────────────────────────────────
        self.lista = ctk.CTkScrollableFrame(self, fg_color=("gray94", "gray13"))
        self.lista.pack(side="top", fill="both", expand=True, pady=(8, 0))
        self.lista.grid_columnconfigure(0, weight=1)

        self._carregar()

    # ── carga / edição ───────────────────────────────────────────────────
    def _carregar(self):
        regras = hardcodes.carregar()
        for r in regras:
            self._add_cartao(r)
        self.lbl_status.configure(text=f"{len(regras)} hardcode(s) cadastrado(s).")

    def _add_cartao(self, regra: dict):
        c = CartaoHardcode(self.lista, regra, self._remover)
        c.grid(row=len(self.cartoes), column=0, sticky="ew", padx=6, pady=6)
        self.cartoes.append(c)
        return c

    def _novo(self):
        c = self._add_cartao(hardcodes.regra_vazia())
        self.after(50, lambda: self.lista._parent_canvas.yview_moveto(1.0))
        return c

    def _remover(self, cartao: CartaoHardcode):
        nome = cartao.entry_nome.get().strip() or "(sem nome)"
        if not messagebox.askyesno("Excluir hardcode",
                                   f"Excluir o hardcode “{nome}”?\n\n"
                                   "A exclusão só vale depois de salvar."):
            return
        cartao.destroy()
        self.cartoes.remove(cartao)
        for i, c in enumerate(self.cartoes):
            c.grid_configure(row=i)

    def _regras(self) -> list[dict]:
        return [c.dados() for c in self.cartoes]

    def _salvar(self):
        regras = self._regras()
        incompletas = [r["nome"] or "(sem nome)" for r in regras
                       if hardcodes.resumo_texto(r) == "(regra incompleta)"]
        if incompletas:
            messagebox.showwarning(
                "Hardcodes incompletos",
                "Estes hardcodes estão sem condição ou sem ação e não terão efeito:\n\n"
                + "\n".join(f"• {n}" for n in incompletas))
        try:
            hardcodes.salvar(regras)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Não foi possível salvar os hardcodes:\n{e}")
            return
        self.lbl_status.configure(text=f"✅ {len(regras)} hardcode(s) salvo(s).")

    # ── aplicar sobre uma planilha existente ─────────────────────────────
    def _aplicar_planilha(self):
        entrada = filedialog.askopenfilename(
            title="Selecione a planilha sobre a qual aplicar os hardcodes",
            filetypes=[("Planilha Excel", "*.xlsx *.xlsm")])
        if not entrada:
            return
        sugerido = os.path.basename(hardcodes.caminho_saida_padrao(entrada))
        saida = filedialog.asksaveasfilename(
            title="Salvar planilha com os hardcodes aplicados",
            defaultextension=".xlsx", initialfile=sugerido,
            initialdir=os.path.dirname(entrada),
            filetypes=[("Planilha Excel", "*.xlsx")])
        if not saida:
            return
        if os.path.abspath(saida) == os.path.abspath(entrada):
            messagebox.showwarning(
                "Atenção", "Escolha um arquivo de saída diferente da planilha de origem.")
            return

        # Usa as regras da TELA (inclusive edições ainda não salvas).
        regras = self._regras()
        self.btn_planilha.configure(state="disabled")
        self.lbl_status.configure(text="⏳ Aplicando hardcodes na planilha… (pode demorar)")

        def tarefa():
            try:
                rel = hardcodes.aplicar_planilha(entrada, saida, regras)
                self._fila.put(("ok", rel))
            except Exception as e:  # noqa: BLE001
                self._fila.put(("erro", e))

        threading.Thread(target=tarefa, daemon=True).start()
        self.after(200, lambda: self._poll(saida))

    def _poll(self, saida: str):
        try:
            tipo, payload = self._fila.get_nowait()
        except queue.Empty:
            self.after(200, lambda: self._poll(saida))
            return
        self.btn_planilha.configure(state="normal")
        if tipo == "erro":
            self.lbl_status.configure(text="⚠ Falha ao aplicar os hardcodes.")
            messagebox.showerror("Erro", f"Falha ao aplicar os hardcodes:\n{payload}")
            return
        self.lbl_status.configure(text="✅ Planilha gerada.\n" + "\n".join(payload))
        if messagebox.askyesno("Pronto",
                               f"Planilha salva em:\n{saida}\n\n"
                               + "\n".join(payload) + "\n\nDeseja abrir agora?"):
            try:
                os.startfile(saida)  # type: ignore[attr-defined]
            except Exception:
                pass
