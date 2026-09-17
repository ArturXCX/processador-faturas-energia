"""SANEAGO — borderô (fatura agrupada de órgão público): várias contas num único documento, retenção de IRPJ no nível da
fatura. Um PDF pode conter mais de uma fatura agrupada (desde 2024, três por mês).

Dois formatos da tabela de contas:
  * antigo: CONSUMO (M³) ÁGUA · VALOR R$ · CONSUMO (M³) ESGOTO · VALOR R$
  * novo:   CONSUMO (M³) · ÁGUA · ESGOTO · SMRSU
Cada número da linha é atribuído à coluna cujo rótulo do cabeçalho está mais perto (uma coluna em branco não desloca as
demais), como no extrator original de Matheus Braga. Funciona igual para PDF de texto e para OCR posicional."""
from __future__ import annotations

import re
from collections import Counter

from . import schema_agua as S
from .base import RE_MOEDA, Resultado, busca, rx
from .texto import competencia, data_iso, inteiro, moeda, sem_acento

_RE_CONTA = re.compile(r"^\s*(\d{3,9})(?:\s*[-—–]?\s*(\d))?(?=\s|[-—–])")
_RE_MOEDA_TOK = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{1,2}$|^-?\d*,\d{1,2}$")     # ",03" = 0,03 (a Saneago omite o zero)
_RE_INT_TOK = re.compile(r"^\d{1,3}(?:\.\d{3})*$|^\d+$")
_RE_FATURA = rx(r"N[º°o]\s*FATURA:?\s+(\d{6,})")
_FIM_TABELA = ("FATURADO TOTAL", "INFORMACOES IMPORTANTES", "COMUNICADO", "RETENCOES", "TOTAL DA FATURA")


def _up(s: str) -> str:
    return " ".join(sem_acento(s).upper().split())


def _centro(m) -> float:
    return (m.start() + m.end()) / 2


def _colunas(cab: str, ant: str) -> dict:
    """Centros (coluna de caractere) dos rótulos das colunas numéricas do cabeçalho da tabela."""
    up, up_ant = sem_acento(cab).upper(), sem_acento(ant).upper()
    cols = {"nome": up.find("NOME"), "log": up.find("LOGRADOURO"), "valores": [], "consumos": []}
    if "SMRSU" in up or "SMRSU" in up_ant:
        cols["formato"] = "novo"
        rot = up if "SMRSU" in up else up_ant
        for k, r in (("agua", r"\bAGUA\b"), ("esgoto", r"\bESGOTO\b"), ("smrsu", r"\bSMRSU\b")):
            m = re.search(r, rot)
            if m:
                cols["valores"].append((k, _centro(m)))
        m = re.search(r"CONSUMO", up) or re.search(r"CONSUMO", up_ant)
        cols["consumos"] = [("consumo", _centro(m) + 3)] if m else []
    else:
        cols["formato"] = "antigo"
        vals = [_centro(m) for m in re.finditer(r"VALOR", up)]
        cols["valores"] = [("agua", vals[0])] if vals else []
        if len(vals) > 1:
            cols["valores"].append(("esgoto", vals[1]))
        ma, me = re.search(r"\bAGUA\b", up), re.search(r"\bESGOTO\b", up)
        cons = [_centro(m) for m in re.finditer(r"CONSUMO", up_ant)]
        if ma:
            cols["consumos"].append(("consumo", _centro(ma)))
        elif cons:
            cols["consumos"].append(("consumo", cons[0] + 3))
        if me:
            cols["consumos"].append(("consumo_esgoto", _centro(me)))
        elif len(cons) > 1:
            cols["consumos"].append(("consumo_esgoto", cons[1] + 3))
    if not cols["valores"]:
        cols["valores"] = [("agua", len(cab) - 6)]
    return cols


_TRACOS = ("-", "—", "–", "R$", "R5", "RS")


