"""Utilidades compartilhadas pelos extratores de água: regex tolerante a espaçamento, montagem das linhas canônicas,
itens/histórico e o resultado de um PDF."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import schema_agua as S
import os

from .texto import (categoria_valor, competencia, competencia_do_nome, competencia_por_caminho, data_iso, digitos, inteiro,
                    moeda, normalizar_descricao, sem_acento)

RE_DATA = r"\d{1,2}/\d{1,2}/\d{2,4}"
RE_MOEDA = r"-?\d{1,3}(?:\.\d{3})*,\d{1,2}|-?\d+,\d{1,2}"


def rx(padrao: str, flags=re.IGNORECASE):
    """Compila um regex em que cada espaço literal do padrão aceita qualquer espaçamento (o texto em layout tem
    vários espaços entre palavras)."""
    return re.compile(re.sub(r"(?<!\\) +", r"\\s+", padrao), flags)


def busca(padrao: str, texto: str, grupo=1, flags=re.IGNORECASE):
    m = rx(padrao, flags).search(texto)
    if not m:
        return None
    v = m.group(grupo)
    return v.strip() if isinstance(v, str) else v


def busca_todas(padrao: str, texto: str, flags=re.IGNORECASE):
    return rx(padrao, flags).findall(texto)


def apos(rotulo: str, texto: str, padrao: str = RE_DATA, janela: int = 450):
    """Primeiro `padrao` que aparece logo DEPOIS do rótulo (o valor pode estar na linha de baixo)."""
    m = rx(rotulo).search(texto)
    if not m:
        return None
    trecho = texto[m.end(): m.end() + janela]
    m2 = re.search(padrao, trecho)
    return m2.group(1 if m2.re.groups else 0).strip() if m2 else None


def linhas(texto: str) -> list[str]:
    return texto.replace("\f", "\n").splitlines()


def trecho(texto: str, inicio: str, fim: str | None = None) -> str:
    """Texto entre o primeiro `inicio` e o primeiro `fim` depois dele (padrões tolerantes a espaçamento)."""
    m = rx(inicio).search(texto)
    if not m:
        return ""
    resto = texto[m.end():]
    if fim:
        m2 = rx(fim).search(resto)
        if m2:
            return resto[: m2.start()]
    return resto


def coluna_de(linha: str, rotulo: str) -> int | None:
    """Posição (coluna de caractere) em que um rótulo começa numa linha, sem acento e sem diferenciar maiúsculas."""
    i = sem_acento(linha).upper().find(sem_acento(rotulo).upper())
    return i if i >= 0 else None


def montar_id(fornecedor: str, numero, conta, comp) -> str:
    n = digitos(numero)
    if n:
        return f"{fornecedor}_{n}"
    c = digitos(conta).lstrip("0")
    return f"{fornecedor}_{c or 'SEMCONTA'}_{comp or 'SEMCOMP'}"


@dataclass
class Resultado:
    faturas: list[dict] = field(default_factory=list)
    itens: list[dict] = field(default_factory=list)
    historico: list[dict] = field(default_factory=list)
    borderos: list[dict] = field(default_factory=list)
    contas_bordero: list[dict] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def estender(self, outro: "Resultado"):
        for k in ("faturas", "itens", "historico", "borderos", "contas_bordero", "avisos"):
            getattr(self, k).extend(getattr(outro, k))


def nova_fatura(fornecedor: str, arquivo: str, ocr: bool = False, origem: str = "fatura") -> dict:
    f = S.linha_vazia(S.ABA_FATURAS)
    f.update(fornecedor=fornecedor, cnpj_fornecedor=S.FORNECEDORES.get(fornecedor, {}).get("cnpj"),
             arquivo_pdf=arquivo, extraido_por_ocr=bool(ocr), origem=origem)
    return f


def novo_item(f: dict, ordem: int, descricao: str, valor, codigo=None) -> dict:
    d = S.linha_vazia(S.ABA_ITENS)
    desc = " ".join(str(descricao or "").split())
    d.update(id_fatura_agua=f.get("id_fatura_agua"), fornecedor=f["fornecedor"], conta=f.get("conta"),
             competencia=f.get("competencia"), ordem=ordem, codigo=(str(codigo).strip() if codigo else None),
             descricao=desc, descricao_normalizada=normalizar_descricao(desc), categoria_valor=categoria_valor(desc),
             valor=moeda(valor) if not isinstance(valor, (int, float)) else float(valor))
    return d


def novo_historico(f: dict, comp, consumo, valor=None, tipo=None) -> dict | None:
    c = competencia(comp)
    if not c:
        return None
    d = S.linha_vazia(S.ABA_HISTORICO)
    d.update(id_fatura_agua=f.get("id_fatura_agua"), fornecedor=f["fornecedor"], conta=f.get("conta"),
             competencia_fatura=f.get("competencia"), competencia=c, consumo_m3=inteiro(consumo),
             valor=moeda(valor) if valor is not None and not isinstance(valor, (int, float)) else valor, tipo=tipo)
    return d


def numero_do_nome(nome_arquivo: str) -> str | None:
    """'FATURA Nº 110495 - ...pdf' → '110495' (o número que o próprio acervo dá ao arquivo)."""
    m = re.search(r"FATURA\s*-?\s*N[º°o]?\.?\s*(\d{4,})", os.path.basename(nome_arquivo or ""), re.IGNORECASE)
    return m.group(1) if m else None


def vencimento_do_nome(caminho: str) -> str | None:
    """'… - VENC. 05.02.2024.pdf' → '2024-02-05'; sem o ano no nome, usa o ano da pasta ('2021/… venc. 27.05.pdf')."""
    nome = os.path.basename(caminho or "")
    m = re.search(r"V(?:ENC[A-Z]*|CTO)\.?\s*(\d{2})[.\-/](\d{2})(?:[.\-/](\d{2,4}))?", nome, re.IGNORECASE)
    if not m:
        return None
    ano = m.group(3)
    if not ano:
        pasta = os.path.dirname(caminho or "")
        ma = re.search(r"(20\d{2})", os.path.basename(pasta) + " " + os.path.basename(os.path.dirname(pasta)))
        ano = ma.group(1) if ma else None
    return data_iso(f"{m.group(1)}/{m.group(2)}/{ano}") if ano else None


def fechar_fatura(f: dict, itens: list[dict], nome_arquivo: str = "") -> None:
    """Completa a fatura: conta em dígitos, competência (do nome do arquivo se faltar), id, somas por categoria a partir
    dos itens (quando o extrator não preencheu) e soma dos itens."""
    n_nome = numero_do_nome(nome_arquivo)
    if n_nome and (not f.get("numero_fatura") or (f.get("extraido_por_ocr") and digitos(f["numero_fatura"]) != n_nome)):
        f["numero_fatura"] = n_nome        # nome do arquivo é mais confiável do que o OCR
    if f.get("conta_formatada") and not f.get("conta"):
        f["conta"] = digitos(f["conta_formatada"])
    elif f.get("conta") and not f.get("conta_formatada"):
        f["conta_formatada"] = str(f["conta"])
    if f.get("conta"):
        f["conta"] = digitos(f["conta"])
    if f.get("competencia"):
        f["competencia"] = competencia(f["competencia"]) or f["competencia"]
    if not f.get("competencia") and nome_arquivo:
        f["competencia"] = competencia_do_nome(os.path.basename(nome_arquivo)) or competencia_por_caminho(nome_arquivo)
    for k in ("data_emissao", "data_vencimento", "data_leitura_anterior", "data_leitura_atual"):
        if f.get(k):
            f[k] = data_iso(f[k]) or f[k]
    if nome_arquivo and (f.get("extraido_por_ocr") or not f.get("data_vencimento")):
        v = vencimento_do_nome(nome_arquivo)        # OCR erra dígitos de datas; o nome dado pelo acervo é confiável
        if v:
            f["data_vencimento"] = v
    f["id_fatura_agua"] = montar_id(f["fornecedor"], f.get("numero_fatura"), f.get("conta"), f.get("competencia"))
    for it in itens:
        it["id_fatura_agua"] = f["id_fatura_agua"]
        it["conta"] = f.get("conta")
        it["competencia"] = f.get("competencia")
    somas = {c: 0.0 for c in S.CATEGORIAS_VALOR}
    tem = False
    for it in itens:
        if it.get("valor") is None:
            continue
        tem = True
        somas[it["categoria_valor"]] += it["valor"]
    if tem:
        f["soma_itens"] = round(sum(somas.values()), 2)
        if f.get("valor_agua") is None:
            f["valor_agua"] = round(somas["agua"], 2)
        if f.get("valor_esgoto") is None:
            f["valor_esgoto"] = round(somas["esgoto"], 2)
        if f.get("valor_taxas") is None:
            f["valor_taxas"] = round(somas["taxas"] + somas["outros"] + somas["credito"], 2)
        if f.get("valor_multa_juros") is None:
            f["valor_multa_juros"] = round(somas["multa_juros"], 2)
        if f.get("valor_total") is None:
            f["valor_total"] = f["soma_itens"]
    for k in ("valor_agua", "valor_esgoto", "valor_taxas", "valor_multa_juros", "valor_total", "soma_itens"):
        v = f.get(k)
        if isinstance(v, str):
            f[k] = moeda(v)
    for k in ("leitura_anterior", "leitura_atual", "consumo_m3", "consumo_faturado_m3", "dias"):
        v = f.get(k)
        if v is not None and not isinstance(v, (int, float)):
            f[k] = inteiro(v)
    if f.get("consumo_faturado_m3") is None and f.get("consumo_m3") is not None:
        f["consumo_faturado_m3"] = f["consumo_m3"]
    for k in ("nome_cliente", "logradouro", "tipo_consumo", "categoria", "hidrometro", "numero_fatura"):
        if f.get(k):
            f[k] = " ".join(str(f[k]).split())


def itens_coluna_direita(texto_linhas: list[str], i_cabecalho: int, col: int, parar: str, incluir_sub: bool = False):
    """Itens impressos numa coluna à direita (a partir da coluna `col`), da linha seguinte ao cabeçalho até `parar`.
    Devolve [(descricao, valor_str)] — linhas de detalhe que começam com '>' são ignoradas."""
    saida = []
    for ln in texto_linhas[i_cabecalho + 1:]:
        seg = ln[max(0, col - 3):]
        if rx(parar).search(seg):
            break
        s = seg.strip()
        if not s or (s.startswith(">") and not incluir_sub):
            continue
        m = re.match(r"^(.+?)\s+(" + RE_MOEDA + r")\s*$", s)
        if m and re.search(r"[A-Za-zÀ-ÿ]", m.group(1)):
            saida.append((m.group(1).strip(" -"), m.group(2)))
    return saida


def categoria_por_contagem(texto: str) -> str | None:
    """Quadro 'RES COM PÚB IND …' com as contagens de economias na(s) linha(s) de baixo → a categoria com contagem > 0.
    A ordem dos rótulos varia entre concessionárias; é lida do próprio cabeçalho."""
    for m in re.finditer(r"^(.*\bRES\b.*\bCOM\b.*)$", texto, re.MULTILINE):
        cab = sem_acento(m.group(1)).upper()
        rotulos = re.findall(r"\b(RES|COM|PUB|IND|OUT)\b", cab)
        if len(rotulos) < 3:
            continue
        resto = texto[m.end(): m.end() + 400]
        for ln in resto.splitlines()[1:4]:
            nums = re.findall(r"\b(\d{1,3})\b", ln)
            if len(nums) >= len(rotulos):
                n = [int(x) for x in nums[: len(rotulos)]]
                if any(n):
                    return rotulos[n.index(max(n))]
    return None
