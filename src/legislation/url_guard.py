"""Validador de URL oficial por construção (.gov.br, .leg.br, .jus.br, .mp.br)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

URL_OFICIAL_REGEX = re.compile(
    r"^https?://[^/@\s]+\.(gov|leg|jus|mp)\.br(?::\d+)?(?:/|$)",
    re.IGNORECASE,
)


class DominioNaoOficialError(ValueError):
    """Lançada quando uma URL não pertence a domínio oficial brasileiro permitido."""


def validar_url_oficial(url: str) -> str:
    """Valida estritamente que a URL pertence a .gov.br, .leg.br, .jus.br ou .mp.br."""
    if not isinstance(url, str) or not url.strip():
        raise DominioNaoOficialError("URL oficial vazia ou inválida.")

    limpa = url.strip()
    if not URL_OFICIAL_REGEX.match(limpa):
        raise DominioNaoOficialError(
            f"URL bloqueada pela whitelist oficial (.gov.br/.leg.br/.jus.br/.mp.br): {limpa}"
        )

    parsed = urlparse(limpa)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise DominioNaoOficialError(f"Esquema não permitido: {parsed.scheme}")
    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        raise DominioNaoOficialError(f"URL com credenciais/userinfo bloqueada: {limpa}")

    hostname = (parsed.hostname or "").lower()
    if not hostname.endswith((".gov.br", ".leg.br", ".jus.br", ".mp.br")):
        raise DominioNaoOficialError(f"Hostname fora da whitelist oficial: {hostname}")

    return limpa


@dataclass(frozen=True)
class OfficialURL:
    """Tipo seguro que garante URL oficial válida por construção."""

    url: str

    def __post_init__(self) -> None:
        validada = validar_url_oficial(self.url)
        object.__setattr__(self, "url", validada)

    def __str__(self) -> str:
        return self.url
