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

from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai import cache as ai_cache
from app.ai.explainer import ClaudeExplainer, ExplanationError
from app.core.config import settings
from app.core.db import SessionLocal, init_db
from app.models.orm import Opportunity, PriceSnapshot, Ticker
from app.screener import canslim, scoring, universe
from app.screener.canslim import InstitutionalData
from app.screener.data_source import AlpacaDataSource, FundamentalData, YFinanceDataSource, _yoy_growth
from app.screener.sec_edgar import get_edgar_data
from app.screener.sec_13f import latest_available_quarter, prior_quarter_end
from app.screener.strategies import evaluate_all_strategies
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
    signal_type: str | None = None


_WEINSTEIN_MAX_WEEKS = 8


def _compute_signal_type(weinstein_result: WeinsteinResult, criteria: dict[str, canslim.CriterionResult]) -> str | None:
    """Mismo criterio que la capa API: Weinstein 1→2 fresco O CAN SLIM completo."""
    is_weinstein = weinstein_result.is_transition_1_to_2 and weinstein_result.weeks_in_stage <= _WEINSTEIN_MAX_WEEKS
    n_passes = criteria.get("N", canslim.CriterionResult(None, "")).value is True
    all_verifiable_pass = all(c.value is True for c in criteria.values() if c.value is not None)
    is_canslim = n_passes and all_verifiable_pass
    if is_weinstein and is_canslim:
        return "both"
    if is_weinstein:
        return "weinstein"
    if is_canslim:
        return "canslim"
    return None


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


def _get_universe_ath(db: Session) -> dict[str, float]:
    """ATH histórico por símbolo desde price_snapshots acumulado."""
    sql = text("""
        SELECT t.symbol, MAX(ps.high) AS ath
        FROM price_snapshots ps
        JOIN tickers t ON t.id = ps.ticker_id
        GROUP BY t.symbol
    """)
    rows = db.execute(sql).fetchall()
    return {row[0]: float(row[1]) for row in rows if row[1] is not None}


def _get_universe_institutional(db: Session) -> dict[str, InstitutionalData]:
    """Pre-carga conteo de holders institucionales (trimestre actual y anterior)
    desde institutional_holdings. Si la tabla está vacía devuelve {}."""
    current_q = latest_available_quarter()
    prior_q = prior_quarter_end(current_q)
    sql = text("""
        SELECT t.symbol,
               COUNT(CASE WHEN ih.quarter = :current_q THEN 1 END) AS current_holders,
               COUNT(CASE WHEN ih.quarter = :prior_q   THEN 1 END) AS prior_holders,
               COALESCE(SUM(CASE WHEN ih.quarter = :current_q THEN ih.shares ELSE 0 END), 0) AS current_shares,
               COALESCE(SUM(CASE WHEN ih.quarter = :prior_q   THEN ih.shares ELSE 0 END), 0) AS prior_shares
        FROM tickers t
        JOIN institutional_holdings ih ON ih.ticker_id = t.id
        WHERE ih.quarter IN (:current_q, :prior_q)
        GROUP BY t.symbol
    """)
    try:
        rows = db.execute(sql, {"current_q": current_q, "prior_q": prior_q}).fetchall()
    except Exception:
        # La tabla puede no existir todavía si aún no se ha ejecutado update_institutional
        return {}
    result: dict[str, InstitutionalData] = {}
    for row in rows:
        symbol, cur_h, pri_h, cur_s, pri_s = row
        result[symbol] = InstitutionalData(
            current_holders=int(cur_h or 0),
            prior_holders=int(pri_h) if pri_h else None,
            current_shares=int(cur_s or 0),
            prior_shares=int(pri_s) if pri_s else None,
        )
    return result


def _get_universe_returns(db: Session, lookback_weeks: int = 52) -> list[float]:
    """Retorno a 52 semanas de cada ticker activo desde price_snapshots.
    Usado para calcular el RS Rating percentil (criterio L estilo IBD)."""
    year_ago = date.today() - timedelta(weeks=lookback_weeks)
    sql = text("""
        WITH oldest AS (
            SELECT ticker_id, close,
                   ROW_NUMBER() OVER (PARTITION BY ticker_id ORDER BY date ASC) AS rn
            FROM price_snapshots
            WHERE date >= :year_ago
        ),
        newest AS (
            SELECT ticker_id, close,
                   ROW_NUMBER() OVER (PARTITION BY ticker_id ORDER BY date DESC) AS rn
            FROM price_snapshots
        )
        SELECT (n.close - o.close) / NULLIF(o.close, 0) AS return_52w
        FROM oldest o
        JOIN newest n ON n.ticker_id = o.ticker_id AND n.rn = 1
        WHERE o.rn = 1
          AND o.close > 0
    """)
    rows = db.execute(sql, {"year_ago": year_ago}).fetchall()
    return [float(row[0]) for row in rows if row[0] is not None]


def _upsert_price_snapshots(db: Session, ticker: Ticker, weekly: "pd.DataFrame") -> int:
    """Inserta las filas de OHLCV semanal que no existan todavía. No sobreescribe
    datos históricos ya persistidos (los precios del pasado no cambian)."""
    if weekly.empty:
        return 0

    existing_dates = {
        row[0]
        for row in db.query(PriceSnapshot.date).filter(PriceSnapshot.ticker_id == ticker.id).all()
    }

    new_rows = []
    for dt, row in weekly.iterrows():
        snapshot_date = dt.date() if hasattr(dt, "date") else dt
        if snapshot_date not in existing_dates:
            new_rows.append(
                PriceSnapshot(
                    ticker_id=ticker.id,
                    date=snapshot_date,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                )
            )

    if new_rows:
        db.add_all(new_rows)

    return len(new_rows)


