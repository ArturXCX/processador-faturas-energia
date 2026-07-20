"""Widgets reutilizáveis da interface."""
from __future__ import annotations

import os
from tkinter import filedialog

import customtkinter as ctk

from ..core.controller import Job, listar_pdfs
from ..core import links

FORNECEDORES = ["EQUATORIAL", "CHESP"]

_LINK_OPCOES = {
    "Caminho local (sem link)": links.MODO_LOCAL,
    "Link de busca no Drive": links.MODO_BUSCA,
    "Modelo de URL personalizado": links.MODO_TEMPLATE,
}
_LINK_OPCOES_REV = {v: k for k, v in _LINK_OPCOES.items()}


class LinhaPasta(ctk.CTkFrame):
    """Uma pasta selecionada: caminho + fornecedora + contagem + remover."""

    def __init__(self, master, caminho: str, on_remover, **kw):
        super().__init__(master, fg_color=("gray92", "gray20"), corner_radius=8, **kw)
        self.caminho = caminho
        self._on_remover = on_remover

        self.grid_columnconfigure(0, weight=1)

        n = len(listar_pdfs(caminho))
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.grid(row=0, column=0, columnspan=4, sticky="ew", padx=10, pady=(8, 0))
        topo.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(topo, text=os.path.basename(caminho) or caminho,
                     font=ctk.CTkFont(size=13, weight="bold"), anchor="w").grid(
            row=0, column=0, sticky="ew")
        self.lbl_contagem = ctk.CTkLabel(topo, text=f"{n} PDF(s)",
                                         text_color=("gray40", "gray60"))
        self.lbl_contagem.grid(row=0, column=1, sticky="e", padx=(8, 0))

        ctk.CTkLabel(self, text=caminho, text_color=("gray45", "gray60"),
                     anchor="w", font=ctk.CTkFont(size=11)).grid(
            row=1, column=0, columnspan=4, sticky="ew", padx=10)

        baixo = ctk.CTkFrame(self, fg_color="transparent")
        baixo.grid(row=2, column=0, columnspan=4, sticky="ew", padx=10, pady=(2, 8))
        ctk.CTkLabel(baixo, text="Fornecedora:").pack(side="left")
        self.combo = ctk.CTkOptionMenu(baixo, values=FORNECEDORES, width=160)
        self.combo.pack(side="left", padx=(8, 0))
        ctk.CTkButton(baixo, text="Remover", width=80, fg_color="transparent",
                      border_width=1, text_color=("gray30", "gray80"),
                      command=lambda: self._on_remover(self)).pack(side="right")

    def job(self, incluir_subpastas: bool) -> Job:
        return Job(pasta=self.caminho, fornecedor=self.combo.get(),
                   incluir_subpastas=incluir_subpastas)


