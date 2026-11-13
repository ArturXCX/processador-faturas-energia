"""T3 — resíduos do borderô Saneago: cabeçalho (competência, emissão, nome do agrupador, reserva pelo nome do arquivo) e
linhas de conta com ruído de OCR de SÍMBOLO no lugar de números.

Os PDFs reais não ficam no repositório: as páginas são texto sintético (usa números de conta já presentes nos testes do projeto e trechos de logradouro, sem dados pessoais) que mantém
os tokens de ruído exatos lidos nos PDFs reais.

Rodar:  PYTHONPATH=src python -m pytest tests/test_agua_saneago_t3.py -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core.agua import extrator, saneago_bordero  # noqa: E402


class _DocFalso:
    def __init__(self, paginas, ocr=False):
        self.paginas = list(paginas)
        self.usou_ocr = ocr
        self.vazio = False
        self.simples = "\n".join(self.paginas)
        self.texto = self.simples


def _pos(*partes):
    """(coluna, texto) alinha à esquerda; (coluna, texto, 'd') alinha o FIM do texto na coluna."""
    buf = ""
    for p in partes:
        col, txt = p[0], p[1]
        if len(p) > 2 and p[2] == "d":
            col = col - len(txt)
        buf += " " * (col - len(buf)) if col > len(buf) else " "
        buf += txt
    return buf


def _cols_antigo():
    cab = _pos((3, "CONTA - DV"), (16, "NOME CLIENTE"), (53, "LOGRADOURO"), (103, "ÁGUA"), (110, "VALOR R$"), (126, "ESGOTO"), (133, "VALOR R$"))
    ant = _pos((100, "CONSUMO (M³)"), (123, "CONSUMO (M³)"))
    return cab, ant, saneago_bordero._colunas(cab, ant)


def _cauda(ln, ocr=True):
    _cab, _ant, cols = _cols_antigo()
    valores, consumos, _ini = saneago_bordero._numeros_da_cauda(ln, cols, ocr)
    return valores, consumos


# ── B. ruído com SÍMBOLO / não ASCII (1–3 caracteres) no lugar de números ─────
def test_cauda_real_1_simbolo_antes_de_cada_valor():
    # '02 CONJUNTO HABIT. PAINEIRAS TÁ! 665,95 TÁ! 665,95'
    ln = _pos((3, "1627885 2"), (15, "CONJUNTO HABIT. PAINEIRAS"), (53, "02 CONJUNTO HABIT. PAINEIRAS"),
              (96, "TÁ!"), (117, "665,95", "d"), (121, "TÁ!"), (140, "665,95", "d"))
    assert _cauda(ln) == ({"agua": 665.95, "esgoto": 665.95}, {})


def test_cauda_real_2_simbolo_entre_consumos_sem_valor_de_agua():
    # 'LT. SETOR CENTRAL ANAPOLIS 6 AE) 6 57,12'
    ln = _pos((3, "2656388 1"), (15, "ESCOLA ESTADUAL"), (53, "LT. SETOR CENTRAL ANAPOLIS"),
              (106, "6", "d"), (108, "AE)"), (131, "6", "d"), (140, "57,12", "d"))
    valores, consumos = _cauda(ln)
    assert consumos == {"consumo": 6, "consumo_esgoto": 6} and valores == {"esgoto": 57.12}


def test_cauda_real_3_simbolo_antes_do_valor_de_esgoto():
    # 'ENCONTRO DOS RIOS ARUANA 20 182,80 r\xe1! 710,14'
    ln = _pos((3, "16369742 1"), (15, "FORUM"), (53, "ENCONTRO DOS RIOS ARUANA"),
              (106, "20", "d"), (117, "182,80", "d"), (121, "r\xe1!"), (140, "710,14", "d"))
    valores, consumos = _cauda(ln)
    assert valores == {"agua": 182.80, "esgoto": 710.14} and consumos == {"consumo": 20}


def test_cauda_real_4_simbolo_antes_de_cada_valor():
    # '4 PARK LOZANDES GOIANIA rá! 729,46 rá! 584,89'
    ln = _pos((3, "17095549 1"), (15, "FORUM"), (53, "4 PARK LOZANDES GOIANIA"),
              (96, "r\xe1!"), (117, "729,46", "d"), (121, "r\xe1!"), (140, "584,89", "d"))
    assert _cauda(ln) == ({"agua": 729.46, "esgoto": 584.89}, {})


def test_cauda_simbolo_isento_da_regra_dos_dois_espacos():
    ln = _pos((3, "1627885 2"), (53, "RUA CARMOS GOIAS"), (111, "109,06"), (118, "TÁ!"), (122, "109,06"))
    assert "109,06 TÁ! 109,06" in ln
    valores, consumos = _cauda(ln)
    assert len(valores) == 2 and sorted(valores.values()) == [109.06, 109.06] and consumos == {}


def test_cauda_sem_ocr_simbolo_continua_encerrando_a_cauda():
    ln = _pos((3, "1627885 2"), (15, "TRIBUNAL"), (53, "RUA CARMOS GOIAS"), (96, "TÁ!"), (117, "109,06", "d"),
              (121, "TÁ!"), (140, "109,06", "d"))
    assert _cauda(ln, ocr=False) == ({"esgoto": 109.06}, {})


def test_cauda_sn_nao_fabrica_consumo():
    ln = _pos((3, "1627885 2"), (15, "TRIBUNAL"), (53, "RUA 5 S/N"), (117, "109,06", "d"), (140, "109,06", "d"))
    assert _cauda(ln) == ({"agua": 109.06, "esgoto": 109.06}, {})
    ln2 = _pos((3, "1627885 2"), (15, "TRIBUNAL"), (53, "RUA 5 S/N 109,06 109,06"))
    assert _cauda(ln2)[1] == {}


def test_cauda_palavras_curtas_sem_simbolo_nao_viram_ruido():
    for tok in ("ABC", "LT", "QD.", "S/N", "B-2"):
        ln = _pos((3, "1627885 2"), (15, "TRIBUNAL"), (53, f"RUA X 12 {tok} 109,06 109,06"))
        valores, consumos = _cauda(ln)
        assert consumos == {} and len(valores) == 2, tok
    # token sem símbolo ENTRE dois números da cauda continua encerrando a cauda
    for tok in ("ABC", "S/N", "QD."):
        ln = _pos((3, "1627885 2"), (53, "RUA CARMOS GOIAS"), (117, "109,06", "d"), (123, tok), (140, "109,06", "d"))
        assert _cauda(ln) == ({"esgoto": 109.06}, {}), tok


def test_cauda_ordinal_e_simbolos_de_endereco_nao_viram_ruido():
    """`RUA 5 Nº 12   109,06   109,06`: o "Nº" (e afins) entre dois números do logradouro NÃO é ruído; senão o 5 viraria
    consumo_esgoto e o logradouro seria truncado. Tudo igual ao comportamento anterior à T3."""
    _cab, _ant, cols = _cols_antigo()
    for tok in ("Nº", "Nº.", "N°", "1º", "2ª", "(2)", "Nº5"):
        ln = _pos((3, "1627885 2"), (15, "TRIBUNAL"), (53, f"RUA 5 {tok} 12"), (117, "109,06", "d"), (140, "109,06", "d"))
        valores, consumos, ini = saneago_bordero._numeros_da_cauda(ln, cols, True)
        assert consumos == {"consumo": 12} and valores == {"agua": 109.06, "esgoto": 109.06}, tok
        assert ln[ini:].startswith("12") and ln[:ini].rstrip().endswith(tok), tok


def test_cauda_simbolos_reais_de_ocr_continuam_sendo_ruido():
    _cab, _ant, cols = _cols_antigo()
    for tok in ("TÁ!", "rá!", "AE)", "|", "!", "[", "]"):
        ln = _pos((3, "1627885 2"), (15, "TRIBUNAL"), (53, "RUA CARMOS GOIAS"), (96, "6"), (99, tok), (117, "109,06", "d"),
                  (121, tok), (140, "109,06", "d"))
        valores, consumos, ini = saneago_bordero._numeros_da_cauda(ln, cols, True)
        assert valores == {"agua": 109.06, "esgoto": 109.06}, tok


def test_cauda_simbolo_sem_numero_a_esquerda_ou_a_direita_encerra_a_cauda():
    ln = _pos((3, "1627885 2"), (53, "RUA CARMOS GOIAS"), (96, "TÁ!"), (140, "109,06", "d"))
    assert _cauda(ln) == ({"esgoto": 109.06}, {})
    ln2 = _pos((3, "1627885 2"), (53, "RUA CARMOS GOIAS"), (140, "109,06", "d"), (142, "TÁ!"))
    assert saneago_bordero._numeros_da_cauda(ln2, _cols_antigo()[2], True)[:2] == ({}, {})


# ── páginas sintéticas de borderô (OCR) ───────────────────────────────────────
def _pagina(cabecalho, contas=None):
    contas = contas if contas is not None else [
        _pos((3, "1627885 2"), (15, "TRIBUNAL DE JUSTICA"), (53, "RUA CARMOS GOIAS"), (117, "109,06", "d"), (140, "109,06", "d"))]
    L = list(cabecalho) + [
        _pos((100, "CONSUMO (M³)"), (123, "CONSUMO (M³)")),
        _pos((3, "CONTA - DV"), (16, "NOME CLIENTE"), (53, "LOGRADOURO"), (103, "ÁGUA"), (110, "VALOR R$"), (126, "ESGOTO"), (133, "VALOR R$")),
    ] + contas + [
        _pos((3, "CONSUMO FATURADO TOTAL / VALOR TOTAL DA FATURA"), (117, "109,06", "d"), (140, "109,06", "d")),
        "   RETENÇÕES     DE IMPOSTOS",
        "   QUANTIDADE    DE CONTAS   AGRUPADAS:   1",
    ]
    return "\n".join(L)


def _cab(fatura="3000112233", mes="   Nº  FATURA:    3000112233            MÊS/ANO     REF:   04/2024",
         emissao="   DATA    DE  EMISSÃO:     14/05/2024          VENCIMENTO:       30/05/2024",
         nome="   TRIBUNAL DE JUSTICA ESTADO DE GOIÁS                                                    2130  2130"):
    return ["   SANEAMENTO        DE  GOIÁS S.A.", mes, emissao, "   NOME DO ÓRGÃO AGRUPADOR:", nome]


def _extrair(cab, ocr=True):
    return saneago_bordero.extrair(_DocFalso([_pagina(cab)], ocr=ocr), "x.pdf")


# ── A1. competência ───────────────────────────────────────────────────────────
def test_competencia_normal_continua():
    b, = _extrair(_cab()).borderos
    assert b["competencia"] == "2024-04"


def test_competencia_com_e_agudo_no_mes():
    b, = _extrair(_cab(mes="   Nº  FATURA:    3000112233            MÉS/ANO     REF:  08/2021")).borderos
    assert b["competencia"] == "2021-08"


def test_competencia_com_espaco_antes_da_barra():
    b, = _extrair(_cab(mes="   Nº  FATURA:    3000112233    MÊS /ANO   REF.   08/2021")).borderos
    assert b["competencia"] == "2021-08"


# ── A2. data de emissão quebrada em duas linhas ───────────────────────────────
def test_emissao_na_mesma_linha_continua():
    b, = _extrair(_cab()).borderos
    assert b["data_emissao"] == "2024-05-14" and b["data_vencimento"] == "2024-05-30"


def test_emissao_quebrada_em_duas_linhas():
    cab = _cab(emissao="   SETOR OESTE 74130011 GOIANIA GO EMISSÃO:")
    cab.insert(3, "   - DATA DE 10/11/2023")
    cab.insert(4, "   VENCIMENTO:   30/11/2023")
    b, = _extrair(cab).borderos
    assert b["data_emissao"] == "2023-11-10" and b["data_vencimento"] == "2023-11-30"


def test_emissao_sem_data_nao_pega_o_vencimento_da_linha_seguinte():
    cab = _cab(emissao="   SETOR OESTE 74130011 GOIANIA GO EMISSÃO:")
    cab.insert(3, "   VENCIMENTO:   30/11/2023")
    b, = _extrair(cab).borderos
    assert b["data_emissao"] is None and b["data_vencimento"] == "2023-11-30"


def test_emissao_ja_lida_nao_e_sobrescrita():
    cab = _cab()
    cab.insert(3, "   OUTRO EMISSÃO:")
    cab.insert(4, "   - DATA DE 10/11/2023")
    b, = _extrair(cab).borderos
    assert b["data_emissao"] == "2024-05-14"


# ── A3. nome do órgão agrupador ───────────────────────────────────────────────
_CAB_TABELA = ["   CONSUMO (M³)      CONSUMO (M³)",
               "   CONTA - DV NOME CLIENTE LOGRADOURO ÁGUA VALOR R$ ESGOTO VALOR R$"]


def _cab_sem_nome(fatura, cod="2130", mes="04/2024"):
    return ["   SANEAMENTO        DE  GOIÁS S.A.",
            f"   Nº  FATURA:    {fatura}            MÊS/ANO     REF:   {mes}",
            f"   CÓDIGO ÓRGÃO PAGADOR  2999   CÓDIGO ÓRGÃO AGRUPADOR  {cod}",
            "   NOME DO ÓRGÃO AGRUPADOR:"] + _CAB_TABELA


def test_nome_agrupador_nao_pega_cabecalho_da_tabela():
    b, = _extrair(_cab_sem_nome("3000112233")).borderos
    assert b["nome_agrupador"] is None
    assert "CONSUMO" not in str(b["nome_agrupador"])


def test_nome_agrupador_normal_continua():
    b, = _extrair(_cab()).borderos
    assert b["nome_agrupador"] == "TRIBUNAL DE JUSTICA ESTADO DE GOIÁS" and b["cod_agrupador"] == "2130"


def test_segundo_bordero_herda_o_nome_do_mesmo_agrupador():
    cab1 = _cab()
    cab1[1] = "   Nº  FATURA:    3000000001            MÊS/ANO     REF:   04/2024"
    cab1.insert(3, "   CÓDIGO ÓRGÃO PAGADOR  2999   CÓDIGO ÓRGÃO AGRUPADOR  2130")
    doc = _DocFalso([_pagina(cab1), _pagina(_cab_sem_nome("3000000002", cod="2130"))], ocr=True)
    b1, b2 = saneago_bordero.extrair(doc, "x.pdf").borderos
    assert b1["nome_agrupador"] == "TRIBUNAL DE JUSTICA ESTADO DE GOIÁS"
    assert b2["cod_agrupador"] == "2130" and b2["nome_agrupador"] == b1["nome_agrupador"]


def test_codigo_diferente_nao_herda_o_nome():
    cab1 = _cab()
    cab1[1] = "   Nº  FATURA:    3000000001            MÊS/ANO     REF:   04/2024"
    cab1.insert(3, "   CÓDIGO ÓRGÃO PAGADOR  2999   CÓDIGO ÓRGÃO AGRUPADOR  2130")
    doc = _DocFalso([_pagina(cab1), _pagina(_cab_sem_nome("3000000002", cod="7777"))], ocr=True)
    b1, b2 = saneago_bordero.extrair(doc, "x.pdf").borderos
    assert b1["nome_agrupador"] and b2["nome_agrupador"] is None


def test_nome_agrupador_com_palavra_parecida_com_cabecalho_e_mantido():
    """O filtro do cabeçalho da tabela usa limite de palavra: "CONTADORIA GERAL" é nome; "CONSUMO (M³)" não é."""
    cab = ["   SANEAMENTO        DE  GOIÁS S.A.", "   Nº  FATURA:    3000112233            MÊS/ANO     REF:   04/2024",
           "   NOME DO ÓRGÃO AGRUPADOR:", "   CONTADORIA GERAL DO ESTADO"]
    b, = _extrair(cab).borderos
    assert b["nome_agrupador"] == "CONTADORIA GERAL DO ESTADO"
    cab2 = cab[:3] + ["   CONSUMO (M³)      CONSUMO (M³)"]
    b2, = _extrair(cab2).borderos
    assert b2["nome_agrupador"] is None


def test_sobra_de_ocr_nao_vale_como_nome_do_agrupador():
    """Linhas reais do OCR na VM: "-  2130 2130" e "R$ — VALORRS  2130 2130". Os códigos valem; o nome fica para herdar."""
    for sobra in ("   -                     2130  2130", "   R$ — VALORRS          2130  2130"):
        cab = ["   SANEAMENTO        DE  GOIÁS S.A.", "   Nº  FATURA:    3000112233            MÊS/ANO     REF:   04/2024",
               "   NOME DO ÓRGÃO AGRUPADOR:", sobra]
        b, = _extrair(cab).borderos
        assert b["nome_agrupador"] is None
    b, = _extrair(cab[:3] + ["   -"]).borderos
    assert b["nome_agrupador"] is None
    b, = _extrair(cab[:3] + ["   TRIBUNAL DE JUSTICA/GO     2130  2130"]).borderos
    assert b["nome_agrupador"] == "TRIBUNAL DE JUSTICA/GO" and b["cod_agrupador"] == "2130"


# ── A4. reserva da competência pelo nome do arquivo ───────────────────────────
_ARQ = os.path.join("2021", "FATURAS DE ÁGUA - SANEAGO - AGOSTO.2021 - VENC. 30.09.2021.pdf")


def test_competencia_do_nome_do_arquivo_quando_o_borderô_sai_sem():
    cab = _cab(mes="   Nº  FATURA:    3000112233            M?S/ANO     REF:   ")
    doc = _DocFalso([_pagina(cab)], ocr=True)
    res = extrator.processar_documento(doc, _ARQ)
    b, = res.borderos
    assert b["competencia"] == "2021-08"
    assert res.contas_bordero and all(c["competencia"] == "2021-08" for c in res.contas_bordero)


def test_competencia_lida_nao_e_sobrescrita_pelo_nome_do_arquivo():
    doc = _DocFalso([_pagina(_cab())], ocr=True)
    res = extrator.processar_documento(doc, _ARQ)
    b, = res.borderos
    assert b["competencia"] == "2024-04" and all(c["competencia"] == "2024-04" for c in res.contas_bordero)
