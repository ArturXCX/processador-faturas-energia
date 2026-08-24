"""
Hardcodes: regras "SE → ENTÃO" cadastradas pelo usuário.

Diferente de `correcoes.py` (correções de EXTRAÇÃO, embutidas no app), um
hardcode conserta um erro que veio da PRÓPRIA FATURA emitida pela concessionária:
o processador leu certo, o dado é que está errado na origem. Por isso as regras
ficam sob controle do usuário — cadastradas na aba "Hardcodes" e persistidas em
%APPDATA%/FaturasEnergia/hardcodes.json (mesma pasta de `equivalencias.py`).

Estrutura de uma regra::

    {
      "id": "…", "nome": "…", "aba": "itens_fatura", "ativo": true,
      "grupos": [                       # grupos ligados entre si por E
        {"operador": "OU",              # ligação DENTRO do grupo: "E" ou "OU"
         "condicoes": [{"coluna": "item", "operador": "igual", "valor": "X"}]}
      ],
      "acoes": [{"coluna": "item", "valor": "CONSUMO"}]
    }

o que expressa exatamente `SE (X=1 OU X=2) E (Y≠3) ENTÃO Z=0`: cada parêntese é
um grupo, e novos grupos/condições podem ser acrescentados sem limite.

Casamento TOLERANTE (mesmo princípio de `correcoes.py`): nomes de aba e de coluna
e os valores comparados são normalizados (maiúsculas, sem acento, espaços
colapsados) e, quando os dois lados são numéricos, a comparação é numérica. Assim
uma regra escrita como `Postos Horários = FORA PONTA` casa com a coluna
`Postos horarios`, e `quantidade = 30` casa tanto com "30" quanto com 30.0.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
import uuid
from importlib import resources
from pathlib import Path

import pandas as pd

from . import schema

# ──────────────────────────────────────────────────────────────────────────────
# Operadores das condições (código -> rótulo exibido na interface)
# ──────────────────────────────────────────────────────────────────────────────
OPERADORES = {
    "igual":        "é igual a",
    "diferente":    "é diferente de",
    "esta_em":      "é um de (lista)",
    "nao_esta_em":  "não é nenhum de (lista)",
    "contem":       "contém",
    "nao_contem":   "não contém",
    "maior_que":    "é maior que",
    "menor_que":    "é menor que",
    "vazio":        "está vazio",
    "nao_vazio":    "não está vazio",
}

# Operadores que não usam o campo "valor" e os que leem uma LISTA de valores.
OPERADORES_SEM_VALOR = {"vazio", "nao_vazio"}
OPERADORES_LISTA = {"esta_em", "nao_esta_em"}
SEPARADOR_LISTA = ";"

# Ligação entre condições dentro de um grupo.
LIGACOES = ["E", "OU"]

# Sufixo do arquivo gerado ao aplicar os hardcodes sobre uma planilha enviada.
SUFIXO_SAIDA = "_hardcodes"


# ──────────────────────────────────────────────────────────────────────────────
# Domínios: "faturas" (padrão) e "borderos" têm esquemas de abas/colunas e
# arquivos de persistência PRÓPRIOS, para que as regras de um não colidam com
# as do outro nem apareçam nos menus errados da interface.
# ──────────────────────────────────────────────────────────────────────────────
def _dominio_cfg(dominio: str) -> dict:
    if dominio == "borderos":
        from . import borderos as _borderos
        return {
            "arquivo": "hardcodes_borderos.json",
            "abas": list(_borderos.SHEET_ORDER),
            "colunas": {
                _borderos.ABA_BORDEROS: _borderos.BORDERO_COLS,
                _borderos.ABA_UNIDADES: _borderos.UNIDADE_COLS,
                _borderos.ABA_RESUMO: _borderos.RESUMO_COLS,
            },
            "aba_padrao": _borderos.ABA_UNIDADES,
        }
    return {
        "arquivo": "hardcodes.json",
        "abas": list(schema.SHEET_ORDER),
        "colunas": {aba: schema.all_canonical(aba) for aba in schema.SHEET_ORDER},
        "aba_padrao": "itens_fatura",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Normalização / comparação tolerante
# ──────────────────────────────────────────────────────────────────────────────
def _vazio(v) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return str(v).strip() == ""


def _chave(v) -> str:
    """Maiúsculas, sem acento, espaços colapsados — para comparar texto."""
    s = unicodedata.normalize("NFKD", str(v))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().upper()


def _chave_col(nome) -> str:
    """Como `_chave`, mas também sem espaços/sublinhados — para casar COLUNAS
    ('Postos Horários' ≡ 'Postos horarios' ≡ 'postos_horarios')."""
    return re.sub(r"[\s_]+", "", _chave(nome))


_RE_NUM = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")


def _num(v) -> float | None:
    """Valor como float, ou None se não for numérico."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return None if pd.isna(v) else float(v)
    s = str(v).strip().replace(" ", "")
    if not _RE_NUM.match(s):
        return None
    return float(s.replace(",", "."))


