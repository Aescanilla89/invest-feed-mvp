"""Utilidad puntual: repara el histórico de PriceSnapshot para tickers que
hicieron un stock split.

Motivo: hasta la corrección en app/screener/data_source.py
(AlpacaDataSource.get_weekly_prices), las peticiones a Alpaca no pedían
adjustment="split" -- Alpaca devolvía precios "raw" (el nivel real en cada
fecha histórica, sin reescalar por splits posteriores). Como
_upsert_price_snapshots (run_screener.py) solo actualiza la última semana y
nunca reescribe semanas ya cerradas, un split partía la serie en dos
niveles de precio distintos: todo lo anterior al split se quedaba congelado
al nivel pre-split, y la semana del split (y las siguientes) llegaban ya al
nivel post-split -- un "crash" en el gráfico que nunca ocurrió en la
realidad (caso detectado: Amphenol/APH, caída ~50% de una semana a otra).

Este script:
  1. Detecta candidatos: tickers cuyo histórico semanal tiene un salto de
     cierre entre dos semanas consecutivas fuera de un umbral (por defecto
     >35% en cualquier sentido) -- un movimiento normal de mercado casi
     nunca es tan brusco en una sola semana; un split sí lo parece.
  2. Para cada candidato, borra TODO su histórico de PriceSnapshot y lo
     vuelve a descargar desde cero con la petición ya corregida
     (adjustment="split"), que devuelve la serie completa consistente en
     un único nivel de precio.

Uso:
    cd backend && PYTHONPATH=. python scripts/repair_split_prices.py           # solo detecta, no repara
    cd backend && PYTHONPATH=. python scripts/repair_split_prices.py --apply   # detecta y repara
    cd backend && PYTHONPATH=. python scripts/repair_split_prices.py --apply --tickers APH,XYZ  # repara tickers concretos sin detección
"""
from __future__ import annotations

import argparse
import logging

from app.core.config import settings
from app.core.db import SessionLocal, init_db
from app.models.orm import PriceSnapshot, Ticker
from app.screener.data_source import AlpacaDataSource

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("repair_split_prices")

_JUMP_THRESHOLD = 0.35


def _detect_candidates(db) -> list[str]:
    candidates = []
    for ticker in db.query(Ticker).all():
        rows = (
            db.query(PriceSnapshot)
            .filter(PriceSnapshot.ticker_id == ticker.id)
            .order_by(PriceSnapshot.date.asc())
            .all()
        )
        for prev, curr in zip(rows, rows[1:]):
            if prev.close <= 0:
                continue
            change = abs(curr.close / prev.close - 1)
            if change > _JUMP_THRESHOLD:
                logger.warning(
                    "%s: salto %.0f%% entre %s (%.2f) y %s (%.2f) -- posible split",
                    ticker.symbol, change * 100, prev.date, prev.close, curr.date, curr.close,
                )
                candidates.append(ticker.symbol)
                break
    return candidates


def _repair(db, source: AlpacaDataSource, symbol: str) -> None:
    ticker = db.query(Ticker).filter(Ticker.symbol == symbol).one_or_none()
    if ticker is None:
        logger.warning("%s: no existe en BD, se omite", symbol)
        return

    deleted = db.query(PriceSnapshot).filter(PriceSnapshot.ticker_id == ticker.id).delete()
    db.commit()

    weekly = source.get_weekly_prices(symbol, lookback_weeks=260)
    if weekly.empty:
        logger.error("%s: Alpaca no devolvió datos, histórico queda vacío (%d filas borradas)", symbol, deleted)
        return

    rows = [
        PriceSnapshot(
            ticker_id=ticker.id,
            date=dt.date() if hasattr(dt, "date") else dt,
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=float(row["Volume"]),
        )
        for dt, row in weekly.iterrows()
    ]
    db.add_all(rows)
    db.commit()
    logger.info("%s: %d filas borradas, %d filas reinsertadas (split-adjusted)", symbol, deleted, len(rows))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Ejecuta la reparación (por defecto solo detecta)")
    parser.add_argument("--tickers", type=str, default=None, help="Lista de símbolos separados por coma a reparar directamente, sin detección")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        if args.tickers:
            symbols = [s.strip().upper() for s in args.tickers.split(",")]
        else:
            symbols = _detect_candidates(db)
            if not symbols:
                logger.info("No se detectaron candidatos a split sin ajustar")
                return
            logger.info("Candidatos detectados: %s", ", ".join(symbols))

        if not args.apply:
            logger.info("Modo detección -- vuelve a ejecutar con --apply para reparar")
            return

        source = AlpacaDataSource(settings.alpaca_api_key, settings.alpaca_secret_key, request_delay_seconds=0.15)
        for symbol in symbols:
            _repair(db, source, symbol)
    finally:
        db.close()


if __name__ == "__main__":
    main()
