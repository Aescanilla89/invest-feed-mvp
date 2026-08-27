"""Backtest histórico de 1 año (52 semanas) para poblar la cartera pública con
datos realistas, aplicando el método real (Weinstein + CAN SLIM + las 4
estrategias) semana a semana, sin look-ahead bias:

- Precio/volumen (Weinstein, RS Rating, N, S vía shares outstanding): se
  truncan al histórico disponible en cada semana pasada -- 100% reconstruible
  porque solo depende de OHLCV, que no cambia con el tiempo.
- Fundamentales EPS (C, A) y calidad (Berkshire): se filtran por la fecha
  REAL de publicación del filing SEC (`filed`), no por la fecha del periodo
  -- así una semana de julio de 2025 nunca "sabe" datos publicados en 2026.
- Tenencia institucional (I): igual, se usa el trimestre 13F más reciente
  cuyo plazo de publicación (45 días tras fin de trimestre) ya habría vencido
  en esa semana histórica.
- Dividendos: AlpacaDataSource no expone histórico de dividendos (limitación
  ya existente en producción, no solo en el backtest) -- la estrategia
  "dividendos" queda sin datos ("None") en todo el backtest, igual que hoy
  en producción para tickers servidos por Alpaca.

Estrategia de ejecución (2 pasadas, ambas seguras frente a lookahead):
  1. Por cada ticker se descarga UNA VEZ el histórico completo (precio,
     companyfacts EDGAR crudo) y se recalcula CAN SLIM/Weinstein/estrategias
     para cada una de las 52 semanas truncando esos datos ya descargados --
     evita repetir peticiones HTTP 52 veces por ticker. Se persiste una fila
     `Opportunity` por (ticker, semana) -- exactamente igual que run_screener,
     salvo que `run_date` es una fecha pasada.
  2. Con todas las semanas ya persistidas, se llama a
     `update_portfolio.run(run_date=semana)` semana a semana en orden
     cronológico -- reutiliza sin cambios la lógica de entrada/salida
     anti-lookahead ya probada en producción, que solo mira filas con
     `run_date <= target_date`, así que tener ya en BD semanas "futuras"
     (respecto a la semana que se está procesando) no filtra información:
     cada consulta de update_portfolio.py está explícitamente acotada por
     fecha.

Uso:
    python -m app.jobs.backtest_portfolio                              # completo: 52 semanas, S&P500+Nasdaq100+Russell2000
    python -m app.jobs.backtest_portfolio --weeks 8 --tickers AAPL,MSFT,NVDA  # prueba rápida
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from app.core.config import settings
from app.core.db import SessionLocal, init_db
from app.jobs import update_portfolio
from app.jobs.run_screener import (
    BENCHMARK_SYMBOL,
    _get_or_create_ticker,
    _update_latest_daily_price,
    _upsert_opportunity,
    _upsert_price_snapshots,
)
from app.jobs.update_institutional import _match_ticker
from app.models.orm import PortfolioPosition, Ticker
from app.screener import canslim, scoring, universe
from app.screener.canslim import InstitutionalData
from app.screener.data_source import AlpacaDataSource, DividendData, FundamentalData, _yoy_growth
from app.screener.sec_13f import (
    MULTI_CIK_OVERRIDES,
    TOP_INSTITUTION_NAMES,
    download_institution_holdings,
    latest_available_quarter,
    prior_quarter_end,
    quarter_end_date,
    search_institution_cik,
)
from app.screener.sec_edgar import get_company_facts, get_edgar_data_from_facts
from app.screener.strategies import evaluate_all_strategies
from app.screener.weinstein import InsufficientDataError, analyze

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backtest_portfolio")

WEEKS_BACK_DEFAULT = 52
# Margen antes de la semana más antigua del backtest para que Weinstein (36
# semanas mínimo) y RS/N (52 semanas) tengan histórico suficiente incluso ahí.
LOOKBACK_BUFFER_WEEKS = 60
QUARTERS_BACK_INSTITUTIONAL = 8  # ~2 años, cubre semanas antiguas + comparación "trimestre anterior"


def _reduced_universe() -> dict[str, list[str]]:
    """S&P 500 + Nasdaq 100 + Russell 2000 -- universo US completo servible por
    Alpaca (se excluye Europa: esos tickers no tienen datos en Alpaca y solo
    desperdiciarían tiempo de descarga sin aportar nada al backtest)."""
    universes = {
        "sp500": universe.get_sp500_tickers(),
        "nasdaq100": universe.get_nasdaq100_tickers(),
    }
    try:
        universes["russell2000"] = universe.get_russell2000_tickers()
    except universe.UniverseScrapeError:
        logger.warning("Russell 2000 no disponible para este backtest, se omite")
    return universes


def _available_quarter_as_of(as_of: date) -> date:
    """Último trimestre cuyo 13F-HR ya sería público en `as_of` (plazo: 45
    días tras el fin de trimestre) -- evita usar tenencia institucional que
    en esa fecha histórica todavía no se habría publicado."""
    q = quarter_end_date(as_of)
    while q + timedelta(days=45) > as_of:
        q = prior_quarter_end(q)
    return q


@dataclass
class TickerData:
    symbol: str
    universe_name: str
    name: str | None
    weekly: pd.DataFrame  # histórico completo (~112 semanas), no truncado
    facts: dict | None    # companyfacts crudo de EDGAR, None si no hay CIK/datos


def _fetch_all_ticker_data(
    source: AlpacaDataSource, symbols_by_universe: dict[str, list[str]], lookback_weeks: int,
) -> dict[str, TickerData]:
    """Pasada única de descarga por ticker: precio completo + companyfacts crudo.
    Se reutiliza para las 52 semanas del backtest sin repetir peticiones HTTP."""
    result: dict[str, TickerData] = {}
    seen: set[str] = set()
    total = sum(len(v) for v in symbols_by_universe.values())
    done = 0
    for universe_name, symbols in symbols_by_universe.items():
        for symbol in symbols:
            done += 1
            if symbol in seen:
                continue
            seen.add(symbol)
            try:
                weekly = source.get_weekly_prices(symbol, lookback_weeks=lookback_weeks)
                if weekly.empty:
                    logger.warning("%s (%d/%d): sin precio, se omite", symbol, done, total)
                    continue
                name, _sector, _pct = source.get_profile(symbol)
                facts = get_company_facts(symbol)
                result[symbol] = TickerData(symbol, universe_name, name, weekly, facts)
                if done % 25 == 0:
                    logger.info("Descarga base: %d/%d tickers (%s)", done, total, symbol)
            except Exception:
                logger.exception("%s: error en descarga base, se omite", symbol)
    logger.info("Descarga base completada: %d/%d tickers con datos", len(result), total)
    return result


def _fetch_institutional_by_quarter(
    tickers: dict[str, TickerData], quarters: list[date], inst_names: list[str],
) -> dict[date, dict[str, tuple[int, int]]]:
    """Descarga las holdings 13F-HR de `inst_names` para cada trimestre
    histórico solicitado, matcheadas contra nuestro universo por nombre de
    empresa. Devuelve {quarter: {symbol: (shares, n_instituciones)}}."""
    name_map: dict[str, str] = {}
    for td in tickers.values():
        if td.name:
            from app.screener.sec_13f import normalize_company_name
            key = normalize_company_name(td.name)
            if key:
                name_map[key] = td.symbol
        name_map[td.symbol.upper()] = td.symbol

    result: dict[date, dict[str, tuple[int, int]]] = {q: {} for q in quarters}

    for inst_name in inst_names:
        cik = search_institution_cik(inst_name)
        if not cik:
            logger.warning("13F: no se encontró CIK para %s, se omite en todos los trimestres", inst_name)
            continue
        for q in quarters:
            try:
                if inst_name in MULTI_CIK_OVERRIDES:
                    holdings = []
                    for sub_cik in MULTI_CIK_OVERRIDES[inst_name]:
                        sub_holdings, _rd = download_institution_holdings(sub_cik, inst_name, target_quarter=q)
                        holdings.extend(sub_holdings)
                else:
                    holdings, _rd = download_institution_holdings(cik, inst_name, target_quarter=q)
            except Exception:
                logger.exception("13F: error descargando %s trimestre %s", inst_name, q)
                continue

            if not holdings:
                continue
            per_symbol: dict[str, int] = {}
            for h in holdings:
                sym = _match_ticker(h.name_issuer, name_map)
                if sym is None:
                    continue
                per_symbol[sym] = per_symbol.get(sym, 0) + h.shares

            for sym, shares in per_symbol.items():
                prev_shares, prev_count = result[q].get(sym, (0, 0))
                result[q][sym] = (prev_shares + shares, prev_count + 1)

        logger.info("13F: %s procesado (%d trimestres)", inst_name, len(quarters))

    return result


def _institutional_data_for(
    symbol: str, as_of: date, holdings_by_quarter: dict[date, dict[str, tuple[int, int]]],
) -> InstitutionalData | None:
    current_q = _available_quarter_as_of(as_of)
    prior_q = prior_quarter_end(current_q)
    cur = holdings_by_quarter.get(current_q, {}).get(symbol)
    if cur is None:
        return None
    pri = holdings_by_quarter.get(prior_q, {}).get(symbol)
    return InstitutionalData(
        current_holders=cur[1],
        prior_holders=pri[1] if pri else None,
        current_shares=cur[0],
        prior_shares=pri[0] if pri else None,
    )


def _fundamentals_as_of(td: TickerData, as_of: date) -> tuple[FundamentalData, object, object]:
    """Réplica de AlpacaDataSource.get_fundamentals() + get_edgar_data pero a
    partir del companyfacts ya descargado, filtrado por fecha real de
    publicación -- ver sec_edgar.get_edgar_data_from_facts."""
    if td.facts is None:
        from app.screener.sec_edgar import QualityMetrics, SupplySignal
        return FundamentalData(None, None, [], []), SupplySignal(None, None, 0), QualityMetrics(None, None, None, None)

    supply, eps, quality = get_edgar_data_from_facts(td.facts, as_of=as_of)
    fundamentals = FundamentalData(
        eps_quarterly_yoy_growth=_yoy_growth(eps.quarterly, 4) if len(eps.quarterly) >= 5 else None,
        eps_annual_growth=_yoy_growth(eps.annual, 1) if len(eps.annual) >= 2 else None,
        raw_quarterly_eps=eps.quarterly,
        raw_annual_eps=eps.annual,
    )
    return fundamentals, supply, quality


def _week_dates(reference_weekly: pd.DataFrame, weeks_back: int) -> list[date]:
    """Fechas semanales (viernes) para el backtest, EXCLUYENDO la semana en
    curso. El resample W-FRI etiqueta la semana incompleta de hoy con la
    fecha del viernes que todavía no ha llegado -- si esa fecha "futura"
    quedara persistida como run_date, un MAX(run_date) hecho por la
    producción en vivo (p.ej. update_portfolio.run() sin fecha explícita)
    la recogería en vez de la fecha real de hoy, rompiendo esa lógica.
    Por eso solo se admiten fechas estrictamente anteriores a hoy."""
    idx = reference_weekly.index[-(weeks_back + 1):]
    dates = [d.date() if hasattr(d, "date") else d for d in idx]
    dates = [d for d in dates if d < date.today()]
    return dates[-weeks_back:]


def run(
    weeks_back: int = WEEKS_BACK_DEFAULT,
    tickers_override: list[str] | None = None,
    institutions_override: list[str] | None = None,
) -> dict:
    init_db()

    if not (settings.alpaca_api_key and settings.alpaca_secret_key):
        raise RuntimeError("Backtest requiere ALPACA_API_KEY/ALPACA_SECRET_KEY (precio histórico real)")
    source = AlpacaDataSource(settings.alpaca_api_key, settings.alpaca_secret_key, request_delay_seconds=0.15)

    fetch_lookback = weeks_back + LOOKBACK_BUFFER_WEEKS

    symbols_by_universe = (
        {"manual": tickers_override} if tickers_override else _reduced_universe()
    )

    logger.info("=== Fase 1/4: descarga base (precio + EDGAR) ===")
    tickers = _fetch_all_ticker_data(source, symbols_by_universe, fetch_lookback)

    logger.info("=== Fase 1b/4: benchmark %s ===", BENCHMARK_SYMBOL)
    benchmark_weekly = source.get_weekly_prices(BENCHMARK_SYMBOL, lookback_weeks=fetch_lookback)
    if benchmark_weekly.empty:
        raise RuntimeError(f"Sin precio histórico para el benchmark {BENCHMARK_SYMBOL}")

    week_dates = _week_dates(benchmark_weekly, weeks_back)
    logger.info("Semanas del backtest: %s -> %s (%d semanas)", week_dates[0], week_dates[-1], len(week_dates))

    logger.info("=== Fase 2/4: tenencia institucional histórica ===")
    inst_names = institutions_override or TOP_INSTITUTION_NAMES
    quarters: list[date] = []
    q = latest_available_quarter()
    for _ in range(QUARTERS_BACK_INSTITUTIONAL):
        quarters.append(q)
        q = prior_quarter_end(q)
    holdings_by_quarter = _fetch_institutional_by_quarter(tickers, quarters, inst_names)

    # La sesión de BD se abre aquí, no al principio de run(): las fases 1 y 2
    # son puro I/O HTTP (pueden tardar 20+ min) y una sesión abierta tanto
    # tiempo sin usarse contra Neon (Postgres serverless) muere por inactividad
    # antes de que llegue a hacer su primera query real.
    db = SessionLocal()

    logger.info("=== Fase 3/4: persistiendo precio histórico + Opportunity semana a semana ===")
    benchmark_ticker = _get_or_create_ticker(db, BENCHMARK_SYMBOL, "benchmark", "SPDR S&P 500 ETF Trust", None)
    _upsert_price_snapshots(db, benchmark_ticker, benchmark_weekly)
    _update_latest_daily_price(benchmark_ticker, benchmark_weekly)
    db.commit()

    orm_tickers: dict[str, Ticker] = {}
    for symbol, td in tickers.items():
        ticker = _get_or_create_ticker(db, symbol, td.universe_name, td.name, None)
        _upsert_price_snapshots(db, ticker, td.weekly)
        _update_latest_daily_price(ticker, td.weekly)
        orm_tickers[symbol] = ticker
    db.commit()
    logger.info("Precio histórico persistido para %d tickers", len(orm_tickers))

    stats = {"weeks": len(week_dates), "tickers": len(tickers), "opportunities_written": 0, "errors": 0}

    for week_idx, week_date in enumerate(week_dates, start=1):
        week_ts = pd.Timestamp(week_date)
        benchmark_slice = benchmark_weekly[benchmark_weekly.index <= week_ts]
        try:
            benchmark_weinstein = analyze(benchmark_slice)
        except InsufficientDataError:
            logger.warning("Semana %s: histórico insuficiente para el benchmark, se omite semana entera", week_date)
            continue

        # Retornos 52 semanas de todo el universo, truncados a esta semana --
        # necesarios para el RS Rating (percentil) de los criterios L y Minervini.
        universe_returns: list[float] = []
        for td in tickers.values():
            slice_ = td.weekly[td.weekly.index <= week_ts]
            if len(slice_) >= 52:
                universe_returns.append(float(slice_["Close"].iloc[-1] / slice_["Close"].iloc[-52] - 1))

        for symbol, td in tickers.items():
            weekly_slice = td.weekly[td.weekly.index <= week_ts]
            try:
                weinstein_result = analyze(weekly_slice)
            except InsufficientDataError:
                continue

            try:
                fundamentals, supply_signal, quality = _fundamentals_as_of(td, week_date)
                dividend_data = DividendData(None, None, None)  # ver docstring: limitación de Alpaca, no del backtest
                institutional_data = _institutional_data_for(symbol, week_date, holdings_by_quarter)
                all_time_high = float(weekly_slice["High"].max())

                criteria = canslim.evaluate_all(
                    fundamentals, weekly_slice, benchmark_slice, benchmark_weinstein, supply_signal,
                    institutional_pct=None, all_time_high=all_time_high,
                    universe_returns=universe_returns, institutional_data=institutional_data,
                )
                score = scoring.compute_combined_score(weinstein_result, criteria, weekly_slice)
                strategies = evaluate_all_strategies(
                    weekly_slice, fundamentals, supply_signal, quality, dividend_data,
                    universe_returns=universe_returns,
                )
                _upsert_opportunity(db, orm_tickers[symbol], week_date, score, weinstein_result, criteria, strategies)
                stats["opportunities_written"] += 1
            except Exception:
                logger.exception("%s semana %s: error inesperado, se omite", symbol, week_date)
                stats["errors"] += 1
                db.rollback()

        db.commit()
        logger.info("Semana %d/%d (%s) persistida", week_idx, len(week_dates), week_date)

    db.close()

    logger.info("=== Fase 4/4: simulando cartera pública semana a semana ===")
    # Re-correr el backtest (p.ej. tras ampliar el universo) sin borrar antes
    # la cartera pública dejaría posiciones "open" del backtest anterior
    # interfiriendo con la simulación desde la primera semana -- mismo motivo
    # por el que resimulate_portfolio.py la borra antes de resimular.
    db = SessionLocal()
    try:
        deleted = db.query(PortfolioPosition).delete()
        db.commit()
        logger.info("Borradas %d posiciones de la cartera pública antes de resimular", deleted)
    finally:
        db.close()

    portfolio_stats = {"opened": 0, "closed": 0}
    for week_date in week_dates:
        try:
            r = update_portfolio.run(run_date=week_date)
            portfolio_stats["opened"] += r.get("opened", 0)
            portfolio_stats["closed"] += r.get("closed", 0)
        except Exception:
            logger.exception("update_portfolio falló en la semana %s", week_date)

    stats["portfolio"] = portfolio_stats
    logger.info("Backtest completado: %s", stats)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weeks", type=int, default=WEEKS_BACK_DEFAULT, help="Nº de semanas hacia atrás")
    parser.add_argument("--tickers", type=str, default=None, help="Lista separada por comas, override del universo (debug)")
    parser.add_argument("--institutions", type=str, default=None, help="Lista separada por comas, override de instituciones 13F (debug)")
    args = parser.parse_args()

    tickers_override = [s.strip().upper() for s in args.tickers.split(",")] if args.tickers else None
    institutions_override = [s.strip() for s in args.institutions.split(",")] if args.institutions else None

    result = run(weeks_back=args.weeks, tickers_override=tickers_override, institutions_override=institutions_override)
    print(result)


if __name__ == "__main__":
    main()
