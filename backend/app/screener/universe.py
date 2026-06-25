"""Universo de tickers: S&P 500 + Nasdaq 100, vía scraping de Wikipedia
en cada ejecución del job (decisión: priorizar estar siempre actualizado
sobre la fragilidad de depender de una página externa que puede cambiar
de estructura HTML).

Si este scraping rompe, el job debe loguearlo claramente y NO fallar en
silencio con una lista vacía -- mejor abortar la corrida del día.
"""
from __future__ import annotations

import io

import pandas as pd
import requests

SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_WIKI_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"

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
    tables = _fetch_tables(NASDAQ100_WIKI_URL)
    candidate = None
    for t in tables:
        cols = {c.strip().lower() for c in t.columns.astype(str)}
        if "ticker" in cols or "symbol" in cols:
            candidate = t
            break
    if candidate is None:
        raise UniverseScrapeError("No se encontró tabla con columna Ticker/Symbol en Nasdaq-100 Wikipedia")
    col = "Ticker" if "Ticker" in candidate.columns else "Symbol"
    tickers = candidate[col].astype(str).str.replace(".", "-", regex=False).str.strip().tolist()
    if len(tickers) < 80:
        raise UniverseScrapeError(f"Nasdaq100 scraping devolvió solo {len(tickers)} tickers, esperado ~100")
    return sorted(set(tickers))


def get_universe() -> dict[str, list[str]]:
    """Devuelve {"sp500": [...], "nasdaq100": [...]} con duplicados ya
    resueltos a nivel de unión si se necesita, manteniendo el origen
    de cada ticker para el campo `universe` del modelo Ticker."""
    return {
        "sp500": get_sp500_tickers(),
        "nasdaq100": get_nasdaq100_tickers(),
    }
