"""Endpoints de administración para operaciones manuales.
Protegidos por ADMIN_SECRET — no exponer públicamente sin token."""
import threading
import traceback

from fastapi import APIRouter, Depends, HTTPException, Header

from app.core.config import settings
from app.jobs import run_screener
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
    """Genera explicaciones para el top 10 de la última corrida.
    Se puede llamar en cualquier momento — no requiere que el screener haya terminado."""
    from sqlalchemy import func

    from app.ai.cache import get_or_create_explanation
    from app.ai.explainer import ClaudeExplainer, ExplanationError
    from app.core.db import SessionLocal
    from app.models.orm import Opportunity, Ticker
    from app.screener.canslim import CriterionResult
    from app.screener.weinstein import WeinsteinResult

    db = SessionLocal()
    try:
        run_date = db.query(func.max(Opportunity.run_date)).scalar()
        if not run_date:
            return {"error": "No hay corridas en BD"}

        top10 = (
            db.query(Opportunity, Ticker)
            .join(Ticker, Opportunity.ticker_id == Ticker.id)
            .filter(Opportunity.run_date == run_date)
            .order_by(Opportunity.combined_score.desc())
            .limit(10)
            .all()
        )

        try:
            explainer = ClaudeExplainer()
        except ExplanationError as exc:
            return {"error": str(exc)}

        results = []
        for opp, ticker in top10:
            try:
                weinstein = WeinsteinResult(
                    stage=opp.weinstein_stage,
                    weeks_in_stage=opp.weeks_in_stage,
                    ma_slope_pct=opp.weinstein_ma_slope_pct,
                    relative_volume=opp.weinstein_relative_volume,
                    is_transition_1_to_2=opp.weinstein_transition,
                )
                criteria = {
                    k: CriterionResult(value=v["value"], detail=v["detail"])
                    for k, v in opp.canslim_criteria.items()
                }
                exp = get_or_create_explanation(db, ticker, run_date, opp.combined_score, weinstein, criteria, explainer)
                db.commit()
                results.append({"ticker": ticker.symbol, "ok": exp is not None})
            except Exception:
                db.rollback()
                results.append({"ticker": ticker.symbol, "ok": False, "error": traceback.format_exc()})

        return {"run_date": run_date.isoformat(), "results": results}
    except Exception:
        return {"error": traceback.format_exc()}
    finally:
        db.close()


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
