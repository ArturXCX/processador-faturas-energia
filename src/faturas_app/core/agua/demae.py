"""DEMAE Caldas Novas (PDF de texto) e DEMAE Panamá (acervo 100 % digitalizado: OCR, extração parcial)."""
from __future__ import annotations

import os
import re

from .base import (RE_DATA, RE_MOEDA, Resultado, busca, coluna_de, fechar_fatura, itens_coluna_direita, linhas,
                   nova_fatura, novo_historico, novo_item, rx, valor_linha_digitavel, _blocos_arrecadacao, _dv_mod10)
from .texto import competencia, competencia_do_nome, data_iso, inteiro, moeda

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
    _devolucao_como_credito(f, itens)
    fechar_fatura(f, itens, arquivo)
    res.faturas.append(f)
    res.itens.extend(itens)
    return res


def _devolucao_como_credito(f: dict, itens: list[dict]) -> None:
    """"DEVOLUCAO NUMERÁRIO Ref: 04/2025   0,61" sai impresso SEM sinal, mas é abatido do total (59,18 + 35,48 − 0,61 =
    94,05). Só quando os itens não fecham com o total impresso E passam a fechar com a devolução negativa: o item vira
    crédito (valor negativo). Fatura que já fecha não é tocada."""
    total = f.get("valor_total")
    if total is None or not itens:
        return
    soma = round(sum(it.get("valor") or 0 for it in itens), 2)
    if abs(soma - total) <= 0.01:
        return
    dev = [it for it in itens if (it.get("valor") or 0) > 0 and (it.get("descricao_normalizada") or "").startswith("DEVOLUC")]
    if dev and abs(soma - 2 * sum(it["valor"] for it in dev) - total) <= 0.01:
        for it in dev:
            it["valor"] = -it["valor"]
            it["categoria_valor"] = "credito"


_RE_VALOR_OCR = r"\d{1,3}(?:\.\d{3})*,\d{2}"
# 2º bloco da linha digitável do DEMAE Panamá: 4 últimos dígitos do valor + código fixo do órgão (0888 + 023; 0888 + 202 em 2021)
_ORGAO_PANAMA = ("0888023", "0888202")


def _falta_um(curto: str, inteiro_: str) -> bool:
    """`curto` é `inteiro_` com exatamente um caractere a menos (o OCR engoliu um dígito repetido: "088023" × "0888023")."""
    return len(curto) == len(inteiro_) - 1 and any(inteiro_[:i] + inteiro_[i + 1:] == curto for i in range(len(inteiro_)))


def _centavos_2o_bloco(texto: str) -> set[str]:
    """Os 4 primeiros dígitos (fim do valor) de cada 2º bloco da linha digitável do Panamá reconhecido pelo código do órgão,
    sem exigir a linha inteira: bloco limpo; bloco com um dígito a menos no código do órgão ("3880088023"); bloco com UM
    caractere ilegível entre os 4 primeiros, recuperado pelo dígito verificador ("G3750888023-3" → 6375)."""
    c: set[str] = set()
    for _i, _col, b, dv in _blocos_arrecadacao(texto):
        if b[4:] in _ORGAO_PANAMA and (dv is None or _dv_mod10(b) == int(dv)):
            c.add(b[:4])
    for m in re.finditer(r"(?<![\dOo])(\d{4})(\d{6})(?![\dOo])", texto):
        if any(_falta_um(m.group(2), s) for s in _ORGAO_PANAMA):
            c.add(m.group(1))
    for m in re.finditer(r"(?<![\dA-Za-z$])([\dA-Za-z$]{4})(" + "|".join(_ORGAO_PANAMA) + r")\s?[-. ]\s?(\d)(?!\d)", texto):
        ini, dv = m.group(1), int(m.group(3))
        ruins = [i for i, ch in enumerate(ini) if not ch.isdigit()]
        if len(ruins) == 1:
            for d in "0123456789":
                cand = ini[:ruins[0]] + d + ini[ruins[0] + 1:]
                if _dv_mod10(cand + m.group(2)) == dv:
                    c.add(cand)
    return c


