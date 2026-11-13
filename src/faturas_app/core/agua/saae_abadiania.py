"""SAAE Abadiânia — conta com canhoto (INSCRIÇÃO · MÊS FAT · NF/CONTA · VENCIMENTO · VALOR), itens codificados
(001 TARIFA DE AGUA…), hidrometria e últimos consumos. O acervo de 2021 é digitalizado (OCR, extração parcial)."""
from __future__ import annotations

import os
import re
from collections import Counter

from .base import (RE_DATA, RE_MOEDA, Resultado, busca, fechar_fatura, nova_fatura, novo_historico, novo_item, rx,
                   valor_linha_digitavel, vencimento_do_nome, vencimento_pelo_documento, vencimento_plausivel)
from .texto import competencia, competencia_por_caminho, data_iso, inteiro, moeda

# linha de código acima da linha digitável: inscrição (sem DV) . MM . AA . NF/conta  →  "0001255.06.25.250023083"
_RE_CODIGO = re.compile(r"(?<![\d.,])(\d{7})[.,](0[1-9]|1[0-2])[.,](\d{2})[.,](\d{9})(?!\d)")
_ORGAO = ("0325000",)       # dígitos fixos que fecham o 2º bloco da linha digitável do SAAE Abadiânia ("81450325000")
# "VENCIMENTO 23/07/2021  VALOR R$ 81,45" depois do OCR: a data (com ano de 4 dígitos) e o valor na mesma linha
_RE_PAR_VENC_VALOR = re.compile(r"(\d{2}/\d{2}/\d{4})[ \t]+(?:VALOR ?R[S$][ \t]*)?[—–-]?[ \t]*(\d{1,3}(?:\.\d{3})*,\d{2})(?![\d,])")


def _codigo(texto: str) -> dict | None:
    m = _RE_CODIGO.search(texto)
    if not m:
        return None
    return {"inscricao": m.group(1), "competencia": f"20{m.group(3)}-{m.group(2)}", "numero": m.group(4)}


