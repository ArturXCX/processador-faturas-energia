"""
Colunas DERIVADAS/agregadas, recalculadas do zero sobre o conjunto completo de
faturas (tanto no processamento quanto na concatenação):

  - unidade_consumidora.primeira_competencia / ultima_competencia e
    primeira_fatura / ultima_fatura: a competência mais antiga/mais recente
    (e o id_fatura correspondente) por id_uc_canonico.
  - id_uc_sem_format / id_uc_atual_medidor / id_uc_atual_medidor_sem_format:
    ao lado de id_uc, em TODAS as abas.
  - id_uc_canonico e o cadastro do MAPA DE UCs importado: ver
    `_enriquecer_mapa_uc` e core/dicionario_uc.py. Sem mapa carregado nenhuma
    das duas coisas existe.
  - medidor: em 'fatura' e 'fatura_resumida', o medidor (moda) da fatura.
  - item_normalizado: em itens_fatura.
  - a aba 'tarifas' inteira: ver `_derivar_tarifas`.

`aplicar(dfs)` opera sobre DataFrames CANÔNICOS. `aplicar_concat(res_dfs, meta)`
converte o resultado (nomes exibidos) para canônico, recalcula e grava de volta.
"""
from __future__ import annotations

import re

import pandas as pd

from . import concat as _concat
from . import dicionario_uc
from . import equivalencias
from . import schema

# Colunas produzidas por este módulo (para o writeback na concatenação).
COLUNAS_DERIVADAS = ["primeira_competencia", "ultima_competencia",
                     "primeira_fatura", "ultima_fatura",
                     "id_uc_sem_format", "id_uc_atual_medidor",
                     "id_uc_atual_medidor_sem_format", "id_uc_atual", "medidor",
                     "item_normalizado", "tipo_fornecimento",
                     "id_uc_canonico",
                     # as colunas do mapa de UCs são dinâmicas (dependem do que
                     # o usuário importou), por isso entram em tempo de execução
                     *dicionario_uc.COLUNAS_TEMPLATE]


def aplicar(dfs: dict) -> dict:
    """Preenche as colunas derivadas nos DataFrames canônicos (in place)."""
    _calcular(dfs)
    _dedup_unidade_consumidora(dfs)
    return dfs


def _calcular(dfs: dict) -> None:
    # A ORDEM importa (não é só anexar linhas novas no fim):
    _colunas_medidor(dfs)            # (1) antes do dicionário: é o fallback de
                                     #     id_uc_canonico (id_uc_atual_medidor)
    _enriquecer_mapa_uc(dfs)         # (2) id_uc_canonico + cadastro do mapa de UCs
    _extremos_por_uc(dfs)            # (3) depois de (2): agrupa por id_uc_canonico
    _item_normalizado(dfs)           # (4)
    _derivar_tarifas(dfs)            # (5) depois de (4): tarifas leva item_normalizado
    _tipo_fornecimento_upper(dfs)    # (6)
    _remover_colunas_medidor(dfs)    # (7) depois de tudo que as usa
    _derivar_validacao(dfs)          # (8) cruza fatura × mapa × itens × medição
    _reordenar_canonico(dfs)         # (9) por último, sempre


# Abas recalculadas do ZERO sobre o conjunto completo (não passam pelo dedup
# incremental da concatenação): reinstaladas inteiras em `aplicar_concat`.
ABAS_RECALCULADAS = ("tarifas", "validacao")


