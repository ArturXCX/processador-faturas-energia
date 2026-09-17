"""Família "GSAN" (mesmo sistema de faturamento): Águas de Ipameri, Buriti Alegre Ambiental, São Simão Saneamento
Ambiental e SAE Catalão. Layout: canhoto no rodapé com "FATURA: MM/AAAA Nº n VENCIMENTO: data VALOR (R$): v",
"MATRÍCULA: m DÍGITO: d", itens à direita ("DESCRIÇÃO DOS ITENS FATURADOS … TOTAL A PAGAR") e histórico de consumo.

São Simão usou até 2024 (e de novo em 2026) o modelo "Nota Fiscal Fatura de Serviços" (Id, Seq, MATRÍCULA: n-d,
"Leitura ant. / Leitura atual / Consumo real / Consumo fat."), tratado em `_nota_fiscal`."""
from __future__ import annotations

import re

from .base import (RE_DATA, RE_MOEDA, Resultado, busca, categoria_por_contagem, coluna_de, fechar_fatura,
                   itens_coluna_direita, linhas, nova_fatura, novo_historico, novo_item, rx, trecho)
from .texto import competencia, inteiro, moeda

_LETRAS = r"[A-Za-zÀ-ÿ]+"


def _bloco_cliente(L: list[str], f: dict, parar: str = "CADASTRO") -> None:
    """Nome e endereço no bloco do topo (coluna da esquerda; a da direita fica a 4+ espaços)."""
    chave = (f.get("nome_cliente") or "TRIBUNAL FORUM").split()[0].upper()
    for i, ln in enumerate(L[:30]):
        esq = re.match(r"^\s*(.+?)(?:\s{4,}|\s*$)", ln)
        if not esq:
            continue
        s = " ".join(esq.group(1).split())
        if s.upper().startswith(chave) or s.upper().startswith(("TRIBUNAL", "FORUM", "FÓRUM")):
            f["nome_cliente"] = s
            partes = []
            for lx in L[i + 1: i + 7]:
                m2 = re.match(r"^\s*(.+?)(?:\s{4,}|\s*$)", lx)
                seg = " ".join(m2.group(1).split()) if m2 else ""
                if not seg or seg.lower().startswith("www") or "VIA DO" in seg.upper():
                    continue
                if parar in seg.upper() or "MATR" in seg.upper():
                    break
                partes.append(seg)
            f["logradouro"] = " ".join(partes) or None
            return


def _nota_fiscal(doc, arquivo: str, fornecedor: str) -> Resultado:
    res = Resultado()
    texto = doc.texto.replace("\f", "\n")
    L = linhas(doc.texto)
    f = nova_fatura(fornecedor, arquivo, doc.usou_ocr)
    f["numero_fatura"] = busca(r"\bId:\s*(\d+)", texto)
    mm = rx(r"MATR[ÍI]CULA:\s*(\d+)\s*-\s*(\d)").search(texto)
    if mm:
        f["conta_formatada"], f["conta"] = f"{mm.group(1)}-{mm.group(2)}", mm.group(1) + mm.group(2)
    f["competencia"] = competencia(busca(r"M[ÊE]S\s*/\s*ANO\s*\n(?:[^\n]*\n){0,2}?[^\n]*?(\d{2}/\d{4})", texto))
    for i, ln in enumerate(L):
        if "MATR" in ln.upper() and i + 1 < len(L):
            m2 = re.match(r"^\s*(.+?)(?:\s{4,}|\s*$)", L[i + 1])
            if m2:
                f["nome_cliente"] = " ".join(m2.group(1).split())
                partes = []
                for lx in L[i + 2: i + 6]:
                    m3 = re.match(r"^\s*(.+?)(?:\s{4,}|\s*$)", lx)
                    seg = " ".join(m3.group(1).split()) if m3 else ""
                    if seg and "DESCRI" not in seg.upper() and not re.match(r"^(RES|\d{3})\b", seg) and not re.fullmatch(r"\d{2}/\d{4}", seg):
                        partes.append(seg)
                f["logradouro"] = " ".join(partes) or None
            break
    itens = []
    bloco = trecho(texto, r"DESCRI[ÇC][ÃA]O\s+VALOR", r"Data\s+de\s+Leitura")
    for k, mi in enumerate(re.finditer(r"^\s*(.+?)\s{2,}(-?" + RE_MOEDA + r")\s*$", bloco, re.MULTILINE), 1):
        itens.append(novo_item(f, k, mi.group(1), mi.group(2)))
    md = rx(r"Data de Leitura[^\n]*\n([^\n]+)").search(texto)
    if md:
        datas = re.findall(RE_DATA, md.group(1))
        vals = re.findall(r"R\$\s*(" + RE_MOEDA + ")", md.group(1))
        if datas:
            f["data_leitura_atual"] = datas[0]
            f["data_vencimento"] = datas[-1] if len(datas) > 1 else None
        if vals:
            f["valor_total"] = moeda(vals[-1])
    f["data_vencimento"] = f["data_vencimento"] or busca(r"Vencimento:\s*(" + RE_DATA + ")", texto)
    f["valor_total"] = f["valor_total"] if f["valor_total"] is not None else moeda(busca(r"Valor a pagar:\s*R\$\s*(" + RE_MOEDA + ")", texto))
    ml = rx(r"Leitura ant\.[^\n]*\n\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(" + _LETRAS + ")").search(texto)
    if ml:
        f["leitura_anterior"], f["leitura_atual"], f["consumo_m3"], f["consumo_faturado_m3"], f["tipo_consumo"] = \
            inteiro(ml.group(1)), inteiro(ml.group(2)), inteiro(ml.group(3)), inteiro(ml.group(4)), ml.group(6)
    f["hidrometro"] = busca(r"No\. do hidr[ôo]metro[^\n]*\n\s*([A-Z0-9]{6,})", texto)
    f["categoria"] = categoria_por_contagem(texto)
    fechar_fatura(f, itens, arquivo)
    res.faturas.append(f)
    res.itens.extend(itens)
    hist = trecho(texto, r"Hist[óo]rico de consumo", r"CARACTER[ÍI]STICAS")
    for mh in re.finditer(r"^\s*(\d{2}/\d{4})\s+(" + _LETRAS + r")\s+((?:\d+\s+)*\d+)", hist, re.MULTILINE):
        nums = mh.group(3).split()
        h = novo_historico(f, mh.group(1), nums[-1], None, mh.group(2))
        if h:
            res.historico.append(h)
    return res


