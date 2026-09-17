"""SANEAGO — fatura ANALÍTICA de órgão público: um bloco por conta (hidrômetro, leituras, consumo, lançamentos, total e
histórico de 6 meses). Vira uma linha de `fatura_agua` por conta (origem = analitica), com itens e histórico.

Formato antigo (2021–2023): leituras/datas em branco, valores sem "R$"; formato novo (2024+): "LEITURA: n DATA: d",
valores "R$1.307,73"."""
from __future__ import annotations

import re

from .base import RE_DATA, RE_MOEDA, Resultado, busca, fechar_fatura, nova_fatura, novo_historico, novo_item, rx
from .texto import competencia, data_iso, inteiro, moeda, sem_acento

_RE_CONTA = rx(r"CONTA\s*N[º°o]?\.?:?\s*(\d{2,8})\s*-\s*(\d)")
_MESES = {"JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
          "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}
_RE_LEITURA = rx(r"^\s*LEITURA\s*:?\s+(?:(\d+)\s+)?DATA\s*:?\s*(?:(" + RE_DATA + r")\s+)?CONSUMO\s*:?\s+(\d+)", re.IGNORECASE | re.MULTILINE)
_RE_LEITURA_ATUAL = rx(r"^\s*LEITURA ATUAL\s*:?\s+(?:(\d+)\s+)?DATA\s*:?\s*(?:(" + RE_DATA + r")\s+)?CONSUMO ESTIMADO\s*:?\s+(\d+)", re.IGNORECASE | re.MULTILINE)


_RE_REF = rx(r"REFER[ÊE]NCIA:?[^\n\d]{0,12}?(?:\d\s+)?(\d{1,2}/\d{4})")    # tolera ruído de OCR ("REFERENCIA: 2 05/2022")
_RE_VALOR_LIVRE = r"-?\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|-?\d+(?:,\d{1,2})?"   # 1.307,73 · 85 · 340,2 · 1.047 (milhar sem centavos)


def _cabecalho(texto: str) -> dict:
    m = _RE_REF.search(texto)
    return {
        "referencia": competencia(m.group(1)) if m else None,
        "pagador": busca(r"[ÓO]RG[ÃA]O PAGADOR:?\s*(\d{3,})", texto),
        "agrupador": busca(r"[ÓO]RG[ÃA]O AGRUPADOR:?\s*(\d{3,})", texto),
        "emissao": data_iso(busca(r"EMISS[ÃA]O DESTE:?\s*(\d{2}/\d{2}/\d{4})", texto)),
    }


def _historico(bloco: str, f: dict) -> list[dict]:
    out = []
    m = rx(r"HIST[ÓO]RICO DE CONSUMO\s*\n(.*?)\n(.*?)\n(.*?)(?:\n|$)").search(bloco)
    if not m:
        return out
    meses = re.findall(r"([A-Za-zçÇ]+)/(\d{4})", m.group(1))
    m3 = [t for t in re.findall(r"\d+", re.sub(r"\bm3\b", "", m.group(2), flags=re.IGNORECASE))]
    vals = [x for x in re.findall(_RE_VALOR_LIVRE, m.group(3)) if x]
    if len(m3) > len(meses):
        m3 = m3[: len(meses)]          # a última coluna é a média
    if len(vals) > len(meses):
        vals = vals[: len(meses)]
    for i, (mes, ano) in enumerate(meses):
        num = _MESES.get(sem_acento(mes).upper())
        if not num:
            continue
        h = novo_historico(f, f"{num:02d}/{ano}", m3[i] if i < len(m3) else None, vals[i] if i < len(vals) else None, "historico")
        if h:
            out.append(h)
    return out


def extrair(doc, arquivo: str) -> Resultado:
    res = Resultado()
    texto = doc.texto.replace("\f", "\n")
    cab = _cabecalho(texto)
    posicoes = [m.start() for m in _RE_CONTA.finditer(texto)]
    if not posicoes:
        res.avisos.append(f"{arquivo}: nenhuma 'CONTA N°' encontrada")
        return res
    for k, ini in enumerate(posicoes):
        fim = posicoes[k + 1] if k + 1 < len(posicoes) else len(texto)
        bloco = texto[ini:fim]
        m = _RE_CONTA.search(bloco)
        f = nova_fatura("SANEAGO", arquivo, doc.usou_ocr, origem="analitica")
        f["conta_formatada"] = f"{m.group(1)}-{m.group(2)}"
        f["conta"] = m.group(1) + m.group(2)
        ref_local = None       # a referência pode mudar no meio do arquivo (mais de um órgão pagador)
        for mm in _RE_REF.finditer(texto[:ini]):
            ref_local = mm.group(1)
        f["competencia"] = competencia(ref_local) or cab["referencia"]
        f["data_emissao"] = cab["emissao"]
        f["nome_cliente"] = busca(r"NOME:\s*(.+?)\s*\n", bloco)
        f["logradouro"] = busca(r"ENDERE[ÇC]O:\s*(.+?)\s*\n", bloco)
        f["hidrometro"] = busca(r"HIDR[ÔO]METRO:?\s*([A-Z0-9]{4,})", bloco)
        f["tipo_consumo"] = busca(r"TIPO DE CONSUMO:?\s*(\d-[A-Za-zçãéí]+)", bloco)
        ml = _RE_LEITURA.search(bloco)
        if ml:
            f["leitura_anterior"], f["data_leitura_anterior"], f["consumo_m3"] = inteiro(ml.group(1)), data_iso(ml.group(2)), inteiro(ml.group(3))
        ma = _RE_LEITURA_ATUAL.search(bloco)
        if ma:
            f["leitura_atual"], f["data_leitura_atual"] = inteiro(ma.group(1)), data_iso(ma.group(2))
            f["observacao"] = f"consumo estimado {ma.group(3)}"
        f["consumo_faturado_m3"] = f["consumo_m3"]
        f["valor_total"] = moeda(busca(r"VALOR TOTAL \(R\$\)\s*R?\$?\s*(" + _RE_VALOR_LIVRE + r")", bloco))
        itens = []
        lanc = rx(r"LAN[ÇC]AMENTOS(.*?)VALOR TOTAL \(R\$\)", re.IGNORECASE | re.DOTALL).search(bloco)
        if lanc:
            ordem = 0
            for ln in lanc.group(1).splitlines():
                mi = re.search(r"^\s*(.+?)\s+R?\$?\s*(-?[\d.]*\d(?:,\d{1,2})?)\s*$", ln)
                if mi and "DESCRI" not in sem_acento(mi.group(1)).upper():
                    ordem += 1
                    codigo, desc = None, mi.group(1).strip()
                    mc = re.match(r"^(\d{2,4})\s*-\s*(.+)$", desc)
                    if mc:
                        codigo, desc = mc.group(1), mc.group(2)
                    itens.append(novo_item(f, ordem, desc, mi.group(2), codigo))
        fechar_fatura(f, itens, "")
        f["observacao"] = "; ".join(x for x in (f.get("observacao"), f"órgão pagador {cab['pagador'] or '?'} · agrupador {cab['agrupador'] or '?'}") if x)
        res.faturas.append(f)
        res.itens.extend(itens)
        res.historico.extend(_historico(bloco, f))
    return res