def _iguais(a, b) -> bool:
    """Igualdade numérica quando ambos são números; senão, textual tolerante."""
    na, nb = _num(a), _num(b)
    if na is not None and nb is not None:
        return abs(na - nb) < 1e-9
    return _chave(a) == _chave(b)


def _testar(valor, operador: str, alvo) -> bool:
    """Avalia UMA condição sobre o valor de uma célula."""
    if operador == "vazio":
        return _vazio(valor)
    if operador == "nao_vazio":
        return not _vazio(valor)
    if operador == "igual":
        return _iguais(valor, alvo)
    if operador == "diferente":
        return not _iguais(valor, alvo)
    if operador == "esta_em":
        return any(_iguais(valor, a) for a in alvo)
    if operador == "nao_esta_em":
        return not any(_iguais(valor, a) for a in alvo)
    if operador == "contem":
        return _chave(alvo) in _chave(valor)
    if operador == "nao_contem":
        return _chave(alvo) not in _chave(valor)
    if operador in ("maior_que", "menor_que"):
        nv, na = _num(valor), _num(alvo)
        if nv is None or na is None:
            return False
        return nv > na if operador == "maior_que" else nv < na
    return False


def _valor_tipado(v):
    """Converte o valor da AÇÃO: '' → vazio, '0' → 0, '1,5' → 1.5, resto → texto."""
    s = str(v if v is not None else "").strip()
    if s == "":
        return None
    n = _num(s)
    if n is None:
        return s
    if n.is_integer() and "." not in s and "," not in s:
        return int(n)
    return n


# ──────────────────────────────────────────────────────────────────────────────
# Resolução tolerante de abas e colunas
# ──────────────────────────────────────────────────────────────────────────────
def _resolver_aba(dfs: dict, nome: str) -> str | None:
    if nome in dfs:
        return nome
    alvo = _chave_col(nome)
    for aba in dfs:
        if _chave_col(aba) == alvo:
            return aba
    return None


def _resolver_coluna(df: pd.DataFrame, nome: str) -> str | None:
    if nome in df.columns:
        return nome
    alvo = _chave_col(nome)
    for c in df.columns:
        if _chave_col(c) == alvo:
            return c
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Avaliação e aplicação
# ──────────────────────────────────────────────────────────────────────────────
def _mask_condicao(df: pd.DataFrame, cond: dict) -> pd.Series | None:
    """Máscara booleana de UMA condição; None se a coluna não existe na aba."""
    col = _resolver_coluna(df, cond.get("coluna", ""))
    if col is None:
        return None
    op = cond.get("operador", "igual")
    alvo = cond.get("valor", "")
    if op in OPERADORES_LISTA:
        alvo = [p.strip() for p in str(alvo).split(SEPARADOR_LISTA) if p.strip()]
    return df[col].map(lambda v: _testar(v, op, alvo))