def _extremos_por_uc(dfs: dict) -> None:
    """
    primeira/ultima competencia e fatura, por id_uc_canonico (extremos
    cronológicos). Usa a chave canônica em vez do id_uc bruto para não
    fragmentar o histórico de uma UC que mudou de formato de id_uc no meio do
    tempo — que apareceria como "duas UCs", cada uma com um intervalo de
    competências pela metade.
    """
    fat = dfs.get("fatura")
    cli = dfs.get("unidade_consumidora")
    if fat is None or cli is None or getattr(fat, "empty", True) or getattr(cli, "empty", True):
        return
    if not {"id_uc_canonico", "competencia", "id_fatura"}.issubset(fat.columns):
        return
    if "id_uc_canonico" not in cli.columns:
        return
    tmp = fat[["id_uc_canonico", "competencia", "id_fatura"]].copy()
    tmp = tmp[tmp["id_uc_canonico"].notna()]
    # competencia no formato AAAA-MM ordena lexicograficamente = cronologicamente.
    tmp["_k"] = tmp["competencia"].astype(str)
    tmp = tmp.sort_values("_k")
    grp = tmp.groupby("id_uc_canonico", sort=False)
    primeira = grp.head(1)
    ultima = grp.tail(1)
    cli["primeira_competencia"] = cli["id_uc_canonico"].map(
        dict(zip(primeira["id_uc_canonico"], primeira["competencia"])))
    cli["ultima_competencia"] = cli["id_uc_canonico"].map(
        dict(zip(ultima["id_uc_canonico"], ultima["competencia"])))
    cli["primeira_fatura"] = cli["id_uc_canonico"].map(
        dict(zip(primeira["id_uc_canonico"], primeira["id_fatura"])))
    cli["ultima_fatura"] = cli["id_uc_canonico"].map(
        dict(zip(ultima["id_uc_canonico"], ultima["id_fatura"])))


def _moda(serie: pd.Series):
    s = serie.dropna().astype(str)
    if s.empty:
        return None
    md = s.mode()
    return md.iat[0] if not md.empty else s.iat[0]


