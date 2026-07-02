"""Detección de catalizadores de inversión.

Fuentes:
- Earnings: yfinance ticker.earnings_dates (Q2 season ~11 julio)
- Insider buying: SEC EDGAR Form 4 por ticker (Railway-compatible; Yahoo Finance no)

Estrategia insider:
1. Obtiene CIKs de nuestros tickers via EDGAR company_tickers.json
2. Para cada CIK, consulta submissions.json → busca Form 4 recientes
3. Descarga XML del Form 4 → verifica transacción tipo P (Purchase)
"""
from __future__ import annotations

import json
import logging
import math
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, timedelta

logger = logging.getLogger("catalysts")

_EDGAR_USER_AGENT = "invest-feed-mvp research@invest-feed.com"
_EDGAR_DELAY = 0.12  # 10 req/s max según EDGAR ToS


@dataclass
class CatalystData:
    catalyst_type: str  # "earnings" | "insider_buy"
    symbol: str
    title: str
    source_id: str
    description: str | None = None
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Earnings — yfinance (Q2 season starts ~July 11, blank before that)
# ---------------------------------------------------------------------------

def detect_earnings(symbols: list[str], lookback_days: int = 3) -> list[CatalystData]:
    """Detecta earnings publicados en los últimos `lookback_days` días via yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance no disponible, skipping earnings")
        return []

    cutoff = date.today() - timedelta(days=lookback_days)
    results: list[CatalystData] = []

    for symbol in symbols:
        try:
            t = yf.Ticker(symbol)
            dates_df = t.earnings_dates
            if dates_df is None or dates_df.empty:
                continue

            for dt_idx in dates_df.index:
                d = _to_date(dt_idx)
                if d is None or d < cutoff or d > date.today():
                    continue

                row = dates_df.loc[dt_idx]
                eps_est = _safe_float(row.get("EPS Estimate"))
                eps_act = _safe_float(row.get("Reported EPS"))
                surprise = _safe_float(row.get("Surprise(%)"))

                if eps_act is None:
                    continue  # sin EPS real publicado, no es un earnings ya ocurrido

                if eps_est is not None and eps_act > eps_est:
                    pct = round(((eps_act - eps_est) / abs(eps_est)) * 100, 1) if eps_est != 0 else None
                    title = "Earnings beat" + (f" +{pct}%" if pct is not None else "")
                elif eps_est is not None and eps_act < eps_est:
                    title = "Earnings miss"
                else:
                    title = "Resultados publicados"

                desc_parts = []
                if eps_est is not None:
                    desc_parts.append(f"EPS estimado: {eps_est:.2f}")
                if eps_act is not None:
                    desc_parts.append(f"EPS real: {eps_act:.2f}")
                if surprise is not None:
                    desc_parts.append(f"Sorpresa: {surprise:+.1f}%")

                results.append(CatalystData(
                    catalyst_type="earnings",
                    symbol=symbol,
                    title=title,
                    source_id=f"earnings_{symbol}_{d.isoformat()}",
                    description=", ".join(desc_parts) if desc_parts else None,
                    extra={
                        "earnings_date": d.isoformat(),
                        "eps_estimated": eps_est,
                        "eps_actual": eps_act,
                        "surprise_pct": surprise,
                    },
                ))
                break  # solo el más reciente por ticker

        except Exception:
            logger.debug("Error obteniendo earnings de %s", symbol, exc_info=True)

    logger.info("Earnings detectados: %d de %d tickers", len(results), len(symbols))
    return results


# ---------------------------------------------------------------------------
# Insider buying — SEC EDGAR submissions por ticker (Railway-compatible)
# ---------------------------------------------------------------------------

def detect_insider_buys(symbols: list[str], lookback_days: int = 21) -> list[CatalystData]:
    """Detecta compras de insiders via SEC EDGAR Form 4 por ticker.

    1. Descarga company_tickers.json → mapa ticker→CIK
    2. Para cada CIK, consulta submissions.json → filtra Form 4 recientes
    3. Descarga XML del Form 4 → verifica transacción tipo P (Purchase)
    """
    symbol_set = {s.upper() for s in symbols}
    ticker_cik_map = _fetch_ticker_cik_map(symbol_set)

    if not ticker_cik_map:
        logger.warning("No se pudo obtener mapa ticker→CIK de EDGAR")
        return []

    cutoff = date.today() - timedelta(days=lookback_days)
    results: list[CatalystData] = []

    logger.info("Buscando Form 4 en EDGAR para %d tickers (lookback %d días)", len(ticker_cik_map), lookback_days)

    for ticker, cik in ticker_cik_map.items():
        try:
            recent_form4s = _get_recent_form4_for_cik(cik, cutoff)
            if not recent_form4s:
                continue

            # Comprueba el más reciente
            filing = recent_form4s[0]
            purchase = _parse_form4_purchase(filing["accession"], cik)
            if purchase is None:
                continue

            filing_date = _to_date(filing["date"])
            insider = purchase.get("insider_name", "Directivo")
            position = purchase.get("position", "")
            shares = purchase.get("shares")
            value_usd = purchase.get("value_usd")

            title = f"Compra insider: {insider}"
            if position:
                title += f" ({position})"

            desc_parts = []
            if shares:
                desc_parts.append(f"{shares:,} acciones")
            if value_usd:
                desc_parts.append(f"${value_usd:,}")

            source_key = insider[:30].replace(" ", "_")
            results.append(CatalystData(
                catalyst_type="insider_buy",
                symbol=ticker,
                title=title[:255],
                source_id=f"insider_{ticker}_{(filing_date or date.today()).isoformat()}_{source_key}",
                description=", ".join(desc_parts) if desc_parts else None,
                extra={
                    "filing_date": filing_date.isoformat() if filing_date else None,
                    "accession": filing["accession"],
                    "insider": insider,
                    "position": position,
                    "shares": shares,
                    "value_usd": value_usd,
                },
            ))

        except Exception:
            logger.debug("Error procesando insiders de %s", ticker, exc_info=True)
        finally:
            time.sleep(_EDGAR_DELAY)

    logger.info("Insider buys detectados: %d de %d tickers en universo", len(results), len(ticker_cik_map))
    return results


def _fetch_ticker_cik_map(symbol_set: set[str]) -> dict[str, str]:
    """Descarga el mapa ticker→CIK de SEC EDGAR (CIK de 10 dígitos con padding)."""
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _EDGAR_USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        return {
            item["ticker"].upper(): str(item["cik_str"]).zfill(10)
            for item in data.values()
            if item["ticker"].upper() in symbol_set
        }
    except Exception:
        logger.debug("Error descargando company_tickers.json", exc_info=True)
        return {}


def _get_recent_form4_for_cik(cik: str, cutoff: date) -> list[dict]:
    """Consulta EDGAR submissions.json para un CIK y devuelve Form 4 recientes."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _EDGAR_USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])

        results = []
        for form, filing_date_str, accession in zip(forms, dates, accessions):
            if form != "4":
                continue
            d = _to_date(filing_date_str)
            if d is None or d < cutoff:
                break  # filings están ordenados por fecha desc, stop early
            results.append({"date": filing_date_str, "accession": accession})

        return results

    except Exception:
        logger.debug("Error obteniendo submissions de CIK %s", cik, exc_info=True)
        return []


