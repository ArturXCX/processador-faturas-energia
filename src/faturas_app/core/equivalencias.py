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


# ──────────────────────────────────────────────────────────────────────────────
# JSON: o formato de troca da tabela de normalização
# ──────────────────────────────────────────────────────────────────────────────
# A tabela é persistida em JSON (`equivalencias.json`) e é também por JSON que
# ela entra e sai do app. A planilha continua aceita como ENTRADA — é convertida
# para o mesmo JSON na importação —, porque montar a lista no Excel é mais
# cômodo do que escrever JSON à mão.
def exportar_json(caminho: str, linhas: list[dict] | None = None) -> int:
    """Grava a tabela em JSON. Devolve quantos pares saíram."""
    dados = carregar() if linhas is None else linhas
    limpo = [{"item": str(l.get("item", "")).strip(),
              "item_normalizado": str(l.get("item_normalizado", "")).strip()}
             for l in dados if str(l.get("item", "")).strip()]
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(limpo, f, ensure_ascii=False, indent=1)
    return len(limpo)


def importar_json(caminho: str) -> tuple[list[dict], list[str]]:
    """
    Lê um JSON de equivalências e devolve `(linhas, relatorio)` sem gravar nada.

    Aceita a lista de objetos `{"item", "item_normalizado"}` e também o formato
    abreviado `{"ITEM ORIGINAL": "ITEM NORMALIZADO"}`, que é o jeito natural de
    escrever isso à mão.
    """
    with open(caminho, "r", encoding="utf-8") as f:
        data = json.load(f)

    linhas: list[dict] = []
    avisos: list[str] = []
    if isinstance(data, dict):
        candidatas = [v for v in data.values()
                      if isinstance(v, list) and v and isinstance(v[0], dict)]
        if candidatas:
            data = max(candidatas, key=len)
        else:
            data = [{"item": k, "item_normalizado": v} for k, v in data.items()]
    if not isinstance(data, list):
        raise ValueError(
            "Esperado uma LISTA de equivalências (ou um objeto "
            '{"item original": "item normalizado"}).')

    vistos = set()
    for i, reg in enumerate(data, start=1):
        if not isinstance(reg, dict):
            avisos.append(f"registro {i} ignorado: não é um objeto.")
            continue
        colmap = {re.sub(r"[\s_]+", "", str(k)).strip().lower(): k for k in reg}
        k_item = colmap.get("item")
        k_norm = colmap.get("itemnormalizado") or colmap.get("normalizado")
        if k_item is None:
            avisos.append(f"registro {i} ignorado: sem o campo 'item'.")
            continue
        item = str(reg[k_item]).strip()
        if not item:
            continue
        chave = item.upper()
        if chave in vistos:
            avisos.append(f"'{item}' aparece mais de uma vez; mantida a última.")
            linhas = [l for l in linhas if l["item"].upper() != chave]
        vistos.add(chave)
        linhas.append({"item": item,
                       "item_normalizado": str(reg.get(k_norm, "")).strip()
                       if k_norm else ""})

    relatorio = [f"{len(linhas)} equivalência(s) lida(s) de {os.path.basename(caminho)}."]
    sem_destino = [l["item"] for l in linhas if not l["item_normalizado"]]
    if sem_destino:
        relatorio.append(f"⚠ {len(sem_destino)} sem 'item_normalizado' — esses itens "
                         f"ficam como estão.")
    relatorio += [f"⚠ {a}" for a in avisos[:15]]
    return linhas, relatorio


def importar_arquivo(caminho: str) -> tuple[list[dict], list[str]]:
    """
    Importa de JSON **ou** de planilha, pela extensão. A planilha é convertida
    para o mesmo formato do JSON — é só um jeito mais cômodo de montar a lista.
    """
    if os.path.splitext(caminho)[1].lower() == ".json":
        return importar_json(caminho)
    linhas = ler_arquivo_importacao(caminho)
    return linhas, [f"{len(linhas)} equivalência(s) lida(s) de "
                    f"{os.path.basename(caminho)} (planilha convertida para JSON)."]
