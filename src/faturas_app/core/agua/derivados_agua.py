"""Colunas derivadas e VALIDAÇÃO das faturas de água (todas as concessionárias, mesmo modelo).

* conta canônica / unidade institucional pelo mapa de contas (`mapa_conta`);
* regras de validação (aba `validacao_agua`): uma linha por ocorrência, com gravidade erro / aviso / info;
* cruzamento borderô × analítica da Saneago (a mesma conta, na mesma competência, deve ter o mesmo valor)."""
from __future__ import annotations

from collections import defaultdict

from . import mapa_conta
from . import schema_agua as S
from .base import Resultado

TOL_VALOR = 1.0     # R$ — soma dos itens × total impresso
TOL_CRUZAMENTO = 0.05

REGRAS = {
    "CONTA_AUSENTE":            ("erro", "a fatura saiu sem conta/matrícula legível"),
    "CONTA_INFERIDA_PELO_MAPA": ("info", "sem conta legível no PDF; conta atribuída porque é a única da concessionária no mapa"),
    "COMPETENCIA_AUSENTE":      ("erro", "não foi possível ler a competência (mês/ano de referência)"),
    "VALOR_TOTAL_AUSENTE":      ("erro", "não foi possível ler o valor total da fatura"),
    "ITENS_NAO_FECHAM":         ("erro", "a soma dos lançamentos difere do total impresso em mais de R$ 1"),
    "BORDERO_NAO_CONFERE":      ("erro", "a soma das contas do borderô difere do total impresso"),
    "FATURA_SEM_NUMERO":        ("info", "a concessionária não imprime número de fatura; o id usa conta + competência"),
    "LIDA_POR_OCR":             ("info", "PDF digitalizado lido por OCR — conferir os valores"),
    "LEITURA_INCONSISTENTE":    ("aviso", "leitura atual menor que a anterior"),
    "CONSUMO_DIVERGENTE":       ("aviso", "consumo impresso diferente de (leitura atual − leitura anterior)"),
    "VENCIMENTO_ANTES_DA_COMPETENCIA": ("aviso", "vencimento anterior ao mês de referência"),
    "CONTA_FORA_DO_MAPA":       ("aviso", "há mapa de contas carregado mas a conta não está nele"),
    "DUPLICIDADE":              ("aviso", "o mesmo id apareceu em mais de um PDF (só o primeiro foi mantido)"),
    "BORDERO_CONTAS_DIFEREM":   ("aviso", "quantidade de contas extraídas diferente da impressa"),
    "BORDERO_ESCANEADO":        ("info", "borderô digitalizado: contas lidas por OCR ou não extraídas"),
    "ANALITICA_DIVERGE_BORDERO": ("aviso", "valor da conta na analítica difere do valor no borderô da mesma competência"),
    "CONTA_SEM_ANALITICA":      ("aviso", "conta do borderô sem bloco correspondente na fatura analítica da competência"),
    "CONTA_SEM_BORDERO":        ("info", "conta da analítica que não aparece no borderô da competência"),
}


def _ocorrencia(id_, f: dict, regra: str, detalhe: str = "") -> dict:
    grav, desc = REGRAS[regra]
    return {"id": id_, "fornecedor": f.get("fornecedor"), "conta": f.get("conta"), "conta_canonica": f.get("conta_canonica"),
            "competencia": f.get("competencia"), "gravidade": grav, "regra": regra, "detalhe": detalhe or desc}


def _unica_conta_por_fornecedor() -> dict[str, dict]:
    """Concessionárias em que o mapa tem UMA só conta: uma fatura sem conta legível (OCR) só pode ser dela."""
    por: dict[str, list] = {}
    for r in mapa_conta.registros():
        if r.get("fornecedor"):
            por.setdefault(r["fornecedor"], []).append(r)
    return {k: v[0] for k, v in por.items() if len(v) == 1}


def aplicar_mapa(res: Resultado) -> None:
    """conta_canonica / unidade_institucional em todas as linhas com conta; fatura sem conta legível herda a conta do mapa
    quando a concessionária tem uma única conta cadastrada."""
    ativo = mapa_conta.ativo()
    unicas = _unica_conta_por_fornecedor() if ativo else {}
    for f in res.faturas + res.contas_bordero:
        forn, conta = f.get("fornecedor"), f.get("conta")
        if not conta and forn in unicas and "id_fatura_agua" in f:
            u = unicas[forn]
            f["conta_canonica"], f["unidade_institucional"] = u["conta_canonica"], u.get("unidade_institucional")
            f["observacao"] = "; ".join(x for x in (f.get("observacao"), "conta inferida pelo mapa (única conta da concessionária)") if x)
            continue
        f["conta_canonica"] = mapa_conta.canonica(conta, forn) if conta else None
        r = mapa_conta.buscar(conta, forn) if (ativo and conta) else None
        f["unidade_institucional"] = (r or {}).get("unidade_institucional")
    por_id = {f["id_fatura_agua"]: f for f in res.faturas}
    for linha in res.itens + res.historico:
        f = por_id.get(linha.get("id_fatura_agua"))
        linha["conta_canonica"] = f.get("conta_canonica") if f else mapa_conta.chave(linha.get("conta"))


