"""
Tabela de equivalências de itens (parâmetro do sistema, persistido).

Guarda pares (item -> item_normalizado) num JSON em %APPDATA%/FaturasEnergia/, de
modo que o usuário possa criar/editar/excluir equivalências e elas fiquem salvas
entre execuções. Usada para preencher a coluna `item_normalizado` da aba
`itens_fatura`: se o item existir na tabela, usa o valor normalizado; senão, usa
o próprio item.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

# Sufixo do arquivo gerado ao aplicar a normalização sobre uma planilha enviada.
SUFIXO_SAIDA = "_normalizado"


def _dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = Path(base) / "FaturasEnergia"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


def _arquivo() -> Path:
    return _dir() / "equivalencias.json"


def carregar() -> list[dict]:
    """Lista de {'item': ..., 'item_normalizado': ...}."""
    try:
        data = json.loads(_arquivo().read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [{"item": str(d.get("item", "")).strip(),
                     "item_normalizado": str(d.get("item_normalizado", "")).strip()}
                    for d in data if str(d.get("item", "")).strip()]
    except Exception:
        pass
    return []


def salvar(linhas: list[dict]) -> None:
    limpo = []
    vistos = set()
    for l in linhas:
        item = str(l.get("item", "")).strip()
        norm = str(l.get("item_normalizado", "")).strip()
        chave = item.upper()
        if not item or chave in vistos:
            continue
        vistos.add(chave)
        limpo.append({"item": item, "item_normalizado": norm})
    _arquivo().write_text(json.dumps(limpo, ensure_ascii=False, indent=1), encoding="utf-8")


def mapa() -> dict[str, str]:
    """{ITEM_EM_MAIUSCULAS: item_normalizado} para consulta (só com valor preenchido)."""
    m: dict[str, str] = {}
    for l in carregar():
        k = l["item"].strip().upper()
        v = l["item_normalizado"].strip()
        if k and v:
            m[k] = v
    return m


def aplicar(df_itens, coluna_item: str = "item", coluna_destino: str = "item_normalizado"):
    """
    Preenche `coluna_destino` no DataFrame de itens: valor do mapa (se o item
    existir na tabela) ou o próprio item. Modifica in place e devolve o df.
    """
    if df_itens is None or getattr(df_itens, "empty", True) or coluna_item not in df_itens.columns:
        return df_itens
    m = mapa()
    df_itens[coluna_destino] = df_itens[coluna_item].map(
        lambda v: m.get(str(v).strip().upper(), v))
    return df_itens


# ──────────────────────────────────────────────────────────────────────────────
# Importação de equivalências a partir de uma planilha Excel ou CSV
# ──────────────────────────────────────────────────────────────────────────────
COLUNAS_IMPORTACAO = ("item", "item_normalizado")


def ler_arquivo_importacao(caminho: str) -> list[dict]:
    """
    Lê um .xlsx/.xlsm/.csv externo e devolve as linhas {'item', 'item_normalizado'}
    encontradas nele. O arquivo precisa ter colunas com esses dois nomes de
    cabeçalho exatos (sem diferenciar maiúsculas/espaços nas bordas); levanta
    ValueError, explicitando o que falta, caso contrário. Linhas com 'item'
    vazio são ignoradas e duplicatas de 'item' dentro do próprio arquivo são
    colapsadas (mantém a última ocorrência).
    """
    import pandas as pd

    ext = os.path.splitext(caminho)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(caminho, dtype=str, keep_default_na=False)
    else:
        df = pd.read_excel(caminho, dtype=str, engine="openpyxl")
        df = df.fillna("")

    colmap = {str(c).strip().lower(): c for c in df.columns}
    faltantes = [n for n in COLUNAS_IMPORTACAO if n not in colmap]
    if faltantes:
        raise ValueError(
            "O arquivo precisa ter as colunas " +
            " e ".join(f"'{n}'" for n in COLUNAS_IMPORTACAO) +
            f" — não encontrada(s): {', '.join(faltantes)}.")

    linhas: dict[str, dict] = {}
    for _, row in df.iterrows():
        item = str(row[colmap["item"]]).strip()
        if not item:
            continue
        norm = str(row[colmap["item_normalizado"]]).strip()
        linhas[item.upper()] = {"item": item, "item_normalizado": norm}
    return list(linhas.values())


# ──────────────────────────────────────────────────────────────────────────────
# Aplicar a normalização sobre uma planilha já existente
# ──────────────────────────────────────────────────────────────────────────────
def _resolver_aba_itens(dfs: dict) -> str | None:
    if "itens_fatura" in dfs:
        return "itens_fatura"
    alvo = "itensfatura"
    for aba in dfs:
        if re.sub(r"[\s_]+", "", str(aba)).strip().lower() == alvo:
            return aba
    return None


def aplicar_planilha(caminho_entrada: str, caminho_saida: str) -> list[str]:
    """Lê uma planilha, reaplica a normalização de itens sobre a aba
    'itens_fatura' (coluna 'item_normalizado') e grava em `caminho_saida`."""
    from . import excel_io

    dfs, meta = excel_io.ler_workbook(caminho_entrada)
    aba = _resolver_aba_itens(dfs)
    if aba is None:
        raise ValueError("A planilha não tem uma aba 'itens_fatura'.")
    df = dfs[aba]
    if "item" not in df.columns:
        raise ValueError(f"A aba '{aba}' não tem a coluna 'item'.")
    if "item_normalizado" not in df.columns:
        raise ValueError(f"A aba '{aba}' não tem a coluna 'item_normalizado'.")

    antes = df["item_normalizado"].astype(str).fillna("")
    aplicar(df, "item", "item_normalizado")
    depois = df["item_normalizado"].astype(str).fillna("")
    alterados = int((antes != depois).sum())

    excel_io.escrever_workbook(dfs, meta or {}, caminho_saida)
    return [f"{aba}: {alterados} de {len(df)} linha(s) com 'item_normalizado' atualizado."]


def caminho_saida_padrao(caminho_entrada: str) -> str:
    """'…/x.xlsx' → '…/x_normalizado.xlsx' (mesmo nome, com o sufixo ao final)."""
    base, ext = os.path.splitext(caminho_entrada)
    return f"{base}{SUFIXO_SAIDA}{ext or '.xlsx'}"
