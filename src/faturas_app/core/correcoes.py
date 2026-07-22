"""
Correções pontuais de extração, escopadas por `id_fatura`.

Alguns PDFs antigos (ou escaneados/OCR) produzem, em faturas ESPECÍFICAS, um
nome de item quebrado (quebra de linha no PDF fundindo a unidade ao nome, ou
ruído de OCR) ou um campo de medição vazio preenchido com valor errado. Estas
correções reescrevem SÓ as linhas das faturas listadas em `resources/correcoes.json`.

Princípio-chave (segurança): o casamento é sempre escopado ao `id_fatura`, então
corrigir uma fatura NUNCA altera as demais. O nome do item é casado de forma
tolerante (maiúsculas, sem acento, sem espaços) para absorver variações de OCR;
se o item já sair correto, a correção simplesmente não casa (no-op).
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from importlib import resources


def _chave(texto) -> str:
    """Normaliza para casamento tolerante: maiúsculas, sem acento, sem espaços."""
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", "", s).upper()


@lru_cache(maxsize=1)
def _dados() -> dict:
    with resources.files("faturas_app.resources").joinpath("correcoes.json").open(
            "r", encoding="utf-8") as f:
        bruto = json.load(f)
    # itens: {(id_fatura, chave(item_estranho)): item_correto}
    itens: dict[tuple[str, str], str] = {}
    for reg in bruto.get("itens", []):
        itens[(reg["id_fatura"], _chave(reg["item_estranho"]))] = reg["item_correto"]
    # medicao: {(id_fatura, chave(Grandezas), chave(Postos horarios)): {campo: valor}}
    medicao: dict[tuple[str, str, str], dict] = {}
    for reg in bruto.get("medicao", []):
        medicao[(reg["id_fatura"], _chave(reg["Grandezas"]),
                 _chave(reg["Postos horarios"]))] = reg["set"]
    return {"itens": itens, "medicao": medicao}


def corrigir_itens(linhas: list[dict]) -> None:
    """Reescreve o nome (`item`) das linhas cujo (id_fatura, item) está na tabela."""
    itens = _dados()["itens"]
    if not itens:
        return
    for row in linhas:
        correto = itens.get((row.get("id_fatura"), _chave(row.get("item"))))
        if correto is not None:
            row["item"] = correto


def corrigir_medicao(linhas: list[dict]) -> None:
    """Corrige campos de linhas de medição de faturas específicas (campo vazio
    preenchido com valor errado)."""
    medicao = _dados()["medicao"]
    if not medicao:
        return
    for row in linhas:
        campos = medicao.get((row.get("id_fatura"), _chave(row.get("Grandezas")),
                              _chave(row.get("Postos horarios"))))
        if campos:
            row.update(campos)


def aplicar(resultado: dict) -> None:
    """Aplica as correções de itens e medição ao resultado de UMA fatura (in place)."""
    if resultado.get("itens_fatura"):
        corrigir_itens(resultado["itens_fatura"])
    if resultado.get("medicao"):
        corrigir_medicao(resultado["medicao"])
