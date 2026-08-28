"""
Aba 3 — Parâmetros do sistema.

Duas seções independentes:

  1. **Tabela de equivalências de itens** — tabela editável (criar/editar/
     excluir) com as colunas 'item' e 'item_normalizado', salva dentro do
     sistema (%APPDATA%/FaturasEnergia/). Preenche a coluna `item_normalizado`
     da aba `itens_fatura`: se o item existir aqui, usa o valor normalizado;
     senão, mantém o próprio item.
  2. **Mapa de Unidades Consumidoras** — cadastro das UCs, importado pelo
     usuário (core/dicionario_uc.py). O app não embarca nenhum: gera um
     TEMPLATE, o usuário preenche (JSON ou planilha), importa, e a tela de
     mapeamento resolve os nomes que não batem com o template. Sem mapa, nada
     do template entra na planilha.

Tudo aqui é persistido em JSON e pode ser editado de dentro do app; ao salvar,
o JSON é regravado com as alterações.
"""
from __future__ import annotations

import json
import os
import queue
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..core import dicionario_uc, equivalencias
from .editor_json import EditorJson
from .mapa_uc_dialog import DialogoMapaUC


class AbaParametros(ctk.CTkFrame):
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
            rod, text="📂  Aplicar sobre uma planilha…", width=210,
            command=self._aplicar_planilha)
        self.btn_normalizar.grid(row=1, column=0, sticky="w")
        ctk.CTkButton(rod, text="⇩  Importar", width=110, command=self._importar).grid(
            row=1, column=1, padx=(8, 4))
        ctk.CTkButton(rod, text="⇧  Exportar JSON", width=140,
                      command=self._exportar_equivalencias).grid(row=1, column=2, padx=(0, 4))
        ctk.CTkButton(rod, text="✎  Editar JSON", width=130,
                      command=self._editar_equivalencias).grid(row=1, column=3, padx=(0, 4))
        ctk.CTkButton(rod, text="➕  Adicionar", width=110, command=self._add_linha).grid(
            row=1, column=4, padx=(0, 8))
        ctk.CTkButton(rod, text="💾  Salvar tabela", height=36, command=self._salvar).grid(
            row=1, column=5)

        # ── Mapa de Unidades Consumidoras (seção própria, acima) ───────────
        dic = ctk.CTkFrame(self, fg_color=("gray92", "gray17"))
        dic.pack(side="top", fill="x", pady=(2, 10))
        dic.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(dic, text="Mapa de Unidades Consumidoras",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 2))
        ctk.CTkLabel(dic, justify="left", text_color=("gray40", "gray65"), wraplength=560,
                     text=("Cadastro das UCs da sua instituição. Gere o modelo, preencha "
                           "(JSON ou planilha) e importe — os nomes que não baterem com o "
                           "modelo você resolve na tela de mapeamento. Sem mapa, nenhuma "
                           "coluna de cadastro entra na planilha.")).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=10)

        self.lbl_dicionario = ctk.CTkLabel(dic, anchor="w", justify="left",
                                           wraplength=760,
                                           text_color=("gray35", "gray70"))
        self.lbl_dicionario.grid(row=2, column=0, columnspan=2, sticky="w",
                                 padx=10, pady=(8, 4))

        self.chk_medidor = ctk.CTkCheckBox(
            dic, text="Identificação histórica por medidor",
            command=self._trocar_medidor)
        self.chk_medidor.grid(row=3, column=0, sticky="w", padx=10, pady=(0, 2))
        ctk.CTkLabel(dic, wraplength=560, justify="left", anchor="w",
                     font=ctk.CTkFont(size=11), text_color=("gray45", "gray60"),
                     text=("Desmarcado (só possível com mapa), as colunas "
                           "'id_uc_atual_medidor', 'id_uc_atual_medidor_sem_format' e "
                           "'id_uc_atual' não são criadas em nenhuma aba.")).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=32, pady=(0, 8))

        botoes = ctk.CTkFrame(dic, fg_color="transparent")
        botoes.grid(row=5, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))
        ctk.CTkButton(botoes, text="📄  Gerar modelo…", width=150,
                      command=self._gerar_template).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(botoes, text="⇩  Importar mapa…", width=160,
                      command=self._importar_dicionario).grid(row=0, column=1, padx=(0, 8))
        self.btn_editar_mapa = ctk.CTkButton(botoes, text="✎  Editar mapa…", width=150,
                                             command=self._editar_mapa)
        self.btn_editar_mapa.grid(row=0, column=2, padx=(0, 8))
        self.btn_remover_mapa = ctk.CTkButton(
            botoes, text="🗑  Remover", width=110, fg_color="transparent",
            border_width=1, text_color=("gray30", "gray80"),
            command=self._remover_mapa)
        self.btn_remover_mapa.grid(row=0, column=3)
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

    def _exportar_equivalencias(self):
        caminho = filedialog.asksaveasfilename(
            title="Exportar equivalências", defaultextension=".json",
            initialfile="equivalencias.json",
            filetypes=[("Arquivo JSON", "*.json")])
        if not caminho:
            return
        dados = [{"item": e_item.get().strip(),
                  "item_normalizado": e_norm.get().strip()}
                 for _f, e_item, e_norm in self.linhas if e_item.get().strip()]
        try:
            n = equivalencias.exportar_json(caminho, dados)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", "Não foi possível exportar:\n" + str(e))
            return
        self.lbl_status.configure(text=f"✅ {n} equivalência(s) em: {caminho}")

    def _editar_equivalencias(self):
        EditorJson(self, "Normalização de itens", equivalencias._arquivo(),
                   self._apos_editar_equivalencias).focus()

    def _apos_editar_equivalencias(self):
        for frame, _i, _n in list(self.linhas):
            frame.destroy()
        self.linhas.clear()
        self._carregar()
        self.lbl_status.configure(text="✅ Normalização de itens salva.")

    # ── mapa de Unidades Consumidoras ────────────────────────────────────
    def _trocar_medidor(self):
        try:
            dicionario_uc.definir_usar_medidor(bool(self.chk_medidor.get()))
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Não foi possível salvar a escolha:\n{e}")
            return
        self._atualizar_label_dicionario()
        self.lbl_status.configure(
            text=("✅ Identificação por medidor "
                  + ("ligada." if dicionario_uc.usar_medidor() else "desligada.")))

    def _atualizar_label_dicionario(self):
        m = dicionario_uc.metadados()
        tem = dicionario_uc.ativo()
        self.btn_editar_mapa.configure(state="normal" if tem else "disabled")
        self.btn_remover_mapa.configure(state="normal" if tem else "disabled")
        # Sem mapa a identificação por medidor é a única que existe: fica
        # marcada e travada, para não prometer uma escolha que não há.
        self.chk_medidor.select() if dicionario_uc.usar_medidor() else self.chk_medidor.deselect()
        self.chk_medidor.configure(state="normal" if tem else "disabled")
        if not tem:
            self.lbl_dicionario.configure(
                text="📖  Nenhum mapa carregado — a planilha não recebe colunas de "
                     "cadastro nem 'id_uc_canonico'.")
            return
        cols = m["colunas"]
        texto = (f"📖  {m['total_ucs']} UC(s) · {m['operantes']} operante(s) · "
                 f"{len(cols)} coluna(s): {', '.join(cols) if cols else '(nenhuma)'}")
        avisos = dicionario_uc.avisos()
        if avisos:
            texto += f"\n⚠  {len(avisos)} aviso(s): {avisos[0]}"
        self.lbl_dicionario.configure(text=texto)

    def _gerar_template(self):
        caminho = filedialog.asksaveasfilename(
            title="Gerar modelo do mapa de UCs", defaultextension=".json",
            initialfile="mapa_uc_modelo.json",
            filetypes=[("Arquivo JSON", "*.json"), ("Planilha Excel", "*.xlsx")])
        if not caminho:
            return
        try:
            dicionario_uc.gerar_template(caminho)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Não foi possível gerar o modelo:\n{e}")
            return
        self.lbl_status.configure(text=f"✅ Modelo gerado em: {caminho}")

    def _importar_dicionario(self):
        caminho = filedialog.askopenfilename(
            title="Selecione o mapa de UCs (JSON ou planilha)",
            filetypes=[("JSON ou planilha", "*.json *.xlsx *.xlsm *.csv")])
        if not caminho:
            return
        try:
            analise = dicionario_uc.analisar_arquivo(caminho)
        except ValueError as e:
            messagebox.showerror("Arquivo inválido", str(e))
            return
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Não foi possível ler o arquivo:\n{e}")
            return

        dlg = DialogoMapaUC(self, analise)
        self.wait_window(dlg)
        if not dlg.resultado:
            return
        try:
            registros, extras = dicionario_uc.aplicar_mapeamento(
                analise, dlg.resultado["mapeamento"], dlg.resultado["extras"])
            if not registros:
                messagebox.showwarning("Atenção", "Nenhum registro com 'id_uc' "
                                                  "preenchido — nada foi importado.")
                return
            m = dicionario_uc.salvar_mapa(registros, extras)
            dicionario_uc.definir_usar_medidor(dlg.resultado["usar_medidor"])
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Erro", f"Não foi possível importar:\n{e}")
            return
        self._atualizar_label_dicionario()
        self.lbl_status.configure(
            text=f"✅ Mapa importado: {m['total_ucs']} UC(s), "
                 f"{len(m['colunas'])} coluna(s).")

    def _editar_mapa(self):
        EditorJson(self, "Mapa de Unidades Consumidoras",
                   dicionario_uc.arquivo_mapa(), self._apos_editar_mapa).focus()

    def _apos_editar_mapa(self):
        dicionario_uc.recarregar()
        self._atualizar_label_dicionario()
        self.lbl_status.configure(text="✅ Mapa de UCs salvo.")

    def _remover_mapa(self):
        if not messagebox.askyesno(
                "Remover mapa de UCs",
                "O cadastro importado será apagado.\n\nA planilha volta a sair sem "
                "as colunas de cadastro e sem 'id_uc_canonico'. Prosseguir?"):
            return
        dicionario_uc.limpar_mapa()
        self._atualizar_label_dicionario()
        self.lbl_status.configure(text="✅ Mapa removido.")

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
