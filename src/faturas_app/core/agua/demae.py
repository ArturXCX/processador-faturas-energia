"""DEMAE Caldas Novas (PDF de texto) e DEMAE Panamá (acervo 100 % digitalizado: OCR, extração parcial)."""
from __future__ import annotations

import os
import re

from .base import (RE_DATA, RE_MOEDA, Resultado, busca, coluna_de, fechar_fatura, itens_coluna_direita, linhas,
                   nova_fatura, novo_historico, novo_item, rx)
from .texto import competencia, competencia_do_nome, data_iso, digitos, inteiro, moeda

_LETRAS = r"[A-Za-zÀ-ÿ]+"


def _caldas_novas(doc, arquivo: str, fornecedor: str) -> Resultado:
    res = Resultado()
    texto = doc.texto.replace("\f", "\n")
    L = linhas(doc.texto)
    f = nova_fatura(fornecedor, arquivo, doc.usou_ocr)
    f["conta_formatada"] = busca(r"Matr[íi]cula:\s*([\d-]+)", texto)
    f["numero_fatura"] = busca(r"Fatura\s*n[º°o]?:?\s*(\d+)", texto)
    f["competencia"] = competencia(busca(r"Refer[êe]ncia:\s*(\d{2}/\d{4})", texto))
    f["data_vencimento"] = busca(r"Data de Vencimento:\s*(" + RE_DATA + ")", texto)
    f["valor_total"] = moeda(busca(r"\bValor:\s*R\$\s*(" + RE_MOEDA + ")", texto))
    f["data_emissao"] = busca(r"Data de emiss[ãa]o:\s*(" + RE_DATA + ")", texto)
    f["nome_cliente"] = busca(r"MORADOR:\s*(.+?)(?:\s{2,}|\n)", texto)
    f["hidrometro"] = busca(r"HIDR[ÔO]METRO:\s*([A-Z0-9]{5,})", texto)
    f["dias"] = inteiro(busca(r"Dias Consumo:\s*(\d+)", texto))
    f["categoria"] = busca(r"TIPO TARIFA\s*\n\s*[^\n]*?\d+\s+(" + _LETRAS + ")", texto)
    for i, ln in enumerate(L):
        if "MORADOR:" in ln.upper():
            partes = []
            for lx in L[i + 1: i + 4]:
                seg = lx[:75].strip()
                if seg and not re.match(r"^(PROPRIET|MATR)", seg.upper()):
                    partes.append(seg)
            f["logradouro"] = " ".join(partes) or None
            break
    itens = []
    for i, ln in enumerate(L):
        c = coluna_de(ln, "DESCRIÇÃO")
        if c is not None and "ITENS" in ln.upper():
            for k, (desc, val) in enumerate(itens_coluna_direita(L, i, c, r"TOTAL A PAGAR"), 1):
                itens.append(novo_item(f, k, desc, val))
            break
    for mh in re.finditer(r"^\s*(\d{2}/\d{4})(?:\s*\((Anterior|Atual)\))?\s+(" + _LETRAS + r")\s+(\d+)\s+(\d+)\s+(\d+)(?:\s+(" + RE_DATA + "))?",
                          texto, re.MULTILINE):
        comp, marca, tipo, leitura, lido, faturado, data = mh.groups()
        if marca == "Anterior":
            f["leitura_anterior"], f["data_leitura_anterior"] = inteiro(leitura), data
        elif marca == "Atual":
            f["leitura_atual"], f["data_leitura_atual"] = inteiro(leitura), data
            f["consumo_m3"], f["consumo_faturado_m3"], f["tipo_consumo"] = inteiro(lido), inteiro(faturado), tipo
        h = novo_historico(f, comp, faturado, None, tipo)
        if h:
            res.historico.append(h)
    fechar_fatura(f, itens, arquivo)
    res.faturas.append(f)
    res.itens.extend(itens)
    return res


