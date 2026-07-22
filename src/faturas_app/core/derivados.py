"""
Colunas DERIVADAS/agregadas, recalculadas do zero sobre o conjunto completo de
faturas (tanto no processamento quanto na concatenação):

  - unidade_consumidora.primeira_competencia / ultima_competencia e
    primeira_fatura / ultima_fatura: a competência mais antiga/mais recente
    (e o id_fatura correspondente) por id_uc.
  - id_uc_sem_format / id_uc_atual_medidor / id_uc_atual_medidor_sem_format:
    ao lado de id_uc, em TODAS as abas.
  - medidor: em 'fatura' e 'fatura_resumida', o medidor (moda) da fatura.
  - item_normalizado: em itens_fatura.

`aplicar(dfs)` opera sobre DataFrames CANÔNICOS. `aplicar_concat(res_dfs, meta)`
converte o resultado (nomes exibidos) para canônico, recalcula e grava de volta.
"""
from __future__ import annotations

import re

import pandas as pd

from . import concat as _concat
from . import equivalencias
from . import schema

# Colunas produzidas por este módulo (para o writeback na concatenação).
COLUNAS_DERIVADAS = ["primeira_competencia", "ultima_competencia",
                     "primeira_fatura", "ultima_fatura",
                     "id_uc_sem_format", "id_uc_atual_medidor",
                     "id_uc_atual_medidor_sem_format", "id_uc_atual", "medidor",
                     "item_normalizado", "tipo_fornecimento"]


def aplicar(dfs: dict) -> dict:
    """Preenche as colunas derivadas nos DataFrames canônicos (in place)."""
    _calcular(dfs)
    _dedup_unidade_consumidora(dfs)
    return dfs


def _calcular(dfs: dict) -> None:
    _extremos_por_uc(dfs)
    _colunas_medidor(dfs)
    _item_normalizado(dfs)
    _tipo_fornecimento_upper(dfs)
    _reordenar_canonico(dfs)


def _extremos_por_uc(dfs: dict) -> None:
    """primeira/ultima competencia e fatura, por id_uc (extremos cronológicos)."""
    fat = dfs.get("fatura")
    cli = dfs.get("unidade_consumidora")
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
    tmp = tmp.sort_values("_k")
    grp = tmp.groupby("id_uc", sort=False)
    primeira = grp.head(1)
    ultima = grp.tail(1)
    cli["primeira_competencia"] = cli["id_uc"].map(dict(zip(primeira["id_uc"], primeira["competencia"])))
    cli["ultima_competencia"] = cli["id_uc"].map(dict(zip(ultima["id_uc"], ultima["competencia"])))
    cli["primeira_fatura"] = cli["id_uc"].map(dict(zip(primeira["id_uc"], primeira["id_fatura"])))
    cli["ultima_fatura"] = cli["id_uc"].map(dict(zip(ultima["id_uc"], ultima["id_fatura"])))


def _moda(serie: pd.Series):
    s = serie.dropna().astype(str)
    if s.empty:
        return None
    md = s.mode()
    return md.iat[0] if not md.empty else s.iat[0]


