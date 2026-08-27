"""Cliente SEC EDGAR (data.sec.gov) -- gratuito, sin API key, fuente
primaria oficial. Se usa para los criterios CAN SLIM S, C y A.

- Criterio S (supply/demand): histórico de shares outstanding via companyfacts.
- Criterios C y A (EPS growth): EPS diluido de 10-Q/10-K via companyfacts XBRL.
- Criterio I (institutional sponsorship): ver sec_13f.py (Form 13F-HR, top-30 instituciones).

IMPORTANTE: usar get_edgar_data() en lugar de get_supply_signal() + get_eps_series()
por separado — hace una sola petición HTTP a companyfacts por ticker en vez de dos.

Rate limit de SEC: ~10 req/seg razonable; identificar con User-Agent de contacto.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date

import requests

_HEADERS = {"User-Agent": "invest-feed-mvp/0.1 (contacto: escanillaalberto@gmail.com)"}
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

SHARES_OUTSTANDING_TAGS = (
    "EntityCommonStockSharesOutstanding",
    "CommonStockSharesOutstanding",
)
_EPS_TAGS = ("EarningsPerShareDiluted", "EarningsPerShareBasic")

SEC_REQUEST_DELAY = 0.12  # ~8 req/s, dentro del límite de SEC


class SECEdgarError(RuntimeError):
    pass


@dataclass
class SupplySignal:
    is_buyback_trend: bool | None
    shares_outstanding_change_pct: float | None
    quarters_compared: int


@dataclass
class EpsSeriesData:
    quarterly: list[float] = field(default_factory=list)
    annual: list[float] = field(default_factory=list)


@dataclass
class QualityMetrics:
    """Métricas de calidad para el criterio Berkshire: márgenes, OCF/NI, ROE.
    None significa que el dato no está disponible en EDGAR para este ticker."""
    gross_margin: float | None       # GrossProfit / Revenues (3y avg)
    net_margin: float | None         # NetIncomeLoss / Revenues (3y avg)
    ocf_to_ni: float | None          # OperatingCF / NetIncomeLoss (3y avg)
    roe: float | None                # NetIncomeLoss / StockholdersEquity (latest)


_cik_map_cache: dict[str, int] | None = None


def _load_cik_map() -> dict[str, int]:
    global _cik_map_cache
    if _cik_map_cache is not None:
        return _cik_map_cache
    resp = requests.get(TICKER_MAP_URL, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    _cik_map_cache = {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}
    return _cik_map_cache


def get_cik(symbol: str) -> int | None:
    return _load_cik_map().get(symbol.upper())


def _fetch_companyfacts(cik: int) -> dict | None:
    time.sleep(SEC_REQUEST_DELAY)
    resp = requests.get(COMPANYFACTS_URL.format(cik=cik), headers=_HEADERS, timeout=15)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


_RELEVANT_TAGS = {
    "dei": SHARES_OUTSTANDING_TAGS,
    "us-gaap": (
        *SHARES_OUTSTANDING_TAGS,
        *_EPS_TAGS,
        "GrossProfit",
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "NetIncomeLoss",
        "NetCashProvidedByUsedInOperatingActivities",
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
}


def _trim_companyfacts(facts: dict) -> dict:
    """El companyfacts crudo de EDGAR trae CADA concepto XBRL que la empresa ha
    reportado jamás (a menudo cientos de tags) -- solo usamos ~12. Un backtest
    guarda esta estructura en memoria simultáneamente para miles de tickers
    durante toda la corrida, así que quedarnos con todo el JSON crudo agota la
    RAM del runner con universos grandes (visto en producción: "the hosted
    runner lost communication with the server... starves it for CPU/Memory").
    Se descarta todo lo que no sea uno de los tags que de verdad se lee."""
    raw = facts.get("facts", {})
    trimmed = {
        taxonomy: {tag: raw[taxonomy][tag] for tag in tags if tag in raw.get(taxonomy, {})}
        for taxonomy, tags in _RELEVANT_TAGS.items()
    }
    return {"facts": trimmed}


def get_company_facts(symbol: str) -> dict | None:
    """Descarga el companyfacts de un ticker (1 sola petición HTTP), recortado
    a los ~12 tags XBRL que realmente se usan.
    Pensado para un backtest histórico: se descarga UNA vez por ticker y se
    reutiliza con get_edgar_data_from_facts(facts, as_of=...) para muchas
    fechas distintas sin repetir la petición a EDGAR."""
    cik = get_cik(symbol)
    if cik is None:
        return None
    try:
        raw = _fetch_companyfacts(cik)
    except Exception:
        return None
    if raw is None:
        return None
    return _trim_companyfacts(raw)


def get_edgar_data(
    symbol: str, quarters_to_compare: int = 4, as_of: date | None = None,
) -> tuple[SupplySignal, EpsSeriesData, QualityMetrics]:
    """Una sola petición a companyfacts extrae S (supply), C/A (EPS) y métricas de calidad.
    Usar siempre esta función en lugar de get_supply_signal + get_eps_series por separado.

    `as_of`: si se pasa, solo se usan filings con fecha de publicación (`filed`)
    <= as_of -- para reconstruir "qué sabíamos en esa fecha" en un backtest
    histórico, sin look-ahead bias. None (default) usa todo lo disponible hoy,
    igual que antes de este parámetro (comportamiento de producción sin cambios)."""
    cik = get_cik(symbol)
    if cik is None:
        return SupplySignal(None, None, 0), EpsSeriesData(), QualityMetrics(None, None, None, None)

    try:
        facts = _fetch_companyfacts(cik)
    except Exception:
        return SupplySignal(None, None, 0), EpsSeriesData(), QualityMetrics(None, None, None, None)

    if facts is None:
        return SupplySignal(None, None, 0), EpsSeriesData(), QualityMetrics(None, None, None, None)

    return get_edgar_data_from_facts(facts, quarters_to_compare, as_of)


def get_edgar_data_from_facts(
    facts: dict, quarters_to_compare: int = 4, as_of: date | None = None,
) -> tuple[SupplySignal, EpsSeriesData, QualityMetrics]:
    """Igual que get_edgar_data pero reutilizando un companyfacts ya descargado --
    permite a un backtest histórico descargar cada ticker UNA vez y reevaluar
    muchas fechas `as_of` distintas sin repetir la petición HTTP a EDGAR."""
    return (
        _extract_supply(facts, quarters_to_compare, as_of),
        _extract_eps(facts, as_of),
        _extract_quality(facts, as_of),
    )


def _filed_ok(item: dict, as_of: date | None) -> bool:
    if as_of is None:
        return True
    filed = item.get("filed")
    if not filed:
        return False
    try:
        return date.fromisoformat(filed) <= as_of
    except ValueError:
        return False


def _extract_supply(facts: dict, quarters_to_compare: int, as_of: date | None = None) -> SupplySignal:
    series = None
    for tag in SHARES_OUTSTANDING_TAGS:
        node = (
            facts.get("facts", {}).get("dei", {}).get(tag)
            or facts.get("facts", {}).get("us-gaap", {}).get(tag)
        )
        if node:
            units = [u for u in node.get("units", {}).get("shares", []) if _filed_ok(u, as_of)]
            if units:
                series = sorted(units, key=lambda u: u.get("end", ""))
                break

    if not series or len(series) <= quarters_to_compare:
        return SupplySignal(None, None, 0)

    current = series[-1]["val"]
    prior = series[-1 - quarters_to_compare]["val"]
    if not prior:
        return SupplySignal(None, None, 0)

    change_pct = (current - prior) / prior
    return SupplySignal(
        is_buyback_trend=change_pct < -0.01,
        shares_outstanding_change_pct=change_pct,
        quarters_compared=quarters_to_compare,
    )


def _extract_eps(facts: dict, as_of: date | None = None) -> EpsSeriesData:
    units: list[dict] = []
    for tag in _EPS_TAGS:
        node = facts.get("facts", {}).get("us-gaap", {}).get(tag)
        if node:
            candidate = node.get("units", {}).get("USD/shares", [])
            if candidate:
                units = candidate
                break

    if not units:
        return EpsSeriesData()

    sorted_units = sorted((u for u in units if _filed_ok(u, as_of)), key=lambda u: u.get("filed", ""))
    quarterly: dict[date, float] = {}
    annual: dict[date, float] = {}

    for item in sorted_units:
        start_str = item.get("start")
        end_str = item.get("end")
        val = item.get("val")
        form = item.get("form", "")

        if not start_str or not end_str or val is None:
            continue
        try:
            start_date = date.fromisoformat(start_str)
            end_date = date.fromisoformat(end_str)
        except ValueError:
            continue

        period_days = (end_date - start_date).days
        if form == "10-Q" and 60 <= period_days <= 120:
            quarterly[end_date] = float(val)
        elif form == "10-K" and 330 <= period_days <= 400:
            annual[end_date] = float(val)

    return EpsSeriesData(
        quarterly=[v for _, v in sorted(quarterly.items())],
        annual=[v for _, v in sorted(annual.items())],
    )


def _annual_series(facts: dict, *tags: str, unit: str = "USD", as_of: date | None = None) -> list[float]:
    """Extrae la serie anual (10-K) de un concepto XBRL. Prueba tags en orden."""
    for tag in tags:
        node = facts.get("facts", {}).get("us-gaap", {}).get(tag)
        if not node:
            continue
        items = node.get("units", {}).get(unit, [])
        annual: dict[str, float] = {}
        for item in items:
            if item.get("form") != "10-K" or not _filed_ok(item, as_of):
                continue
            start, end = item.get("start"), item.get("end")
            val = item.get("val")
            if not start or not end or val is None:
                continue
            try:
                days = (date.fromisoformat(end) - date.fromisoformat(start)).days
            except ValueError:
                continue
            if 330 <= days <= 400:
                annual[end] = float(val)
        if annual:
            return [v for _, v in sorted(annual.items())]
    return []


def _extract_quality(facts: dict, as_of: date | None = None) -> QualityMetrics:
    """Extrae métricas de calidad del mismo companyfacts que ya descargamos."""
    gross_profits = _annual_series(facts, "GrossProfit", as_of=as_of)
    revenues = _annual_series(
        facts,
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        as_of=as_of,
    )
    net_incomes = _annual_series(facts, "NetIncomeLoss", as_of=as_of)
    ocfs = _annual_series(facts, "NetCashProvidedByUsedInOperatingActivities", as_of=as_of)
    equities = _annual_series(facts, "StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", as_of=as_of)

    def _avg_ratio(numerators: list[float], denominators: list[float], n_years: int = 3) -> float | None:
        pairs = [
            (n, d)
            for n, d in zip(numerators[-n_years:], denominators[-n_years:])
            if d and d != 0
        ]
        if not pairs:
            return None
        ratios = [n / d for n, d in pairs]
        return sum(ratios) / len(ratios)

    gross_margin = _avg_ratio(gross_profits, revenues)
    net_margin = _avg_ratio(net_incomes, revenues)
    ocf_to_ni = _avg_ratio(ocfs, net_incomes) if net_incomes and all(v > 0 for v in net_incomes[-3:]) else None
    roe = (net_incomes[-1] / equities[-1]) if net_incomes and equities and equities[-1] != 0 else None

    return QualityMetrics(
        gross_margin=gross_margin,
        net_margin=net_margin,
        ocf_to_ni=ocf_to_ni,
        roe=roe,
    )


# Wrappers de compatibilidad (llaman a get_edgar_data internamente)
def get_supply_signal(symbol: str, quarters_to_compare: int = 4) -> SupplySignal:
    supply, _, _ = get_edgar_data(symbol, quarters_to_compare)
    return supply


def get_eps_series(symbol: str) -> EpsSeriesData:
    _, eps, _ = get_edgar_data(symbol)
    return eps