def _ocr(doc, arquivo: str, fornecedor: str) -> Resultado:
    """Conta digitalizada. O que o OCR lê no corpo é parcial e instável; a identidade e o valor vêm, nesta ordem, do que
    tem conferência: linha digitável (valor, com dígitos verificadores), linha de código (mês/fat. e nº da conta) e nome
    do arquivo (nº e vencimento). Nesta concessionária o MÊS/FAT. impresso é o mês do VENCIMENTO (MAI/2021 vence em
    23/05/2021); os PDFs de texto saem assim, então a competência das digitalizadas segue a mesma regra (o acervo nomeia
    o arquivo pelo mês anterior: "OUTUBRO.2023 - VENC. 23.11" é a conta NOV/2023)."""
    res = Resultado()
    texto = doc.texto.replace("\f", "\n")
    f = nova_fatura(fornecedor, arquivo, True)
    cod = _codigo(texto)
    n_nome = re.search(r"N[º°o]\.?\s*(\d{9})(?!\d)", os.path.basename(arquivo))
    f["numero_fatura"] = (n_nome.group(1) if n_nome else None) or (cod or {}).get("numero") or busca(r"\b(2[0-9]\d{7})\b", texto)
    f["conta_formatada"] = busca(r"\b(\d{4,7}\.\d)\b", texto)
    pares = [(data_iso(m.group(1)), moeda(m.group(2))) for m in _RE_PAR_VENC_VALOR.finditer(texto)]
    venc = vencimento_do_nome(arquivo) or vencimento_pelo_documento(texto, arquivo) or (pares[0][0] if pares else None)
    venc = vencimento_plausivel(venc, (cod or {}).get("competencia") or competencia_por_caminho(arquivo))
    f["data_vencimento"] = venc
    comp_cod = (cod or {}).get("competencia")
    f["competencia"] = comp_cod or (venc[:7] if venc else None) or competencia_por_caminho(arquivo) \
        or competencia(busca(r"(?<!\d/)\b(0[1-9]|1[0-2])/(202\d)\b", texto, grupo=0))
    f["nome_cliente"] = busca(r"(F[OÓ]RUM DE ABAD[A-Z|]+)", texto)
    f["leitura_anterior"] = inteiro(busca(r"ANTERIOR[,.:]?\s*(\d{3,6})", texto))
    f["consumo_m3"] = inteiro(busca(r"CONSUMO[.,:]?\s*(\d{1,3})\b", texto))
    itens = []
    for k, mi in enumerate(re.finditer(r"^\s*(?:\S{1,2}\s+){0,2}?[|+]?\s*(\d{2})\s*[|/]*\s*([A-Z][^\n]*?)\s+(\d[\d.]*,?\d{2})\s*$", texto, re.MULTILINE), 1):
        raw = mi.group(3)
        val = moeda(raw) if "," in raw else float(raw.replace(".", "")[:-2] + "." + raw[-2:])
        itens.append(novo_item(f, k, mi.group(2).strip(" |"), val, mi.group(1)))
    soma = round(sum(it["valor"] or 0 for it in itens), 2) if itens else None
    # valor: linha digitável conferida; senão o valor mais repetido ao lado de uma data (corpo e canhoto), preferindo o que
    # fecha com os itens; senão a soma dos itens, só se forem exatamente água + esgoto a 50 % (tarifa desta concessionária)
    origem = ""
    valor = valor_linha_digitavel(texto, orgao=_ORGAO)
    if valor is not None:
        origem = "; valor pela linha digitável"
    elif any(v for _d, v in pares):
        cont = Counter(v for _d, v in pares if v)
        valor = soma if soma in cont else cont.most_common(1)[0][0]
    elif len(itens) == 2 and abs(max(it["valor"] for it in itens) / 2 - min(it["valor"] for it in itens)) <= 0.011:
        valor, origem = soma, "; valor pela soma de água + esgoto (50 %)"
    f["valor_total"] = valor
    if valor is None or soma is None or abs(soma - valor) > 0.011:
        itens = []                              # itens lidos pela metade não fecham com o total: não entram
    f["observacao"] = "PDF digitalizado: lido por OCR (parcial)" + origem
    fechar_fatura(f, itens, arquivo)
    res.faturas.append(f)
    res.itens.extend(itens)
    return res


def _sem_rotulos(texto: str, f: dict) -> None:
    """Conta impressa só com os dados, sem os rótulos do formulário (2021, "FATURA DE ÁGUA.pdf"): a linha de código
    "0001255.05.21.210016274" dá mês/fat. e número; "23/05/2021   81,45" dá vencimento e valor (que tem de bater com a
    linha digitável quando ela está inteira)."""
    cod = _codigo(texto)
    if not cod:
        return
    f["numero_fatura"], f["competencia"] = cod["numero"], cod["competencia"]
    f["conta_formatada"] = busca(r"^\s*(" + cod["inscricao"] + r"\.\d)(?!\d)", texto, flags=re.MULTILINE)
    pares = [(m.group(1), moeda(m.group(2))) for m in re.finditer(r"(" + RE_DATA + r")\s+(" + RE_MOEDA + r")[ \t]*$", texto, re.MULTILINE)]
    linha = valor_linha_digitavel(texto)
    if pares and (linha is None or abs(pares[0][1] - linha) <= 0.005):
        f["data_vencimento"], f["valor_total"] = pares[0]
    elif linha is not None:
        f["valor_total"] = linha
    f["data_emissao"] = busca(cod["numero"] + r"\s+(\d{2}/\d{2}/\d{4})\s+[A-Z]{3}/\d{4}", texto)
    f["observacao"] = "conta impressa sem os rótulos do formulário"


