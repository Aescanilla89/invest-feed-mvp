"""Universo de tickers para el screener.

S&P 500 / Nasdaq 100  : scraping Wikipedia (fuente primaria, siempre actualizado).
Russell 2000           : holdings CSV del ETF iShares IWM (~2000 small caps US).
                         Funciona en Railway via Alpaca (todos son tickers US).
Europa (sin microcaps) : FTSE 100, DAX 40, CAC 40, IBEX 35, FTSE MIB, AEX via Wikipedia.
                         Tickers en formato yfinance con sufijo de bolsa (.L, .DE, .PA…).
                         NOTA: Solo funcionan localmente con yfinance; Yahoo bloquea Railway,
                         por lo que en Railway estos tickers se saltan silenciosamente.

Política de errores:
  - S&P 500 / Russell 2000 → fallo levanta UniverseScrapeError (abortan el job).
  - Nasdaq 100 → fallo (p.ej. bloqueo anti-bot de slickcharts a IPs de datacenter
    de Railway, ya visto con Yahoo/iShares) cae a `_NASDAQ100_FALLBACK`, una lista
    estática congelada en el último scraping exitoso. El índice rebalancea ~1 vez
    al año, así que quedarse unas semanas desactualizado es preferible a que todo
    el job (y por tanto update_portfolio) se quede sin correr días seguidos.
  - Índices europeos → fallo loguea warning y continúa con el resto de índices.

Si este scraping rompe, el job debe loguearlo claramente y NO fallar en
silencio con una lista vacía — mejor abortar (o caer a fallback, para Nasdaq100)
que procesar con datos incompletos.
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
RUSSELL2000_ISHARES_URL = (
    "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/"
    "1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
)

# (url, lista de posibles nombres de columna ticker, sufijo yfinance, min tickers esperados)
_EUROPEAN_INDICES: list[tuple[str, list[str], str, int]] = [
    ("https://en.wikipedia.org/wiki/FTSE_100_Index", ["EPIC", "Ticker", "Symbol"], ".L", 80),
    ("https://en.wikipedia.org/wiki/DAX", ["Ticker symbol", "Ticker", "Symbol"], ".DE", 30),
    ("https://en.wikipedia.org/wiki/CAC_40", ["Ticker", "Symbol", "Code"], ".PA", 30),
    ("https://en.wikipedia.org/wiki/IBEX_35", ["Ticker", "Symbol", "Code"], ".MC", 25),
    ("https://en.wikipedia.org/wiki/FTSE_MIB", ["Ticker", "Symbol", "Code"], ".MI", 25),
    ("https://en.wikipedia.org/wiki/AEX_index", ["Ticker", "Symbol", "Code"], ".AS", 15),
]

_HEADERS = {"User-Agent": "invest-feed-mvp/0.1 (contacto: escanillaalberto@gmail.com)"}
_ISHARES_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.ishares.com/",
}


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


def get_russell2000_tickers() -> list[str]:
    """Obtiene los componentes del Russell 2000 desde el CSV de holdings del ETF iShares IWM.

    El CSV de iShares incluye filas de metadatos al principio y posiciones de cash al
    final; se localizan la cabecera real y se filtran las filas equity.
    Usa csv.DictReader (no pandas) para manejar correctamente los campos con comas.
    """
    import csv as _csv

    try:
        resp = requests.get(RUSSELL2000_ISHARES_URL, headers=_ISHARES_HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as exc:
        raise UniverseScrapeError(f"No se pudo descargar IWM holdings de iShares: {exc}") from exc

    text = resp.text
    if text.lstrip().startswith("<"):
        raise UniverseScrapeError(
            "iShares IWM devolvió HTML en lugar de CSV (bot detection). "
            "El screener continuará sin Russell 2000 en esta corrida."
        )

    lines = text.splitlines()

    # Localizar la fila de cabecera real: primera línea donde "Ticker" es un campo separado
    header_idx = None
    for i, line in enumerate(lines):
        fields = [f.strip().strip('"') for f in line.split(",")]
        if "Ticker" in fields and "Name" in fields:
            header_idx = i
            break

    if header_idx is None:
        raise UniverseScrapeError(
            "iShares IWM CSV: no se encontró fila de cabecera con columnas 'Ticker' y 'Name'."
        )

    csv_text = "\n".join(lines[header_idx:])
    reader = _csv.DictReader(io.StringIO(csv_text))

    tickers: list[str] = []
    for row in reader:
        ticker = (row.get("Ticker") or "").strip().strip('"')
        asset_class = (row.get("Asset Class") or "").strip()
        if not ticker or ticker in ("-", "CASH_USD"):
            continue
        if asset_class and asset_class != "Equity":
            continue
        tickers.append(ticker.replace(".", "-"))

    if len(tickers) < 1500:
        raise UniverseScrapeError(
            f"Russell 2000 scraping devolvió solo {len(tickers)} tickers, esperado ≥1500. "
            "Comprueba que el CSV de iShares IWM sigue siendo accesible."
        )

    return sorted(set(tickers))


def _scrape_european_index(url: str, ticker_cols: list[str], suffix: str, min_tickers: int) -> list[str]:
    """Descarga una página Wikipedia de un índice europeo y extrae tickers en formato yfinance.

    Prueba cada nombre de columna en ticker_cols hasta encontrar una tabla con al menos
    min_tickers filas válidas. Añade el sufijo de bolsa si el ticker no lo lleva ya.
    Devuelve lista vacía (con warning) si no puede obtener datos — nunca propaga la excepción
    para que un índice roto no aborte la corrida completa.
    """
    try:
        tables = _fetch_tables(url)
    except Exception as exc:
        logger.warning("Europa | %s: error al descargar página (%s)", url, exc)
        return []

    cols_to_try = [c.strip().lower() for c in ticker_cols]

    for table in tables:
        col_map = {str(c).strip().lower(): c for c in table.columns}
        for col_lower in cols_to_try:
            if col_lower not in col_map:
                continue
            actual_col = col_map[col_lower]
            raw = table[actual_col].astype(str).str.strip().str.replace(r"\s+", "", regex=True)
            candidates = [t for t in raw if t and t != "nan" and not t.startswith("nan")]
            if len(candidates) < min_tickers:
                continue
            # Añadir sufijo de bolsa si el ticker no lo tiene ya
            result = [t if "." in t else f"{t}{suffix}" for t in candidates]
            logger.info("Europa | %s: %d tickers (col '%s', sufijo '%s')", url, len(result), actual_col, suffix)
            return sorted(set(result))

    logger.warning(
        "Europa | %s: no se encontró columna válida (probadas: %s). "
        "La página de Wikipedia puede haber cambiado de estructura.",
        url, ticker_cols,
    )
    return []


def get_european_tickers() -> dict[str, list[str]]:
    """Devuelve tickers por índice para los principales mercados europeos (sin microcaps).

    Índices incluidos: FTSE 100, DAX 40, CAC 40, IBEX 35, FTSE MIB, AEX (~290 large/mid caps).
    Los tickers usan el formato yfinance con sufijo de bolsa ({TICKER}.{SUFFIX}).

    NOTA: Estos tickers solo funcionan con yfinance (entorno local). En Railway con Alpaca,
    los tickers europeos se saltarán silenciosamente con InsufficientDataError.
    """
    index_names = ["ftse100", "dax40", "cac40", "ibex35", "ftsemib", "aex"]
    result: dict[str, list[str]] = {}
    for name, (url, cols, suffix, min_t) in zip(index_names, _EUROPEAN_INDICES):
        tickers = _scrape_european_index(url, cols, suffix, min_t)
        if tickers:
            result[name] = tickers
    return result


def get_universe() -> dict[str, list[str]]:
    """Devuelve el universo completo de tickers agrupados por índice de origen.

    Estructura: {"sp500": [...], "nasdaq100": [...], "russell2000": [...],
                 "ftse100": [...], "dax40": [...], ...}

    S&P500 y Nasdaq100 son obligatorios (fallo → UniverseScrapeError).
    Russell 2000 y Europa fallan gracefully (warning + continúa sin ellos).
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
    try:
        universes["russell2000"] = get_russell2000_tickers()
        logger.info("Russell 2000: %d tickers cargados", len(universes["russell2000"]))
    except UniverseScrapeError as exc:
        logger.warning("Russell 2000 no disponible esta corrida: %s", exc)
    universes.update(get_european_tickers())
    return universes
