"""Ponto de entrada: um PDF de água → Resultado (faturas, itens, histórico, borderôs, contas de borderô).

`processar_pdf(caminho)` abre o PDF (texto em layout; OCR nas páginas-imagem), identifica fornecedor e tipo pelo
conteúdo e despacha para o extrator certo. Todas as concessionárias produzem as MESMAS colunas (schema_agua)."""
from __future__ import annotations

import os

from . import (codego, demae, duam, gsan, identificar, leopoldo_bulhoes, saae_abadiania, saneago_analitica,
               saneago_bordero, sanesc)
from .base import Resultado, montar_id
from .texto import Documento, competencia_por_caminho

_GSAN = {"AGUAS_IPAMERI", "BURITI_ALEGRE_AMBIENTAL", "SAO_SIMAO_SA", "SAE_CATALAO"}
_DUAM = {"SAAE_CORUMBA", "SAAE_MINEIROS"}


class FornecedorDesconhecido(ValueError):
    pass


def processar_documento(doc: Documento, caminho: str, fornecedor: str | None = None) -> Resultado:
    nome, pasta = os.path.basename(caminho), os.path.basename(os.path.dirname(caminho))
    base = doc.simples if len(doc.simples.strip()) > 40 else doc.texto
    forn = fornecedor or identificar.fornecedor(base, nome, pasta)
    if not forn:
        raise FornecedorDesconhecido(f"fornecedor de água não identificado em {nome}")
    tp = identificar.tipo(base, forn, nome)
    # os extratores recebem o caminho completo: o nome do arquivo e a pasta (ano) socorrem competência/vencimento no OCR
    if forn == "SANEAGO":
        if tp == identificar.TIPO_ANALITICA:
            res = saneago_analitica.extrair(doc, caminho)
        else:
            res = saneago_bordero.extrair(doc, caminho)
    elif forn in _GSAN:
        res = gsan.extrair(doc, caminho, forn)
    elif forn in ("DEMAE_CALDAS_NOVAS", "DEMAE_PANAMA"):
        res = demae.extrair(doc, caminho, forn)
    elif forn == "SAAE_ABADIANIA":
        res = saae_abadiania.extrair(doc, caminho, forn)
    elif forn in _DUAM:
        res = duam.extrair(doc, caminho, forn)
    elif forn == "SANESC":
        res = sanesc.extrair(doc, caminho, forn)
    elif forn == "SAAE_LEOPOLDO_BULHOES":
        res = leopoldo_bulhoes.extrair(doc, caminho, forn)
    elif forn == "CODEGO":
        res = codego.extrair(doc, caminho, forn)
    else:
        raise FornecedorDesconhecido(f"sem extrator para {forn}")
    comp_caminho = None
    for f in res.faturas:
        f["arquivo_pdf"] = nome
        f["extraido_por_ocr"] = bool(doc.usou_ocr)
        if not f.get("competencia") or str(f["competencia"]) < "2015":
            comp_caminho = comp_caminho or competencia_por_caminho(caminho)
            if comp_caminho:
                f["competencia"] = comp_caminho
                f["id_fatura_agua"] = montar_id(f["fornecedor"], f.get("numero_fatura"), f.get("conta"), comp_caminho)
    for b in res.borderos:
        b["arquivo_pdf"] = nome
    for a in res.avisos:
        pass
    res.avisos = [a.replace(caminho, nome) for a in res.avisos]
    return res


def processar_pdf(caminho: str, fornecedor: str | None = None, ocr: bool = True) -> Resultado:
    doc = Documento(caminho, ocr=ocr)
    return processar_documento(doc, caminho, fornecedor)


def tipo_do_pdf(caminho: str, ocr: bool = False) -> tuple[str | None, str | None]:
    """(fornecedor, tipo) de um PDF, para classificação rápida (bot/vigia); sem OCR por padrão."""
    doc = Documento(caminho, ocr=ocr)
    base = doc.simples if len(doc.simples.strip()) > 40 else doc.texto
    forn = identificar.fornecedor(base, os.path.basename(caminho), os.path.basename(os.path.dirname(caminho)))
    if not forn:
        return None, None
    return forn, identificar.tipo(base, forn, os.path.basename(caminho))
