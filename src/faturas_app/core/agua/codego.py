"""CODEGO — porte do extrator original (sem PDF no acervo atual para validar; marcado como experimental)."""
from __future__ import annotations

import re

from .base import RE_DATA, RE_MOEDA, Resultado, busca, fechar_fatura, nova_fatura, novo_item, rx
from .texto import competencia, inteiro, moeda, sem_acento

_MESES = {"JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
          "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}


def extrair(doc, arquivo: str, fornecedor: str = "CODEGO") -> Resultado:
    res = Resultado()
    texto = doc.texto.replace("\f", "\n")
    f = nova_fatura(fornecedor, arquivo, doc.usou_ocr)
    m = rx(r"R\$?\s*(" + RE_MOEDA + r")\s+(" + RE_DATA + r")\s+([\w/-]+)\s*\n\s*Pagador").search(texto)
    if m:
        f["valor_total"], f["data_vencimento"], f["numero_fatura"] = moeda(m.group(1)), m.group(2), m.group(3)
    f["hidrometro"] = busca(r"Hidrometro:\s*([A-Z0-9]+)", texto)
    f["conta_formatada"] = f["hidrometro"]
    mm = rx(r"Hidrometro:[^\n]*\n\s*([A-Za-zç]+)/(\d{4})").search(texto)
    if mm and sem_acento(mm.group(1)).upper() in _MESES:
        f["competencia"] = f"{mm.group(2)}-{_MESES[sem_acento(mm.group(1)).upper()]:02d}"
    f["nome_cliente"] = busca(r"Pagador\s+(.*?)\s*C[óo]digo de Baixa", texto)
    f["consumo_m3"] = inteiro(busca(r"Consumo:\s*M[³3]\s*(\d+)", texto))
    itens = []
    for k, (rot, pad) in enumerate((("Água", r"Agua:\s*(" + RE_MOEDA + ")"), ("Coleta/Esgoto", r"Coleta/Esgoto:\s*(" + RE_MOEDA + ")")), 1):
        v = busca(pad, texto)
        if v:
            itens.append(novo_item(f, k, rot, v))
    f["observacao"] = "extrator experimental (sem acervo de validação)"
    fechar_fatura(f, itens, arquivo)
    res.faturas.append(f)
    res.itens.extend(itens)
    return res
