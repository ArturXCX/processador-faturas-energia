"""
Aba 3 — Parâmetros do sistema.

Duas seções independentes:

  1. **Tabela de equivalências de itens** — tabela editável (criar/editar/
     excluir) com as colunas 'item' e 'item_normalizado', salva dentro do
     sistema (%APPDATA%/FaturasEnergia/). Preenche a coluna `item_normalizado`
     da aba `itens_fatura`: se o item existir aqui, usa o valor normalizado;
     senão, mantém o próprio item.
  2. **Dicionário de Unidades Consumidoras** — cadastro oficial das UCs
     (core/dicionario_uc.py). Diferente da tabela acima, não é editável linha a
     linha: é mantido pela fonte oficial e só precisa ser REIMPORTADO quando
     atualizado (UC nova, medidor trocado, unidade judiciária renomeada), sem
     exigir um build novo do aplicativo.
"""
from __future__ import annotations

import json
import os
import queue
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..core import dicionario_uc, equivalencias


class AbaParametros(ctk.CTkFrame):
    _ROTULO_DIC = "Com dicionário (JSON)"
    _ROTULO_MED = "Sem dicionário (pelo medidor)"

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.linhas: list[tuple] = []   # (frame, entry_item, entry_norm)
        self._fila: queue.Queue = queue.Queue()

        # rodapé fixo (ações)
        rod = ctk.CTkFrame(self, fg_color="transparent")
        rod.pack(side="bottom", fill="x", pady=(8, 2))
        rod.grid_columnconfigure(0, weight=1)
        self.lbl_status = ctk.CTkLabel(rod, text="", anchor="w", justify="left",
                                       text_color=("gray35", "gray70"))
        self.lbl_status.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 6))
        self.btn_normalizar = ctk.CTkButton(
            rod, text="📂  Aplicar normalização sobre uma planilha…", width=280,
            command=self._aplicar_planilha)
        self.btn_normalizar.grid(row=1, column=0, sticky="w")
        ctk.CTkButton(rod, text="⇩  Importar equivalências", command=self._importar).grid(
            row=1, column=1, padx=(8, 8))
        ctk.CTkButton(rod, text="➕  Adicionar equivalência", command=self._add_linha).grid(
            row=1, column=2, padx=(0, 8))
        ctk.CTkButton(rod, text="💾  Salvar tabela", height=36, command=self._salvar).grid(
            row=1, column=3)

        # ── Dicionário de Unidades Consumidoras (seção própria, acima) ──────
        dic = ctk.CTkFrame(self, fg_color=("gray92", "gray17"))
        dic.pack(side="top", fill="x", pady=(2, 10))
        dic.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(dic, text="Dicionário de Unidades Consumidoras",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 2))
        ctk.CTkLabel(dic, justify="left", text_color=("gray40", "gray65"), wraplength=560,
                     text=("Como as Unidades Consumidoras são identificadas e de onde vêm "
                           "os dados de cadastro. Escolha 'Sem dicionário' se a sua "
                           "instituição não tem um arquivo de cadastro oficial.")).grid(
            row=1, column=0, sticky="w", padx=10)

        self.opt_metodo = ctk.CTkSegmentedButton(
            dic, values=[self._ROTULO_DIC, self._ROTULO_MED],
            command=self._trocar_metodo)
        self.opt_metodo.grid(row=2, column=0, sticky="w", padx=10, pady=(8, 2))
        self.opt_metodo.set(self._ROTULO_DIC if dicionario_uc.ativo() else self._ROTULO_MED)

        self.lbl_metodo = ctk.CTkLabel(dic, anchor="w", justify="left", wraplength=560,
                                       text_color=("gray40", "gray65"))
        self.lbl_metodo.grid(row=3, column=0, sticky="w", padx=10)
        self.lbl_dicionario = ctk.CTkLabel(dic, anchor="w", justify="left",
                                           text_color=("gray35", "gray70"))
        self.lbl_dicionario.grid(row=4, column=0, sticky="w", padx=10, pady=(6, 10))
        self.btn_importar_dic = ctk.CTkButton(
            dic, text="⇩  Importar novo dicionário (.json)", width=260,
            command=self._importar_dicionario)
        self.btn_importar_dic.grid(row=2, column=1, rowspan=3, padx=10, pady=(0, 10))
        self._atualizar_label_dicionario()

        # cabeçalho / explicação
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(side="top", fill="x")
        ctk.CTkLabel(top, text="Tabela de equivalências de itens",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", pady=(2, 2))
        ctk.CTkLabel(top, justify="left", text_color=("gray40", "gray65"), wraplength=760,
                     text=("Na aba 'itens_fatura', a coluna 'item_normalizado' recebe o valor "
                           "abaixo quando o 'item' estiver listado aqui; caso contrário, fica "
                           "igual ao próprio 'item'. A tabela fica salva no aplicativo.")).pack(
            anchor="w")

        # grade rolável
        self.lista = ctk.CTkScrollableFrame(self, fg_color=("gray96", "gray14"))
        self.lista.pack(side="top", fill="both", expand=True, pady=(8, 0))
        self.lista.grid_columnconfigure(0, weight=1)
        self.lista.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.lista, text="item", font=ctk.CTkFont(size=11, weight="bold"),
                     anchor="w").grid(row=0, column=0, sticky="w", padx=6, pady=(2, 4))
        ctk.CTkLabel(self.lista, text="item_normalizado", font=ctk.CTkFont(size=11, weight="bold"),
                     anchor="w").grid(row=0, column=1, sticky="w", padx=6, pady=(2, 4))

        self._carregar()

    def _carregar(self):
        for l in equivalencias.carregar():
            self._add_linha(l.get("item", ""), l.get("item_normalizado", ""))
        if not self.linhas:
            self._add_linha()

    def _add_linha(self, item="", norm=""):
        i = len(self.linhas) + 1
        frame = ctk.CTkFrame(self.lista, fg_color="transparent")
        frame.grid(row=i, column=0, columnspan=3, sticky="ew", pady=2)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        e_item = ctk.CTkEntry(frame)
        e_item.insert(0, item or "")
        e_item.grid(row=0, column=0, sticky="ew", padx=(4, 4))
        e_norm = ctk.CTkEntry(frame)
        e_norm.insert(0, norm or "")
        e_norm.grid(row=0, column=1, sticky="ew", padx=(4, 4))
        reg = (frame, e_item, e_norm)
        ctk.CTkButton(frame, text="✕", width=30, fg_color="transparent", border_width=1,
                      text_color=("gray30", "gray80"),
                      command=lambda: self._remover(reg)).grid(row=0, column=2, padx=(0, 4))
        self.linhas.append(reg)

    def _remover(self, reg):
        frame, _, _ = reg
        frame.destroy()
        if reg in self.linhas:
            self.linhas.remove(reg)

    def _salvar(self):
        dados = []
        for _frame, e_item, e_norm in self.linhas:
            item = e_item.get().strip()
            if not item:
                continue
            dados.append({"item": item, "item_normalizado": e_norm.get().strip()})
        try:
            equivalencias.salvar(dados)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Não foi possível salvar as equivalências:\n{e}")
            return
        self.lbl_status.configure(text=f"✅ {len(dados)} equivalência(s) salva(s).")

    # ── dicionário de Unidades Consumidoras ──────────────────────────────
    def _trocar_metodo(self, rotulo):
        novo = (dicionario_uc.MODO_DICIONARIO if rotulo == self._ROTULO_DIC
                else dicionario_uc.MODO_MEDIDOR)
        try:
            dicionario_uc.definir_modo(novo)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Não foi possível salvar a escolha:\n{e}")
            return
        self._atualizar_label_dicionario()
        self.lbl_status.configure(
            text=f"✅ Metodologia de identificação de UC: {rotulo}.")

    def _atualizar_label_dicionario(self):
        usando = dicionario_uc.ativo()
        self.lbl_metodo.configure(text=(
            "As colunas de cadastro (unidade judiciária, comarca, endereço, medidor "
            "atual, rateios) vêm do dicionário, e 'id_uc_canonico' usa a UC oficial — "
            "o que une o histórico da mesma UC mesmo quando o número muda de formato."
            if usando else
            "Nada vem de cadastro externo: os dados da UC saem dos próprios PDFs e a "
            "correspondência entre faturas da mesma UC é feita pelo MEDIDOR. "
            "'id_uc_canonico' recebe esse valor e as colunas do dicionário não são "
            "criadas na planilha."))
        # O bloco do dicionário só faz sentido na metodologia com JSON.
        self.btn_importar_dic.configure(state="normal" if usando else "disabled")
        if not usando:
            self.lbl_dicionario.configure(
                text="📖  Dicionário desativado nesta metodologia.")
            return
        try:
            m = dicionario_uc.metadados()
        except Exception as e:  # noqa: BLE001
            self.lbl_dicionario.configure(text=f"⚠ Não foi possível ler o dicionário: {e}")
            return
        fonte = ("arquivo importado" if m["fonte"] == "usuario"
                 else "versão embutida no aplicativo")
        texto = (f"📖  {m['total_ucs']} UC(s) cadastrada(s) · {m['operantes']} operante(s) "
                 f"· fonte: {fonte}")
        avisos = dicionario_uc.avisos()
        if avisos:
            texto += f"\n⚠  {len(avisos)} aviso(s) na carga: {avisos[0]}"
        self.lbl_dicionario.configure(text=texto)

    def _importar_dicionario(self):
        caminho = filedialog.askopenfilename(
            title="Selecione o dicionário de Unidades Consumidoras (.json)",
            filetypes=[("Arquivo JSON", "*.json")])
        if not caminho:
            return
        # `analisar` lê e INTERPRETA sem gravar nada: é ele que casa os nomes de
        # campo do arquivo com os campos conhecidos (um cadastro de outra
        # instituição não usa os rótulos do TJGO) e devolve o relatório do que
        # entendeu. O usuário confere ANTES de substituir o cadastro atual.
        try:
            registros, relatorio = dicionario_uc.analisar(caminho)
        except ValueError as e:
            messagebox.showerror("Arquivo inválido",
                                 f"O arquivo não é um cadastro de UCs válido:\n\n{e}")
            return
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Não foi possível ler o arquivo:\n{e}")
            return

        atual = dicionario_uc.metadados()
        if not messagebox.askyesno(
                "Importar dicionário de UCs",
                "\n".join(relatorio)
                + f"\n\nCadastro atual: {atual['total_ucs']} UC(s)."
                + f"\nArquivo selecionado: {len(registros)} UC(s)."
                + "\n\nO cadastro atual será substituído. Prosseguir?"):
            return
        try:
            m = dicionario_uc.importar(caminho)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Não foi possível importar o dicionário:\n{e}")
            return
        # Importar um cadastro já liga a metodologia por dicionário (é o que a
        # pessoa quis dizer ao importar), então o seletor precisa acompanhar.
        self.opt_metodo.set(self._ROTULO_DIC if dicionario_uc.ativo() else self._ROTULO_MED)
        self._atualizar_label_dicionario()
        self.lbl_status.configure(
            text=f"✅ Dicionário importado: {m['total_ucs']} UC(s) cadastrada(s).")

    # ── importar de um arquivo Excel/CSV ─────────────────────────────────
    def _importar(self):
        caminho = filedialog.askopenfilename(
            title="Selecione a planilha ou CSV de equivalências",
            filetypes=[("Planilha ou CSV", "*.xlsx *.xlsm *.csv")])
        if not caminho:
            return
        try:
            linhas = equivalencias.ler_arquivo_importacao(caminho)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Não foi possível importar o arquivo:\n{e}")
            return
        if not linhas:
            messagebox.showwarning("Atenção", "Nenhuma equivalência válida encontrada no arquivo.")
            return
        if not messagebox.askyesno(
                "Importar equivalências",
                f"{len(linhas)} equivalência(s) serão importadas.\n\n"
                "Deseja prosseguir com a importação?"):
            return

        existentes = {}
        for frame, e_item, e_norm in self.linhas:
            item = e_item.get().strip()
            if item:
                existentes[item.upper()] = e_norm

        novas = atualizadas = 0
        for l in linhas:
            chave = l["item"].upper()
            if chave in existentes:
                e_norm = existentes[chave]
                e_norm.delete(0, "end")
                e_norm.insert(0, l["item_normalizado"])
                atualizadas += 1
            else:
                self._add_linha(l["item"], l["item_normalizado"])
                novas += 1

        self._salvar()
        self.lbl_status.configure(
            text=f"✅ Importação concluída: {novas} nova(s), {atualizadas} atualizada(s).")

    # ── aplicar sobre uma planilha existente ─────────────────────────────
    def _aplicar_planilha(self):
        entrada = filedialog.askopenfilename(
            title="Selecione a planilha sobre a qual aplicar a normalização",
            filetypes=[("Planilha Excel", "*.xlsx *.xlsm")])
        if not entrada:
            return
        sugerido = os.path.basename(equivalencias.caminho_saida_padrao(entrada))
        saida = filedialog.asksaveasfilename(
            title="Salvar planilha com a normalização aplicada",
            defaultextension=".xlsx", initialfile=sugerido,
            initialdir=os.path.dirname(entrada),
            filetypes=[("Planilha Excel", "*.xlsx")])
        if not saida:
            return
        if os.path.abspath(saida) == os.path.abspath(entrada):
            messagebox.showwarning(
                "Atenção", "Escolha um arquivo de saída diferente da planilha de origem.")
            return

        self.btn_normalizar.configure(state="disabled")
        self.lbl_status.configure(text="⏳ Aplicando normalização na planilha… (pode demorar)")

        def tarefa():
            try:
                rel = equivalencias.aplicar_planilha(entrada, saida)
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
        self.btn_normalizar.configure(state="normal")
        if tipo == "erro":
            self.lbl_status.configure(text="⚠ Falha ao aplicar a normalização.")
            messagebox.showerror("Erro", f"Falha ao aplicar a normalização:\n{payload}")
            return
        # Sem pop-up de "deseja abrir agora?": o caminho e o resumo já ficam
        # visíveis no rótulo de status da própria tela.
        self.lbl_status.configure(
            text="✅ Planilha gerada em: " + str(saida) + "\n" + "\n".join(payload))