def _parse_form4_purchase(accession: str, cik: str) -> dict | None:
    """Descarga y parsea el XML de un Form 4. Devuelve info de la compra o None si es venta/none."""
    if not accession or not cik:
        return None

    acc_nodash = accession.replace("-", "")
    cik_int = int(cik)
    xml_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
        f"{acc_nodash}/{accession}.xml"
    )

    try:
        req = urllib.request.Request(xml_url, headers={"User-Agent": _EDGAR_USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()

        root = ET.fromstring(content)

        # Buscar transacciones no-derivadas tipo P (Purchase)
        shares = None
        price = None
        has_purchase = False

        for tx in root.iter("nonDerivativeTransaction"):
            code_el = tx.find(".//transactionCode")
            if code_el is None or code_el.text != "P":
                continue
            has_purchase = True
            shares_el = tx.find(".//transactionShares/value")
            price_el = tx.find(".//transactionPricePerShare/value")
            if shares_el is not None and shares_el.text:
                shares = _safe_int(shares_el.text)
            if price_el is not None and price_el.text:
                price = _safe_float(price_el.text)
            break

        if not has_purchase:
            return None

        insider_name = ""
        position = ""
        name_el = root.find(".//reportingOwner/reportingOwnerId/rptOwnerName")
        if name_el is not None:
            insider_name = (name_el.text or "").strip()
        pos_el = root.find(".//reportingOwner/reportingOwnerRelationship/officerTitle")
        if pos_el is not None:
            position = (pos_el.text or "").strip()

        value_usd = int(shares * price) if shares and price else None

        return {
            "insider_name": insider_name or "Directivo",
            "position": position,
            "shares": shares,
            "value_usd": value_usd,
        }

    except Exception:
        logger.debug("Error parseando Form 4 %s", accession, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_date(val) -> date | None:
    if val is None:
        return None
    if isinstance(val, date) and not hasattr(val, "hour"):
        return val
    if hasattr(val, "date"):
        return val.date()
    if hasattr(val, "to_pydatetime"):
        return val.to_pydatetime().date()
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(val)[:10]).date()
    except Exception:
        return None


def _safe_float(val) -> float | None:
    try:
        if val is None:
            return None
        f = float(val)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> int | None:
    f = _safe_float(val)
    return int(f) if f is not None else None
