"""Utilidad puntual: borra la cartera pública simulada y la vuelve a generar
llamando a update_portfolio.run() semana a semana sobre el histórico de
Opportunity ya persistido (por el backtest) -- sin repetir las descargas de
precio/EDGAR/13F, solo la lógica de entrada/salida.

Se usa tras un cambio en la lógica de update_portfolio.py (p.ej. el fix de
_exit_signal) que no afecta a los datos de Opportunity, solo a cómo se
deciden entradas/salidas sobre ellos.

Uso:
    python -m scripts.resimulate_portfolio
"""
from __future__ import annotations

import logging

from app.core.db import SessionLocal, init_db
from app.jobs import update_portfolio
from app.models.orm import Opportunity, PortfolioPosition

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("resimulate_portfolio")


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        deleted = db.query(PortfolioPosition).delete()
        db.commit()
        logger.info("Borradas %d posiciones de la cartera pública", deleted)

        run_dates = [
            row[0]
            for row in db.query(Opportunity.run_date).distinct().order_by(Opportunity.run_date.asc()).all()
        ]
        logger.info("Resimulando sobre %d fechas históricas", len(run_dates))
    finally:
        db.close()

    stats = {"opened": 0, "closed": 0}
    for run_date in run_dates:
        r = update_portfolio.run(run_date=run_date)
        stats["opened"] += r.get("opened", 0)
        stats["closed"] += r.get("closed", 0)

    logger.info("Resimulación completada: %s", stats)
    print(stats)


if __name__ == "__main__":
    main()