def validar(res: Resultado, duplicados: list[tuple[str, str]] | None = None) -> list[dict]:
    val: list[dict] = []
    ativo = mapa_conta.ativo()
    for f in res.faturas:
        id_ = f["id_fatura_agua"]
        if not f.get("conta") and not f.get("conta_canonica"):
            val.append(_ocorrencia(id_, f, "CONTA_AUSENTE"))
        elif not f.get("conta") and f.get("conta_canonica"):
            val.append(_ocorrencia(id_, f, "CONTA_INFERIDA_PELO_MAPA", f"conta {f['conta_canonica']} ({f.get('fornecedor')})"))
        elif ativo and not mapa_conta.buscar(f["conta"], f.get("fornecedor")):
            val.append(_ocorrencia(id_, f, "CONTA_FORA_DO_MAPA", f"conta {f.get('conta_formatada') or f['conta']} ({f.get('fornecedor')})"))
        if not f.get("competencia"):
            val.append(_ocorrencia(id_, f, "COMPETENCIA_AUSENTE"))
        if f.get("valor_total") is None:
            val.append(_ocorrencia(id_, f, "VALOR_TOTAL_AUSENTE"))
        elif f.get("soma_itens") is not None and abs(f["soma_itens"] - f["valor_total"]) > TOL_VALOR:
            val.append(_ocorrencia(id_, f, "ITENS_NAO_FECHAM", f"itens {f['soma_itens']:,.2f} × total {f['valor_total']:,.2f}"))
        if not f.get("numero_fatura"):
            val.append(_ocorrencia(id_, f, "FATURA_SEM_NUMERO"))
        if f.get("extraido_por_ocr"):
            val.append(_ocorrencia(id_, f, "LIDA_POR_OCR"))
        la, lt = f.get("leitura_anterior"), f.get("leitura_atual")
        if la is not None and lt is not None:
            if lt < la:
                val.append(_ocorrencia(id_, f, "LEITURA_INCONSISTENTE", f"anterior {la} → atual {lt}"))
            elif f.get("consumo_m3") is not None and abs((lt - la) - f["consumo_m3"]) > 1 and f.get("origem") != "analitica":
                val.append(_ocorrencia(id_, f, "CONSUMO_DIVERGENTE", f"impresso {f['consumo_m3']} × leituras {lt - la}"))
        if f.get("competencia") and f.get("data_vencimento") and str(f["data_vencimento"])[:7] < f["competencia"]:
            val.append(_ocorrencia(id_, f, "VENCIMENTO_ANTES_DA_COMPETENCIA", f"vence {f['data_vencimento']}, referência {f['competencia']}"))
    for b in res.borderos:
        id_ = b["id_bordero_agua"]
        if b.get("bate_total") == "NÃO":
            val.append(_ocorrencia(id_, b, "BORDERO_NAO_CONFERE", b.get("observacao") or ""))
        if b.get("escaneado") == "SIM":
            val.append(_ocorrencia(id_, b, "BORDERO_ESCANEADO"))
        if b.get("quantidade_contas") and b.get("quantidade_contas") != b.get("quantidade_contas_extraidas"):
            val.append(_ocorrencia(id_, b, "BORDERO_CONTAS_DIFEREM", f"{b['quantidade_contas_extraidas']} extraídas de {b['quantidade_contas']}"))
    for id_, arquivo in duplicados or []:
        val.append(_ocorrencia(id_, {}, "DUPLICIDADE", f"também em {arquivo}"))
    val.extend(cruzar_bordero_analitica(res))
    return val


def cruzar_bordero_analitica(res: Resultado) -> list[dict]:
    """Saneago: cada conta do borderô deve ter o mesmo valor no bloco da analítica da mesma competência."""
    analitica: dict[tuple, dict] = {}
    comps_analitica = set()
    for f in res.faturas:
        if f.get("origem") == "analitica" and f.get("conta") and f.get("competencia"):
            analitica[(mapa_conta.chave(f["conta"]), f["competencia"])] = f
            comps_analitica.add(f["competencia"])
    comps_bordero = defaultdict(set)
    val: list[dict] = []
    for c in res.contas_bordero:
        k = (mapa_conta.chave(c.get("conta")), c.get("competencia"))
        if not k[0] or not k[1]:
            continue
        comps_bordero[k[1]].add(k[0])
        if k[1] not in comps_analitica:
            continue
        a = analitica.get(k)
        if not a:
            val.append(_ocorrencia(c["id_bordero_agua"], c, "CONTA_SEM_ANALITICA", f"conta {c.get('conta_formatada')} em {k[1]}"))
        elif a.get("valor_total") is not None and c.get("valor_total") is not None and abs(a["valor_total"] - c["valor_total"]) > TOL_CRUZAMENTO:
            val.append(_ocorrencia(c["id_bordero_agua"], c, "ANALITICA_DIVERGE_BORDERO",
                                   f"borderô {c['valor_total']:,.2f} × analítica {a['valor_total']:,.2f} ({a['id_fatura_agua']})"))
    for (conta, comp), a in analitica.items():
        if comp in comps_bordero and conta not in comps_bordero[comp]:
            val.append(_ocorrencia(a["id_fatura_agua"], a, "CONTA_SEM_BORDERO", f"conta {a.get('conta_formatada')} em {comp}"))
    return val


def aplicar(res: Resultado, duplicados: list[tuple[str, str]] | None = None) -> list[dict]:
    """Mapa + validação. Devolve as linhas da aba `validacao_agua`."""
    aplicar_mapa(res)
    return validar(res, duplicados)