def _sem_formatacao(v):
    """Valor de id_uc/id_uc_atual_medidor sem ponto ou hífen."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return v
    return re.sub(r'[.\-]', '', str(v))


def _colunas_medidor(dfs: dict) -> None:
    """
    id_uc_atual_medidor: por medidor, o id_uc mais recente (por competência) que
    NÃO começa com 'NULO_'. Cada linha recebe o valor do seu medidor (medição:
    coluna Medidor; demais abas: via id_fatura; unidade_consumidora: via id_uc).
    Sem medidor conhecido, mantém o próprio id_uc.

    Colunas gravadas ao lado de id_uc dependem da aba:
      - 'unidade_consumidora': id_uc_sem_format, id_uc_atual_medidor e
        id_uc_atual_medidor_sem_format (as três completas).
      - demais abas: apenas 'id_uc_atual' (= id_uc_atual_medidor sem ponto/hífen).
    E, só em 'fatura'/'fatura_resumida': a coluna 'medidor' (moda do medidor
    daquela fatura, vinda da aba medicao).
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
        else:                                   # unidade_consumidora
            medidor = df["id_uc"].map(mapa_uc_med)
        ucatual = medidor.map(lambda m: mapa_med_uc.get(str(m))
                              if (m is not None and pd.notna(m)) else None)
        id_uc_atual_medidor = ucatual.where(ucatual.notna(), df["id_uc"])
        if aba == "unidade_consumidora":
            df["id_uc_atual_medidor"] = id_uc_atual_medidor
            df["id_uc_sem_format"] = df["id_uc"].map(_sem_formatacao)
            df["id_uc_atual_medidor_sem_format"] = id_uc_atual_medidor.map(_sem_formatacao)
        else:
            df["id_uc_atual"] = id_uc_atual_medidor.map(_sem_formatacao)

    for aba in ("fatura", "fatura_resumida"):
        df = dfs.get(aba)
        if df is not None and not df.empty and "id_fatura" in df.columns:
            df["medidor"] = df["id_fatura"].map(mapa_fat_med)


def _item_normalizado(dfs: dict) -> None:
    itf = dfs.get("itens_fatura")
    if itf is not None and not itf.empty and "item" in itf.columns:
        equivalencias.aplicar(itf, "item", "item_normalizado")


def _tipo_fornecimento_upper(dfs: dict) -> None:
    """tipo_fornecimento ('fatura'/'fatura_resumida'): valores não vazios em
    maiúsculas (independe da fornecedora)."""
    for aba in ("fatura", "fatura_resumida"):
        df = dfs.get(aba)
        if df is not None and not df.empty and "tipo_fornecimento" in df.columns:
            df["tipo_fornecimento"] = df["tipo_fornecimento"].map(
                lambda v: v.upper() if isinstance(v, str) else v)


def _reordenar_canonico(dfs: dict) -> None:
    """
    Reordena as colunas de cada aba na ordem canônica (schema.py), agora que
    todas as colunas derivadas já foram calculadas. Sem isso, colunas novas
    (atribuídas via df['nova'] = ...) ficam sempre no FINAL do DataFrame,
    independente da posição definida no esquema.
    """
    for aba, df in dfs.items():
        if df is None or df.empty:
            continue
        cols_canon = schema.all_canonical(aba)
        if not cols_canon:
            continue
        ordenadas = [c for c in cols_canon if c in df.columns]
        extras = [c for c in df.columns if c not in cols_canon]
        if list(df.columns) != ordenadas + extras:
            dfs[aba] = df.reindex(columns=ordenadas + extras)


def _dedup_unidade_consumidora(dfs: dict) -> None:
    """
    A aba 'unidade_consumidora' acumula 1 linha por FATURA processada (não por
    UC). Como os dados cadastrais e os agregados (primeira/ultima_*) são os
    mesmos para todas as faturas da mesma UC, ao final basta um drop_duplicates
    para sobrar 1 linha por UC.
    """
    df = dfs.get("unidade_consumidora")
    if df is not None and not df.empty:
        dfs["unidade_consumidora"] = df.drop_duplicates().reset_index(drop=True)


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

    _calcular(canon)

    for aba, cdf in canon.items():
        for canonico in COLUNAS_DERIVADAS:
            if canonico in cdf.columns:
                exib = reverso.get(aba, {}).get(canonico, canonico)
                res_dfs[aba][exib] = cdf[canonico].values

    # Dedup ao final (linha completa) — direto no resultado (nomes exibidos),
    # já que a contagem de linhas de `canon` pode ter mudado com o dedup interno.
    df_uc = res_dfs.get("unidade_consumidora")
    if df_uc is not None and not df_uc.empty:
        res_dfs["unidade_consumidora"] = df_uc.drop_duplicates().reset_index(drop=True)
