"""Detección de catalizadores de inversión.

Fuentes:
- Earnings: yfinance ticker.earnings_dates (Q2 season ~11 julio)
- Insider buying: SEC EDGAR Form 4 por ticker (Railway-compatible; Yahoo Finance no)
- FED rate decisions: Polymarket gamma API (mercado de predicción, macro/market-wide)
- Geopolítica: Polymarket gamma API (feed de mercados activos, macro/market-wide)
- Datos macro EEUU: FRED releases/dates (CPI, NFP, PIB) — requiere FRED_API_KEY

Estrategia insider:
1. Obtiene CIKs de nuestros tickers via EDGAR company_tickers.json
2. Para cada CIK, consulta submissions.json → busca Form 4 recientes
3. Descarga XML del Form 4 → verifica transacción tipo P (Purchase)

Los detectores macro (FED, geopolítica, datos macro) no dependen de nuestro
universo de tickers: producen catalizadores con ticker_id=None (soportado
nativamente por el modelo ORM `Catalyst`).
"""
from __future__ import annotations

import json
import logging
import math
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, timedelta

logger = logging.getLogger("catalysts")

_EDGAR_USER_AGENT = "invest-feed-mvp research@invest-feed.com"
_EDGAR_DELAY = 0.12  # 10 req/s max según EDGAR ToS


@dataclass
class CatalystData:
    catalyst_type: str  # "earnings" | "insider_buy" | "fed_meeting" | "geopolitical" | "macro_data"
    title: str
    source_id: str
    symbol: str | None = None  # None para catalizadores macro/market-wide
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
            purchase = _parse_form4_purchase(filing["accession"], cik, filing.get("primary_doc", ""))
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
        primary_docs = recent.get("primaryDocument", [])

        results = []
        for form, filing_date_str, accession, primary_doc in zip(forms, dates, accessions, primary_docs):
            if form != "4":
                continue
            d = _to_date(filing_date_str)
            if d is None or d < cutoff:
                break  # filings están ordenados por fecha desc, stop early
            results.append({
                "date": filing_date_str,
                "accession": accession,
                "primary_doc": primary_doc,
            })

        return results

    except Exception:
        logger.debug("Error obteniendo submissions de CIK %s", cik, exc_info=True)
        return []


