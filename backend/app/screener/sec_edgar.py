"""Cliente SEC EDGAR (data.sec.gov) -- gratuito, sin API key, fuente
primaria oficial. Se usa para complementar yfinance en los criterios
CAN SLIM que peor cubre (S e I).

IMPORTANTE -- corrección respecto a lo planteado inicialmente:
- Criterio S (supply/demand): SÍ se implementa aquí, vía el histórico de
  `shares outstanding` del endpoint companyfacts. Si las acciones en
  circulación bajan trimestre a trimestre, es señal de buyback (supply
  favorable). Esto es directo y fiable.
- Criterio I (institutional sponsorship): NO se implementa en este MVP.
  Para calcularlo de verdad (cuántas instituciones tienen el valor y si
  ese número crece) hace falta agregar los Form 13F de todos los
  filers que reportan ese CUSIP, y eso solo está disponible como dataset
  bulk trimestral (varios GB, ver sec.gov/data-research/sec-markets-data
  /form-13f-data-sets) -- no como endpoint por ticker. Se deja para fase 2.
  get_institutional_sponsorship() existe como contrato/placeholder y
  devuelve siempre None con el motivo, para que canslim.py lo marque
  explícitamente como no verificable en lugar de omitirlo en silencio.

Rate limit de SEC: sin límite oficial publicado, pero piden identificar
al cliente con un User-Agent de contacto real y no abusar (~10 req/seg
es razonable). No usar en paralelo masivo sin pausas.
"""
from __future__ import annotations

from dataclasses import dataclass

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


def get_institutional_sponsorship(symbol: str) -> None:
    """Placeholder explícito: ver docstring del módulo. Devuelve siempre
    None -- no fingir un valor que no se puede calcular con la infra
    actual del MVP."""
    return None
