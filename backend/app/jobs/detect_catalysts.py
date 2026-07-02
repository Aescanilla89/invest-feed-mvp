"""Job: detecta catalizadores de inversión (earnings + insider buys) para los
tickers activos y los guarda en la tabla `catalysts`.

Ejecutar DESPUÉS del screener diario. Solo analiza los tickers que ya tienen
oportunidades en BD (no el universo completo) para mantener el tiempo acotado.

Uso:
    python -m app.jobs.detect_catalysts
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from app.core.db import SessionLocal, init_db
from app.models.orm import Catalyst, Opportunity, Ticker
from app.screener.catalysts import CatalystData, detect_earnings, detect_insider_buys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("detect_catalysts")


def run(lookback_days_opps: int = 7) -> dict:
    """Detecta catalizadores y los persiste. Devuelve resumen con contadores."""
    init_db()
    db = SessionLocal()
    today = date.today()

    try:
        # Tickers con oportunidades recientes = nuestro universo analizado
        since = today - timedelta(days=lookback_days_opps)
        rows = (
            db.query(Ticker.symbol)
            .join(Opportunity, Opportunity.ticker_id == Ticker.id)
            .filter(Opportunity.run_date >= since)
            .distinct()
            .all()
        )
        symbols = [r[0] for r in rows]

        if not symbols:
            logger.warning("No hay tickers con oportunidades recientes — skipping")
            return {"status": "skipped", "reason": "no symbols"}

        logger.info("Detectando catalizadores para %d tickers activos", len(symbols))

        all_catalysts: list[CatalystData] = []
        all_catalysts.extend(detect_earnings(symbols, lookback_days=3))
        all_catalysts.extend(detect_insider_buys(symbols, lookback_days=14))

        saved, skipped = 0, 0
        for cd in all_catalysts:
            if db.query(Catalyst).filter_by(source_id=cd.source_id).one_or_none():
                skipped += 1
                continue

            ticker = db.query(Ticker).filter_by(symbol=cd.symbol).one_or_none()
            db.add(Catalyst(
                ticker_id=ticker.id if ticker else None,
                detected_date=today,
                catalyst_type=cd.catalyst_type,
                title=cd.title,
                description=cd.description,
                source_id=cd.source_id,
                extra=cd.extra,
            ))
            saved += 1

        db.commit()
        logger.info("Catalizadores: %d guardados, %d ya existían", saved, skipped)
        return {
            "status": "ok",
            "saved": saved,
            "skipped": skipped,
            "symbols_checked": len(symbols),
        }

    except Exception:
        db.rollback()
        logger.exception("Error en detect_catalysts")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    result = run()
    print(result)
