"""
Dicionário oficial de Unidades Consumidoras.

O `id_uc` impresso na fatura NÃO é um identificador estável da UC ao longo do
tempo: o formato mudou historicamente (`10008414082` → `2.742.876.012-19`, mesma
UC). Até aqui o app tentava reconciliar isso por MEDIDOR (`id_uc_atual_medidor`,
em `derivados.py`), heurística que quebra quando a UC troca de medidor — o
histórico anterior à troca não tem o medidor novo. A raiz do problema é derivar
identidade e cadastro de UC de texto de fatura (ruidoso, variável por
layout/época) quando existe uma fonte melhor: um cadastro oficial mantido à
parte, que é o que este módulo lê.

O app NÃO embarca nenhum dicionário: o que existia era o cadastro do TJGO, e
embarcá-lo impunha os dados de uma instituição a todas as outras. O cadastro é
sempre IMPORTADO pelo usuário, e fica em
`%APPDATA%/FaturasEnergia/dicionario_uc.json`.

  - **Importação tolerante**: o JSON não precisa ter exatamente os nomes de
    campo do TJGO. As chaves são casadas sem acento/maiúsculas/pontuação contra
    uma tabela de sinônimos (`_ALIASES`), então um cadastro de outra origem
    (`"unidade_consumidora"`, `"id_uc"`, `"endereco"`, `"orgao"`…) é entendido
    do mesmo jeito. O que não for reconhecido vira aviso, não erro.
  - **Índice de busca** por dígitos, cobrindo `UC`, `UC VELHA` e
    `UC FORMATADO (…)` — é isso que faz um `id_uc` em QUALQUER formato (antigo
    ou atual, com ou sem pontuação) resolver para o mesmo registro.

**Demanda contratada nunca sai daqui.** `fatura.demanda_contratada_kw` e
`fatura.demanda_geracao_contratada_kw` vêm EXCLUSIVAMENTE do PDF da fatura. O
próprio dicionário trata alteração de demanda como um evento com protocolo
formal (`Alteração de Demanda (kW)` / `Demanda Futura (kW)` / `Protocolo …`),
não um valor cadastral estático — e o que a planilha precisa é o que a fatura
daquele mês realmente cobrou. Duas fontes para o mesmo conceito criariam risco
de divergência silenciosa. A blindagem é estrutural: `_CAMPO_PARA_COLUNA` é uma
tabela EXPLÍCITA campo→coluna, não um "copia toda chave do registro", então um
dicionário futuro que reintroduza essas chaves simplesmente as ignora.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Mapeamento campo do JSON → coluna canônica de `unidade_consumidora`.
# É esta tabela (e o fato de ser explícita) que serve de blindagem contra os
# campos de demanda voltarem pelo dicionário — ver o docstring do módulo.
# ──────────────────────────────────────────────────────────────────────────────
_CAMPO_PARA_COLUNA = {
    # (chave no JSON): (coluna canônica, transformação)
    "UC VELHA": ("id_uc_antigo_dicionario", str),
    "UC RESOLUÇÃO Nº 1095/2024 ANEEL (BORDERÔ)": ("id_uc_aneel_bordero", str),
    "OPERANTE": ("uc_operante", bool),
    "MEDIDOR_ATUAL": ("medidor_atual_dicionario", str),
    "UNIDADE JUDICIÁRIA": ("unidade_judiciaria", str),
    "UJ - UC - AT/BT - GD": ("uj_uc_at_bt_gd", str),
    "CONCESSIONÁRIA": ("concessionaria", str),
    "ENDEREÇO": ("endereco_dicionario", str),
    "COMARCA": ("comarca", str),
    "FORNECIMENTO (GRUPO AT/BT)": ("grupo_fornecimento_at_bt", str),
    "LIMITE FORNECIMENTO": ("limite_fornecimento_tensao", str),
    "GD (GERAÇÃO DISTRIBUÍDA)": ("possui_geracao_distribuida", bool),
    "PARTICIPA DOS RATEIOS DE ALGUMA FORMA": ("participa_rateio", bool),
    "GERADOR (PARA OS RATEIOS)": ("e_gerador_rateio", bool),
    "BENEFICIÁRIAS DO RATEIO": ("e_beneficiaria_rateio", bool),
    "RATEIO COMUM": ("rateio_comum", bool),
    "RATEIO DA UFV DE CACHOEIRA DOURADA": ("rateio_ufv_cachoeira_dourada", bool),
    "PORCENTAGEM (%)": ("percentual_rateio", str),
    "Alteração de Demanda (kW)": ("demanda_alterada", bool),
    "Demanda Futura (kW)": ("demanda_futura_kw", float),
    "Protocolo da alteração de demanda": ("protocolo_alteracao_demanda", str),
    "Saldos do SCEE (GDs)": ("saldo_scee_cadastro_kwh", float),
    "PRIORIDADE": ("prioridade_rateio", str),
    "GD SEM RATEIO": ("gd_sem_rateio", bool),
    "USINA FOTOVOLTAICA (USINA DE CACHOEIRA DOURADA/UFV DE CACHOEIRA DOURADA)":
        ("usina_fotovoltaica_cachoeira_dourada", bool),
    # DELIBERADAMENTE ausentes: "DEMANDA CONTRATADA (kW)" e "DEMANDA GERAÇÃO
    # (kW)" — NUNCA adicionar de volta aqui (ver docstring do módulo).
}

# Chaves do JSON que NÃO viram coluna por `_CAMPO_PARA_COLUNA` mas são
# conhecidas e tratadas à parte — não devem entrar no aviso de "chave nova".
_CAMPOS_TRATADOS_A_PARTE = {"UC", "MEDIDORES_UTILIZADOS"}

# Chaves que já foram excluídas de propósito: se reaparecerem, o aviso deve
# dizer que a exclusão é intencional, para ninguém "consertar" isso depois.
_CAMPOS_EXCLUIDOS = {"DEMANDA CONTRATADA (kW)", "DEMANDA GERAÇÃO (kW)"}


# ──────────────────────────────────────────────────────────────────────────────
# Importação TOLERANTE: sinônimos de nome de campo
# ──────────────────────────────────────────────────────────────────────────────
# Um cadastro vindo de outra instituição não vai usar os rótulos do TJGO. Cada
# chave do JSON é normalizada (sem acento, sem pontuação, minúscula, sem
# espaços) e casada contra esta tabela; o registro é reescrito para as chaves
# canônicas ANTES de qualquer outra coisa. Assim `_CAMPO_PARA_COLUNA` continua
# sendo uma tabela explícita (a blindagem contra os campos de demanda), e ao
# mesmo tempo o app aceita arquivos de origens diferentes.
def _n(txt) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(txt))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]+", "", s).upper()


_ALIASES = {
    "UC": ("UC", "IDUC", "UNIDADECONSUMIDORA", "NUMEROUC", "NUMERODAUC",
           "CODIGOUC", "INSTALACAO", "NUMEROINSTALACAO"),
    "UC VELHA": ("UCVELHA", "UCANTIGA", "IDUCANTIGO", "UCANTIGO",
                 "NUMEROANTIGO", "CODIGOANTIGO"),
    "UC RESOLUÇÃO Nº 1095/2024 ANEEL (BORDERÔ)": (
        "UCRESOLUCAON10952024ANEELBORDERO", "UCBORDERO", "UCANEEL", "BORDERO"),
    "OPERANTE": ("OPERANTE", "ATIVA", "ATIVO", "EMOPERACAO", "SITUACAO"),
    "MEDIDORES_UTILIZADOS": ("MEDIDORESUTILIZADOS", "MEDIDORES",
                             "MEDIDORESUSADOS", "HISTORICOMEDIDORES"),
    "MEDIDOR_ATUAL": ("MEDIDORATUAL", "MEDIDOR", "NUMEROMEDIDOR"),
    "UNIDADE JUDICIÁRIA": ("UNIDADEJUDICIARIA", "UJ", "ORGAO", "UNIDADE",
                           "LOTACAO", "SETOR", "DESCRICAO", "NOME"),
    "UJ - UC - AT/BT - GD": ("UJUCATBTGD", "RESUMO"),
    "CONCESSIONÁRIA": ("CONCESSIONARIA", "DISTRIBUIDORA", "FORNECEDORA",
                       "FORNECEDOR"),
    "ENDEREÇO": ("ENDERECO", "LOGRADOURO", "ENDERECOCOMPLETO", "LOCAL"),
    "COMARCA": ("COMARCA", "MUNICIPIO", "CIDADE"),
    "FORNECIMENTO (GRUPO AT/BT)": ("FORNECIMENTOGRUPOATBT", "GRUPO",
                                   "GRUPOTENSAO", "TIPOFORNECIMENTO"),
    "LIMITE FORNECIMENTO": ("LIMITEFORNECIMENTO", "LIMITETENSAO", "TENSAO",
                            "FAIXATENSAO"),
    "GD (GERAÇÃO DISTRIBUÍDA)": ("GDGERACAODISTRIBUIDA", "GD",
                                 "GERACAODISTRIBUIDA", "POSSUIGD"),
    "PARTICIPA DOS RATEIOS DE ALGUMA FORMA": (
        "PARTICIPADOSRATEIOSDEALGUMAFORMA", "PARTICIPARATEIO", "RATEIO"),
    "GERADOR (PARA OS RATEIOS)": ("GERADORPARAOSRATEIOS", "GERADOR",
                                  "EGERADOR"),
    "BENEFICIÁRIAS DO RATEIO": ("BENEFICIARIASDORATEIO", "BENEFICIARIA",
                                "EBENEFICIARIA"),
    "RATEIO COMUM": ("RATEIOCOMUM",),
    "RATEIO DA UFV DE CACHOEIRA DOURADA": ("RATEIODAUFVDECACHOEIRADOURADA",),
    "PORCENTAGEM (%)": ("PORCENTAGEM", "PERCENTUAL", "PERCENTUALRATEIO"),
    "Alteração de Demanda (kW)": ("ALTERACAODEDEMANDAKW", "ALTERACAODEDEMANDA"),
    "Demanda Futura (kW)": ("DEMANDAFUTURAKW", "DEMANDAFUTURA"),
    "Protocolo da alteração de demanda": ("PROTOCOLODAALTERACAODEDEMANDA",
                                          "PROTOCOLO"),
    "Saldos do SCEE (GDs)": ("SALDOSDOSCEEGDS", "SALDOSCEE", "SALDO"),
    "PRIORIDADE": ("PRIORIDADE",),
    "GD SEM RATEIO": ("GDSEMRATEIO",),
    "USINA FOTOVOLTAICA (USINA DE CACHOEIRA DOURADA/UFV DE CACHOEIRA DOURADA)": (
        "USINAFOTOVOLTAICAUSINADECACHOEIRADOURADAUFVDECACHOEIRADOURADA",
        "USINAFOTOVOLTAICA", "UFV"),
}

# {forma_normalizada: chave_canonica}
_MAPA_ALIAS = {}
for _canon, _formas in _ALIASES.items():
    _MAPA_ALIAS[_n(_canon)] = _canon
    for _f in _formas:
        _MAPA_ALIAS.setdefault(_n(_f), _canon)


def _canonizar_registro(reg: dict) -> dict:
    """Reescreve as chaves de UM registro para os nomes canônicos conhecidos.

    Chave já canônica passa direto. Chave reconhecida por sinônimo é renomeada
    (sem sobrescrever uma canônica que já exista). Chave desconhecida é mantida
    como veio — `_construir` avisa sobre ela, e é assim que um campo novo do
    cadastro aparece no relatório em vez de sumir em silêncio.
    """
    if not isinstance(reg, dict):
        return reg
    out = {}
    for k, v in reg.items():
        if k in _CAMPO_PARA_COLUNA or k in _CAMPOS_TRATADOS_A_PARTE \
                or str(k).startswith("UC FORMATADO"):
            out[k] = v
            continue
        nk = _n(k)
        if nk.startswith("UCFORMATADO"):
            out["UC FORMATADO (importado)"] = v
            continue
        canon = _MAPA_ALIAS.get(nk)
        out[canon if (canon and canon not in out and canon not in reg) else k] = v
    return out

# Colunas produzidas por `campos_unidade_consumidora`, na ordem em que aparecem
# em `schema.CANONICAL_COLUMNS["unidade_consumidora"]`.
# `medidores_utilizados_dicionario` não vem de `_CAMPO_PARA_COLUNA` (o campo é
# uma lista, unida à parte), por isso entra na posição certa manualmente.
COLUNAS_UNIDADE_CONSUMIDORA = [
    "id_uc_dicionario",
    "id_uc_dicionario_sem_format",
    "id_uc_antigo_dicionario",
    "id_uc_aneel_bordero",
    "uc_operante",
    "medidores_utilizados_dicionario",
    *[coluna for coluna, _ in _CAMPO_PARA_COLUNA.values()
      if coluna not in ("id_uc_antigo_dicionario", "id_uc_aneel_bordero",
                        "uc_operante")],
]

_NOME_ARQUIVO = "dicionario_uc.json"
_NOME_CONFIG = "config_uc.json"

# ──────────────────────────────────────────────────────────────────────────────
# Metodologia de identificação da Unidade Consumidora
# ──────────────────────────────────────────────────────────────────────────────
# O dicionário oficial é um cadastro de UMA instituição (no caso, o TJGO). Um
# app que dependesse SÓ dele não serviria para nenhuma outra instituição, cujas
# UCs não estão nesse arquivo. Por isso a metodologia é escolhida pelo usuário:
#
#   MODO_DICIONARIO — o cadastro (endereço, unidade judiciária, medidor atual,
#       rateios…) vem do JSON oficial, e `id_uc_canonico` é a UC do dicionário.
#       Resolve a instabilidade do id_uc ao longo do tempo (mudança de formato)
#       e a troca de medidor.
#   MODO_MEDIDOR — comportamento CLÁSSICO, que não depende de cadastro nenhum:
#       tudo vem do PDF e a reconciliação entre UCs é feita pelo MEDIDOR
#       (id_uc_atual_medidor). `id_uc_canonico` recebe esse mesmo valor e as
#       colunas cadastrais do dicionário não são criadas.
MODO_DICIONARIO = "dicionario"
MODO_MEDIDOR = "medidor"
MODOS = (MODO_DICIONARIO, MODO_MEDIDOR)

# Padrão: MEDIDOR. Como o app não embarca mais nenhum dicionário, a metodologia
# que funciona sem cadastro é a única que faz sentido numa instalação nova.
# Importar um JSON pela aba Parâmetros já liga o MODO_DICIONARIO sozinho.
MODO_PADRAO = MODO_MEDIDOR

# Cache em memória (invalidado por `recarregar()`), no mesmo espírito de
# `correcoes._dados()`: {"registros", "indice", "avisos", "fonte", "arquivo"}.
_CACHE: dict | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Carga
# ──────────────────────────────────────────────────────────────────────────────
def _dir_usuario() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = Path(base) / "FaturasEnergia"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


def arquivo_usuario() -> Path:
    """Caminho do override do usuário (pode não existir)."""
    return _dir_usuario() / _NOME_ARQUIVO


def _arquivo_config() -> Path:
    return _dir_usuario() / _NOME_CONFIG


def modo() -> str:
    """Metodologia escolhida: MODO_DICIONARIO ou MODO_MEDIDOR."""
    try:
        cfg = json.loads(_arquivo_config().read_text(encoding="utf-8"))
        m = cfg.get("modo_identificacao_uc")
        if m in MODOS:
            return m
    except Exception:
        pass
    return MODO_PADRAO


def definir_modo(novo: str) -> None:
    """Grava a metodologia escolhida (persistida entre execuções)."""
    if novo not in MODOS:
        raise ValueError(f"Metodologia desconhecida: {novo!r}")
    cfg = {}
    try:
        cfg = json.loads(_arquivo_config().read_text(encoding="utf-8"))
    except Exception:
        pass
    cfg["modo_identificacao_uc"] = novo
    _arquivo_config().write_text(
        json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


def ativo() -> bool:
    """O cadastro do dicionário deve ser usado neste processamento?"""
    return modo() == MODO_DICIONARIO


def _so_digitos(v):
    return re.sub(r"\D", "", str(v)) if v is not None else None


def _ler_bruto() -> tuple[list, str, str | None]:
    """
    (registros, fonte, caminho) — só o arquivo IMPORTADO pelo usuário.

    O app não embarca mais nenhum dicionário: o que existia era o cadastro do
    TJGO, que não serve (e não deveria ser imposto) a outras instituições. Sem
    arquivo importado, o dicionário fica vazio e o app usa a metodologia por
    MEDIDOR (ver `MODO_PADRAO`).
    """
    alvo = arquivo_usuario()
    if alvo.is_file():
        try:
            data = _lista_de_registros(json.loads(alvo.read_text(encoding="utf-8")))
            if data is not None:
                return [_canonizar_registro(r) for r in data], "usuario", str(alvo)
        except Exception:
            # Arquivo corrompido/ilegível: segue vazio em vez de derrubar o
            # processamento (o aviso sai em `avisos()`).
            pass
    return [], "nenhum", None


def _chaves_de_busca(reg: dict) -> list:
    """Todos os identificadores pelos quais um registro pode ser encontrado."""
    chaves = [reg.get("UC"), reg.get("UC VELHA")]
    chaves += [v for k, v in reg.items() if k.startswith("UC FORMATADO")]
    return chaves


def _construir(registros: list) -> dict:
    indice: dict[str, dict] = {}
    avisos: list[str] = []
    desconhecidas: set[str] = set()
    for reg in registros:
        if not isinstance(reg, dict):
            continue
        for chave in _chaves_de_busca(reg):
            d = _so_digitos(chave)
            if not d:
                continue
            anterior = indice.get(d)
            if anterior is not None and anterior is not reg:
                # Colisão: dois registros diferentes reivindicam o mesmo número.
                # Não falha silenciosamente nem derruba o processamento — o
                # primeiro registro continua valendo e o aviso sobe no relatório.
                avisos.append(
                    f"Dicionário de UC: o identificador {d} aparece em mais de um "
                    f"registro (UC {anterior.get('UC')} e UC {reg.get('UC')}); "
                    f"mantido o primeiro.")
                continue
            indice[d] = reg
        for k in reg:
            if (k in _CAMPO_PARA_COLUNA or k in _CAMPOS_TRATADOS_A_PARTE
                    or k.startswith("UC FORMATADO")):
                continue
            desconhecidas.add(k)
    for k in sorted(desconhecidas):
        if k in _CAMPOS_EXCLUIDOS:
            avisos.append(
                f"Dicionário de UC: o campo '{k}' voltou a aparecer no arquivo e "
                f"continua IGNORADO de propósito — demanda contratada vem sempre "
                f"da fatura, nunca do cadastro.")
        else:
            avisos.append(
                f"Dicionário de UC: campo '{k}' não está mapeado para nenhuma "
                f"coluna e foi ignorado.")
    return {"registros": registros, "indice": indice, "avisos": avisos}


def _dados() -> dict:
    global _CACHE
    if _CACHE is None:
        registros, fonte, caminho = _ler_bruto()
        _CACHE = _construir(registros)
        _CACHE["fonte"] = fonte
        _CACHE["arquivo"] = caminho
    return _CACHE


def recarregar() -> None:
    """Invalida o cache em memória (chamar após importar um novo dicionário)."""
    global _CACHE
    _CACHE = None


# ──────────────────────────────────────────────────────────────────────────────
# API pública
# ──────────────────────────────────────────────────────────────────────────────
def buscar(id_uc_extraido) -> dict | None:
    """Registro bruto do dicionário (dict original do JSON), ou None."""
    d = _so_digitos(id_uc_extraido)
    if not d:
        return None
    return _dados()["indice"].get(d)


def campos_unidade_consumidora(id_uc_extraido) -> dict | None:
    """
    Registro já mapeado para as colunas canônicas de `unidade_consumidora`, ou
    None se `id_uc_extraido` não bater com nenhum registro.

    NUNCA inclui chaves relacionadas a demanda contratada, mesmo que o registro
    bruto as tenha — a tabela `_CAMPO_PARA_COLUNA` é a blindagem.
    """
    reg = buscar(id_uc_extraido)
    if reg is None:
        return None
    uc_formatado = next((v for k, v in reg.items()
                         if k.startswith("UC FORMATADO")), None)
    out = {
        "id_uc_dicionario": uc_formatado or str(reg.get("UC")),
        "id_uc_dicionario_sem_format": _so_digitos(reg.get("UC")),
    }
    for campo_json, (coluna, tipo) in _CAMPO_PARA_COLUNA.items():
        v = reg.get(campo_json)
        if v is None:
            out[coluna] = None
        elif tipo is bool:
            out[coluna] = bool(v)
        elif tipo is float:
            try:
                out[coluna] = float(v)
            except (TypeError, ValueError):
                out[coluna] = None
        else:
            out[coluna] = str(v)
    # MEDIDORES_UTILIZADOS é uma lista -> string unida por "; ".
    meds = reg.get("MEDIDORES_UTILIZADOS")
    if isinstance(meds, list):
        out["medidores_utilizados_dicionario"] = "; ".join(str(m) for m in meds)
    elif meds is None:
        out["medidores_utilizados_dicionario"] = None
    else:
        out["medidores_utilizados_dicionario"] = str(meds)
    return out


def metadados() -> dict:
    """{'total_ucs', 'operantes', 'fonte': 'semente'|'usuario', 'arquivo'}."""
    d = _dados()
    registros = [r for r in d["registros"] if isinstance(r, dict)]
    return {
        "total_ucs": len(registros),
        "operantes": sum(1 for r in registros if r.get("OPERANTE")),
        "fonte": d.get("fonte", "semente"),
        "arquivo": d.get("arquivo"),
    }


def avisos() -> list[str]:
    """Mensagens acumuladas na carga (colisões, campos não mapeados)."""
    return list(_dados()["avisos"])


def _lista_de_registros(data):
    """
    Extrai a LISTA de UCs de um JSON, aceitando os formatos usuais:

      * uma lista de objetos (formato canônico);
      * um objeto embrulhando a lista (`{"ucs": [...]}`, `{"data": [...]}`,
        `{"registros": [...]}` — ou qualquer chave cujo valor seja a maior
        lista de objetos do arquivo);
      * um objeto indexado por UC (`{"274287601219": {...}, ...}`), caso em que
        a chave vira o campo `UC` do registro.

    Devolve None quando não dá para enxergar uma lista de registros.
    """
    if isinstance(data, list):
        # lista vazia continua sendo "uma lista" — quem valida dá a mensagem
        # certa ("não tem nenhuma UC"), em vez de "não enxerguei uma lista".
        return [r for r in data if isinstance(r, dict)]
    if not isinstance(data, dict):
        return None
    # objeto embrulhando a lista: pega a maior lista de dicts entre os valores
    candidatas = [v for v in data.values()
                  if isinstance(v, list) and v and isinstance(v[0], dict)]
    if candidatas:
        return max(candidatas, key=len)
    # objeto indexado pela própria UC
    if data and all(isinstance(v, dict) for v in data.values()):
        out = []
        for chave, reg in data.items():
            reg = dict(reg)
            reg.setdefault("UC", chave)
            out.append(reg)
        return out
    return None


def _uc_do_registro(reg: dict):
    """Identificador da UC no registro, aceitando qualquer sinônimo conhecido."""
    if not isinstance(reg, dict):
        return None
    reg = _canonizar_registro(reg)
    v = reg.get("UC")
    return v if str(v or "").strip() else None


def validar_estrutura(registros) -> None:
    """
    Valida o mínimo para um cadastro ser utilizável: dá para enxergar uma lista
    de registros, e ao menos um deles tem um identificador de UC reconhecível.

    Deliberadamente FROUXA: o objetivo é aceitar cadastros de origens
    diferentes, não impor o formato do TJGO. O que estiver estranho aparece no
    relatório de `importar`, não como exceção.
    """
    lista = _lista_de_registros(registros)
    if lista is None:
        raise ValueError(
            "Não consegui enxergar uma lista de unidades consumidoras no "
            "arquivo. Esperado: uma lista de objetos JSON, ou um objeto "
            "contendo essa lista.")
    if not lista:
        raise ValueError("O arquivo não tem nenhuma unidade consumidora.")
    com_uc = sum(1 for r in lista if _uc_do_registro(r) is not None)
    if com_uc == 0:
        exemplo = ", ".join(list(lista[0].keys())[:8]) or "(registro vazio)"
        raise ValueError(
            "Nenhum registro tem um campo de Unidade Consumidora reconhecível "
            "(UC, id_uc, unidade_consumidora, instalacao…).\n"
            f"Campos encontrados no 1º registro: {exemplo}")


def analisar(caminho: str):
    """
    Lê um JSON de cadastro e devolve `(registros_canonizados, relatorio)` SEM
    gravar nada — para a interface mostrar o que entendeu antes de aplicar.
    """
    with open(caminho, "r", encoding="utf-8") as f:
        data = json.load(f)
    validar_estrutura(data)
    lista = _lista_de_registros(data) or []
    registros = [_canonizar_registro(r) for r in lista]

    com_uc = sum(1 for r in registros if str(r.get("UC") or "").strip())
    reconhecidos, desconhecidos = set(), {}
    for r in registros:
        for k in r:
            if k in _CAMPO_PARA_COLUNA or k in _CAMPOS_TRATADOS_A_PARTE \
                    or str(k).startswith("UC FORMATADO"):
                reconhecidos.add(k)
            else:
                desconhecidos[k] = desconhecidos.get(k, 0) + 1

    rel = [f"{len(registros)} unidade(s) consumidora(s) no arquivo.",
           f"{com_uc} com identificador de UC reconhecido."]
    if com_uc < len(registros):
        rel.append(f"⚠ {len(registros) - com_uc} registro(s) SEM UC — serão "
                   f"ignorados na busca.")
    rel.append(f"{len(reconhecidos)} campo(s) de cadastro reconhecido(s) e "
               f"mapeado(s) para colunas.")
    for k, n in sorted(desconhecidos.items(), key=lambda kv: -kv[1])[:10]:
        if k in _CAMPOS_EXCLUIDOS:
            rel.append(f"⚠ campo '{k}' IGNORADO de propósito — demanda "
                       f"contratada vem sempre da fatura, nunca do cadastro.")
        else:
            rel.append(f"⚠ campo '{k}' não é conhecido ({n} registro(s)) — "
                       f"ignorado.")
    return registros, rel


def importar(caminho: str) -> dict:
    """
    Copia um cadastro externo para `%APPDATA%/FaturasEnergia/`, recarrega o
    cache e LIGA a metodologia por dicionário (importar um cadastro é a forma
    de dizer que se quer usá-lo). Devolve os metadados novos.

    Levanta ValueError se o arquivo não puder ser interpretado.
    """
    registros, _rel = analisar(caminho)
    arquivo_usuario().write_text(
        json.dumps(registros, ensure_ascii=False, indent=1), encoding="utf-8")
    recarregar()
    try:
        definir_modo(MODO_DICIONARIO)
    except Exception:
        pass
    return metadados()
