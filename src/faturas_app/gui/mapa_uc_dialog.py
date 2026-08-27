"""
Tela de mapeamento do MAPA DE UNIDADES CONSUMIDORAS.

O arquivo que o usuário importa (JSON ou planilha) raramente usa exatamente os
nomes do template. O app já casa sozinho o que tem nome idêntico; esta tela
resolve o resto, e é aqui que o usuário vê — antes de aplicar — o que vai virar
coluna e o que vai ficar de fora.

Três blocos:

  1. **Itens do template** — cada item com o campo do arquivo correspondente.
     Os casados automaticamente já vêm preenchidos. Item deixado em
     "(não usar)" NÃO vira coluna, que é o comportamento pedido.
  2. **Campos que sobraram** — o que existe no arquivo e não é do template.
     Marcados viram coluna nova; o nome da coluna é editável.
  3. **Identificação por medidor** — com um mapa carregado ela deixa de ser
     necessária, então pode ser desligada aqui mesmo.
"""
from __future__ import annotations

import customtkinter as ctk

from ..core import dicionario_uc

NAO_USAR = "(não usar)"


class DialogoMapaUC(ctk.CTkToplevel):
    """Devolve em `self.resultado` o dict {mapeamento, extras, usar_medidor}."""

    def __init__(self, master, analise: dict):
        super().__init__(master)
        self.title("Mapear o arquivo de UCs")
        self.geometry("820x680")
        self.resultado: dict | None = None
        self._analise = analise
        self._combos: dict[str, ctk.CTkComboBox] = {}
        self._extras: dict[str, tuple] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── cabeçalho ────────────────────────────────────────────────────
        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        ctk.CTkLabel(cab, text="Confira o que será importado",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w")
        n_auto = len(analise["auto"])
        ctk.CTkLabel(
            cab, justify="left", wraplength=770, anchor="w",
            text_color=("gray40", "gray65"),
            text=(f"{len(analise['registros'])} unidade(s) consumidora(s) no arquivo. "
                  f"{n_auto} item(ns) do template foram reconhecidos pelo nome. "
                  f"Complete o que faltar — item deixado em “{NAO_USAR}” não vira "
                  f"coluna na planilha.")).pack(anchor="w", pady=(2, 0))
        for aviso in analise.get("avisos", []):
            ctk.CTkLabel(cab, text="⚠ " + aviso, justify="left", wraplength=770,
                         anchor="w", text_color=("#8a6100", "#e0b050")).pack(
                anchor="w", pady=(4, 0))

        corpo = ctk.CTkScrollableFrame(self, fg_color=("gray96", "gray14"))
        corpo.grid(row=1, column=0, sticky="nsew", padx=16, pady=8)
        corpo.grid_columnconfigure(1, weight=1)

        opcoes = [NAO_USAR] + list(analise["campos"])
        linha = 0

        # ── 1) itens do template ─────────────────────────────────────────
        ctk.CTkLabel(corpo, text="Itens do template",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=linha, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 2))
        linha += 1
        ctk.CTkLabel(corpo, text=f"{dicionario_uc.ITEM_CHAVE}  (chave)",
                     font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=linha, column=0, sticky="w", padx=8, pady=3)
        ctk.CTkLabel(corpo, text=analise["chave"], anchor="w",
                     text_color=("gray35", "gray70")).grid(
            row=linha, column=1, sticky="ew", padx=8)
        linha += 1

        for item, coluna, tipo, descricao in dicionario_uc.TEMPLATE:
            if item == dicionario_uc.ITEM_CHAVE:
                continue
            ctk.CTkLabel(corpo, text=item).grid(row=linha, column=0, sticky="w",
                                                padx=8, pady=3)
            combo = ctk.CTkComboBox(corpo, values=opcoes, width=280)
            combo.set(analise["auto"].get(item, NAO_USAR))
            combo.grid(row=linha, column=1, sticky="w", padx=8)
            self._combos[item] = combo
            ctk.CTkLabel(corpo, text=descricao, wraplength=300, justify="left",
                         anchor="w", font=ctk.CTkFont(size=11),
                         text_color=("gray45", "gray60")).grid(
                row=linha, column=2, sticky="w", padx=8)
            linha += 1

        # ── 2) campos que sobraram ───────────────────────────────────────
        sobrando = analise.get("sobrando") or []
        ctk.CTkLabel(corpo, text="Campos fora do template",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=linha, column=0, columnspan=3, sticky="w", padx=8, pady=(14, 2))
        linha += 1
        if not sobrando:
            ctk.CTkLabel(corpo, text="nenhum — o arquivo só tem itens do template.",
                         text_color=("gray45", "gray60")).grid(
                row=linha, column=0, columnspan=3, sticky="w", padx=8, pady=2)
            linha += 1
        else:
            ctk.CTkLabel(
                corpo, wraplength=760, justify="left", anchor="w",
                font=ctk.CTkFont(size=11), text_color=("gray45", "gray60"),
                text="Marque os que devem virar coluna nova na aba "
                     "'unidade_consumidora'. O nome da coluna pode ser trocado.").grid(
                row=linha, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 4))
            linha += 1
            for campo in sobrando:
                var = ctk.BooleanVar(value=False)
                ctk.CTkCheckBox(corpo, text=campo, variable=var, width=240).grid(
                    row=linha, column=0, sticky="w", padx=8, pady=3)
                entry = ctk.CTkEntry(corpo, width=280)
                entry.insert(0, campo)
                entry.grid(row=linha, column=1, sticky="w", padx=8)
                self._extras[campo] = (var, entry)
                linha += 1

        # ── 3) identificação por medidor ─────────────────────────────────
        ctk.CTkLabel(corpo, text="Identificação histórica por medidor",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=linha, column=0, columnspan=3, sticky="w", padx=8, pady=(14, 2))
        linha += 1
        self.var_medidor = ctk.BooleanVar(value=dicionario_uc.usar_medidor())
        ctk.CTkCheckBox(
            corpo, variable=self.var_medidor,
            text="Manter as colunas de identificação por medidor").grid(
            row=linha, column=0, columnspan=2, sticky="w", padx=8, pady=3)
        linha += 1
        ctk.CTkLabel(
            corpo, wraplength=760, justify="left", anchor="w",
            font=ctk.CTkFont(size=11), text_color=("gray45", "gray60"),
            text="Com um mapa carregado, a UC já é identificada pelo cadastro. "
                 "Desmarcado, as colunas 'id_uc_atual_medidor', "
                 "'id_uc_atual_medidor_sem_format' e 'id_uc_atual' deixam de ser "
                 "criadas em qualquer aba.").grid(
            row=linha, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 8))

        # ── rodapé ───────────────────────────────────────────────────────
        rod = ctk.CTkFrame(self, fg_color="transparent")
        rod.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        rod.grid_columnconfigure(0, weight=1)
        self.lbl_previa = ctk.CTkLabel(rod, text="", anchor="w",
                                       text_color=("gray35", "gray70"))
        self.lbl_previa.grid(row=0, column=0, sticky="w")
        ctk.CTkButton(rod, text="Cancelar", width=110, fg_color="transparent",
                      border_width=1, text_color=("gray30", "gray80"),
                      command=self._cancelar).grid(row=0, column=1, padx=(8, 8))
        ctk.CTkButton(rod, text="Importar", width=140, height=36,
                      command=self._confirmar).grid(row=0, column=2)

        self._atualizar_previa()
        for c in self._combos.values():
            c.configure(command=lambda _v: self._atualizar_previa())
        for var, _e in self._extras.values():
            var.trace_add("write", lambda *_a: self._atualizar_previa())

        self.transient(master)
        self.grab_set()

    # ── ações ────────────────────────────────────────────────────────────
    def _coletar(self):
        mapeamento = {item: (c.get() if c.get() != NAO_USAR else None)
                      for item, c in self._combos.items()}
        extras = {campo: entry.get().strip()
                  for campo, (var, entry) in self._extras.items()
                  if var.get() and entry.get().strip()}
        return mapeamento, extras

    def _atualizar_previa(self):
        mapeamento, extras = self._coletar()
        n_itens = sum(1 for v in mapeamento.values() if v)
        fora = [i for i, v in mapeamento.items() if not v]
        texto = f"{n_itens} coluna(s) do template + {len(extras)} extra(s)."
        if fora:
            texto += f"  Ficam de fora: {', '.join(fora[:3])}"
            if len(fora) > 3:
                texto += f" e mais {len(fora) - 3}"
        self.lbl_previa.configure(text=texto)

    def _confirmar(self):
        mapeamento, extras = self._coletar()
        self.resultado = {"mapeamento": {k: v for k, v in mapeamento.items() if v},
                          "extras": extras,
                          "usar_medidor": bool(self.var_medidor.get())}
        self.grab_release()
        self.destroy()

    def _cancelar(self):
        self.resultado = None
        self.grab_release()
        self.destroy()
