"""SANESC (Senador Canedo) — três modelos no acervo:
  * 2021: guia igual à de Leopoldo de Bulhões ("Número da guia", "CÓD. LIG.: 07155-5", "MÊS / ANO") → mesmo extrator;
  * 2022+: conta com "Cadastro · Código de Baixa · Hidrômetro · Referência · Vencimento" e "TOTAL DA CONTA";
  * boletim de arrecadação (2ª via / cobrança): "BOLETIM DE ARRECADAÇÃO", "Dívida Cadastro Vencimento … Valor", "Total da Guia".
Sem número de fatura próprio: o id usa cadastro + competência."""
from __future__ import annotations

import re

from . import leopoldo_bulhoes
from .base import RE_DATA, RE_MOEDA, Resultado, busca, fechar_fatura, nova_fatura, novo_historico, novo_item, rx
from .texto import competencia, digitos, inteiro, moeda


def _guia(doc, arquivo: str, fornecedor: str) -> Resultado:
    res = leopoldo_bulhoes.extrair(doc, arquivo, fornecedor)
    for f in res.faturas:
        lig = busca(r"C[OÓ]{1,2}D\.?\s*LIG\.?:?\s*(\d{3,6})-\d", doc.texto)
        if lig:                                   # cadastro sem o dígito verificador, como nas contas 2022+ (000007155 → 7155)
            f["conta_formatada"], f["conta"] = lig, lig
        f["id_fatura_agua"] = f"{fornecedor}_{digitos(f['conta']).lstrip('0') or 'SEMCONTA'}_{f.get('competencia') or 'SEMCOMP'}" if not f.get("numero_fatura") else f["id_fatura_agua"]
        for it in res.itens:
            it["conta"] = f["conta"]
    return res


def _boletim(doc, arquivo: str, fornecedor: str) -> Resultado:
    res = Resultado()
    texto = doc.texto.replace("\f", "\n")
    f = nova_fatura(fornecedor, arquivo, doc.usou_ocr)
    f["conta_formatada"] = busca(r"Cadastro[^\n]*\n\s*(\d{6,})", texto)
    f["nome_cliente"] = busca(r"\bNome\s*\n[^\n]*?\s{2,}([A-Z][^\n]+?)\s*$", texto, flags=re.IGNORECASE | re.MULTILINE)
    m = re.search(r"^\s*(\d+)\s+(\d{6,})\s+(" + RE_DATA + r")\s+\d+\s+(.+?)\s{2,}(" + RE_MOEDA + ")", texto, re.MULTILINE)
    if m:
        f["data_vencimento"], f["valor_total"] = m.group(3), moeda(m.group(5))
        f["observacao"] = f"boletim de arrecadação (dívida {m.group(1)}): {m.group(4).strip()}"
    f["valor_total"] = f["valor_total"] if f["valor_total"] is not None else moeda(busca(r"Total da Guia\s+(" + RE_MOEDA + ")", texto))
    f["data_vencimento"] = f["data_vencimento"] or busca(r"C[óo]digo de Baixa[^\n]*\n[^\n]*?(" + RE_DATA + ")", texto)
    f["logradouro"] = busca(r"Logradouro[^\n]*\n\s*(\S[^\n]*?)\s{3,}", texto)
    itens = []
    bloco = texto[texto.find("Discrimina"):] if "Discrimina" in texto else ""
    for k, mi in enumerate(re.finditer(r"^\s*(\d{1,4})\s+([A-Z][A-Za-z /]+?)\s{2,}(" + RE_MOEDA + ")", bloco, re.MULTILINE), 1):
        itens.append(novo_item(f, k, mi.group(2), mi.group(3), mi.group(1)))
    f["categoria"] = "PUB"
    fechar_fatura(f, itens, arquivo)
    res.faturas.append(f)
    res.itens.extend(itens)
    return res


