"""Universo de tickers para el screener.

S&P 500 / Nasdaq 100  : scraping Wikipedia / slickcharts (fuente primaria, siempre actualizado).
                         Universo US puro, compatible con la fuente de datos Alpaca.

Política de errores:
  - S&P 500 → fallo levanta UniverseScrapeError (aborta el job).
  - Nasdaq 100 → fallo (p.ej. bloqueo anti-bot de slickcharts a IPs de datacenter
    de Railway, ya visto con Yahoo/iShares) cae a `_NASDAQ100_FALLBACK`, una lista
    estática congelada en el último scraping exitoso. El índice rebalancea ~1 vez
    al año, así que quedarse unas semanas desactualizado es preferible a que todo
    el job (y por tanto update_portfolio) se quede sin correr días seguidos.

Si este scraping rompe, el job debe loguearlo claramente y NO fallar en
silencio con una lista vacía — mejor abortar (o caer a fallback, para Nasdaq100)
que procesar con datos incompletos.

NOTA: Russell 2000 y los índices europeos se soportaron en su momento, pero se
retiraron -- el universo Russell (~2000 tickers extra) disparó el volumen de
datos históricos guardados y agotó el espacio de la BD (Neon free tier). Ver
histórico de git si hace falta reintroducir alguno.
"""
from __future__ import annotations

import io
import logging

import pandas as pd
import requests

logger = logging.getLogger(__name__)

SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
# Wikipedia quitó la tabla de componentes de la página de Nasdaq-100 (ahora solo
# enlaza externamente a nasdaq.com) -- slickcharts sí mantiene la tabla completa.
NASDAQ100_URL = "https://www.slickcharts.com/nasdaq100"

# Congelado desde el último scraping exitoso de slickcharts (2026-07-17).
# Usado solo cuando el scraping en vivo falla -- ver política de errores arriba.
_NASDAQ100_FALLBACK: list[str] = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "ALAB", "ALNY", "AMAT",
    "AMD", "AMGN", "AMZN", "APP", "ARM", "ASML", "AVGO", "AXON", "BKNG", "BKR",
    "CCEP", "CDNS", "CEG", "CMCSA", "COST", "CPRT", "CRWD", "CRWV", "CSCO", "CSX",
    "CTAS", "DASH", "DDOG", "DXCM", "EA", "EXC", "FANG", "FAST", "FER", "FTNT",
    "GEHC", "GILD", "GOOG", "GOOGL", "HON", "HONA", "IDXX", "INTC", "INTU", "ISRG",
    "KDP", "KHC", "KLAC", "LIN", "LITE", "LRCX", "MAR", "MCHP", "MDLZ", "MELI",
    "META", "MNST", "MPWR", "MRVL", "MSFT", "MSTR", "MU", "NBIS", "NFLX", "NVDA",
    "NXPI", "ODFL", "ORLY", "PANW", "PAYX", "PCAR", "PDD", "PEP", "PLTR", "PYPL",
    "QCOM", "REGN", "RKLB", "ROP", "ROST", "SBUX", "SHOP", "SNDK", "SNPS", "SPCX",
    "STX", "TER", "TMUS", "TRI", "TSLA", "TTWO", "TXN", "VRTX", "WBD", "WDAY",
    "WDC", "WMT", "XEL",
]
_HEADERS = {"User-Agent": "invest-feed-mvp/0.1 (contacto: escanillaalberto@gmail.com)"}


class UniverseScrapeError(RuntimeError):
    """Se lanza si el scraping no devuelve una lista de tickers plausible."""


def _fetch_tables(url: str) -> list[pd.DataFrame]:
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    return pd.read_html(io.StringIO(resp.text))


def get_sp500_tickers() -> list[str]:
    tables = _fetch_tables(SP500_WIKI_URL)
    df = tables[0]
    if "Symbol" not in df.columns:
        raise UniverseScrapeError("Tabla S&P500 de Wikipedia cambió de estructura (sin columna 'Symbol')")
    tickers = df["Symbol"].astype(str).str.replace(".", "-", regex=False).str.strip().tolist()
    if len(tickers) < 400:
        raise UniverseScrapeError(f"S&P500 scraping devolvió solo {len(tickers)} tickers, esperado ~500")
    return sorted(set(tickers))


def get_nasdaq100_tickers() -> list[str]:
    tables = _fetch_tables(NASDAQ100_URL)
    candidate = None
    for t in tables:
        cols = {c.strip().lower() for c in t.columns.astype(str)}
        if "ticker" in cols or "symbol" in cols:
            candidate = t
            break
    if candidate is None:
        raise UniverseScrapeError("No se encontró tabla con columna Ticker/Symbol en slickcharts Nasdaq-100")
    col = "Ticker" if "Ticker" in candidate.columns else "Symbol"
    tickers = candidate[col].astype(str).str.replace(".", "-", regex=False).str.strip().tolist()
    if len(tickers) < 80:
        raise UniverseScrapeError(f"Nasdaq100 scraping devolvió solo {len(tickers)} tickers, esperado ~100")
    return sorted(set(tickers))


def get_universe() -> dict[str, list[str]]:
    """Devuelve el universo completo de tickers agrupados por índice de origen.

    Estructura: {"sp500": [...], "nasdaq100": [...]}

    S&P500 es obligatorio (fallo → UniverseScrapeError). Nasdaq100 cae a la
    lista estática congelada si el scraping en vivo falla.
    """
    universes: dict[str, list[str]] = {
        "sp500": get_sp500_tickers(),
    }
    try:
        universes["nasdaq100"] = get_nasdaq100_tickers()
    except Exception as exc:
        logger.warning(
            "Nasdaq100 scraping falló (%s), usando lista estática congelada de %d tickers",
            exc, len(_NASDAQ100_FALLBACK),
        )
        universes["nasdaq100"] = list(_NASDAQ100_FALLBACK)
    return universes
