"""Fuentes de datos para el screener.

YFinanceDataSource  -- wrapper yfinance (scraping Yahoo Finance). Solo fiable en
                       entornos locales; Yahoo bloquea IPs de datacenter (Railway).
AlpacaDataSource    -- Alpaca Markets API oficial (free tier: IEX feed, US stocks).
                       Sin bloqueo en Railway. Fundamentales EPS via SEC EDGAR XBRL.

Para cambiar de proveedor: reimplementa la misma interfaz de tres métodos sin
tocar weinstein.py / canslim.py.

Interfaz esperada:
    get_weekly_prices(symbol, lookback_weeks) -> pd.DataFrame [Open High Low Close Volume]
    get_fundamentals(symbol) -> FundamentalData
    get_profile(symbol) -> tuple[name|None, sector|None, institutional_pct|None]
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import pandas as pd
import requests
import yfinance as yf

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
_SESSION = requests.Session()
_SESSION.headers.update(_BROWSER_HEADERS)


@dataclass
class FundamentalData:
    eps_quarterly_yoy_growth: float | None
    eps_annual_growth: float | None
    raw_quarterly_eps: list[float]
    raw_annual_eps: list[float]


def _yoy_growth(series: list[float], periods_back: int) -> float | None:
    if len(series) <= periods_back:
        return None
    current, prior = series[-1], series[-1 - periods_back]
    if prior == 0:
        return None
    return (current - prior) / abs(prior)


# ---------------------------------------------------------------------------
# YFinance (local only)
# ---------------------------------------------------------------------------

class YFinanceDataSource:
    """Punto único de acceso a yfinance. Solo para uso local; Yahoo bloquea
    IPs de datacenter. Si cambias de proveedor, reimplementa esta clase."""

    def __init__(self, request_delay_seconds: float = 0.0):
        self._delay = request_delay_seconds

    def get_weekly_prices(self, symbol: str, lookback_weeks: int = 104) -> pd.DataFrame:
        ticker = yf.Ticker(symbol, session=_SESSION)
        daily = ticker.history(period=f"{lookback_weeks * 7 + 30}d", interval="1d")
        if self._delay:
            time.sleep(self._delay)
        if daily.empty:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        weekly = daily.resample("W-FRI").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
        ).dropna()
        return weekly.tail(lookback_weeks)

    def get_fundamentals(self, symbol: str) -> FundamentalData:
        ticker = yf.Ticker(symbol, session=_SESSION)
        q_eps = self._extract_eps_series(ticker.quarterly_income_stmt)
        a_eps = self._extract_eps_series(ticker.income_stmt)
        if self._delay:
            time.sleep(self._delay)

        return FundamentalData(
            eps_quarterly_yoy_growth=_yoy_growth(q_eps, 4) if len(q_eps) >= 5 else None,
            eps_annual_growth=_yoy_growth(a_eps, 1) if len(a_eps) >= 2 else None,
            raw_quarterly_eps=q_eps,
            raw_annual_eps=a_eps,
        )

    @staticmethod
    def _extract_eps_series(income_stmt: pd.DataFrame) -> list[float]:
        if income_stmt is None or income_stmt.empty or "Diluted EPS" not in income_stmt.index:
            return []
        row = income_stmt.loc["Diluted EPS"].dropna()
        row = row.sort_index()
        return [float(v) for v in row.tolist()]

    def get_profile(self, symbol: str) -> tuple[str | None, str | None, float | None]:
        try:
            info = yf.Ticker(symbol, session=_SESSION).info
        except Exception:
            return None, None, None
        if self._delay:
            time.sleep(self._delay)
        name = info.get("shortName") or info.get("longName")
        sector = info.get("sector")
        pct_institutional: float | None = (
            info.get("heldPercentInstitutions") or info.get("institutionPercentHeld")
        )
        return name, sector, pct_institutional


# ---------------------------------------------------------------------------
# Alpaca (Railway-compatible)
# ---------------------------------------------------------------------------

_ALPACA_PAPER_URL = "https://paper-api.alpaca.markets"


class AlpacaDataSource:
    """Alpaca Markets API oficial (free tier: IEX feed para US stocks).
    No bloqueado en Railway → permite que el cron diario corra en el servidor.

    OHLCV        : Alpaca Bars API (alpaca-py).
    EPS (C y A)  : SEC EDGAR XBRL companyfacts — misma infra que el criterio S.
    Perfil       : Alpaca /v2/assets/{symbol} para el nombre; sector=None
                   (los tickers existentes en BD conservan el sector previo).
    Institutional: None — no disponible en free tier (criterio I queda no verificable).
    """

    def __init__(self, api_key: str, secret_key: str, request_delay_seconds: float = 0.0):
        from alpaca.data.historical import StockHistoricalDataClient

        self._client = StockHistoricalDataClient(api_key, secret_key)
        self._api_key = api_key
        self._secret_key = secret_key
        self._delay = request_delay_seconds
        self._asset_cache: dict[str, dict] = {}

    def get_weekly_prices(self, symbol: str, lookback_weeks: int = 104) -> pd.DataFrame:
        from datetime import datetime, timedelta, timezone

        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        start = datetime.now(tz=timezone.utc) - timedelta(weeks=lookback_weeks + 4)
        request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=start)

        try:
            bars = self._client.get_stock_bars(request)
        except Exception:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        finally:
            if self._delay:
                time.sleep(self._delay)

        df = bars.df
        if df.empty:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        # bars.df tiene MultiIndex (symbol, timestamp) cuando se pide un solo símbolo
        if isinstance(df.index, pd.MultiIndex):
            if symbol not in df.index.get_level_values(0):
                return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
            daily = df.loc[symbol].copy()
        else:
            daily = df.copy()

        daily = daily.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
        daily = daily[["Open", "High", "Low", "Close", "Volume"]]

        if daily.index.tz is not None:
            daily.index = daily.index.tz_convert(None)

        weekly = daily.resample("W-FRI").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
        ).dropna()
        return weekly.tail(lookback_weeks)

    def get_fundamentals(self, symbol: str) -> FundamentalData:
        from app.screener.sec_edgar import get_eps_series

        eps = get_eps_series(symbol)
        return FundamentalData(
            eps_quarterly_yoy_growth=_yoy_growth(eps.quarterly, 4) if len(eps.quarterly) >= 5 else None,
            eps_annual_growth=_yoy_growth(eps.annual, 1) if len(eps.annual) >= 2 else None,
            raw_quarterly_eps=eps.quarterly,
            raw_annual_eps=eps.annual,
        )

    def get_profile(self, symbol: str) -> tuple[str | None, str | None, float | None]:
        """Nombre via Alpaca /v2/assets. Sector e institutional_pct no disponibles
        en free tier — los tickers existentes en BD conservan sus valores previos."""
        try:
            if symbol not in self._asset_cache:
                resp = requests.get(
                    f"{_ALPACA_PAPER_URL}/v2/assets/{symbol}",
                    headers={
                        "APCA-API-KEY-ID": self._api_key,
                        "APCA-API-SECRET-KEY": self._secret_key,
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    self._asset_cache[symbol] = resp.json()
            asset = self._asset_cache.get(symbol, {})
            return asset.get("name"), None, None
        except Exception:
            return None, None, None