def _parse_form4_purchase(accession: str, cik: str, primary_doc: str = "") -> dict | None:
    """Descarga y parsea un Form 4 de EDGAR. Devuelve info de la compra o None.

    Estrategia:
    1. Intenta descargar el archivo con el índice de la presentación
    2. Busca el primaryDocument o un .htm en el índice
    3. Parsea el contenido buscando transactionCode == 'P' (open-market purchase)
    """
    if not accession or not cik:
        return None

    acc_nodash = accession.replace("-", "")
    cik_int = int(cik)

    # Obtener el índice del filing para encontrar el documento principal
    doc_name = _find_primary_htm_from_index(cik_int, acc_nodash, accession)
    if not doc_name and primary_doc:
        # Usar el primaryDocument registrado en submissions.json
        # Si es xslF345X06/... usarlo directamente
        doc_name = primary_doc

    if not doc_name:
        logger.debug("No se encontró documento del Form 4 %s", accession)
        return None

    time.sleep(_EDGAR_DELAY)
    doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{doc_name}"

    try:
        req = urllib.request.Request(doc_url, headers={"User-Agent": _EDGAR_USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="replace")

        return _extract_purchase_from_form4_content(content, accession)

    except Exception:
        logger.debug("Error descargando Form 4 %s", accession, exc_info=True)
        return None


def _find_primary_htm_from_index(cik_int: int, acc_nodash: str, accession: str) -> str | None:
    """Consulta el filing index y devuelve el .htm principal del Form 4."""
    index_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
        f"{acc_nodash}/{accession}-index.json"
    )
    try:
        req = urllib.request.Request(index_url, headers={"User-Agent": _EDGAR_USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        time.sleep(_EDGAR_DELAY)
        items = data.get("directory", {}).get("item", [])
        # Preferir .htm sobre .xml (iXBRL moderno)
        for item in items:
            name = item.get("name", "")
            if name.endswith(".htm") and not name.startswith("R"):
                return name
        for item in items:
            if item.get("name", "").endswith(".xml"):
                return item["name"]
        return None
    except Exception:
        logger.debug("Error obteniendo filing index %s", accession, exc_info=True)
        return None


def _extract_purchase_from_form4_content(content: str, accession: str) -> dict | None:
    """Extrae datos de compra de un Form 4 (HTML o XML).

    - Intenta parsear como XML estricto (filings pre-2020)
    - Si falla, busca patrones en el texto (iXBRL moderno)
    """
    import re

    # Intento 1: XML estricto (formato clásico EDGAR Form 4)
    try:
        root = ET.fromstring(content.encode("utf-8"))
        return _parse_ownership_xml(root)
    except ET.ParseError:
        pass

    # Intento 2: Buscar en HTML/iXBRL con regex
    # transactionCode aparece cerca de la tabla de transacciones
    # Patrones comunes: <td>P</td>, >P<, value="P", etc.
    codes_found = re.findall(
        r"(?:transactionCode|TransactionCode)[^>]*>([A-Z])<",
        content,
    )
    if not codes_found:
        # iXBRL: <ix:nonFraction ...>P</ix:nonFraction>
        codes_found = re.findall(r"TransactionCode[^>]*>\s*([A-Z])\s*<", content)

    if "P" not in codes_found:
        return None  # no hay open-market purchase

    # Extraer shares y precio (best-effort)
    shares = None
    price = None

    shares_match = re.search(
        r"transactionShares[^>]*>\s*<value>\s*([\d,.]+)",
        content,
    )
    if shares_match:
        shares = _safe_int(shares_match.group(1).replace(",", ""))

    price_match = re.search(
        r"transactionPricePerShare[^>]*>\s*<value>\s*([\d,.]+)",
        content,
    )
    if price_match:
        price = _safe_float(price_match.group(1).replace(",", ""))

    # Extraer nombre del insider
    name_match = re.search(r"rptOwnerName[^>]*>\s*([^<]{3,80})\s*<", content)
    insider_name = name_match.group(1).strip() if name_match else "Directivo"

    pos_match = re.search(r"officerTitle[^>]*>\s*([^<]{2,60})\s*<", content)
    position = pos_match.group(1).strip() if pos_match else ""

    value_usd = int(shares * price) if shares and price else None

    return {
        "insider_name": insider_name,
        "position": position,
        "shares": shares,
        "value_usd": value_usd,
    }


def _parse_ownership_xml(root: ET.Element) -> dict | None:
    """Parsea un ownershipDocument XML clásico de EDGAR Form 4."""
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


# ---------------------------------------------------------------------------
# FED rate decisions — Polymarket gamma API (macro, ticker_id=None)
# ---------------------------------------------------------------------------

_POLYMARKET_API_URL = "https://gamma-api.polymarket.com/markets"
_POLYMARKET_USER_AGENT = "invest-feed-mvp research@invest-feed.com"

# Mismas listas de keywords que el bot de Polymarket (inferir_categoria)
_FED_KEYWORDS = ("rate", "fomc", "decision", "cut", "hike")
_GEOPOLITICAL_KEYWORDS = ("war", "conflict", "attack", "ceasefire", "treaty", "sanctions", "invasion")


def detect_fed_meeting() -> list[CatalystData]:
    """Detecta el mercado de Polymarket sobre la próxima decisión de tipos de la FED.

    Filtra mercados cuya pregunta contiene "fed" + (rate/fomc/decision/cut/hike)
    y escoge el de mayor volumen (la reunión FOMC más relevante/próxima).
    """
    markets = _fetch_polymarket_markets()
    if not markets:
        logger.warning("No se pudo obtener mercados de Polymarket para FED")
        return []

    candidates = []
    for m in markets:
        question = (m.get("question") or "").strip().lower()
        if not question or "fed" not in question:
            continue
        if any(kw in question for kw in _FED_KEYWORDS):
            candidates.append(m)

    if not candidates:
        logger.info("Sin mercados FED relevantes en Polymarket")
        return []

    best = max(candidates, key=lambda m: _safe_float(m.get("volume")) or 0.0)

    try:
        outcomes = _parse_polymarket_outcomes(best)
        if not outcomes:
            return []

        outcomes.sort(key=lambda pair: pair[1], reverse=True)
        description = " · ".join(f"{name}: {price * 100:.0f}%" for name, price in outcomes)

        question = (best.get("question") or "").strip()
        end_date = best.get("endDate", "") or ""
        market_key = best.get("id") or best.get("slug") or question[:40]
        slug = best.get("slug", "")

        return [CatalystData(
            catalyst_type="fed_meeting",
            title=f"Reunión FED: {question}"[:255],
            source_id=f"fed_meeting_{market_key}_{end_date[:10]}",
            description=description[:1000] if description else None,
            extra={
                "question": question,
                "end_date": end_date,
                "outcomes": [name for name, _ in outcomes],
                "prices": [price for _, price in outcomes],
                "volume": _safe_float(best.get("volume")),
                "url": f"https://polymarket.com/event/{slug}" if slug else None,
            },
        )]

    except Exception:
        logger.debug("Error procesando mercado FED de Polymarket", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Riesgo geopolítico — Polymarket gamma API (feed, macro, ticker_id=None)
# ---------------------------------------------------------------------------

def detect_geopolitical_events(top_n: int = 5) -> list[CatalystData]:
    """Detecta los mercados geopolíticos más relevantes de Polymarket (feed continuo).

    A diferencia de `detect_fed_meeting`, no busca un único evento sino los
    `top_n` mercados por volumen relacionados con guerra/conflicto/sanciones.
    """
    markets = _fetch_polymarket_markets()
    if not markets:
        logger.warning("No se pudo obtener mercados de Polymarket para geopolítica")
        return []

    candidates = [
        m for m in markets
        if (m.get("question") or "").strip()
        and any(kw in m["question"].lower() for kw in _GEOPOLITICAL_KEYWORDS)
    ]
    candidates.sort(key=lambda m: _safe_float(m.get("volume")) or 0.0, reverse=True)

    results: list[CatalystData] = []
    for m in candidates[:top_n]:
        try:
            outcomes = _parse_polymarket_outcomes(m)
            if not outcomes:
                continue
            outcomes.sort(key=lambda pair: pair[1], reverse=True)
            leader_name, leader_price = outcomes[0]

            question = m["question"].strip()
            end_date = m.get("endDate", "") or ""
            market_key = m.get("id") or m.get("slug") or question[:40]
            slug = m.get("slug", "")

            results.append(CatalystData(
                catalyst_type="geopolitical",
                title=question[:255],
                source_id=f"geopolitical_{market_key}",
                description=f"{leader_name}: {leader_price * 100:.0f}%",
                extra={
                    "question": question,
                    "end_date": end_date,
                    "outcomes": [name for name, _ in outcomes],
                    "prices": [price for _, price in outcomes],
                    "volume": _safe_float(m.get("volume")),
                    "url": f"https://polymarket.com/event/{slug}" if slug else None,
                },
            ))
        except Exception:
            logger.debug("Error procesando mercado geopolítico de Polymarket", exc_info=True)

    logger.info("Mercados geopolíticos detectados: %d", len(results))
    return results


def _fetch_polymarket_markets(limit: int = 100) -> list[dict]:
    """Descarga mercados activos de Polymarket (API pública gamma, sin auth)."""
    params = {
        "active": "true",
        "closed": "false",
        "limit": str(limit),
        "offset": "0",
        "order": "volume",
        "ascending": "false",
    }
    url = f"{_POLYMARKET_API_URL}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _POLYMARKET_USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data if isinstance(data, list) else []
    except Exception:
        logger.debug("Error descargando mercados de Polymarket", exc_info=True)
        return []


def _parse_polymarket_outcomes(market: dict) -> list[tuple[str, float]] | None:
    """Extrae pares (nombre, precio 0-1 ~ probabilidad) de un mercado Polymarket.

    `outcomes` y `outcomePrices` vienen codificados como JSON-string. Devuelve
    None si el mercado no tiene datos de outcomes válidos.
    """
    try:
        outcomes_raw = market.get("outcomes", "[]")
        prices_raw = market.get("outcomePrices", "[]")
        outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
        prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw

        if not outcomes or not prices or len(outcomes) != len(prices):
            return None

        pairs = []
        for name, price_raw in zip(outcomes, prices):
            price = _safe_float(price_raw)
            if price is None:
                continue
            pairs.append((str(name), price))

        return pairs or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Próximos datos macro EEUU — FRED releases/dates (macro, ticker_id=None)
# ---------------------------------------------------------------------------

_FRED_API_URL = "https://api.stlouisfed.org/fred/releases/dates"

# release_id conocidos de FRED (St. Louis Fed). GDP verificado manualmente:
# https://fred.stlouisfed.org/release?rid=53 → "Gross Domestic Product" (BEA).
_FRED_RELEASES = {
    10: "CPI (inflación)",
    50: "Empleo no agrícola (NFP)",
    53: "PIB (GDP)",
}


def detect_macro_data_releases(days_ahead: int = 30) -> list[CatalystData]:
    """Detecta próximas fechas de publicación de datos macro EEUU via FRED.

    Requiere la variable de entorno FRED_API_KEY (St. Louis Fed, gratuita).
    Si no está configurada, se omite el detector sin fallar el job (mismo
    estilo defensivo que el `except ImportError` de detect_earnings).
    """
    from app.core.config import settings

    api_key = settings.fred_api_key
    if not api_key:
        logger.warning("FRED_API_KEY no configurada, skipping macro_data releases")
        return []

    today = date.today()
    horizon = today + timedelta(days=days_ahead)
    results: list[CatalystData] = []

    for release_id, label in _FRED_RELEASES.items():
        try:
            next_date = _fetch_next_fred_release_date(release_id, api_key, today, horizon)
            if next_date is None:
                continue

            results.append(CatalystData(
                catalyst_type="macro_data",
                title=f"Próximo dato: {label}",
                source_id=f"macro_data_{release_id}_{next_date.isoformat()}",
                description=f"Publicación programada: {next_date.isoformat()}",
                extra={
                    "release_id": release_id,
                    "release_name": label,
                    "date": next_date.isoformat(),
                },
            ))
        except Exception:
            logger.debug("Error obteniendo fechas FRED release_id=%s", release_id, exc_info=True)

    logger.info("Datos macro detectados: %d", len(results))
    return results


def _fetch_next_fred_release_date(
    release_id: int, api_key: str, today: date, horizon: date
) -> date | None:
    """Consulta FRED releases/dates y devuelve la próxima fecha dentro del horizonte."""
    params = {
        "release_id": str(release_id),
        "api_key": api_key,
        "file_type": "json",
        "include_release_dates_with_no_data": "true",
        "sort_order": "asc",
    }
    url = f"{_FRED_API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": _EDGAR_USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    for entry in data.get("release_dates", []):
        d = _to_date(entry.get("date"))
        if d is None:
            continue
        if today <= d <= horizon:
            return d
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