def _sem_formatacao(v):
    """Valor de id_uc/id_uc_atual_medidor sem ponto ou hífen."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return v
    return re.sub(r'[.\-]', '', str(v))


def _colunas_medidor(dfs: dict) -> None:
    """
    id_uc_atual_medidor: por medidor, o id_uc mais recente (por competência) que
    NÃO começa com 'NULO_'. Cada linha recebe o valor do seu medidor (medição:
    coluna Medidor; demais abas: via id_fatura; unidade_consumidora: via id_uc).
    Sem medidor conhecido, mantém o próprio id_uc.

    Colunas gravadas ao lado de id_uc dependem da aba:
      - 'unidade_consumidora': id_uc_sem_format, id_uc_atual_medidor e
        id_uc_atual_medidor_sem_format (as três completas).
      - demais abas: apenas 'id_uc_atual' (= id_uc_atual_medidor sem ponto/hífen).
    E, só em 'fatura'/'fatura_resumida': a coluna 'medidor' (moda do medidor
    daquela fatura, vinda da aba medicao).
    """
    med = dfs.get("medicao")
    mapa_med_uc: dict[str, str] = {}
    mapa_fat_med: dict = {}
    mapa_uc_med: dict = {}
    if med is not None and not med.empty and \
            {"Medidor", "id_uc", "competencia"}.issubset(med.columns):
        t = med[["Medidor", "id_uc", "competencia", "id_fatura"]].copy() \
            if "id_fatura" in med.columns else med[["Medidor", "id_uc", "competencia"]].copy()
        t = t[t["Medidor"].notna()]
        nn = t[t["id_uc"].notna() & ~t["id_uc"].astype(str).str.startswith("NULO_")].copy()
        if not nn.empty:
            nn["_k"] = nn["competencia"].astype(str)
            ult = nn.sort_values("_k").groupby(nn["Medidor"].astype(str), sort=False).tail(1)
            mapa_med_uc = dict(zip(ult["Medidor"].astype(str), ult["id_uc"]))
        if "id_fatura" in t.columns:
            mapa_fat_med = t.groupby("id_fatura")["Medidor"].agg(_moda).to_dict()
        if "id_uc" in t.columns:
            mapa_uc_med = t.groupby("id_uc")["Medidor"].agg(_moda).to_dict()

    for aba, df in dfs.items():
        if df is None or df.empty or "id_uc" not in df.columns:
            continue
        if "Medidor" in df.columns:
            medidor = df["Medidor"].astype("object")
            if "id_fatura" in df.columns:
                medidor = medidor.where(medidor.notna(), df["id_fatura"].map(mapa_fat_med))
        elif "id_fatura" in df.columns:
            medidor = df["id_fatura"].map(mapa_fat_med)
        else:                                   # unidade_consumidora
            medidor = df["id_uc"].map(mapa_uc_med)
        ucatual = medidor.map(lambda m: mapa_med_uc.get(str(m))
                              if (m is not None and pd.notna(m)) else None)
        id_uc_atual_medidor = ucatual.where(ucatual.notna(), df["id_uc"])
        if aba == "unidade_consumidora":
            df["id_uc_atual_medidor"] = id_uc_atual_medidor
            df["id_uc_sem_format"] = df["id_uc"].map(_sem_formatacao)
            df["id_uc_atual_medidor_sem_format"] = id_uc_atual_medidor.map(_sem_formatacao)
        else:
            df["id_uc_atual"] = id_uc_atual_medidor.map(_sem_formatacao)

    for aba in ("fatura", "fatura_resumida"):
        df = dfs.get(aba)
        if df is not None and not df.empty and "id_fatura" in df.columns:
            df["medidor"] = df["id_fatura"].map(mapa_fat_med)


def _enriquecer_mapa_uc(dfs: dict) -> None:
    """
    Aplica o MAPA DE UCs importado (core/dicionario_uc.py) sobre as abas.

      - Em TODAS as abas com 'id_uc': grava 'id_uc_canonico' — a UC canônica do
        mapa. Quando o mapa não conhece a UC, cai para o valor inferido pelo
        medidor (se a identificação por medidor estiver ligada).
      - APENAS em 'unidade_consumidora': as colunas de cadastro que o mapa
        realmente tem. Item do template que não foi mapeado na importação não
        vira coluna; nas outras abas o cadastro ficaria repetido por linha.

    SEM MAPA CARREGADO nada disso acontece: nenhuma coluna de cadastro e, em
    aba nenhuma, 'id_uc_canonico'.

    Precisa rodar DEPOIS de `_colunas_medidor` (usa suas colunas de fallback).
    """
    if not dicionario_uc.ativo():
        return

    colunas = dicionario_uc.colunas_ativas()
    usar_medidor = dicionario_uc.usar_medidor()
    for aba, df in dfs.items():
        if df is None or df.empty or "id_uc" not in df.columns:
            continue
        # Consulta o mapa uma vez por id_uc DISTINTO, não por linha: são
        # centenas de UCs para dezenas de milhares de linhas em
        # itens_fatura/medicao. Sem isso, o pós-processamento de um lote grande
        # (10 mil faturas) levava minutos.
        distintos = list(df["id_uc"].unique())
        canonico = {v: dicionario_uc.id_canonico(v) for v in distintos}
        serie = df["id_uc"].map(canonico)

        if aba == "unidade_consumidora":
            campos = {v: dicionario_uc.campos_unidade_consumidora(v) for v in distintos}
            for col in colunas:
                df[col] = df["id_uc"].map(
                    {k: (c.get(col) if c else None) for k, c in campos.items()})
            fallback = df.get("id_uc_atual_medidor_sem_format") if usar_medidor else None
        else:
            fallback = df.get("id_uc_atual") if usar_medidor else None

        if fallback is None:
            df["id_uc_canonico"] = serie
        else:
            df["id_uc_canonico"] = serie.where(serie.notna(), fallback)


def _remover_colunas_medidor(dfs: dict) -> None:
    """
    Tira as colunas de identificação por MEDIDOR quando o usuário desligou essa
    identificação (só possível com mapa carregado — sem mapa, o medidor é a
    única identificação que existe).

    São três, e todas carregam o mesmo dado: 'id_uc_atual_medidor' e
    'id_uc_atual_medidor_sem_format' em `unidade_consumidora`, e 'id_uc_atual'
    nas demais abas — manter esta última deixaria o dado do medidor na planilha
    sob outro nome.
    """
    if dicionario_uc.usar_medidor():
        return
    alvo = ("id_uc_atual_medidor", "id_uc_atual_medidor_sem_format", "id_uc_atual")
    for aba, df in dfs.items():
        if df is None or getattr(df, "empty", True):
            continue
        sobrando = [c for c in alvo if c in df.columns]
        if sobrando:
            dfs[aba] = df.drop(columns=sobrando)


def _item_normalizado(dfs: dict) -> None:
    itf = dfs.get("itens_fatura")
    if itf is not None and not itf.empty and "item" in itf.columns:
        equivalencias.aplicar(itf, "item", "item_normalizado")


def _derivar_tarifas(dfs: dict) -> None:
    """
    Aba 'tarifas': tabela de REFERÊNCIA — 1 linha por (fornecedor, item,
    tarifa_unitaria_r$), na competência em que essa combinação apareceu pela
    PRIMEIRA vez. Nomes de item mudam quando a distribuidora reformula a fatura,
    mas a tarifa numérica por trás costuma ser estável dentro do mesmo
    enquadramento — é essa linha do tempo que a aba guarda.

    Ficam de fora:
      - bandeira tarifária (item contém 'BAND'): é proporcional aos dias de
        vigência dentro do ciclo de leitura de CADA fatura, então não é uma
        propriedade estável do item da forma que esta aba tenta capturar;
      - linhas sem tarifa_unitaria_r$: elimina inteiramente os itens
        financeiros, que não têm tarifa vinculada à resolução homologatória.

    'fornecedor' entra na chave de dedup porque CHESP e Equatorial chegam a
    coincidir no valor numérico da tarifa de DEMANDA em dezembro (as resoluções
    homologatórias saem em meses diferentes, mas o faturamento das duas só
    estabiliza em dezembro) — sem ele, duas distribuidoras virariam uma linha só.

    Recalculada do ZERO a cada processamento/concatenação (mesmo padrão de
    'unidade_consumidora'): a regra "mantém a mais antiga" só fecha olhando o
    conjunto completo, e um backfill de faturas antigas pode deslocar qual linha
    é a mais antiga de um grupo.
    """
    itf = dfs.get("itens_fatura")
    fat = dfs.get("fatura")
    cols_saida = schema.all_canonical("tarifas")
    if itf is None or fat is None or getattr(itf, "empty", True) or getattr(fat, "empty", True):
        dfs["tarifas"] = pd.DataFrame(columns=cols_saida)
        return
    if not {"id_fatura", "fornecedor"}.issubset(fat.columns) or "id_fatura" not in itf.columns:
        dfs["tarifas"] = pd.DataFrame(columns=cols_saida)
        return

    t = itf.copy()
    t["fornecedor"] = t["id_fatura"].map(dict(zip(fat["id_fatura"], fat["fornecedor"])))

    base_cols = ["fornecedor", "competencia", "item", "tipo", "unidade",
                 "preco_unitario_com_tributos_r$", "tarifa_unitaria_r$",
                 "item_normalizado"]
    if not set(base_cols).issubset(t.columns):
        dfs["tarifas"] = pd.DataFrame(columns=cols_saida)
        return

    base = t[base_cols].drop_duplicates()
    sem_vazio = base[base["tarifa_unitaria_r$"].notna()]
    sem_bandeira = sem_vazio[~sem_vazio["item"].astype(str)
                             .str.contains("BAND", case=False, na=False)]
    # kind="mergesort" NÃO é opcional: o quicksort padrão do pandas não é
    # estável, e sem sort estável o desempate entre linhas de mesma competência
    # muda entre execuções — mesmo lote, resultado diferente.
    dedup = (sem_bandeira.sort_values("competencia", kind="mergesort")
             .drop_duplicates(subset=["item", "tarifa_unitaria_r$", "fornecedor"],
                              keep="first"))

    dfs["tarifas"] = dedup.reindex(columns=cols_saida).reset_index(drop=True)


_RE_SUBGRUPO_A = re.compile(r'\bA[34]a?\b', re.IGNORECASE)
_RE_SUBGRUPO_B = re.compile(r'\bB[1-4]\b', re.IGNORECASE)


def grupo_da_classificacao(v) -> str | None:
    """
    'A' ou 'B' a partir de classificacao_tarifaria, pelo grupo de TENSÃO da
    UC: "A A4 …"/"A4 - …" → A; "B B3 …"/"B3 - …" → B; "A OPT B3 …" (UC do
    grupo A OPTANTE pela tarifa do grupo B) → A — continua ligada em alta
    tensão e com demanda contratada, só é tarifada como B; é assim que o
    mapa de UCs a cadastra (AT).
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v)
    if re.match(r'^\s*A\b', s) or _RE_SUBGRUPO_A.search(s):
        return 'A'
    if re.match(r'^\s*B\b', s) or _RE_SUBGRUPO_B.search(s):
        return 'B'
    return None


