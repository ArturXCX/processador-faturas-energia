"""Ponto de entrada: um PDF de água → Resultado (faturas, itens, histórico, borderôs, contas de borderô).

`processar_pdf(caminho)` abre o PDF (texto em layout; OCR nas páginas-imagem), identifica fornecedor e tipo pelo
conteúdo e despacha para o extrator certo. Todas as concessionárias produzem as MESMAS colunas (schema_agua)."""
from __future__ import annotations

import os

from .. import ocr as ocr_motor
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
            # borderô com pouca tabela e títulos grandes: a mediana da largura de caractere da página acompanha o título
            # e desloca os números; o 1º quartil acompanha a fonte da tabela. Só aqui (nem analítica, nem outras).
            if hasattr(doc, "repaginar"):
                doc.repaginar()
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
        if not b.get("competencia"):                       # borderô sem competência lida: reserva pelo nome do arquivo
            comp_caminho = comp_caminho or competencia_por_caminho(caminho)
            if comp_caminho:
                b["competencia"] = comp_caminho
                for c in res.contas_bordero:
                    if c.get("id_bordero_agua") == b.get("id_bordero_agua"):
                        c["competencia"] = comp_caminho
    for a in res.avisos:
        pass
    res.avisos = [a.replace(caminho, nome) for a in res.avisos]
    return res


_DPIS_RELEITURA = (400, 500)         # resoluções da releitura do borderô Saneago por OCR (a leitura normal é 300 dpi)
# Da releitura só entram NÚMEROS; identidade e texto (conta, nome, logradouro, ordem, ids, competência...) são sempre os da
# leitura de 300 dpi.
_NUM_CONTA = ("consumo_m3", "valor_agua", "valor_esgoto", "valor_smrsu", "valor_total")
_NUM_BORDERO = ("valor_agua", "valor_esgoto", "valor_smrsu", "consumo_total_m3", "base_calculo", "valor_retido", "valor_final",
                "soma_valores_extraidos", "bate_total", "quantidade_contas", "quantidade_contas_extraidas")


def _contas_de(res: Resultado, bid) -> list[dict]:
    return [c for c in res.contas_bordero if c.get("id_bordero_agua") == bid]


def _conta_compativel(a, b) -> bool:
    """Mesmo número de conta, ou um é prefixo do outro (a releitura costuma perder o dígito verificador), com 4+ dígitos."""
    a, b = str(a or ""), str(b or "")
    curto, longo = sorted((a, b), key=len)
    return len(curto) >= 4 and longo.startswith(curto)


def _alinhado(base_contas: list[dict], nova_contas: list[dict]) -> bool:
    return (len(base_contas) == len(nova_contas)
            and all(_conta_compativel(x.get("conta"), y.get("conta")) for x, y in zip(base_contas, nova_contas)))


def _medida(b: dict, contas: list[dict], lido) -> tuple[int, float]:
    return saneago_bordero.medida_divergencia([b], contas, {b.get("id_bordero_agua"): lido})


def _elegivel(base_b: dict, base_lido, nb: dict, lido) -> bool:
    """A releitura não pode perder rodapé que a base leu: coluna comparável (água, esgoto, SMRSU, consumo do rodapé) lida na
    base e não lida na releitura torna o candidato inelegível (rodapé não lido não confere nada, logo não é "fechar")."""
    if any(base_b.get(k) is not None and nb.get(k) is None for k in ("valor_agua", "valor_esgoto", "valor_smrsu")):
        return False
    return not (base_lido is not None and lido is None)


def _nota_leitura(res: Resultado) -> tuple:
    """Quanto menor, melhor: borderôs que não fecham, colunas fora do rodapé, faturas sem competência e, por último, menos linhas lidas."""
    return (sum(1 for b in res.borderos if b.get("bate_total") == "NÃO"),
            saneago_bordero.medida_divergencia(res.borderos, res.contas_bordero, res.consumo_rodape_lido)[0] if res.borderos else 0,
            sum(1 for f in res.faturas if not f.get("competencia")),
            -(len(res.contas_bordero) + len(res.faturas)))


def _leitura_modelo_tabelas(caminho: str, fornecedor: str | None, res: Resultado) -> tuple[Resultado, str]:
    """Tabela digitalizada da Saneago: lê também com o modelo `por_fast` e fica com ele se a nota não piorar. Devolve (resultado, idioma)."""
    lang = ocr_motor.idioma_tabelas()
    if not lang:
        return res, "por"
    try:
        novo = processar_documento(Documento(caminho, ocr=True, lang=lang), caminho, fornecedor)
    except Exception as e:  # noqa: BLE001  (melhoria opcional: qualquer falha mantém a leitura padrão)
        res.avisos.append(f"leitura com {lang} falhou: {type(e).__name__}: {e}".replace(caminho, os.path.basename(caminho)))
        return res, "por"
    return (novo, lang) if _nota_leitura(novo) <= _nota_leitura(res) else (res, "por")


