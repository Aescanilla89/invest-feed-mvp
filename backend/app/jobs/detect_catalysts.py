"""Job: detecta catalizadores de inversión (earnings, insider buys y
catalizadores macro) y los guarda en la tabla `catalysts`.

Ejecutar DESPUÉS del screener diario. Earnings/insider buys solo analizan los
tickers que ya tienen oportunidades en BD (no el universo completo) para
mantener el tiempo acotado. Los catalizadores macro (FED, geopolítica, datos
macro EEUU) no dependen de ningún ticker — se ejecutan siempre.

Uso:
    python -m app.jobs.detect_catalysts
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from app.core.db import SessionLocal, init_db
from app.models.orm import Catalyst, Opportunity, Ticker
from app.screener.catalysts import (
    CatalystData,
    detect_earnings,
    detect_fed_meeting,
    detect_geopolitical_events,
    detect_insider_buys,
    detect_macro_data_releases,
)

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

        def _persist(items: list[CatalystData]) -> tuple[int, int]:
            saved, skipped = 0, 0
            for cd in items:
                if db.query(Catalyst).filter_by(source_id=cd.source_id).one_or_none():
                    skipped += 1
                    continue
                ticker = db.query(Ticker).filter_by(symbol=cd.symbol).one_or_none() if cd.symbol else None
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
            return saved, skipped

        # Catalizadores macro/market-wide (ticker_id=None) primero — Polymarket/FRED
        # son unas pocas peticiones HTTP rápidas, independientes del universo.
        # Se guardan con su propio commit para que estén disponibles ya mismo aunque
        # el bucle de earnings/insider (potencialmente lento, cientos de tickers) se
        # quede atascado o el proceso se reinicie a mitad de camino.
        macro_catalysts: list[CatalystData] = []
        macro_catalysts.extend(detect_fed_meeting())
        macro_catalysts.extend(detect_geopolitical_events())
        macro_catalysts.extend(detect_macro_data_releases())
        saved, skipped = _persist(macro_catalysts)

        if symbols:
            logger.info("Detectando catalizadores para %d tickers activos", len(symbols))
            per_ticker: list[CatalystData] = []
            per_ticker.extend(detect_earnings(symbols, lookback_days=3))
            per_ticker.extend(detect_insider_buys(symbols, lookback_days=14))
            more_saved, more_skipped = _persist(per_ticker)
            saved += more_saved
            skipped += more_skipped
        else:
            logger.warning("No hay tickers con oportunidades recientes — solo catalizadores macro")

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