def _itens_do_quadro(texto: str, f: dict, itens: list[dict]) -> list[dict]:
    """Só quando os itens lidos NÃO fecham com o total: relê o quadro SERVIÇOS E TARIFAS inteiro (qualquer descrição, como
    "CUSTO MINIMO FIXO" ou "2ª Via de …") e fica com ele se a soma fechar com o total impresso. Fatura que já fecha não muda."""
    total = f.get("valor_total")
    if total is None or not itens or abs(round(sum(it.get("valor") or 0 for it in itens), 2) - total) <= 0.01:
        return itens
    quadro = rx(r"DESCRI[ÇC][ÃA]O\s+(?:PREST\.?\s+)?VALOR\s*\n(.*?)\n[^\n]*HIDROMETRIA", re.IGNORECASE | re.DOTALL).search(texto)
    if not quadro:
        return itens
    novos = []
    for ln in quadro.group(1).splitlines():
        seg = [x for x in re.split(r"\s{2,}", ln.strip()) if x]
        if len(seg) >= 2 and re.fullmatch(RE_MOEDA, seg[-1]) and re.search(r"[A-Za-zÀ-ÿ]{3}", seg[-2]):
            novos.append((seg[-2], seg[-1]))
    if novos and abs(round(sum(moeda(v) for _d, v in novos), 2) - total) <= 0.01:
        return [novo_item(f, k, d, v) for k, (d, v) in enumerate(novos, 1)]
    return itens


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
    if not f["numero_fatura"] and not f["competencia"] and f["valor_total"] is None and "INSCRI" not in texto.upper():
        _sem_rotulos(texto, f)
    f["data_emissao"] = f["data_emissao"] or busca(r"(\d{8,})\s+(\d{2}/\d{2}/\d{2})\s+[A-Z]{3}/\d{4}", texto, grupo=2)
    f["nome_cliente"] = busca(r"NOME:\s*(.+?)\s{2,}", texto) or busca(r"^\s*(F[ÓO]RUM[^\n]*?)\s*$", texto, flags=re.IGNORECASE | re.MULTILINE)
    f["logradouro"] = busca(r"END:\s*(.+?)\s{2,}", texto)
    d2 = r"\d{2}/\d{2}/\d{2,4}"
    mh = re.search(r"^\s*([A-Z0-9]{6,})\s+(" + d2 + r")\s+(\d+)\s+(" + d2 + r")\s+(\d+)\s+(" + d2 + r")\s+(\d+|\*{2,})\s+(\d+)", texto, re.MULTILINE)
    if mh:
        f["hidrometro"], f["leitura_anterior"], f["data_leitura_anterior"] = mh.group(1), inteiro(mh.group(3)), mh.group(4)
        f["leitura_atual"], f["data_leitura_atual"], f["consumo_m3"], f["dias"] = inteiro(mh.group(5)), mh.group(6), inteiro(mh.group(7)), inteiro(mh.group(8))
        if f["consumo_m3"] is None and f["leitura_atual"] >= f["leitura_anterior"]:
            # consumo impresso como "***" (mês sem consumo: leitura igual à anterior): vale a diferença das leituras
            f["consumo_m3"] = f["leitura_atual"] - f["leitura_anterior"]
    itens = []
    for k, mi in enumerate(re.finditer(r"(?:^|\s)(?:(\d{3})\s+)?((?:TARIFA|TAXA|SERV|MULTA|JUROS)[^\n]*?)\s+(" + RE_MOEDA + r")[ \t]*$", texto, re.MULTILINE), 1):
        itens.append(novo_item(f, k, mi.group(2), mi.group(3), mi.group(1)))
    itens = _itens_do_quadro(texto, f, itens)
    f["categoria"] = "PUB"
    fechar_fatura(f, itens, arquivo)
    res.faturas.append(f)
    res.itens.extend(itens)
    for mh2 in re.finditer(r"^\s*([A-Z]{3}/\d{2})\s+(\d+)\s+(\d{3})\s+(\d{2,3})\b", texto, re.MULTILINE):
        h = novo_historico(f, mh2.group(1), mh2.group(2), None, None)
        if h:
            res.historico.append(h)
    return res
