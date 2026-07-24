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


def aplicar_dfs(dfs: dict, regras: list[dict] | None = None) -> list[str]:
    """
    Aplica os hardcodes (in place) a um conjunto de abas {nome: DataFrame} e
    devolve um relatório legível, uma linha por regra.
    """
    regras = carregar() if regras is None else regras
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
                     regras: list[dict] | None = None) -> list[str]:
    """Lê uma planilha, aplica os hardcodes e grava o resultado em `caminho_saida`."""
    from . import excel_io
    dfs, meta = excel_io.ler_workbook(caminho_entrada)
    relatorio = aplicar_dfs(dfs, regras)
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


def _arquivo() -> Path:
    return _dir() / "hardcodes.json"


def regra_vazia(aba: str = "itens_fatura") -> dict:
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


def padrao() -> list[dict]:
    """Hardcodes que já acompanham o app (resources/hardcodes_padrao.json)."""
    try:
        with resources.files("faturas_app.resources").joinpath(
                "hardcodes_padrao.json").open("r", encoding="utf-8") as f:
            return [_normalizar(r) for r in json.load(f)]
    except Exception:
        return []


def carregar() -> list[dict]:
    """
    Regras salvas. Na PRIMEIRA execução (arquivo ainda inexistente) grava os
    hardcodes padrão — depois disso o arquivo manda, inclusive se o usuário
    apagar tudo (lista vazia é respeitada, não é re-semeada).
    """
    fp = _arquivo()
    if not fp.exists():
        sementes = padrao()
        if sementes:
            try:
                salvar(sementes)
            except Exception:
                pass
        return sementes
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [_normalizar(r) for r in data]


def salvar(regras: list[dict]) -> None:
    limpo = [_normalizar(r) for r in regras]
    _arquivo().write_text(json.dumps(limpo, ensure_ascii=False, indent=1),
                          encoding="utf-8")


def colunas_da_aba(aba: str) -> list[str]:
    """Colunas canônicas sugeridas para a aba (para os menus da interface)."""
    return schema.all_canonical(aba)


def abas_disponiveis() -> list[str]:
    return list(schema.SHEET_ORDER)


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
