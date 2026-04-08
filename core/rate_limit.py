"""
Rate limiting centralizado para la API.

Uso:
  - En main.py: app.state.limiter = limiter  +  registrar el handler de excepción
  - En routers: @limiter.limit("5/minute")   +  añadir 'request: Request' al endpoint

Límites aplicados:
  - /api/compras/buscar → 5 req/minuto por IP  (scraping es costoso y lento)
  - /api/compras/carrito → 30 req/minuto por IP (operaciones rápidas de carrito)
"""

from __future__ import annotations

import logging
from typing import Optional

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from core.security import decode_token

logger = logging.getLogger(__name__)


def _extract_user_id(request: Request) -> Optional[int]:
    """
    Intenta extraer el user_id del JWT del header Authorization SIN tocar
    la base de datos. Si falla por cualquier motivo (header ausente, token
    inválido/expirado), devuelve None y el caller cae a IP.
    """
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        payload = decode_token(token, expected_type="access")
    except Exception:
        return None
    try:
        uid = int(payload.get("sub"))
        return uid if uid > 0 else None
    except (TypeError, ValueError):
        return None


def rate_limit_key(request: Request) -> str:
    """
    Key func dual:
      - Si hay JWT válido → "user:<id>"  (evita NAT-bypass entre usuarios)
      - Si no           → "ip:<remote>" (comportamiento original)
    """
    uid = _extract_user_id(request)
    if uid is not None:
        return f"user:{uid}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=rate_limit_key)
