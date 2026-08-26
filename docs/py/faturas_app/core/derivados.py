"""
Colunas DERIVADAS/agregadas, recalculadas do zero sobre o conjunto completo de
faturas (tanto no processamento quanto na concatenação):

  - unidade_consumidora.primeira_competencia / ultima_competencia e
    primeira_fatura / ultima_fatura: a competência mais antiga/mais recente
    (e o id_fatura correspondente) por id_uc_canonico.
  - id_uc_sem_format / id_uc_atual_medidor / id_uc_atual_medidor_sem_format:
    ao lado de id_uc, em TODAS as abas.
  - id_uc_canonico e o cadastro do dicionário oficial de UCs: ver
    `_enriquecer_dicionario_uc` e core/dicionario_uc.py.
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
                     *dicionario_uc.COLUNAS_UNIDADE_CONSUMIDORA]


def aplicar(dfs: dict) -> dict:
    """Preenche as colunas derivadas nos DataFrames canônicos (in place)."""
    _calcular(dfs)
    _dedup_unidade_consumidora(dfs)
    return dfs


def _calcular(dfs: dict) -> None:
    # A ORDEM importa (não é só anexar linhas novas no fim):
    _colunas_medidor(dfs)            # (1) antes do dicionário: é o fallback de
                                     #     id_uc_canonico (id_uc_atual_medidor)
    _enriquecer_dicionario_uc(dfs)   # (2) id_uc_canonico + cadastro do dicionário
    _extremos_por_uc(dfs)            # (3) depois de (2): agrupa por id_uc_canonico
    _item_normalizado(dfs)           # (4)
    _derivar_tarifas(dfs)            # (5) depois de (4): tarifas leva item_normalizado
    _tipo_fornecimento_upper(dfs)    # (6)
    _reordenar_canonico(dfs)         # (7) por último, sempre


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


def _enriquecer_dicionario_uc(dfs: dict) -> None:
    """
    Consulta o dicionário oficial de UCs (core/dicionario_uc.py) por id_uc — a
    busca já normaliza para dígitos, então casa o id_uc em qualquer formato
    (antigo, atual, com ou sem pontuação) — e grava:

      - Em TODAS as abas com 'id_uc': 'id_uc_canonico' = a UC atual segundo o
        dicionário; quando o dicionário não conhece a UC, cai para o fallback
        já calculado por `_colunas_medidor` ('id_uc_atual_medidor_sem_format'
        em 'unidade_consumidora', 'id_uc_atual' nas demais abas).
      - APENAS em 'unidade_consumidora': também as colunas cadastrais
        (dicionario_uc.COLUNAS_UNIDADE_CONSUMIDORA). Nas outras abas ficaria
        um cadastro redundante repetido por linha.

    Precisa rodar DEPOIS de `_colunas_medidor` (usa suas colunas como fallback).

    Respeita a metodologia escolhida pelo usuário (`dicionario_uc.modo()`): em
    MODO_MEDIDOR o dicionário não é consultado, `id_uc_canonico` recebe o valor
    da heurística de medidor e as colunas cadastrais NÃO são criadas — é o
    comportamento clássico, para instituições que não têm um cadastro oficial.
    """
    usar_dicionario = dicionario_uc.ativo()
    for aba, df in dfs.items():
        if df is None or df.empty or "id_uc" not in df.columns:
            continue
        if not usar_dicionario:
            fallback = (df.get("id_uc_atual_medidor_sem_format")
                        if aba == "unidade_consumidora" else df.get("id_uc_atual"))
            if fallback is not None:
                df["id_uc_canonico"] = fallback
            continue
        # Consulta o dicionário uma vez por id_uc DISTINTO, não por linha: são
        # ~400 UCs para dezenas de milhares de linhas em itens_fatura/medicao,
        # e cada consulta monta um dict de 28 campos. Sem isso, o
        # pós-processamento de um lote grande (10 mil faturas) levava minutos.
        unicos = {v: dicionario_uc.campos_unidade_consumidora(v)
                  for v in df["id_uc"].unique()}
        canonico_dicionario = df["id_uc"].map(
            {k: (c.get("id_uc_dicionario_sem_format") if c else None)
             for k, c in unicos.items()})
        if aba == "unidade_consumidora":
            fallback = df.get("id_uc_atual_medidor_sem_format")
            for col in dicionario_uc.COLUNAS_UNIDADE_CONSUMIDORA:
                df[col] = df["id_uc"].map(
                    {k: (c.get(col) if c else None) for k, c in unicos.items()})
        else:
            fallback = df.get("id_uc_atual")
        if fallback is None:
            df["id_uc_canonico"] = canonico_dicionario
        else:
            df["id_uc_canonico"] = canonico_dicionario.where(
                canonico_dicionario.notna(), fallback)


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
        # 'tarifas' fica FORA do writeback coluna-a-coluna: ela é recalculada do
        # zero (número de linhas próprio, sem relação com o da planilha enviada)
        # e reinstalada inteira logo abaixo. Escrever coluna a coluna aqui daria
        # erro de tamanho assim que a planilha enviada já tivesse a aba.
        if aba == "tarifas" or aba not in res_dfs:
            continue
        for canonico in COLUNAS_DERIVADAS:
            if canonico in cdf.columns:
                exib = reverso.get(aba, {}).get(canonico, canonico)
                res_dfs[aba][exib] = cdf[canonico].values

    # 'tarifas' é instalada/sobrescrita inteira, como 'unidade_consumidora' logo
    # abaixo: não passa pelo dedup genérico de concat.py. Isso vale também
    # quando a planilha enviada foi gerada por uma versão anterior do app e nem
    # tinha a aba — ela é criada aqui.
    res_dfs["tarifas"] = canon.get(
        "tarifas", pd.DataFrame(columns=schema.all_canonical("tarifas")))
    # Registra a aba nos metadados (nomes canônicos = exibidos, já que ela é
    # sempre regerada por aqui): sem isso, o próximo upload dessa planilha não
    # teria mapa para 'tarifas' e cairia no casamento por similaridade.
    if isinstance(meta, dict):
        meta.setdefault("abas", {})["tarifas"] = {
            "incluida": True,
            "colunas": [{"exibido": c, "canonico": c, "incluida": True}
                        for c in res_dfs["tarifas"].columns],
        }

    # Dedup ao final (linha completa) — direto no resultado (nomes exibidos),
    # já que a contagem de linhas de `canon` pode ter mudado com o dedup interno.
    df_uc = res_dfs.get("unidade_consumidora")
    if df_uc is not None and not df_uc.empty:
        res_dfs["unidade_consumidora"] = df_uc.drop_duplicates().reset_index(drop=True)
