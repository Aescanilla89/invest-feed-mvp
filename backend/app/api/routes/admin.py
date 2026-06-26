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
