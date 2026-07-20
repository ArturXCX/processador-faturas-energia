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
from pathlib import Path


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