def _mask_regra(df: pd.DataFrame, regra: dict) -> tuple[pd.Series | None, str | None]:
    """Máscara do SE inteiro: grupos combinados por E, condições internas por E/OU."""
    total = None
    for grupo in regra.get("grupos", []):
        interno = str(grupo.get("operador") or "E").upper()
        sub = None
        for cond in grupo.get("condicoes", []):
            if not str(cond.get("coluna", "")).strip():
                continue
            m = _mask_condicao(df, cond)
            if m is None:
                return None, f"coluna '{cond.get('coluna')}' não existe nesta aba"
            sub = m if sub is None else ((sub | m) if interno == "OU" else (sub & m))
        if sub is None:
            continue
        total = sub if total is None else (total & sub)
    if total is None:
        return None, "regra sem condições"
    return total, None


def _atribuir(df: pd.DataFrame, mask: pd.Series, col: str, valor) -> None:
    """Grava `valor` nas linhas de `mask`, promovendo a coluna a object quando o
    novo valor não couber no dtype atual (evita o upcast implícito do pandas)."""
    serie = df[col]
    if not pd.api.types.is_object_dtype(serie) and not isinstance(valor, (int, float)):
        df[col] = serie.astype(object)
    df.loc[mask, col] = valor


def aplicar_dfs(dfs: dict, regras: list[dict] | None = None,
                dominio: str = "faturas") -> list[str]:
    """
    Aplica os hardcodes (in place) a um conjunto de abas {nome: DataFrame} e
    devolve um relatório legível, uma linha por regra.
    """
    regras = carregar(dominio) if regras is None else regras
    relatorio: list[str] = []
    for regra in regras:
        if not regra.get("ativo", True):
            continue
        nome = regra.get("nome") or "(sem nome)"
        aba_pedida = regra.get("aba", "")
        aba = _resolver_aba(dfs, aba_pedida)
        if aba is None:
            relatorio.append(f"⚠ {nome}: aba '{aba_pedida}' não encontrada — regra ignorada.")
            continue
        df = dfs.get(aba)
        if df is None or df.empty:
            relatorio.append(f"• {aba} · {nome}: aba vazia — 0 linha(s).")
            continue
        mask, erro = _mask_regra(df, regra)
        if erro:
            relatorio.append(f"⚠ {aba} · {nome}: {erro} — regra ignorada.")
            continue
        n = int(mask.sum())
        if n:
            for acao in regra.get("acoes", []):
                if not str(acao.get("coluna", "")).strip():
                    continue
                col = _resolver_coluna(df, acao["coluna"])
                if col is None:
                    relatorio.append(
                        f"⚠ {aba} · {nome}: coluna de destino '{acao['coluna']}' "
                        "não existe — ação ignorada.")
                    continue
                _atribuir(df, mask, col, _valor_tipado(acao.get("valor", "")))
        relatorio.append(f"• {aba} · {nome}: {n} linha(s) alterada(s).")
    return relatorio


def aplicar_planilha(caminho_entrada: str, caminho_saida: str,
                     regras: list[dict] | None = None,
                     dominio: str = "faturas") -> list[str]:
    """Lê uma planilha, aplica os hardcodes e grava o resultado em `caminho_saida`."""
    if dominio == "borderos":
        from . import borderos as _borderos
        dfs = _borderos.ler_planilha(caminho_entrada)
        relatorio = aplicar_dfs(dfs, regras, dominio)
        _borderos.escrever_dfs(dfs, caminho_saida)
        return relatorio
    from . import excel_io
    dfs, meta = excel_io.ler_workbook(caminho_entrada)
    relatorio = aplicar_dfs(dfs, regras, dominio)
    excel_io.escrever_workbook(dfs, meta or {}, caminho_saida)
    return relatorio


def caminho_saida_padrao(caminho_entrada: str) -> str:
    """'…/x.xlsx' → '…/x_hardcodes.xlsx' (mesmo nome, com o sufixo ao final)."""
    base, ext = os.path.splitext(caminho_entrada)
    return f"{base}{SUFIXO_SAIDA}{ext or '.xlsx'}"


