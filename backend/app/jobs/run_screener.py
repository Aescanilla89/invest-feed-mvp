"""Job diario: recorre el universo, calcula Weinstein + CAN SLIM + score
combinado por ticker, y persiste una fila `Opportunity` por ticker/día.

Uso:
    python -m app.jobs.run_screener                     # universo completo
    python -m app.jobs.run_screener --tickers AAPL,MSFT  # solo estos tickers (debug)
    python -m app.jobs.run_screener --limit 20           # primeros N del universo
    python -m app.jobs.run_screener --delay 0.3          # pausa entre llamadas yfinance

No falla la corrida completa por un ticker individual: si un ticker da
error (datos insuficientes, fallo de red, etc.) se loguea y se continúa.
"""
from __future__ import annotations

import argparse
import logging
import math
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.ai import cache as ai_cache
from app.ai.explainer import ClaudeExplainer, ExplanationError
from app.core.config import settings
from app.core.db import SessionLocal, init_db
from app.models.orm import Opportunity, Ticker
from app.screener import canslim, scoring, universe
from app.screener.data_source import YFinanceDataSource
from app.screener.sec_edgar import get_supply_signal
from app.screener.weinstein import InsufficientDataError, WeinsteinResult, analyze

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("run_screener")

BENCHMARK_SYMBOL = "SPY"


@dataclass
class ScreenedTicker:
    ticker: Ticker
    score: scoring.CombinedScore
    weinstein_result: WeinsteinResult
    criteria: dict[str, canslim.CriterionResult]


def _get_or_create_ticker(db: Session, symbol: str, universe_name: str, name: str | None, sector: str | None) -> Ticker:
    ticker = db.query(Ticker).filter_by(symbol=symbol).one_or_none()
    if ticker is None:
        ticker = Ticker(symbol=symbol, universe=universe_name, name=name, sector=sector, is_active=True)
        db.add(ticker)
        db.flush()
    else:
        ticker.name = name or ticker.name
        ticker.sector = sector or ticker.sector
    return ticker


def _upsert_opportunity(db: Session, ticker: Ticker, run_date: date, score: scoring.CombinedScore,
                         weinstein_result, criteria: dict[str, canslim.CriterionResult]) -> None:
    criteria_json = {k: {"value": v.value, "detail": v.detail} for k, v in criteria.items()}
    existing = db.query(Opportunity).filter_by(ticker_id=ticker.id, run_date=run_date).one_or_none()
    if existing is None:
        existing = Opportunity(ticker_id=ticker.id, run_date=run_date)
        db.add(existing)

    existing.weinstein_stage = weinstein_result.stage
    existing.weinstein_transition = weinstein_result.is_transition_1_to_2
    existing.weeks_in_stage = weinstein_result.weeks_in_stage
    existing.weinstein_ma_slope_pct = weinstein_result.ma_slope_pct
    existing.weinstein_relative_volume = 0.0 if math.isnan(weinstein_result.relative_volume) else weinstein_result.relative_volume
    existing.canslim_criteria = criteria_json
    existing.canslim_score = score.canslim_component
    existing.canslim_verifiable_count = score.canslim_verifiable_count
    existing.canslim_passed_count = score.canslim_passed_count
    existing.combined_score = score.combined_score
    existing.risk_bucket = score.risk_bucket


def run(symbols_by_universe: dict[str, list[str]], delay_seconds: float = 0.0) -> None:
    init_db()
    db = SessionLocal()
    source = YFinanceDataSource(request_delay_seconds=delay_seconds)
    run_date = date.today()

    try:
        logger.info("Descargando histórico semanal del benchmark %s", BENCHMARK_SYMBOL)
        benchmark_weekly = source.get_weekly_prices(BENCHMARK_SYMBOL)
        benchmark_weinstein = analyze(benchmark_weekly)
    except InsufficientDataError as exc:
        logger.error("No se pudo analizar el benchmark %s: %s. Abortando corrida.", BENCHMARK_SYMBOL, exc)
        db.close()
        return

    processed, skipped = 0, 0
    screened: list[ScreenedTicker] = []
    for universe_name, symbols in symbols_by_universe.items():
        for symbol in symbols:
            try:
                weekly = source.get_weekly_prices(symbol)
                weinstein_result = analyze(weekly)
                fundamentals = source.get_fundamentals(symbol)
                supply_signal = get_supply_signal(symbol)
                criteria = canslim.evaluate_all(fundamentals, weekly, benchmark_weekly, benchmark_weinstein, supply_signal)
                score = scoring.compute_combined_score(weinstein_result, criteria, weekly)
                name, sector = source.get_profile(symbol)

                ticker = _get_or_create_ticker(db, symbol, universe_name, name, sector)
                _upsert_opportunity(db, ticker, run_date, score, weinstein_result, criteria)
                db.commit()
                processed += 1
                screened.append(ScreenedTicker(ticker, score, weinstein_result, criteria))
                logger.info("%s: stage=%s score=%s risk=%s", symbol, weinstein_result.stage, score.combined_score, score.risk_bucket)
            except InsufficientDataError as exc:
                logger.warning("%s: histórico insuficiente, se omite (%s)", symbol, exc)
                skipped += 1
                db.rollback()
            except Exception as exc:  # noqa: BLE001 -- un fallo puntual no debe tirar toda la corrida
                logger.exception("%s: error inesperado, se omite", symbol)
                skipped += 1
                db.rollback()

    logger.info("Corrida %s completada: %d procesados, %d omitidos", run_date, processed, skipped)
    _generate_explanations(db, run_date, screened)
    db.close()


def _generate_explanations(db: Session, run_date: date, screened: list[ScreenedTicker]) -> None:
    """Solo se generan explicaciones para las mejores oportunidades de la
    corrida (top N por score, por encima de un umbral mínimo) -- el feed
    tipo Netflix solo necesita explicar lo que va a mostrar destacado, no
    cada ticker del universo. Esto es lo que mantiene el coste de la API
    de Claude acotado y predecible."""
    try:
        explainer = ClaudeExplainer()
    except ExplanationError as exc:
        logger.warning("Generación de explicaciones desactivada: %s", exc)
        return

    candidates = [s for s in screened if s.score.combined_score >= settings.explanation_min_score]
    candidates.sort(key=lambda s: s.score.combined_score, reverse=True)
    candidates = candidates[: settings.explanation_max_per_run]

    logger.info("Generando explicaciones para %d/%d tickers (umbral %d, máx %d)",
                len(candidates), len(screened), settings.explanation_min_score, settings.explanation_max_per_run)

    for item in candidates:
        explanation = ai_cache.get_or_create_explanation(
            db, item.ticker, run_date, item.score.combined_score, item.weinstein_result, item.criteria, explainer
        )
        db.commit()
        if explanation is not None:
            logger.info("%s: explicación lista", item.ticker.symbol)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", type=str, default=None, help="Lista separada por comas, override del universo")
    parser.add_argument("--limit", type=int, default=None, help="Limitar a los primeros N tickers del universo")
    parser.add_argument("--delay", type=float, default=0.2, help="Pausa en segundos entre llamadas a yfinance")
    args = parser.parse_args()

    if args.tickers:
        symbols_by_universe = {"manual": [s.strip().upper() for s in args.tickers.split(",")]}
    else:
        symbols_by_universe = universe.get_universe()
        if args.limit:
            symbols_by_universe = {k: v[: args.limit] for k, v in symbols_by_universe.items()}

    run(symbols_by_universe, delay_seconds=args.delay)


if __name__ == "__main__":
    main()