class SeletorPastas(ctk.CTkFrame):
    """Lista de pastas (cada uma com fornecedora) + botão adicionar."""

    def __init__(self, master, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.linhas: list[LinhaPasta] = []

        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        barra.grid_columnconfigure(0, weight=1)
        self.var_sub = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(barra, text="Incluir subpastas", variable=self.var_sub).grid(
            row=0, column=0, sticky="w")
        ctk.CTkButton(barra, text="➕  Adicionar pasta", command=self.adicionar).grid(
            row=0, column=1, sticky="e")

        self.lista = ctk.CTkScrollableFrame(self, fg_color=("gray96", "gray14"),
                                            label_text="")
        self.lista.grid(row=1, column=0, sticky="nsew")
        self.lista.grid_columnconfigure(0, weight=1)

        self.vazio = ctk.CTkLabel(self.lista,
                                  text="Nenhuma pasta adicionada.\nClique em “Adicionar pasta”.",
                                  text_color=("gray50", "gray55"))
        self.vazio.grid(row=0, column=0, pady=30)

    def adicionar(self):
        caminho = filedialog.askdirectory(title="Selecione uma pasta com PDFs")
        if not caminho:
            return
        if any(l.caminho == caminho for l in self.linhas):
            return
        self.vazio.grid_remove()
        linha = LinhaPasta(self.lista, caminho, on_remover=self._remover)
        linha.grid(row=len(self.linhas), column=0, sticky="ew", pady=4, padx=4)
        self.linhas.append(linha)

    def _remover(self, linha: LinhaPasta):
        linha.destroy()
        self.linhas.remove(linha)
        for i, l in enumerate(self.linhas):
            l.grid_configure(row=i)
        if not self.linhas:
            self.vazio.grid()

    def jobs(self) -> list[Job]:
        return [l.job(self.var_sub.get()) for l in self.linhas]

    def total_pdfs(self) -> int:
        from ..core.controller import contar_pdfs
        return contar_pdfs(self.jobs())


class PainelProgresso(ctk.CTkFrame):
    """Barra de progresso + status + log + botão cancelar."""

    def __init__(self, master, on_cancelar=None, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._on_cancelar = on_cancelar
        self.grid_columnconfigure(0, weight=1)

        linha = ctk.CTkFrame(self, fg_color="transparent")
        linha.grid(row=0, column=0, sticky="ew")
        linha.grid_columnconfigure(0, weight=1)
        self.barra = ctk.CTkProgressBar(linha)
        self.barra.set(0)
        self.barra.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.btn_cancelar = ctk.CTkButton(linha, text="Cancelar", width=90,
                                          fg_color="transparent", border_width=1,
                                          text_color=("gray30", "gray80"),
                                          command=self._cancelar)
        self.btn_cancelar.grid(row=0, column=1)

        self.lbl_status = ctk.CTkLabel(self, text="", anchor="w",
                                       text_color=("gray35", "gray70"))
        self.lbl_status.grid(row=1, column=0, sticky="ew", pady=(4, 2))

        self.log = ctk.CTkTextbox(self, height=72, font=ctk.CTkFont(size=11))
        self.log.grid(row=2, column=0, sticky="nsew")
        self.log.configure(state="disabled")

    def _cancelar(self):
        if self._on_cancelar:
            self._on_cancelar()

    def resetar(self, status=""):
        self.barra.set(0)
        self.lbl_status.configure(text=status)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def progresso(self, feito: int, total: int, status: str):
        self.barra.set((feito / total) if total else 0)
        self.lbl_status.configure(text=status)

    def escrever(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def habilitar_cancelar(self, valor: bool):
        self.btn_cancelar.configure(state="normal" if valor else "disabled")


class SeletorLink(ctk.CTkFrame):
    """Escolhe como preencher a coluna `link_pdf` (caminho local / busca Drive / modelo)."""

    def __init__(self, master, modo_inicial=links.MODO_BUSCA, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(self, text="Link do PDF:").grid(row=0, column=0, sticky="w")
        self.combo = ctk.CTkOptionMenu(self, values=list(_LINK_OPCOES.keys()),
                                       width=220, command=self._mudou)
        self.combo.set(_LINK_OPCOES_REV.get(modo_inicial, "Link de busca no Drive"))
        self.combo.grid(row=0, column=1, sticky="w", padx=(8, 8))

        self.entry = ctk.CTkEntry(self, placeholder_text=links.TEMPLATE_EXEMPLO)
        self.entry.insert(0, links.TEMPLATE_EXEMPLO)
        self.entry.grid(row=0, column=2, sticky="ew")

        self.hint = ctk.CTkLabel(self, text="Use {arquivo} ou {arquivo_sem_ext} no modelo.",
                                 text_color=("gray45", "gray60"),
                                 font=ctk.CTkFont(size=11))
        self.hint.grid(row=1, column=2, sticky="w", pady=(2, 0))
        self._mudou(self.combo.get())

    def _mudou(self, _val):
        eh_template = (_LINK_OPCOES.get(self.combo.get()) == links.MODO_TEMPLATE)
        estado = "normal" if eh_template else "disabled"
        self.entry.configure(state=estado)
        self.hint.grid() if eh_template else self.hint.grid_remove()

    def config(self) -> tuple[str, str | None]:
        """Devolve (modo, template) conforme a seleção atual."""
        modo = _LINK_OPCOES.get(self.combo.get(), links.MODO_BUSCA)
        template = self.entry.get().strip() if modo == links.MODO_TEMPLATE else None
        return modo, template