def _numeros_da_cauda(ln: str, cols: dict, ocr: bool):
    """Números do fim da linha (a "cauda" numérica depois do logradouro) → (valores, consumos, início da cauda).

    Cada número vai para a coluna cujo rótulo está mais perto; se essa coluna já tem valor (linha "escorregada" por um
    logradouro longo, que empurra os números para a esquerda), vai para a coluna livre mais perto. Só os últimos
    N números da linha entram (N = colunas numéricas do cabeçalho): os demais são números do logradouro."""
    toks = list(re.finditer(r"\S+", ln))
    cauda = []
    for t in reversed(toks):
        s = t.group(0)
        if _RE_MOEDA_TOK.match(s) or _RE_INT_TOK.match(s) or s in _TRACOS:
            cauda.append(t)
        else:
            break
    numericos = [t for t in reversed(cauda) if t.group(0) not in _TRACOS]
    max_n = len(cols["valores"]) + len(cols["consumos"])
    numericos = numericos[-max_n:] if max_n else []
    valores: dict[str, float] = {}
    consumos: dict[str, int] = {}
    usados: list = []

    def _coluna(colunas, ocupadas, c):
        k, _ = min(colunas, key=lambda kv: abs(c - kv[1]))
        if k in ocupadas:
            livres = [kv for kv in colunas if kv[0] not in ocupadas]
            if not livres:
                return None
            k = min(livres, key=lambda kv: abs(c - kv[1]))[0]
        return k

    moedas = [t for t in numericos if _RE_MOEDA_TOK.match(t.group(0))]
    inteiros = [t for t in numericos if not _RE_MOEDA_TOK.match(t.group(0))]
    for t in reversed(moedas):
        c = (t.start() + t.end()) / 2
        k = _coluna(cols["valores"], valores, c)
        if k is None:
            continue
        valores[k] = moeda(t.group(0))
        usados.append(t)
    for t in reversed(inteiros):
        s, c = t.group(0), (t.start() + t.end()) / 2
        d = s.replace(".", "")
        kv, dv = min(cols["valores"], key=lambda kv: abs(c - kv[1]))
        kc, dc = min(cols["consumos"], key=lambda kv: abs(c - kv[1])) if cols["consumos"] else (None, 1e9)
        if len(d) >= 3 and (ocr or len(d) >= 4) and kv not in valores and abs(c - dv) < abs(c - dc) and abs(c - dv) <= 10:
            valores[kv] = float(d[:-2] + "." + d[-2:])          # camada de texto/OCR perdeu a vírgula (32318 → 323,18)
            usados.append(t)
            continue
        k = _coluna(cols["consumos"], consumos, c) if cols["consumos"] else None
        if k is None:
            break                                                # inteiro sobrando à esquerda: é número do logradouro
        consumos[k] = int(d)
        usados.append(t)
    inicio = min((t.start() for t in usados), default=len(ln))
    return valores, consumos, inicio


def _col_logradouro(linhas_conta: list[tuple[str, int, int]], cols: dict) -> int:
    """Coluna em que começa o logradouro nas linhas da página: o início de segmento (após 2+ espaços) mais frequente
    perto do rótulo LOGRADOURO; senão o próprio rótulo."""
    alvo = cols["log"] if cols["log"] >= 0 else cols["nome"] + 30
    cont = Counter()
    for ln, ini, fim in linhas_conta:
        for m in re.finditer(r"\s{2,}(?=\S)", ln[ini:fim]):
            pos = ini + m.end()
            if abs(pos - alvo) <= 28:
                cont[pos] += 1
    if cont:
        melhor = max(cont.items(), key=lambda kv: (kv[1], -abs(kv[0] - alvo)))[0]
        return melhor
    return max(alvo - 2, 0)


def _dividir_texto(ln: str, ini: int, fim: int, col_log: int) -> tuple[str, str]:
    texto = ln[ini:fim]
    if col_log <= ini or col_log >= fim:
        partes = re.split(r"\s{2,}", texto.strip(), maxsplit=1)
        return (partes[0], partes[1] if len(partes) > 1 else "")
    c = col_log
    if ln[c - 1] != " ":
        for d in (1, -1, 2, -2, 3, -3):
            if 0 < c + d < len(ln) and ln[c + d - 1] == " " and ln[c + d] != " ":
                c = c + d
                break
    return ln[ini:c].strip(" -—–"), ln[c:fim].strip(" -—–")


def _com_valor_vizinho(L: list[str], i: int) -> str:
    """Rótulo sem número na própria linha: junta a linha vizinha (anterior, senão seguinte) se ela só tiver um número."""
    so_numero = re.compile(r"^\s*(?:R\$)?\s*[\d.,]+\s*$")
    for j in (i - 1, i + 1):
        if 0 <= j < len(L) and so_numero.match(L[j]):
            return L[i] + " " + L[j].strip()
    return L[i]


def _linha_conta(ln: str):
    m = _RE_CONTA.match(ln)
    if not m:
        return None
    conta, dv = m.group(1), m.group(2)
    if dv is None:
        if len(conta) < 5:
            return None
        conta, dv = conta[:-1], conta[-1]
    return conta, dv, m.end()