# ──────────────────────────────────────────────────────────────────────────────
# Persistência (%APPDATA%/FaturasEnergia/hardcodes.json)
# ──────────────────────────────────────────────────────────────────────────────
def _dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = Path(base) / "FaturasEnergia"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


def _arquivo(dominio: str = "faturas") -> Path:
    return _dir() / _dominio_cfg(dominio)["arquivo"]


def regra_vazia(aba: str | None = None, dominio: str = "faturas") -> dict:
    aba = aba or _dominio_cfg(dominio)["aba_padrao"]
    return {
        "id": uuid.uuid4().hex,
        "nome": "",
        "aba": aba,
        "ativo": True,
        "grupos": [{"operador": "E", "condicoes": [
            {"coluna": "", "operador": "igual", "valor": ""}]}],
        "acoes": [{"coluna": "", "valor": ""}],
    }


def _normalizar(regra: dict) -> dict:
    grupos = []
    for g in regra.get("grupos") or []:
        conds = [{"coluna": str(c.get("coluna", "")),
                  "operador": c.get("operador", "igual") if c.get("operador") in OPERADORES else "igual",
                  "valor": str(c.get("valor", ""))}
                 for c in (g.get("condicoes") or [])]
        op = str(g.get("operador") or "E").upper()
        grupos.append({"operador": op if op in LIGACOES else "E", "condicoes": conds})
    acoes = [{"coluna": str(a.get("coluna", "")), "valor": str(a.get("valor", ""))}
             for a in (regra.get("acoes") or [])]
    return {
        "id": str(regra.get("id") or uuid.uuid4().hex),
        "nome": str(regra.get("nome", "")).strip(),
        "aba": str(regra.get("aba", "")).strip(),
        "ativo": bool(regra.get("ativo", True)),
        "grupos": grupos,
        "acoes": acoes,
    }


def padrao(dominio: str = "faturas") -> list[dict]:
    """
    Nenhum hardcode acompanha o app — SEMPRE vazio, nos dois domínios.

    Antes o app trazia embutidas as regras do TJGO (resources/hardcodes_padrao.json),
    o que impunha correções de UMA instituição a todo mundo que instalasse o
    programa. Agora o conjunto de regras nasce vazio e cada instituição importa o
    seu, por planilha (`importar_planilha`). As regras que vinham embutidas
    continuam disponíveis como planilha, para quem quiser reimportá-las.
    """
    return []


def carregar(dominio: str = "faturas") -> list[dict]:
    """
    Regras salvas do domínio (faturas/borderos). Sem arquivo, começa VAZIO —
    o app não traz nenhuma regra embutida (ver `padrao`).
    """
    fp = _arquivo(dominio)
    if not fp.exists():
        return []
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [_normalizar(r) for r in data]


def salvar(regras: list[dict], dominio: str = "faturas") -> None:
    limpo = [_normalizar(r) for r in regras]
    _arquivo(dominio).write_text(json.dumps(limpo, ensure_ascii=False, indent=1),
                                 encoding="utf-8")


def colunas_da_aba(aba: str, dominio: str = "faturas") -> list[str]:
    """Colunas canônicas sugeridas para a aba (para os menus da interface)."""
    return list(_dominio_cfg(dominio)["colunas"].get(aba, []))


def abas_disponiveis(dominio: str = "faturas") -> list[str]:
    return list(_dominio_cfg(dominio)["abas"])


def resumo_texto(regra: dict) -> str:
    """Descrição em uma linha: 'SE (…) E (…) ENTÃO x = y'."""
    partes = []
    for g in regra.get("grupos", []):
        lig = f" {g.get('operador', 'E')} "
        conds = [f"{c.get('coluna', '?')} {OPERADORES.get(c.get('operador'), '?')}"
                 + ("" if c.get("operador") in OPERADORES_SEM_VALOR
                    else f" “{c.get('valor', '')}”")
                 for c in g.get("condicoes", []) if str(c.get("coluna", "")).strip()]
        if conds:
            partes.append(f"({lig.join(conds)})")
    acoes = [f"{a.get('coluna', '?')} = “{a.get('valor', '')}”"
             for a in regra.get("acoes", []) if str(a.get("coluna", "")).strip()]
    if not partes or not acoes:
        return "(regra incompleta)"
    return "SE " + " E ".join(partes) + " ENTÃO " + ", ".join(acoes)