def _upsert_opportunity(db: Session, ticker: Ticker, run_date: date, score: scoring.CombinedScore,
                         weinstein_result, criteria: dict[str, canslim.CriterionResult],
                         strategies: dict | None = None) -> None:
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
    existing.weinstein_rsi = weinstein_result.rsi
    existing.canslim_criteria = criteria_json
    existing.canslim_score = score.canslim_component
    existing.canslim_verifiable_count = score.canslim_verifiable_count
    existing.canslim_passed_count = score.canslim_passed_count
    existing.combined_score = score.combined_score
    existing.risk_bucket = score.risk_bucket
    if strategies is not None:
        existing.strategies = strategies


def run(symbols_by_universe: dict[str, list[str]], delay_seconds: float = 0.0) -> None:
    init_db()
    db = SessionLocal()
    if settings.alpaca_api_key and settings.alpaca_secret_key:
        source = AlpacaDataSource(settings.alpaca_api_key, settings.alpaca_secret_key, delay_seconds)
        logger.info("Data source: Alpaca Markets API (Railway-compatible)")
    else:
        source = YFinanceDataSource(request_delay_seconds=delay_seconds)
        logger.info("Data source: yfinance (solo local; Railway bloqueará Yahoo Finance)")
    run_date = date.today()

    try:
        logger.info("Descargando histórico semanal del benchmark %s", BENCHMARK_SYMBOL)
        benchmark_weekly = source.get_weekly_prices(BENCHMARK_SYMBOL)
        benchmark_weinstein = analyze(benchmark_weekly)
    except InsufficientDataError as exc:
        logger.error("No se pudo analizar el benchmark %s: %s. Abortando corrida.", BENCHMARK_SYMBOL, exc)
        db.close()
        return

    logger.info("Pre-cargando ATH histórico, retornos de universo y datos institucionales...")
    universe_ath = _get_universe_ath(db)
    universe_returns = _get_universe_returns(db)
    universe_institutional = _get_universe_institutional(db)
    logger.info(
        "ATH: %d tickers | RS returns: %d | datos 13F: %d tickers",
        len(universe_ath), len(universe_returns), len(universe_institutional),
    )

    processed, skipped = 0, 0
    screened: list[ScreenedTicker] = []
    for universe_name, symbols in symbols_by_universe.items():
        for symbol in symbols:
            try:
                weekly = source.get_weekly_prices(symbol)
                weinstein_result = analyze(weekly)
                # Una sola llamada a SEC EDGAR extrae supply (S), EPS (C/A) y métricas de calidad
                supply_signal, edgar_eps, quality = get_edgar_data(symbol)
                if isinstance(source, AlpacaDataSource):
                    fundamentals = FundamentalData(
                        eps_quarterly_yoy_growth=_yoy_growth(edgar_eps.quarterly, 4) if len(edgar_eps.quarterly) >= 5 else None,
                        eps_annual_growth=_yoy_growth(edgar_eps.annual, 1) if len(edgar_eps.annual) >= 2 else None,
                        raw_quarterly_eps=edgar_eps.quarterly,
                        raw_annual_eps=edgar_eps.annual,
                    )
                else:
                    fundamentals = source.get_fundamentals(symbol)
                name, sector, institutional_pct = source.get_profile(symbol)
                dividend_data = source.get_dividend_data(symbol)
                # ATH: máximo entre histórico acumulado en BD y lo descargado hoy
                ath_from_db = universe_ath.get(symbol)
                ath_from_download = float(weekly["High"].max()) if not weekly.empty else None
                all_time_high = max(filter(None, [ath_from_db, ath_from_download])) if (ath_from_db or ath_from_download) else None
                criteria = canslim.evaluate_all(
                    fundamentals, weekly, benchmark_weekly, benchmark_weinstein,
                    supply_signal, institutional_pct,
                    all_time_high=all_time_high,
                    universe_returns=universe_returns if universe_returns else None,
                    institutional_data=universe_institutional.get(symbol),
                )
                score = scoring.compute_combined_score(weinstein_result, criteria, weekly)
                signal_type = _compute_signal_type(weinstein_result, criteria)
                strategies = evaluate_all_strategies(
                    weekly, fundamentals, supply_signal, quality, dividend_data,
                    universe_returns=universe_returns if universe_returns else None,
                )

                ticker = _get_or_create_ticker(db, symbol, universe_name, name, sector)
                _upsert_price_snapshots(db, ticker, weekly)
                _upsert_opportunity(db, ticker, run_date, score, weinstein_result, criteria, strategies)
                db.commit()
                processed += 1
                screened.append(ScreenedTicker(ticker, score, weinstein_result, criteria, signal_type))
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

    # Solo se generan explicaciones para tickers con señal de entrada real.
    # Esto acota el gasto de API de Claude a lo que realmente aparece en el feed.
    candidates = [
        s for s in screened
        if s.signal_type is not None and s.score.combined_score >= settings.explanation_min_score
    ]
    candidates.sort(key=lambda s: s.score.combined_score, reverse=True)
    candidates = candidates[: settings.explanation_max_per_run]

    logger.info(
        "Generando explicaciones para %d/%d tickers con señal (umbral score %d, máx %d)",
        len(candidates), len(screened), settings.explanation_min_score, settings.explanation_max_per_run,
    )

    for item in candidates:
        explanation = ai_cache.get_or_create_explanation(
            db, item.ticker, run_date, item.score.combined_score,
            item.weinstein_result, item.criteria, explainer,
            signal_type=item.signal_type,
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
