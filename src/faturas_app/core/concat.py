"""
Concatenação de uma planilha ENVIADA (possivelmente com colunas renomeadas ou
removidas) com NOVAS faturas processadas (em formato canônico).

A robustez vem do mapeamento `nome_exibido -> canônico`:
  - se a planilha enviada foi gerada por este app, o mapa vem dos metadados
    embutidos (exato, sem ambiguidade);
  - caso contrário, sugerimos o mapa por similaridade de nomes e o usuário
    confirma/ajusta na tela de mapeamento.

Com o mapa, traduzimos as novas faturas para o MESMO layout da planilha enviada
(respeitando renomeações e exclusões do usuário) e empilhamos, removendo
duplicatas por chave canônica.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

from . import schema


# ──────────────────────────────────────────────────────────────────────────────
# Mapeamento de colunas (auto-sugestão + via metadados)
# ──────────────────────────────────────────────────────────────────────────────
def normalizar(nome: str) -> str:
    s = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def sugerir_mapeamento(aba: str, colunas_exibidas: list[str]) -> dict[str, str | None]:
    """
    Sugere {nome_exibido -> canonico|None} para uma aba, por similaridade.
    Usado quando NÃO há metadados embutidos.
    """
    canon = schema.all_canonical(aba)
    norm_canon = {normalizar(c): c for c in canon}
    aliases = {normalizar(k): v for k, v in schema.COLUMN_ALIASES.get(aba, {}).items()}
    usados: set[str] = set()
    mapa: dict[str, str | None] = {}
    for col in colunas_exibidas:
        n = normalizar(col)
        achado = None
        # 1) match exato normalizado
        if n in norm_canon and norm_canon[n] not in usados:
            achado = norm_canon[n]
        # 1b) apelido conhecido
        if achado is None and n in aliases and aliases[n] not in usados:
            achado = aliases[n]
        # 2) prefixo/contido (ex.: "valortotal" ~ "valortotalr")
        if achado is None:
            for nc, c in norm_canon.items():
                if c in usados:
                    continue
                if n and (n in nc or nc in n) and abs(len(n) - len(nc)) <= 3:
                    achado = c
                    break
        if achado:
            usados.add(achado)
        mapa[col] = achado
    return mapa


def mapeamento_de_meta(meta: dict | None, aba: str) -> dict[str, str | None] | None:
    """Extrai {nome_exibido -> canonico} dos metadados embutidos, se houver."""
    if not meta:
        return None
    info = meta.get("abas", {}).get(aba)
    if not info:
        return None
    return {c["exibido"]: c.get("canonico") for c in info.get("colunas", [])}


# ──────────────────────────────────────────────────────────────────────────────
# Concatenação
# ──────────────────────────────────────────────────────────────────────────────
def _dedup(df: pd.DataFrame, chaves_disp: list[str]) -> tuple[pd.DataFrame, int]:
    chaves_validas = [k for k in chaves_disp if k in df.columns]
    if not chaves_validas:
        return df, 0
    antes = len(df)
    df2 = df.drop_duplicates(subset=chaves_validas, keep="first").reset_index(drop=True)
    return df2, antes - len(df2)


def _dedup_linha_completa(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Remove apenas linhas 100% idênticas (todas as colunas)."""
    antes = len(df)
    df2 = df.drop_duplicates(keep="first").reset_index(drop=True)
    return df2, antes - len(df2)