def _releitura_saneago(caminho: str, fornecedor: str | None, res: Resultado, lang: str = "por") -> Resultado:
    """Borderô Saneago lido por OCR cujas somas por coluna não fecham com o rodapé: relê o PDF a 400 e, se preciso, 500 dpi
    (o OCR a 300 dpi às vezes perde dígitos do consumo). A mescla é por borderô e NUMÉRICA: o resultado de 300 dpi continua
    sendo a base de toda identidade e texto; de cada releitura vêm só os números das contas e do rodapé, e só de um borderô
    alinhado (mesmo id, mesmo número de contas, números de conta compatíveis) e elegível (`_elegivel`: não perde rodapé que a
    base leu); nenhum valor de rodapé não nulo da base é sobrescrito por None. Cada borderô fica com a leitura de menor
    divergência (colunas divergentes, depois diferenças normalizadas); em empate, a de menor dpi (a base). Para quando todos
    fecham. Só o borderô que melhorou é reescrito e anotado. Limite inerente à métrica: somas iguais com distribuição
    diferente entre as linhas contam como "fechou". Releitura que levanta exceção deixa um aviso em `res.avisos` e a base
    sobrevive. Resíduo aceito: `base_calculo`, `valor_retido` e `valor_final` seguem vindo da releitura nos borderôs alinhados
    e elegíveis (não entram na conferência por coluna)."""
    ids = [b.get("id_bordero_agua") for b in res.borderos]
    base = {b["id_bordero_agua"]: b for b in res.borderos}
    medida = {i: _medida(base[i], _contas_de(res, i), res.consumo_rodape_lido.get(i)) for i in ids}
    escolha: dict[str, tuple[int, dict, list[dict], object]] = {}
    falhas: list[str] = []
    for dpi in _DPIS_RELEITURA:
        if all(m[0] == 0 for m in medida.values()):
            break
        try:
            kw = {} if lang == "por" else {"lang": lang}
            cand = processar_documento(Documento(caminho, ocr=True, dpi=dpi, **kw), caminho, fornecedor)
        except Exception as e:  # noqa: BLE001  (releitura é melhoria opcional: qualquer falha mantém a leitura anterior)
            falhas.append(f"releitura a {dpi} dpi falhou: {type(e).__name__}: {e}")
            continue
        novos = {b.get("id_bordero_agua"): b for b in cand.borderos}
        for i in ids:
            if medida[i][0] == 0 or i not in novos:
                continue
            nb, ncontas = novos[i], _contas_de(cand, i)
            if not _alinhado(_contas_de(res, i), ncontas):
                continue
            lido = cand.consumo_rodape_lido.get(i)
            if not _elegivel(base[i], res.consumo_rodape_lido.get(i), nb, lido):
                continue
            m = _medida(nb, ncontas, lido)
            if m < medida[i]:
                medida[i], escolha[i] = m, (dpi, nb, ncontas, lido)
    for i, (dpi, nb, ncontas, lido) in escolha.items():
        for antiga, nova in zip(_contas_de(res, i), ncontas):
            for k in _NUM_CONTA:
                if k != "valor_total" and nova.get(k) is not None:      # só copia o que a releitura leu: None não apaga a base
                    antiga[k] = nova[k]
            antiga["valor_total"] = round(sum(antiga.get(k) or 0 for k in ("valor_agua", "valor_esgoto", "valor_smrsu")), 2)
        for k in _NUM_BORDERO:
            if nb.get(k) is not None or base[i].get(k) is None:       # nunca apaga com None um número que a base leu
                base[i][k] = nb.get(k)
        if lido is not None or res.consumo_rodape_lido.get(i) is None:
            res.consumo_rodape_lido[i] = lido
        relido = f"relido por OCR a {dpi} dpi para fechar com o rodapé"
        base[i]["observacao"] = "; ".join(x for x in (nb.get("observacao"), relido) if x)
    nome = os.path.basename(caminho)
    res.avisos.extend(a.replace(caminho, nome) for a in falhas)       # como em `processar_documento`: sem caminho completo
    return res


def processar_pdf(caminho: str, fornecedor: str | None = None, ocr: bool = True) -> Resultado:
    doc = Documento(caminho, ocr=ocr)
    res = processar_documento(doc, caminho, fornecedor)
    if ocr and doc.usou_ocr and (res.borderos or any(f.get("origem") == "analitica" for f in res.faturas)) \
            and any(x.get("fornecedor") == "SANEAGO" for x in res.borderos + res.faturas):
        res, lang = _leitura_modelo_tabelas(caminho, fornecedor, res)
        if res.borderos and saneago_bordero.colunas_divergentes(res.borderos, res.contas_bordero, res.consumo_rodape_lido):
            res = _releitura_saneago(caminho, fornecedor, res, lang)
    return res


def tipo_do_pdf(caminho: str, ocr: bool = False) -> tuple[str | None, str | None]:
    """(fornecedor, tipo) de um PDF, para classificação rápida (bot/vigia); sem OCR por padrão."""
    doc = Documento(caminho, ocr=ocr)
    base = doc.simples if len(doc.simples.strip()) > 40 else doc.texto
    forn = identificar.fornecedor(base, os.path.basename(caminho), os.path.basename(os.path.dirname(caminho)))
    if not forn:
        return None, None
    return forn, identificar.tipo(base, forn, os.path.basename(caminho))
