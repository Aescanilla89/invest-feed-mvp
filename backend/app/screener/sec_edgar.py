"""Cliente SEC EDGAR (data.sec.gov) -- gratuito, sin API key, fuente
primaria oficial. Se usa para los criterios CAN SLIM S, C y A.

- Criterio S (supply/demand): histórico de shares outstanding via companyfacts.
- Criterios C y A (EPS growth): EPS diluido de 10-Q/10-K via companyfacts XBRL.
- Criterio I (institutional sponsorship): NO implementado (Form 13F bulk, fase 2).

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


def get_edgar_data(symbol: str, quarters_to_compare: int = 4) -> tuple[SupplySignal, EpsSeriesData]:
    """Una sola petición a companyfacts extrae criterio S (supply) y C/A (EPS).
    Usar siempre esta función en lugar de get_supply_signal + get_eps_series por separado."""
    cik = get_cik(symbol)
    if cik is None:
        return SupplySignal(None, None, 0), EpsSeriesData()

    try:
        facts = _fetch_companyfacts(cik)
    except Exception:
        return SupplySignal(None, None, 0), EpsSeriesData()

    if facts is None:
        return SupplySignal(None, None, 0), EpsSeriesData()

    return _extract_supply(facts, quarters_to_compare), _extract_eps(facts)


def _extract_supply(facts: dict, quarters_to_compare: int) -> SupplySignal:
    series = None
    for tag in SHARES_OUTSTANDING_TAGS:
        node = (
            facts.get("facts", {}).get("dei", {}).get(tag)
            or facts.get("facts", {}).get("us-gaap", {}).get(tag)
        )
        if node:
            units = node.get("units", {}).get("shares", [])
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


def _extract_eps(facts: dict) -> EpsSeriesData:
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

    sorted_units = sorted(units, key=lambda u: u.get("filed", ""))
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


# Wrappers de compatibilidad (llaman a get_edgar_data internamente)
def get_supply_signal(symbol: str, quarters_to_compare: int = 4) -> SupplySignal:
    supply, _ = get_edgar_data(symbol, quarters_to_compare)
    return supply


def get_eps_series(symbol: str) -> EpsSeriesData:
    _, eps = get_edgar_data(symbol)
    return eps


def get_institutional_sponsorship(symbol: str) -> None:
    return None