def extrair(doc, arquivo: str, fornecedor: str = "SANESC") -> Resultado:
    texto = doc.texto.replace("\f", "\n")
    if re.search(r"N[úu]mero da guia|C[OÓ]{1,2}D\.?\s*LIG\.?:", texto):
        return _guia(doc, arquivo, fornecedor)
    if re.search(r"BOLETIM\s+DE\s+ARRECADA", texto):
        return _boletim(doc, arquivo, fornecedor)
    res = Resultado()
    f = nova_fatura(fornecedor, arquivo, doc.usou_ocr)
    m = re.search(r"^\s*(\d{6,})\s+([\d-]{6,})\s+([A-Z0-9]{6,})\s+(\d{1,2}/\d{4})\s+(" + RE_DATA + ")", texto, re.MULTILINE)
    if m:
        f["conta_formatada"], f["hidrometro"], f["competencia"], f["data_vencimento"] = m.group(1), m.group(3), competencia(m.group(4)), m.group(5)
        f["observacao"] = f"código de baixa {m.group(2)}"
    else:
        f["conta_formatada"] = busca(r"Cadastro\s*\n?\s*(\d{6,})", texto) or busca(r"^\s*(0{3,}\d{3,})\s+[A-Z]", texto, flags=re.MULTILINE)
        f["hidrometro"] = busca(r"\b([A-Z]\d{2}[A-Z]\d{6})\b", texto)
        mr = rx(r"Refer[êe]ncia\s+Vencimento\s*\n[^\n]*?(\d{1,2}/\d{4})\s+(" + RE_DATA + ")").search(texto) \
            or rx(r"Vencimento\s+Refer[êe]ncia\s*\n[^\n]*?(" + RE_DATA + r")\s+(\d{1,2}/\d{4})").search(texto)
        if mr:
            a, b = mr.group(1), mr.group(2)
            if "/" in a and len(a) <= 7:
                f["competencia"], f["data_vencimento"] = competencia(a), b
            else:
                f["competencia"], f["data_vencimento"] = competencia(b), a
        if not f["data_vencimento"]:
            mv = re.search(r"^\s*(" + RE_DATA + r")\s+(\d{1,2}/\d{4})\s*$", texto, re.MULTILINE)
            if mv:
                f["data_vencimento"], f["competencia"] = mv.group(1), competencia(mv.group(2))
    ml = re.search(r"^\s*(\d+)\s+(\d+)\s+(" + RE_DATA + r")\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$", texto, re.MULTILINE)
    if ml:
        f["dias"], f["data_leitura_atual"], f["leitura_anterior"], f["leitura_atual"] = inteiro(ml.group(2)), ml.group(3), inteiro(ml.group(4)), inteiro(ml.group(5))
        f["consumo_m3"], f["consumo_faturado_m3"] = inteiro(ml.group(6)), inteiro(ml.group(7))
    else:
        ml2 = re.search(r"^\s*(\d{2,4})\s+(\d{2,4})\s+(\d{3,6})\s+(\d{1,2})\s*$", texto, re.MULTILINE)   # 2022: "72 72 2876 2" (cons fat, consumo, leitura, dias?)
        if ml2:
            f["consumo_faturado_m3"], f["consumo_m3"], f["leitura_atual"] = inteiro(ml2.group(1)), inteiro(ml2.group(2)), inteiro(ml2.group(3))
    f["categoria"] = busca(r"Categoria\s+Ocorr[êe]ncia\s*\n\s*([A-Z]+)", texto) or busca(r"Categoria\s*\n\s*([A-Z]+)", texto)
    f["tipo_consumo"] = busca(r"Ocorr[êe]ncia\s*\n[^\n]*?([A-Z]+\s+[A-Z]+)\s*$", texto, flags=re.IGNORECASE | re.MULTILINE)
    f["nome_cliente"] = busca(r"\d{6,}\s+(TRIBUNAL[^\n]+?)\s*$", texto, flags=re.IGNORECASE | re.MULTILINE) \
        or busca(r"Propriet[áa]rio\s*\n\s*(TRIBUNAL[^\n]+?)\s{2,}", texto) or busca(r"(TRIBUNAL DE JUSTI[CÇ]A[^\n]*?GOI[AÁ]S)", texto)
    f["logradouro"] = busca(r"Endere[çc]o da Lig\s*a?[çc][ãa]o[^\n]*\n\s*(.+?)\s{2,}", texto)
    f["data_emissao"] = busca(r"Emiss[ãa]o[^\n]*\n\s*(" + RE_DATA + ")", texto)
    f["valor_total"] = moeda(busca(r"TOTAL DA CONTA:?\s*(" + RE_MOEDA + ")", texto)) or moeda(busca(r"Total da Conta:?\s*(" + RE_MOEDA + ")", texto))
    itens = []
    for k, mi in enumerate(re.finditer(r"\s(AGUA|ESGOTO|[A-Z]{4,}(?: [A-Z]{3,})*)\s+(" + RE_MOEDA + r")\s*$", texto, re.MULTILINE), 1):
        if "TOTAL" in mi.group(1):
            continue
        itens.append(novo_item(f, k, mi.group(1), mi.group(2)))
    fechar_fatura(f, itens, arquivo)
    res.faturas.append(f)
    res.itens.extend(itens)
    for mh in re.finditer(r"^\s*(\d{1,2}/\d{4})\s+(\d+)\s+(\d+)\s+(?:(\d+)\s+)?(" + RE_DATA + ")", texto, re.MULTILINE):
        h = novo_historico(f, mh.group(1), mh.group(2), None, None)
        if h:
            res.historico.append(h)
    return res
