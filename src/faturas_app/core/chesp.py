"""
Processador de faturas da CHESP — portado fielmente do notebook
`proc_chesp.ipynb` (v1/v2). Suporta PDFs-texto (pdfplumber) e PDFs escaneados
(OCR via PyMuPDF + pytesseract). A localização do Tesseract é resolvida pelo
módulo `ocr` (embutido no app ou no sistema).
"""
from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime

import pdfplumber

from . import ocr

FORNECEDOR = "CHESP"

MESES_REV = {'01': 'JAN', '02': 'FEV', '03': 'MAR', '04': 'ABR', '05': 'MAI', '06': 'JUN',
             '07': 'JUL', '08': 'AGO', '09': 'SET', '10': 'OUT', '11': 'NOV', '12': 'DEZ'}


def pf(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip().rstrip('%').replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def get(pattern, text, group=1, default=None, flags=re.IGNORECASE | re.DOTALL):
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else default


def fmt_br(d):
    if not d:
        return None
    p = d.split('/')
    return f"{p[2]}-{p[1]}-{p[0]}" if len(p) == 3 else d


class OCRIndisponivelError(RuntimeError):
    """Levantada quando um PDF escaneado precisa de OCR mas o Tesseract não está disponível."""


def _texto_completo_chesp(txt):
    """O texto tem o corpo da fatura (tabela de itens/total)?"""
    return len(txt) >= 100 and bool(re.search(
        r'TOTAL A PAGAR|Itens de fatura', txt, re.IGNORECASE))


def extrair_texto_chesp(pdf_path):
    """
    Tenta pdfplumber. Normalmente a página 0 basta; nas faturas de jan–mai/2022
    a página 0 tem SÓ o cabeçalho e o corpo fica na página 1 (ainda em texto).
    Se nem juntando as páginas o corpo aparecer (PDF de imagem), usa OCR via
    PyMuPDF + pytesseract e junta com o texto que existir.
    """
    with pdfplumber.open(pdf_path) as pdf:
        paginas = [unicodedata.normalize('NFC', pg.extract_text() or '')
                   for pg in pdf.pages]
    txt = paginas[0] if paginas else ''
    if _texto_completo_chesp(txt):
        return txt
    txt = '\n'.join(p for p in paginas if p.strip())
    if _texto_completo_chesp(txt):
        return txt
    # Fallback/complemento: OCR (todas as páginas).
    if not ocr.configurar_ocr():
        if len(txt) >= 100:
            return txt               # sem OCR: devolve ao menos o que há
        raise OCRIndisponivelError(
            f"O PDF '{os.path.basename(pdf_path)}' é escaneado e precisa de OCR, "
            "mas o motor de OCR (Tesseract) não foi encontrado."
        )
    import fitz                      # PyMuPDF
    import pytesseract
    from PIL import Image
    ocr_paginas = []
    with fitz.open(pdf_path) as doc:
        mat = fitz.Matrix(300 / 72, 300 / 72)      # 300 DPI
        for pg in doc:
            pix = pg.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
            ocr_paginas.append(unicodedata.normalize(
                'NFC', pytesseract.image_to_string(img, lang='por', config='--psm 6')))
    ocr_txt = '\n'.join(p for p in ocr_paginas if p.strip())
    # híbrido: junta o cabeçalho em texto (limpo) com o corpo vindo do OCR
    return (txt + '\n' + ocr_txt) if txt.strip() else ocr_txt


# ─────────────────────────────────────────────────────────────────────────────
# 1. FATURA
# ─────────────────────────────────────────────────────────────────────────────
_MESES_NOME = {'JANEIRO': '01', 'FEVEREIRO': '02', 'MARCO': '03', 'ABRIL': '04',
               'MAIO': '05', 'JUNHO': '06', 'JULHO': '07', 'AGOSTO': '08',
               'SETEMBRO': '09', 'OUTUBRO': '10', 'NOVEMBRO': '11', 'DEZEMBRO': '12'}


def _competencia_do_nome(pdf_path):
    """Extrai a competência (AAAA-MM) do NOME do arquivo (ex.: '... OUTUBRO.2025 ...')."""
    nome = os.path.basename(pdf_path)
    m = re.search(r'\b(JANEIRO|FEVEREIRO|MAR[ÇC]O|ABRIL|MAIO|JUNHO|JULHO|AGOSTO'
                  r'|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO)\.?\s*(\d{4})\b', nome, re.IGNORECASE)
    if not m:
        return None
    mes = _MESES_NOME.get(m.group(1).upper().replace('Ç', 'C'))
    return f"{m.group(2)}-{mes}" if mes else None


def _id_uc_chesp(texto):
    # Rótulo (pode vir com ':' colado, ex.: 'UNIDADE CONSUMIDORA:10605788').
    m = re.search(r'UNIDADE CONSUMIDORA[:\s]{0,2}(\d{5,})', texto, re.IGNORECASE)
    if m:
        return m.group(1)
    # Rodapé tolerante a ruído de OCR: MM/AAAA <id_uc> ... 905 (ex.: '10/2025 – 80703340 905').
    m = re.search(r'\b\d{2}/\d{4}\b[^\d\n]{0,4}(\d{6,10})[^\d\n]{0,6}905', texto)
    if m:
        return m.group(1)
    m = re.search(r'\d{2}/\d{4}\s+(\d{5,})\s+905\s*-', texto)
    if m:
        return m.group(1)
    # A UC pode cair LONGE do rótulo (linha "Rota: 825, Sequência: 159 80703340
    # … NOTA FISCAL"): 1º número de 8–10 dígitos até 120 chars após o rótulo
    # (Rota/Sequência têm ≤4 dígitos; nº da NF tem ≤7).
    m = re.search(r'UNIDADE CONSUMIDORA.{0,120}?(?<!\d)(\d{8,10})(?!\d)',
                  texto, re.IGNORECASE | re.DOTALL)
    return m.group(1) if m else None


def extrair_fatura_chesp(texto, pdf_path):
    numero_fatura = get(r'NOTA FISCAL N[ºo°]\s+(\d+)', texto)
    if not numero_fatura:
        # fallback (OCR falhou): número no nome do arquivo ("FATURA Nº 96411 - ...").
        mnf = re.search(r'FATURA\s*N[ºo°]?\s*(\d+)', os.path.basename(pdf_path), re.IGNORECASE)
        numero_fatura = mnf.group(1) if mnf else os.path.splitext(os.path.basename(pdf_path))[0]
    id_fatura = f"{FORNECEDOR}_{numero_fatura}"

    id_uc = _id_uc_chesp(texto)
    emissao = get(r'DATA DE\s*EMISS[ÃA]O:\s*(\d{2}/\d{2}/\d{4})', texto)

    competencia = None
    m_comp = re.search(r'(\d{2}/\d{4})\s+\d{2}/\d{2}/\d{4}\s+R\$', texto)
    if not m_comp:
        m_comp = re.search(r'(\d{2})/(\d{4})\s+\d{5,}\s+905\s*-\s*EMAIL', texto)
        if m_comp:
            competencia = f"{m_comp.group(2)}-{m_comp.group(1)}"
    if competencia is None and m_comp:
        mm, aa = m_comp.group(1).split('/')
        competencia = f"{aa}-{mm}"
    if competencia is None:
        m_alt = re.search(r'REF:[^\n]*\n(\d{2})/(\d{4})', texto)
        if m_alt:
            competencia = f"{m_alt.group(2)}-{m_alt.group(1)}"
    # Fallback robusto (faturas escaneadas): o mês vem no NOME do arquivo,
    # ex.: "... OUTUBRO.2025 - VENC. ...".
    if competencia is None:
        competencia = _competencia_do_nome(pdf_path)

    m_venc = re.search(r'\d{2}/\d{4}\s+(\d{2}/\d{2}/\d{4})\s+R\$', texto)
    venc = fmt_br(m_venc.group(1)) if m_venc else None

    valor = get(r'TOTAL A PAGAR\s*R?\$?\s*([\d.]+,\d{2})', texto)
    if not valor:
        m_v = re.findall(r'R\$([\d.]+,\d{2})', texto)
        valor = m_v[0] if m_v else None
    if not valor:
        # Modelo 6 (nota antiga, jan–mai/2022): o rótulo fica numa linha de
        # cabeçalho e o valor vem na LINHA SEGUINTE, após o vencimento
        # ("… 30 23/05/2022 6.487,48").
        valor = get(r'TOTAL A PAGAR[\s\S]{0,160}?\d{2}/\d{2}/\d{4}\s+([\d.]+,\d{2})', texto)
        if valor and not venc:
            venc = fmt_br(get(
                r'TOTAL A PAGAR[\s\S]{0,160}?(\d{2}/\d{2}/\d{4})\s+[\d.]+,\d{2}', texto))

    numero_nf = get(r'NOTA FISCAL N[ºo°]\s+(\d+)', texto)
    serie_nf = get(r'NOTA FISCAL[^-]+-\s*S[ÉE]RIE\s+(\d+)', texto) or '000'

    m_ch = re.search(r'(?:Chave de acesso|chave de acesso)[^\n]*\n?\s*([\d\s]{44,60})', texto, re.IGNORECASE)
    chave = re.sub(r'\s', '', m_ch.group(1))[:44] if m_ch else None
    if not chave or len(chave) < 44:
        m_ch2 = re.search(r'(\d{4}(?:\s+\d{4}){10})', texto)
        if m_ch2:
            chave = re.sub(r'\s', '', m_ch2.group(1))

    protocolo = get(r'Protocolo de autoriza[çc][ãa]o:\s*(\d+)', texto)
    m_dh = re.search(r'Protocolo[^\n]+?(\d{2}/\d{2}/\d{4})\s+[àa]s\s+(\d{2}:\d{2})', texto)
    data_hora_protocolo = (fmt_br(m_dh.group(1)) + ' ' + m_dh.group(2)) if m_dh else None

    classif = get(r'Classifica[çc][ãa]o:\s*([AB]\d[^\n]*?)(?:Tipo de|Modalidade)', texto,
                  flags=re.IGNORECASE | re.DOTALL)
    if not classif:
        # Modelo 6 (nota antiga, jan–mai/2022): rótulo em CAIXA ALTA
        # "CLASSIFICAÇÃO:", sem "Tipo de"/"Modalidade" na mesma linha — o
        # texto termina antes de um valor monetário colado ao final (mesma
        # linha da tabela ao lado, ex.: "CLASSIFICAÇÃO: A4 - HORO-SAZONAL
        # VERDE - Poderes Públicos 6.487,48").
        classif = get(r'CLASSIFICA[ÇC][ÃA]O:\s*([AB]\d\s*-\s*.+?)\s+[\d.,]+\s*$',
                      texto, flags=re.MULTILINE | re.IGNORECASE)
    if not classif:
        # Quando o OCR corrompe o marcador "Tipo de"/"Modalidade" que delimita
        # o fim do texto de classificação (mas o código de grupo/subgrupo,
        # ex. "B3", continua legível), recupera um trecho limitado em vez de
        # deixar o campo inteiro em branco.
        classif = get(r'Classifica[çc][ãa]o:\s*([AB]\d[^\n]{0,45})', texto, flags=re.IGNORECASE)
    if classif:
        classif = re.sub(r'\s+', ' ', classif).strip().rstrip(' o')
    else:
        # O OCR às vezes lê a unidade "kW" com um caractere solto colado
        # ("kWw"), quebrando a fronteira de palavra \b original.
        tem_demanda = bool(re.search(r'^\s*DEMANDA\s+kW[Ww]?\b', texto, re.MULTILINE | re.IGNORECASE))
        tem_horaria = bool(re.search(r'Hor[áa]ria\s+Verde', texto, re.IGNORECASE))
        tem_conv = bool(re.search(r'Modalidade.*?Convencional', texto, re.IGNORECASE | re.DOTALL))
        if tem_demanda or tem_horaria:
            classif = 'A4 - Poder Público - Poder Público Estad'
        elif tem_conv:
            classif = 'B3 - Poder Público - Poder Público Estadual'

    m_tf = re.search(r'\b(Trif[áa]sico|Bif[áa]sico|Monof[áa]sico)\b', texto, re.IGNORECASE)
    if m_tf:
        v = m_tf.group(1)
        tipo_forn = v[0].upper() + v[1:].lower()
    else:
        tipo_forn = 'Trifásico'

    m_dem = re.search(r'Demanda fora ponta-kW\s+([\d.,]+)', texto, re.IGNORECASE)
    if not m_dem:
        m_dem = re.search(r'^DEMANDA\s+kW\s+([\d.,]+)', texto, re.MULTILINE | re.IGNORECASE)
    demanda_cont = pf(m_dem.group(1)) if m_dem else 0.0

    m_leit = re.search(
        r'(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(\d{1,3})\s+(\d{2}/\d{2}/\d{4})',
        texto)
    leit_ant = fmt_br(m_leit.group(1)) if m_leit else None
    leit_atu = fmt_br(m_leit.group(2)) if m_leit else None
    dias_leit = int(m_leit.group(3)) if m_leit else None
    prox_leit = fmt_br(m_leit.group(4)) if m_leit else None
    if not m_leit:
        # Modelo 6 (nota antiga, jan–mai/2022): as datas de leitura vêm em
        # colunas próprias ("ANTERIOR ATUAL PRÓXIMA EMISSÃO APRESENTAÇÃO"
        # seguida de uma linha com as 5 datas nessa ordem), não na sequência
        # "data data dias data" das notas mais recentes. O nº de dias não vem
        # impresso perto dali; calcula pela diferença entre anterior/atual
        # (mesma semântica da coluna nas demais faturas).
        m_leit_m6 = re.search(
            r'ANTERIOR\s+ATUAL\s+PR[ÓO]XIMA\s+EMISS[ÃA]O\s+APRESENTA[ÇC][ÃA]O[^\n]*\n\s*'
            r'(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})',
            texto, re.IGNORECASE)
        if m_leit_m6:
            leit_ant = fmt_br(m_leit_m6.group(1))
            leit_atu = fmt_br(m_leit_m6.group(2))
            prox_leit = fmt_br(m_leit_m6.group(3))
            try:
                d1 = datetime.strptime(m_leit_m6.group(1), '%d/%m/%Y')
                d2 = datetime.strptime(m_leit_m6.group(2), '%d/%m/%Y')
                dias_leit = (d2 - d1).days
            except ValueError:
                dias_leit = None

    return {
        'id_fatura':               id_fatura,
        'numero_fatura':           numero_fatura,
        'arquivo_pdf':             os.path.basename(pdf_path),
        'fornecedor':              FORNECEDOR,
        'id_uc':                   id_uc,
        'data_emissao':            fmt_br(emissao),
        'competencia':             competencia,
        'data_vencimento':         venc,
        'valor_total_r$':          pf(valor),
        'numero_nf':               numero_nf,
        'serie_nf':                serie_nf,
        'cfop':                    None,
        'chave_acesso_nfe':        chave,
        'protocolo_autorizacao':   protocolo,
        'data_hora_protocolo':     data_hora_protocolo,
        'classificacao_tarifaria': classif,
        'tipo_fornecimento':       tipo_forn,
        'tensao_nominal_v':        None,
        'tensao_min_v':            None,
        'tensao_max_v':            None,
        'demanda_contratada_kw':   demanda_cont,
        'perdas_transformacao_pct': None,
        'scee_geracao_ciclo':      None,
        'scee_saldo_kwh_total':    None,
        'scee_saldo_kwh_P':        None,
        'scee_saldo_kwh_FP':       None,
        'scee_saldo_kwh_HR':       None,
        'data_leitura_anterior':   leit_ant,
        'data_leitura_atual':      leit_atu,
        'numero_dias_leitura':     dias_leit,
        'data_proxima_leitura':    prox_leit,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. CLIENTE
# ─────────────────────────────────────────────────────────────────────────────
def extrair_cliente_chesp(texto):
    id_uc = _id_uc_chesp(texto)
    razao = get(r'(GOIAS TRIBUNAL DE JUSTICA DO ESTADO DE GOIAS)', texto)
    cnpj = get(r'CPF/CNPJ:?\s*([\d./-]+)', texto)

    munics = re.findall(r'/\s*([^/\n]+?)\s*-\s*GO\b', texto)
    municipio = munics[-1].strip().upper() if munics else None

    ceps = re.findall(r'CEP:?\s*(\d{2})\s*(\d{3})[-\s]?(\d{3})', texto)
    m_bloco = re.search(
        r'TRIBUNAL DE JUSTICA.+?(CEP:?\s*\d{2}\s*\d{3}[-\s]?\d{3})',
        texto, re.DOTALL | re.IGNORECASE)
    cep = None
    if m_bloco:
        m_c = re.search(r'(\d{2})\s*(\d{3})[-\s]?(\d{3})', m_bloco.group(1))
        if m_c:
            cep = m_c.group(1) + m_c.group(2) + m_c.group(3)
    elif len(ceps) >= 2:
        cep = ''.join(ceps[1])
    elif ceps:
        cep = ''.join(ceps[0])

    return {
        'id_uc':        id_uc,
        'razao_social': razao,
        'cnpj':         cnpj,
        'cep':          cep,
        'municipio':    municipio,
        'uf':           'GO',
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. ITENS DA FATURA
# ─────────────────────────────────────────────────────────────────────────────
def _limpar_linha_item(linha):
    linha = re.sub(r'\s+(?:PIS/PASEP|PISIPASEP|COFINS|cus(?:tos?)?|ICMS|icms)\b.*$',
                   '', linha, flags=re.IGNORECASE)
    linha = re.sub(r'\s+"?GRANDEZAS CONTRATADAS.*$', '', linha, flags=re.IGNORECASE)
    linha = re.sub(r'\s+[A-Z]{2,}\s+[A-Z\s]+\d+\s*$', '', linha)
    return linha.strip()


def _norm_unidade(u):
    """Normaliza a unidade, tolerando ruído de OCR ('kWwh'→kWh, 'kWw'→kW)."""
    ul = u.lower()
    if 'v' in ul:
        return 'kVArh'
    return 'kWh' if ul.endswith('h') else 'kW'


def _valor_confiavel(qtd, preco, valor, token_valor, tarifa=None):
    """
    O OCR corrompe a coluna Valor ('15147' sem vírgula = 151,47; '1.801,15'
    com dígito trocado quando qtd×preço = 1.301,15). Na tabela da CHESP
    Valor = Quant × Preço unit; quando o preço é crível (razão preço/tarifa
    dentro do esperado com tributos) e o valor impresso destoa > R$1,
    recalcula. Sem base p/ recálculo, corrige só a vírgula ausente.
    """
    if valor is None:
        return valor
    if qtd and preco and qtd > 0 and preco > 0:
        esperado = round(qtd * preco, 2)
        suspeito = (',' not in token_valor) or abs(valor - esperado) > 1.0
        preco_crivel = tarifa is None or (tarifa > 0 and 0.98 <= preco / tarifa <= 1.30)
        if suspeito and preco_crivel:
            return esperado
    if ',' not in token_valor and valor >= 100:
        return round(valor / 100, 2)
    return valor


def _tarifa_confiavel(token_tarifa, tarifa):
    """
    O OCR às vezes lê a tarifa unitária sem a vírgula decimal quando o
    algarismo antes dela é '0' ('042212' em vez de '0,42212'), e a tarifa vira
    um valor absurdo (42212 em vez de 0,42212). Tarifas de energia sempre têm
    1 dígito antes da vírgula; reinserida logo após o 1º dígito quando o token
    capturado não tem vírgula/ponto e começa com '0'.
    """
    if tarifa is None or not token_tarifa or ',' in token_tarifa or '.' in token_tarifa:
        return tarifa
    if re.match(r'^0\d+$', token_tarifa):
        return tarifa / 10 ** (len(token_tarifa) - 1)
    return tarifa


def _extrair_itens_modelo6(texto, id_fatura):
    """
    Nota antiga "Modelo 6" (jan–mai/2022): os itens ficam na coluna DIREITA,
    mesclados às linhas da medição ("kWh Ativa F P … 8.852 CONSUMO FORA DE
    PONTA 8852 0,32776 2.901,33"). Formato: NOME qtd preço(4+ decimais) valor
    no FIM da linha. Os preços NÃO embutem tributos; a própria fatura imprime
    o total deles ("TRIBUTOS: 316,79"), capturado como item financeiro para a
    soma dos itens fechar com o TOTAL A PAGAR.
    """
    itens = []
    for m in re.finditer(
            r'(?:^|\s)([A-ZÀ-Ü][A-ZÀ-Ü ]{3,}?)\s+(\d+)\s+(\d+,\d{3,})\s+([\d.]+,\d{2})\s*$',
            texto, re.MULTILINE):
        nome = m.group(1).strip()
        if re.match(r'^(TOTAL|LIMITE|VENCIMENTO)', nome):
            continue
        itens.append({'id_fatura': id_fatura, 'item': nome,
                      'tipo': 'FORNECIMENTO', 'unidade': None,
                      'quantidade': pf(m.group(2)),
                      'preco_unitario_com_tributos_r$': pf(m.group(3)),
                      'valor_r$': pf(m.group(4)), 'pis_cofins': None,
                      'base_calc_icms_r$': None, 'aliquota_icms_r$': None,
                      'icms': None, 'tarifa_unitaria_r$': None})
    m = re.search(r'(CUSTEIO DE ILUMINACAO PUBLIC[A-Z ]*?)\s+([\d.]+,\d{2})\s*$',
                  texto, re.MULTILINE)
    if m:
        itens.append({'id_fatura': id_fatura, 'item': m.group(1).strip(),
                      'tipo': 'ITENS FINANCEIROS', 'unidade': None, 'quantidade': 1,
                      'preco_unitario_com_tributos_r$': None,
                      'valor_r$': pf(m.group(2)), 'pis_cofins': None,
                      'base_calc_icms_r$': None, 'aliquota_icms_r$': None,
                      'icms': None, 'tarifa_unitaria_r$': None})
    # Compensações/créditos: linha "NOME [MM/AA] -valor" (ex.:
    # 'COMP. DMIC MENSAL 11/21 -276,65'). Só valores NEGATIVOS, para não
    # capturar rótulos soltos de tributos ("PIS PASEP 68,05").
    for m in re.finditer(
            r'(?:^|\s)([A-ZÀ-Ü][A-ZÀ-Ü ./]{3,}?(?:\s+\d{1,2}/\d{2,4})?)\s+(-\d[\d.]*,\d{2})\s*$',
            texto, re.MULTILINE):
        nome = m.group(1).strip()
        if re.match(r'^(TOTAL|LIMITE|VENCIMENTO)', nome):
            continue
        itens.append({'id_fatura': id_fatura, 'item': nome,
                      'tipo': 'ITENS FINANCEIROS', 'unidade': None, 'quantidade': None,
                      'preco_unitario_com_tributos_r$': None,
                      'valor_r$': pf(m.group(2)), 'pis_cofins': None,
                      'base_calc_icms_r$': None, 'aliquota_icms_r$': None,
                      'icms': None, 'tarifa_unitaria_r$': None})
    # Tributos: usa a SOMA REAL de PIS PASEP + COFINS do quadro de tributos
    # ("PIS 6.656,87 1,02230% 68,05"). O campo "TRIBUTOS:" do quadro
    # "Demonstrativo da Tarifa" costuma ser igual, mas em algumas faturas
    # (RIALMA jan–abr/2022) diverge por centavos de arredondamento na origem —
    # e é PIS+COFINS que compõe de fato o TOTAL A PAGAR. "TRIBUTOS:" fica só
    # como fallback quando o quadro de tributos não for legível.
    m_pis = re.search(r'\bPIS(?:\s*/?\s*PASEP)?\s+[\d.]+,\d{2}\s+[\d.,]+%?\s+([\d.]+,\d{2})',
                      texto)
    m_cof = re.search(r'\bCOFINS\s+[\d.]+,\d{2}\s+[\d.,]+%?\s+([\d.]+,\d{2})', texto)
    val_trib = None
    if m_pis and m_cof:
        val_trib = round((pf(m_pis.group(1)) or 0.0) + (pf(m_cof.group(1)) or 0.0), 2)
    else:
        m = re.search(r'TRIBUTOS:\s*([\d.]+,\d{2})', texto)
        if m:
            val_trib = pf(m.group(1))
    if val_trib is not None:
        itens.append({'id_fatura': id_fatura, 'item': 'TRIBUTOS (PIS/COFINS)',
                      'tipo': 'ITENS FINANCEIROS', 'unidade': None, 'quantidade': None,
                      'preco_unitario_com_tributos_r$': None,
                      'valor_r$': val_trib, 'pis_cofins': None,
                      'base_calc_icms_r$': None, 'aliquota_icms_r$': None,
                      'icms': None, 'tarifa_unitaria_r$': None})
    return itens


def extrair_itens_chesp(texto, id_fatura, id_uc=None):
    itens = []

    bloco = re.search(
        r'Itens de fatura.+?\n(.+?)^TOTAL\b',
        texto, re.DOTALL | re.IGNORECASE | re.MULTILINE)
    if not bloco and re.search(r'Modelo\s*6', texto, re.IGNORECASE):
        itens = _extrair_itens_modelo6(texto, id_fatura)
        for it in itens:
            it['id_uc'] = id_uc
        return itens
    if not bloco:
        bloco = re.search(r'\nCONSUMO.+?\nTOTAL\b', texto, re.DOTALL)

    linhas = bloco.group(0).split('\n') if bloco else texto.split('\n')

    for raw in linhas:
        linha = _limpar_linha_item(raw)
        if not linha or re.match(r'^(TOTAL|VALOR BRUTO|Itens de|Tributo|Medidor|PIS|COF|ICM)', linha, re.IGNORECASE):
            continue

        # Padrão A: item com unidade kWh / kW / kVArh (7 tokens). A unidade
        # tolera ruído de OCR ('kWwh', 'kWw'); a quantidade pode virar uma
        # letra solta no OCR ('n') — capturada como None.
        m = re.match(
            r'^(.+?)\s+(kWwh|kWh|kwh|kWw|kW|kw|kVArh|kvarh)\s+'
            r'([\d.,]+|[a-zº])\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)',
            linha, re.IGNORECASE)
        if m:
            qtd = pf(m.group(3)) if re.match(r'[\d.,]', m.group(3)) else None
            preco = pf(m.group(4))
            tarifa = _tarifa_confiavel(m.group(7), pf(m.group(7)))
            valor = _valor_confiavel(qtd, preco, pf(m.group(5)), m.group(5), tarifa)
            itens.append({'id_fatura': id_fatura,
                          'item':         m.group(1).strip().upper(),
                          'tipo':         'FORNECIMENTO',
                          'unidade':      _norm_unidade(m.group(2)),
                          'quantidade':   qtd,
                          'preco_unitario_com_tributos_r$': preco,
                          'valor_r$':     valor,
                          'pis_cofins':   pf(m.group(6)),
                          'base_calc_icms_r$': None,
                          'aliquota_icms_r$':  None,
                          'icms':         None,
                          'tarifa_unitaria_r$': tarifa})
            continue

        # Padrão B: ADICIONAL BANDEIRA VERMELHA (sem unidade, 5 tokens)
        m = re.match(
            r'^(ADICIONAL BANDEIRA[^\d]+?)\s+'
            r'([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)',
            linha, re.IGNORECASE)
        if m:
            qtd = pf(m.group(2))
            preco = pf(m.group(3))
            tarifa = _tarifa_confiavel(m.group(6), pf(m.group(6)))
            valor = _valor_confiavel(qtd, preco, pf(m.group(4)), m.group(4), tarifa)
            itens.append({'id_fatura': id_fatura,
                          'item':         m.group(1).strip().upper(),
                          'tipo':         'FORNECIMENTO',
                          'unidade':      None,
                          'quantidade':   qtd,
                          'preco_unitario_com_tributos_r$': preco,
                          'valor_r$':     valor,
                          'pis_cofins':   pf(m.group(5)),
                          'base_calc_icms_r$': None,
                          'aliquota_icms_r$':  None,
                          'icms':         None,
                          'tarifa_unitaria_r$': tarifa})
            continue

        # Padrão C: RETENCAO IRPJ (nome inclui "X,X%"; quantidade forçada para -1)
        m = re.match(
            r'^(RETENCAO IRPJ[^\n]+?%)\s+\S+\s+([\d.,]+)\s+(-[\d.,]+)',
            linha, re.IGNORECASE)
        if m:
            itens.append({'id_fatura': id_fatura,
                          'item':         m.group(1).strip().upper(),
                          'tipo':         'ITENS FINANCEIROS',
                          'unidade':      None, 'quantidade': -1,
                          'preco_unitario_com_tributos_r$': pf(m.group(2)),
                          'valor_r$':     pf(m.group(3)),
                          'pis_cofins':   None, 'base_calc_icms_r$': None,
                          'aliquota_icms_r$': None, 'icms': None, 'tarifa_unitaria_r$': None})
            continue

        # Padrão D: CUSTEIO DE ILUMINACAO (3 tokens)
        m = re.match(
            r'^(CUSTEIO[^\d]+?)\s+\d+\s+([\d.,]+)\s+([\d.,]+)',
            linha, re.IGNORECASE)
        if m:
            itens.append({'id_fatura': id_fatura,
                          'item':         m.group(1).strip().upper(),
                          'tipo':         'ITENS FINANCEIROS',
                          'unidade':      None, 'quantidade': 1,
                          'preco_unitario_com_tributos_r$': pf(m.group(2)),
                          'valor_r$':     pf(m.group(3)),
                          'pis_cofins':   None, 'base_calc_icms_r$': None,
                          'aliquota_icms_r$': None, 'icms': None, 'tarifa_unitaria_r$': None})
            continue

        # Padrão E: financeiro genérico "NOME <qtd inteira ±> <preço> <valor>"
        # (ex.: 'COMP. FIC-MENSAL - 09/23 -1 409,70000 -409,70'). Só dentro do
        # bloco de itens, para não capturar cabeçalhos do restante da página.
        if bloco:
            m = re.match(
                r'^([A-ZÀ-ÿ][A-Za-zÀ-ÿ0-9 ./%\-]{3,}?)\s+(-?\d+)\s+'
                r'([\d.,]+)\s+(-?\d[\d.]*,\d{2})\b',
                linha)
            if m:
                itens.append({'id_fatura': id_fatura,
                              'item':         m.group(1).strip().upper(),
                              'tipo':         'ITENS FINANCEIROS',
                              'unidade':      None, 'quantidade': pf(m.group(2)),
                              'preco_unitario_com_tributos_r$': pf(m.group(3)),
                              'valor_r$':     pf(m.group(4)),
                              'pis_cofins':   None, 'base_calc_icms_r$': None,
                              'aliquota_icms_r$': None, 'icms': None, 'tarifa_unitaria_r$': None})
    for it in itens:
        it['id_uc'] = id_uc
    return itens


# ─────────────────────────────────────────────────────────────────────────────
# 4. IMPOSTOS
# ─────────────────────────────────────────────────────────────────────────────
def extrair_impostos_chesp(texto, id_fatura):
    t = re.sub(r'[\|\[\]()\{\}]', ' ', texto)

    # Separador tolerante entre as colunas numéricas (Base/Alíquota/Valor): o
    # OCR às vezes lê o '%' da coluna Alíquota como um caractere solto ('/' ou
    # um traço/travessão) cercado de espaço, quebrando o '\s+' original — ex.:
    # 'COFINS 1.437,22 431 — 61,95' ou '... 4,16 / 126,23'. Tolera no máximo UM
    # desses caracteres entre os números; texto limpo (só espaço) não muda.
    SEP = r'\s*[%/\-–—]?\s+'

    def _corr100(v, ref=None):
        if v is None:
            return v
        if ref is not None and ref > 0 and 90 < v / ref < 110:
            return v / 100
        return v

    def _base_confiavel(base, aliq, val):
        """
        A Base impressa é o campo mais vulnerável ao OCR (mais dígitos; o
        separador decimal pode se perder — '7.120,47' vira '712047', ou até
        '712.047,00' -> '712047', inflando a Base em 100x/1000x+). O Valor
        final tem poucos dígitos e é bem mais confiável. Quando a Base diverge
        muito do esperado (Base×Alíquota/100 muito diferente do Valor
        impresso), recalcula a Base a partir de Valor/Alíquota — a mesma
        fórmula da fatura — em vez de tentar adivinhar o fator de correção.
        Não mexe em nada quando Base já é consistente (tolerância ampla: só
        corrige divergência de mais de 2x, nunca ruído normal de arredondamento).
        """
        if not base or not aliq or not val or base <= 0 or aliq <= 0 or val <= 0:
            return base
        esperado = base * aliq / 100
        if esperado <= 0:
            return base
        razao = val / esperado
        if razao < 0.5 or razao > 2.0:
            return round(val * 100 / aliq, 2)
        return base

    # 'PIS\b' cobre o Modelo 6 (rótulo sem '/PASEP'); tolera 'PIS/IPASEP' (OCR
    # insere um 'I' espúrio após a barra); alíquota pode vir com '%'.
    m_pis = re.search(rf'(?:PIS\s*/?\s*I?PASEP|PIS\b)\s*([\d.,]+)%?{SEP}([\d.,]+)%?{SEP}([\d.,]+)',
                       t, re.IGNORECASE)
    pis_base = pf(m_pis.group(1)) if m_pis else None
    pis_aliq = pf(m_pis.group(2)) if m_pis else None
    pis_val = pf(m_pis.group(3)) if m_pis else None
    if pis_aliq and pis_aliq > 2:
        pis_aliq /= 100
    if pis_base and pis_aliq and pis_val and pis_aliq > 0:
        expected_val = pis_base * pis_aliq / 100
        if expected_val > 0 and abs(expected_val / pis_val - 100) < 10:
            pis_base /= 100
            expected_val /= 100
        if expected_val > 0 and abs(pis_val / expected_val - 100) < 10:
            pis_val /= 100
    pis_base = _base_confiavel(pis_base, pis_aliq, pis_val)

    m_cof = re.search(rf'COFINS\s*([\d.,]+)%?{SEP}([\d.,]+)%?{SEP}([\d.,]+)', t, re.IGNORECASE)
    cof_base = pf(m_cof.group(1)) if m_cof else None
    cof_aliq = pf(m_cof.group(2)) if m_cof else None
    cof_val = pf(m_cof.group(3)) if m_cof else None
    if cof_aliq and cof_aliq > 10:
        cof_aliq /= 100
    cof_base = _corr100(cof_base, pis_base)
    if cof_base and cof_aliq and cof_val and cof_aliq > 0:
        expected_val = cof_base * cof_aliq / 100
        if expected_val > 0 and abs(cof_val / expected_val - 100) < 10:
            cof_val /= 100
    cof_base = _base_confiavel(cof_base, cof_aliq, cof_val)

    m_icm = re.search(rf'ICMS\s*([\d.,]+)%?{SEP}([\d.,]+)%?{SEP}([\d.,]+)', t, re.IGNORECASE)

    impostos = []
    if pis_base is not None:
        impostos.append({'id_fatura': id_fatura, 'Tributo': 'PIS/PASEP',
                         'Base (R$)': pis_base, 'Aliquota (%)': f"{pis_aliq}%", 'Valor (R$)': pis_val})
    if cof_base is not None:
        impostos.append({'id_fatura': id_fatura, 'Tributo': 'COFINS',
                         'Base (R$)': cof_base, 'Aliquota (%)': f"{cof_aliq}%", 'Valor (R$)': cof_val})
    if m_icm:
        impostos.append({'id_fatura': id_fatura, 'Tributo': 'ICMS',
                         'Base (R$)': pf(m_icm.group(1)), 'Aliquota (%)': f"{pf(m_icm.group(2))}%",
                         'Valor (R$)': pf(m_icm.group(3))})
    else:
        impostos.append({'id_fatura': id_fatura, 'Tributo': 'ICMS',
                         'Base (R$)': None, 'Aliquota (%)': '0%', 'Valor (R$)': 0.0})
    return impostos


# ─────────────────────────────────────────────────────────────────────────────
# 5. MEDIÇÃO
# ─────────────────────────────────────────────────────────────────────────────
def extrair_medicao_chesp(texto, id_fatura):
    import re as _re
    texto = _re.sub(r'\(o\)', '0', texto, flags=_re.IGNORECASE)
    texto = _re.sub(r'\[o\]', '0', texto, flags=_re.IGNORECASE)
    texto = _re.sub(r'\bº\b', '0', texto)
    texto = _re.sub(r'\b[jf]o\]\b', '0', texto, flags=_re.IGNORECASE)
    medicao = []
    GRANDEZA = (r'(Energia Ativa-kWh|Energia Reativa|Demanda-kW|'
                r'Demanda Reativa|Demanda kW)')
    POSTO = r'(Ponta|Fora Ponta|Fora\s*[Pp]onta|Reservado|Unico|Único)'

    pat = re.compile(
        rf'^(\d+)\s+{GRANDEZA}\s+{POSTO}\s+'
        r'([\d.,]+)\s+([\d.,]+)\s+(\d+)\s+([\d.,]+)',
        re.IGNORECASE | re.MULTILINE)

    # Dedup só de linhas completamente idênticas (mantém variações de leitura).
    seen = set()
    for m in pat.finditer(texto):
        if re.search(r'[A-F]{4}', m.group(5)):
            continue
        linha = {'id_fatura':        id_fatura,
                 'Grandezas':        m.group(2),
                 'Postos horarios':  re.sub(r'\s+', ' ', m.group(3)).title(),
                 'Leitura Anterior': int(re.sub(r'\D', '', m.group(4))),
                 'Leitura Atual':    int(re.sub(r'\D', '', m.group(5))),
                 'Const Medidor':    pf(m.group(6)),
                 'Consumo kWh':      pf(m.group(7)),
                 'Medidor':          m.group(1)}
        key = tuple(v for k, v in linha.items() if k != 'id_fatura')
        if key in seen:
            continue
        seen.add(key)
        medicao.append(linha)
    _padronizar_medicao_chesp(medicao)
    return medicao


def _padronizar_medicao_chesp(medicao):
    """
    Padroniza (só CHESP) 'Grandezas' e 'Postos horarios' das linhas de medição:
      - Grandezas: MAIÚSCULAS; todo hífen fica cercado por 1 espaço de cada lado
        (não encosta em palavra); 'ENERGIA REATIVA' vira 'ENERGIA REATIVA - KWH'.
      - Postos horarios: MAIÚSCULAS.
    """
    for linha in medicao:
        g = str(linha.get('Grandezas', '')).upper()
        g = re.sub(r'\s*-\s*', ' - ', g).strip()
        if g == 'ENERGIA REATIVA':
            g = 'ENERGIA REATIVA - KWH'
        linha['Grandezas'] = g
        linha['Postos horarios'] = str(linha.get('Postos horarios', '')).upper()
    return medicao


# ─────────────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────────────
def processar_pdf(pdf_path):
    """Processa um único PDF da CHESP e devolve as linhas de cada aba."""
    from .equatorial import carimbar_id_uc_competencia
    txt = extrair_texto_chesp(pdf_path)
    fat = extrair_fatura_chesp(txt, pdf_path)
    cli = extrair_cliente_chesp(txt)
    fid = fat['id_fatura']
    id_uc = fat.get('id_uc') or f"NULO_{fid}"
    resultado = {
        'fatura':               fat,
        'unidade_consumidora':  cli,
        'itens_fatura': extrair_itens_chesp(txt, fid, id_uc),
        'impostos':     extrair_impostos_chesp(txt, fid),
        'medicao':      extrair_medicao_chesp(txt, fid),
    }
    carimbar_id_uc_competencia(resultado, id_uc, fat.get('competencia'))
    from . import correcoes
    correcoes.aplicar(resultado)
    return resultado