def _grupo_do_mapa(uc_df: pd.DataFrame | None) -> dict:
    """
    {id_uc: 'AT'|'BT'} a partir de uma coluna do MAPA DE UCs em
    unidade_consumidora cujo nome fale em fornecimento/grupo e cujos valores
    tragam AT/BT (ex.: 'FORNECIMENTO (GRUPO AT/BT)' = 'TRIFÁSICO (AT)').
    """
    if uc_df is None or uc_df.empty or "id_uc" not in uc_df.columns:
        return {}
    for col in uc_df.columns:
        n = re.sub(r'[^a-z]', '', str(col).lower())
        if not ("fornecimento" in n or "grupo" in n) or "tipo" in n:
            continue
        vals = uc_df[col].dropna().astype(str)
        if vals.empty or not vals.str.contains(r'\b(?:AT|BT)\b').mean() > 0.5:
            continue
        def _at_bt(v):
            m = re.search(r'\b(AT|BT)\b', str(v)) if v is not None else None
            return m.group(1) if m else None
        return {k: v for k, v in zip(uc_df["id_uc"], uc_df[col].map(_at_bt)) if v}
    return {}


def _derivar_validacao(dfs: dict) -> None:
    """
    Aba 'validacao': 1 linha por ocorrência, com o que a fatura sozinha não
    deixa conferir. Regras (gravidade):
      erro  DEMANDA_AUSENTE_UC_AT     mapa diz AT e demanda_contratada_kw vazia
      erro  DEMANDA_AUSENTE_GRUPO_A   fatura do grupo A (sem info do mapa) e demanda vazia
      erro  ITENS_NAO_FECHAM          |soma dos itens − valor_total_r$| > R$ 1
      erro  SEM_ID_UC                 fatura sem UC legível (id_uc NULO_…)
      aviso GRUPO_DIVERGENTE_MAPA     grupo da fatura (A/B) ≠ grupo do mapa (AT/BT)
      aviso DEMANDA_EM_UC_BT          demanda contratada > 0 numa UC/fatura do grupo B
      aviso UC_FORA_DO_MAPA           (1 por UC) mapa carregado, UC não cadastrada
      aviso MEDICAO_VAZIA             fatura sem nenhuma linha de medição
      aviso MEDICAO_INCOMPLETA        grupo A com menos de 9 linhas de medição
      info  DEMANDA_SEM_CONTRATO      demanda 0 porque os itens vieram "S/ CONTRATO"
      info  LIDA_POR_OCR              fatura escaneada: campos podem ter ruído de OCR
    Recalculada do zero a cada processamento/concatenação.
    """
    cols = schema.all_canonical("validacao")
    fat = dfs.get("fatura")
    if fat is None or getattr(fat, "empty", True) or "id_fatura" not in fat.columns:
        dfs["validacao"] = pd.DataFrame(columns=cols)
        return
    itf = dfs.get("itens_fatura")
    med = dfs.get("medicao")
    uc = dfs.get("unidade_consumidora")

    def col(nome):
        return fat[nome] if nome in fat.columns else pd.Series([None] * len(fat), index=fat.index)

    soma_itens = {}
    sem_contrato = set()
    if itf is not None and not itf.empty and {"id_fatura", "valor_r$"}.issubset(itf.columns):
        vals = pd.to_numeric(itf["valor_r$"], errors="coerce").fillna(0.0)
        soma_itens = vals.groupby(itf["id_fatura"]).sum().to_dict()
        if "item" in itf.columns:
            mask = itf["item"].astype(str).str.contains(r'S/\s*CONTRATO', case=False, regex=True)
            sem_contrato = set(itf.loc[mask, "id_fatura"])
    n_med = {}
    if med is not None and not med.empty and "id_fatura" in med.columns:
        n_med = med.groupby("id_fatura").size().to_dict()
    grupo_mapa = _grupo_do_mapa(uc)
    mapa_ativo = dicionario_uc.ativo()
    info_uc = {}
    if uc is not None and not uc.empty and "id_uc" in uc.columns:
        for _, r in uc.drop_duplicates("id_uc").iterrows():
            info_uc[r["id_uc"]] = (r.get("razao_social"), r.get("municipio"))

    linhas = []
    fora_mapa: dict = {}
    canon = col("id_uc_canonico")
    demanda = pd.to_numeric(col("demanda_contratada_kw"), errors="coerce")
    total = pd.to_numeric(col("valor_total_r$"), errors="coerce")
    ocr = col("extraido_por_ocr")

    def add(i, gravidade, regra, detalhe):
        linhas.append({
            "id_fatura": fat.at[i, "id_fatura"],
            "id_uc": fat.at[i, "id_uc"] if "id_uc" in fat.columns else None,
            "id_uc_canonico": canon.at[i],
            "competencia": fat.at[i, "competencia"] if "competencia" in fat.columns else None,
            "fornecedor": fat.at[i, "fornecedor"] if "fornecedor" in fat.columns else None,
            "gravidade": gravidade, "regra": regra, "detalhe": detalhe,
        })

    for i in fat.index:
        fid = fat.at[i, "id_fatura"]
        id_uc = fat.at[i, "id_uc"] if "id_uc" in fat.columns else None
        grupo = grupo_da_classificacao(col("classificacao_tarifaria").at[i])
        gm = grupo_mapa.get(id_uc)
        dem = demanda.at[i]
        dem_vazia = pd.isna(dem)

        if isinstance(id_uc, str) and id_uc.startswith("NULO_"):
            add(i, "erro", "SEM_ID_UC", "a fatura não trouxe UC legível")
        if gm == "AT" and dem_vazia:
            add(i, "erro", "DEMANDA_AUSENTE_UC_AT",
                "o mapa de UCs diz AT (grupo A) e a fatura saiu sem demanda contratada")
        elif grupo == "A" and dem_vazia:
            add(i, "erro", "DEMANDA_AUSENTE_GRUPO_A",
                f"classificação '{col('classificacao_tarifaria').at[i]}' é do grupo A e a "
                "fatura saiu sem demanda contratada")
        if grupo and gm and ((grupo == "A") != (gm == "AT")):
            add(i, "aviso", "GRUPO_DIVERGENTE_MAPA",
                f"fatura no grupo {grupo} ('{col('classificacao_tarifaria').at[i]}'), "
                f"mapa de UCs diz {gm}")
        if not dem_vazia and dem > 0 and (gm == "BT" or (gm is None and grupo == "B")):
            add(i, "aviso", "DEMANDA_EM_UC_BT",
                f"demanda contratada {dem:g} kW numa UC/fatura do grupo B")
        if fid in sem_contrato and not dem_vazia and dem == 0:
            add(i, "info", "DEMANDA_SEM_CONTRATO",
                "itens 'S/ CONTRATO': UC sem contrato de demanda no mês (demanda = 0)")
        tot = total.at[i]
        if fid in soma_itens and not pd.isna(tot):
            dif = soma_itens[fid] - tot
            if abs(dif) > 1.0:
                add(i, "erro", "ITENS_NAO_FECHAM",
                    f"soma dos itens R$ {soma_itens[fid]:,.2f} × total R$ {tot:,.2f} "
                    f"(diferença R$ {dif:,.2f})")
        n = n_med.get(fid, 0)
        # Mínimo de linhas de uma tabela de medição COMPLETA do grupo A: 9 na
        # Equatorial (11 no layout 2023+, 15 no de 2022) e 8 na CHESP (o layout
        # de ago–nov/2022 tem 8; o atual, 9).
        minimo = 8 if str(fat.at[i, "fornecedor"] if "fornecedor" in fat.columns else "") == "CHESP" else 9
        if n == 0:
            add(i, "aviso", "MEDICAO_VAZIA", "nenhuma linha de medição extraída")
        elif grupo == "A" and n < minimo:
            add(i, "aviso", "MEDICAO_INCOMPLETA",
                f"{n} linha(s) de medição numa fatura do grupo A (esperado ≥ {minimo})")
        if ocr.at[i] is True or str(ocr.at[i]).lower() == "true":
            add(i, "info", "LIDA_POR_OCR",
                "PDF escaneado: valores lidos por OCR podem ter ruído")
        if mapa_ativo and id_uc is not None and not (isinstance(id_uc, str) and id_uc.startswith("NULO_")) \
                and dicionario_uc.buscar(id_uc) is None:
            fora_mapa.setdefault(id_uc, [0, i])
            fora_mapa[id_uc][0] += 1

    for id_uc, (n, i) in fora_mapa.items():
        razao, munic = info_uc.get(id_uc, (None, None))
        linhas.append({
            "id_fatura": None, "id_uc": id_uc, "id_uc_canonico": canon.at[i],
            "competencia": None,
            "fornecedor": fat.at[i, "fornecedor"] if "fornecedor" in fat.columns else None,
            "gravidade": "aviso", "regra": "UC_FORA_DO_MAPA",
            "detalhe": f"{n} fatura(s); UC não está no mapa de UCs"
                       + (f" — {razao}, {munic}" if razao or munic else ""),
        })

    ordem = {"erro": 0, "aviso": 1, "info": 2}
    df = pd.DataFrame(linhas, columns=cols)
    if not df.empty:
        df["_o"] = df["gravidade"].map(ordem)
        df = df.sort_values(["_o", "regra", "id_fatura"], kind="mergesort").drop(columns="_o")
    if not mapa_ativo:
        # Mesma regra das demais abas: sem mapa de UCs, nenhuma aba tem id_uc_canonico.
        df = df.drop(columns=["id_uc_canonico"])
    dfs["validacao"] = df.reset_index(drop=True)


