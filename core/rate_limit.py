"""
Rate limiting centralizado para la API.

Uso:
  - En main.py: app.state.limiter = limiter  +  registrar el handler de excepción
  - En routers: @limiter.limit("5/minute")   +  añadir 'request: Request' al endpoint

Límites aplicados:
  - /api/compras/buscar → 5 req/minuto por IP  (scraping es costoso y lento)
  - /api/compras/carrito → 30 req/minuto por IP (operaciones rápidas de carrito)
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
