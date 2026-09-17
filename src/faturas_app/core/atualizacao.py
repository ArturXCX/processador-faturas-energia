"""Verificação de ATUALIZAÇÃO OBRIGATÓRIA do app distribuído pelo GitHub (Releases).

Ao abrir, o app consulta a última release pública do repositório. Se houver versão mais nova, a interface mostra um aviso
bloqueante com o link para baixar. Sem internet (ou qualquer falha na consulta) o app segue normalmente — a verificação
nunca impede o uso offline. Para desligar (testes, capturas de tela): variável de ambiente FATURAS_SEM_ATUALIZACAO=1."""
from __future__ import annotations

import json
import os
import re
import urllib.request

from .. import __version__

REPO = "ArturXCX/processador-faturas-energia"
URL_API = f"https://api.github.com/repos/{REPO}/releases/latest"
URL_RELEASES = f"https://github.com/{REPO}/releases/latest"
TIMEOUT = 5


def versao_tupla(texto: str) -> tuple[int, ...]:
    """'V.3.1.0', 'v4.0', '4.0.0', 'Versão 2.0' → (3,1,0), (4,0), (4,0,0), (2,0). Vazio → ()."""
    nums = re.findall(r"\d+", str(texto or ""))
    return tuple(int(n) for n in nums[:4])


def mais_nova(tag: str, atual: str = __version__) -> bool:
    a, b = versao_tupla(tag), versao_tupla(atual)
    if not a:
        return False
    n = max(len(a), len(b))
    return tuple(a + (0,) * (n - len(a))) > tuple(b + (0,) * (n - len(b)))


def consultar(timeout: int = TIMEOUT) -> dict | None:
    """Última release: {'tag', 'nome', 'url', 'zip', 'instalador', 'publicada'}; None se offline/falha."""
    req = urllib.request.Request(URL_API, headers={"User-Agent": "faturas-app", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    assets = {a.get("name", ""): a.get("browser_download_url") for a in d.get("assets", [])}
    zip_url = next((u for n, u in assets.items() if n.lower().endswith(".zip")), None)
    setup_url = next((u for n, u in assets.items() if n.lower().endswith(".exe")), None)
    return {"tag": d.get("tag_name", ""), "nome": d.get("name") or d.get("tag_name", ""), "url": d.get("html_url") or URL_RELEASES,
            "zip": zip_url, "instalador": setup_url, "publicada": (d.get("published_at") or "")[:10]}


def verificar(timeout: int = TIMEOUT) -> dict | None:
    """Devolve os dados da release só quando ela é MAIS NOVA que a versão em execução; None nos demais casos
    (inclusive offline). Nunca levanta exceção."""
    if os.environ.get("FATURAS_SEM_ATUALIZACAO"):
        return None
    try:
        rel = consultar(timeout)
    except Exception:
        return None
    if rel and mais_nova(rel["tag"]):
        return rel
    return None