def _tipo_fornecimento_upper(dfs: dict) -> None:
    """tipo_fornecimento ('fatura'/'fatura_resumida'): valores não vazios em
    maiúsculas (independe da fornecedora)."""
    for aba in ("fatura", "fatura_resumida"):
        df = dfs.get(aba)
        if df is not None and not df.empty and "tipo_fornecimento" in df.columns:
            df["tipo_fornecimento"] = df["tipo_fornecimento"].map(
                lambda v: v.upper() if isinstance(v, str) else v)


def _reordenar_canonico(dfs: dict) -> None:
    """
    Reordena as colunas de cada aba na ordem canônica (schema.py), agora que
    todas as colunas derivadas já foram calculadas. Sem isso, colunas novas
    (atribuídas via df['nova'] = ...) ficam sempre no FINAL do DataFrame,
    independente da posição definida no esquema.
    """
    for aba, df in dfs.items():
        if df is None or df.empty:
            continue
        cols_canon = schema.all_canonical(aba)
        if not cols_canon:
            continue
        ordenadas = [c for c in cols_canon if c in df.columns]
        extras = [c for c in df.columns if c not in cols_canon]
        if list(df.columns) != ordenadas + extras:
            dfs[aba] = df.reindex(columns=ordenadas + extras)


def _dedup_unidade_consumidora(dfs: dict) -> None:
    """
    A aba 'unidade_consumidora' acumula 1 linha por FATURA processada (não por
    UC). Como os dados cadastrais e os agregados (primeira/ultima_*) são os
    mesmos para todas as faturas da mesma UC, ao final basta um drop_duplicates
    para sobrar 1 linha por UC.
    """
    df = dfs.get("unidade_consumidora")
    if df is not None and not df.empty:
        dfs["unidade_consumidora"] = df.drop_duplicates().reset_index(drop=True)


