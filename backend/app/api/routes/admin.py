"""Endpoints de administración para operaciones manuales.
Protegidos por ADMIN_SECRET — no exponer públicamente sin token."""
import threading
import traceback
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Header

from app.core.config import settings
from app.jobs import detect_catalysts, run_screener
from app.screener import universe

router = APIRouter(prefix="/admin", tags=["admin"])


def _verify_token(x_admin_secret: str | None = Header(default=None)) -> None:
    if not settings.admin_secret or x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/run-screener")
def trigger_screener(
    limit: int | None = None,
    _: None = Depends(_verify_token),
) -> dict:
    """Lanza el screener en background. Devuelve inmediatamente."""
    def _job():
        try:
            symbols = universe.get_universe()
            if limit:
                symbols = {k: v[:limit] for k, v in symbols.items()}
            run_screener.run(symbols)
        except Exception:
            import logging
            logging.getLogger("admin").exception("Screener background job falló")

    thread = threading.Thread(target=_job, daemon=True)
    thread.start()
    tickers_approx = limit * 2 if limit else "~600"
    return {"status": "started", "tickers": tickers_approx}


@router.post("/generate-explanations")
def generate_explanations(_: None = Depends(_verify_token)) -> dict:
    """Genera explicaciones para el top N de la última corrida en background.
    Devuelve inmediatamente — las explicaciones aparecen en el feed al terminar."""
    from sqlalchemy import func

    from app.ai.cache import get_or_create_explanation
    from app.ai.explainer import ClaudeExplainer, ExplanationError
    from app.core.db import SessionLocal
    from app.models.orm import Opportunity, Ticker
    from app.screener.canslim import CriterionResult
    from app.screener.weinstein import WeinsteinResult

    def _job():
        import logging
        log = logging.getLogger("admin")
        db = SessionLocal()
        try:
            run_date = db.query(func.max(Opportunity.run_date)).scalar()
            if not run_date:
                log.warning("generate-explanations: no hay corridas en BD")
                return

            candidates = (
                db.query(Opportunity, Ticker)
                .join(Ticker, Opportunity.ticker_id == Ticker.id)
                .filter(Opportunity.run_date == run_date)
                .order_by(Opportunity.combined_score.desc())
                .all()
            )
            top_n = [(opp, t) for opp, t in candidates if opp.combined_score >= settings.explanation_min_score][:settings.explanation_max_per_run]

            try:
                explainer = ClaudeExplainer()
            except ExplanationError as exc:
                log.error("generate-explanations: no se pudo crear explainer: %s", exc)
                return

            for opp, ticker in top_n:
                try:
                    weinstein = WeinsteinResult(
                        stage=opp.weinstein_stage,
                        weeks_in_stage=opp.weeks_in_stage,
                        ma_slope_pct=opp.weinstein_ma_slope_pct,
                        relative_volume=opp.weinstein_relative_volume,
                        is_transition_1_to_2=opp.weinstein_transition,
                        rsi=opp.weinstein_rsi if opp.weinstein_rsi is not None else 50.0,
                    )
                    criteria = {
                        k: CriterionResult(value=v["value"], detail=v["detail"])
                        for k, v in opp.canslim_criteria.items()
                    }
                    exp = get_or_create_explanation(db, ticker, run_date, opp.combined_score, weinstein, criteria, explainer)
                    db.commit()
                    log.info("generate-explanations: %s → %s", ticker.symbol, "ok" if exp else "sin cambio")
                except Exception:
                    db.rollback()
                    log.exception("generate-explanations: error en %s", ticker.symbol)
        finally:
            db.close()

    thread = threading.Thread(target=_job, daemon=True)
    thread.start()
    return {"status": "started", "max_tickers": settings.explanation_max_per_run}


@router.post("/update-institutional")
def trigger_institutional_update(
    quarter: str | None = None,
    institutions: str | None = None,
    force: bool = False,
    _: None = Depends(_verify_token),
) -> dict:
    """Descarga 13F-HR de las top-30 instituciones y actualiza institutional_holdings.
    Ejecutar una vez por trimestre (≈ 45 días después del cierre de cada trimestre).
    - quarter: fecha fin de trimestre en YYYY-MM-DD (por defecto: último disponible)
    - institutions: lista separada por comas (por defecto: top-30 hardcodeadas)
    - force: re-procesar aunque el trimestre ya esté en BD
    """
    from app.jobs.update_institutional import run as run_institutional

    target_quarter = date.fromisoformat(quarter) if quarter else None
    names = [n.strip() for n in institutions.split(",")] if institutions else None

    result_container: dict = {}

    def _job() -> None:
        try:
            result_container.update(run_institutional(
                quarter=target_quarter,
                institution_names=names,
                force=force,
            ))
        except Exception:
            import logging
            logging.getLogger("admin").exception("update_institutional background job falló")

    thread = threading.Thread(target=_job, daemon=True)
    thread.start()
    thread.join(timeout=600)  # máx 10 min — síncrono para poder ver el resultado

    return result_container if result_container else {"status": "running (timeout 10min excedido)"}


