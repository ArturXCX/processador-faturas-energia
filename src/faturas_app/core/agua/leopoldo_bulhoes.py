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


def _linhas_do_ocr(doc) -> list[str]:
    """Linhas como o próprio Tesseract as montou (bloco, linha), de cima para baixo, nas páginas lidas por OCR. Numa guia
    fotografada torta o layout em colunas separa a descrição do valor ("TARIFA DE" / "AGUA … 110,50"); a linha do
    Tesseract os mantém juntos."""
    saida = []
    for palavras, ocr in zip(getattr(doc, "_palavras", None) or [], getattr(doc, "paginas_ocr", None) or []):
        if not ocr:
            continue
        linhas: dict[tuple, list] = {}
        for w in palavras:
            if len(w) >= 7:
                linhas.setdefault((w[5], w[6]), []).append(w)
        for k in sorted(linhas, key=lambda k: min(w[1] for w in linhas[k])):
            saida.append(" ".join(str(w[4]) for w in sorted(linhas[k], key=lambda w: w[0])))
    return saida


def _um_digito_de_diferenca(a: float, b: float) -> bool:
    """Os centavos de `a` e `b` diferem por um único dígito trocado, a mais ou a menos (erro típico de OCR num número)."""
    sa, sb = str(int(round(a * 100))), str(int(round(b * 100)))
    if len(sa) == len(sb):
        return sum(1 for x, y in zip(sa, sb) if x != y) == 1
    curto, longo = sorted((sa, sb), key=len)
    return len(longo) - len(curto) == 1 and any(longo[:i] + longo[i + 1:] == curto for i in range(len(longo)))


def _reler_ocr(doc, f: dict, itens: list[dict]) -> list[dict]:
    """Só na guia lida por OCR em que o total não saiu ou os itens não fecham com ele: relê os lançamentos nas linhas do
    Tesseract e fica com eles quando a soma (2+ itens, um deles a tarifa de água) é igual a um valor impresso ao lado de
    "R$" — ou difere dele por um único dígito, caso em que vale a soma dos itens (três leituras quase iguais: o OCR
    trocou um dígito do total, "1.288,96" / "1.2889,96" para 1.275,62 + 14,34 = 1.289,96). Guia que já fecha não muda."""
    total = f.get("valor_total")
    soma = round(sum(it.get("valor") or 0 for it in itens), 2) if itens else None
    if total is not None and soma is not None and abs(soma - total) <= 0.01:
        return itens
    so_itens = total is not None and soma is None      # total lido, nenhum item: os itens só entram se somarem EXATAMENTE o total
    L = _linhas_do_ocr(doc)
    novos: list[tuple[str, float]] = []
    lidos: set[float] = set() if total is None else {total}
    for ln in L:
        m = re.search(r"(TARIFA\s+DE\s+A*[ÁA]GUA|TARIFA\s+DE\s+ESGOTO|CUSTO\b.*?\bFIXO)\b.*?(\d{1,3}(?:\.\d{3})*,\d{2})\s*$", ln, re.IGNORECASE)
        if m:
            desc = "CUSTO MINIMO FIXO" if m.group(1).upper().startswith("CUSTO") else "TARIFA DE " + ("ESGOTO" if "ESGOTO" in m.group(1).upper() else "AGUA")
            if desc not in [d for d, _v in novos]:
                novos.append((desc, moeda(m.group(2))))
        elif "R$" in ln:
            lidos.update(v for v in (moeda(x) for x in re.findall(r"\d[\d.]*,\d{2}", ln)) if v)
    soma_n = round(sum(v for _d, v in novos), 2)
    if so_itens:
        if len(novos) >= 2 and novos[0][0] == "TARIFA DE AGUA" and abs(soma_n - total) <= 0.01:
            f["observacao"] = "; ".join(x for x in (f.get("observacao"), "itens relidos nas linhas do OCR (guia fotografada)") if x)
            return [novo_item(f, k, d, v) for k, (d, v) in enumerate(novos, 1)]
        return itens
    if len(novos) >= 2 and novos[0][0] == "TARIFA DE AGUA" and (soma_n in lidos or any(_um_digito_de_diferenca(soma_n, v) for v in lidos)):
        f["valor_total"] = soma_n
        f["observacao"] = "; ".join(x for x in (f.get("observacao"), "itens e total relidos nas linhas do OCR (guia fotografada)") if x)
        return [novo_item(f, k, d, v) for k, (d, v) in enumerate(novos, 1)]
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
    if doc.usou_ocr:
        itens = _reler_ocr(doc, f, itens)
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
