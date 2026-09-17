"""DUAM (Documento Único de Arrecadação Municipal): SAAE Corumbá (layout 2021–2025 e o novo de 2026) e SAAE Mineiros."""
from __future__ import annotations

import re

from .base import RE_DATA, RE_MOEDA, Resultado, apos, busca, fechar_fatura, nova_fatura, novo_item, rx, trecho
from .texto import competencia, inteiro, moeda


def _antigo(texto: str, f: dict) -> list[dict]:
    f["numero_fatura"] = busca(r"N\.\s*(?:Duam:?)?\s*(\d{5,})", texto)
    mr = rx(r"Refer[êe]ncia:?\s*(\d{1,2})\s*/\s*(\d{4})").search(texto)
    if mr:
        f["competencia"] = competencia(f"{mr.group(1)}/{mr.group(2)}")
    f["conta_formatada"] = busca(r"N[º°o] Conta:\s*(\d+)", texto)
    f["nome_cliente"] = busca(r"\bNome:\s*(.+?)(?:\s{2,}|\n)", texto)
    f["logradouro"] = busca(r"Endere[çc]o:\s*(.+?)(?:\s{2,}N[º°o] hidr|\n)", texto)
    f["hidrometro"] = busca(r"N[º°o] hidr[ôo]metro:\s*([A-Z0-9]{5,})", texto)
    f["leitura_atual"] = inteiro(busca(r"Leitura do m[êe]s:\s*(\d+)", texto))
    f["leitura_anterior"] = inteiro(busca(r"Leitura do m[êe]s anterior:\s*(\d+)", texto))
    f["consumo_m3"] = inteiro(busca(r"Consumo do m[êe]s:\s*(\d+)", texto))
    f["data_emissao"] = busca(r"Data (?:de )?Emiss[ãa]o:\s*(" + RE_DATA + ")", texto) or busca(r"Data Impress[ãa]o:\s*(" + RE_DATA + ")", texto)
    f["data_vencimento"] = apos(r"Vencimento:", texto, r"(" + RE_DATA + ")")
    f["valor_total"] = moeda(apos(r"\(-\) Valor do Pagamento", texto, r"R\$\s*(" + RE_MOEDA + ")"))
    multa = moeda(apos(r"\(\+\) Mora/Multa", texto, r"R\$\s*(" + RE_MOEDA + ")") or "0")
    juros = moeda(apos(r"\(\+\) Juros", texto, r"R\$\s*(" + RE_MOEDA + ")") or "0")
    f["valor_multa_juros"] = round((multa or 0) + (juros or 0), 2) if (multa or juros) else None
    f["categoria"] = "PUB"
    itens = []
    bloco = trecho(texto, r"C[óo]d\.\s+Receita", r"(?:AUTARQUIA|PREFEITURA|DUAM|SERVI[ÇC]O AUT)")
    for k, mi in enumerate(re.finditer(r"^\s*(\d{1,5})\s+(.+?)\s+(" + RE_MOEDA + r")\s*$", bloco, re.MULTILINE), 1):
        itens.append(novo_item(f, k, mi.group(2), mi.group(3), mi.group(1)))
    return itens


def _novo(texto: str, f: dict) -> list[dict]:
    m = rx(r"N\. Duam\s+Refer[êe]ncia\s+Parcela\s+Categoria\s+Hidr[ôo]metro\s*\n\s*(\d+)\s+(\d+)\s+(\d{1,2})\s*/\s*(\d{4})\s+(\d+)\s+(\w+)\s+([A-Z0-9]{5,})").search(texto)
    if m:
        f["numero_fatura"], f["competencia"], f["categoria"], f["hidrometro"] = m.group(2), competencia(f"{m.group(3)}/{m.group(4)}"), m.group(6), m.group(7)
    ml = rx(r"CCI\s+ID Fatura\s+Leitura Atual[^\n]*\n\s*(\d+)\s+(\d+)\s+(\d+)\s+(" + RE_DATA + r")\s+(\d+)\s+(" + RE_DATA + r")\s+(\d+)").search(texto)
    if ml:
        f["conta_formatada"], f["leitura_atual"], f["data_leitura_atual"] = ml.group(1), inteiro(ml.group(3)), ml.group(4)
        f["leitura_anterior"], f["data_leitura_anterior"], f["consumo_m3"] = inteiro(ml.group(5)), ml.group(6), inteiro(ml.group(7))
        f["numero_fatura"] = f["numero_fatura"] or ml.group(2)
    f["conta_formatada"] = f["conta_formatada"] or busca(r"CCI:\s*(\d+)", texto)
    mv = rx(r"\bValor\s+Vencimento\s*\n\s*R\$\s*(" + RE_MOEDA + r")\s+(" + RE_DATA + ")").search(texto)
    if mv:
        f["valor_total"], f["data_vencimento"] = moeda(mv.group(1)), mv.group(2)
    f["valor_total"] = f["valor_total"] if f["valor_total"] is not None else moeda(busca(r"TOTAL A PAGAR\s+R\$\s*(" + RE_MOEDA + ")", texto))
    f["nome_cliente"] = busca(r"Contribuinte\s*\n\s*(.+?)\s*\n", texto)
    f["logradouro"] = busca(r"Endere[çc]o\s*\n[^\n]*?\d{2}\.\*{3}\.\*{3}/\d{4}-\d{2}\s+(.+?)\s*\n", texto)
    itens = []
    bloco = trecho(texto, r"Composi[çc][ãa]o do Valor", r"TOTAL A PAGAR")
    for k, mi in enumerate(re.finditer(r"^\s*(.+?)\s+R\$\s*(" + RE_MOEDA + r")\s*$", bloco, re.MULTILINE), 1):
        itens.append(novo_item(f, k, mi.group(1), mi.group(2)))
    return itens