def extrair(doc, arquivo: str, fornecedor: str) -> Resultado:
    texto = doc.texto.replace("\f", "\n")
    if re.search(r"Nota\s+Fiscal\s+Fatura|Leitura ant\.", texto) and not re.search(r"DESCRI[ÇC][ÃA]O\s+DOS\s+ITENS", texto):
        return _nota_fiscal(doc, arquivo, fornecedor)
    res = Resultado()
    L = linhas(doc.texto)
    f = nova_fatura(fornecedor, arquivo, doc.usou_ocr)
    m = rx(r"FATURA:\s*(\d{2}/\d{4})\s+N[º°o]\s*(\d+)\s+VENCIMENTO:\s*(" + RE_DATA + r")\s+VALOR\s*\(R\$\):\s*(" + RE_MOEDA + ")").search(texto)
    if m:
        f["competencia"], f["numero_fatura"], f["data_vencimento"], f["valor_total"] = competencia(m.group(1)), m.group(2), m.group(3), moeda(m.group(4))
    f["numero_fatura"] = f["numero_fatura"] or busca(r"FATURA\s+N\.?[º°o]\s*(\d{4,})", texto)
    f["competencia"] = f["competencia"] or competencia(busca(r"M[êe]s/Ano Faturamento:?\s*(\d{2}/\d{4})", texto))
    if not f["data_vencimento"]:
        mv = rx(r"Vencimento\s+Valor a Pagar \(R\$\)\s*\n\s*(?:.*?)(" + RE_DATA + r")\s+(" + RE_MOEDA + ")").search(texto)
        if mv:
            f["data_vencimento"], f["valor_total"] = mv.group(1), moeda(mv.group(2))
    f["valor_total"] = f["valor_total"] if f["valor_total"] is not None else moeda(busca(r"TOTAL A PAGAR\s+(" + RE_MOEDA + ")", texto))
    mm = rx(r"MATR[ÍI]CULA:\s*(\d+)\s+D[ÍI]GITO:\s*(\d)").search(texto)
    if not mm:
        mm = rx(r"Matr[íi]cula\s+D[íi]gito(?:\s+Grupo)?\s*\n\s*(\d+)\s+(\d)").search(texto)
    if mm:
        f["conta_formatada"], f["conta"] = f"{mm.group(1)}-{mm.group(2)}", mm.group(1) + mm.group(2)
    f["hidrometro"] = busca(r"HIDR[ÔO]METRO\s+N\.?[º°o]\s*([A-Z0-9]{5,})", texto)
    f["nome_cliente"] = busca(r"\bNOME:\s*(.+?)(?:\s{2,}|\s*$)", texto)
    _bloco_cliente(L, f)
    ma = rx(r"Leitura Atual:\s*(" + RE_DATA + r")\s+(\d+)").search(texto)
    if ma:
        f["data_leitura_atual"], f["leitura_atual"] = ma.group(1), inteiro(ma.group(2))
    mb = rx(r"Leitura Anterior:\s*(" + RE_DATA + r")\s+(\d+)").search(texto)
    if mb:
        f["data_leitura_anterior"], f["leitura_anterior"] = mb.group(1), inteiro(mb.group(2))
    f["consumo_faturado_m3"] = inteiro(busca(r"Consumo Faturado:\s*(\d+)", texto))
    if f["leitura_atual"] is not None and f["leitura_anterior"] is not None:
        f["consumo_m3"] = f["leitura_atual"] - f["leitura_anterior"]
    else:
        f["consumo_m3"] = f["consumo_faturado_m3"]
    f["dias"] = inteiro(busca(r"Dias de Consumo:\s*(\d+)", texto))
    f["tipo_consumo"] = busca(r"Ocorr[êe]ncia do M[êe]s:\s*(" + _LETRAS + ")", texto)
    f["categoria"] = categoria_por_contagem(texto)
    itens = []
    for i, ln in enumerate(L):
        c = coluna_de(ln, "DESCRIÇÃO")
        if c is not None and "ITENS" in ln.upper():
            for k, (desc, val) in enumerate(itens_coluna_direita(L, i, c, r"TOTAL A PAGAR"), 1):
                itens.append(novo_item(f, k, desc, val))
            break
    fechar_fatura(f, itens, arquivo)
    res.faturas.append(f)
    res.itens.extend(itens)
    hist = rx(r"HIST[ÓO]RICO DE CONSUMO(.*?)(?:FATURAS PENDENTES|VALOR TOTAL PENDENTE|$)", re.IGNORECASE | re.DOTALL).search(texto)
    if hist:
        for mh in re.finditer(r"^\s*(\d{2}/\d{4})\s+(" + _LETRAS + r")\s+(\d+)\s+(\d+)\s+(\d+)", hist.group(1), re.MULTILINE):
            h = novo_historico(f, mh.group(1), mh.group(5), None, mh.group(2))
            if h:
                res.historico.append(h)
    return res
