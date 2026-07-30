"""
Testes de extração da MEDIÇÃO, com trechos REAIS de faturas (sem depender dos
PDFs). Cada bloco abaixo foi copiado do texto que o pdfplumber devolve para a
fatura citada no comentário.

Cobrem os layouts que ficavam SEM NENHUMA linha de medição na planilha final
(~1.100 faturas) e, principalmente, travam os layouts que JÁ funcionavam — é
esse segundo grupo que não pode mudar de resultado.

Rodar:  PYTHONPATH=src python -m pytest tests/ -q
   ou:  PYTHONPATH=src python tests/test_medicao.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faturas_app.core import chesp, equatorial  # noqa: E402


def _linhas(medicao):
    """(Grandezas, Posto, Leit.Ant, Leit.Atual, Const, Consumo, Medidor)."""
    return [(m["Grandezas"], m["Postos horarios"], m["Leitura Anterior"],
             m["Leitura Atual"], m["Const Medidor"], m["Consumo kWh"],
             m["Medidor"]) for m in medicao]


# ─────────────────────────────────────────────────────────────────────────────
# EQUATORIAL — medidor COLADO na grandeza (sem espaço)
# ─────────────────────────────────────────────────────────────────────────────
def test_eq_medidor_colado_na_grandeza():
    """2022005218435.pdf — template usado até meados de 2023 (posto ÚNICO)."""
    txt = "11242277-2ENERGIA ATIVA - KWH ÚNICO 70695 71451 1,000000 756\n"
    assert _linhas(equatorial.extrair_medicao(txt, "F")) == [
        ("ENERGIA ATIVA - KWH", "ÚNICO", 70695, 71451, 1.0, 756.0, "11242277-2"),
    ]


def test_eq_medidor_colado_linha_sem_numero_algum():
    """2022093327464.pdf — a 2ª linha não traz leitura, constante nem consumo."""
    txt = ("12794856-2ENERGIA ATIVA - KWH ÚNICO 00000 00000 1,000000 0\n"
           "12794856-2ENERGIA GERAÇÃO - KWH ÚNICO\n")
    assert _linhas(equatorial.extrair_medicao(txt, "F")) == [
        ("ENERGIA ATIVA - KWH", "ÚNICO", 0, 0, 1.0, 0.0, "12794856-2"),
        ("ENERGIA GERAÇÃO - KWH", "ÚNICO", 0, 0, 0.0, 0.0, "12794856-2"),
    ]


def test_eq_medidor_colado_uma_leitura_so():
    """2023038617648.pdf — só a leitura e a constante são impressas."""
    txt = "12982533-6ENERGIA ATIVA - KWH ÚNICO 000000 50,000000\n"
    assert _linhas(equatorial.extrair_medicao(txt, "F")) == [
        ("ENERGIA ATIVA - KWH", "ÚNICO", 0, 0, 50.0, 0.0, "12982533-6"),
    ]


def test_eq_com_espaco_continua_igual():
    """Regressão: com o espaço presente a captura não pode mudar."""
    txt = "11595015-0 ENERGIA ATIVA - KWH ÚNICO 01103 01107 1,000000 4\n"
    assert _linhas(equatorial.extrair_medicao(txt, "F")) == [
        ("ENERGIA ATIVA - KWH", "ÚNICO", 1103, 1107, 1.0, 4.0, "11595015-0"),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# EQUATORIAL — medidor à DIREITA, linha sem leitura anterior nem consumo
# ─────────────────────────────────────────────────────────────────────────────
def test_eq_truncada_com_medidor_a_direita():
    """2024118160906.pdf — faltam as colunas 'Leitura Anterior' e 'Consumo'."""
    txt = ("ENERGIA ATIVA - KWH PONTA 086926 0,012000 11556447-1\n"
           "DEMANDA - KW RESERVADO 011017 0,048000 11556447-1 03/01/2025\n"
           "UFER PONTA 074175 0,012000 11556447-1 2384,76\n")
    assert _linhas(equatorial.extrair_medicao(txt, "F")) == [
        ("ENERGIA ATIVA - KWH", "PONTA", 0, 86926, 0.012, 0.0, "11556447-1"),
        ("DEMANDA - KW", "RESERVADO", 0, 11017, 0.048, 0.0, "11556447-1"),
        ("UFER", "PONTA", 0, 74175, 0.012, 0.0, "11556447-1"),
    ]


def test_eq_linha_completa_tem_prioridade_sobre_a_truncada():
    """Regressão: linha com consumo continua indo pelo pat_a, com o consumo."""
    txt = ("ENERGIA ATIVA - KWH PONTA 523190 541431 0,012000 224,36 12506079-3\n"
           "DEMANDA - KW PONTA 008559 008816 0,048000 12,6444 12506079-3\n")
    assert _linhas(equatorial.extrair_medicao(txt, "F")) == [
        ("ENERGIA ATIVA - KWH", "PONTA", 523190, 541431, 0.012, 224.36, "12506079-3"),
        ("DEMANDA - KW", "PONTA", 8559, 8816, 0.048, 12.6444, "12506079-3"),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# CHESP
# ─────────────────────────────────────────────────────────────────────────────
def test_chesp_unico_corrompido_e_reativa_kvarh():
    """FATURA Nº 928633.pdf — 'Único' sai como '?nico' na fonte do PDF."""
    txt = ("1194091 Energia Ativa-kWh ?nico 20174 23269 1 3095\n"
           "1194091 Energia Reativa-kVArh ?nico 0 0 1 0\n")
    assert _linhas(chesp.extrair_medicao_chesp(txt, "F")) == [
        ("ENERGIA ATIVA - KWH", "ÚNICO", 20174, 23269, 1.0, 3095.0, "1194091"),
        ("ENERGIA REATIVA - KWH", "ÚNICO", 0, 0, 1.0, 0.0, "1194091"),
    ]


def test_chesp_layout_atual_continua_igual():
    """Regressão: o layout de 2023+ que já funcionava não pode mudar."""
    txt = ("302 Energia Ativa-kWh Ponta 88 94 100 662\n"
           "302 Energia Ativa-kWh Fora Ponta 1.041 1.131 100 9238\n"
           "302 Demanda-kW Ponta 0 0 100 21\n")
    assert _linhas(chesp.extrair_medicao_chesp(txt, "F")) == [
        ("ENERGIA ATIVA - KWH", "Ponta".upper(), 88, 94, 100.0, 662.0, "302"),
        ("ENERGIA ATIVA - KWH", "FORA PONTA", 1041, 1131, 100.0, 9238.0, "302"),
        ("DEMANDA - KW", "PONTA", 0, 0, 100.0, 21.0, "302"),
    ]


def test_chesp_layout_modelo6_antigo():
    """FATURA Nº 136454.pdf (mai/2022) — medidor só no cabeçalho."""
    txt = ("Nº MEDIDOR: 1194091\n"
           "TIPO DE MEDIÇÃO GRANDEZA LEITURA ANTERIOR LEITURA ATUAL CONSTANTE "
           "CONSUMO MEDIDO CONSUMO FATURADO\n"
           "ATIVA kWh 56475,000 60848,000 1,00 4.373 4.373\n")
    assert _linhas(chesp.extrair_medicao_chesp(txt, "F")) == [
        ("ENERGIA ATIVA - KWH", "ÚNICO", 56475, 60848, 1.0, 4373.0, "1194091"),
    ]


def test_chesp_layout_grupo_a_antigo():
    """FATURA Nº 78902.pdf (mar/2022) — rótulo junta grandeza e posto, e a
    coluna da direita da fatura cai na mesma linha de texto."""
    txt = (
        "LEITURA DATAS FATOR DE POT.: 96,60 N° MEDIDOR(kWh): 185\n"
        "Tipo de consumo Anterior Atual Constante Total Faturado\n"
        "kWh Ativa Ponta 922,762 932,334 40,00000 392 392\n"
        "kWh Ativa F P 10.549,471 10.654,866 40,00000 4.321 4.321 CONSUMO FORA "
        "DE PONTA 4321 0,32776 1.416,25\n"
        "kWh Res 0,000 0,000 40,00000 0 0\n"
        "UFER F P 57,539 57,984 40,00000 18 0 DEMANDA 40 18,92000 756,80\n"
        "kW F P (Q) 0,688 0,761 40,00000 31 40\n"
        "DMCR Ponta (Q) 0,308 0,416 40,00000 17 0 BANDEIRA TARIFARIA ESCASSEZ H\n"
        "Ultrapass Ponta 0,000 0,000 40,00000 0 0\n"
    )
    assert _linhas(chesp.extrair_medicao_chesp(txt, "F")) == [
        ("ENERGIA ATIVA - KWH", "PONTA", 922, 932, 40.0, 392.0, "185"),
        ("ENERGIA ATIVA - KWH", "FORA PONTA", 10549, 10654, 40.0, 4321.0, "185"),
        ("ENERGIA ATIVA - KWH", "RESERVADO", 0, 0, 40.0, 0.0, "185"),
        ("UFER", "FORA PONTA", 57, 57, 40.0, 18.0, "185"),
        ("DEMANDA - KW", "FORA PONTA", 0, 0, 40.0, 31.0, "185"),
        ("DMCR", "PONTA", 0, 0, 40.0, 17.0, "185"),
        ("ULTRAPASSAGEM", "PONTA", 0, 0, 40.0, 0.0, "185"),
    ]


if __name__ == "__main__":
    falhas = 0
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK ", nome)
            except AssertionError as e:
                falhas += 1
                print("FALHOU ", nome, e)
    print(f"\n{falhas} falha(s).")
    sys.exit(1 if falhas else 0)