# ──────────────────────────────────────────────────────────────────────────────
# Importação / exportação por PLANILHA
# ──────────────────────────────────────────────────────────────────────────────
# Uma regra tem N grupos × M condições e K ações — uma árvore, que não cabe numa
# única linha de planilha. O formato usa DUAS abas, ligadas pelo `id`:
#
#   aba 'hardcodes' -> 1 linha por CONDIÇÃO
#       id · nome · aba · ativo · grupo · ligacao · coluna · operador · valor
#   aba 'acoes'     -> 1 linha por AÇÃO
#       id · coluna · valor
#
# A leitura é TOLERANTE: nomes de coluna casam sem acento/maiúsculas/espaços, o
# operador pode vir pelo código (`igual`) ou pelo rótulo da interface ("é igual
# a"), `ativo` aceita sim/não/true/false/1/0, e o que faltar recebe um padrão
# razoável (sem `grupo`, tudo vira um grupo só; sem `ligacao`, "E"; sem `id`, um
# id derivado do nome). Nada disso interrompe a importação: o que não deu para
# entender vira aviso no relatório, que a interface mostra ANTES de aplicar.
ABA_IMPORT_REGRAS = "hardcodes"
ABA_IMPORT_ACOES = "acoes"

# Rótulo exibido -> código do operador (a importação aceita os dois).
_ROTULO_PARA_OPERADOR = {_chave(v): k for k, v in OPERADORES.items()}

_VERDADEIRO = {"SIM", "S", "TRUE", "VERDADEIRO", "1", "X", "ATIVO"}
_FALSO = {"NAO", "N", "FALSE", "FALSO", "0", "", "INATIVO"}


def _col(df, *nomes):
    """Acha a coluna do DataFrame por qualquer um dos nomes (casamento tolerante)."""
    alvo = {_chave_col(n) for n in nomes}
    for c in df.columns:
        if _chave_col(c) in alvo:
            return c
    return None


def _texto(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "nat") else s


def _operador(v):
    """Aceita o código ('igual') ou o rótulo da interface ('é igual a')."""
    s = _texto(v)
    if not s:
        return None
    if s in OPERADORES:
        return s
    return _ROTULO_PARA_OPERADOR.get(_chave(s))


def _ativo(v, padrao=True) -> bool:
    s = _chave(_texto(v))
    if not s:
        return padrao
    if s in _VERDADEIRO:
        return True
    if s in _FALSO:
        return False
    return padrao


def exportar_planilha(caminho: str, regras=None, dominio: str = "faturas") -> int:
    """
    Grava as regras no formato de duas abas descrito acima e devolve quantas
    regras saíram. Serve de backup e de MODELO: exporte, edite no Excel e
    reimporte com `importar_planilha`.
    """
    import pandas as pd

    regras = carregar(dominio) if regras is None else [_normalizar(r) for r in regras]
    linhas_cond, linhas_acao = [], []
    for r in regras:
        grupos = r.get("grupos") or []
        if not grupos:
            linhas_cond.append({"id": r["id"], "nome": r["nome"], "aba": r["aba"],
                                "ativo": "SIM" if r["ativo"] else "NAO",
                                "grupo": 1, "ligacao": "E",
                                "coluna": "", "operador": "", "valor": ""})
        for i, g in enumerate(grupos, start=1):
            lig = g.get("operador", "E")
            for c in (g.get("condicoes") or []):
                linhas_cond.append({
                    "id": r["id"], "nome": r["nome"], "aba": r["aba"],
                    "ativo": "SIM" if r["ativo"] else "NAO",
                    "grupo": i, "ligacao": lig,
                    "coluna": c.get("coluna", ""),
                    "operador": c.get("operador", ""),
                    "valor": c.get("valor", ""),
                })
        for a in (r.get("acoes") or []):
            linhas_acao.append({"id": r["id"], "coluna": a.get("coluna", ""),
                                "valor": a.get("valor", "")})

    cols_cond = ["id", "nome", "aba", "ativo", "grupo", "ligacao",
                 "coluna", "operador", "valor"]
    cols_acao = ["id", "coluna", "valor"]
    with pd.ExcelWriter(caminho, engine="openpyxl") as w:
        pd.DataFrame(linhas_cond, columns=cols_cond).to_excel(
            w, sheet_name=ABA_IMPORT_REGRAS, index=False)
        pd.DataFrame(linhas_acao, columns=cols_acao).to_excel(
            w, sheet_name=ABA_IMPORT_ACOES, index=False)
    return len(regras)


