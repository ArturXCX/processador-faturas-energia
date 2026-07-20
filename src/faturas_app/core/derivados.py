"""
Colunas DERIVADAS/agregadas, recalculadas do zero sobre o conjunto completo de
faturas (tanto no processamento quanto na concatenação):

  - cliente.ultima_competencia / cliente.ultima_fatura: a competência mais recente
    e o id_fatura correspondente, por id_uc.

(Increment 2 adicionará aqui id_uc_normalizado e item_normalizado.)

`aplicar(dfs)` opera sobre DataFrames CANÔNICOS. `aplicar_concat(res_dfs, meta)`
converte o resultado (nomes exibidos) para canônico, recalcula e grava de volta.
"""
from __future__ import annotations

import pandas as pd

from . import concat as _concat
from . import equivalencias

# Colunas produzidas por este módulo (para o writeback na concatenação).
COLUNAS_DERIVADAS = ["ultima_competencia", "ultima_fatura",
                     "id_uc_normalizado", "item_normalizado"]


def aplicar(dfs: dict) -> dict:
    """Preenche as colunas derivadas nos DataFrames canônicos (in place)."""
    _ultima_por_uc(dfs)
    _id_uc_normalizado(dfs)
    _item_normalizado(dfs)
    return dfs


def _ultima_por_uc(dfs: dict) -> None:
    fat = dfs.get("fatura")
    cli = dfs.get("cliente")
    if fat is None or cli is None or getattr(fat, "empty", True) or getattr(cli, "empty", True):
        return
    if not {"id_uc", "competencia", "id_fatura"}.issubset(fat.columns):
        return
    if "id_uc" not in cli.columns:
        return
    tmp = fat[["id_uc", "competencia", "id_fatura"]].copy()
    tmp = tmp[tmp["id_uc"].notna()]
    # competencia no formato AAAA-MM ordena lexicograficamente = cronologicamente.
    tmp["_k"] = tmp["competencia"].astype(str)
    ult = tmp.sort_values("_k").groupby("id_uc", sort=False).tail(1)
    mapa_comp = dict(zip(ult["id_uc"], ult["competencia"]))
    mapa_fat = dict(zip(ult["id_uc"], ult["id_fatura"]))
    cli["ultima_competencia"] = cli["id_uc"].map(mapa_comp)
    cli["ultima_fatura"] = cli["id_uc"].map(mapa_fat)


def _moda(serie: pd.Series):
    s = serie.dropna().astype(str)
    if s.empty:
        return None
    md = s.mode()
    return md.iat[0] if not md.empty else s.iat[0]


def _id_uc_normalizado(dfs: dict) -> None:
    """
    id_uc_normalizado: por medidor, o id_uc mais recente (por competência) que
    NÃO começa com 'NULO_'. Cada linha recebe o valor do seu medidor (medição:
    coluna Medidor; demais abas: via id_fatura; cliente: via id_uc). Sem medidor
    conhecido, mantém o próprio id_uc.
    """
    med = dfs.get("medicao")
    mapa_med_uc: dict[str, str] = {}
    mapa_fat_med: dict = {}
    mapa_uc_med: dict = {}
    if med is not None and not med.empty and \
            {"Medidor", "id_uc", "competencia"}.issubset(med.columns):
        t = med[["Medidor", "id_uc", "competencia", "id_fatura"]].copy() \
            if "id_fatura" in med.columns else med[["Medidor", "id_uc", "competencia"]].copy()
        t = t[t["Medidor"].notna()]
        nn = t[t["id_uc"].notna() & ~t["id_uc"].astype(str).str.startswith("NULO_")].copy()
        if not nn.empty:
            nn["_k"] = nn["competencia"].astype(str)
            ult = nn.sort_values("_k").groupby(nn["Medidor"].astype(str), sort=False).tail(1)
            mapa_med_uc = dict(zip(ult["Medidor"].astype(str), ult["id_uc"]))
        if "id_fatura" in t.columns:
            mapa_fat_med = t.groupby("id_fatura")["Medidor"].agg(_moda).to_dict()
        if "id_uc" in t.columns:
            mapa_uc_med = t.groupby("id_uc")["Medidor"].agg(_moda).to_dict()

    for aba, df in dfs.items():
        if df is None or df.empty or "id_uc" not in df.columns:
            continue
        if "Medidor" in df.columns:
            medidor = df["Medidor"].astype("object")
            if "id_fatura" in df.columns:
                medidor = medidor.where(medidor.notna(), df["id_fatura"].map(mapa_fat_med))
        elif "id_fatura" in df.columns:
            medidor = df["id_fatura"].map(mapa_fat_med)
        else:                                   # cliente
            medidor = df["id_uc"].map(mapa_uc_med)
        ucnorm = medidor.map(lambda m: mapa_med_uc.get(str(m))
                             if (m is not None and pd.notna(m)) else None)
        df["id_uc_normalizado"] = ucnorm.where(ucnorm.notna(), df["id_uc"])


def _item_normalizado(dfs: dict) -> None:
    itf = dfs.get("itens_fatura")
    if itf is not None and not itf.empty and "item" in itf.columns:
        equivalencias.aplicar(itf, "item", "item_normalizado")


def aplicar_concat(res_dfs: dict, meta: dict | None) -> None:
    """
    Recalcula as colunas derivadas sobre o resultado da concatenação (nomes
    exibidos). Canoniza via metadados, calcula e grava de volta (in place).
    """
    canon: dict[str, pd.DataFrame] = {}
    reverso: dict[str, dict] = {}   # aba -> {canonico: nome_exibido}
    for aba, df in res_dfs.items():
        m = _concat.mapeamento_de_meta(meta, aba) or {}   # exibido -> canonico
        inv = {exib: can for exib, can in m.items() if can}       # exibido -> canonico
        reverso[aba] = {can: exib for exib, can in inv.items()}   # canonico -> exibido
        canon[aba] = df.rename(columns=inv)

    aplicar(canon)

    for aba, cdf in canon.items():
        for canonico in COLUNAS_DERIVADAS:
            if canonico in cdf.columns:
                exib = reverso.get(aba, {}).get(canonico, canonico)
                res_dfs[aba][exib] = cdf[canonico].values