def aplicar_concat(res_dfs: dict, meta: dict | None) -> None:
    """
    Recalcula as colunas derivadas sobre o resultado da concatenação (nomes
    exibidos). Canoniza via metadados, calcula e grava de volta (in place).
    """
    canon: dict[str, pd.DataFrame] = {}
    reverso: dict[str, dict] = {}   # aba -> {canonico: nome_exibido}
    for aba, df in res_dfs.items():
        m = _concat.mapeamento_de_meta(meta, aba) or {}   # exibido -> canonico
        inv = {exib: can for exib, can in m.items() if can}       # exibido -> canonico
        reverso[aba] = {can: exib for exib, can in inv.items()}   # canonico -> exibido
        canon[aba] = df.rename(columns=inv)

    _calcular(canon)

    for aba, cdf in canon.items():
        # 'tarifas'/'validacao' ficam FORA do writeback coluna-a-coluna: são
        # recalculadas do zero (número de linhas próprio, sem relação com o da
        # planilha enviada) e reinstaladas inteiras logo abaixo. Escrever
        # coluna a coluna aqui daria erro de tamanho assim que a planilha
        # enviada já tivesse a aba.
        if aba in ABAS_RECALCULADAS or aba not in res_dfs:
            continue
        for canonico in COLUNAS_DERIVADAS:
            if canonico in cdf.columns:
                exib = reverso.get(aba, {}).get(canonico, canonico)
                res_dfs[aba][exib] = cdf[canonico].values

    # 'tarifas' e 'validacao' são instaladas/sobrescritas inteiras, como
    # 'unidade_consumidora' logo abaixo: não passam pelo dedup genérico de
    # concat.py. Isso vale também quando a planilha enviada foi gerada por uma
    # versão anterior do app e nem tinha a aba — ela é criada aqui.
    for aba in ABAS_RECALCULADAS:
        res_dfs[aba] = canon.get(aba, pd.DataFrame(columns=schema.all_canonical(aba)))
        # Registra a aba nos metadados (nomes canônicos = exibidos, já que ela
        # é sempre regerada por aqui): sem isso, o próximo upload dessa planilha
        # não teria mapa para ela e cairia no casamento por similaridade.
        if isinstance(meta, dict):
            meta.setdefault("abas", {})[aba] = {
                "incluida": True,
                "colunas": [{"exibido": c, "canonico": c, "incluida": True}
                            for c in res_dfs[aba].columns],
            }

    # Dedup ao final (linha completa) — direto no resultado (nomes exibidos),
    # já que a contagem de linhas de `canon` pode ter mudado com o dedup interno.
    df_uc = res_dfs.get("unidade_consumidora")
    if df_uc is not None and not df_uc.empty:
        res_dfs["unidade_consumidora"] = df_uc.drop_duplicates().reset_index(drop=True)
