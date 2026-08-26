"""
Modelo de dados em memória: acumula as linhas (canônicas) produzidas pelos
processadores e converte para DataFrames com a ordem de colunas canônica.
"""
from __future__ import annotations

import re

import pandas as pd

from . import schema

# Itens meramente INFORMATIVOS da fatura (não compõem o valor total): linhas
# "DEMONSTRATIVO"/"DEMO" são removidas da aba itens_fatura no pós-processamento,
# senão a soma dos itens fica maior que o valor_total_r$ da fatura.
_RE_ITEM_INFORMATIVO = re.compile(r'DEMO', re.IGNORECASE)


class Dataset:
    """Coleção de linhas canônicas, por aba."""

    def __init__(self):
        self.linhas: dict[str, list[dict]] = {aba: [] for aba in schema.BASE_SHEETS}
        self._ids_fatura_vistos: set = set()

    def adicionar_resultado(self, resultado: dict):
        """Acrescenta o resultado de UMA fatura (saída de processar_pdf).

        A MESMA fatura pode chegar mais de uma vez no lote: PDF mesclado
        (PDFsam) que repete faturas já presentes como arquivos individuais, ou
        cópia renomeada do mesmo PDF. Nesses casos ignora o resultado inteiro
        (senão fatura/itens/medição saem duplicados na planilha).
        """
        fat = resultado.get("fatura")
        fid = fat.get("id_fatura") if isinstance(fat, dict) else None
        if fid:
            if fid in self._ids_fatura_vistos:
                return
            self._ids_fatura_vistos.add(fid)
        for aba in schema.BASE_SHEETS:
            val = resultado.get(aba)
            if val is None:
                continue
            if aba == "itens_fatura" and isinstance(val, list):
                val = [r for r in val
                       if not _RE_ITEM_INFORMATIVO.search(str(r.get("item", "")))]
            if isinstance(val, list):
                self.linhas[aba].extend(val)
            else:
                self.linhas[aba].append(val)

    def _reindex_canon(self, aba: str, df: pd.DataFrame) -> pd.DataFrame:
        cols = schema.all_canonical(aba)
        ordenadas = [c for c in cols if c in df.columns]
        extras = [c for c in df.columns if c not in cols]
        return df.reindex(columns=ordenadas + extras)

    def to_dataframes(self) -> dict[str, pd.DataFrame]:
        """
        Converte para DataFrames canônicos, na ordem de SHEET_ORDER.
        As abas base vêm das linhas acumuladas; as abas DERIVADAS
        (fatura_resumida, medicao_resumida) são calculadas a partir delas.
        """
        base: dict[str, pd.DataFrame] = {}
        for aba in schema.BASE_SHEETS:
            base[aba] = self._reindex_canon(aba, pd.DataFrame(self.linhas[aba]))

        derivadas = {
            "fatura_resumida": self._derivar_fatura_resumida(base["fatura"]),
            "medicao_resumida": self._derivar_medicao_resumida(base["medicao"]),
        }

        todas = {**base, **derivadas}
        # devolve na ordem de saída
        return {aba: todas[aba] for aba in schema.SHEET_ORDER if aba in todas}

    def _derivar_fatura_resumida(self, df_fatura: pd.DataFrame) -> pd.DataFrame:
        cols = schema.all_canonical("fatura_resumida")
        presentes = [c for c in cols if c in df_fatura.columns]
        return df_fatura.reindex(columns=presentes).copy()

    def _derivar_medicao_resumida(self, df_medicao: pd.DataFrame) -> pd.DataFrame:
        if df_medicao.empty or "Grandezas" not in df_medicao.columns:
            return pd.DataFrame(columns=schema.all_canonical("medicao_resumida"))
        import re
        alvo = re.compile(r'^ENERGIA\s+GERA[ÇC][ÃA]O\s*-\s*KWH$', re.IGNORECASE)
        mask = df_medicao["Grandezas"].astype(str).str.strip().apply(lambda v: bool(alvo.match(v)))
        df = df_medicao[mask].copy()
        df = df.rename(columns={"Consumo kWh": schema.MEDICAO_RESUMIDA_COL})
        return self._reindex_canon("medicao_resumida", df)

    def total_faturas(self) -> int:
        return len(self.linhas.get("fatura", []))


def colunas_todas_nulas(df: pd.DataFrame) -> list[str]:
    """Colunas 100% vazias (NaN/None/'') — exceto as protegidas pelo schema."""
    nulas = []
    for c in df.columns:
        if c in schema.COLS_PROTEGIDAS:
            continue
        col = df[c]
        if col.isna().all() or (col.astype(str).str.strip() == "").all():
            nulas.append(c)
    return nulas
