"""
Processador de faturas da EQUATORIAL (Goiás) — portado fielmente do notebook
`proc_equatorial.ipynb` (v4). A lógica de extração (regexes) é idêntica à do
notebook validado; aqui apenas reorganizamos em funções reutilizáveis pela
interface, expondo `processar_pdf(path)` que devolve as linhas de uma fatura.
"""
from __future__ import annotations

import os
import re
import unicodedata

import pdfplumber

FORNECEDOR = "EQUATORIAL"

MESES = {'JAN': '01', 'FEV': '02', 'MAR': '03', 'ABR': '04', 'MAI': '05', 'JUN': '06',
         'JUL': '07', 'AGO': '08', 'SET': '09', 'OUT': '10', 'NOV': '11', 'DEZ': '12'}


def extrair_texto(pdf_path):
    """Concatena APENAS as páginas úteis (que começam com 'ENDEREÇO DE ENTREGA:')."""
    with pdfplumber.open(pdf_path) as pdf:
        pages = [unicodedata.normalize('NFC', pg.extract_text() or '')
                 for pg in pdf.pages]
    util = [pg for pg in pages
            if re.match(r'ENDERE[ÇC]O DE ENTREGA:', pg.strip(), re.IGNORECASE)]
    texto = '\n'.join(util) if util else '\n'.join(pages)
    if len(texto.strip()) >= 100:
        return texto
    # PDF escaneado (ex.: faturas CELG-D antigas): OCR página a página,
    # como no processador da CHESP.
    from . import ocr
    if not ocr.configurar_ocr():
        raise RuntimeError(
            f"O PDF '{os.path.basename(pdf_path)}' é escaneado e precisa de OCR, "
            "mas o motor de OCR (Tesseract) não foi encontrado.")
    import fitz  # PyMuPDF
    import pytesseract
    from PIL import Image
    paginas_ocr = []
    with fitz.open(pdf_path) as doc:
        for pg in doc:
            pix = pg.get_pixmap(dpi=200)
            img = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
            paginas_ocr.append(unicodedata.normalize(
                'NFC', pytesseract.image_to_string(img, lang='por', config='--psm 6')))
    return '\n'.join(paginas_ocr)


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


# ──────────────────────────────────────────────────────────────────────────────
# 1. FATURA
# ──────────────────────────────────────────────────────────────────────────────
def _extrair_id_uc(texto):
    m = re.search(r'^(\d{4,})\s+Consulte', texto, re.MULTILINE | re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'Consulte pela Chave[^\n]*\n(\d{4,})\s', texto, re.IGNORECASE)
    if m:
        return m.group(1)
    # Formatos antigos (a UC não fica junto de "Consulte"):
    #  Out/2023 ("Número da UC"): UC ao fim da linha de PERDAS.
    m = re.search(r'PERDAS DE TRANSFORMA[ÇC][ÃA]O\s*/\s*RAMAL:\s*[\d.,]+\s*%\s+(\d{6,})',
                  texto, re.IGNORECASE)
    if m:
        return m.group(1)
    #  2022 até ~mai/2023 ("Instalação/Unidade Consumidora"): UC antes de "NOTA FISCAL Nº".
    m = re.search(r'(?<!\d)(\d{8,12})\s+NOTA FISCAL\s*N', texto, re.IGNORECASE)
    if m:
        return m.group(1)
    #  Layout antigo (DANF3E 2022–mai/2023): a UC fica SOZINHA numa linha do
    #  cabeçalho, entre a razão social e o endereço — sempre ANTES da linha
    #  "NOTA FISCAL Nº" (confirmado pelo bloco 'CADASTRO RATEIO GERAÇÃO: UC <n>'
    #  das faturas SCEE). Linhas só-dígitos DEPOIS dessa âncora (ex.: código de
    #  rota "2535528"/"194170") não são a UC, por isso o corte no cabeçalho.
    m_nf = re.search(r'NOTA FISCAL\s*N', texto, re.IGNORECASE)
    if m_nf:
        soltas = re.findall(r'^\s*(\d{5,12})\s*$', texto[:m_nf.start()], re.MULTILINE)
        if soltas:
            return soltas[-1]
    #  Set–out/2023 ("Segunda via"): a UC vem COLADA ao fim da linha do CEP do
    #  cabeçalho ("CEP: 74140110 GOIANIA GO BRASIL 10029747412"). Exige 8–12
    #  dígitos para não confundir com o nº do cliente (194170 / 2535528, 6–7).
    m = re.search(r'^CEP:\s*\d{5,8}[^\n]*?BRASIL\s+(\d{8,12})\s*$', texto,
                  re.IGNORECASE | re.MULTILINE)
    if m:
        return m.group(1)
    #  Faturas CELG-D escaneadas (texto de OCR, com ruído): UC logo após o
    #  rótulo 'UNIDADE CONSUMIDORA'.
    m = re.search(r'UNIDADE CONSUMIDORA[^\d]{0,60}?(\d{8,12})', texto, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'\b(\d{1,3}(?:\.\d{3})+\.\d{3}-\d{2}|\d{1,3}\.\d{3}\.\d{3}-\d{2})\b', texto)
    if m:
        return m.group(1)
    return None


def extrair_scee(texto):
    """
    Extrai do bloco 'INFORMAÇÕES DO SCEE' (presente apenas em UCs do SCEE):
      - ciclo : ciclo de geração no formato AAAA_MM (de '(M/AAAA)').
      - total : valor após 'SALDO KWH:' quando é um número único, ou o valor de
                'ATV:' (os dois casos são equivalentes; o rótulo ATV é descartado).
      - p/fp/hr : valores de 'P=', 'FP=', 'HR=' quando o saldo vem por posto
                  (ex.: 'P=0,00, FP=51.271,68, HR=0,00').
    Devolve (ciclo, total, p, fp, hr); campos ausentes vêm como None.
    """
    ciclo = total = p = fp = hr = None
    m = re.search(r'GERA[ÇC][ÃA]O\s+CICLO\s*\((\d{1,2})/(\d{4})\)', texto, re.IGNORECASE)
    if m:
        ciclo = f"{m.group(2)}_{int(m.group(1)):02d}"

    # DOTALL: o bloco 'SALDO KWH: P=.., FP=.., HR=..' pode quebrar em duas linhas
    # (ex.: HR na linha de baixo). Sem cruzar a quebra, o HR ficava sem preencher.
    ms = re.search(
        r'\bSALDO\s+KWH:\s*(.*?)(?:,?\s*SALDO\s+A\s+EXPIRAR|,?\s*CADASTRO|$)',
        texto, re.IGNORECASE | re.DOTALL)
    if ms:
        seg = ms.group(1).strip().rstrip(',').strip()
        num = r'(-?\d[\d.]*,\d{2})'

        def _val(chave):
            mm = re.search(rf'\b{chave}\s*[:=]\s*{num}', seg, re.IGNORECASE)
            return mm.group(1) if mm else None

        p, fp, hr = _val('P'), _val('FP'), _val('HR')
        atv = _val('ATV')
        if atv:                                  # 'SALDO KWH: ATV: <num>'
            total = atv
        elif p is None and fp is None and hr is None:
            # 'SALDO KWH: <num>' — segmento é apenas o número.
            mm = re.match(rf'^{num}', seg)
            total = mm.group(1) if mm else None
    return ciclo, total, p, fp, hr


