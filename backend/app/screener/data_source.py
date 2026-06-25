"""Wrapper sobre yfinance. Abstrae la fuente de datos para poder cambiarla
sin tocar weinstein.py / canslim.py, que solo conocen estos DataFrames.

Limitaciones conocidas de yfinance (no oficial, scraping de Yahoo Finance):
- Sin API key ni SLA: puede romperse sin aviso si Yahoo cambia su estructura.
- Rate limit no documentado; lotes grandes (S&P500 + Nasdaq100, ~600 tickers)
  necesitan pausas para evitar HTTP 429.
- Cobertura de datos fundamentales (earnings) inconsistente fuera de large-cap.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import pandas as pd
import requests
import yfinance as yf

# Yahoo Finance bloquea IPs de cloud sin User-Agent de navegador.
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


class YFinanceDataSource:
    """Punto único de acceso a yfinance. Si cambias de proveedor, solo
    reimplementas esta clase manteniendo la misma interfaz."""

    def __init__(self, request_delay_seconds: float = 0.0):
        # request_delay_seconds > 0 recomendado en jobs batch sobre cientos
        # de tickers para mitigar rate-limiting no documentado de Yahoo.
        self._delay = request_delay_seconds

    def get_weekly_prices(self, symbol: str, lookback_weeks: int = 104) -> pd.DataFrame:
        """OHLCV semanal. lookback_weeks=104 (~2 años) da margen suficiente
        para una media móvil de 30 semanas con histórico previo a la ventana."""
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
        # `Ticker.quarterly_earnings` / `Ticker.earnings` están deprecados y
        # ya no devuelven datos (Yahoo retiró ese endpoint) -- se usa el EPS
        # de income_stmt, que sigue activo.
        ticker = yf.Ticker(symbol, session=_SESSION)
        q_eps = self._extract_eps_series(ticker.quarterly_income_stmt)
        a_eps = self._extract_eps_series(ticker.income_stmt)
        if self._delay:
            time.sleep(self._delay)

        q_growth = self._yoy_growth(q_eps, periods_back=4) if len(q_eps) >= 5 else None
        a_growth = self._yoy_growth(a_eps, periods_back=1) if len(a_eps) >= 2 else None

        return FundamentalData(
            eps_quarterly_yoy_growth=q_growth,
            eps_annual_growth=a_growth,
            raw_quarterly_eps=q_eps,
            raw_annual_eps=a_eps,
        )

    @staticmethod
    def _extract_eps_series(income_stmt: pd.DataFrame) -> list[float]:
        """income_stmt de yfinance trae columnas (periodos) en orden
        descendente (más reciente primero). Se devuelve en orden ascendente
        para que _yoy_growth pueda asumir que el último elemento es el más
        reciente."""
        if income_stmt is None or income_stmt.empty or "Diluted EPS" not in income_stmt.index:
            return []
        row = income_stmt.loc["Diluted EPS"].dropna()
        row = row.sort_index()  # las columnas son Timestamps de fin de periodo
        return [float(v) for v in row.tolist()]

    def get_profile(self, symbol: str) -> tuple[str | None, str | None, float | None]:
        """Nombre, sector y % de acciones en manos institucionales.
        Best-effort: `.info` es pesado y propenso a fallos en yfinance.
        Nunca debe bloquear el score si falla.
        Tercer elemento: fracción 0-1 (ej. 0.62 = 62%) o None si no disponible."""
        try:
            info = yf.Ticker(symbol, session=_SESSION).info
        except Exception:
            return None, None, None
        if self._delay:
            time.sleep(self._delay)
        name = info.get("shortName") or info.get("longName")
        sector = info.get("sector")
        # Yahoo expone el campo con dos nombres distintos según la versión.
        pct_institutional: float | None = (
            info.get("heldPercentInstitutions") or info.get("institutionPercentHeld")
        )
        return name, sector, pct_institutional

    @staticmethod
    def _yoy_growth(series: list[float], periods_back: int) -> float | None:
        if len(series) <= periods_back:
            return None
        current, prior = series[-1], series[-1 - periods_back]
        if prior == 0:
            return None
        return (current - prior) / abs(prior)
