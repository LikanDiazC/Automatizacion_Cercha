"""
Launcher del backend — garantiza que Windows use ProactorEventLoop ANTES
de que uvicorn/FastAPI/Playwright existan en memoria.

Motivo:
  Playwright necesita `subprocess_exec`, que en Windows SOLO funciona con
  `WindowsProactorEventLoopPolicy`. Uvicorn con --reload o apscheduler en
  threads secundarios pueden crear loops con SelectorEventLoop, que lanza
  `NotImplementedError` al intentar spawnear un proceso.

  Este launcher fija la política a nivel de proceso e hijos, antes de
  cualquier import pesado, y luego llama a uvicorn programáticamente.

Uso:
    python run.py            # modo estable SIN reload (recomendado en Windows)
    python run.py --reload   # solo si NO vas a usar el scraper de Playwright

Equivalente a:
    python -m uvicorn main:app --loop asyncio
pero con la política del event loop blindada. El autoreload queda opt-in
porque el reloader de uvicorn en Windows spawnea subprocesos cuyo event loop
termina siendo SelectorEventLoop — y Playwright exige ProactorEventLoop.
"""
from __future__ import annotations

import sys
import asyncio
import argparse


def _force_proactor_loop() -> None:
    """Fuerza ProactorEventLoopPolicy en Windows, idempotente."""
    if sys.platform != "win32":
        return
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception as exc:  # pragma: no cover
        print(f"[run.py] No pude fijar ProactorEventLoopPolicy: {exc}", file=sys.stderr)


# ¡IMPORTANTE! Fijar la política ANTES de importar uvicorn / fastapi / playwright.
_force_proactor_loop()

import uvicorn  # noqa: E402  (import tardío intencional)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cercha backend launcher")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--reload",
        action="store_true",
        help=(
            "Activa autoreload. DESACTIVADO por defecto porque el reloader de uvicorn "
            "en Windows crea subprocesos que rompen Playwright (NotImplementedError en "
            "create_subprocess_exec). Usalo solo si no vas a ejecutar el scraper."
        ),
    )
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    # Re-aseguramos la política tras parsear argumentos (por si argparse tocó algo)
    _force_proactor_loop()

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
        # Forzamos el loop estándar de asyncio (no uvloop; uvloop no existe en Windows
        # y en Linux también es inofensivo para este flag).
        loop="asyncio",
    )


if __name__ == "__main__":
    main()