def _valor_panama(texto: str) -> tuple[float | None, str]:
    """Valor da guia do Panamá → (valor, origem), sempre apoiado na linha digitável, que traz dígito verificador:
      1. linha completa conferida (4 blocos, DVs e DV geral);
      2. 1º e 2º blocos, cada um conferido pelo próprio DV, com o 2º terminando no código do DEMAE Panamá (um bloco fora
         de ordem não passa por 2º bloco);
      3. um valor lido no corpo da guia ("TARIFA DE AGUA 235,98", "R$ 26,78", "Valor total: 38,93") cujos 4 últimos
         dígitos reaparecem no 2º bloco da linha digitável (`_centavos_2o_bloco`): duas leituras independentes iguais.
    Leitura solta do corpo não vale: no OCR destas guias o mesmo número sai diferente a cada leitura ("30,45" lido
    "36,45") e o ano de uma data ("05/04/2022") já foi tomado por valor (R$ 20,22)."""
    v = valor_linha_digitavel(texto)
    if v is not None:
        return v, "linha digitável"
    blocos = [b for b in _blocos_arrecadacao(texto) if b[3] is not None and _dv_mod10(b[2]) == int(b[3])]
    b1s = {b[2] for b in blocos if re.match(r"8[1-9][67]", b[2])}
    b2s = {b[2] for b in blocos if b[2][4:] in _ORGAO_PANAMA}
    if len(b1s) == 1 and len(b2s) == 1:
        return int(next(iter(b1s))[4:] + next(iter(b2s))[:4]) / 100.0, "linha digitável (1º e 2º blocos)"
    centavos = _centavos_2o_bloco(texto)
    if centavos:
        leituras: set[float] = set()
        for m in re.finditer(r"TARIFA\s+D?E?\s*[ÁA]GUA\s+(?:R\$\s*)?(" + _RE_VALOR_OCR + r")(?![\d/])", texto, re.IGNORECASE):
            leituras.add(moeda(m.group(1)))
        for m in re.finditer(r"[RI1l|\[]\$\s*(" + _RE_VALOR_OCR + r"|\d{3,6})(?![\d,./])", texto):
            raw = m.group(1)
            leituras.add(moeda(raw) if "," in raw else float(raw[:-2] + "." + raw[-2:]))
        for m in re.finditer(r"Valor\s*total:?\s*(" + _RE_VALOR_OCR + r")(?![\d/])", texto, re.IGNORECASE):
            leituras.add(moeda(m.group(1)))
        casam = {x for x in leituras if x and f"{int(round(x * 100)) % 10000:04d}" in centavos}
        if len(b1s) == 1:                          # o 1º bloco conferido dá os dígitos acima dos 4 últimos
            casam = {x for x in casam if int(round(x * 100)) // 10000 == int(next(iter(b1s))[4:])}
        if len(casam) == 1:
            return casam.pop(), "linha digitável (2º bloco) + valor impresso"
    return None, ""


def _panama(doc, arquivo: str, fornecedor: str) -> Resultado:
    """Guias escaneadas: número da guia = AA MM + ligação (240123382 → 2024-01, conta 23382)."""
    res = Resultado()
    texto = doc.texto.replace("\f", "\n")
    nome = os.path.basename(arquivo)
    f = nova_fatura(fornecedor, arquivo, doc.usou_ocr)
    # guias de 2021 (modelo da prefeitura): o número é o "Lançamento" de 6–7 dígitos que o acervo põe no nome ("Nº 988195")
    num = busca(r"N[º°o]\s*(\d{9})", nome) or busca(r"\b(2\d{8})\b", texto) or busca(r"N[º°o]\s*(\d{6,8})(?!\d)", nome)
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
    if not f["competencia"] and not f["data_vencimento"]:
        # sem número de 9 dígitos, sem mês e sem vencimento no nome ("sem_/FATURA Nº 993588 - DEMAE PANAMÁ.pdf"): a guia de
        # 2021 imprime "Referência: 2021/05" e "Pagamento até: 05/06/2021"
        mr = re.search(r"Refer[êe]ncia:?\s*(20[12]\d)\s*/\s*(0[1-9]|1[0-2])(?!\d)", texto, re.IGNORECASE)
        if mr:
            f["competencia"] = f"{mr.group(1)}-{mr.group(2)}"
            pg = data_iso(busca(r"Pagamento\s+at[ée]:?\s*[—–-]?\s*(" + RE_DATA + ")", texto))
            if pg and f["competencia"] <= pg[:7] <= "2035-12":
                f["data_vencimento"] = pg
    if not f["data_vencimento"] and f["competencia"]:
        datas = [d for d in (data_iso(x) for x in re.findall(RE_DATA, texto)) if d and d[:7] > f["competencia"] and d[:4] <= "2030"]
        f["data_vencimento"] = datas[0] if datas else None
    if not f["competencia"] and f["data_vencimento"]:      # guia vence no mês seguinte ao de referência
        a, m = int(f["data_vencimento"][:4]), int(f["data_vencimento"][5:7]) - 1
        f["competencia"] = f"{a - 1}-12" if m == 0 else f"{a}-{m:02d}"
    f["valor_total"], origem_valor = _valor_panama(texto)
    f["hidrometro"] = busca(r"HIDR[ÔO]METRO\D{0,60}?(\d{5,8})", texto)
    f["nome_cliente"] = "TRIBUNAL DE JUSTICA DO ESTADO DE GOIAS" if re.search(r"TRIBUNAL", texto, re.IGNORECASE) else None
    f["observacao"] = "DEMAE Panamá: guia digitalizada, campos por OCR (parcial)" + (f"; valor pela {origem_valor}" if origem_valor else "")
    fechar_fatura(f, [], arquivo)
    res.faturas.append(f)
    return res


def extrair(doc, arquivo: str, fornecedor: str) -> Resultado:
    if fornecedor == "DEMAE_PANAMA" or (doc.usou_ocr and "PANAM" in doc.texto.upper()):
        return _panama(doc, arquivo, "DEMAE_PANAMA")
    return _caldas_novas(doc, arquivo, fornecedor)