def concatenar(uploaded_dfs: dict[str, pd.DataFrame],
               mapeamentos: dict[str, dict[str, str | None]],
               novos_canon: dict[str, pd.DataFrame],
               adicionar_novas_colunas: bool = False):
    """
    Parâmetros
    ----------
    uploaded_dfs : {aba -> DataFrame} da planilha enviada (nomes EXIBIDOS).
    mapeamentos  : {aba -> {nome_exibido -> canonico|None}} confirmado.
    novos_canon  : {aba -> DataFrame} das novas faturas (nomes CANÔNICOS).
    adicionar_novas_colunas : se True, colunas canônicas que existem nas novas
                              faturas mas foram removidas da planilha enviada são
                              re-adicionadas ao final (linhas antigas ficam vazias).

    Retorna (display_dfs_resultado, meta_resultado, resumo:list[str]).
    """
    resumo: list[str] = []
    resultado: dict[str, pd.DataFrame] = {}
    meta_abas: dict[str, dict] = {}

    abas_upload = list(uploaded_dfs.keys())
    abas_novas = [a for a in novos_canon if not novos_canon[a].empty]
    # Ordem: abas do upload primeiro (preserva a estrutura do usuário), depois
    # abas presentes só nas novas faturas.
    todas = abas_upload + [a for a in abas_novas if a not in abas_upload]

    for aba in todas:
        up_df = uploaded_dfs.get(aba)
        novos = novos_canon.get(aba)
        canonica = aba in schema.CANONICAL_COLUMNS

        # Caso 1: aba só existe na planilha enviada (sem novas faturas dessa aba).
        if up_df is not None and (novos is None or novos.empty):
            resultado[aba] = up_df.copy()
            mapa = mapeamentos.get(aba, {c: None for c in up_df.columns})
            meta_abas[aba] = {"incluida": True, "colunas": [
                {"exibido": c, "canonico": mapa.get(c), "incluida": True}
                for c in up_df.columns]}
            continue

        # Caso 2: aba só existe nas novas faturas (não estava no arquivo enviado).
        if up_df is None:
            df = novos.copy()
            resultado[aba] = df
            meta_abas[aba] = {"incluida": True, "colunas": [
                {"exibido": c, "canonico": c, "incluida": True} for c in df.columns]}
            resumo.append(f"Aba '{aba}': não existia no arquivo enviado; "
                          f"criada com {len(df)} linha(s) das novas faturas.")
            continue

        # Caso 3: aba existe nos dois lados → traduzir novas p/ layout do enviado.
        mapa = mapeamentos.get(aba) or {c: None for c in up_df.columns}
        reverse = {canon: exib for exib, canon in mapa.items() if canon}

        # Constrói o DataFrame das novas faturas no layout (nomes exibidos) do upload.
        dados_novos = {}
        for exib in up_df.columns:
            canon = mapa.get(exib)
            if canon and canon in novos.columns:
                dados_novos[exib] = list(novos[canon])
            else:
                dados_novos[exib] = [None] * len(novos)
        novos_layout = pd.DataFrame(dados_novos).reindex(columns=list(up_df.columns))

        up_ext = up_df.copy()
        colunas_adicionadas = []
        if adicionar_novas_colunas and canonica:
            faltantes = [c for c in novos.columns if c not in reverse]
            for c in faltantes:
                up_ext[c] = None
                novos_layout[c] = list(novos[c])
                colunas_adicionadas.append(c)
            if colunas_adicionadas:
                resumo.append(f"Aba '{aba}': colunas novas adicionadas ao final: "
                              f"{', '.join(colunas_adicionadas)}.")

        # Alinha colunas e empilha.
        cols_final = list(up_ext.columns)
        for c in novos_layout.columns:
            if c not in cols_final:
                cols_final.append(c)
        combinado = pd.concat(
            [up_ext.reindex(columns=cols_final), novos_layout.reindex(columns=cols_final)],
            ignore_index=True)

        # Dedup: medição usa LINHA COMPLETA (variações de leitura são válidas);
        # demais abas usam a chave canônica (traduzida para nomes exibidos).
        if aba in schema.DEDUP_FULL_ROW:
            combinado, n_dup = _dedup_linha_completa(combinado)
            if n_dup:
                resumo.append(f"Aba '{aba}': {n_dup} linha(s) 100% idêntica(s) ignorada(s).")
        else:
            chaves_canon = schema.DEDUP_KEYS.get(aba, [])
            chaves_disp = [reverse[k] for k in chaves_canon if k in reverse]
            combinado, n_dup = _dedup(combinado, chaves_disp)
            if n_dup:
                resumo.append(f"Aba '{aba}': {n_dup} fatura(s) duplicada(s) ignorada(s) "
                              f"(já existiam no arquivo enviado).")
            elif not chaves_disp and chaves_canon:
                resumo.append(f"Aba '{aba}': não foi possível remover duplicatas — a(s) "
                              f"coluna(s)-chave ({', '.join(chaves_canon)}) não estão no arquivo enviado.")

        resultado[aba] = combinado
        # Monta metadados de saída.
        cols_meta = []
        for c in cols_final:
            if c in mapa:
                canon = mapa.get(c)
            elif c in colunas_adicionadas:
                canon = c
            else:
                canon = None
            cols_meta.append({"exibido": c, "canonico": canon, "incluida": True})
        meta_abas[aba] = {"incluida": True, "colunas": cols_meta}

        resumo.append(f"Aba '{aba}': {len(up_df)} (enviado) + {len(novos)} (novas) "
                      f"= {len(combinado)} linha(s).")

    meta = {"app": "Processador de Faturas de Energia", "versao_meta": 1, "abas": meta_abas}
    return resultado, meta, resumo
