"""Que documento de água é este? Fornecedor pelo CNPJ/nome impresso e tipo (fatura, borderô Saneago, analítica Saneago).

O nome da pasta/arquivo entra só como DICA de desempate: a decisão vem do conteúdo. Isso evita que um PDF colocado na
pasta errada seja lido pelo extrator errado (o roteador original decidia pelo nome da pasta)."""
from __future__ import annotations

import re

from . import schema_agua as S
from .texto import digitos, sem_acento

TIPO_FATURA = "fatura_agua"
TIPO_BORDERO = "bordero_agua"
TIPO_ANALITICA = "analitica_agua"

# CNPJ (só dígitos) → fornecedor
CNPJS = {d["cnpj"]: f for f, d in S.FORNECEDORES.items() if d["cnpj"]}

# palavras-chave (texto sem acento, maiúsculo) → fornecedor, em ordem de especificidade
PALAVRAS = [
    ("SANEAMENTO DE GOIAS", "SANEAGO"),
    ("SANEAGO", "SANEAGO"),
    ("AGENCIA DE SANEAMENTO DE SENADOR CANEDO", "SANESC"),
    ("SANESC", "SANESC"),
    ("SAO SIMAO SANEAMENTO", "SAO_SIMAO_SA"),
    ("SAO SIMAO SAN", "SAO_SIMAO_SA"),
    ("AGUAS DE IPAMERI", "AGUAS_IPAMERI"),
    ("BURITI ALEGRE AMBIENTAL", "BURITI_ALEGRE_AMBIENTAL"),
    ("LEOPOLDO DE BULHOES", "SAAE_LEOPOLDO_BULHOES"),
    ("LEOPOLDO DE BULH", "SAAE_LEOPOLDO_BULHOES"),
    ("PREFEITURA MUNICIPAL DE MINEIROS", "SAAE_MINEIROS"),
    ("SAAE MINEIROS", "SAAE_MINEIROS"),
    ("MINEIROS - GO", "SAAE_MINEIROS"),
    ("CORUMBA DE GOIAS", "SAAE_CORUMBA"),
    ("ESGOTO - CORUMBA", "SAAE_CORUMBA"),
    ("SAAE CORUMBA", "SAAE_CORUMBA"),
    ("ABADIANIA", "SAAE_ABADIANIA"),
    ("CATALAO", "SAE_CATALAO"),
    ("DEMAE PANAMA", "DEMAE_PANAMA"),
    ("DEMAEP", "DEMAE_PANAMA"),
    ("CALDAS NOVAS", "DEMAE_CALDAS_NOVAS"),
    ("DEMAE", "DEMAE_CALDAS_NOVAS"),
    ("CODEGO", "CODEGO"),
]
_RE_CNPJ = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")


def _up(s: str) -> str:
    return sem_acento(s or "").upper()


def fornecedor(texto: str, nome_arquivo: str = "", pasta: str = "") -> str | None:
    """Fornecedor pelo CNPJ impresso; senão por palavras-chave do texto; por último pelo nome do arquivo/pasta."""
    up = _up(texto)
    for m in _RE_CNPJ.finditer(up):
        f = CNPJS.get(digitos(m.group(0)))
        if f:
            return f
    for chave, f in PALAVRAS:
        if chave in up:
            return f
    dica = _up(nome_arquivo) + " " + _up(pasta)
    for chave, f in PALAVRAS:
        if chave in dica:
            return f
    if "PANAMA" in dica and "DEMAE" in dica:
        return "DEMAE_PANAMA"
    if "SAE" in dica.split() and "SAAE" not in dica:
        return "SAE_CATALAO"
    if "IPAMERI" in dica:
        return "AGUAS_IPAMERI"
    if "BURITI" in dica:
        return "BURITI_ALEGRE_AMBIENTAL"
    if "SIMAO" in dica or "SSSA" in dica:
        return "SAO_SIMAO_SA"
    if "MINEIROS" in dica:
        return "SAAE_MINEIROS"
    if "CORUMB" in dica:
        return "SAAE_CORUMBA"
    if "LEOPOLDO" in dica or "BULH" in dica:
        return "SAAE_LEOPOLDO_BULHOES"
    return None


def tipo(texto: str, forn: str | None, nome_arquivo: str = "") -> str:
    """fatura_agua | bordero_agua | analitica_agua (os dois últimos só existem na Saneago)."""
    up = _up(texto)
    if forn == "SANEAGO" or "SANEAGO" in up or "SANEAMENTO DE GOIAS" in up:
        if "FATURA ANALITICA" in up or "ANALITICA DE ORGAO PUBLICO" in up:
            return TIPO_ANALITICA
        if ("ORGAO AGRUPADOR" in up or "CONTAS AGRUPADAS" in up or re.search(r"CONTA\s*-?\s*DV", up)
                or "COMUNICADO PARA PAGAMENTO" in up):
            return TIPO_BORDERO
        dica = _up(nome_arquivo)
        if "ANALIT" in dica:
            return TIPO_ANALITICA
        return TIPO_BORDERO
    return TIPO_FATURA


def eh_documento_de_agua(texto: str, nome_arquivo: str = "", pasta: str = "") -> bool:
    """Heurística rápida para o classificador do bot: há um fornecedor de água reconhecível E vocabulário de água."""
    f = fornecedor(texto, nome_arquivo, pasta)
    if not f:
        return False
    up = _up(texto)
    return any(k in up for k in ("AGUA", "ESGOTO", "HIDROMETRO", "SANEAMENTO", "M3", "CONSUMO FATURADO", "FAES"))
