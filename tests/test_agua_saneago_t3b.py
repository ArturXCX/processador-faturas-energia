"""Borderô Saneago (T3b + T4): conferência da soma por coluna contra o rodapé e releitura por OCR em resolução maior.

Os PDFs reais não ficam no repositório: tudo aqui é sintético (página de `tests/test_agua.py` e `Documento` falso).

Rodar:  PYTHONPATH=src python -m pytest tests/test_agua_saneago_t3b.py -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from faturas_app.core.agua import extrator, saneago_bordero  # noqa: E402
from faturas_app.core.agua.base import Resultado  # noqa: E402
from test_agua import _GSAN, DocFalso, _pagina_bordero  # noqa: E402

NOME = "FATURAS DE ÁGUA - SANEAGO - ABRIL.2024.pdf"


def _pagina(consumo=None, agua=None):
    """Página sintética do borderô (contas: consumo 112 e 33, rodapé 145; água 1.254,06 + 375,35 = rodapé 1.629,41).
    `consumo` troca o consumo da 1ª conta; `agua` troca o valor de água da 1ª conta."""
    p = _pagina_bordero()
    if consumo is not None:
        assert p.count("112") == 1
        p = p.replace("112", str(consumo))
    if agua is not None:
        assert p.count("1.254,06") == 1
        p = p.replace("1.254,06", agua)
    return p


def _extrair(pagina, ocr=False):
    return saneago_bordero.extrair(DocFalso([pagina], ocr=ocr), NOME)


# ── colunas_divergentes (função pura) ─────────────────────────────────────────
def _b(**kw):
    b = {"id_bordero_agua": "B1", "valor_agua": 100.0, "valor_esgoto": 50.0, "valor_smrsu": 10.0, "consumo_total_m3": 30}
    b.update(kw)
    return b


def _contas(*linhas, id_="B1"):
    """linhas: (consumo, água, esgoto, smrsu)."""
    return [{"id_bordero_agua": id_, "consumo_m3": c, "valor_agua": a, "valor_esgoto": e, "valor_smrsu": s} for c, a, e, s in linhas]


CONTAS_OK = _contas((10, 60.0, 30.0, None), (20, 40.0, 20.0, 10.0))


def test_colunas_divergentes_fecha_nao_acusa_nada():
    assert saneago_bordero.colunas_divergentes([_b()], CONTAS_OK) == {}


def test_colunas_divergentes_agua():
    r = saneago_bordero.colunas_divergentes([_b(valor_agua=101.5)], CONTAS_OK)
    assert list(r) == ["B1"] and len(r["B1"]) == 1
    assert r["B1"][0] == "valor_agua: contas 100,00 x rodapé 101,50"


def test_colunas_divergentes_esgoto_e_smrsu():
    r = saneago_bordero.colunas_divergentes([_b(valor_esgoto=51.0, valor_smrsu=9.0)], CONTAS_OK)
    assert [t.split(":")[0] for t in r["B1"]] == ["valor_esgoto", "valor_smrsu"]


def test_colunas_divergentes_formata_milhar_no_estilo_brasileiro():
    contas = _contas((10, 1551.06, None, None))
    r = saneago_bordero.colunas_divergentes([_b(valor_agua=9546.12, valor_esgoto=None, valor_smrsu=None, consumo_total_m3=10)], contas)
    assert r["B1"] == ["valor_agua: contas 1.551,06 x rodapé 9.546,12"]


def test_colunas_divergentes_tolerancia_de_5_centavos():
    assert saneago_bordero.colunas_divergentes([_b(valor_agua=100.05)], CONTAS_OK) == {}
    assert saneago_bordero.colunas_divergentes([_b(valor_agua=99.95)], CONTAS_OK) == {}
    assert "valor_agua" in saneago_bordero.colunas_divergentes([_b(valor_agua=100.06)], CONTAS_OK)["B1"][0]


def test_colunas_divergentes_sem_rodape_de_esgoto_nao_confere_a_coluna():
    r = saneago_bordero.colunas_divergentes([_b(valor_esgoto=None)], CONTAS_OK)
    assert r == {}


def test_colunas_divergentes_consumo_exato_quando_rodape_lido():
    r = saneago_bordero.colunas_divergentes([_b(consumo_total_m3=31)], CONTAS_OK)
    assert r == {"B1": ["consumo_m3: contas 30 x rodapé 31"]}


def test_colunas_divergentes_consumo_nao_conferido_sem_rodape_lido():
    """O fechamento do borderô preenche `consumo_total_m3` com a soma das contas quando o rodapé não foi lido: a conferência
    precisa saber disso (`consumo_rodape` = o que foi LIDO) e não pode tratar o preenchimento como leitura."""
    b = _b(consumo_total_m3=30)                                    # valor preenchido pelo fallback
    assert saneago_bordero.colunas_divergentes([b], CONTAS_OK, {"B1": None}) == {}
    contas_dif = _contas((10, 60.0, 30.0, None), (25, 40.0, 20.0, 10.0))
    assert saneago_bordero.colunas_divergentes([b], contas_dif, {"B1": None}) == {}      # sem rodapé lido: não confere
    assert saneago_bordero.colunas_divergentes([b], contas_dif, {"B1": 30}) == {"B1": ["consumo_m3: contas 35 x rodapé 30"]}


def test_colunas_divergentes_so_as_contas_do_proprio_bordero():
    contas = CONTAS_OK + _contas((999, 999.0, 999.0, 999.0), id_="OUTRO")
    assert saneago_bordero.colunas_divergentes([_b()], contas) == {}


def test_colunas_divergentes_valores_none_nas_contas_contam_zero():
    contas = _contas((None, 100.0, None, None))
    r = saneago_bordero.colunas_divergentes([_b(valor_esgoto=None, valor_smrsu=None, consumo_total_m3=None)], contas, {"B1": None})
    assert r == {}


# ── T4: observação ────────────────────────────────────────────────────────────
def test_observacao_fecha_nao_menciona_soma_por_coluna():
    for ocr in (False, True):
        res = _extrair(_pagina(), ocr=ocr)
        b, = res.borderos
        assert "soma por coluna" not in b["observacao"]
        assert saneago_bordero.colunas_divergentes(res.borderos, res.contas_bordero, res.consumo_rodape_lido) == {}


def test_observacao_com_consumo_divergente():
    for ocr in (False, True):
        res = _extrair(_pagina(consumo=110), ocr=ocr)
        b, = res.borderos
        assert "soma por coluna difere do rodapé: consumo_m3: contas 143 x rodapé 145" in b["observacao"]
        assert b["consumo_total_m3"] == 145                         # a coluna continua com o valor lido no rodapé


def test_observacao_com_agua_divergente_e_itens_separados_por_barra():
    res = _extrair(_pagina(consumo=110, agua="1.254,16"))
    b, = res.borderos
    obs = b["observacao"]
    assert "soma por coluna difere do rodapé: valor_agua: contas 1.629,51 x rodapé 1.629,41 | consumo_m3: contas 143 x rodapé 145" in obs


def test_rodape_sem_consumo_lido_nao_confere_consumo_e_nao_muda_a_coluna():
    pag = _pagina()
    linhas = pag.splitlines()
    i = next(k for k, ln in enumerate(linhas) if "1.629,41" in ln and "FATURA" in ln)
    linhas[i] = linhas[i].replace(" 145 ", "     ", 1)             # rodapé sem o consumo
    res = _extrair("\n".join(linhas))
    b, = res.borderos
    assert res.consumo_rodape_lido[b["id_bordero_agua"]] is None
    assert b["consumo_total_m3"] == 145                             # fallback: soma das contas, como antes
    assert "consumo_m3" not in b["observacao"] and "soma por coluna" not in b["observacao"]


# ── T3b: releitura por OCR ────────────────────────────────────────────────────
class _DocOcr:
    """Documento falso: `paginas_por_dpi[dpi]` é a página lida naquela resolução; registra as chamadas."""
    chamadas: list = []
    paginas_por_dpi: dict = {}
    ocr_por_dpi: dict = {}

    def __init__(self, caminho, ocr=True, dpi=300):
        type(self).chamadas.append((ocr, dpi))
        p = type(self).paginas_por_dpi[dpi]
        self.paginas = list(p) if isinstance(p, list) else [p]
        self.usou_ocr = type(self).ocr_por_dpi.get(dpi, True) and ocr
        self.vazio = False

    @property
    def texto(self):
        return "\f".join(self.paginas)

    @property
    def simples(self):
        return "\n".join(" ".join(ln.split()) for p in self.paginas for ln in p.splitlines())


def _preparar(monkeypatch, por_dpi, ocr_por_dpi=None):
    _DocOcr.chamadas = []
    _DocOcr.paginas_por_dpi = por_dpi
    _DocOcr.ocr_por_dpi = ocr_por_dpi or {}
    monkeypatch.setattr(extrator, "Documento", _DocOcr)
    monkeypatch.setattr(extrator.ocr_motor, "idioma_tabelas", lambda: None)     # estes testes são da releitura com o modelo padrão


def _dpis():
    return [d for _o, d in _DocOcr.chamadas]


def test_releitura_escolhe_400_quando_fecha(monkeypatch):
    _preparar(monkeypatch, {300: _pagina(consumo=110), 400: _pagina()})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert _dpis() == [300, 400]                                    # 500 não é pedido: já fechou
    b, = res.borderos
    assert "relido por OCR a 400 dpi para fechar com o rodapé" in b["observacao"]
    assert "soma por coluna" not in b["observacao"]
    assert sorted(c["consumo_m3"] for c in res.contas_bordero) == [33, 112]


def test_primeira_leitura_sem_dpi_explicito(monkeypatch):
    """A 1ª leitura continua sendo `Documento(caminho, ocr=ocr)` (dpi padrão do Documento = 300)."""
    seen = []

    class _D(_DocOcr):
        def __init__(self, caminho, **kw):
            seen.append(kw)
            super().__init__(caminho, **kw)

    _preparar(monkeypatch, {300: _pagina(consumo=110), 400: _pagina()})
    monkeypatch.setattr(extrator, "Documento", _D)
    extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert seen[0] == {"ocr": True} and seen[1] == {"ocr": True, "dpi": 400}


def test_releitura_pior_mantem_300_e_tenta_500(monkeypatch):
    pior = _pagina(consumo=100, agua="1.254,16")                     # 2 colunas divergentes (300 tem 1)
    _preparar(monkeypatch, {300: _pagina(consumo=110), 400: pior, 500: _pagina()})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert _dpis() == [300, 400, 500]
    b, = res.borderos
    assert "relido por OCR a 500 dpi" in b["observacao"] and "relido por OCR a 400 dpi" not in b["observacao"]
    assert "soma por coluna" not in b["observacao"]


def test_releituras_todas_piores_mantem_300_sem_frase_de_releitura(monkeypatch):
    pior = _pagina(consumo=100, agua="1.254,16")
    _preparar(monkeypatch, {300: _pagina(consumo=110), 400: pior, 500: pior})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert _dpis() == [300, 400, 500]
    b, = res.borderos
    assert "relido por OCR" not in b["observacao"]
    assert "consumo_m3: contas 143 x rodapé 145" in b["observacao"]  # continua o resultado de 300


def test_empate_fica_no_dpi_mais_baixo(monkeypatch):
    # 300: contas 143 x 145 (diferença 2); 400: contas 144 x 145 (diferença 1, mesma contagem de colunas) → 400 é melhor;
    # 500 volta a 143 (pior que 400): fica em 400
    _preparar(monkeypatch, {300: _pagina(consumo=110), 400: _pagina(consumo=111), 500: _pagina(consumo=110)})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    b, = res.borderos
    assert "relido por OCR a 400 dpi" in b["observacao"] and "contas 144 x rodapé 145" in b["observacao"]
    # empate exato entre 300, 400 e 500: nenhuma releitura é escolhida
    _preparar(monkeypatch, {300: _pagina(consumo=110), 400: _pagina(consumo=110), 500: _pagina(consumo=110)})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert "relido por OCR" not in res.borderos[0]["observacao"]
    # empate entre 400 e 500 (ambos melhores que 300): fica 400
    _preparar(monkeypatch, {300: _pagina(consumo=100), 400: _pagina(consumo=111), 500: _pagina(consumo=111)})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert _dpis() == [300, 400, 500]
    assert "relido por OCR a 400 dpi" in res.borderos[0]["observacao"]


def test_ocr_false_nao_rele(monkeypatch):
    _preparar(monkeypatch, {300: _pagina(consumo=110), 400: _pagina()}, ocr_por_dpi={300: True})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO", ocr=False)
    assert _dpis() == [300]
    assert "relido por OCR" not in res.borderos[0]["observacao"]


def test_documento_sem_ocr_nao_rele(monkeypatch):
    _preparar(monkeypatch, {300: _pagina(consumo=110), 400: _pagina()}, ocr_por_dpi={300: False, 400: False})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert _dpis() == [300]
    assert "relido por OCR" not in res.borderos[0]["observacao"]


def test_tudo_fecha_a_300_nao_rele(monkeypatch):
    _preparar(monkeypatch, {300: _pagina(), 400: _pagina(consumo=110)})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert _dpis() == [300]
    assert "relido por OCR" not in res.borderos[0]["observacao"] and "soma por coluna" not in res.borderos[0]["observacao"]


def test_sem_bordero_nao_rele(monkeypatch):
    vazia = "   SANEAMENTO DE GOIÁS S.A.\n   NOME DO ÓRGÃO AGRUPADOR:\n"
    _preparar(monkeypatch, {300: vazia, 400: _pagina()})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert _dpis() == [300] and not res.borderos


def test_releitura_que_falha_mantem_o_resultado_de_300(monkeypatch):
    _preparar(monkeypatch, {300: _pagina(consumo=110)})                 # 400/500 levantam KeyError
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert _dpis() == [300, 400, 500]
    assert "consumo_m3: contas 143 x rodapé 145" in res.borderos[0]["observacao"]


def test_outro_fornecedor_com_ocr_nao_rele(monkeypatch):
    """Fatura GSAN (Buriti Alegre) lida por OCR: não é borderô Saneago, logo uma única chamada ao Documento (300 dpi)."""
    _preparar(monkeypatch, {300: _GSAN, 400: _GSAN})
    res = extrator.processar_pdf("FATURA Nº 110495 - BURITI ALEGRE AMBIENTAL - JANEIRO.2024.pdf", fornecedor="BURITI_ALEGRE_AMBIENTAL")
    assert _dpis() == [300]
    assert len(res.faturas) == 1 and not res.borderos


# ── releitura: mescla NUMÉRICA por borderô sobre a leitura de 300 dpi (identidade e texto nunca vêm da releitura) ──
NOME_1, NOME_1_SEM_CEDILHA = "TRIBUNAL DE JUSTIÇA DO ESTADO DE GO", "TRIBUNAL DE JUSTICA DO ESTADO DE GO"


def _sem_dv(pagina):
    """Simula o OCR que perde o DV da 1ª conta: '1627885 2' → '1627885' (a conta fica com 7 dígitos: prefixo da completa)."""
    assert pagina.count("1627885 2") == 1
    return pagina.replace("1627885 2", "1627885  ")


def _pagina_b(**kw):
    """Mesma página com outro número de fatura: um 2º borderô no mesmo PDF."""
    p = _pagina(**kw)
    assert "3000483958" in p
    return p.replace("3000483958", "3000483959")


def _bord(res, num):
    return next(b for b in res.borderos if b["id_bordero_agua"] == f"SANEAGO_{num}")


def _contas_do(res, num):
    return [c for c in res.contas_bordero if c["id_bordero_agua"] == f"SANEAGO_{num}"]


def test_resultado_declara_consumo_rodape_lido_e_estender_carrega():
    a, b = Resultado(), Resultado()
    assert a.consumo_rodape_lido == {} and a.consumo_rodape_lido is not b.consumo_rodape_lido
    a.consumo_rodape_lido["A"] = 10
    b.consumo_rodape_lido["B"] = None
    a.estender(b)
    assert a.consumo_rodape_lido == {"A": 10, "B": None}


def test_releitura_com_conta_truncada_mantem_conta_e_texto_da_base_e_toma_o_consumo(monkeypatch):
    p400 = _sem_dv(_pagina()).replace(NOME_1, NOME_1_SEM_CEDILHA)
    _preparar(monkeypatch, {300: _pagina(consumo=110), 400: p400})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert _dpis() == [300, 400]
    c1, c2 = res.contas_bordero
    assert (c1["conta"], c1["conta_formatada"], c1["nome_cliente"], c1["ordem"]) == ("16278852", "1627885 2", NOME_1, 1)
    assert c1["consumo_m3"] == 112 and c2["consumo_m3"] == 33                       # números da releitura
    assert "relido por OCR a 400 dpi para fechar com o rodapé" in res.borderos[0]["observacao"]
    assert saneago_bordero.colunas_divergentes(res.borderos, res.contas_bordero, res.consumo_rodape_lido) == {}


def test_releitura_com_numero_de_contas_diferente_mantem_a_base_do_bordero(monkeypatch):
    p400 = "\n".join(ln for ln in _pagina().splitlines() if "1584740 3" not in ln)       # 400 dpi perdeu uma conta
    _preparar(monkeypatch, {300: _pagina(consumo=110), 400: p400, 500: p400})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert _dpis() == [300, 400, 500]
    assert [c["consumo_m3"] for c in res.contas_bordero] == [110, 33]
    assert "relido por OCR" not in res.borderos[0]["observacao"]
    assert "consumo_m3: contas 143 x rodapé 145" in res.borderos[0]["observacao"]


def test_releitura_com_conta_incompativel_mantem_a_base_do_bordero(monkeypatch):
    p400 = _pagina().replace("1627885 2", "1627886 2")                  # dígito trocado, sem prefixo comum completo
    _preparar(monkeypatch, {300: _pagina(consumo=110), 400: p400, 500: p400})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert _dpis() == [300, 400, 500]
    assert [(c["conta"], c["consumo_m3"]) for c in res.contas_bordero] == [("16278852", 110), ("15847403", 33)]
    assert "relido por OCR" not in res.borderos[0]["observacao"]


def test_releitura_com_prefixo_comum_curto_demais_nao_alinha(monkeypatch):
    # 1ª conta da releitura: "162" (só 3 dígitos em comum): não é um alinhamento confiável
    p400 = _pagina().replace("1627885 2", "162       ")
    _preparar(monkeypatch, {300: _pagina(consumo=110), 400: p400, 500: p400})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert [c["consumo_m3"] for c in res.contas_bordero] == [110, 33]
    assert "relido por OCR" not in res.borderos[0]["observacao"]


def test_dois_borderos_so_o_que_melhora_e_reescrito_e_anotado(monkeypatch):
    # A e B divergem a 300 dpi; a 400 dpi só A fecha; a 500 dpi nada melhora. B continua com a leitura de 300.
    _preparar(monkeypatch, {300: [_pagina(consumo=110), _pagina_b(consumo=110)],
                            400: [_pagina(), _pagina_b(consumo=110)],
                            500: [_pagina(consumo=110), _pagina_b(consumo=110)]})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert _dpis() == [300, 400, 500]                                 # B ainda divergia: a segunda releitura acontece
    a, b = _bord(res, "3000483958"), _bord(res, "3000483959")
    assert [c["consumo_m3"] for c in _contas_do(res, "3000483958")] == [112, 33]
    assert [c["consumo_m3"] for c in _contas_do(res, "3000483959")] == [110, 33]
    assert "relido por OCR a 400 dpi para fechar com o rodapé" in a["observacao"] and "soma por coluna" not in a["observacao"]
    assert "relido por OCR" not in b["observacao"] and "consumo_m3: contas 143 x rodapé 145" in b["observacao"]


def test_bordero_que_ja_fecha_nao_e_tocado_pela_releitura(monkeypatch):
    _preparar(monkeypatch, {300: [_pagina(), _pagina_b(consumo=110)],
                            400: [_pagina(consumo=100), _pagina_b()]})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert _dpis() == [300, 400]
    a, b = _bord(res, "3000483958"), _bord(res, "3000483959")
    assert [c["consumo_m3"] for c in _contas_do(res, "3000483958")] == [112, 33] and "relido por OCR" not in a["observacao"]
    assert [c["consumo_m3"] for c in _contas_do(res, "3000483959")] == [112, 33]
    assert "relido por OCR a 400 dpi" in b["observacao"]


def test_numeros_do_rodape_vem_da_releitura(monkeypatch):
    pag300 = _pagina()
    assert pag300.count("1.629,41") == 1 and pag300.count("2.680,25") == 1
    pag300 = pag300.replace("1.629,41", "1.629,47").replace("2.680,25", "2.680,24")        # rodapé mal lido a 300 dpi
    base = _extrair(pag300)
    assert base.borderos[0]["valor_agua"] == 1629.47 and base.borderos[0]["base_calculo"] == 2680.24
    _preparar(monkeypatch, {300: pag300, 400: _pagina()})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert _dpis() == [300, 400]
    b, = res.borderos
    assert b["valor_agua"] == 1629.41 and b["base_calculo"] == 2680.25 and b["bate_total"] == "SIM"
    assert b["consumo_total_m3"] == 145 and b["quantidade_contas"] == 2 and b["quantidade_contas_extraidas"] == 2
    assert "relido por OCR a 400 dpi" in b["observacao"] and "soma por coluna" not in b["observacao"]
    assert b["id_bordero_agua"] == "SANEAGO_3000483958" and b["numero_fatura"] == "3000483958"


# ── releitura: rodapé não lido na releitura nunca vale como melhora (elegibilidade) ────────────────────────────
def _sem_linha_do_rodape(pagina):
    """Tira a linha do rodapé com os totais de água/esgoto/SMRSU/consumo (o OCR não a leu)."""
    linhas = pagina.splitlines()
    alvo = [ln for ln in linhas if "1.629,41" in ln and "FATURA" in ln]
    assert len(alvo) == 1
    return "\n".join(ln for ln in linhas if ln is not alvo[0])


def _sem_consumo_no_rodape(pagina):
    linhas = pagina.splitlines()
    i = next(k for k, ln in enumerate(linhas) if "1.629,41" in ln and "FATURA" in ln)
    assert " 145 " in linhas[i]
    linhas[i] = linhas[i].replace(" 145 ", "     ", 1)
    return "\n".join(linhas)


def test_releitura_sem_rodape_nao_vale_como_melhora_e_nao_apaga_o_rodape_da_base(monkeypatch):
    p400 = _sem_linha_do_rodape(_pagina())                           # contas certas, mas o rodapé não foi lido
    _preparar(monkeypatch, {300: _pagina(consumo=110), 400: p400, 500: p400})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert _dpis() == [300, 400, 500]
    b, = res.borderos
    assert (b["valor_agua"], b["valor_esgoto"], b["valor_smrsu"], b["consumo_total_m3"]) == (1629.41, 1050.84, 45.0, 145)
    assert b["bate_total"] == "SIM" and res.consumo_rodape_lido[b["id_bordero_agua"]] == 145
    assert "relido por OCR" not in b["observacao"] and "consumo_m3: contas 143 x rodapé 145" in b["observacao"]
    assert [c["consumo_m3"] for c in res.contas_bordero] == [110, 33]


def test_releitura_sem_consumo_no_rodape_e_contas_erradas_mantem_a_base(monkeypatch):
    p400 = _sem_consumo_no_rodape(_pagina(consumo=50))               # consumo do rodapé não lido; contas piores
    _preparar(monkeypatch, {300: _pagina(consumo=110), 400: p400, 500: p400})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    b, = res.borderos
    assert b["consumo_total_m3"] == 145 and res.consumo_rodape_lido[b["id_bordero_agua"]] == 145
    assert [c["consumo_m3"] for c in res.contas_bordero] == [110, 33]
    assert "relido por OCR" not in b["observacao"] and "consumo_m3: contas 143 x rodapé 145" in b["observacao"]
    assert saneago_bordero.colunas_divergentes(res.borderos, res.contas_bordero, res.consumo_rodape_lido)


def test_releitura_que_le_o_rodape_ate_entao_nao_lido_continua_elegivel(monkeypatch):
    p300 = _sem_consumo_no_rodape(_pagina(agua="1.254,16"))          # base: sem consumo no rodapé, água das contas errada
    base = _extrair(p300)
    assert base.consumo_rodape_lido[base.borderos[0]["id_bordero_agua"]] is None
    assert "valor_agua" in base.borderos[0]["observacao"]
    _preparar(monkeypatch, {300: p300, 400: _pagina()})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert _dpis() == [300, 400]
    b, = res.borderos
    assert res.consumo_rodape_lido[b["id_bordero_agua"]] == 145 and b["consumo_total_m3"] == 145
    assert [c["valor_agua"] for c in res.contas_bordero] == [1254.06, 375.35]
    assert "relido por OCR a 400 dpi" in b["observacao"] and "soma por coluna" not in b["observacao"]


def test_releitura_que_levanta_deixa_aviso_e_mantem_a_base(monkeypatch):
    _preparar(monkeypatch, {300: _pagina(consumo=110)})              # 400/500: KeyError
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert [c["consumo_m3"] for c in res.contas_bordero] == [110, 33]
    assert any("releitura a 400 dpi falhou: KeyError" in a for a in res.avisos)
    assert any("releitura a 500 dpi falhou: KeyError" in a for a in res.avisos)
    assert "relido por OCR" not in res.borderos[0]["observacao"]


# ── releitura: número da base nunca vira None; aviso de falha sem caminho completo ─────────────────────────────
def _sem_consumo_da_conta_2(pagina):
    linhas = pagina.splitlines()
    i = next(k for k, ln in enumerate(linhas) if "1584740 3" in ln)
    assert linhas[i].count(" 33 ") == 1
    assert linhas[i].count(", 256") == 1                              # senão o nº do logradouro viraria o "consumo"
    linhas[i] = linhas[i].replace(" 33 ", "    ", 1).replace(", 256", "     ", 1)
    return "\n".join(linhas)


def test_releitura_que_da_none_mantem_o_numero_da_base_e_toma_o_resto(monkeypatch):
    p400 = _sem_consumo_da_conta_2(_pagina())                       # releitura: certa, mas sem o consumo da conta 2
    assert _extrair(p400).contas_bordero[1]["consumo_m3"] is None
    _preparar(monkeypatch, {300: _pagina(consumo=110, agua="1.254,16"), 400: p400, 500: p400})   # base: 2 colunas divergentes
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    assert _dpis() == [300, 400, 500]
    c1, c2 = res.contas_bordero
    assert (c1["consumo_m3"], c1["valor_agua"]) == (112, 1254.06)                   # números da releitura
    assert (c2["consumo_m3"], c2["valor_agua"], c2["valor_smrsu"]) == (33, 375.35, 45.0)   # consumo None → fica o da base
    assert (c1["valor_total"], c2["valor_total"]) == (2304.9, 420.35)               # recalculado: água + esgoto + SMRSU
    assert "relido por OCR a 400 dpi" in res.borderos[0]["observacao"]


def test_releitura_toma_valor_para_campo_que_a_base_nao_leu(monkeypatch):
    p300 = _sem_consumo_da_conta_2(_pagina(agua="1.254,16"))         # base: conta 2 sem consumo
    assert _extrair(p300).contas_bordero[1]["consumo_m3"] is None
    _preparar(monkeypatch, {300: p300, 400: _pagina()})
    res = extrator.processar_pdf(NOME, fornecedor="SANEAGO")
    c1, c2 = res.contas_bordero
    assert c2["consumo_m3"] == 33 and c1["valor_agua"] == 1254.06 and c1["valor_total"] == 2304.9
    assert "relido por OCR a 400 dpi" in res.borderos[0]["observacao"]


def test_aviso_de_releitura_que_falha_nao_traz_o_caminho_completo(monkeypatch):
    caminho = "C:/pasta secreta/sub/" + NOME

    class _Quebra(_DocOcr):
        def __init__(self, cam, ocr=True, dpi=300):
            if dpi != 300:
                raise OSError(f"cannot open {cam}")
            super().__init__(cam, ocr=ocr, dpi=dpi)

    _preparar(monkeypatch, {300: _pagina(consumo=110)})
    monkeypatch.setattr(extrator, "Documento", _Quebra)
    res = extrator.processar_pdf(caminho, fornecedor="SANEAGO")
    falhas = [a for a in res.avisos if "releitura a" in a]
    assert len(falhas) == 2
    assert all("pasta secreta" not in a and NOME in a and "OSError" in a for a in falhas)