def extrair_fatura(texto, pdf_path, numero_forcado=None):
    numero_fatura = numero_forcado or os.path.splitext(os.path.basename(pdf_path))[0]
    if not numero_fatura.isdigit():
        # canhoto: 'data numero MMM/AAAA' (grupo B) ou 'data numero data' (grupo A)
        m = (re.search(r'\d{2}/\d{2}/\d{4}\s+(\d{10,})\s+[A-Z]{3}/\d{4}', texto)
             or re.search(r'\d{2}/\d{2}/\d{4}\s+(\d{10,})\s+\d{2}/\d{2}/\d{4}', texto))
        if m:
            numero_fatura = m.group(1)
        else:
            # último recurso: número isolado de 13 dígitos iniciando pelo ano
            m = re.search(r'(?<![\d.])(20\d{11})(?![\d.])', texto)
            if m:
                numero_fatura = m.group(1)
    # id_fatura recebe prefixo da fornecedora; numero_fatura preserva o valor
    # original (= nome do PDF no Drive, usado na busca do link).
    id_fatura = f"{FORNECEDOR}_{numero_fatura}"

    id_uc = _extrair_id_uc(texto)
    scee_ciclo, scee_tot, scee_p, scee_fp, scee_hr = extrair_scee(texto)
    emissao = get(r'DATA DE EMISS[ÃA]O:\s*(\d{2}/\d{2}/\d{4})', texto)
    m_comp = re.search(r'\b(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)/(\d{4})\b', texto, re.IGNORECASE)
    if not m_comp:
        # OCR de fatura escaneada: a barra vira ruído ("JANI2023", "JAN12023").
        m_comp = re.search(r'\b(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)[^\s\d]?(\d{4})\b',
                           texto, re.IGNORECASE)
    competencia = f"{m_comp.group(2)}-{MESES[m_comp.group(1).upper()]}" if m_comp else None
    venc = get(r'(?:JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)/\d{4}\s+(\d{2}/\d{2}/\d{4})', texto)
    if not venc:
        venc = get(r'(?:JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)[^\s\d]?\d{4}\s+(\d{2}/\d{2}/\d{4})',
                   texto)
    valor = get(r'R\$\*+([\d.,]+)', texto)
    if valor is None:
        # OCR: ruído entre o R$ e o valor ("R$º******2.464,09"); exige junção sem
        # espaço para não capturar valores soltos como "R$ 748,52311" (VRC).
        valor = get(r'R\$\S{0,12}?(\d{1,3}(?:\.\d{3})*,\d{2})(?!\d)', texto)
    numero_nf = get(r'NOTA FISCAL N[º°O\s]+(\d+)', texto)
    serie_nf = get(r'NOTA FISCAL[^-]+-\s*S[ÉE]RIE\s+(\d+)', texto) or '0'

    m_ch = re.search(r'chave de acesso:\s*\n?\s*(\d{44})', texto, re.IGNORECASE)
    chave = m_ch.group(1) if m_ch else None

    m_pr = re.search(r'Protocolo de autoriza[çc][ãa]o:\s*(\d+)', texto, re.IGNORECASE)
    protocolo = m_pr.group(1) if m_pr else None
    m_dh = re.search(r'Protocolo[^\n]+?(\d{2}/\d{2}/\d{4})\s+[àa]s\s+(\d{2}:\d{2})', texto, re.IGNORECASE)
    data_hora_protocolo = (fmt_br(m_dh.group(1)) + ' ' + m_dh.group(2)) if m_dh else None

    classif = get(r'Classifica[çc][ãa]o:\s*(.+?)\s+Tipo de [Ff]ornecimento:', texto)
    if not classif:
        classif = get(r'Classifica[çc][ãa]o:\s*([^\n]+)', texto)
    tipo_forn = get(r'Tipo de [Ff]ornecimento:\s*(\S+)', texto)
    m_cab = None
    if not classif:
        # layout antigo: cabeçalho "B B3 PODER PÚBLICO - ESTADUAL CONVENCIONAL
        # TRIFÁSICO <datas de leitura>" (grupo, subgrupo, classificação,
        # modalidade, fases) — sem os rótulos "Classificação:"/"Tipo de". O
        # código de grupo/subgrupo (ex.: "B B3") entra junto no group(1) —
        # sem isso, classificacao_tarifaria saía incompleta ("PODER PÚBLICO -
        # ESTADUAL", sem o "B B3" na frente). Entre as FASES e a 1ª data pode
        # haver o "Nº de dias" da leitura colado ANTES dela (variante rara);
        # tolerar isso (grupo opcional, não usado aqui) evita que classif/
        # tipo_fornecimento falhem também — sem essa tolerância, a linha
        # inteira (inclusive campos que nada têm a ver com a leitura) ficava
        # em branco.
        m_cab = re.search(
            r'^([AB]\s+[AB]\d?\S*)\s+(.+?)\s+\S+\s+((?:MONO|BI|TRI)F[ÁA]SICO)\s+'
            r'(?:(\d{1,3})\s+)?(\d{2}/\d{2}/\d{4})', texto, re.MULTILINE | re.IGNORECASE)
        if m_cab:
            classif = f"{m_cab.group(1)} {m_cab.group(2).strip()}"
            if not tipo_forn:
                tipo_forn = m_cab.group(3).upper()
    tensao_nom = get(r'Tens[ãa]o Nominal Disp:\s*(\d+)\s*V', texto)
    tensao_min = get(r'Lim Min:\s*([\d.,]+)\s*V', texto)
    tensao_max = get(r'Lim Max:\s*([\d.,]+)\s*V', texto)

    # ── GRANDEZAS CONTRATADAS ──────────────────────────────────────────────
    m_dem = re.search(r'DEMANDA\s*-\s*kW\s+(\d+(?:[.,]\d+)?)', texto, re.IGNORECASE)
    demanda_cont = pf(m_dem.group(1)) if m_dem else 0.0
    m_dem_g = re.search(r'DEMANDA\s+GERA[ÇC][ÃA]O\s*-\s*kW\s+(\d+(?:[.,]\d+)?)', texto, re.IGNORECASE)
    demanda_ger_cont = pf(m_dem_g.group(1)) if m_dem_g else 0.0

    perdas = pf(get(r'PERDAS DE TRANSFORMA[ÇC][ÃA]O\s*/\s*RAMAL:\s*([\d.,]+)\s*%', texto))

    m_leit = re.search(
        r'(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(\d{1,3})\s+(\d{2}/\d{2}/\d{4})',
        texto)
    numero_dias_leit = int(m_leit.group(3)) if m_leit else None
    data_prox_leit = fmt_br(m_leit.group(4)) if m_leit else None
    if not m_leit and m_cab and m_cab.group(4):
        # Layout antigo, variante onde "Leitura anterior/atual" não aparecem
        # na sequência padrão (2 datas + dias + data) em nenhum lugar do
        # texto, mas "dias" e "próxima leitura" vêm colados ao fim da MESMA
        # linha do cabeçalho (grupo/subgrupo/classificação/fases). Recupera
        # pelo menos esses dois em vez de deixar as 4 colunas em branco;
        # leitura anterior/atual seguem None (não há como inferi-las com
        # segurança a partir só dessa linha).
        numero_dias_leit = int(m_cab.group(4))
        data_prox_leit = fmt_br(m_cab.group(5))
    return {
        'id_fatura':                     id_fatura,
        'numero_fatura':                 numero_fatura,
        'arquivo_pdf':                   os.path.basename(pdf_path),
        'fornecedor':                    FORNECEDOR,
        'id_uc':                         id_uc,
        'data_emissao':                  fmt_br(emissao),
        'competencia':                   competencia,
        'data_vencimento':               fmt_br(venc),
        'valor_total_r$':                pf(valor),
        'numero_nf':                     numero_nf,
        'serie_nf':                      serie_nf,
        'cfop':                          '5258',
        'chave_acesso_nfe':              chave,
        'protocolo_autorizacao':         protocolo,
        'data_hora_protocolo':           data_hora_protocolo,
        'classificacao_tarifaria':       classif,
        'tipo_fornecimento':             tipo_forn,
        'tensao_nominal_v':              tensao_nom,
        'tensao_min_v':                  tensao_min,
        'tensao_max_v':                  tensao_max,
        'demanda_contratada_kw':         demanda_cont,
        'demanda_geracao_contratada_kw': demanda_ger_cont,
        'perdas_transformacao_pct':      perdas,
        'scee_geracao_ciclo':            scee_ciclo,
        'scee_saldo_kwh_total':          scee_tot,
        'scee_saldo_kwh_P':              scee_p,
        'scee_saldo_kwh_FP':             scee_fp,
        'scee_saldo_kwh_HR':             scee_hr,
        'data_leitura_anterior':         fmt_br(m_leit.group(1)) if m_leit else None,
        'data_leitura_atual':            fmt_br(m_leit.group(2)) if m_leit else None,
        'numero_dias_leitura':           numero_dias_leit,
        'data_proxima_leitura':          data_prox_leit,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 2. CLIENTE
# ──────────────────────────────────────────────────────────────────────────────
UFS = (r'AC|AL|AM|AP|BA|CE|DF|ES|GO|MA|MG|MS|MT|PA|PB|PE|PI|PR|RJ|RN|RO|RR|RS|'
       r'SC|SE|SP|TO')


def _parse_cep_bloco(bloco):
    m = re.search(
        rf'CEP:\s*(\d{{8}})\s+([A-ZÀ-ÿ][A-ZÀ-ÿ\s]+?)\s+({UFS})\s+BRASIL',
        bloco, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2).strip(), m.group(3).upper()
    m2 = re.search(
        rf'(?:Segunda via\s+)?([A-ZÀ-ÿ][A-ZÀ-ÿ\s]+?)\s+({UFS})\s+BRASIL',
        bloco)
    if m2:
        return None, m2.group(1).strip(), m2.group(2).upper()
    return None, None, None


def extrair_cliente(texto):
    id_uc = _extrair_id_uc(texto)
    razao = get(r'\n([A-ZÇÃÁÉÍÓÚÊÔÂ][A-ZÇÃÁÉÍÓÚÊÔÂ ]+?)\s*\nCNPJ/CPF:', texto)
    if not razao:
        # layout antigo: razão social e CNPJ na MESMA linha (canhoto da fatura)
        razao = get(r'\n([A-ZÇÃÁÉÍÓÚÊÔÂ][A-ZÇÃÁÉÍÓÚÊÔÂ .]+?)\s+CNPJ/CPF:', texto)
    cnpj = get(r'CNPJ/CPF:\s*([\d./-]+)', texto)

    cep = municipio = uf = None
    bloco_end = get(r'ENDERE[ÇC]O DE ENTREGA:[^\n]*\n((?:[^\n]+\n){2,5})', texto)
    if bloco_end:
        cep, municipio, uf = _parse_cep_bloco(bloco_end)
    if not cep and not municipio:
        bloco_cnpj = get(r'CNPJ/CPF:[^\n]+\n(.+?)PERDAS DE TRANSFORMA', texto,
                         flags=re.IGNORECASE | re.DOTALL)
        if bloco_cnpj:
            cep, municipio, uf = _parse_cep_bloco(bloco_cnpj)
    if not cep and not municipio:
        # layout antigo: sem os blocos-âncora; o 1º 'CEP: … <município> <UF> BRASIL'
        # do texto é o endereço de entrega.
        cep, municipio, uf = _parse_cep_bloco(texto)

    return {
        'id_uc': id_uc, 'razao_social': razao, 'cnpj': cnpj,
        'cep': cep, 'municipio': municipio, 'uf': uf,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 3. ITENS DA FATURA
# ──────────────────────────────────────────────────────────────────────────────
_FIN_KNOWN = [
    ('IR LEI 9430(-)',                     r'IR LEI 9430\(-\)\s*(-?[\d,.]+)'),
    ('CSLL LEI 9430(-)',                   r'CSLL[^\n]*?LEI 9430\(-\)\s*(-?[\d,.]+)'),
    ('COFINS LEI 9430(-)',                 r'COFINS\s*(?:\([^\)]+\))?\s*LEI 9430\(-\)\s*(-?[\d,.]+)'),
    ('PIS/PASEP LEI 9430(-)',              r'PIS/PASEP\s*(?:\([^\)]+\))?\s*LEI 9430\(-\)\s*(-?[\d,.]+)'),
    ('CONTRIB. ILUM. PÚBLICA - MUNICIPAL', r'CONTRIB\.\s*ILUM\.\s*P[ÚU]BLICA\s*-\s*MUNICIPAL\s+(-?[\d,.]+)'),
    ('VALOR ACUM. PROXIMO MES',            r'VALOR ACUM\.\s*PROXIMO MES\s+(-?[\d,.]+)'),
    ('VALOR ACUM. MES PASSADO',            r'VALOR ACUM\.\s*M[ÊE]S PASSADO[^\d]*\d{1,2}/\d{4}\s+(-?[\d,.]+)'),
]

_FIN_TERM = re.compile(
    r'^\s*(TOTAL\b'
    r'|Cliente poder'
    r'|Nota fiscal emitida'
    r'|A EQUATORIAL'
    r'|EQUATORIAL GOIAS'
    r'|TRIBUNAL DE JUSTICA'
    r'|FATURA PERTENCENTE'
    r'|Aproveite'
    r'|Consulte'
    r'|https?:'
    r'|CEP:'
    r'|RODOVIA\b|RUA\b|AVENIDA\b|AV\.|QUADRA\b|ZONA RURAL|PRA[ÇC]A\b)',
    re.IGNORECASE)
_FIN_SKIP = re.compile(
    r'^\s*(M[ÊE]S\s*/\s*ANO\b|MES\s*/\s*ANO\b|TIPOS DE\b|CONSUMO FATURADO)',
    re.IGNORECASE)
_FIN_MED = re.compile(
    r'^(ENERGIA ATIVA|ENERGIA GERA|DEMANDA|UFER|DMCR)\b.*\b'
    r'(PONTA|FORA PONTA|RESERVADO|[ÚU]NICO|INTERMEDI)', re.IGNORECASE)
_FIN_MEDIDOR = re.compile(r'\b\d{7,}-\d\b')
_FIN_PREF_KNOWN = re.compile(
    r'^(IR LEI 9430|CONTRIB\.\s*ILUM|COFINS\b|PIS/PASEP\b|PIS\b|CSLL\b|ICMS\b'
    r'|VALOR ACUM\.\s*M[ÊE]S PASSADO|VALOR ACUM\.\s*PROXIMO)', re.IGNORECASE)
_FIN_HIST = re.compile(
    r'\s+\d+\s+(LIDA|M[ÉE]DIA|M[ÍI]NIMO|ESTIMADA|LEITURA)\b.*$', re.IGNORECASE)
# Créditos/devoluções que às vezes VAZAM para fora da seção ITENS FINANCEIROS
# (ex.: linha 'DEVOLUÇÃO DOBRO -11,11' no meio do bloco de impostos). Linha
# estrita nome+valor; dedup por (nome, valor) contra o que já foi capturado.
_FIN_LEAK = re.compile(
    r'^((?:DEV\.|DEVOLU[ÇC][ÃA]O|CR[ÉE]DITO DE CONSUMO|JUROS DEV\.|ATUAL\. MONET)'
    r'[A-ZÀ-ÿa-z ./()\-]*(?:\d{1,2}/\d{4})?)\s+(-?\d[\d.]*,\d{2})\s*$',
    re.IGNORECASE | re.MULTILINE)


# ── Layout ANTIGO (DANF3E Enel/Equatorial, 2022 até ~mai/2023) ────────────────
# Não existem os marcadores "FORNECIMENTO"/"ITENS FINANCEIROS"; a tabela
# "Itens da Fatura" fica LADO A LADO com a tabela de medição e o pdfplumber
# mescla as duas na mesma linha (às vezes intercalando caractere a caractere).
# Item completo: nome + unidade (kWh/kW/kVArh, minúsculas — distingue da
# grandeza "KWH" da medição) + 8 colunas numéricas. O nome NÃO admite dígitos,
# para não engolir os números da medição que vêm antes na linha.
_ANT_ITEM = re.compile(
    r'([A-ZÀ-Þ(][A-Za-zÀ-ÿ .,/()\-]*?(?:\d{1,2}/\d{1,2})?)\s+(kWh|kW|kVArh|kVar)\s+'
    r'(-?[\d.,]+)\s+(-?[\d.,]+)\s+(-?[\d.,]+)\s+(-?[\d.,]+)\s+(-?[\d.,]+)\s+'
    r'([\d.,]+)%\s+(-?[\d.,]+)\s+(-?[\d.,]+)')
# Itens só-valor (CIP, verificação de tensão, juros…): nome + 1º número com 2
# decimais; tolera no fim números residuais da coluna vizinha e/ou um imposto
# mesclado na mesma linha ("… 15,88 COFINS 83,82 5,8225% …"). O nome admite
# tokens de data/parcela ("CRÉDITO DE CONSUMO - 09/2022", "CIP RETROATIVA-
# PARCELADA 1/3", "PARC. DEBITO-PRC - 214/2026 - 1/4"), mas não outros dígitos
# (para não engolir os números da tabela de medição mesclada na mesma linha).
_ANT_FIN_NOME = r'[A-ZÀ-Þ][A-Za-zÀ-ÿ .,/()\-]{2,}?(?:\d{1,6}/\d{1,4}[A-Za-zÀ-ÿ .,/()\-]*?)*'
_ANT_FIN = re.compile(
    rf'({_ANT_FIN_NOME})\s+(-?\d[\d.]*,\d{{2}})(?:\s+-?[\d.,]+%?)*'
    r'(?:\s+(?:PIS(?:/PASEP)?|COFINS|ICMS|CSLL)\b.*)?\s*$')
# Financeiro COM quantidade e preço unitário (6 decimais) além do valor
# ("RELIGAÇÃO NORMAL DISJUNTOR 1,00 11,364000 11,36 …"). Sem este caso, o
# captador só-valor pegava a quantidade (1,00) como valor_r$.
_ANT_FIN_QTD = re.compile(
    rf'({_ANT_FIN_NOME})\s+(\d[\d.]*,\d{{2}})\s+(\d[\d.]*,\d{{6}})\s+(-?\d[\d.]*,\d{{2}})\b')
_ANT_FIN_EXCL = re.compile(r'^\s*(PIS|COFINS|ICMS|CSLL|TOTAL|M[ÊE]S|MES)\b', re.IGNORECASE)

# Quando o nome do item quebra em duas linhas no PDF, o pdfplumber intercala os
# caracteres das duas linhas ("E TE NERGIA … - PARC." = "ENERGIA … - PARC. TE").
# O nome embaralhado tem EXATAMENTE os mesmos caracteres do nome real, então a
# assinatura (multiconjunto de caracteres, sem espaços) identifica o canônico.
# Quando a linha vizinha da MEDIÇÃO também se intercala ("E TE N E - R KW GI H A
# ATIVA…" carrega o "- KWH" da grandeza), sobram caracteres estranhos e a
# assinatura exata falha; nesse caso vale a CONTENÇÃO: todos os caracteres do
# canônico presentes no embaralhado (com sobra limitada) identificam o item.
_ITENS_CANONICOS_ANTIGO = [
    'ENERGIA ATIVA FORNECIDA FP - PARC. TE',
    'ENERGIA ATIVA FORNECIDA HR - PARC. TE',
    'ENERGIA ATIVA FORNECIDA P - PARC. TE',
    'AD. BAND. VERMELHA EN. ATIVA FORN. FP - PARC. TE',
    'AD. BAND. VERMELHA EN. ATIVA FORN. HR - PARC. TE',
    'AD. BAND. VERMELHA EN. ATIVA FORN. P - PARC. TE',
    'AD. BAND. AMARELA EN. ATIVA FORN. FP - PARC. TE',
    'AD. BAND. AMARELA EN. ATIVA FORN. HR - PARC. TE',
    'AD. BAND. AMARELA EN. ATIVA FORN. P - PARC. TE',
    'AD. BAND. VERMELHA EN. ATIVA FORN. FP',
    'AD. BAND. VERMELHA EN. ATIVA FORN. HR',
    'AD. BAND. VERMELHA EN. ATIVA FORN. P',
    'AD. BAND. AMARELA EN. ATIVA FORN. FP',
    'AD. BAND. AMARELA EN. ATIVA FORN. HR',
    'AD. BAND. AMARELA EN. ATIVA FORN. P',
    'ENERGIA ATIVA FORNECIDA FP',
    'ENERGIA ATIVA FORNECIDA HR',
    'ENERGIA ATIVA FORNECIDA P',
    'UFER DEMONSTRATIVO FORA DE PONTA',
    'UFER DEMONSTRATIVO HORÁRIO RESERVADO',
    'UFER DEMONSTRATIVO PONTA',
]


def _assinatura(nome):
    return ''.join(sorted(nome.replace(' ', '')))


_CANON_POR_ASSINATURA = {_assinatura(n): n for n in _ITENS_CANONICOS_ANTIGO}
# mais longos primeiro: entre os que couberem, o mais específico vence
_CANONICOS_POR_TAMANHO = sorted(
    _ITENS_CANONICOS_ANTIGO, key=lambda n: -len(n.replace(' ', '')))


def _canonico_contido(nome):
    """Maior canônico cujos caracteres estão TODOS contidos no nome embaralhado
    (multiconjunto), desde que cubra a maior parte dele. None se nenhum servir.

    Só se aplica a nomes visivelmente intercalados (3+ letras isoladas), para
    nunca reescrever um nome LIMPO que apenas contenha um canônico (ex.:
    'ENERGIA ATIVA FORNECIDA FP - TE' contém 'ENERGIA ATIVA FORNECIDA FP',
    mas é outro item e deve ser preservado).
    """
    if len(re.findall(r'(?<![A-Za-zÀ-ÿ])[A-ZÀ-Þ](?![A-Za-zÀ-ÿ])', nome)) < 3:
        return None
    # O posto (FP/HR/P) costuma sobreviver legível no fim do nome ("… DA P -
    # PARC."). Quando presente, desempata candidatos: resíduos grandes (ex.
    # "FATOR DE POTÊNCIA ÚNICO" da medição) contêm letras que fazem o
    # multiconjunto aceitar o posto errado.
    m_hint = re.search(r'\b(FP|HR|P)\s*-\s*PARC|\b(FP|HR|P)\s*\.?\s*$', nome)
    posto_hint = (m_hint.group(1) or m_hint.group(2)) if m_hint else None
    from collections import Counter
    alvo = Counter(nome.replace(' ', ''))
    total = sum(alvo.values())
    for cand in _CANONICOS_POR_TAMANHO:
        if posto_hint:
            m_cand = re.search(r'\b(FP|HR|P)\b(?=(?:\s*-\s*PARC\. TE)?$)', cand)
            if m_cand and m_cand.group(1) != posto_hint:
                continue
        c = Counter(cand.replace(' ', ''))
        if sum(c.values()) * 2 >= total and not (c - alvo):
            return cand
    return None


def _limpar_nome_antigo(nome):
    nome = nome.strip()
    # rótulos antigos trazem a unidade colada ao nome ("CONSUMO FP - kWh")
    nome = re.sub(r'\s*-\s*k(?:Wh|W|VArh|Var)\s*$', '', nome).strip()
    nome = nome.upper()
    # linha da MEDIÇÃO mesclada antes do item ("ENERGIA GERAÇÃO - KWH
    # RESERVADO UFER FP"): remove grandeza+posto do começo do nome. Inclui
    # "FATOR DE POTÊNCIA ÚNICO": essa grandeza não tem colunas de leitura
    # (linha em branco na tabela de medição), então gruda inteira no nome
    # do item vizinho (ex.: "FATOR DE POTÊNCIA ÚNICO UFER HR" -> "UFER HR").
    nome = re.sub(
        r'^(?:(?:ENERGIA|DEMANDA)\s[A-ZÀ-Ü ÇÃ]*-\s*KWH?|UFER(?:\s+GERA[ÇC][ÃA]O)?|DMCR'
        r'|FATOR DE POT[ÊE]NCIA)\s+'
        r'(?:PONTA|FORA PONTA|RESERVADO|[ÚU]NICO|INTERMEDI[ÁA]RIO)\s+',
        '', nome).strip() or nome
    canon = _CANON_POR_ASSINATURA.get(_assinatura(nome))
    if not canon:
        canon = _canonico_contido(nome)
    return canon or nome


def _financeiro_de_linha(resto, id_fatura):
    """Item financeiro contido em `resto` (linha, ou sobra após o item de
    fornecimento). Devolve o dict do item ou None."""
    resto = _FIN_HIST.sub('', resto).strip()
    if not resto:
        return None
    mq = _ANT_FIN_QTD.search(resto)
    if mq and not _ANT_FIN_EXCL.match(mq.group(1)):
        val = pf(mq.group(4))
        m_unid = re.search(r'-?\s*(kWh|kW|kVArh|kVar)\s*$', mq.group(1).strip())
        if m_unid:
            # Fatura DESCRITIVA: item de fornecimento com só 4 colunas
            # ("CONSUMO - kWh 470,00 0,650560 305,76") — a unidade fica
            # colada ao nome. Sem isto, a quantidade virava valor_r$.
            nome = _limpar_nome_antigo(mq.group(1))
            if nome and val is not None:
                return {'id_fatura': id_fatura, 'item': nome,
                        'tipo': 'FORNECIMENTO', 'unidade': m_unid.group(1),
                        'quantidade': pf(mq.group(2)),
                        'preco_unitario_com_tributos_r$': pf(mq.group(3)),
                        'valor_r$': val, 'pis_cofins': None,
                        'base_calc_icms_r$': None, 'aliquota_icms_r$': None,
                        'icms': None, 'tarifa_unitaria_r$': None}
        nome = mq.group(1).strip().rstrip('-').strip().upper()
        if nome and val is not None:
            return {'id_fatura': id_fatura, 'item': nome,
                    'tipo': 'ITENS FINANCEIROS', 'unidade': None,
                    'quantidade': pf(mq.group(2)),
                    'preco_unitario_com_tributos_r$': pf(mq.group(3)),
                    'valor_r$': val, 'pis_cofins': None,
                    'base_calc_icms_r$': None, 'aliquota_icms_r$': None,
                    'icms': None, 'tarifa_unitaria_r$': None}
    mf = _ANT_FIN.search(resto)
    if mf and not _ANT_FIN_EXCL.match(mf.group(1)):
        nome = mf.group(1).strip().rstrip('-').strip().upper()
        val = pf(mf.group(2))
        if nome and val is not None:
            return {'id_fatura': id_fatura, 'item': nome,
                    'tipo': 'ITENS FINANCEIROS', 'unidade': None,
                    'quantidade': None,
                    'preco_unitario_com_tributos_r$': None,
                    'valor_r$': val, 'pis_cofins': None,
                    'base_calc_icms_r$': None, 'aliquota_icms_r$': None,
                    'icms': None, 'tarifa_unitaria_r$': None}
    return None


def _extrair_itens_layout_antigo(texto, id_fatura):
    itens = []
    for mwin in re.finditer(r'Itens da Fatura(.*?)(?:^\s*TOTAL\b|\Z)', texto,
                            re.DOTALL | re.MULTILINE | re.IGNORECASE):
        for linha in mwin.group(1).split('\n'):
            linha = linha.strip()
            if not linha:
                continue
            resto = linha
            m = _ANT_ITEM.search(linha)
            if m:
                itens.append({'id_fatura': id_fatura,
                              'item': _limpar_nome_antigo(m.group(1)),
                              'tipo': 'FORNECIMENTO', 'unidade': m.group(2),
                              'quantidade': pf(m.group(3)),
                              'preco_unitario_com_tributos_r$': pf(m.group(4)),
                              'valor_r$': pf(m.group(5)), 'pis_cofins': pf(m.group(6)),
                              'base_calc_icms_r$': pf(m.group(7)),
                              'aliquota_icms_r$': f"{m.group(8)}%",
                              'icms': pf(m.group(9)), 'tarifa_unitaria_r$': pf(m.group(10))})
                resto = linha[m.end():]
            fin = _financeiro_de_linha(resto, id_fatura)
            if fin:
                itens.append(fin)
    return itens


def extrair_itens_fatura(texto, id_fatura, id_uc=None):
    itens = []

    # Sem o marcador "ITENS FINANCEIROS" (e com "Itens da Fatura"), é o layout
    # antigo — parser próprio, exclusivo (evita capturas duplicadas).
    if (not re.search(r'ITENS FINANCEIROS', texto, re.IGNORECASE)
            and re.search(r'Itens da Fatura', texto, re.IGNORECASE)):
        itens = _extrair_itens_layout_antigo(texto, id_fatura)
        for it in itens:
            it['id_uc'] = id_uc
        return itens

    # Variante de jun–jul/2023 (transição Enel→Equatorial): existe o marcador
    # FORNECIMENTO mas NÃO o "ITENS FINANCEIROS"; a tabela termina no TOTAL.
    tem_marcador_fin = bool(re.search(r'ITENS FINANCEIROS', texto, re.IGNORECASE))
    if tem_marcador_fin:
        bloco = re.search(r'FORNECIMENTO[^\n]*\n(.+?)ITENS FINANCEIROS', texto,
                          re.DOTALL | re.IGNORECASE)
    else:
        bloco = re.search(r'FORNECIMENTO[^\n]*\n(.+?)^\s*TOTAL\b', texto,
                          re.DOTALL | re.IGNORECASE | re.MULTILINE)
    if bloco:
        for linha in bloco.group(1).split('\n'):
            linha = linha.strip()
            if not linha:
                continue
            linha = re.sub(r'\s+DEMANDA(?:\s+GERA[ÇC][ÃA]O)?\s*-\s*kW\s+\d+.*$', '',
                           linha, flags=re.IGNORECASE)
            linha = re.sub(r'\s+(COFINS|PIS/PASEP|ICMS)\s+[\d.,]+\s+[\d.,]+%?\s+[\d.,]+.*$',
                           '', linha, flags=re.IGNORECASE)
            linha = re.sub(r'\s+TIPOS DE.*$', '', linha, flags=re.IGNORECASE)
            linha = re.sub(r'\s+\d+\s+(LIDA|M[ÉE]DIA|M[ÍI]NIMO|ESTIMADA|LEITURA)\b.*$',
                           '', linha, flags=re.IGNORECASE)
            linha = re.sub(r'\s+[\d.,]+\s+\d{2}/\d{2}/\d{4}.*$', '', linha)
            linha = re.sub(r'\s+[\d.,]+\s+\d{4}/\d{2}.*$', '', linha)

            m = re.match(
                r'^(.+?)\s+(kWh|kVArh|kVar|kW)\s+'
                r'(-?[\d.,]+)\s+(-?[\d.,]+)\s+(-?[\d.,]+)\s+(-?[\d.,]+)\s+(-?[\d.,]+)\s+'
                r'([\d.,]+)%\s+(-?[\d.,]+)\s+(-?[\d.,]+)(?:\s+.*)?$', linha, re.IGNORECASE)
            if m:
                # linha da MEDIÇÃO mesclada antes do item ("ENERGIA GERAÇÃO -
                # KWH RESERVADO UFER FP kWh …"): remove grandeza+posto do nome
                # (mesmo caso de "FATOR DE POTÊNCIA ÚNICO" tratado em
                # _limpar_nome_antigo).
                nome_item = re.sub(
                    r'^(?:(?:ENERGIA|DEMANDA)\s[A-ZÀ-Ü ÇÃ]*-\s*KWH?|UFER(?:\s+GERA[ÇC][ÃA]O)?|DMCR'
                    r'|FATOR DE POT[ÊE]NCIA)\s+'
                    r'(?:PONTA|FORA PONTA|RESERVADO|[ÚU]NICO|INTERMEDI[ÁA]RIO)\s+',
                    '', m.group(1).strip().upper())
                itens.append({'id_fatura': id_fatura,
                              'item': nome_item, 'tipo': 'FORNECIMENTO',
                              'unidade': m.group(2),
                              'quantidade': pf(m.group(3)), 'preco_unitario_com_tributos_r$': pf(m.group(4)),
                              'valor_r$': pf(m.group(5)), 'pis_cofins': pf(m.group(6)),
                              'base_calc_icms_r$': pf(m.group(7)), 'aliquota_icms_r$': f"{m.group(8)}%",
                              'icms': pf(m.group(9)), 'tarifa_unitaria_r$': pf(m.group(10))})
                continue
            # DEMANDA ISENTO DE ICMS / DEMANDA EXCED. CONTRATADA…: às vezes a
            # alíquota vem como '0' (sem '%') e SEM a coluna de ICMS, restando
            # 7 valores: qtd, preço, valor, pis, base, alíquota, tarifa. Sem
            # este tratamento a tarifa recebia a base (ou o item era perdido).
            m_isento = re.match(
                r'^(DEMANDA[^\d]*?)\s+(kWh|kW|kVar)\s+'
                r'([\d.,]+)\s+([\d.,]+)\s+(-?[\d.,]+)\s+(-?[\d.,]+)\s+(-?[\d.,]+)\s+'
                r'([\d.,]+)%?\s+([\d.,]+)(?:\s+.*)?$', linha, re.IGNORECASE)
            if m_isento:
                itens.append({'id_fatura': id_fatura,
                              'item': m_isento.group(1).strip().upper(), 'tipo': 'FORNECIMENTO',
                              'unidade': m_isento.group(2),
                              'quantidade': pf(m_isento.group(3)),
                              'preco_unitario_com_tributos_r$': pf(m_isento.group(4)),
                              'valor_r$': pf(m_isento.group(5)), 'pis_cofins': pf(m_isento.group(6)),
                              'base_calc_icms_r$': pf(m_isento.group(7)),
                              'aliquota_icms_r$': f"{m_isento.group(8)}%",
                              'icms': None, 'tarifa_unitaria_r$': pf(m_isento.group(9))})
                continue
            m2 = re.match(
                r'^((?:DEMANDA|INJEÇÃO SCEE)[^\d]*?)\s+(kWh|kW|kVar)\s+'
                r'([\d.,]+)\s+([\d.,]+)\s+(-?[\d.,]+)\s+(-?[\d.,]+)\s+([\d.,]+)(?:\s+.*)?$',
                linha, re.IGNORECASE)
            if m2:
                itens.append({'id_fatura': id_fatura,
                              'item': m2.group(1).strip().upper(), 'tipo': 'FORNECIMENTO',
                              'unidade': m2.group(2),
                              'quantidade': pf(m2.group(3)), 'preco_unitario_com_tributos_r$': pf(m2.group(4)),
                              'valor_r$': pf(m2.group(5)), 'pis_cofins': pf(m2.group(6)),
                              'base_calc_icms_r$': None, 'aliquota_icms_r$': None,
                              'icms': None, 'tarifa_unitaria_r$': pf(m2.group(7))})
                continue
            # "BENEFÍCIO TARIFÁRIO BRUTO SCEE <valor>": item SEM unidade (só
            # nome + 1 valor) que aparece no FIM do bloco FORNECIMENTO, mesmo
            # quando existe a seção ITENS FINANCEIROS (então o fallback
            # genérico abaixo, exclusivo de `not tem_marcador_fin`, não
            # entraria em ação). Tem sempre uma linha irmã de sinal oposto em
            # ITENS FINANCEIROS ("BENEFÍCIO TARIFÁRIO LÍQUIDO SCEE").
            m_benef = re.match(
                r'^(BENEF[ÍI]CIO TARIF[ÁA]RIO\s+.+?)\s+(-?\d[\d.]*,\d{2})\s*$',
                linha, re.IGNORECASE)
            if m_benef:
                itens.append({'id_fatura': id_fatura,
                              'item': m_benef.group(1).strip().upper(), 'tipo': 'FORNECIMENTO',
                              'unidade': None, 'quantidade': None,
                              'preco_unitario_com_tributos_r$': None,
                              'valor_r$': pf(m_benef.group(2)), 'pis_cofins': None,
                              'base_calc_icms_r$': None, 'aliquota_icms_r$': None,
                              'icms': None, 'tarifa_unitaria_r$': None})
                continue
            if not tem_marcador_fin:
                # Sem a seção "ITENS FINANCEIROS", eventuais itens financeiros
                # (créditos, CIP retroativa…) ficam no MESMO bloco da tabela.
                if _FIN_SKIP.match(linha) or _FIN_PREF_KNOWN.match(linha):
                    continue
                fin = _financeiro_de_linha(linha, id_fatura)
                if fin and not _FIN_PREF_KNOWN.match(fin['item']):
                    itens.append(fin)

    for nome, pat in _FIN_KNOWN:
        m = re.search(pat, texto, re.IGNORECASE)
        if m:
            itens.append({'id_fatura': id_fatura, 'item': nome, 'tipo': 'ITENS FINANCEIROS',
                          'unidade': None, 'quantidade': None, 'preco_unitario_com_tributos_r$': None,
                          'valor_r$': pf(m.group(1)), 'pis_cofins': None, 'base_calc_icms_r$': None,
                          'aliquota_icms_r$': None, 'icms': None, 'tarifa_unitaria_r$': None})

    mfin = re.search(r'ITENS FINANCEIROS(.*)$', texto, re.DOTALL | re.IGNORECASE)
    if mfin:
        for raw in mfin.group(1).split('\n'):
            linha = raw.strip()
            if not linha:
                continue
            if _FIN_TERM.match(linha) or _FIN_MED.match(linha) or _FIN_MEDIDOR.search(linha):
                break
            if _FIN_SKIP.match(linha):
                continue
            linha = re.sub(r'\s+TIPOS DE.*$', '', linha, flags=re.IGNORECASE)
            linha = _FIN_HIST.sub('', linha)
            if not linha or _FIN_PREF_KNOWN.match(linha):
                continue
            if not re.match(r'^[A-Za-zÀ-ÿ]', linha):
                continue
            # Itens financeiros que TÊM quantidade (nome + qtd + preço + valor),
            # diferente da maioria (que só tem valor). Sem isto, o captador
            # genérico pegava a quantidade como valor_r$.
            mem = re.match(
                r'^(EMIS\.\s*SEGUNDA VIA|RELIGA[ÇC][ÃA]O PROGRAMADA|DESLIGAMENTO PROGRAMADO)'
                r'\s+([\d.,]+)\s+([\d.,]+)\s+(-?[\d.,]+)',
                linha, re.IGNORECASE)
            if mem:
                val_gen = pf(mem.group(4))
                if val_gen is None:
                    continue
                itens.append({'id_fatura': id_fatura, 'item': mem.group(1).strip().upper(),
                              'tipo': 'ITENS FINANCEIROS', 'unidade': None,
                              'quantidade': pf(mem.group(2)),
                              'preco_unitario_com_tributos_r$': pf(mem.group(3)),
                              'valor_r$': val_gen, 'pis_cofins': None, 'base_calc_icms_r$': None,
                              'aliquota_icms_r$': None, 'icms': None, 'tarifa_unitaria_r$': None})
                continue
            mtok = list(re.finditer(r'-?\d[\d.]*,\d{2}\b', linha))
            if not mtok:
                continue
            nome_gen = linha[:mtok[0].start()].strip().rstrip('-').strip().upper()
            val_gen = pf(mtok[0].group(0))
            if not nome_gen or val_gen is None or nome_gen.startswith('TOTAL'):
                continue
            itens.append({'id_fatura': id_fatura, 'item': nome_gen,
                          'tipo': 'ITENS FINANCEIROS', 'unidade': None, 'quantidade': None,
                          'preco_unitario_com_tributos_r$': None,
                          'valor_r$': val_gen, 'pis_cofins': None, 'base_calc_icms_r$': None,
                          'aliquota_icms_r$': None, 'icms': None, 'tarifa_unitaria_r$': None})

    # Créditos/devoluções que vazam para FORA da seção ITENS FINANCEIROS
    # (aparecem no meio do bloco de impostos). Só adiciona o que ainda não foi
    # capturado com o mesmo nome+valor (as vias repetidas caem no dedup).
    capturados = {(it['item'], it['valor_r$']) for it in itens}
    for m in _FIN_LEAK.finditer(texto):
        nome_leak = m.group(1).strip().rstrip('-').strip().upper()
        val_leak = pf(m.group(2))
        if val_leak is None or (nome_leak, val_leak) in capturados:
            continue
        capturados.add((nome_leak, val_leak))
        itens.append({'id_fatura': id_fatura, 'item': nome_leak,
                      'tipo': 'ITENS FINANCEIROS', 'unidade': None, 'quantidade': None,
                      'preco_unitario_com_tributos_r$': None,
                      'valor_r$': val_leak, 'pis_cofins': None, 'base_calc_icms_r$': None,
                      'aliquota_icms_r$': None, 'icms': None, 'tarifa_unitaria_r$': None})
    for it in itens:
        it['id_uc'] = id_uc
    return itens


# ──────────────────────────────────────────────────────────────────────────────
# 4. IMPOSTOS
# ──────────────────────────────────────────────────────────────────────────────
def extrair_impostos(texto, id_fatura):
    impostos = []
    for nome, pat in [
        ('PIS/PASEP', r'PIS/PASEP\s+([\d.,]+)\s+([\d.,]+)%\s+([\d.,]+)'),
        ('ICMS',      r'ICMS\s+([\d.,]+)\s+([\d.,]+)%\s+([\d.,]+)'),
        ('COFINS',    r'COFINS\s+([\d.,]+)\s+([\d.,]+)%\s+([\d.,]+)'),
    ]:
        m = re.search(pat, texto, re.IGNORECASE)
        if m:
            impostos.append({'id_fatura': id_fatura, 'Tributo': nome,
                             'Base (R$)': pf(m.group(1)), 'Aliquota (%)': f"{pf(m.group(2))}%",
                             'Valor (R$)': pf(m.group(3))})
        elif nome == 'ICMS':
            impostos.append({'id_fatura': id_fatura, 'Tributo': 'ICMS',
                             'Base (R$)': None, 'Aliquota (%)': '0%', 'Valor (R$)': 0.0})
    return impostos


# ──────────────────────────────────────────────────────────────────────────────
# 5. MEDIÇÃO
# ──────────────────────────────────────────────────────────────────────────────
def extrair_medicao(texto, id_fatura):
    medicao = []
    # mais longas primeiro; REATIVA e UFER GERAÇÃO só existem no layout antigo
    GRANDEZA = (r'(ENERGIA REATIVA GERA[ÇC][ÃA]O - KWH|ENERGIA REATIVA - KWH'
                r'|ENERGIA GERA[ÇC][ÃA]O - KWH|ENERGIA ATIVA - KWH'
                r'|DEMANDA GERA[ÇC][ÃA]O - KW|DEMANDA - KW'
                r'|UFER GERA[ÇC][ÃA]O|UFER|DMCR)')
    POSTO = r'(PONTA|FORA PONTA|RESERVADO|INTERMEDI[ÁA]RIO|[ÚU]NICO)'

    # A 2ª leitura é OPCIONAL: em algumas faturas a coluna "Leitura Anterior"
    # vem vazia no PDF (ex.: DEMANDA GERAÇÃO - KW / FORA PONTA), restando só um
    # número (a Leitura Atual). Sem isso, a linha era perdida.
    #
    # ESPAÇO HORIZONTAL (`H`), nunca `\s`: uma linha de medição ocupa UMA linha
    # do PDF. Com `\s+` (que casa '\n') uma linha TRUNCADA — o PDF não imprime
    # a leitura anterior nem o consumo — completava os grupos que faltavam com
    # os números da linha SEGUINTE, gravando o nº do medidor da linha de baixo
    # como 'Consumo kWh'. Ex. (2024078766455.pdf):
    #     2993839-2 ENERGIA ATIVA - KWH ÚNICO 763377 1,000000
    #     2993839-2 ENERGIA REATIVA - KWH ÚNICO 074647 1,000000
    # capturava Consumo kWh = 2993839. Restringindo a espaço horizontal, a
    # linha truncada simplesmente não casa (nenhuma linha inventada).
    H = r'[^\S\n]'
    pat_a = re.compile(
        rf'^{GRANDEZA}{H}+{POSTO}{H}+(\d+)(?:{H}+(\d+))?{H}+([\d.,]+){H}+([\d.,]+){H}+(\d+-?\d*)',
        re.IGNORECASE | re.MULTILINE)
    pat_b = re.compile(
        rf'^(\d+-?\d*){H}+{GRANDEZA}{H}+{POSTO}{H}+(\d+)(?:{H}+(\d+))?{H}+([\d.,]+){H}+([\d.,]+)',
        re.IGNORECASE | re.MULTILINE)
    # Linha TRUNCADA: o PDF imprime medidor, grandeza, posto, UMA leitura e a
    # constante, e acaba — a coluna de consumo não existe naquela linha. Ex.:
    #     10586992-9 ENERGIA ATIVA - KWH ÚNICO 80535 1,000000
    # Registra o que a fatura realmente traz (leitura atual, constante, medidor)
    # com 'Consumo kWh' vazio, em vez de descartar a linha inteira. O '$' torna
    # este padrão exclusivo das linhas truncadas: uma linha completa sempre tem
    # mais um número depois da constante e é capturada pelo pat_b.
    pat_c = re.compile(
        rf'^(\d+-?\d*){H}+{GRANDEZA}{H}+{POSTO}{H}+(\d+){H}+([\d.,]+){H}*$',
        re.IGNORECASE | re.MULTILINE)

    # Dedup APENAS de linhas completamente idênticas: uma mesma grandeza/posto
    # pode aparecer mais de uma vez no mês (variações de leitura) e todas devem
    # ser mantidas; só descartamos capturas duplicadas idênticas (pat_a/pat_b).
    seen = set()
    for m in pat_a.finditer(texto):
        # Com dois inteiros: (anterior, atual). Com apenas um: anterior ausente
        # no PDF -> o número é a Leitura Atual.
        if m.group(4):
            leit_ant = int(m.group(3))
            leit_at = int(m.group(4))
        else:
            leit_ant = None
            leit_at = int(m.group(3))
        gr, po = m.group(1).upper(), m.group(2).upper()
        const, consumo, medidor = pf(m.group(5)), pf(m.group(6)), m.group(7)
        key = (gr, po, leit_ant, leit_at, const, consumo, medidor)
        if key in seen:
            continue
        seen.add(key)
        medicao.append({'id_fatura': id_fatura,
                        'Grandezas': gr, 'Postos horarios': po,
                        'Leitura Anterior': leit_ant, 'Leitura Atual': leit_at,
                        'Const Medidor': const, 'Consumo kWh': consumo,
                        'Medidor': medidor})
    for m in pat_b.finditer(texto):
        # Mesma regra do pat_a: o grupo OPCIONAL é o SEGUNDO número (group 5).
        # Com um só número, ele é a Leitura Atual e a Anterior fica vazia —
        # antes ambas recebiam o mesmo valor, produzindo linhas com
        # 'Leitura Anterior == Leitura Atual' e consumo > 0.
        if m.group(5):
            leit_ant = int(m.group(4))
            leit_at = int(m.group(5))
        else:
            leit_ant = None
            leit_at = int(m.group(4))
        gr, po = m.group(2).upper(), m.group(3).upper()
        const, consumo, medidor = pf(m.group(6)), pf(m.group(7)), m.group(1)
        key = (gr, po, leit_ant, leit_at, const, consumo, medidor)
        if key in seen:
            continue
        seen.add(key)
        medicao.append({'id_fatura': id_fatura,
                        'Grandezas': gr, 'Postos horarios': po,
                        'Leitura Anterior': leit_ant, 'Leitura Atual': leit_at,
                        'Const Medidor': const, 'Consumo kWh': consumo,
                        'Medidor': medidor})
    for m in pat_c.finditer(texto):
        gr, po = m.group(2).upper(), m.group(3).upper()
        medidor = m.group(1)
        # Só entra se aquela grandeza/posto/medidor ainda não veio de uma linha
        # completa (evita duplicar quando a fatura repete o bloco de medição).
        if any(l['Grandezas'] == gr and l['Postos horarios'] == po
               and l['Medidor'] == medidor for l in medicao):
            continue
        medicao.append({'id_fatura': id_fatura,
                        'Grandezas': gr, 'Postos horarios': po,
                        'Leitura Anterior': None, 'Leitura Atual': int(m.group(4)),
                        'Const Medidor': pf(m.group(5)), 'Consumo kWh': None,
                        'Medidor': medidor})
    return medicao


# ──────────────────────────────────────────────────────────────────────────────
# API pública
# ──────────────────────────────────────────────────────────────────────────────
def carimbar_id_uc_competencia(resultado, id_uc, competencia):
    """
    Aplica id_uc e competencia a TODAS as abas (competencia exceto em
    'unidade_consumidora'), para que todas as linhas de uma fatura tenham os
    mesmos valores.
    """
    cli = resultado.get('unidade_consumidora')
    if isinstance(cli, dict):
        cli['id_uc'] = id_uc
    fat = resultado.get('fatura')
    if isinstance(fat, dict):
        fat['id_uc'] = id_uc
    for aba in ('itens_fatura', 'impostos', 'medicao'):
        for row in resultado.get(aba, []):
            row['id_uc'] = id_uc
            row['competencia'] = competencia


def _montar_resultado(txt, pdf_path, numero_forcado=None):
    fat = extrair_fatura(txt, pdf_path, numero_forcado)
    cli = extrair_cliente(txt)
    fid = fat['id_fatura']
    # id_uc final: quando ausente, usa 'NULO_<id_fatura>' (não deixa vazio).
    id_uc = fat.get('id_uc') or f"NULO_{fid}"
    resultado = {
        'fatura':               fat,
        'unidade_consumidora':  cli,
        'itens_fatura': extrair_itens_fatura(txt, fid, id_uc),
        'impostos':     extrair_impostos(txt, fid),
        'medicao':      extrair_medicao(txt, fid),
    }
    carimbar_id_uc_competencia(resultado, id_uc, fat.get('competencia'))
    from . import correcoes
    correcoes.aplicar(resultado)
    return resultado


def processar_pdf(pdf_path):
    """Processa um único PDF da Equatorial e devolve as linhas de cada aba."""
    return _montar_resultado(extrair_texto(pdf_path), pdf_path)


# Número de fatura (13 dígitos iniciando pelo ano) fora de códigos maiores.
_RE_NUM_13 = re.compile(r'(?<![\d.])(20\d{11})(?![\d.])')
_RE_INICIO_DANF3E = re.compile(r'DOCUMENTO AUXILIAR DA NOTA FISCAL DE ENERGIA',
                               re.IGNORECASE)


def processar_pdf_multi(pdf_path):
    """
    Processa um PDF que pode conter VÁRIAS faturas mescladas (ex.: arquivos
    unidos com PDFsam). Devolve uma lista de resultados — um por fatura.

    Detecção: 2+ números de fatura distintos no texto. A divisão é pela âncora
    'DOCUMENTO AUXILIAR DA NOTA FISCAL…' (início de cada DANF3E); segmentos sem
    número próprio (página do caixa/canhoto) são anexados ao segmento anterior.
    Vias repetidas da mesma fatura são deduplicadas (fica o segmento maior).
    """
    txt = extrair_texto(pdf_path)
    numeros = set(_RE_NUM_13.findall(txt))
    if len(numeros) <= 1:
        return [_montar_resultado(txt, pdf_path)]
    inicios = [m.start() for m in _RE_INICIO_DANF3E.finditer(txt)]
    if len(inicios) <= 1:
        return [_montar_resultado(txt, pdf_path)]

    cortes = inicios + [len(txt)]
    segmentos: list[tuple[str, str]] = []          # (numero_fatura, texto)
    for a, b in zip(cortes, cortes[1:]):
        seg = txt[a:b]
        nums = _RE_NUM_13.findall(seg)
        if nums:
            # o número do canhoto fica ao FIM do segmento (o último é o da fatura)
            segmentos.append((nums[-1], seg))
        elif segmentos:
            n, s = segmentos[-1]
            segmentos[-1] = (n, s + seg)
    por_numero: dict[str, str] = {}
    for n, seg in segmentos:
        if n not in por_numero or len(seg) > len(por_numero[n]):
            por_numero[n] = seg
    return [_montar_resultado(seg, pdf_path, numero_forcado=n)
            for n, seg in por_numero.items()]
