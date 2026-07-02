"""Detección de catalizadores de inversión.

Fuentes:
- Earnings: yfinance ticker.earnings_dates (Q2 earnings season arranca ~11 julio)
- Insider buying: SEC EDGAR Form 4 RSS (funciona desde Railway; Yahoo Finance no)

El job corre sobre los tickers activos (con oportunidades recientes) para
mantener el tiempo de ejecución manejable.
"""
from __future__ import annotations

import logging
import math
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, timedelta

logger = logging.getLogger("catalysts")

_EDGAR_USER_AGENT = "invest-feed-mvp research@invest-feed.com"


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
# Insider buying — SEC EDGAR Form 4 (Railway-compatible)
# ---------------------------------------------------------------------------

def detect_insider_buys(symbols: list[str], lookback_days: int = 21) -> list[CatalystData]:
    """Detecta compras de insiders vía SEC EDGAR Form 4 RSS.

    Flujo:
    1. Descarga EDGAR company_tickers.json (mapa ticker→CIK)
    2. Descarga RSS de los 100 Form 4 más recientes de EDGAR
    3. Filtra por tickers en nuestro universo
    4. Para cada match, descarga el XML del Form 4 para verificar que es compra
    """
    symbol_set = {s.upper() for s in symbols}
    ticker_cik_map = _fetch_ticker_cik_map(symbol_set)
    if not ticker_cik_map:
        logger.warning("No se pudo obtener mapa ticker→CIK de EDGAR")
        return []

    cutoff = date.today() - timedelta(days=lookback_days)
    recent_form4 = _fetch_recent_form4_entries(count=100)
    if not recent_form4:
        logger.warning("No se obtuvieron entradas Form 4 de EDGAR RSS")
        return []

    # CIK → ticker (invertir el mapa)
    cik_ticker_map = {cik: ticker for ticker, cik in ticker_cik_map.items()}

    results: list[CatalystData] = []
    seen_tickers: set[str] = set()

    for entry in recent_form4:
        cik = entry.get("cik")
        ticker = cik_ticker_map.get(cik)
        if ticker is None or ticker not in symbol_set:
            continue
        if ticker in seen_tickers:
            continue

        filing_date = _to_date(entry.get("date"))
        if filing_date is None or filing_date < cutoff:
            continue

        # Descarga el XML para confirmar tipo de transacción
        purchase = _parse_form4_purchase(entry.get("accession"), cik)
        if purchase is None:
            continue

        seen_tickers.add(ticker)
        insider = purchase.get("insider_name", "Directivo")
        position = purchase.get("position", "")
        shares = purchase.get("shares")
        value = purchase.get("value_usd")

        title = f"Compra insider: {insider}"
        if position:
            title += f" ({position})"

        desc_parts = []
        if shares:
            desc_parts.append(f"{shares:,} acciones")
        if value:
            desc_parts.append(f"${value:,}")

        source_key = insider[:30].replace(" ", "_")
        results.append(CatalystData(
            catalyst_type="insider_buy",
            symbol=ticker,
            title=title[:255],
            source_id=f"insider_{ticker}_{filing_date.isoformat()}_{source_key}",
            description=", ".join(desc_parts) if desc_parts else None,
            extra={
                "filing_date": filing_date.isoformat(),
                "accession": entry.get("accession"),
                "insider": insider,
                "position": position,
                "shares": shares,
                "value_usd": value,
            },
        ))

    logger.info("Insider buys detectados: %d de %d tickers en universo", len(results), len(symbol_set))
    return results


def _fetch_ticker_cik_map(symbol_set: set[str]) -> dict[str, str]:
    """Descarga el mapa ticker→CIK de SEC EDGAR y filtra al universo dado."""
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _EDGAR_USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            import json
            data = json.loads(resp.read())
        return {
            item["ticker"].upper(): str(item["cik_str"]).zfill(10)
            for item in data.values()
            if item["ticker"].upper() in symbol_set
        }
    except Exception:
        logger.debug("Error descargando company_tickers.json", exc_info=True)
        return {}


def _fetch_recent_form4_entries(count: int = 100) -> list[dict]:
    """Descarga el RSS de Form 4 recientes de EDGAR y devuelve lista de entries."""
    url = (
        f"https://www.sec.gov/cgi-bin/browse-edgar"
        f"?action=getcurrent&type=4&dateb=&owner=include"
        f"&count={count}&search_text=&output=atom"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _EDGAR_USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read()

        root = ET.fromstring(content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = []

        for entry in root.findall("atom:entry", ns):
            link_el = entry.find("atom:link", ns)
            href = link_el.attrib.get("href", "") if link_el is not None else ""

            # href: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193&type=4&...
            cik = ""
            if "CIK=" in href:
                cik = href.split("CIK=")[1].split("&")[0].zfill(10)

            # Filing date from <updated>
            updated_el = entry.find("atom:updated", ns)
            date_str = updated_el.text[:10] if updated_el is not None and updated_el.text else None

            # Accession number from content or title — fallback: parse from link
            accession = ""
            content_el = entry.find("atom:content", ns)
            if content_el is not None and content_el.text:
                import re
                m = re.search(r"(\d{18})", content_el.text.replace("-", ""))
                if m:
                    raw = m.group(1)
                    accession = f"{raw[:10]}-{raw[10:12]}-{raw[12:]}"

            entries.append({"cik": cik, "date": date_str, "accession": accession})

        return entries
    except Exception:
        logger.debug("Error descargando Form 4 RSS", exc_info=True)
        return []


def _parse_form4_purchase(accession: str, cik: str) -> dict | None:
    """Descarga y parsea el XML de un Form 4. Devuelve info de la compra o None si es venta."""
    if not accession or not cik:
        return None

    acc_nodash = accession.replace("-", "")
    # Formato: https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{accession}.txt
    # Primero intentar el índice para encontrar el XML
    index_url = (
        f"https://www.sec.gov/cgi-bin/browse-edgar"
        f"?action=getcompany&CIK={cik}&type=4&dateb=&owner=include&count=1"
        f"&search_text=&output=atom"
    )

    # Construir URL directa al filing XML
    xml_url = (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{acc_nodash}/{accession}.xml"
    )

    try:
        req = urllib.request.Request(xml_url, headers={"User-Agent": _EDGAR_USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()

        root = ET.fromstring(content)

        # Verificar que hay transacciones de tipo P (Purchase)
        has_purchase = False
        shares = None
        price = None

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
