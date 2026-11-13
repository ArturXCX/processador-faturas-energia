"""Utilidades compartilhadas pelos extratores de água: regex tolerante a espaçamento, montagem das linhas canônicas,
itens/histórico e o resultado de um PDF."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import permutations

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
    consumo_rodape_lido: dict = field(default_factory=dict)       # borderô Saneago → consumo LIDO no rodapé (None = não lido)

    def estender(self, outro: "Resultado"):
        for k in ("faturas", "itens", "historico", "borderos", "contas_bordero", "avisos"):
            getattr(self, k).extend(getattr(outro, k))
        self.consumo_rodape_lido.update(outro.consumo_rodape_lido)


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


def dia_mes_vencimento_do_nome(caminho: str) -> tuple[str, str] | None:
    """(dia, mês) do vencimento que o acervo pôs no nome do arquivo ('… VENC. 23.06.pdf' → ('23', '06')), com ou sem ano."""
    m = re.search(r"V(?:ENC[A-Z]*|CTO)\.?\s*(\d{2})[.\-/](\d{2})(?![\d])", os.path.basename(caminho or ""), re.IGNORECASE)
    return (m.group(1), m.group(2)) if m else None


def vencimento_plausivel(venc: str | None, comp: str | None) -> str | None:
    """Vencimento tirado do NOME do arquivo que cai antes do mês de referência só acontece com o ano truncado no nome
    ("… OUTUBRO.2023 - VENC. 23.11.20.pdf" → 2020-11-23): mantém dia e mês e usa o ano da competência (o seguinte, se o
    mês do vencimento for menor que o dela). Vencimento no mês da competência ou depois volta como veio."""
    if not venc or not comp or not re.fullmatch(r"\d{4}-\d{2}", str(comp)) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(venc)):
        return venc
    if venc[:7] >= comp:
        return venc
    ano = int(comp[:4]) + (1 if venc[5:7] < comp[5:7] else 0)
    return f"{ano:04d}{venc[4:]}"


def vencimento_pelo_documento(texto: str, caminho: str) -> str | None:
    """Vencimento lido no documento que confere com o dia e o mês do nome do arquivo: serve quando o nome não traz o ano e a
    pasta também não ('sem_/FATURA … VENC. 23.06.pdf' + "23/06/2021" impresso → '2021-06-23'). Só datas de 2015 a 2035."""
    dm = dia_mes_vencimento_do_nome(caminho)
    if not dm:
        return None
    for m in re.finditer(r"(?<!\d)(\d{2})\s?/\s?(\d{2})\s?/\s?(20\d{2})(?!\d)", texto or ""):
        if (m.group(1), m.group(2)) == dm and 2015 <= int(m.group(3)) <= 2035:
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


# ── linha digitável de arrecadação (contas de concessionárias: "8" + segmento + tipo de valor + DV geral + valor …) ─────
# um bloco: 11 dígitos e, se impresso junto, o dígito verificador ("82650000001-1", "81450325000.7", "82620000004 8")
_RE_BLOCO_ARRECADACAO = re.compile(r"(?<![\dOo.,/-])([\dOo]{11})(?:\s?[-. ]\s?([\dOo])(?![\dOo,]))?(?![\dOo])")


def _dv_mod10(digitos_: str) -> int:
    soma = 0
    for i, c in enumerate(reversed(digitos_)):
        p = int(c) * (2 if i % 2 == 0 else 1)
        soma += p // 10 + p % 10
    return (10 - soma % 10) % 10


def _blocos_arrecadacao(texto: str) -> list[tuple[int, int, str, str | None]]:
    """(linha, coluna, 11 dígitos, DV impresso ou None) de cada bloco de 11 dígitos do texto; O/o lidos pelo OCR viram 0."""
    saida = []
    for i, ln in enumerate((texto or "").replace("\f", "\n").split("\n")):
        for m in _RE_BLOCO_ARRECADACAO.finditer(ln):
            b = re.sub(r"[Oo]", "0", m.group(1))
            d = re.sub(r"[Oo]", "0", m.group(2)) if m.group(2) else None
            saida.append((i, m.start(), b, d))
    return saida


def linha_digitavel(texto: str) -> dict | None:
    """Linha digitável de arrecadação lida no texto → {"valor", "conferida", "blocos"} ou None.

    O valor ocupa os dígitos 5 a 15 do código de 44 dígitos (os 7 últimos do 1º bloco + os 4 primeiros do 2º).
    `conferida` só é True quando os QUATRO blocos foram achados (na linha do 1º ou até 3 linhas de distância: o OCR de
    página torta espalha a linha), cada DV impresso confere com o seu bloco e o DV geral (4º dígito, módulo 10 sobre os
    outros 43) confere: um dígito trocado pelo OCR, ou um bloco fora de ordem, reprova. Sem os quatro blocos, devolve o
    valor do 1º bloco + o bloco seguinte da mesma linha com `conferida=False`: é só mais uma leitura, a confirmar por
    outra fonte. Tipos de valor 8 e 9 (módulo 11) não são tratados."""
    blocos = _blocos_arrecadacao(texto)
    incompleta = None
    for k, (i, _col, b1, d1) in enumerate(blocos):
        if not re.match(r"8[1-9][67]", b1):
            continue
        outros = [b for j, b in enumerate(blocos) if j != k and abs(b[0] - i) <= 3 and b[2] != b1]
        if len(outros) == 3 and (d1 is None or _dv_mod10(b1) == int(d1)) \
                and all(b[3] is None or _dv_mod10(b[2]) == int(b[3]) for b in outros):
            def geral(ordem) -> bool:
                return _dv_mod10(b1[:3] + b1[4:] + "".join(b[2] for b in ordem)) == int(b1[3])
            mesma_linha = all(b[0] == i for b in outros)
            # na mesma linha vale a ordem do texto; espalhados em linhas vizinhas, a ordem das colunas (é uma linha só no papel)
            ordem = outros if mesma_linha else sorted(outros, key=lambda b: b[1])
            if not geral(ordem) and not mesma_linha:
                validas = [list(p) for p in permutations(outros) if geral(p)]
                ordem = validas[0] if len(validas) == 1 else ordem
            if geral(ordem):
                return {"valor": int(b1[4:] + ordem[0][2][:4]) / 100.0, "conferida": True, "blocos": [b1] + [b[2] for b in ordem]}
        seg = [b for b in blocos[k + 1:] if b[0] == i]
        if seg and incompleta is None and d1 is not None and seg[0][3] is not None \
                and _dv_mod10(b1) == int(d1) and _dv_mod10(seg[0][2]) == int(seg[0][3]):
            incompleta = {"valor": int(b1[4:] + seg[0][2][:4]) / 100.0, "conferida": False, "blocos": [b1, seg[0][2]]}
    return incompleta


def valor_linha_digitavel(texto: str, conferir: bool = True, orgao: tuple[str, ...] = ()) -> float | None:
    """Valor do documento pela linha digitável de arrecadação ("82650000001-1 10300325000-0 12550625250-6 02308300002-8").

    Devolve o valor de uma linha CONFERIDA (ver `linha_digitavel`). Com `orgao` (os 7 dígitos fixos que fecham o 2º bloco
    na concessionária, p. ex. "0325000" no SAAE Abadiânia) aceita também a linha em que o OCR só leu bem os dois primeiros
    blocos: 1º e 2º, cada um conferido pelo próprio DV, e o 2º terminando no código do órgão — um bloco fora de ordem não
    passa por 2º bloco. `conferir=False` devolve ainda o de uma linha incompleta qualquer: só serve como uma leitura a
    mais, a confirmar por outra fonte."""
    r = linha_digitavel(texto)
    if r and r["conferida"]:
        return r["valor"]
    if orgao:
        bons = [b[2] for b in _blocos_arrecadacao(texto) if b[3] is not None and _dv_mod10(b[2]) == int(b[3])]
        b1s = {b for b in bons if re.match(r"8[1-9][67]", b)}
        b2s = {b for b in bons if b[4:] in orgao}
        if len(b1s) == 1 and len(b2s) == 1:
            return int(next(iter(b1s))[4:] + next(iter(b2s))[:4]) / 100.0
    if r and not conferir:
        return r["valor"]
    return None


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
            f["data_vencimento"] = vencimento_plausivel(v, f.get("competencia"))
        elif re.fullmatch(r"\d{4}-\d{2}", str(f.get("competencia") or "")):
            # nome com dia e mês do vencimento mas sem ano, numa pasta sem ano ("sem_/FATURA DE ÁGUA - VENC. 27.05.pdf"): o ano
            # é o da competência, ou o seguinte se o mês do vencimento for menor que o dela
            dm = dia_mes_vencimento_do_nome(nome_arquivo)
            if dm:
                ano = int(f["competencia"][:4]) + (1 if dm[1] < f["competencia"][5:7] else 0)
                f["data_vencimento"] = data_iso(f"{dm[0]}/{dm[1]}/{ano}") or f.get("data_vencimento")
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
    # IRPJ retido (valor com o sinal impresso, negativo): já está dentro de valor_total e de valor_taxas. O bruto é o total
    # sem esse desconto. Calculado só aqui, com valor_total já definido (impresso, ou soma_itens) e convertido em número.
    irpj = [it["valor"] for it in itens
            if it.get("valor") is not None and re.search(r"\bIRPJ\b", it.get("descricao_normalizada") or "")]
    f["valor_irpj"] = round(sum(irpj), 2) if irpj else None
    f["valor_bruto"] = round(f["valor_total"] - (f["valor_irpj"] or 0), 2) if f.get("valor_total") is not None else None
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
