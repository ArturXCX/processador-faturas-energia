"""
Medições que existiam na fatura mas não eram lidas.

Cada bloco abaixo é o texto REAL que o pdfplumber/OCR devolve para a fatura
citada — as mesmas faturas da planilha `medicoes_faltantes`. Dois problemas
distintos, com correções distintas:

  1. **Equatorial, linha truncada com texto colado no fim.** Os padrões de
     linha truncada exigiam FIM DE LINHA depois da constante, e o pdfplumber às
     vezes gruda o texto legal da fatura ali ("CONFORME REN. ANEEL 414/10.").
     A linha existia, era truncada, e não casava com padrão nenhum.
  2. **CHESP, posto horário corrompido pelo OCR.** O prefixo aceito antes de
     'ico' era `{1,6}` — quando o acento some por completo sobra 'ico' puro,
     sem prefixo, e a linha era perdida. Em fatura escaneada o OCR ainda troca
     dígitos por letras parecidas ('B414' por 8414, 'o' por zero).

Os testes de NÃO REGRESSÃO daqui são tão importantes quanto os de recuperação:
as linhas completas e as truncadas que já funcionavam não podem mudar.

Rodar:  PYTHONPATH=src python -m pytest tests/ -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core import chesp, equatorial  # noqa: E402


def _med(txt):
    return equatorial.extrair_medicao(txt, "EQUATORIAL_1")


def _campos(m):
    return (m["Grandezas"], m["Postos horarios"], m["Leitura Anterior"],
            m["Leitura Atual"], m["Const Medidor"], m["Consumo kWh"], m["Medidor"])


# ── Equatorial: texto legal colado no fim da linha ───────────────────────────
def test_linha_so_com_constante_e_texto_colado():
    """2022020380357.pdf — sem nenhuma leitura, só a constante, e texto no fim."""
    txt = "1200764-1 ENERGIA ATIVA - KWH ÚNICO 24,000000 CONFORME REN. ANEEL 414/10.\n"
    linhas = _med(txt)
    assert len(linhas) == 1
    assert _campos(linhas[0]) == (
        "ENERGIA ATIVA - KWH", "ÚNICO", 0, 0, 24.0, 0.0, "1200764-1")


def test_linha_com_uma_leitura_e_texto_colado():
    """2022032612025.pdf — uma leitura + constante, e texto no fim."""
    txt = "1200507-0 ENERGIA ATIVA - KWH ÚNICO 26936 40,000000 CONFORME REN. ANEEL 414/10.\n"
    linhas = _med(txt)
    assert len(linhas) == 1
    assert _campos(linhas[0]) == (
        "ENERGIA ATIVA - KWH", "ÚNICO", 26936, 0, 40.0, 0.0, "1200507-0")


def test_medidor_encostado_na_grandeza_com_texto_colado():
    """2022036956174.pdf — medidor colado na grandeza (template antigo)."""
    txt = "10319533-5ENERGIA ATIVA - KWH ÚNICO 69311 1,000000 CONFORME REN. ANEEL 414/10.\n"
    linhas = _med(txt)
    assert len(linhas) == 1
    assert _campos(linhas[0]) == (
        "ENERGIA ATIVA - KWH", "ÚNICO", 69311, 0, 1.0, 0.0, "10319533-5")


def test_linha_completa_continua_completa():
    """REGRESSÃO: linha com todas as colunas não pode ser lida como truncada."""
    txt = "11242277-2ENERGIA ATIVA - KWH ÚNICO 70695 71451 1,000000 756\n"
    linhas = _med(txt)
    assert len(linhas) == 1
    assert _campos(linhas[0]) == (
        "ENERGIA ATIVA - KWH", "ÚNICO", 70695, 71451, 1.0, 756.0, "11242277-2")


def test_linha_completa_seguida_de_texto_nao_vira_truncada():
    """
    REGRESSÃO (o caso mais delicado da mudança): a linha tem TODAS as colunas
    E ainda texto colado no fim. O consumo (756) tem que continuar sendo lido —
    o padrão de linha truncada não pode roubar esta linha.
    """
    txt = "11242277-2ENERGIA ATIVA - KWH ÚNICO 70695 71451 1,000000 756 CONFORME REN. ANEEL\n"
    linhas = _med(txt)
    assert len(linhas) == 1
    assert _campos(linhas[0]) == (
        "ENERGIA ATIVA - KWH", "ÚNICO", 70695, 71451, 1.0, 756.0, "11242277-2")


def test_duas_leituras_sem_consumo_continua_igual():
    """REGRESSÃO: 2022089485668.pdf — duas leituras + constante, sem consumo."""
    txt = "1866645-1 ENERGIA ATIVA - KWH ÚNICO 485427 530341 0,375000\n"
    linhas = _med(txt)
    assert len(linhas) == 1
    assert _campos(linhas[0]) == (
        "ENERGIA ATIVA - KWH", "ÚNICO", 485427, 530341, 0.375, 0.0, "1866645-1")


def test_linha_sem_nenhum_numero_continua_igual():
    """REGRESSÃO: 2022036945790.pdf — nem leitura, nem constante, nem consumo."""
    txt = "12974430-1 ENERGIA GERAÇÃO - KWH RESERVADO\n"
    linhas = _med(txt)
    assert len(linhas) == 1
    assert _campos(linhas[0]) == (
        "ENERGIA GERAÇÃO - KWH", "RESERVADO", 0, 0, 0.0, 0.0, "12974430-1")


def test_truncada_classica_sem_texto_colado_continua_igual():
    """REGRESSÃO: a linha truncada que já funcionava (acaba na constante)."""
    txt = "10586992-9 ENERGIA ATIVA - KWH ÚNICO 80535 1,000000\n"
    linhas = _med(txt)
    assert len(linhas) == 1
    assert _campos(linhas[0]) == (
        "ENERGIA ATIVA - KWH", "ÚNICO", 80535, 0, 1.0, 0.0, "10586992-9")


def test_nao_inventa_linha_juntando_duas():
    """
    REGRESSÃO: duas linhas truncadas seguidas não podem virar uma linha só
    (o nº do medidor de baixo já foi lido como 'Consumo kWh' no passado).
    """
    txt = ("2993839-2 ENERGIA ATIVA - KWH ÚNICO 763377 1,000000\n"
           "2993839-2 ENERGIA REATIVA - KWH ÚNICO 074647 1,000000\n")
    linhas = _med(txt)
    assert len(linhas) == 2
    assert all(l["Consumo kWh"] == 0.0 for l in linhas)
    assert {l["Grandezas"] for l in linhas} == {
        "ENERGIA ATIVA - KWH", "ENERGIA REATIVA - KWH"}


# ── Equatorial: layout "DESCRITIVA" (grandeza 'CONSUMO') ─────────────────────
def test_layout_descritiva_grandeza_consumo():
    """
    'FATURA UC 10024519241 - DESCRITIVA.pdf' (jan/2022) — fatura simples de
    baixa tensão cuja grandeza é 'CONSUMO', sem sufixo. Não estava na lista de
    grandezas e a fatura saía sem medição nenhuma.
    """
    txt = "11767682-9CONSUMO ÚNICO 47840 48310 1,000000 470\n"
    linhas = _med(txt)
    assert len(linhas) == 1
    assert _campos(linhas[0]) == (
        "CONSUMO", "ÚNICO", 47840, 48310, 1.0, 470.0, "11767682-9")


def test_linha_de_item_consumo_nao_vira_medicao():
    """
    REGRESSÃO (o risco de aceitar 'CONSUMO' como grandeza): a MESMA fatura tem
    uma LINHA DE ITEM chamada 'CONSUMO'. Ela não pode virar linha de medição —
    o que a separa é o posto horário, que a linha de item não tem.
    """
    txt = ("CONSUMO - kWh 470,00 0,650560 305,76 1456,15\n"
           "ADC BANDEIRA VERMELHA - kWh 470,00 0,145040 68,16\n")
    assert _med(txt) == []


def test_consumo_nao_engole_grandeza_mais_especifica():
    """REGRESSÃO: 'CONSUMO' é a última alternativa e não atrapalha as demais."""
    txt = ("11767682-9 ENERGIA ATIVA - KWH ÚNICO 100 200 1,000000 100\n"
           "11767682-9 DEMANDA - KW PONTA 300 400 0,048000 100\n")
    linhas = _med(txt)
    assert [l["Grandezas"] for l in linhas] == ["ENERGIA ATIVA - KWH", "DEMANDA - KW"]


# ── CHESP: posto horário corrompido ──────────────────────────────────────────
def test_chesp_posto_ico_puro():
    """FATURA Nº 1327044 — 'Único' virou só 'ico', sem nenhum prefixo."""
    txt = "1194091 Energia Ativa-kWh ico 46159 48905 1 2746\n"
    linhas = chesp.extrair_medicao_chesp(txt, "CHESP_1")
    assert len(linhas) == 1
    assert _campos(linhas[0]) == (
        "ENERGIA ATIVA - KWH", "ÚNICO", 46159, 48905, 1.0, 2746.0, "1194091")


def test_chesp_postos_com_prefixo_continuam_iguais():
    """REGRESSÃO: as variantes que já funcionavam ('?nico', '¿ico', 'Ãšnico')."""
    for posto in ("?nico", "¿ico", "Ãšnico", "Único", "Unico"):
        txt = f"1194091 Energia Ativa-kWh {posto} 100 200 1 100\n"
        linhas = chesp.extrair_medicao_chesp(txt, "CHESP_1")
        assert len(linhas) == 1, posto
        assert linhas[0]["Postos horarios"] == "ÚNICO", posto


def test_chesp_ponta_e_fora_ponta_continuam_iguais():
    """REGRESSÃO: postos que não terminam em 'ico'."""
    txt = ("1194091 Demanda-kW Ponta 100 200 1 100\n"
           "1194091 Demanda-kW Fora Ponta 300 400 1 100\n")
    linhas = chesp.extrair_medicao_chesp(txt, "CHESP_1")
    assert [l["Postos horarios"] for l in linhas] == ["PONTA", "FORA PONTA"]


# ── CHESP: dígitos corrompidos pelo OCR (só quando nada mais funcionou) ──────
def test_chesp_ocr_troca_digitos_por_letras():
    """FATURA Nº 339374 (escaneada) — 'B414' é 8414 e cada 'o' é um zero."""
    txt = ("1194809 Energia Ativa-kWh AÁsnico 6269 B414 1 2145\n"
           "1194809 Energia Reativa-kVArh A&nico o o 1 o\n")
    linhas = chesp.extrair_medicao_chesp(txt, "CHESP_339374")
    assert len(linhas) == 2
    assert _campos(linhas[0]) == (
        "ENERGIA ATIVA - KWH", "ÚNICO", 6269, 8414, 1.0, 2145.0, "1194809")
    assert _campos(linhas[1]) == (
        "ENERGIA REATIVA - KWH", "ÚNICO", 0, 0, 1.0, 0.0, "1194809")


def test_chesp_ocr_nao_roda_quando_a_leitura_normal_funcionou():
    """
    O passe tolerante é ÚLTIMO recurso: se a fatura já rendeu medição pelo
    caminho normal, ele não roda — nenhuma fatura que já era lida corretamente
    passa a ter dígito "corrigido".
    """
    txt = ("1194091 Energia Ativa-kWh Único 100 200 1 100\n"
           "1194091 Energia Reativa-kVArh Único o o 1 o\n")
    linhas = chesp.extrair_medicao_chesp(txt, "CHESP_1")
    assert len(linhas) == 1              # a 2ª linha (com 'o') NÃO é recuperada
    assert linhas[0]["Leitura Atual"] == 200


def test_chesp_ocr_descarta_token_que_nao_vira_numero():
    """Token que não é número nem depois da troca: descarta, não inventa dado."""
    txt = "1194809 Energia Ativa-kWh ico XYZW 8414 1 2145\n"
    linhas = chesp.extrair_medicao_chesp(txt, "CHESP_1")
    assert linhas == []


def test_chesp_ocr_nao_confunde_chave_de_acesso():
    """A chave de acesso (hexadecimal) não pode virar linha de medição."""
    txt = ("1194809 Energia Reativa-kVArh A&nico o o 1 o "
           "C72E.8377.6B9F.B421.FF12.CAAF.9841.95C1\n")
    linhas = chesp.extrair_medicao_chesp(txt, "CHESP_1")
    assert len(linhas) == 1
    assert _campos(linhas[0]) == (
        "ENERGIA REATIVA - KWH", "ÚNICO", 0, 0, 1.0, 0.0, "1194809")


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
