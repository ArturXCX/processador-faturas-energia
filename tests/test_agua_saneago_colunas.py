"""Borderô Saneago: largura de caractere do 1º quartil no layout (só para o borderô) e leitura das colunas.

Os PDFs reais não ficam no repositório: as páginas abaixo são palavras sintéticas (x0, y0, x1, y1, texto) com a geometria
real do borderô de 2024 (fonte da tabela ≈ 3,05 pt por caractere; títulos bem maiores, que inflam a mediana da página).

Rodar:  PYTHONPATH=src python -m pytest tests/test_agua_saneago_colunas.py -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core.agua import extrator, texto  # noqa: E402
from faturas_app.core.agua.texto import Documento  # noqa: E402

CW_TABELA = 3.05      # pt por caractere da fonte da tabela
CW_TITULO = 4.6       # pt por caractere dos títulos
CW_SUBTIT = 4.0


# ── palavras sintéticas ───────────────────────────────────────────────────────
def _palavras_linha(y, partes, cw=CW_TABELA):
    """Palavras de UMA linha. Cada parte é (x, texto) alinhada à esquerda em x; (x, texto, 'd') com o FIM do texto em x;
    (x, texto, 'c') centrada em x. As palavras do texto ficam separadas por um espaço da fonte."""
    saida = []
    for p in partes:
        x, txt = p[0], p[1]
        modo = p[2] if len(p) > 2 else "e"
        largura = len(txt) * cw
        x0 = x - largura if modo == "d" else x - largura / 2 if modo == "c" else x
        cx = x0
        for w in txt.split(" "):
            if w:
                saida.append((cx, y, cx + len(w) * cw, y + 8.0, w))
            cx += (len(w) + 1) * cw
    return saida


def _fmt(v):
    s = f"{v:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# bordas direitas (pt) dos números e centros dos rótulos do cabeçalho
R_CONSUMO, R_AGUA, R_ESGOTO, R_SMRSU = 431.0, 479.0, 516.0, 560.0
C_CONSUMO, C_AGUA, C_ESGOTO, C_SMRSU = 420.0, 467.0, 504.0, 548.0

_LOG_LONGO = "AV. PRESIDENTE VARGAS QD. 72 LT. 1/8 JARDIM BOA ESPERANCA APARECIDA DE GOIANIA"       # 74 caracteres
_CONTAS = [
    # conta, dv, nome, logradouro, consumo, água, esgoto, smrsu
    ("1627885", "2", "TRIBUNAL DE JUSTICA DO ESTADO DE GO", _LOG_LONGO, 300, 3517.27, 3517.27, None),
    ("1584740", "3", "FORUM DE ALEXANIA", _LOG_LONGO, 45, 512.40, 512.40, None),
    ("1555004", "4", "FORUM DE CIDADE OCIDENTAL", _LOG_LONGO, 12, 140.18, None, 25.50),
    ("1989327", "2", "FORUM DE APARECIDA DE GOIANIA", _LOG_LONGO, 8, 98.76, 98.76, None),
    ("1700011", "9", "JUIZADO ESPECIAL", "RUA 5 QD. 3", 20, 250.00, 250.00, None),
    ("1700022", "6", "CARTORIO ELEITORAL", "RUA 7 QD. 9", 5, 61.33, None, 25.50),
]


def _pagina_bordero_palavras(cabecalho=None, contas=_CONTAS):
    """Página de borderô de 2024 (formato novo) com títulos grandes: a mediana das larguras por caractere da página
    (≈4,0 pt) fica bem acima da fonte da tabela (3,05 pt)."""
    p = []
    y = 20.0
    for _ in range(16):                                         # bloco de títulos: 4,6 pt por caractere
        p += _palavras_linha(y, [(20, "RELATORIO GOVERNO ESTADO TITULO GRANDE INFORMATIVO TEXTO")], CW_TITULO)
        y += 14
    if cabecalho is None:
        cabecalho = [
            [(20, "SANEAMENTO DE GOIÁS S.A. CNPJ 01.616.929/0001-02")],
            [(20, "Nº FATURA: 3000483959"), (300, "MÊS/ANO REF: 04/2024")],
            [(20, "DATA DE EMISSÃO: 14/05/2024"), (300, "VENCIMENTO: 30/05/2024")],
            [(20, "NOME DO ÓRGÃO AGRUPADOR:")],
        ]
    for partes in cabecalho:
        p += _palavras_linha(y, partes, CW_SUBTIT)
        y += 12
    p += _palavras_linha(y, [(20, "TRIBUNAL DE JUSTICA ESTADO DE GOIÁS"), (480, "2130 2130")], CW_SUBTIT)
    y += 16
    p += _palavras_linha(y, [(C_AGUA, "VALOR R$", "c"), (C_ESGOTO, "VALOR R$", "c"), (C_SMRSU, "VALOR R$", "c")])
    y += 10
    p += _palavras_linha(y, [(10, "CONTA - DV"), (48, "NOME CLIENTE"), (170, "LOGRADOURO"), (C_CONSUMO, "CONSUMO (M³)", "c"),
                             (C_AGUA, "ÁGUA", "c"), (C_ESGOTO, "ESGOTO", "c"), (C_SMRSU, "SMRSU", "c")])
    y += 12
    for conta, dv, nome, log, cons, agua, esg, smrsu in contas:
        partes = [(10, f"{conta} {dv}"), (48, nome), (170, log), (R_CONSUMO, str(cons), "d"), (R_AGUA, _fmt(agua), "d")]
        if esg is not None:
            partes.append((R_ESGOTO, _fmt(esg), "d"))
        if smrsu is not None:
            partes.append((R_SMRSU, _fmt(smrsu), "d"))
        p += _palavras_linha(y, partes)
        y += 12
    t_cons = sum(c[4] for c in contas)
    t_agua = round(sum(c[5] for c in contas), 2)
    t_esg = round(sum(c[6] or 0 for c in contas), 2)
    t_smr = round(sum(c[7] or 0 for c in contas), 2)
    base = round(t_agua + t_esg, 2)
    retido = round(base * 0.048, 2)
    rotulo = "CONSUMO FATURADO TOTAL / VALOR TOTAL DA FATURA"
    p += _palavras_linha(y, [(10, rotulo), (R_CONSUMO, str(t_cons), "d"), (R_AGUA, _fmt(t_agua), "d"),
                             (R_ESGOTO, _fmt(t_esg), "d"), (R_SMRSU, _fmt(t_smr), "d")])
    y += 14
    p += _palavras_linha(y, [(10, "RETENÇÕES DE IMPOSTOS")], CW_SUBTIT)
    y += 12
    p += _palavras_linha(y, [(10, "IRPJ"), (200, "ALÍQUOTA TOTAL"), (400, "BASE DE CALCULO")])
    y += 12
    p += _palavras_linha(y, [(10, "4,80%"), (200, "4,80%"), (R_SMRSU, _fmt(base), "d")])
    y += 12
    p += _palavras_linha(y, [(10, rotulo), (R_CONSUMO, str(t_cons), "d"), (R_SMRSU, "R$ " + _fmt(base), "d")])
    y += 12
    p += _palavras_linha(y, [(10, f"QUANTIDADE DE CONTAS AGRUPADAS: {len(contas)}")], CW_SUBTIT)
    y += 12
    p += _palavras_linha(y, [(10, "VALOR DO IMPOSTO RETIDO (água e esgoto)"), (R_SMRSU, "R$ " + _fmt(retido), "d")], CW_SUBTIT)
    y += 12
    p += _palavras_linha(y, [(10, "VALOR FINAL DA FATURA"), (R_SMRSU, "R$ " + _fmt(round(t_agua + t_esg + t_smr - retido, 2)), "d")], CW_SUBTIT)
    y += 12
    p += _palavras_linha(y, [(10, "COMUNICADO PARA PAGAMENTO Nº FATURA 3000483959 MÊS/ANO REF. 04/2024")], CW_SUBTIT)
    y += 12
    p += _palavras_linha(y, [(10, "VALOR TOTAL EM R$"), (R_SMRSU, _fmt(round(t_agua + t_esg + t_smr - retido, 2)), "d")], CW_SUBTIT)
    return p


# ── largura do caractere ──────────────────────────────────────────────────────
def test_largura_q1_ignora_titulos_grandes():
    w = [(0.0, 0.0, 3 * 3.0, 8.0, "ABC")] * 45 + [(0.0, 0.0, 3 * 4.5, 12.0, "ABC")] * 55
    assert texto._largura_char(w) == 4.5
    assert texto._largura_char_q1(w) == 3.2
    assert texto._largura_char_q1([]) == 5.0


def test_layout_aceita_cw_explicito():
    w = [(64.0, 10.0, 64.0 + 7 * 3.05, 18.0, "PALAVRA")]
    assert texto.layout(w, cw=3.2).splitlines()[0].index("PALAVRA") == 20
    assert texto.layout(w).splitlines()[0].index("PALAVRA") == int(round(64.0 / texto._largura_char(w)))


def test_de_palavras_guarda_palavras_e_ocr():
    w = [(10.0, 10.0, 40.0, 18.0, "CONTA"), (100.0, 10.0, 130.0, 18.0, "VALOR")]
    doc = Documento.de_palavras([w], ocr=[True], nome="x.pdf")
    assert doc.paginas == [texto.layout(w)] and doc.usou_ocr and doc.nome == "x.pdf"
    assert doc.simples.split() == ["CONTA", "VALOR"] and doc._palavras == [w]
    assert not Documento.de_palavras([w]).usou_ocr


# ── borderô pequeno do formato novo ───────────────────────────────────────────
def test_repaginar_corrige_borderô_pequeno_formato_novo():
    palavras = _pagina_bordero_palavras()
    # a página de fato tem títulos grandes: a mediana passa de 3,9 pt, a fonte da tabela é 3,05 (1º quartil → 3,2)
    assert texto._largura_char(palavras) >= 3.9
    assert texto._largura_char_q1(palavras) == 3.2
    doc = Documento.de_palavras([palavras])
    antes = doc.paginas[0]
    res = extrator.processar_documento(doc, "FATURAS DE ÁGUA - SANEAGO - ABRIL.2024.pdf")
    assert doc.paginas[0] != antes                                      # o borderô foi refeito com o novo layout
    b, = res.borderos
    assert b["id_bordero_agua"] == "SANEAGO_3000483959" and b["competencia"] == "2024-04" and b["formato"] == "novo"
    c1 = res.contas_bordero[0]
    assert c1["valor_agua"] == 3517.27 and c1["valor_esgoto"] == 3517.27 and c1["valor_smrsu"] is None
    assert c1["consumo_m3"] == 300
    assert c1["logradouro"] == _LOG_LONGO and c1["nome_cliente"] == "TRIBUNAL DE JUSTICA DO ESTADO DE GO"
    for c, (_cta, _dv, _nome, _log, cons, agua, esg, smrsu) in zip(res.contas_bordero, _CONTAS):
        assert (c["consumo_m3"], c["valor_agua"], c["valor_esgoto"], c["valor_smrsu"]) == (cons, agua, esg, smrsu)
    assert len(res.contas_bordero) == 6 and b["quantidade_contas"] == 6
    assert b["valor_agua"] == 4579.94 and b["valor_esgoto"] == 4378.43 and b["valor_smrsu"] == 51.0
    assert round(sum(c["valor_agua"] for c in res.contas_bordero), 2) == b["valor_agua"]
    assert b["bate_total"] == "SIM"


def test_repaginar_borderô_com_logradouro_curto_nao_muda():
    """Borderô pequeno com logradouro curto já saía certo: o novo layout não pode mudar o resultado."""
    contas = [(c[0], c[1], c[2], "RUA 5 QD. 3", *c[4:]) for c in _CONTAS]
    palavras = _pagina_bordero_palavras(contas=contas)
    doc = Documento.de_palavras([palavras])
    res_antes = extrator.saneago_bordero.extrair(doc, "x.pdf")
    res = extrator.processar_documento(doc, "FATURAS DE ÁGUA - SANEAGO - ABRIL.2024.pdf")
    assert [(c["valor_agua"], c["valor_esgoto"], c["valor_smrsu"], c["consumo_m3"]) for c in res.contas_bordero] == \
        [(c["valor_agua"], c["valor_esgoto"], c["valor_smrsu"], c["consumo_m3"]) for c in res_antes.contas_bordero]
    assert res.borderos[0]["bate_total"] == "SIM"


def test_outros_fornecedores_nao_sao_repaginados():
    cab = [[(20, "BURITI ALEGRE AMBIENTAL CNPJ: 43.390.208/0001-77 Vencimento Valor a Pagar")],
           [(20, "FATURA N.º 110495 TARIFA AGUA ESGOTO")]]
    palavras = _pagina_bordero_palavras(cabecalho=cab)
    doc = Documento.de_palavras([palavras])
    antes = list(doc.paginas)
    assert texto._largura_char_q1(palavras) != texto._largura_char(palavras)      # repaginar mudaria o texto
    try:
        extrator.processar_documento(doc, "FATURA Nº 110495 - BURITI ALEGRE AMBIENTAL - JANEIRO.2024.pdf")
    except Exception:  # noqa: BLE001  (o extrator GSAN pode estranhar a página sintética; o que importa é o texto)
        pass
    assert doc.paginas == antes


def test_analitica_saneago_nao_e_repaginada():
    cab = [[(20, "SANEAMENTO DE GOIÁS S.A. CNPJ 01.616.929/0001-02")], [(20, "FATURA ANALÍTICA DE ÓRGÃO PÚBLICO")]]
    doc = Documento.de_palavras([_pagina_bordero_palavras(cabecalho=cab)])
    antes = list(doc.paginas)
    try:
        extrator.processar_documento(doc, "ANALITICA - SANEAGO - ABRIL.2024.pdf")
    except Exception:  # noqa: BLE001
        pass
    assert doc.paginas == antes


def test_repaginar_pagina_vazia():
    doc = Documento.de_palavras([[]])
    doc.repaginar()
    assert doc.paginas == [""]


# ── Task 2: ruído de OCR de 1–2 letras na cauda numérica ──────────────────────
from faturas_app.core.agua import saneago_bordero  # noqa: E402


class _DocFalso:
    def __init__(self, paginas, ocr=False):
        self.paginas = list(paginas)
        self.usou_ocr = ocr
        self.vazio = False


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


def _linha_ruido(final=""):
    return _pos((3, "1627885 2"), (15, "TRIBUNAL DE JUSTICA"), (53, "RUA CARMOS GOIAS"), (96, "ak"), (117, "109,06", "d"),
                (123, "A"), (140, "109,06", "d")) + final


def test_cauda_ignora_ruido_de_ocr_entre_valores():
    _cab, _ant, cols = _cols_antigo()
    ln = _linha_ruido()
    valores, consumos, ini = saneago_bordero._numeros_da_cauda(ln, cols, True)
    assert valores == {"agua": 109.06, "esgoto": 109.06} and consumos == {}
    assert ln[ini:].startswith("109,06")                    # o "ak" à esquerda do 1º número não é consumido


def test_cauda_ruido_no_fim_nao_vira_valor():
    _cab, _ant, cols = _cols_antigo()
    ln = _pos((3, "1627885 2"), (15, "TRIBUNAL DE JUSTICA"), (53, "RUA CARMOS GOIAS"), (117, "109,06", "d"), (122, "A"))
    valores, consumos, ini = saneago_bordero._numeros_da_cauda(ln, cols, True)
    assert valores == {} and consumos == {} and ini == len(ln)      # ruído no fim encerra a cauda, como sempre
    assert saneago_bordero._numeros_da_cauda(ln, cols, False) == (valores, consumos, ini)


def test_cauda_logradouro_com_numeros_e_letras_nao_vira_valor():
    _cab, _ant, cols = _cols_antigo()
    # (a) sem cauda real: nada pode sair do logradouro
    for log in ("RUA X QD. 5 LT 12 B", "RUA 7 B", "RUA 100 B", "RUA 32318 B"):
        ln = _pos((3, "1627885 2"), (15, "TRIBUNAL DE JUSTICA"), (53, log))
        assert saneago_bordero._numeros_da_cauda(ln, cols, True) == ({}, {}, len(ln)), log
    # (b) com cauda real e colunas largas: só a cauda conta e o logradouro não é truncado
    ln = _pos((3, "1627885 2"), (15, "TRIBUNAL DE JUSTICA"), (53, "RUA X QD. 5 LT 12 B"), (117, "109,06", "d"), (123, "A"), (140, "109,06", "d"))
    valores, consumos, ini = saneago_bordero._numeros_da_cauda(ln, cols, True)
    assert valores == {"agua": 109.06, "esgoto": 109.06} and consumos == {}
    assert ln[ini:].startswith("109,06") and ln[:ini].rstrip().endswith("12 B")
    # (c) a mesma linha sem o ruído entre os valores continua igual
    ln2 = _pos((3, "1627885 2"), (15, "TRIBUNAL DE JUSTICA"), (53, "RUA X QD. 5 LT 12 B"), (117, "109,06", "d"), (140, "109,06", "d"))
    assert saneago_bordero._numeros_da_cauda(ln2, cols, True)[:2] == ({"agua": 109.06, "esgoto": 109.06}, {})


def test_cauda_ruido_sem_ocr_mantem_comportamento():
    _cab, _ant, cols = _cols_antigo()
    valores, consumos, _ = saneago_bordero._numeros_da_cauda(_linha_ruido(), cols, False)
    assert valores == {"esgoto": 109.06} and consumos == {}


def test_cauda_ruido_sem_numero_a_esquerda_encerra_a_cauda():
    _cab, _ant, cols = _cols_antigo()
    ln = _pos((3, "1627885 2"), (15, "TRIBUNAL DE JUSTICA"), (53, "RUA CARMOS GOIAS"), (96, "A"), (140, "109,06", "d"))
    valores, consumos, ini = saneago_bordero._numeros_da_cauda(ln, cols, True)
    assert valores == {"esgoto": 109.06} and consumos == {}
    assert ln[ini:].startswith("109,06")                    # o "A" não foi consumido


def test_cauda_palavra_de_tres_letras_continua_encerrando_a_cauda():
    _cab, _ant, cols = _cols_antigo()
    ln = _pos((3, "1627885 2"), (53, "RUA CARMOS GOIAS"), (117, "109,06", "d"), (123, "ABC"), (140, "109,06", "d"))
    valores, consumos, _ = saneago_bordero._numeros_da_cauda(ln, cols, True)
    assert valores == {"esgoto": 109.06} and consumos == {}


def _pagina_bordero_antigo_com_ruido():
    L = [
        "   SANEAMENTO        DE  GOIÁS S.A.",
        "   Nº  FATURA:    3000112233            MÊS/ANO     REF:   02/2022",
        "   DATA    DE  EMISSÃO:     14/03/2022          VENCIMENTO:       30/03/2022",
        "   NOME DO ÓRGÃO AGRUPADOR:",
        "   TRIBUNAL DE JUSTICA ESTADO DE GOIÁS                                                    2130  2130",
        _pos((100, "CONSUMO (M³)"), (123, "CONSUMO (M³)")),
        _pos((3, "CONTA - DV"), (16, "NOME CLIENTE"), (53, "LOGRADOURO"), (103, "ÁGUA"), (110, "VALOR R$"), (126, "ESGOTO"), (133, "VALOR R$")),
        # conta com ruído entre os dois valores (sem consumo)
        _pos((3, "1627885 2"), (15, "TRIBUNAL DE JUSTICA"), (53, "RUA CARMOS GOIAS"), (96, "ak"), (117, "109,06", "d"), (123, "A"), (140, "109,06", "d")),
        # conta com os quatro números e ruído entre o valor da água e o consumo do esgoto
        _pos((3, "1584740 3"), (15, "FORUM DE ALEXANIA"), (53, "AV. BRIGADEIRO EDUARDO GOMES"),
             (106, "12", "d"), (117, "250,00", "d"), (121, "|"), (131, "12", "d"), (140, "250,00", "d")),
        # conta limpa
        _pos((3, "1555004 4"), (15, "FORUM DE CIDADE OCIDENTAL"), (53, "RUA 11A QD. LT. MORADA"),
             (106, "5", "d"), (117, "50,25", "d"), (131, "5", "d"), (140, "50,25", "d")),
        _pos((3, "CONSUMO    FATURADO    TOTAL   / VALOR  TOTAL  DA  FATURA"), (106, "17", "d"), (117, "409,31", "d"),
             (131, "17", "d"), (140, "409,31", "d")),
        "   RETENÇÕES     DE IMPOSTOS",
        "   IRPJ                                                   ALÍQUOTA    TOTAL         BASE   DE CALCULO",
        "   4,80%                                                        4,80%                   818,62",
        "   QUANTIDADE    DE CONTAS   AGRUPADAS:   3",
        "   VALOR  DO  IMPOSTO   RETIDO  (água e esgoto)                                        R$   39,29",
        "   VALOR  FINAL  DA FATURA                                                             R$   779,33",
    ]
    return "\n".join(L)


def test_borderô_ocr_com_ruido_fecha_com_rodapé():
    res = saneago_bordero.extrair(_DocFalso([_pagina_bordero_antigo_com_ruido()], ocr=True), "x.pdf")
    b, = res.borderos
    assert b["formato"] == "antigo" and len(res.contas_bordero) == 3
    c1, c2, c3 = res.contas_bordero
    assert (c1["valor_agua"], c1["valor_esgoto"]) == (109.06, 109.06)
    assert (c2["valor_agua"], c2["valor_esgoto"], c2["consumo_m3"]) == (250.00, 250.00, 12)
    assert (c3["valor_agua"], c3["valor_esgoto"]) == (50.25, 50.25)
    assert b["valor_agua"] == 409.31 and b["valor_esgoto"] == 409.31
    assert round(sum(c["valor_agua"] for c in res.contas_bordero), 2) == b["valor_agua"]
    assert round(sum(c["valor_esgoto"] for c in res.contas_bordero), 2) == b["valor_esgoto"]
    assert b["bate_total"] == "SIM"


def test_cauda_ruido_barra_com_espacos_simples_entre_valores():
    """Rodapé real (OCR): `955  9.108,48  1.121 | 10.045,14` — a barra entre dois números, com espaço simples, é ruído."""
    _cab, _ant, cols = _cols_antigo()
    ln = _pos((3, "CONSUMO FATURADO TOTAL / VALOR TOTAL DA FATURA"), (106, "955", "d"), (117, "9.108,48", "d"), (131, "1.121", "d"),
              (132, "|"), (143, "10.045,14", "d"))
    assert "1.121 | 10.045,14" in ln
    valores, consumos, ini = saneago_bordero._numeros_da_cauda(ln, cols, True)
    assert valores == {"agua": 9108.48, "esgoto": 10045.14} and consumos == {"consumo": 955, "consumo_esgoto": 1121}
    assert ln[ini:].startswith("955")
    # sem OCR a barra continua encerrando a cauda
    assert saneago_bordero._numeros_da_cauda(ln, cols, False)[0] == {"esgoto": 10045.14}


def test_cauda_barra_sem_numero_a_esquerda_ou_a_direita_encerra_a_cauda():
    _cab, _ant, cols = _cols_antigo()
    ln = _pos((3, "1627885 2"), (53, "RUA CARMOS GOIAS"), (96, "|"), (140, "109,06", "d"))
    valores, consumos, ini = saneago_bordero._numeros_da_cauda(ln, cols, True)
    assert valores == {"esgoto": 109.06} and consumos == {} and ln[ini:].startswith("109,06")
    ln2 = _pos((3, "1627885 2"), (53, "RUA CARMOS GOIAS"), (140, "109,06", "d"), (142, "|"))
    assert saneago_bordero._numeros_da_cauda(ln2, cols, True) == ({}, {}, len(ln2))


def test_cauda_letra_com_espacos_simples_entre_numeros_nao_encadeia():
    _cab, _ant, cols = _cols_antigo()
    ln = _pos((3, "1627885 2"), (53, "RUA CARMOS GOIAS"), (111, "109,06"), (118, "A"), (120, "109,06"))
    assert "109,06 A 109,06" in ln
    valores, consumos, ini = saneago_bordero._numeros_da_cauda(ln, cols, True)
    assert list(valores.values()) == [109.06] and len(valores) == 1 and consumos == {}
    assert ln[ini:] == "109,06"