@router.post("/detect-catalysts")
def trigger_detect_catalysts(_: None = Depends(_verify_token)) -> dict:
    """Lanza la detección de catalizadores en background. Devuelve inmediatamente."""
    def _job():
        try:
            detect_catalysts.run()
        except Exception:
            import logging
            logging.getLogger("admin").exception("detect_catalysts background job falló")

    thread = threading.Thread(target=_job, daemon=True)
    thread.start()
    return {"status": "started"}


@router.get("/diagnose-catalysts")
def diagnose_catalysts(_: None = Depends(_verify_token)) -> dict:
    """Diagnóstico síncrono de catalizadores: prueba EDGAR Form 4 + yfinance earnings."""
    from datetime import date, timedelta
    from app.core.db import SessionLocal
    from app.models.orm import Opportunity, Ticker
    from app.screener.catalysts import _fetch_ticker_cik_map, _fetch_recent_form4_entries

    result: dict = {}
    db = SessionLocal()
    try:
        since = date.today() - timedelta(days=7)
        rows = (
            db.query(Ticker.symbol)
            .join(Opportunity, Opportunity.ticker_id == Ticker.id)
            .filter(Opportunity.run_date >= since)
            .distinct()
            .all()
        )
        symbols = [r[0] for r in rows]
        result["symbols_count"] = len(symbols)
        result["symbols_sample"] = symbols[:5]
    finally:
        db.close()

    if not symbols:
        result["error"] = "No hay tickers con oportunidades en los últimos 7 días"
        return result

    # Test EDGAR ticker→CIK map
    try:
        cik_map = _fetch_ticker_cik_map(set(symbols[:10]))
        result["edgar_cik_map_ok"] = True
        result["edgar_cik_sample"] = {k: v for k, v in list(cik_map.items())[:5]}
    except Exception as e:
        result["edgar_cik_map_error"] = str(e)

    # Test EDGAR Form 4 RSS
    try:
        entries = _fetch_recent_form4_entries(count=40)
        result["edgar_form4_entries"] = len(entries)
        # Filtrar los que coinciden con nuestros tickers
        cik_map_all = _fetch_ticker_cik_map(set(symbols))
        cik_to_ticker = {cik: t for t, cik in cik_map_all.items()}
        matches = [e for e in entries if cik_to_ticker.get(e.get("cik"))]
        result["edgar_form4_universe_matches"] = len(matches)
        result["edgar_form4_match_sample"] = [
            {"ticker": cik_to_ticker.get(e["cik"]), "date": e["date"]}
            for e in matches[:5]
        ]
    except Exception as e:
        result["edgar_form4_error"] = str(e)

    # Test yfinance earnings (puede estar bloqueado en Railway)
    import yfinance as yf
    for sym in symbols[:3]:
        try:
            t = yf.Ticker(sym)
            df = t.earnings_dates
            if df is None or df.empty:
                result[f"earnings_{sym}"] = "vacío"
            else:
                result[f"earnings_{sym}"] = f"ok — {len(df)} filas, cols={list(df.columns)}"
        except Exception as e:
            result[f"earnings_{sym}_error"] = str(e)

    # Prueba insiders yfinance (puede estar bloqueado en Railway)
    for sym in symbols[:3]:
        try:
            import yfinance as yf
            t = yf.Ticker(sym)
            tx = t.insider_transactions
            if tx is None or tx.empty:
                result[f"insiders_{sym}"] = "vacío"
            else:
                result[f"insiders_{sym}"] = f"ok — {len(tx)} filas, cols={list(tx.columns)}"
        except Exception as e:
            result[f"insiders_{sym}_error"] = str(e)

    return result


@router.get("/diagnose")
def diagnose(_: None = Depends(_verify_token)) -> dict:
    """Diagnóstico síncrono: verifica config, data source y 2 tickers. Devuelve errores inline."""
    result: dict = {}

    # Config
    result["alpaca_key_set"] = bool(settings.alpaca_api_key)
    result["anthropic_key_set"] = bool(settings.anthropic_api_key)

    # Data source
    try:
        from app.screener.data_source import AlpacaDataSource, YFinanceDataSource
        if settings.alpaca_api_key and settings.alpaca_secret_key:
            source = AlpacaDataSource(settings.alpaca_api_key, settings.alpaca_secret_key)
            result["data_source"] = "alpaca"
        else:
            source = YFinanceDataSource()
            result["data_source"] = "yfinance"
    except Exception:
        result["data_source_error"] = traceback.format_exc()
        return result

    # OHLCV test
    try:
        weekly = source.get_weekly_prices("AAPL", lookback_weeks=40)
        result["aapl_weeks"] = len(weekly)
        result["aapl_last_close"] = float(weekly["Close"].iloc[-1]) if not weekly.empty else None
    except Exception:
        result["ohlcv_error"] = traceback.format_exc()

    # EPS test
    try:
        fund = source.get_fundamentals("AAPL")
        result["aapl_q_eps_growth"] = fund.eps_quarterly_yoy_growth
        result["aapl_a_eps_growth"] = fund.eps_annual_growth
    except Exception:
        result["fundamentals_error"] = traceback.format_exc()

    # Universe test
    try:
        uni = universe.get_universe()
        result["universe_sp500"] = len(uni.get("sp500", []))
        result["universe_nasdaq100"] = len(uni.get("nasdaq100", []))
    except Exception:
        result["universe_error"] = traceback.format_exc()

    return result
