"""
Perfil de saída (camada de EXIBIÇÃO sobre o esquema canônico).

Um perfil descreve, por aba:
  - se a aba será incluída na planilha final;
  - quais colunas entram, em que ordem, e com que nome exibido;
  - a origem canônica de cada coluna (para round-trip e re-concatenação).

O perfil é serializável para os metadados embutidos na planilha (aba oculta),
o que permite, num upload futuro, remapear colunas renomeadas/removidas de volta
ao seu nome canônico sem ambiguidade.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import schema


@dataclass
class ColunaPerfil:
    canonico: str | None       # nome canônico de origem (None = coluna "extra")
    exibido: str               # nome exibido na planilha
    incluida: bool = True


@dataclass
class AbaPerfil:
    nome: str                  # nome canônico da aba (também usado como nome da aba no Excel)
    incluida: bool = True
    colunas: list[ColunaPerfil] = field(default_factory=list)


@dataclass
class Perfil:
    abas: list[AbaPerfil] = field(default_factory=list)

    # ── construção ──────────────────────────────────────────────────────────
    @classmethod
    def padrao_de_dataframes(cls, dfs: dict[str, pd.DataFrame],
                             desmarcar_nulas: bool = True) -> "Perfil":
        """
        Cria um perfil padrão a partir de DataFrames canônicos: tudo incluído,
        nomes exibidos = canônicos. Se `desmarcar_nulas`, colunas 100% vazias
        já vêm desmarcadas (espelha o 'descarte de colunas nulas' dos notebooks).
        """
        from .dataset import colunas_todas_nulas
        abas = []
        for aba in schema.SHEET_ORDER:
            df = dfs.get(aba)
            if df is None:
                continue
            # Abas derivadas (resumidas) são sempre incluídas e mantêm todas as
            # colunas marcadas (ex.: colunas SCEE, mesmo vazias).
            eh_derivada = aba in schema.DERIVED_SHEETS
            if eh_derivada or not desmarcar_nulas or df.empty:
                nulas = set()
            else:
                nulas = set(colunas_todas_nulas(df))
            cols = [ColunaPerfil(canonico=c, exibido=c, incluida=(c not in nulas))
                    for c in df.columns]
            incluida = True if eh_derivada else (not df.empty)
            abas.append(AbaPerfil(nome=aba, incluida=incluida, colunas=cols))
        return cls(abas=abas)

    # ── aplicação ─────────────────────────────────────────────────────────────
    def aplicar(self, dfs_canon: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """
        Aplica o perfil aos DataFrames canônicos, devolvendo DataFrames de saída
        (nomes exibidos, colunas/abas selecionadas, na ordem do perfil).
        """
        out: dict[str, pd.DataFrame] = {}
        for aba in self.abas:
            if not aba.incluida:
                continue
            df = dfs_canon.get(aba.nome)
            if df is None:
                df = pd.DataFrame()
            dados = {}
            nomes_ordenados = []
            for col in aba.colunas:
                if not col.incluida:
                    continue
                serie = df[col.canonico] if (col.canonico in df.columns) else pd.Series([None] * len(df))
                dados[col.exibido] = list(serie)
                nomes_ordenados.append(col.exibido)
            novo = pd.DataFrame(dados)
            if nomes_ordenados:
                novo = novo.reindex(columns=nomes_ordenados)
            out[aba.nome] = novo
        return out

    # ── metadados (serialização) ───────────────────────────────────────────
    def to_meta(self) -> dict:
        return {
            "app": "Processador de Faturas de Energia",
            "versao_meta": 1,
            "abas": {
                aba.nome: {
                    "incluida": aba.incluida,
                    "colunas": [
                        {"exibido": c.exibido, "canonico": c.canonico, "incluida": c.incluida}
                        for c in aba.colunas
                    ],
                }
                for aba in self.abas
            },
        }

    @classmethod
    def from_meta(cls, meta: dict) -> "Perfil":
        abas = []
        for nome, info in meta.get("abas", {}).items():
            cols = [ColunaPerfil(canonico=c.get("canonico"),
                                 exibido=c["exibido"],
                                 incluida=c.get("incluida", True))
                    for c in info.get("colunas", [])]
            abas.append(AbaPerfil(nome=nome, incluida=info.get("incluida", True), colunas=cols))
        return cls(abas=abas)

    def mapa_exibido_para_canonico(self, aba: str) -> dict[str, str | None]:
        """Para uma aba: {nome_exibido: canonico} (canonico pode ser None)."""
        for a in self.abas:
            if a.nome == aba:
                return {c.exibido: c.canonico for c in a.colunas}
        return {}