def _panama(doc, arquivo: str, fornecedor: str) -> Resultado:
    """Guias escaneadas: número da guia = AA MM + ligação (240123382 → 2024-01, conta 23382)."""
    res = Resultado()
    texto = doc.texto.replace("\f", "\n")
    nome = os.path.basename(arquivo)
    f = nova_fatura(fornecedor, arquivo, doc.usou_ocr)
    num = busca(r"N[º°o]\s*(\d{9})", nome) or busca(r"\b(2\d{8})\b", texto)
    f["numero_fatura"] = num
    lig = rx(r"LIGA[ÇC][ÃA]O:?\s*(\d{4,6})\s*-?\s*(\d)").search(texto)
    if lig:      # a conta fica SEM o dígito verificador: é o que o número da guia traz (AA MM + ligação) e o OCR erra o DV
        f["conta_formatada"], f["conta"] = f"{lig.group(1)}-{lig.group(2)}", lig.group(1)
    elif num and len(num) == 9:
        f["conta_formatada"], f["conta"] = num[4:], num[4:]
    if num and len(num) == 9:
        f["competencia"] = f"20{num[:2]}-{num[2:4]}"
    f["competencia"] = f["competencia"] or competencia_do_nome(nome)
    ano_pasta = re.search(r"(20\d{2})", os.path.basename(os.path.dirname(arquivo)) + " " + os.path.basename(os.path.dirname(os.path.dirname(arquivo))))
    venc_nome = re.search(r"VENC\.?\s*(\d{2})[.\-](\d{2})(?:[.\-](\d{2,4}))?", nome, re.IGNORECASE)
    if venc_nome:
        ano = venc_nome.group(3) or (ano_pasta.group(1) if ano_pasta else None)
        if ano:
            f["data_vencimento"] = data_iso(f"{venc_nome.group(1)}/{venc_nome.group(2)}/{ano}")
    if not f["data_vencimento"] and f["competencia"]:
        datas = [d for d in (data_iso(x) for x in re.findall(RE_DATA, texto)) if d and d[:7] > f["competencia"] and d[:4] <= "2030"]
        f["data_vencimento"] = datas[0] if datas else None
    if not f["competencia"] and f["data_vencimento"]:      # guia vence no mês seguinte ao de referência
        a, m = int(f["data_vencimento"][:4]), int(f["data_vencimento"][5:7]) - 1
        f["competencia"] = f"{a - 1}-12" if m == 0 else f"{a}-{m:02d}"
    mv = rx(r"VALOR\s*[ÀA]\s*PAGAR").search(texto)
    if mv:
        janela = texto[mv.end(): mv.end() + 250]
        mr = re.search(r"[RI1l|\[]?\$\s*(\d[\d.,]*)", janela) or re.search(r"\b(\d{3,7}(?:,\d{2})?)\b", janela)
        if mr:
            raw = mr.group(1)
            if "," in raw:
                f["valor_total"] = moeda(raw)
            elif len(digitos(raw)) >= 3:
                d = digitos(raw)
                f["valor_total"] = float(d[:-2] + "." + d[-2:])
    f["hidrometro"] = busca(r"HIDR[ÔO]METRO\D{0,60}?(\d{5,8})", texto)
    f["nome_cliente"] = "TRIBUNAL DE JUSTICA DO ESTADO DE GOIAS" if re.search(r"TRIBUNAL", texto, re.IGNORECASE) else None
    f["observacao"] = "DEMAE Panamá: guia digitalizada, campos por OCR (parcial)"
    fechar_fatura(f, [], arquivo)
    res.faturas.append(f)
    return res


def extrair(doc, arquivo: str, fornecedor: str) -> Resultado:
    if fornecedor == "DEMAE_PANAMA" or (doc.usou_ocr and "PANAM" in doc.texto.upper()):
        return _panama(doc, arquivo, "DEMAE_PANAMA")
    return _caldas_novas(doc, arquivo, fornecedor)