def _abas_da_planilha(caminho: str) -> dict:
    """Lê .xlsx/.xlsm/.csv e devolve {nome_da_aba: DataFrame}."""
    import pandas as pd

    ext = os.path.splitext(caminho)[1].lower()
    if ext == ".csv":
        return {ABA_IMPORT_REGRAS: pd.read_csv(caminho, dtype=str,
                                               keep_default_na=False)}
    xls = pd.ExcelFile(caminho, engine="openpyxl")
    return {nome: pd.read_excel(xls, sheet_name=nome, dtype=str).fillna("")
            for nome in xls.sheet_names}


def _achar_aba(abas: dict, *nomes):
    alvo = {_chave_col(n) for n in nomes}
    for nome, df in abas.items():
        if _chave_col(nome) in alvo:
            return df
    return None


def importar_planilha(caminho: str, dominio: str = "faturas"):
    """
    Lê uma planilha de hardcodes e devolve `(regras, relatorio)`.

    NÃO grava nada — quem chama decide substituir ou mesclar. O relatório é uma
    lista de mensagens contando o que foi entendido e o que foi ignorado; é ele
    que torna a importação "inteligente" na prática, porque o usuário confere o
    que o app leu antes de aplicar.

    Levanta ValueError só quando o arquivo não tem como ser interpretado.
    """
    abas = _abas_da_planilha(caminho)
    df = _achar_aba(abas, ABA_IMPORT_REGRAS, "regras", "hardcode", "condicoes")
    if df is None and len(abas) == 1:
        df = next(iter(abas.values()))          # arquivo de aba única
    if df is None:
        raise ValueError(
            "Nao encontrei a aba de regras. O arquivo precisa ter uma aba "
            "'hardcodes' (e, opcionalmente, uma aba 'acoes' com as acoes).")

    c_id = _col(df, "id", "identificador")
    c_nome = _col(df, "nome", "regra", "descricao")
    c_aba = _col(df, "aba", "planilha", "tabela")
    c_ativo = _col(df, "ativo", "ativa", "habilitado")
    c_grupo = _col(df, "grupo", "bloco", "parenteses")
    c_lig = _col(df, "ligacao", "operador_grupo", "e_ou")
    c_col = _col(df, "coluna", "campo")
    c_op = _col(df, "operador", "condicao", "comparacao")
    c_val = _col(df, "valor", "valores")
    if c_col is None or c_op is None:
        raise ValueError(
            "A aba de regras precisa ter ao menos as colunas 'coluna' e "
            "'operador'. Dica: exporte os hardcodes atuais para ver o formato.")

    abas_validas = {_chave_col(a) for a in abas_disponiveis(dominio)}
    relatorio, avisos = [], []
    regras: dict = {}
    ordem: list = []

    for i, row in df.iterrows():
        linha = i + 2                       # +1 cabecalho, +1 base 1
        nome = _texto(row[c_nome]) if c_nome else ""
        rid = _texto(row[c_id]) if c_id else ""
        if not rid:
            rid = "imp_" + _chave(nome or "linha%d" % linha).lower()[:40]
        operador = _operador(row[c_op])
        coluna = _texto(row[c_col])
        if operador is None and not coluna:
            continue                        # linha em branco: ignora em silencio
        if operador is None:
            avisos.append("linha %d: operador %r nao reconhecido - condicao ignorada."
                          % (linha, _texto(row[c_op])))
            continue

        if rid not in regras:
            aba = _texto(row[c_aba]) if c_aba else ""
            if aba and _chave_col(aba) not in abas_validas:
                avisos.append("linha %d: aba %r nao existe no dominio %r - a regra "
                              "foi importada assim mesmo." % (linha, aba, dominio))
            regras[rid] = {"id": rid, "nome": nome or rid,
                           "aba": aba or _dominio_cfg(dominio)["aba_padrao"],
                           "ativo": _ativo(row[c_ativo]) if c_ativo else True,
                           "grupos": [], "acoes": []}
            ordem.append(rid)

        try:
            bruto = _texto(row[c_grupo]) if c_grupo else ""
            n_grupo = int(float(bruto)) if bruto else 1
        except ValueError:
            n_grupo = 1
        n_grupo = max(1, n_grupo)
        lig = (_texto(row[c_lig]).upper() if c_lig else "") or "E"
        if lig not in LIGACOES:
            lig = "E"

        grupos = regras[rid]["grupos"]
        while len(grupos) < n_grupo:
            grupos.append({"operador": lig, "condicoes": []})
        grupo = grupos[n_grupo - 1]
        grupo["operador"] = lig
        cond = {"coluna": coluna, "operador": operador}
        if operador not in OPERADORES_SEM_VALOR:
            cond["valor"] = _texto(row[c_val]) if c_val else ""
        grupo["condicoes"].append(cond)

    # ── acoes ────────────────────────────────────────────────────────────────
    df_a = _achar_aba(abas, ABA_IMPORT_ACOES, "acao", "then", "entao")
    if df_a is not None and len(df_a):
        a_id = _col(df_a, "id", "identificador")
        a_col = _col(df_a, "coluna", "campo")
        a_val = _col(df_a, "valor", "valores")
        if a_col is None:
            avisos.append("A aba de acoes nao tem a coluna 'coluna' - acoes ignoradas.")
        else:
            for i, row in df_a.iterrows():
                rid = _texto(row[a_id]) if a_id else (ordem[0] if len(ordem) == 1 else "")
                coluna = _texto(row[a_col])
                if not coluna:
                    continue
                if rid not in regras:
                    avisos.append("acoes, linha %d: id %r nao corresponde a nenhuma "
                                  "regra - ignorada." % (i + 2, rid))
                    continue
                regras[rid]["acoes"].append(
                    {"coluna": coluna, "valor": _texto(row[a_val]) if a_val else ""})
    elif df_a is None:
        avisos.append("Sem a aba 'acoes': as regras vieram sem acao (elas nao mudam "
                      "nada ate voce definir o ENTAO).")

    final = [_normalizar(regras[r]) for r in ordem]
    sem_acao = [r["nome"] for r in final if not r["acoes"]]
    n_cond = sum(len(g.get("condicoes", [])) for r in final for g in r.get("grupos", []))
    n_acao = sum(len(r.get("acoes", [])) for r in final)
    relatorio.append("%d regra(s) lida(s) de %s."
                     % (len(final), os.path.basename(caminho)))
    relatorio.append("%d condicao(oes) e %d acao(oes)." % (n_cond, n_acao))
    if sem_acao:
        relatorio.append("⚠ %d regra(s) sem acao: %s%s"
                         % (len(sem_acao), ", ".join(sem_acao[:5]),
                            " …" if len(sem_acao) > 5 else ""))
    relatorio += ["⚠ " + a for a in avisos[:20]]
    if len(avisos) > 20:
        relatorio.append("⚠ … e mais %d aviso(s)." % (len(avisos) - 20))
    return final, relatorio
