"""
Generador de dataset de triplets para fine-tuning de sentence-transformers
con Triplet Loss (Alternativa A — Contrastive Learning).

Formato de salida (por línea):
    {"anchor": "...", "positive": "...", "negative": "..."}

Estrategia de construcción:
  • anchor   → nombre_raw de un producto A con un match exitoso registrado
               en ComparacionPrecios (confidence_score ≥ UMBRAL_POSITIVO).
  • positive → nombre_raw del producto B asociado (match real).
  • negative → nombre_raw de otro producto del MISMO canonical_id o de la
               MISMA clase ETIM (candidato plausible), pero que falló en
               la Capa 1 (unidad) o Capa 1.5 (nodos físicos) — es decir,
               texto muy parecido pero dimensiones/unidades incompatibles.
               Si no existe un negativo duro, se usa un negativo débil
               (producto al azar del mismo proveedor, no asociado).

Uso:
    python -m scripts.generar_dataset_triplets \\
        --output datasets/triplets.jsonl \\
        --formato jsonl \\
        --umbral-positivo 0.85 \\
        --max-triplets 5000

Para CSV:
    python -m scripts.generar_dataset_triplets --output datasets/triplets.csv --formato csv

El archivo generado se puede consumir directamente con:
    from sentence_transformers import InputExample, losses
    from sentence_transformers import SentenceTransformer
    examples = [InputExample(texts=[r["anchor"], r["positive"], r["negative"]])
                for r in json.loads(open("datasets/triplets.jsonl").read().splitlines())]
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import random
import sys
from pathlib import Path
from typing import Iterator, Optional

# Permite ejecutar el script desde la raíz del repo:
#   python -m scripts.generar_dataset_triplets
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from core.database import SessionLocal  # noqa: E402
from modulos.compras.models import (  # noqa: E402
    ComparacionPrecios,
    ProductoCanonical,
    ProductoProveedor,
)
from modulos.compras.etim_taxonomy import (  # noqa: E402
    classify_product,
    extract_product_attributes,
)

logger = logging.getLogger("triplet_builder")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)


# ---------------------------------------------------------------------------
# Negativos duros
# ---------------------------------------------------------------------------

_STRICT_NODES = ("diametro_raw", "largo_raw", "medida_mm", "material", "cabeza")


def _es_negativo_duro(anchor: ProductoProveedor, cand: ProductoProveedor) -> bool:
    """
    Un negativo "duro" es un producto textualmente parecido al anchor
    (misma clase ETIM) pero que fallaría en Capa 1.5: al menos un nodo
    físico diverge.
    """
    if cand.id == anchor.id:
        return False

    cls_a = classify_product(anchor.nombre_raw, anchor.marca or "")
    cls_b = classify_product(cand.nombre_raw, cand.marca or "")

    # Misma clase ETIM → semánticamente cercano (candidato plausible)
    same_class = (
        cls_a.etim_class is not None
        and cls_b.etim_class is not None
        and cls_a.etim_class.code == cls_b.etim_class.code
    )
    if not same_class:
        return False

    attrs_a = extract_product_attributes(anchor.nombre_raw, anchor.marca or "")
    attrs_b = extract_product_attributes(cand.nombre_raw, cand.marca or "")

    for node in _STRICT_NODES:
        if node in attrs_a and node in attrs_b:
            if str(attrs_a[node]).lower() != str(attrs_b[node]).lower():
                return True
    return False


def _buscar_negativo(
    db: Session,
    anchor: ProductoProveedor,
    usados: set[int],
) -> Optional[ProductoProveedor]:
    """
    Busca un candidato negativo "duro" — mismo tipo de producto, dimensiones
    incompatibles. Si no encuentra, retorna un negativo débil al azar.
    """
    cls_a = classify_product(anchor.nombre_raw, anchor.marca or "")
    etim_code = cls_a.etim_class.code if cls_a.etim_class else None

    # Búsqueda por misma clase ETIM para encontrar candidatos duros
    query = db.query(ProductoProveedor).filter(ProductoProveedor.id != anchor.id)
    if etim_code:
        query = query.filter(ProductoProveedor.etim_class_code == etim_code)
    candidatos = query.limit(200).all()
    random.shuffle(candidatos)

    for cand in candidatos:
        if cand.id in usados:
            continue
        if _es_negativo_duro(anchor, cand):
            return cand

    # Fallback: cualquier producto distinto (negativo débil)
    weak = (
        db.query(ProductoProveedor)
        .filter(ProductoProveedor.id != anchor.id)
        .order_by(ProductoProveedor.id.desc())
        .limit(50)
        .all()
    )
    for cand in weak:
        if cand.id not in usados:
            return cand
    return None


# ---------------------------------------------------------------------------
# Generación
# ---------------------------------------------------------------------------

def iterar_triplets(
    db: Session,
    umbral_positivo: float,
    max_triplets: int,
) -> Iterator[dict]:
    """Genera triplets (anchor, positive, negative) a partir del histórico."""
    usados_neg: set[int] = set()
    generados = 0

    # Positivos reales: comparaciones con score alto
    positivos = (
        db.query(ComparacionPrecios)
        .filter(ComparacionPrecios.confidence_score >= umbral_positivo)
        .order_by(ComparacionPrecios.calculado_at.desc())
        .all()
    )
    logger.info("Matches positivos encontrados: %d", len(positivos))

    for comp in positivos:
        if generados >= max_triplets:
            break

        anchor = db.get(ProductoProveedor, comp.producto_a_id)
        positive = db.get(ProductoProveedor, comp.producto_b_id)
        if not anchor or not positive:
            continue

        negative = _buscar_negativo(db, anchor, usados_neg)
        if negative is None:
            continue
        usados_neg.add(negative.id)

        yield {
            "anchor": anchor.nombre_raw,
            "positive": positive.nombre_raw,
            "negative": negative.nombre_raw,
            "meta": {
                "canonical_id": comp.canonical_id,
                "confidence": round(float(comp.confidence_score or 0.0), 4),
                "anchor_id": anchor.id,
                "positive_id": positive.id,
                "negative_id": negative.id,
            },
        }
        generados += 1

    logger.info("Triplets generados: %d", generados)


def exportar_jsonl(triplets: Iterator[dict], out_path: Path) -> int:
    n = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for t in triplets:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
            n += 1
    return n


def exportar_csv(triplets: Iterator[dict], out_path: Path) -> int:
    n = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["anchor", "positive", "negative"])
        writer.writeheader()
        for t in triplets:
            writer.writerow({
                "anchor": t["anchor"],
                "positive": t["positive"],
                "negative": t["negative"],
            })
            n += 1
    return n


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genera dataset de triplets para fine-tuning con Triplet Loss.",
    )
    parser.add_argument("--output", type=Path, default=Path("datasets/triplets.jsonl"),
                        help="Ruta de salida (default: datasets/triplets.jsonl)")
    parser.add_argument("--formato", choices=["jsonl", "csv"], default="jsonl")
    parser.add_argument("--umbral-positivo", type=float, default=0.85,
                        help="Confidence mínimo para considerar un match como positivo")
    parser.add_argument("--max-triplets", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)

    db: Session = SessionLocal()
    try:
        triplets = iterar_triplets(
            db,
            umbral_positivo=args.umbral_positivo,
            max_triplets=args.max_triplets,
        )
        if args.formato == "jsonl":
            n = exportar_jsonl(triplets, args.output)
        else:
            n = exportar_csv(triplets, args.output)
        logger.info("OK — %d triplets exportados a %s", n, args.output)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
