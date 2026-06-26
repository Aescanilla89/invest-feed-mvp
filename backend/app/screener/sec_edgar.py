"""Cliente SEC EDGAR (data.sec.gov) -- gratuito, sin API key, fuente
primaria oficial. Se usa para los criterios CAN SLIM S, C y A.

- Criterio S (supply/demand): histórico de shares outstanding via companyfacts.
  Si las acciones en circulación bajan trimestre a trimestre → señal de buyback.
- Criterios C y A (EPS growth): EPS diluido de 10-Q/10-K via companyfacts XBRL
  (us-gaap/EarningsPerShareDiluted). Misma fuente, misma llamada, sin Yahoo.
- Criterio I (institutional sponsorship): NO implementado. Requiere agregar
  Form 13F de todos los filers (~GB de datos bulk), se deja para fase 2.

Rate limit de SEC: ~10 req/seg razonable; identificar con User-Agent de contacto.
"""
from __future__ import annotations

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


class SECEdgarError(RuntimeError):
    pass


@dataclass
class EpsSeriesData:
    quarterly: list[float] = field(default_factory=list)  # ascendente, periodos 10-Q (~90 días)
    annual: list[float] = field(default_factory=list)     # ascendente, periodos 10-K (~365 días)


@dataclass
class SupplySignal:
    is_buyback_trend: bool | None  # None = sin datos suficientes
    shares_outstanding_change_pct: float | None
    quarters_compared: int


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


def get_supply_signal(symbol: str, quarters_to_compare: int = 4) -> SupplySignal:
    """Compara shares outstanding actuales vs. hace `quarters_to_compare`
    trimestres. Una reducción sostenida es señal de buyback (criterio S)."""
    cik = get_cik(symbol)
    if cik is None:
        return SupplySignal(None, None, 0)

    resp = requests.get(COMPANYFACTS_URL.format(cik=cik), headers=_HEADERS, timeout=15)
    if resp.status_code == 404:
        return SupplySignal(None, None, 0)
    resp.raise_for_status()
    facts = resp.json()

    series = None
    for tag in SHARES_OUTSTANDING_TAGS:
        node = facts.get("facts", {}).get("dei", {}).get(tag) or facts.get("facts", {}).get("us-gaap", {}).get(tag)
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
        is_buyback_trend=change_pct < -0.01,  # >1% de reducción acumulada
        shares_outstanding_change_pct=change_pct,
        quarters_compared=quarters_to_compare,
    )


_EPS_TAGS = ("EarningsPerShareDiluted", "EarningsPerShareBasic")


def get_eps_series(symbol: str) -> EpsSeriesData:
    """EPS diluido de 10-Q (trimestral) y 10-K (anual) vía companyfacts XBRL.
    Reutiliza la misma URL que get_supply_signal para no añadir dependencias nuevas.
    Devuelve listas vacías si no hay datos (criterios C/A quedan como None en CAN SLIM)."""
    cik = get_cik(symbol)
    if cik is None:
        return EpsSeriesData()

    try:
        resp = requests.get(COMPANYFACTS_URL.format(cik=cik), headers=_HEADERS, timeout=15)
        if resp.status_code == 404:
            return EpsSeriesData()
        resp.raise_for_status()
        facts = resp.json()
    except Exception:
        return EpsSeriesData()

    return _extract_eps_from_facts(facts)


def _extract_eps_from_facts(facts: dict) -> EpsSeriesData:
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

    # Ordenar por filed date ascendente: los restatements (filed más tarde)
    # sobreescriben el valor original del mismo periodo.
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


def get_institutional_sponsorship(symbol: str) -> None:
    """Placeholder explícito: ver docstring del módulo. Devuelve siempre
    None -- no fingir un valor que no se puede calcular con la infra
    actual del MVP."""
    return None