def extrair(doc, arquivo: str) -> Resultado:
    res = Resultado()
    faturas: dict[str, dict] = {}
    ordem: list[str] = []
    atual: dict | None = None
    cols: dict | None = None
    ocr = doc.usou_ocr
    for pagina in doc.paginas:
        L = pagina.splitlines()
        em_tabela = False
        pendentes: list[tuple[dict, str, int, int, dict, dict]] = []   # linhas de conta da página (nome/logradouro depois)
        for i, ln in enumerate(L):
            up = _up(ln)
            mf = _RE_FATURA.search(ln)
            if mf:
                num = mf.group(1)
                if num not in faturas:
                    b = S.linha_vazia(S.ABA_BORDEROS)
                    b.update(id_bordero_agua=f"SANEAGO_{num}", fornecedor="SANEAGO", numero_fatura=num, arquivo_pdf=arquivo,
                             quantidade_contas_extraidas=0, extraido_por_ocr=ocr, observacao="")
                    faturas[num] = b
                    ordem.append(num)
                atual = faturas[num]
            if atual is None:
                continue
            if "MES/ANO" in up and not atual.get("competencia"):
                atual["competencia"] = competencia(busca(r"M[ÊE]S/ANO\s*REF\.?:?\s*(\d{1,2}/\d{4})", ln))
            if "EMISSAO" in up and not atual.get("data_emissao"):
                atual["data_emissao"] = data_iso(busca(r"EMISS[ÃA]O:?\s*(\d{2}/\d{2}/\d{4})", ln))
            if "VENCIMENTO" in up and not atual.get("data_vencimento"):
                atual["data_vencimento"] = data_iso(busca(r"VENCIMENTO:?\s*(\d{2}/\d{2}/\d{4})", ln))
            if "ORGAO PAGADOR" in up and "CODIGO" in up:
                atual["cod_pagador"] = atual.get("cod_pagador") or busca(r"PAGADOR\s+(\d{3,})", ln)
                atual["cod_agrupador"] = atual.get("cod_agrupador") or busca(r"AGRUPADOR\s+(\d{3,})", ln)
            if "NOME DO ORGAO AGRUPADOR" in up:
                for j in range(i + 1, min(i + 4, len(L))):
                    m = re.search(r"^\s*(.*?\S)\s+(\d{3,})\s+(\d{3,})\s*$", L[j])
                    if m:
                        atual["nome_agrupador"] = atual.get("nome_agrupador") or " ".join(m.group(1).split())
                        atual["cod_agrupador"] = atual.get("cod_agrupador") or m.group(2)
                        atual["cod_pagador"] = atual.get("cod_pagador") or m.group(3)
                        break
                    if L[j].strip() and not atual.get("nome_agrupador") and not re.search(r"\d{3,}", L[j]):
                        atual["nome_agrupador"] = " ".join(L[j].split())
            if "CONTA" in up and "DV" in up and ("NOME" in up or "CLIENTE" in up):
                cols = _colunas(ln, L[i - 1] if i else "")
                atual["formato"] = atual.get("formato") or cols["formato"]
                em_tabela = True
                continue
            if em_tabela and not any(k in up for k in _FIM_TABELA):
                lc = _linha_conta(ln)
                if lc and cols:
                    conta, dv, fim_conta = lc
                    valores, consumos, ini_cauda = _numeros_da_cauda(ln, cols, ocr)
                    d = S.linha_vazia(S.ABA_CONTAS_BORDERO)
                    d.update(id_bordero_agua=atual["id_bordero_agua"], fornecedor="SANEAGO", conta=conta + dv,
                             conta_formatada=f"{conta} {dv}", consumo_m3=consumos.get("consumo"),
                             valor_agua=valores.get("agua"), valor_esgoto=valores.get("esgoto"), valor_smrsu=valores.get("smrsu"),
                             valor_total=round(sum(valores.values()), 2), ordem=atual["quantidade_contas_extraidas"] + 1)
                    atual["quantidade_contas_extraidas"] += 1
                    pendentes.append((d, ln, fim_conta, ini_cauda, cols, atual))
                    res.contas_bordero.append(d)
                continue
            em_tabela = False
            # rodapé da fatura (a partir de 2026 o valor pode sair na linha vizinha ao rótulo)
            if not re.search(r"\d", ln):
                ln = _com_valor_vizinho(L, i)
            if "FATURADO TOTAL" in up or "TOTAL DA FATURA" in up:
                if "R$" in ln:
                    v = moeda(busca(r"R\$\s*(" + RE_MOEDA + ")", ln))
                    if v is not None and atual.get("base_calculo") is None:
                        atual["base_calculo"] = v
                elif cols and atual.get("valor_agua") is None:
                    valores, consumos, _ = _numeros_da_cauda(ln, cols, ocr)
                    if valores:
                        atual["valor_agua"], atual["valor_esgoto"], atual["valor_smrsu"] = valores.get("agua"), valores.get("esgoto"), valores.get("smrsu")
                        atual["consumo_total_m3"] = consumos.get("consumo")
            elif "CONTAS AGRUPADAS" in up:
                atual["quantidade_contas"] = inteiro(busca(r"AGRUPADAS:?\s*(\d+)", ln))
            elif "IMPOSTO RETIDO" in up:
                atual["valor_retido"] = moeda(busca(r"R\$\s*(" + RE_MOEDA + ")", ln))
            elif "VALOR FINAL DA FATURA" in up:
                atual["valor_final"] = moeda(busca(r"R\$\s*(" + RE_MOEDA + ")", ln))
            elif "VALOR TOTAL EM R" in up:
                v = moeda(busca(r"EM\s*R\$\s*(" + RE_MOEDA + ")", ln))
                if v is not None and atual.get("valor_final") is None:
                    atual["valor_final"] = v
            elif re.search(r"\d,\d{2}\s*%", ln) and atual.get("aliquota_irpj") is None and "IRPJ" not in up:
                m = re.search(r"(\d{1,2},\d{2})\s*%", ln)
                atual["aliquota_irpj"] = moeda(m.group(1)) if m else None
                mb = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*$", ln)
                if mb and atual.get("base_calculo") is None:
                    atual["base_calculo"] = moeda(mb.group(1))
        # nome / logradouro das contas da página, com a coluna do logradouro estimada pela própria página
        if pendentes:
            c0 = pendentes[0][4]
            col_log = _col_logradouro([(ln, ini, fim) for _d, ln, ini, fim, _c, _a in pendentes], c0)
            for d, ln, ini, fim, _c, _a in pendentes:
                nome, log = _dividir_texto(ln, ini, fim, col_log)
                d["nome_cliente"], d["logradouro"] = " ".join(nome.split()), " ".join(log.split())
    for num in ordem:
        b = faturas[num]
        contas = [c for c in res.contas_bordero if c["id_bordero_agua"] == b["id_bordero_agua"]]
        soma = round(sum(c.get("valor_total") or 0 for c in contas), 2)
        b["soma_valores_extraidos"] = soma
        if b.get("consumo_total_m3") is None and contas:
            b["consumo_total_m3"] = sum(c.get("consumo_m3") or 0 for c in contas)
        bruto = None
        if b.get("valor_agua") is not None:
            bruto = round((b.get("valor_agua") or 0) + (b.get("valor_esgoto") or 0) + (b.get("valor_smrsu") or 0), 2)
        if b.get("base_calculo") is None and b.get("valor_agua") is not None:
            b["base_calculo"] = round((b.get("valor_agua") or 0) + (b.get("valor_esgoto") or 0), 2)
        if b.get("valor_retido") is None and b.get("aliquota_irpj") and b.get("base_calculo"):
            b["valor_retido"] = round(b["base_calculo"] * b["aliquota_irpj"] / 100, 2)
        if b.get("valor_final") is None and bruto is not None:
            b["valor_final"] = round(bruto - (b.get("valor_retido") or 0), 2)
        alvo = bruto if bruto is not None else b.get("base_calculo")
        obs = []
        b["escaneado"] = "SIM" if (ocr or doc.vazio) else "NÃO"
        if not contas:
            b["bate_total"] = "N/A"
            obs.append("nenhuma conta extraída da tabela")
        elif alvo is not None:
            b["bate_total"] = "SIM" if abs(soma - alvo) < 1.0 else "NÃO"
            if b["bate_total"] == "NÃO":
                obs.append(f"soma das contas ({soma:,.2f}) difere do total impresso ({alvo:,.2f})")
        else:
            b["bate_total"] = "N/A"
            obs.append("total impresso não encontrado")
        if b.get("quantidade_contas") and b["quantidade_contas"] != b["quantidade_contas_extraidas"]:
            obs.append(f"{b['quantidade_contas_extraidas']} contas extraídas de {b['quantidade_contas']} informadas")
        if ocr:
            obs.append("PDF digitalizado: lido por OCR (conferir valores)")
        b["observacao"] = "; ".join(obs)
        for c in contas:
            c["competencia"] = b.get("competencia")
        res.borderos.append(b)
    if not ordem:
        res.avisos.append(f"{arquivo}: nenhum 'Nº FATURA' encontrado (texto vazio ou ilegível)")
    return res
