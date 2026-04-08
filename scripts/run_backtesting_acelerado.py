"""
run_backtesting_acelerado.py — Estudio Acelerado / Backtesting offline
=======================================================================

Objetivo
--------
Re-procesar MASIVAMENTE el catálogo histórico (Sodimac + Easy + ...) a través
de las capas DETERMINISTAS del pipeline neuro-simbólico, SIN gastar un solo
token de Gemini (ni embeddings ni LLM). El resultado es un dataset de triplets
`(anchor, positive, negative)` listo para fine-tunear un `sentence-transformers`
en local (Capa 2.5 — embeddings especializados en ferretería).

Capas usadas (todas LOCALES, costo $0)
---------------------------------------
  • Capa 0.5  → verificar_marcas_compatibles
  • Capa 1    → compare_units (quantulum3 + pint)
  • Capa 1.25 → to_millimeters (integrada en Capa 1.5)
  • Capa 1.5  → cruzar_grafos_deterministas (grafo de nodos físicos)

Capas explícitamente EXCLUIDAS
------------------------------
  • Capa 2   (Embeddings Gemini)     ← $$
  • Capa 3   (LLM Gemini)            ← $$$
Este script NUNCA las llama.

Reglas de cosecha de triplets
-----------------------------
Para cada par (A, B) con MISMA clase ETIM:

  1. Corre Capa 0.5 → 1 → 1.25/1.5.
  2. Si alguna RECHAZA  →  es un "Negativo Duro" (falso positivo histórico
                           que nuestra nueva matemática captura).
  3. Si TODAS APRUEBAN y el Jaccard de texto (similitud_textual) es > 0.85
                      →  es un "Positivo" (anchor ↔ positive).

Ensamblaje del triplet:
  • anchor    = producto A del positivo
  • positive  = producto B del positivo (misma ETIM, aprobado, jaccard alto)
  • negative  = un "Negativo Duro" cosechado que comparta la clase ETIM
                del anchor. Fallback: negativo débil al azar (otra clase).

Salida
------
Archivo `datasets/triplets_acelerados.jsonl` — una línea JSON por triplet:

    {"anchor": "...", "positive": "...", "negative": "..."}

Formato directamente consumible por:
    from sentence_transformers import InputExample
    ex = InputExample(texts=[r["anchor"], r["positive"], r["negative"]])

Cómo correrlo
-------------
Desde la raíz del worktree:

    python -m scripts.run_backtesting_acelerado \
        --max-pares 20000 \
        --batch-size 500 \
        --jaccard-positivo 0.85

Entrenamiento local (una vez generado el JSONL)
-----------------------------------------------
    pip install sentence-transformers==3.0.1 torch tqdm

    # train_local.py (esqueleto mínimo)
    # --------------------------------
    # import json
    # from sentence_transformers import (SentenceTransformer, InputExample,
    #                                    losses, evaluation)
    # from torch.utils.data import DataLoader
    #
    # model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    # examples = []
    # with open("datasets/triplets_acelerados.jsonl", encoding="utf-8") as f:
    #     for line in f:
    #         r = json.loads(line)
    #         examples.append(InputExample(texts=[r["anchor"], r["positive"], r["negative"]]))
    # loader = DataLoader(examples, shuffle=True, batch_size=32)
    # loss   = losses.TripletLoss(model=model)
    # model.fit(train_objectives=[(loader, loss)], epochs=3, warmup_steps=100,
    #           output_path="models/ferreteria-miniLM-v1")
    #
    # Luego en ai_matcher.py, reemplaza la llamada a Gemini embeddings por:
    #     SentenceTransformer("models/ferreteria-miniLM-v1").encode(texto)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

# Permite `python -m scripts.run_backtesting_acelerado` desde la raíz del repo.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session  # noqa: E402

try:
    from tqdm import tqdm  # noqa: E402
except ImportError:  # pragma: no cover
    print("[WARN] tqdm no está instalado — `pip install tqdm` para barra de progreso")

    def tqdm(it, **_kwargs):  # type: ignore
        return it

from core.database import SessionLocal  # noqa: E402
from modulos.compras.models import ProductoProveedor  # noqa: E402
from modulos.compras.ai_matcher import (  # noqa: E402
    cruzar_grafos_deterministas,
    verificar_marcas_compatibles,
    similitud_textual,
)
from modulos.compras.unit_normalizer import compare_units  # noqa: E402

logger = logging.getLogger("backtesting_acelerado")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)


# ---------------------------------------------------------------------------
# Evaluación offline (0 costo en API)
# ---------------------------------------------------------------------------

def evaluar_par_offline(a: ProductoProveedor, b: ProductoProveedor) -> dict:
    """
    Pasa el par (a, b) por Capas 0.5 → 1 → 1.5 usando solo lógica local.

    Returns:
        {
            "aprobado": bool,
            "capa_rechazo": Optional[str],   # "marca" | "unidad" | "grafo" | None
            "razon": str,
            "jaccard": float,
        }
    """
    # Capa 0.5 — Marca
    marca_ok, marca_reason = verificar_marcas_compatibles(a.marca, b.marca)
    if not marca_ok:
        return {
            "aprobado": False,
            "capa_rechazo": "marca",
            "razon": marca_reason,
            "jaccard": 0.0,
        }

    # Capa 1 — Unidades
    unit = compare_units(
        a.nombre_raw, a.unidad or "",
        b.nombre_raw, b.unidad or "",
    )
    if not unit.compatible:
        return {
            "aprobado": False,
            "capa_rechazo": "unidad",
            "razon": unit.razon,
            "jaccard": 0.0,
        }

    # Capa 1.25 + 1.5 — Grafo determinista (nodos físicos en mm)
    graph_ok, graph_reason, _debug = cruzar_grafos_deterministas(
        a.nombre_raw, a.marca or "",
        b.nombre_raw, b.marca or "",
    )
    if not graph_ok:
        return {
            "aprobado": False,
            "capa_rechazo": "grafo",
            "razon": graph_reason,
            "jaccard": 0.0,
        }

    # Jaccard text fallback (rápido, solo local)
    jac = similitud_textual(a.nombre_raw, b.nombre_raw)
    return {
        "aprobado": True,
        "capa_rechazo": None,
        "razon": "todas las capas aprobaron",
        "jaccard": jac,
    }


async def _evaluar_batch(pares: list[tuple[ProductoProveedor, ProductoProveedor]]) -> list[dict]:
    """
    Evalúa un batch de pares en paralelo cooperativo.

    Las capas son síncronas y CPU-bound ligero, así que envolvemos cada par en
    un `asyncio.to_thread` para liberar el event loop y poder barrer miles de
    pares sin bloquear la barra de progreso / I/O.
    """
    tareas = [
        asyncio.to_thread(evaluar_par_offline, a, b) for (a, b) in pares
    ]
    return await asyncio.gather(*tareas)


# ---------------------------------------------------------------------------
# Construcción de pares por clase ETIM
# ---------------------------------------------------------------------------

def construir_pares_por_etim(
    db: Session,
    max_pares: int,
    max_por_clase: int = 500,
    seed: int = 42,
) -> list[tuple[ProductoProveedor, ProductoProveedor]]:
    """
    Agrupa productos por `etim_class_code` y arma pares dentro de cada clase.
    Se saltan clases vacías (`None` / `""`).
    """
    rng = random.Random(seed)

    productos: list[ProductoProveedor] = (
        db.query(ProductoProveedor)
        .filter(ProductoProveedor.etim_class_code.isnot(None))
        .filter(ProductoProveedor.etim_class_code != "")
        .all()
    )
    logger.info("Productos con clase ETIM: %d", len(productos))

    por_clase: dict[str, list[ProductoProveedor]] = defaultdict(list)
    for p in productos:
        por_clase[p.etim_class_code].append(p)

    logger.info("Clases ETIM distintas: %d", len(por_clase))

    pares: list[tuple[ProductoProveedor, ProductoProveedor]] = []
    for code, items in por_clase.items():
        if len(items) < 2:
            continue
        rng.shuffle(items)
        # Estrategia: pares consecutivos + algunos cruzados, limitado a max_por_clase
        generados_clase = 0
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                pares.append((items[i], items[j]))
                generados_clase += 1
                if generados_clase >= max_por_clase:
                    break
            if generados_clase >= max_por_clase:
                break
        if len(pares) >= max_pares:
            break

    rng.shuffle(pares)
    pares = pares[:max_pares]
    logger.info("Pares candidatos construidos: %d", len(pares))
    return pares


# ---------------------------------------------------------------------------
# Cosecha de triplets
# ---------------------------------------------------------------------------

def _producto_etim(p: ProductoProveedor) -> str:
    return p.etim_class_code or ""


def armar_triplets(
    positivos: list[tuple[ProductoProveedor, ProductoProveedor]],
    negativos_duros: list[tuple[ProductoProveedor, ProductoProveedor]],
    seed: int = 42,
) -> list[dict]:
    """
    Ensambla triplets tomando:
      • anchor/positive desde la lista de positivos
      • negative preferentemente desde un negativo duro de la MISMA clase ETIM
        del anchor (para forzar al modelo a aprender la frontera fina).
    """
    rng = random.Random(seed)

    # Indexa negativos duros por clase ETIM para lookup O(1)
    negs_por_clase: dict[str, list[ProductoProveedor]] = defaultdict(list)
    for na, nb in negativos_duros:
        # Ambos lados del negativo duro son textualmente "candidatos plausibles"
        negs_por_clase[_producto_etim(na)].append(nb)
        negs_por_clase[_producto_etim(nb)].append(na)

    # Pool de fallback (cualquier producto no relacionado)
    fallback_pool: list[ProductoProveedor] = []
    for na, nb in negativos_duros:
        fallback_pool.extend([na, nb])
    rng.shuffle(fallback_pool)

    triplets: list[dict] = []
    for a, b in positivos:
        etim = _producto_etim(a)
        candidatos = negs_por_clase.get(etim, [])
        # Evita que el negativo sea exactamente uno de los dos lados del positivo
        candidatos_validos = [
            c for c in candidatos if c.id != a.id and c.id != b.id
        ]
        negative: Optional[ProductoProveedor] = None
        if candidatos_validos:
            negative = rng.choice(candidatos_validos)
        elif fallback_pool:
            for c in fallback_pool:
                if c.id != a.id and c.id != b.id:
                    negative = c
                    break

        if negative is None:
            continue

        triplets.append({
            "anchor": a.nombre_raw,
            "positive": b.nombre_raw,
            "negative": negative.nombre_raw,
            "meta": {
                "etim_class": etim,
                "anchor_id": a.id,
                "positive_id": b.id,
                "negative_id": negative.id,
            },
        })

    return triplets


# ---------------------------------------------------------------------------
# Exportación
# ---------------------------------------------------------------------------

def exportar_jsonl(triplets: list[dict], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for t in triplets:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    return len(triplets)


# ---------------------------------------------------------------------------
# Driver principal (asyncio + batches)
# ---------------------------------------------------------------------------

async def run(
    max_pares: int,
    batch_size: int,
    jaccard_positivo: float,
    max_por_clase: int,
    output: Path,
    seed: int,
) -> int:
    db: Session = SessionLocal()
    try:
        pares = construir_pares_por_etim(
            db,
            max_pares=max_pares,
            max_por_clase=max_por_clase,
            seed=seed,
        )
        if not pares:
            logger.warning("No hay pares candidatos — ¿la BD tiene productos con etim_class_code?")
            return 1

        positivos: list[tuple[ProductoProveedor, ProductoProveedor]] = []
        negativos_duros: list[tuple[ProductoProveedor, ProductoProveedor]] = []
        contadores = {"marca": 0, "unidad": 0, "grafo": 0, "aprobado": 0, "positivo": 0}

        total = len(pares)
        pbar = tqdm(total=total, desc="Backtesting", unit="par")

        for inicio in range(0, total, batch_size):
            batch = pares[inicio:inicio + batch_size]
            resultados = await _evaluar_batch(batch)

            for (a, b), res in zip(batch, resultados):
                if res["aprobado"]:
                    contadores["aprobado"] += 1
                    if res["jaccard"] >= jaccard_positivo:
                        positivos.append((a, b))
                        contadores["positivo"] += 1
                else:
                    capa = res["capa_rechazo"] or "desconocida"
                    contadores[capa] = contadores.get(capa, 0) + 1
                    # Negativo duro = par rechazado POR grafo o unidad
                    # (rechazo por marca no es "plausible textualmente")
                    if capa in ("grafo", "unidad"):
                        negativos_duros.append((a, b))
            pbar.update(len(batch))
        pbar.close()

        logger.info("Resumen offline:")
        for k, v in contadores.items():
            logger.info("  %-10s  %d", k, v)
        logger.info("Positivos cosechados:      %d", len(positivos))
        logger.info("Negativos duros cosechados: %d", len(negativos_duros))

        triplets = armar_triplets(positivos, negativos_duros, seed=seed)
        logger.info("Triplets ensamblados: %d", len(triplets))

        n = exportar_jsonl(triplets, output)
        logger.info("OK — %d triplets exportados a %s", n, output)
        return 0
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Estudio Acelerado: backtesting offline del pipeline neuro-simbólico "
                    "para cosechar triplets de entrenamiento sin gastar API de Gemini.",
    )
    parser.add_argument("--max-pares", type=int, default=20000,
                        help="Máximo de pares candidatos a evaluar (default: 20000)")
    parser.add_argument("--max-por-clase", type=int, default=500,
                        help="Máximo de pares dentro de una misma clase ETIM (default: 500)")
    parser.add_argument("--batch-size", type=int, default=500,
                        help="Tamaño del batch asyncio (default: 500)")
    parser.add_argument("--jaccard-positivo", type=float, default=0.85,
                        help="Umbral de similitud_textual para aceptar un positivo (default: 0.85)")
    parser.add_argument("--output", type=Path,
                        default=Path("datasets/triplets_acelerados.jsonl"),
                        help="Ruta de salida del JSONL (default: datasets/triplets_acelerados.jsonl)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    return asyncio.run(run(
        max_pares=args.max_pares,
        batch_size=args.batch_size,
        jaccard_positivo=args.jaccard_positivo,
        max_por_clase=args.max_por_clase,
        output=args.output,
        seed=args.seed,
    ))


if __name__ == "__main__":
    raise SystemExit(main())
