"""SAAE Abadiânia — conta com canhoto (INSCRIÇÃO · MÊS FAT · NF/CONTA · VENCIMENTO · VALOR), itens codificados
(001 TARIFA DE AGUA…), hidrometria e últimos consumos. O acervo de 2021 é digitalizado (OCR, extração parcial)."""
from __future__ import annotations

import re

from .base import RE_DATA, RE_MOEDA, Resultado, busca, fechar_fatura, nova_fatura, novo_historico, novo_item, rx
from .texto import competencia, competencia_por_caminho, inteiro, moeda


def _ocr(doc, arquivo: str, fornecedor: str) -> Resultado:
    res = Resultado()
    texto = doc.texto.replace("\f", "\n")
    f = nova_fatura(fornecedor, arquivo, True)
    f["numero_fatura"] = busca(r"\b(2[0-9]\d{7})\b", texto)
    f["conta_formatada"] = busca(r"\b(\d{4,7}\.\d)\b", texto)
    f["competencia"] = competencia_por_caminho(arquivo) or competencia(busca(r"(?<!\d/)\b(0[1-9]|1[0-2])/(202\d)\b", texto, grupo=0))
    mv = re.search(r"(" + RE_DATA + r")\s+[—–-]?\s*(\d{1,3}(?:\.\d{3})*,\d{2})", texto)
    if mv:
        f["data_vencimento"], f["valor_total"] = mv.group(1), moeda(mv.group(2))
    f["nome_cliente"] = busca(r"(F[OÓ]RUM DE ABAD[A-Z|]+)", texto)
    f["leitura_anterior"] = inteiro(busca(r"ANTERIOR[,.:]?\s*(\d{3,6})", texto))
    f["consumo_m3"] = inteiro(busca(r"CONSUMO[.,:]?\s*(\d{1,3})\b", texto))
    itens = []
    for k, mi in enumerate(re.finditer(r"^\s*[|+]?\s*(\d{2})\s*[|/]*\s*([A-Z][^\n]*?)\s+(\d[\d.]*,?\d{2})\s*$", texto, re.MULTILINE), 1):
        raw = mi.group(3)
        val = moeda(raw) if "," in raw else float(raw.replace(".", "")[:-2] + "." + raw[-2:])
        itens.append(novo_item(f, k, mi.group(2).strip(" |"), val, mi.group(1)))
    f["observacao"] = "PDF digitalizado: lido por OCR (parcial)"
    fechar_fatura(f, itens, arquivo)
    res.faturas.append(f)
    res.itens.extend(itens)
    return res


def extrair(doc, arquivo: str, fornecedor: str = "SAAE_ABADIANIA") -> Resultado:
    if doc.usou_ocr:
        return _ocr(doc, arquivo, fornecedor)
    res = Resultado()
    texto = doc.texto.replace("\f", "\n")
    f = nova_fatura(fornecedor, arquivo, doc.usou_ocr)
    m = re.search(r"(\d{6,8}\.\d)\s+([A-Z]{3}/\d{4})\s+(\d{8,})\s+(" + RE_DATA + r")\s+(" + RE_MOEDA + ")", texto)
    if m:
        f["conta_formatada"], f["competencia"], f["numero_fatura"], f["data_vencimento"], f["valor_total"] = \
            m.group(1), competencia(m.group(2)), m.group(3), m.group(4), moeda(m.group(5))
    else:
        m2 = re.search(r"^\s*(\d{6,8}\.\d)\s+\S+\s+\S+\s+(?:RES\s+COM\s+IND\s+PUB\s+OUT\s+)?(\d{8,})\s+(\d{2}/\d{2}/\d{2,4})\s+([A-Z]{3}/\d{4})",
                       texto, re.MULTILINE)
        if m2:
            f["conta_formatada"], f["numero_fatura"], f["data_emissao"], f["competencia"] = m2.group(1), m2.group(2), m2.group(3), competencia(m2.group(4))
        mv = rx(r"VENCIMENTO\s+(" + RE_DATA + r")\s+VALOR\s+R\$\s+(" + RE_MOEDA + ")").search(texto)
        if mv:
            f["data_vencimento"], f["valor_total"] = mv.group(1), moeda(mv.group(2))
    f["conta_formatada"] = f["conta_formatada"] or busca(r"INSCRI[ÇC][ÃA]O[^\n]*\n\s*(\d{6,8}\.\d)", texto)
    f["numero_fatura"] = f["numero_fatura"] or busca(r"CONTA\s+(\d{8,})", texto)
    f["data_emissao"] = f["data_emissao"] or busca(r"(\d{8,})\s+(\d{2}/\d{2}/\d{2})\s+[A-Z]{3}/\d{4}", texto, grupo=2)
    f["nome_cliente"] = busca(r"NOME:\s*(.+?)\s{2,}", texto) or busca(r"^\s*(F[ÓO]RUM[^\n]*?)\s*$", texto, flags=re.IGNORECASE | re.MULTILINE)
    f["logradouro"] = busca(r"END:\s*(.+?)\s{2,}", texto)
    d2 = r"\d{2}/\d{2}/\d{2,4}"
    mh = re.search(r"^\s*([A-Z0-9]{6,})\s+(" + d2 + r")\s+(\d+)\s+(" + d2 + r")\s+(\d+)\s+(" + d2 + r")\s+(\d+)\s+(\d+)", texto, re.MULTILINE)
    if mh:
        f["hidrometro"], f["leitura_anterior"], f["data_leitura_anterior"] = mh.group(1), inteiro(mh.group(3)), mh.group(4)
        f["leitura_atual"], f["data_leitura_atual"], f["consumo_m3"], f["dias"] = inteiro(mh.group(5)), mh.group(6), inteiro(mh.group(7)), inteiro(mh.group(8))
    itens = []
    for k, mi in enumerate(re.finditer(r"(?:^|\s)(?:(\d{3})\s+)?((?:TARIFA|TAXA|SERV|MULTA|JUROS)[^\n]*?)\s+(" + RE_MOEDA + r")[ \t]*$", texto, re.MULTILINE), 1):
        itens.append(novo_item(f, k, mi.group(2), mi.group(3), mi.group(1)))
    f["categoria"] = "PUB"
    fechar_fatura(f, itens, arquivo)
    res.faturas.append(f)
    res.itens.extend(itens)
    for mh2 in re.finditer(r"^\s*([A-Z]{3}/\d{2})\s+(\d+)\s+(\d{3})\s+(\d{2,3})\b", texto, re.MULTILINE):
        h = novo_historico(f, mh2.group(1), mh2.group(2), None, None)
        if h:
            res.historico.append(h)
    return res