def _ocr(texto: str, f: dict) -> list[dict]:
    """Guia digitalizada (Mineiros 2026): rótulos e valores espalhados; extração parcial."""
    f["conta_formatada"] = (busca(r"N[º°o]?\s*Conta:?\s*(\d{3,6})\b", texto) or busca(r"\b(0\d{5})\b", texto)
                            or busca(r"N[º°o]\s*-?\s*CONTA[^\n]*\n(?:[^\n]*\n){0,2}?[^\n]*?\b(\d{4,6})\b", texto))
    mr = rx(r"M[ÊE]S\s*/?\s*ANO\s*REF\.?[^\n]*\n(?:[^\n]*\n){0,3}?[^\n]*?(\d{1,2}/\d{4})").search(texto)
    if mr:
        f["competencia"] = competencia(mr.group(1))
    f["data_vencimento"] = busca(r"VEN[CF]IMENTO[^\n]*\n(?:[^\n]*\n){0,3}?[^\n]*?(" + RE_DATA + ")", texto)
    f["valor_total"] = moeda(busca(r"(?:Valor a pagar|TOTAL\s*A\s*PAG'?AR)[^\n]*\n(?:[^\n]*\n){0,3}?[^\n]*?(" + RE_MOEDA + ")", texto))
    ml = rx(r"LEIT\.?:?\s*ANTERIOR[^\n]*\n\s*(\d{3,6})\s+(\d{3,6})").search(texto)
    if ml:
        f["leitura_anterior"], f["leitura_atual"] = inteiro(ml.group(1)), inteiro(ml.group(2))
        f["consumo_m3"] = f["leitura_atual"] - f["leitura_anterior"]
    f["nome_cliente"] = busca(r"(TRIBUNAL\s+DE\s+JUSTICA\s+DO\s+ESTADO\s+DE\s+GOIAS)", texto)
    f["categoria"] = busca(r"\b(P[úu]blica)\b", texto)
    itens = []
    L = texto.splitlines()
    for i, ln in enumerate(L):
        m = re.search(r"(?:(\d{3,5})\s+)?((?:TARIFA|TAXA|AGUA|ÁGUA|COLETA)[A-ZÁÉÍÓÚÇ .\-]*?)\s+(\d[\d.]*,\d{2}|\d{4,6})(?:\s+\S{1,2})?\s*$", ln)
        if not m:
            mk = re.search(r"((?:TARIFA|TAXA|AGUA|ÁGUA|COLETA)[A-ZÁÉÍÓÚÇ .\-]*)", ln)
            if mk and i + 1 < len(L):
                mv = re.search(r"(\d[\d.]*,\d{2})\s*$", L[i + 1])
                if mv:
                    itens.append(novo_item(f, len(itens) + 1, mk.group(1), mv.group(1)))
            continue
        raw = m.group(3)
        val = moeda(raw) if "," in raw else float(raw[:-2] + "." + raw[-2:])
        itens.append(novo_item(f, len(itens) + 1, m.group(2), val, m.group(1)))
    f["observacao"] = "PDF digitalizado: lido por OCR (parcial)"
    return itens


def extrair(doc, arquivo: str, fornecedor: str) -> Resultado:
    res = Resultado()
    texto = doc.texto.replace("\f", "\n")
    f = nova_fatura(fornecedor, arquivo, doc.usou_ocr)
    if doc.usou_ocr:
        itens = _antigo(texto, f) if re.search(r"N\.\s*Duam", texto) else []
        if not f.get("conta_formatada") or f.get("valor_total") is None:
            f2 = nova_fatura(fornecedor, arquivo, True)
            itens2 = _ocr(texto, f2)
            for k, v in f2.items():
                if v is not None and f.get(k) is None:
                    f[k] = v
            itens = itens or itens2
        f["observacao"] = f.get("observacao") or "PDF digitalizado: lido por OCR"
    elif re.search(r"ID Fatura|Composi[çc][ãa]o\s+do Valor", texto):
        itens = _novo(texto, f)
    else:
        itens = _antigo(texto, f)
    fechar_fatura(f, itens, arquivo)
    if f.get("valor_multa_juros"):
        f["valor_total"] = f["valor_total"]
    res.faturas.append(f)
    res.itens.extend(itens)
    return res
