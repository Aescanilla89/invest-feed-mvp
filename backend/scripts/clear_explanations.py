"""Utilidad puntual: borra el historial de explicaciones IA cacheadas para
forzar su regeneración completa en la próxima corrida del screener (p.ej.
tras un cambio de tono/prompt en app/ai/prompts.py, que el cache no detecta
por sí solo porque solo compara combined_score y catalyst_ids).

Uso:
    cd backend && PYTHONPATH=. python scripts/clear_explanations.py
"""
from __future__ import annotations

import logging

from app.core.db import SessionLocal, init_db
from app.models.orm import Explanation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("clear_explanations")


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        count = db.query(Explanation).delete()
        db.commit()
        logger.info("Borradas %d explicaciones cacheadas", count)
    finally:
        db.close()


if __name__ == "__main__":
    main()
