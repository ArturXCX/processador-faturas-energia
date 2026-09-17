"""SAAE Leopoldo de Bulhões — guia com número, código de ligação, itens, datas de leitura, leituras em m³ e histórico de
12 meses. Guias de 2024 trazem uma camada de texto de scanner (rótulos e valores em linhas separadas, erros de OCR);
as de 2025–2026 são PDFs limpos."""
from __future__ import annotations

import re

from .base import RE_DATA, RE_MOEDA, Resultado, busca, fechar_fatura, nova_fatura, novo_historico, novo_item, rx, trecho
from .texto import inteiro, moeda, sem_acento

_MESES = {"JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
          "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}
_M3 = r"(?:m³|m3|M3)?"


def _itens(bloco: str, f: dict) -> list[dict]:
    itens = []
    pares = re.findall(r"^[ \t]*([A-ZÁÉÍÓÚÇÃÕ][A-ZÁÉÍÓÚÇÃÕ /.\-]{3,}?)[ \t]+(?:R\$[ \t]*)?(" + RE_MOEDA + r")[ \t]*$", bloco, re.MULTILINE)
    if pares:
        return [novo_item(f, k, d, v) for k, (d, v) in enumerate(pares, 1)]
    # camada de scanner: valores e rótulos em linhas separadas, na mesma ordem
    rotulos = [" ".join(l.split()) for l in bloco.splitlines() if re.match(r"^[ \t]*[A-ZÁÉÍÓÚÇÃÕ][A-ZÁÉÍÓÚÇÃÕ /.\-]{3,}[ \t]*$", l)]
    valores = re.findall(r"^[ \t]*(?:R\$[ \t]*)?(" + RE_MOEDA + r")[ \t]*$", bloco, re.MULTILINE)
    for k, (d, v) in enumerate(zip(rotulos, valores), 1):
        itens.append(novo_item(f, k, d, v))
    return itens


def extrair(doc, arquivo: str, fornecedor: str = "SAAE_LEOPOLDO_BULHOES") -> Resultado:
    res = Resultado()
    texto = doc.texto.replace("\f", "\n")
    f = nova_fatura(fornecedor, arquivo, doc.usou_ocr)
    mg = re.search(r"\b(\d{8,13})-(\d)\b", texto)
    if mg:
        f["numero_fatura"] = mg.group(1) + mg.group(2)
    f["conta_formatada"] = busca(r"C[OÓ]{1,2}D\.?\s*LIG\.?:?\s*(\d{3,6}-\d)", texto)
    mm = re.search(r"([A-Za-zç]+)/(\d{4})", trecho(texto, r"M[ÊE]S\s*/?\s*I?\s*ANO", r"CATEGORIA") or "")
    if mm and sem_acento(mm.group(1)).upper() in _MESES:
        f["competencia"] = f"{mm.group(2)}-{_MESES[sem_acento(mm.group(1)).upper()]:02d}"
    if not f["competencia"]:
        mm = re.search(r"([A-Za-zç]+)[l/](\d{4})", texto)
        if mm and sem_acento(mm.group(1)).upper() in _MESES:
            f["competencia"] = f"{mm.group(2)}-{_MESES[sem_acento(mm.group(1)).upper()]:02d}"
    f["nome_cliente"] = busca(r"^\s*(TR[IÍ]BUNAL[^\n]+?)\s*(?:M[ÊE]S / ANO)?\s*$", texto, flags=re.IGNORECASE | re.MULTILINE)
    f["logradouro"] = busca(r"^\s*((?:RUA|AV|PUA)[^\n]*?CEP:?\s*\d{5,8})", texto, flags=re.IGNORECASE | re.MULTILINE) \
        or busca(r"^\s*((?:RUA|AV|PUA)\s[^\n]*?)\s{3,}", texto, flags=re.IGNORECASE | re.MULTILINE)
    f["data_emissao"] = busca(r"N[úu]m[eo]ro da guia[^\n]*\n(?:[^\n]*\n){0,5}?[^\n]*?(" + RE_DATA + ")", texto)
    md = rx(r"Data da leitura anterior\s+Data da leitura[^\n]*\n([^\n]+)").search(texto)
    if md:
        toks = re.findall(RE_DATA + r"|R\$\s*" + RE_MOEDA, md.group(1))
        datas = [t for t in toks if "/" in t]
        vals = [t for t in toks if "R$" in t]
        if datas:
            f["data_leitura_anterior"] = datas[0]
            f["data_leitura_atual"] = datas[1] if len(datas) > 1 else None
            f["data_vencimento"] = datas[-1] if len(datas) >= 3 else None
            if len(datas) == 4:
                f["data_emissao"] = datas[2]
        if vals:
            f["valor_total"] = moeda(vals[-1])
    if not f["data_vencimento"]:
        f["data_vencimento"] = busca(r"Vencimento[^\n]*\n(?:[^\n]*\n){0,2}?[^\n]*?(" + RE_DATA + ")", texto)
    if f["valor_total"] is None:
        f["valor_total"] = moeda(busca(r"Valor\s+[àåa]\s+pagar[^\n]*\n(?:[^\n]*\n){0,2}?[^\n]*?(" + RE_MOEDA + ")", texto))
    ml = rx(r"Leitura anterior\s+Leitura atual[^\n]*\n\s*(\d+)\s*" + _M3 + r"\s+(\d+)\s*" + _M3 + r"\s+(\d+)\s*" + _M3 + r"\s+(\d+)\s*" + _M3 + r"\s+(\d+)\s*" + _M3 + r"\s+(\S+)").search(texto)
    if ml:
        f["leitura_anterior"], f["leitura_atual"], f["consumo_m3"], f["consumo_faturado_m3"] = inteiro(ml.group(1)), inteiro(ml.group(2)), inteiro(ml.group(3)), inteiro(ml.group(4))
        ocor = ml.group(6)
        resto = texto[ml.end(): ml.end() + 120].strip()
        if resto.startswith("-"):
            ocor += " " + resto.splitlines()[0].strip()
        f["tipo_consumo"] = ocor
    else:
        ml = re.search(r"(\d{2,6})\s+M3\s+(\d{2,6})\s+M3\s+(\d{1,4})\s+M3", texto)
        if ml:
            f["leitura_anterior"], f["leitura_atual"], f["consumo_m3"] = inteiro(ml.group(1)), inteiro(ml.group(2)), inteiro(ml.group(3))
    f["hidrometro"] = busca(r"No\. do hidr[ôo]metro[^\n]*\n\s*([A-Z0-9]{6,})", texto)
    mc = rx(r"RES\.?\s+COM\.?\s+IND\.?\s+PU[BR]\.?\s+[CO]UT\s*\n\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)").search(texto)
    if mc:
        n = [int(x) for x in mc.groups()]
        f["categoria"] = ["RES", "COM", "IND", "PUB", "OUT"][n.index(max(n))] if any(n) else None
    itens = _itens(trecho(texto, r"DESCRI[ÇC][ÃA]O\s+VALOR", r"(?:Data da leitura anterior|Valor\s+[àåa]\s+pagar)"), f)
    fechar_fatura(f, itens, arquivo)
    res.faturas.append(f)
    res.itens.extend(itens)
    hist = trecho(texto, r"[Dd]ados das 12", r"(?:Reservat|Par[âa]metro)")
    for mh in re.finditer(r"^\s*(\d{2}(?:/\d{4})?)\s+(\d+)\s+(\d+)\s+([\d.,]+)\s*(?:\S.*)?$", hist, re.MULTILINE):
        comp = mh.group(1)
        if "/" not in comp:
            continue
        h = novo_historico(f, comp, mh.group(2), None, None)
        if h:
            res.historico.append(h)
    return res
