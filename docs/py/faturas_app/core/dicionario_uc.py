"""
Mapa de Unidades Consumidoras: cadastro externo, importado pelo usuário.

O `id_uc` impresso na fatura não é um identificador estável da UC ao longo do
tempo (o formato muda, o medidor é trocado). Um cadastro mantido à parte
resolve isso — mas ele é de UMA instituição, então o app **não embarca nenhum**:
o mapa é sempre importado e fica em `%APPDATA%/FaturasEnergia/mapa_uc.json`.

## Template

`TEMPLATE` define os itens que o app entende. Só `id_uc` é obrigatório; ele é a
chave de casamento com a fatura. Um registro pode declarar VÁRIOS identificadores
para a mesma UC (lista, ou separados por `;`/`,`) — é isso que permite casar o
formato antigo e o novo da mesma UC e fazer o `id_uc_canonico` unir o histórico.
O primeiro identificador da lista é o canônico.

## Importação

`analisar_arquivo()` lê JSON **ou** planilha e devolve o que conseguiu casar
sozinho (item do arquivo com nome idêntico ao do template), o que ficou pendente
e o que sobrou (campos fora do template). A interface completa o mapeamento e
chama `aplicar_mapeamento()`.

Regras que valem em todo o app:

  - **Sem mapa importado**: nenhuma coluna do template aparece em
    `unidade_consumidora`, e NENHUMA aba recebe `id_uc_canonico`.
  - Item do template que ficar sem correspondência: a coluna não é criada.
  - Campo do arquivo fora do template: vira coluna nova, com o nome do próprio
    campo ou um nome escolhido na hora do mapeamento.

## Demanda contratada nunca sai daqui

`fatura.demanda_contratada_kw` e `demanda_geracao_contratada_kw` vêm SEMPRE do
PDF. O template não tem esses itens, e `_CAMPOS_BLOQUEADOS` impede que eles
entrem como "coluna extra" — o que a fatura cobrou naquele mês só a fatura sabe,
e duas fontes para o mesmo conceito divergiriam em silêncio.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Template do mapa de UCs
# ──────────────────────────────────────────────────────────────────────────────
# (item no arquivo, coluna na planilha, tipo, descrição)
TEMPLATE = [
    ("id_uc", "id_uc", str,
     "Identificador da UC, como aparece na fatura. Aceita vários por registro "
     "(lista ou separados por ';') para casar formatos diferentes da mesma UC. "
     "OBRIGATÓRIO."),
    ("id_uc_aneel_bordero", "id_uc_aneel_bordero", str,
     "UC no formato do borderô (Resolução ANEEL nº 1095/2024)."),
    ("uc_operante", "uc_operante", bool,
     "Se a UC está operante."),
    ("medidor_atual_dicionario", "medidor_atual_dicionario", str,
     "Medidor atualmente instalado na UC."),
    ("unidade_institucional", "unidade_institucional", str,
     "Unidade/órgão da instituição atendido por esta UC."),
    ("endereco_dicionario", "endereco_dicionario", str,
     "Endereço da UC (texto livre)."),
    ("participa_rateio", "participa_rateio", bool,
     "Se a UC participa de rateio de geração distribuída."),
    ("demanda_futura_kw", "demanda_futura_kw", float,
     "Demanda contratada futura (kW), quando há alteração em andamento."),
]

ITEM_CHAVE = "id_uc"

# Itens do template, sem a chave — são estes que viram coluna quando mapeados.
ITENS_MAPEAVEIS = [i for i, _c, _t, _d in TEMPLATE if i != ITEM_CHAVE]

# Coluna derivada (não vem do arquivo): a UC canônica, presente em TODAS as abas
# com id_uc quando há mapa carregado.
COLUNA_CANONICA = "id_uc_canonico"

# Todas as colunas que o mapa pode produzir em `unidade_consumidora`, na ordem.
COLUNAS_TEMPLATE = [c for i, c, _t, _d in TEMPLATE if i != ITEM_CHAVE]

# Nunca aceitos como coluna extra, por mais que apareçam no arquivo: demanda
# contratada é sempre a da fatura (ver docstring do módulo).
_CAMPOS_BLOQUEADOS = {
    "demanda_contratada_kw", "demanda_geracao_contratada_kw",
    "demandacontratadakw", "demandageracaokw",
    "demandacontratada", "demandageracao",
}

_TIPO_POR_ITEM = {i: t for i, _c, t, _d in TEMPLATE}
_COLUNA_POR_ITEM = {i: c for i, c, _t, _d in TEMPLATE}

_NOME_MAPA = "mapa_uc.json"
_NOME_CONFIG = "config_uc.json"

_CACHE: dict | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Utilidades
# ──────────────────────────────────────────────────────────────────────────────
def _n(txt) -> str:
    """Normaliza um nome de item/coluna para casamento tolerante."""
    s = unicodedata.normalize("NFKD", str(txt))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]+", "", s).lower()


def _so_digitos(v):
    return re.sub(r"\D", "", str(v)) if v is not None else None


def _texto(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "nat") else s


def _ids_do_registro(reg: dict) -> list[str]:
    """Todos os identificadores declarados no `id_uc` do registro."""
    bruto = reg.get(ITEM_CHAVE)
    if bruto is None:
        return []
    if isinstance(bruto, (list, tuple, set)):
        partes = [str(v) for v in bruto]
    else:
        partes = re.split(r"[;,/|]", str(bruto))
    return [p.strip() for p in partes if p and p.strip()]


def _dir_usuario() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = Path(base) / "FaturasEnergia"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


def arquivo_mapa() -> Path:
    return _dir_usuario() / _NOME_MAPA


def _arquivo_config() -> Path:
    return _dir_usuario() / _NOME_CONFIG


# ──────────────────────────────────────────────────────────────────────────────
# Configuração: identificação histórica por medidor
# ──────────────────────────────────────────────────────────────────────────────
# Quando há mapa carregado, a reconciliação por MEDIDOR passa a ser opcional: o
# mapa já diz qual UC é qual, e em muitos cadastros a heurística de medidor só
# acrescenta colunas que ninguém usa. Desligada, `id_uc_atual_medidor`,
# `id_uc_atual_medidor_sem_format` e `id_uc_atual` não são criadas em aba
# nenhuma. Sem mapa, a heurística é a única identificação que existe e continua
# sempre ligada.
def usar_medidor() -> bool:
    if not ativo():
        return True
    try:
        cfg = json.loads(_arquivo_config().read_text(encoding="utf-8"))
        return bool(cfg.get("identificacao_por_medidor", True))
    except Exception:
        return True


def definir_usar_medidor(valor: bool) -> None:
    cfg = {}
    try:
        cfg = json.loads(_arquivo_config().read_text(encoding="utf-8"))
    except Exception:
        pass
    cfg["identificacao_por_medidor"] = bool(valor)
    _arquivo_config().write_text(json.dumps(cfg, ensure_ascii=False, indent=1),
                                 encoding="utf-8")


def colunas_medidor_ativas() -> list[str]:
    """Colunas de identificação por medidor que devem existir na planilha."""
    if usar_medidor():
        return ["id_uc_atual_medidor", "id_uc_atual_medidor_sem_format", "id_uc_atual"]
    return []


# ──────────────────────────────────────────────────────────────────────────────
# Carga do mapa salvo
# ──────────────────────────────────────────────────────────────────────────────
def _construir(registros: list, extras: list) -> dict:
    indice: dict[str, dict] = {}
    avisos: list[str] = []
    for reg in registros:
        if not isinstance(reg, dict):
            continue
        ids = _ids_do_registro(reg)
        if not ids:
            continue
        for ident in ids:
            d = _so_digitos(ident)
            if not d:
                continue
            anterior = indice.get(d)
            if anterior is not None and anterior is not reg:
                avisos.append(
                    f"o identificador {d} aparece em mais de um registro "
                    f"({anterior.get(ITEM_CHAVE)} e {reg.get(ITEM_CHAVE)}); "
                    f"mantido o primeiro.")
                continue
            indice[d] = reg
    return {"registros": registros, "indice": indice, "avisos": avisos,
            "extras": list(extras)}


def _dados() -> dict:
    global _CACHE
    if _CACHE is None:
        registros, extras = [], []
        fp = arquivo_mapa()
        if fp.is_file():
            try:
                bruto = json.loads(fp.read_text(encoding="utf-8"))
                if isinstance(bruto, dict):
                    registros = bruto.get("registros") or []
                    extras = bruto.get("colunas_extras") or []
                elif isinstance(bruto, list):
                    registros = bruto
            except Exception:
                pass
        _CACHE = _construir(registros, extras)
    return _CACHE


def recarregar() -> None:
    global _CACHE
    _CACHE = None


def ativo() -> bool:
    """Há mapa de UCs carregado? Se não, nada do template entra na planilha."""
    return bool(_dados()["registros"])


def registros() -> list[dict]:
    """Os registros do mapa salvo (para edição manual na interface)."""
    return [dict(r) for r in _dados()["registros"]]


def colunas_extras() -> list[str]:
    """Colunas fora do template criadas na importação."""
    return list(_dados()["extras"])


def colunas_ativas() -> list[str]:
    """
    Colunas que o mapa realmente produz em `unidade_consumidora`.

    Só entram as do template que algum registro preenche (item não mapeado na
    importação simplesmente não existe nos registros) mais as extras.
    """
    if not ativo():
        return []
    presentes = set()
    for reg in _dados()["registros"]:
        presentes.update(reg.keys())
    cols = [c for i, c in ((i, _COLUNA_POR_ITEM[i]) for i in ITENS_MAPEAVEIS)
            if i in presentes]
    cols += [e for e in _dados()["extras"] if e in presentes or True]
    return cols


def avisos() -> list[str]:
    return list(_dados()["avisos"])


def metadados() -> dict:
    d = _dados()
    regs = [r for r in d["registros"] if isinstance(r, dict)]
    return {
        "total_ucs": len(regs),
        "operantes": sum(1 for r in regs if r.get("uc_operante")),
        "colunas": colunas_ativas(),
        "extras": list(d["extras"]),
        "arquivo": str(arquivo_mapa()) if arquivo_mapa().is_file() else None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Consulta
# ──────────────────────────────────────────────────────────────────────────────
def buscar(id_uc_extraido) -> dict | None:
    d = _so_digitos(id_uc_extraido)
    if not d:
        return None
    return _dados()["indice"].get(d)


def _converter(valor, tipo):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if tipo is bool:
        if isinstance(valor, bool):
            return valor
        s = _n(valor)
        if s in ("sim", "s", "true", "verdadeiro", "1", "x", "ativo"):
            return True
        if s in ("nao", "n", "false", "falso", "0", "inativo"):
            return False
        return bool(valor)
    if tipo is float:
        try:
            return float(str(valor).replace(".", "").replace(",", ".")
                         if isinstance(valor, str) and "," in str(valor) else valor)
        except (TypeError, ValueError):
            return None
    if isinstance(valor, (list, tuple)):
        return "; ".join(str(v) for v in valor)
    return str(valor)


def campos_unidade_consumidora(id_uc_extraido) -> dict | None:
    """
    Colunas de `unidade_consumidora` para esta UC, ou None se o mapa não a
    conhece. Só devolve as colunas que o mapa realmente tem.
    """
    reg = buscar(id_uc_extraido)
    if reg is None:
        return None
    out = {}
    for item in ITENS_MAPEAVEIS:
        if item in reg:
            out[_COLUNA_POR_ITEM[item]] = _converter(reg.get(item),
                                                     _TIPO_POR_ITEM[item])
    for extra in _dados()["extras"]:
        if extra in reg:
            out[extra] = _converter(reg.get(extra), str)
    return out


def id_canonico(id_uc_extraido) -> str | None:
    """A UC canônica (primeiro identificador do registro, só dígitos)."""
    reg = buscar(id_uc_extraido)
    if reg is None:
        return None
    ids = _ids_do_registro(reg)
    return _so_digitos(ids[0]) if ids else None


# ──────────────────────────────────────────────────────────────────────────────
# Template: geração do modelo
# ──────────────────────────────────────────────────────────────────────────────
def template_exemplo() -> list[dict]:
    """Um registro de exemplo, com todos os itens do template preenchidos."""
    return [{
        "id_uc": "10008414082; 2.742.876.012-19",
        "id_uc_aneel_bordero": "000274287601219",
        "uc_operante": True,
        "medidor_atual_dicionario": "10517719-9",
        "unidade_institucional": "Nome da unidade/órgão atendido",
        "endereco_dicionario": "Rua Exemplo, 100, Bairro, Cidade-UF",
        "participa_rateio": False,
        "demanda_futura_kw": None,
    }]


def gerar_template(caminho: str) -> str:
    """
    Grava o template do mapa de UCs. `.json` gera o modelo JSON; `.xlsx` gera a
    planilha equivalente (uma coluna por item). Devolve o caminho gravado.
    """
    ext = os.path.splitext(caminho)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        import pandas as pd
        itens = [i for i, _c, _t, _d in TEMPLATE]
        pd.DataFrame(template_exemplo(), columns=itens).to_excel(caminho, index=False)
        return caminho
    conteudo = {
        "_leia_me": {
            "descricao": "Mapa de Unidades Consumidoras do Processador de Faturas.",
            "obrigatorio": f"'{ITEM_CHAVE}' é o único item obrigatório.",
            "varios_ids": "id_uc aceita vários identificadores da MESMA UC "
                          "(lista ou separados por ';'); o primeiro é o canônico.",
            "itens": {i: d for i, _c, _t, d in TEMPLATE},
            "extras": "Campos fora desta lista viram colunas novas na planilha, "
                      "com o nome que você escolher na importação.",
        },
        "registros": template_exemplo(),
    }
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(conteudo, f, ensure_ascii=False, indent=1)
    return caminho


# ──────────────────────────────────────────────────────────────────────────────
# Importação: leitura, casamento automático e aplicação do mapeamento
# ──────────────────────────────────────────────────────────────────────────────
def _ler_registros_brutos(caminho: str) -> list[dict]:
    """Lê JSON ou planilha e devolve a lista de registros, sem renomear nada."""
    ext = os.path.splitext(caminho)[1].lower()
    if ext in (".xlsx", ".xlsm", ".csv"):
        import pandas as pd
        if ext == ".csv":
            df = pd.read_csv(caminho, dtype=str, keep_default_na=False)
        else:
            df = pd.read_excel(caminho, dtype=object).fillna("")
        return df.to_dict("records")

    with open(caminho, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        # objeto embrulhando a lista ({"registros": [...]}, {"ucs": [...]})
        candidatas = [v for k, v in data.items()
                      if isinstance(v, list) and v and isinstance(v[0], dict)]
        if candidatas:
            return max(candidatas, key=len)
        # objeto indexado pela própria UC
        internos = {k: v for k, v in data.items()
                    if isinstance(v, dict) and not str(k).startswith("_")}
        if internos:
            out = []
            for chave, reg in internos.items():
                reg = dict(reg)
                reg.setdefault(ITEM_CHAVE, chave)
                out.append(reg)
            return out
    return []


def analisar_arquivo(caminho: str) -> dict:
    """
    Lê o arquivo e prepara o mapeamento, SEM gravar nada. Devolve:

        {
          "registros": [...],            # como vieram
          "campos": [...],               # nomes de campo encontrados
          "auto": {item_template: campo},# casados por nome idêntico
          "pendentes": [...],            # itens do template ainda sem campo
          "sobrando": [...],             # campos do arquivo fora do template
          "avisos": [...],
        }

    Levanta ValueError quando não há registro nenhum ou quando `id_uc` não está
    presente com esse nome exato — ele é a chave e não pode ser adivinhado.
    """
    regs = _ler_registros_brutos(caminho)
    if not regs:
        raise ValueError(
            "Não encontrei nenhum registro de UC no arquivo. Esperado: uma "
            "lista de objetos JSON (ou uma planilha com uma linha por UC).")

    campos: list[str] = []
    for r in regs:
        for k in r:
            if k not in campos and not str(k).startswith("_"):
                campos.append(str(k))

    por_norma = {_n(c): c for c in campos}
    if _n(ITEM_CHAVE) not in por_norma:
        raise ValueError(
            f"O arquivo precisa ter o item '{ITEM_CHAVE}' com esse nome exato — "
            f"é ele que casa o cadastro com a fatura.\n\n"
            f"Campos encontrados: {', '.join(campos[:12])}"
            + (" …" if len(campos) > 12 else ""))

    auto = {}
    for item in ITENS_MAPEAVEIS:
        if _n(item) in por_norma:
            auto[item] = por_norma[_n(item)]
    usados = set(auto.values()) | {por_norma[_n(ITEM_CHAVE)]}

    avisos = []
    sobrando = []
    for c in campos:
        if c in usados:
            continue
        if _n(c) in _CAMPOS_BLOQUEADOS:
            avisos.append(f"o campo '{c}' é ignorado de propósito — demanda "
                          f"contratada vem sempre da fatura, nunca do cadastro.")
            continue
        sobrando.append(c)

    return {
        "registros": regs,
        "campos": campos,
        "chave": por_norma[_n(ITEM_CHAVE)],
        "auto": auto,
        "pendentes": [i for i in ITENS_MAPEAVEIS if i not in auto],
        "sobrando": sobrando,
        "avisos": avisos,
    }


def aplicar_mapeamento(analise: dict, mapeamento: dict | None = None,
                       extras: dict | None = None) -> tuple[list[dict], list[str]]:
    """
    Converte os registros brutos para os nomes do template.

    `mapeamento`: {item_do_template: campo_no_arquivo} — completa/sobrepõe o
    casamento automático. Item que ficar de fora não vira coluna.
    `extras`: {campo_no_arquivo: nome_da_coluna} — campos fora do template que
    devem virar coluna nova.

    Devolve (registros_normalizados, nomes_das_colunas_extras).
    """
    mapa_itens = dict(analise.get("auto") or {})
    mapa_itens.update({k: v for k, v in (mapeamento or {}).items() if v})
    chave = analise["chave"]

    extras_limpos = {}
    for campo, nome in (extras or {}).items():
        nome = _texto(nome) or str(campo)
        if _n(nome) in _CAMPOS_BLOQUEADOS or _n(campo) in _CAMPOS_BLOQUEADOS:
            continue
        extras_limpos[campo] = nome

    saida = []
    for reg in analise["registros"]:
        novo = {}
        ids = reg.get(chave)
        if ids is None or not _texto(ids if not isinstance(ids, (list, tuple)) else ";".join(map(str, ids))):
            continue
        novo[ITEM_CHAVE] = ids
        for item, campo in mapa_itens.items():
            if campo in reg:
                v = _converter(reg.get(campo), _TIPO_POR_ITEM[item])
                if v is not None:
                    novo[item] = v
        for campo, nome in extras_limpos.items():
            if campo in reg:
                v = _converter(reg.get(campo), str)
                if v is not None:
                    novo[nome] = v
        saida.append(novo)
    return saida, list(extras_limpos.values())


def salvar_mapa(registros: list[dict], extras: list[str] | None = None) -> dict:
    """Grava o mapa e recarrega o cache. Devolve os metadados novos."""
    conteudo = {"versao": 1,
                "colunas_extras": list(extras or []),
                "registros": registros}
    arquivo_mapa().write_text(json.dumps(conteudo, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    recarregar()
    return metadados()


def limpar_mapa() -> None:
    """Remove o mapa salvo — volta ao estado 'sem mapa'."""
    try:
        arquivo_mapa().unlink()
    except FileNotFoundError:
        pass
    recarregar()
