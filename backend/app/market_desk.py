"""Deterministic, source-attributed US market regime briefing.

The score describes prevailing conditions; it is not a return forecast.
Raw series are fetched from FRED (official St Louis Fed API) and, where
configured, Alpaca's market data API. Missing series remain missing.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
TTL_SECONDS = 1800
_cache: dict[str, Any] = {"at": 0.0, "data": None}
_lock = threading.Lock()


class Indicator(BaseModel):
    key: str
    label: str
    value: float | None
    previous: float | None = None
    change: float | None = None
    change_1w: float | None = None
    change_1m: float | None = None
    as_of: str | None = None
    frequency: str
    freshness: str = "missing"
    source: str
    source_url: str | None = None
    reference_source_url: str | None = None
    interpretation: str
    signal: str = "unavailable"
    score: float | None = None
    weight: float = 0


class Desk(BaseModel):
    score: float | None = None
    status: str
    summary: str
    indicators: list[Indicator] = Field(default_factory=list)
    coverage: int = 0


class MarketRegime(BaseModel):
    score: float | None
    label: str
    direction: str
    status: str
    components: dict[str, float | None]
    method: str


class MacroRegime(BaseModel):
    regime: str
    growth: str
    inflation: str
    labour: str
    confidence: int
    indicators: list[Indicator]
    method: str


class CrossAssetSignal(BaseModel):
    level: str
    title: str
    detail: str


class MarketChange(BaseModel):
    label: str
    change: float
    unit: str
    horizon: str
    as_of: str | None
    source: str


class WatchEvent(BaseModel):
    date: str
    title: str
    source: str
    consensus: float | None = None


class MarketDeskResponse(BaseModel):
    market_regime: MarketRegime
    liquidity: Desk
    stress: Desk
    macro: MacroRegime
    market_internals: Desk
    cross_asset_signals: list[CrossAssetSignal]
    desk_call: list[str]
    what_changed: list[MarketChange]
    watch_next: list[WatchEvent]
    confidence: int
    coverage: dict[str, int]
    sources: list[str]
    updated_at: str


# Source set: funding, credit/stress, macro, rates and ETF trend proxies.
# VIX is kept in Stress only, never counted again in Internals.
SERIES: dict[str, dict[str, Any]] = {
    "WALCL": {"label": "Federal Reserve total assets", "group": "liquidity", "frequency": "weekly", "unit": "USD millions", "max_age": 14, "kind": "level_good"},
    "WRESBAL": {"label": "Bank reserve balances", "group": "liquidity", "frequency": "weekly", "unit": "USD millions", "max_age": 14, "kind": "level_good"},
    "WTREGEN": {"label": "Treasury General Account", "group": "liquidity", "frequency": "weekly", "unit": "USD millions", "max_age": 14, "kind": "level_bad"},
    "RRPONTSYD": {"label": "Overnight reverse repo", "group": "liquidity", "frequency": "daily", "unit": "USD billions", "max_age": 5, "kind": "level_bad"},
    "SOFR": {"label": "SOFR", "group": "liquidity", "frequency": "daily", "unit": "%", "max_age": 5, "kind": "level_bad", "normal": 5.5},
    "EFFR": {"label": "Effective federal funds rate", "group": "rates", "frequency": "daily", "unit": "%", "max_age": 5, "kind": "level", "normal": 4},
    "VIXCLS": {"label": "CBOE VIX", "group": "stress", "frequency": "daily", "unit": "index", "max_age": 5, "kind": "level_bad", "normal": 20},
    "NFCI": {"label": "Chicago Fed NFCI", "group": "stress", "frequency": "weekly", "unit": "index", "max_age": 14, "kind": "level_bad", "normal": 0},
    "STLFSI4": {"label": "St. Louis Fed Financial Stress Index", "group": "stress", "frequency": "weekly", "unit": "index", "max_age": 14, "kind": "level_bad", "normal": 0},
    "BAMLH0A0HYM2": {"label": "US high-yield option-adjusted spread", "group": "stress", "frequency": "daily", "unit": "%", "max_age": 7, "kind": "level_bad", "normal": 5},
    "CPIAUCSL": {"label": "CPI (year-over-year)", "group": "inflation", "frequency": "monthly", "unit": "% YoY", "max_age": 70, "kind": "yoy", "price_index": True},
    "CPILFESL": {"label": "Core CPI (year-over-year)", "group": "inflation", "frequency": "monthly", "unit": "% YoY", "max_age": 70, "kind": "yoy", "price_index": True},
    "PCEPI": {"label": "PCE (year-over-year)", "group": "inflation", "frequency": "monthly", "unit": "% YoY", "max_age": 70, "kind": "yoy", "price_index": True},
    "PCEPILFE": {"label": "Core PCE (year-over-year)", "group": "inflation", "frequency": "monthly", "unit": "% YoY", "max_age": 70, "kind": "yoy", "price_index": True},
    "UNRATE": {"label": "Unemployment rate", "group": "labour", "frequency": "monthly", "unit": "%", "max_age": 70, "kind": "level_bad"},
    "PAYEMS": {"label": "Nonfarm payrolls", "group": "labour", "frequency": "monthly", "unit": "thousands", "max_age": 70, "kind": "change_good"},
    "GDPC1": {"label": "Real GDP", "group": "growth", "frequency": "quarterly", "unit": "USD billions, chained", "max_age": 130, "kind": "qoq_annualized", "price_index": True},
    "INDPRO": {"label": "Industrial production", "group": "growth", "frequency": "monthly", "unit": "index", "max_age": 70, "kind": "yoy", "price_index": True},
    "DGS2": {"label": "2-year Treasury yield", "group": "rates", "frequency": "daily", "unit": "%", "max_age": 7, "kind": "level", "normal": 4},
    "DGS10": {"label": "10-year Treasury yield", "group": "rates", "frequency": "daily", "unit": "%", "max_age": 7, "kind": "level", "normal": 4},
    "T10YIE": {"label": "10-year breakeven inflation", "group": "rates", "frequency": "daily", "unit": "%", "max_age": 7, "kind": "level_bad", "normal": 2.5},
}


def regime_label(score: float | None) -> str:
    if score is None:
        return "PARTIAL DATA"
    if score < 20: return "STRESS"
    if score < 40: return "RISK-OFF"
    if score < 60: return "NEUTRAL"
    if score < 80: return "RISK-ON"
    return "STRONG RISK-ON"


def _freshness(as_of: str | None, max_age: int) -> str:
    if not as_of: return "missing"
    try: age = (date.today() - date.fromisoformat(as_of[:10])).days
    except ValueError: return "unknown"
    return "fresh" if age <= max_age else ("stale" if age <= max_age * 2 else "old")


def _score_observation(key: str, latest: float, previous: float | None, history: list[float]) -> tuple[float, str, str]:
    spec = SERIES[key]
    kind = spec["kind"]
    if key in {"WALCL", "WRESBAL", "WTREGEN", "RRPONTSYD"} and len(history) >= 6:
        # Recent change percentile is more meaningful than raw balance-sheet levels.
        delta = latest - history[-6]
        deltas = [history[i] - history[max(0, i - 5)] for i in range(5, len(history))]
        p = sum(x <= delta for x in deltas) / max(1, len(deltas)) * 100
        score = p if kind == "level_good" else 100 - p
        label = "improving" if score >= 60 else ("deteriorating" if score <= 40 else "stable")
        return round(score, 1), label, f"5-observation change {delta:+,.2f}"
    normal = spec.get("normal")
    if normal is not None:
        # Threshold bands are deliberately broad; they communicate conditions, not targets.
        distance = latest - normal
        score = max(0, min(100, 70 - distance * (8 if key in {"VIXCLS", "BAMLH0A0HYM2", "SOFR"} else 20)))
        if kind == "level": score = max(0, min(100, 60 - abs(distance) * 12))
        label = "contained" if score >= 60 else ("elevated" if score < 40 else "watch")
        return round(score, 1), label, f"level {latest:,.2f}; reference band centered near {normal:g}"
    if previous is None: return 50.0, "latest observation", "No prior observation available"
    change = latest - previous
    good_when_up = kind in {"change_good", "yoy", "qoq_annualized"}
    if key in {"UNRATE", "T10YIE"}: good_when_up = False
    if kind == "yoy":
        # For inflation, deviation/change are interpreted as direction, separately from target.
        good_when_up = False
    score = 62.0 if (change >= 0) == good_when_up else 38.0
    if abs(change) < 0.001: score = 50.0
    return score, ("improving" if score > 50 else "deteriorating" if score < 50 else "stable"), f"latest change {change:+.3f}"


def _horizon_change(points: list[tuple[str, float]], days: int, tolerance: int) -> float | None:
    """Compare to the closest observation around a calendar horizon.

    Frequencies without a suitably close point (e.g. quarterly GDP at one
    month) return None rather than disguising a quarter-on-quarter change.
    """
    if len(points) < 2:
        return None
    try:
        latest_date = date.fromisoformat(points[-1][0])
        target = latest_date - timedelta(days=days)
    except ValueError:
        return None
    eligible = []
    for obs_date, value in points[:-1]:
        try: parsed = date.fromisoformat(obs_date)
        except ValueError: continue
        delta = (target - parsed).days
        if 0 <= delta <= tolerance:
            eligible.append((delta, value))
    if not eligible:
        return None
    _, previous_value = min(eligible, key=lambda item: item[0])
    return round(points[-1][1] - previous_value, 3)


def _fetch_fred() -> dict[str, list[tuple[str, float]]]:
    if not settings.fred_api_key:
        return {}
    result: dict[str, list[tuple[str, float]]] = {}
    def fetch(key: str) -> tuple[str, list[tuple[str, float]]]:
        try:
            response = requests.get(FRED_URL, params={"series_id": key, "api_key": settings.fred_api_key, "file_type": "json", "sort_order": "desc", "limit": 30}, timeout=8)
            response.raise_for_status()
            observations = response.json().get("observations", [])
            parsed = [(str(o["date"]), float(o["value"])) for o in observations if o.get("value") not in (None, ".")]
            return key, list(reversed(parsed))
        except Exception as exc:
            logger.warning("Market Desk FRED series %s unavailable: %s", key, exc)
            return key, []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(fetch,key) for key in SERIES]
        for future in as_completed(futures):
            key, parsed=future.result()
            if parsed: result[key]=parsed
    return result


def _fred_indicator(key: str, raw: dict[str, list[tuple[str, float]]]) -> Indicator:
    spec = SERIES[key]
    values = raw.get(key, [])
    if not values:
        return Indicator(key=key, label=spec["label"], value=None, frequency=spec["frequency"], source="FRED", source_url=f"https://fred.stlouisfed.org/series/{key}", interpretation="No observation returned; excluded from score.")
    dates, vals = [x[0] for x in values], [x[1] for x in values]
    if key in {"CPIAUCSL","CPILFESL","PCEPI","PCEPILFE","INDPRO"} and len(vals)<13:
        return Indicator(key=key,label=spec["label"],value=None,as_of=dates[-1],frequency=spec["frequency"],freshness=_freshness(dates[-1],spec["max_age"]),source="FRED",source_url=f"https://fred.stlouisfed.org/series/{key}",interpretation="Insufficient history to calculate the year-over-year rate; excluded from score.")
    if key=="GDPC1" and len(vals)<3:
        return Indicator(key=key,label=spec["label"],value=None,as_of=dates[-1],frequency=spec["frequency"],freshness=_freshness(dates[-1],spec["max_age"]),source="FRED",source_url=f"https://fred.stlouisfed.org/series/{key}",interpretation="Insufficient history to calculate quarterly growth; excluded from score.")
    if key=="PAYEMS" and len(vals)<2:
        return Indicator(key=key,label=spec["label"],value=None,as_of=dates[-1],frequency=spec["frequency"],freshness=_freshness(dates[-1],spec["max_age"]),source="FRED",source_url=f"https://fred.stlouisfed.org/series/{key}",interpretation="Insufficient history to calculate monthly payroll additions; excluded from score.")
    latest, prev = vals[-1], vals[-2] if len(vals) > 1 else None
    if spec.get("price_index") and key in {"CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE", "INDPRO"} and len(vals) >= 13:
        latest = (vals[-1] / vals[-13] - 1) * 100
        prev = (vals[-2] / vals[-14] - 1) * 100 if len(vals) >= 14 else None
        score_hist = [(vals[i] / vals[i-12] - 1) * 100 for i in range(12, len(vals))]
        transformed = [(dates[i], (vals[i] / vals[i-12] - 1) * 100) for i in range(12, len(vals))]
    elif key == "GDPC1" and len(vals) >= 3:
        latest = ((vals[-1] / vals[-2]) ** 4 - 1) * 100
        prev = ((vals[-2] / vals[-3]) ** 4 - 1) * 100 if len(vals) >= 3 else None
        score_hist = [((vals[i] / vals[i-1]) ** 4 - 1) * 100 for i in range(1, len(vals))]
        transformed = [(dates[i], ((vals[i] / vals[i-1]) ** 4 - 1) * 100) for i in range(1, len(vals))]
    else:
        score_hist = vals
        transformed = list(zip(dates, vals))
        if key == "PAYEMS" and len(vals) >= 2:
            latest, prev = vals[-1] - vals[-2], vals[-2] - vals[-3] if len(vals) >= 3 else None
            score_hist = [vals[i] - vals[i-1] for i in range(1, len(vals))]
            transformed = [(dates[i], vals[i] - vals[i-1]) for i in range(1, len(vals))]
    score, signal, reason = _score_observation(key, latest, prev, score_hist)
    if key == "SOFR":
        score=None
        signal="context"
        reason="Overnight secured rate; funding stress is scored separately using SOFR − EFFR."
    as_of = dates[-1]
    fresh = _freshness(as_of, spec["max_age"])
    if fresh in {"old", "stale"}:
        signal = "stale"
    horizon_tolerance = 12 if spec["frequency"] in {"daily", "weekly"} else 40 if spec["frequency"] == "monthly" else 95
    change_1w = _horizon_change(transformed, 7, horizon_tolerance) if spec["frequency"] in {"daily", "weekly"} else None
    change_1m = _horizon_change(transformed, 30, horizon_tolerance) if spec["frequency"] != "quarterly" else None
    return Indicator(key=key, label=spec["label"], value=round(latest, 3), previous=round(prev, 3) if prev is not None else None, change=round(latest-prev, 3) if prev is not None else None, change_1w=change_1w, change_1m=change_1m, as_of=as_of, frequency=spec["frequency"], freshness=fresh, source="FRED (SOFR + EFFR)" if key=="SOFR" else "FRED", source_url=f"https://fred.stlouisfed.org/series/{key}", reference_source_url="https://fred.stlouisfed.org/series/EFFR" if key=="SOFR" else None, interpretation=reason, signal=signal, score=score if fresh == "fresh" else None)


def _sofr_spread_indicator(raw: dict[str, list[tuple[str, float]]]) -> Indicator:
    sofr=dict(raw.get("SOFR", [])); effr=dict(raw.get("EFFR", []))
    points=[(day,(value-effr[day])*100) for day,value in raw.get("SOFR",[]) if day in effr]
    if not points:
        return Indicator(key="SOFR_EFFR",label="SOFR − EFFR spread",value=None,frequency="daily",source="FRED (SOFR + EFFR)",source_url="https://fred.stlouisfed.org/series/SOFR",reference_source_url="https://fred.stlouisfed.org/series/EFFR",interpretation="Matched SOFR and EFFR observations are unavailable; excluded from the funding score.")
    day,value=points[-1]
    change=value-points[-2][1] if len(points)>1 else None
    score=round(max(0,min(100,80-max(0,value-3)*4)),1)
    freshness="fresh" if _freshness(day,5)=="fresh" and _freshness(max(sofr),5)=="fresh" and _freshness(max(effr),5)=="fresh" else "stale"
    signal="normal" if score>=60 else "watch" if score>=40 else "elevated"
    return Indicator(key="SOFR_EFFR",label="SOFR − EFFR spread",value=round(value,2),previous=round(points[-2][1],2) if len(points)>1 else None,change=round(change,2) if change is not None else None,change_1w=_horizon_change(points,7,12),change_1m=_horizon_change(points,30,12),as_of=day,frequency="daily",freshness=freshness,source="FRED (SOFR + EFFR)",source_url="https://fred.stlouisfed.org/series/SOFR",reference_source_url="https://fred.stlouisfed.org/series/EFFR",interpretation=f"Funding score uses the spread: {value:.1f}bp; values above 3bp lower the liquidity signal. This does not include repo volumes or intraday tails.",signal=signal,score=score if freshness=="fresh" else None)


def _alpaca_internals() -> list[Indicator]:
    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        return []
    try:
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=420)
        response = requests.get("https://data.alpaca.markets/v2/stocks/bars", params={"symbols":"SPY,QQQ,IWM,RSP", "timeframe":"1Day", "start":start.isoformat(), "end":end.isoformat(), "limit":10000, "adjustment":"split", "feed":"iex"}, headers={"APCA-API-KEY-ID":settings.alpaca_api_key,"APCA-API-SECRET-KEY":settings.alpaca_secret_key},timeout=12)
        response.raise_for_status()
        bars = response.json().get("bars", {})
        output = []
        for symbol, label in [("SPY","S&P 500 cap-weighted trend"),("RSP","S&P 500 equal-weight confirmation"),("IWM","Small-cap confirmation"),("QQQ","Nasdaq 100 trend")]:
            rows = bars.get(symbol, [])
            closes = [float(x["c"]) for x in rows if x.get("c") is not None]
            as_of = rows[-1]["t"][:10] if rows else None
            value = closes[-1] if closes else None
            sma50 = sum(closes[-50:])/50 if len(closes)>=50 else None
            sma200 = sum(closes[-200:])/200 if len(closes)>=200 else None
            score = (50 + (25 if value and sma50 and value>sma50 else -25) + (25 if value and sma200 and value>sma200 else -25)) if value and sma50 and sma200 else None
            output.append(Indicator(key=symbol,label=label,value=round(value,2) if value else None,previous=round(closes[-2],2) if len(closes)>1 else None,change=round((closes[-1]/closes[-2]-1)*100,2) if len(closes)>1 else None,change_1w=round((closes[-1]/closes[-6]-1)*100,2) if len(closes)>=6 else None,change_1m=round((closes[-1]/closes[-22]-1)*100,2) if len(closes)>=22 else None,as_of=as_of,frequency="daily",freshness=_freshness(as_of,4),source="Alpaca IEX",source_url="https://docs.alpaca.markets/docs/market-data",interpretation=("Above both 50- and 200-day averages" if score and score>50 else "Below one or both trend averages" if score is not None else "Insufficient history"),signal="supportive" if score and score>50 else "weak" if score is not None else "unavailable",score=score))
        return output
    except Exception as exc:
        logger.warning("Market Desk Alpaca internals unavailable: %s", exc)
        return []


def weighted_score(indicators: list[Indicator], weights: dict[str, float]) -> float | None:
    available = [(i.score, weights.get(i.key, i.weight)) for i in indicators if i.score is not None and weights.get(i.key, i.weight) > 0]
    if not available: return None
    return round(sum(float(s)*w for s,w in available)/sum(w for _,w in available), 1)


def composite_score(components: list[tuple[float | None, float]], minimum_components: int = 2) -> float | None:
    available=[(float(score),weight) for score,weight in components if score is not None and weight>0]
    if len(available)<minimum_components: return None
    return round(sum(score*weight for score,weight in available)/sum(weight for _,weight in available),1)


def classify_macro(indicators: list[Indicator]) -> MacroRegime:
    inflation = [i for i in indicators if i.key in {"CPIAUCSL","CPILFESL","PCEPI","PCEPILFE"} and i.value is not None]
    growth = [i for i in indicators if i.key in {"GDPC1","INDPRO"} and i.value is not None]
    labour = [i for i in indicators if i.key in {"UNRATE","PAYEMS"} and i.value is not None]
    inf_delta = sum(i.change or 0 for i in inflation)/len(inflation) if inflation else None
    growth_delta = sum(i.change or 0 for i in growth)/len(growth) if growth else None
    labour_by_key={i.key:i for i in labour}
    unemployment=labour_by_key.get("UNRATE")
    payrolls=labour_by_key.get("PAYEMS")
    labour_stable = None if not labour else not (
        (unemployment is not None and (unemployment.change or 0) > 0.1)
        or (payrolls is not None and payrolls.value is not None and payrolls.value < 100)
    )
    if inf_delta is None or growth_delta is None:
        regime="INSUFFICIENT DATA"; conf=0
    else:
        g_up=growth_delta >= 0; i_up=inf_delta >= 0
        regime = "REFLATION" if g_up and i_up else "GOLDILOCKS" if g_up and not i_up else "STAGFLATION" if not g_up and i_up else "SLOWDOWN"
        conf=min(90, 50 + 10*min(len(inflation),2) + 10*min(len(growth),2) + (10 if labour else 0))
    inflation_level=sum(i.value or 0 for i in inflation)/len(inflation) if inflation else None
    inflation_direction="rising" if inf_delta is not None and inf_delta>0.02 else "cooling" if inf_delta is not None and inf_delta<-.02 else "stable" if inf_delta is not None else "unavailable"
    inflation_reading=f"{inflation_direction}; {'above' if inflation_level is not None and inflation_level>2 else 'at or below'} 2%" if inflation_level is not None else inflation_direction
    growth_direction="improving" if growth_delta is not None and growth_delta>0.05 else "cooling" if growth_delta is not None and growth_delta<-.05 else "stable" if growth_delta is not None else "unavailable"
    return MacroRegime(regime=regime,growth=growth_direction,inflation=inflation_reading,labour="stable" if labour_stable else "softening" if labour_stable is False else "unavailable",confidence=conf,indicators=indicators,method="Regime direction compares the change in real GDP growth and industrial-production growth rates with the change in headline/core inflation rates; the 2% reference is the Federal Reserve longer-run objective. Labour context is reported separately. Not a forecast.")


def _cross_asset(indicators: list[Indicator], desks: dict[str, float | None]) -> list[CrossAssetSignal]:
    by_key={i.key:i for i in indicators}
    signals: list[CrossAssetSignal]=[]
    spy=by_key.get("SPY"); rsp=by_key.get("RSP"); iwm=by_key.get("IWM")
    hy=by_key.get("BAMLH0A0HYM2")
    if spy and hy and spy.change is not None and hy.change is not None and spy.change>0 and hy.change>0.1:
        signals.append(CrossAssetSignal(level="warning",title="Equity-credit divergence",detail="Equities advanced while high-yield spreads widened."))
    if spy and rsp and spy.score is not None and rsp.score is not None and spy.score-rsp.score>=25:
        signals.append(CrossAssetSignal(level="watch",title="Narrow participation",detail="Cap-weighted S&P trend is stronger than equal-weight confirmation."))
    if rsp and iwm and rsp.score is not None and iwm.score is not None and rsp.score>50 and iwm.score<50:
        signals.append(CrossAssetSignal(level="watch",title="Small caps lagging",detail="Small-cap trend is not confirming broader large-cap strength."))
    if desks.get("liquidity",0) and desks.get("stress",0) and desks["liquidity"]>=60 and desks["stress"]>=60:
        signals.append(CrossAssetSignal(level="constructive",title="Liquidity and stress aligned",detail="Liquidity signals are supportive while observed stress remains contained."))
    return signals


def build_market_desk() -> MarketDeskResponse:
    fred = _fetch_fred()
    indicators=[_fred_indicator(k,fred) for k in SERIES]
    indicators.append(_sofr_spread_indicator(fred))
    indicators.extend(_alpaca_internals())
    liquidity=[i for i in indicators if SERIES.get(i.key,{}).get("group")=="liquidity" or i.key=="SOFR_EFFR"]
    stress=[i for i in indicators if SERIES.get(i.key,{}).get("group")=="stress"]
    macro_items=[i for i in indicators if SERIES.get(i.key,{}).get("group") in {"inflation","labour","growth","rates"}]
    internals=[i for i in indicators if i.key in {"SPY","QQQ","IWM","RSP"}]
    liq_score=weighted_score(liquidity,{"WALCL":2,"WRESBAL":2,"WTREGEN":1,"RRPONTSYD":1,"SOFR_EFFR":2})
    stress_score=weighted_score(stress,{"VIXCLS":1,"NFCI":0.5,"STLFSI4":0.5,"BAMLH0A0HYM2":2})
    macro=classify_macro(macro_items)
    macro_by_key={i.key:i for i in macro_items}
    inflation_score=weighted_score([macro_by_key[k] for k in ("CPIAUCSL","CPILFESL","PCEPI","PCEPILFE") if k in macro_by_key],{k:1 for k in ("CPIAUCSL","CPILFESL","PCEPI","PCEPILFE")})
    labour_score=weighted_score([macro_by_key[k] for k in ("UNRATE","PAYEMS") if k in macro_by_key],{"UNRATE":1,"PAYEMS":1})
    growth_score=weighted_score([macro_by_key[k] for k in ("GDPC1","INDPRO") if k in macro_by_key],{"GDPC1":1,"INDPRO":1})
    macro_score=weighted_score([Indicator(key="inflation",label="Inflation",value=None,frequency="mixed",source="FRED",interpretation="",score=inflation_score),Indicator(key="labour",label="Labour",value=None,frequency="mixed",source="FRED",interpretation="",score=labour_score),Indicator(key="growth",label="Growth",value=None,frequency="mixed",source="FRED",interpretation="",score=growth_score)],{"inflation":0.35,"labour":0.25,"growth":0.40})
    internals_score=weighted_score(internals,{k:1 for k in ["SPY","QQQ","IWM","RSP"]})
    components=[(liq_score,.30),(stress_score,.30),(macro_score,.20),(internals_score,.20)]
    total=composite_score(components)
    required_count=25
    available=sum(i.score is not None for i in indicators)
    confidence=round(100*available/required_count) if required_count else 0
    status="complete" if available==required_count else "partial"
    warnings=[]
    if liq_score is not None and liq_score<45: warnings.append("liquidity draining")
    if stress_score is not None and stress_score<45: warnings.append("stress elevated")
    if macro.growth=="cooling": warnings.append("growth cooling")
    if macro.inflation.startswith("rising"): warnings.append("inflation sticky")
    if internals_score is not None and internals_score>=55: warnings.append("ETF trend proxies constructive")
    if not warnings: warnings=["data coverage limited" if status=="partial" else "conditions mixed"]
    grade=regime_label(total)
    # No historical composite snapshots exist yet; do not imply that today's score is moving.
    direction="→"
    cross=_cross_asset(indicators,{"liquidity":liq_score,"stress":stress_score})
    call=[]
    call.append(f"Market conditions are {grade.lower()}" + (f" ({total:.0f}/100)." if total is not None else "; available data are incomplete."))
    call.append(". ".join(warnings[:3]).capitalize()+".")
    if cross: call.append(cross[0].detail)
    changed=[]
    eligible_changes=[]
    scales={"WALCL":100_000,"WRESBAL":100_000,"WTREGEN":100_000,"RRPONTSYD":20,"SOFR_EFFR":5,"BAMLH0A0HYM2":.1,"NFCI":.1,"STLFSI4":.1,"CPIAUCSL":.1,"CPILFESL":.1,"PCEPI":.1,"PCEPILFE":.1,"DGS2":.1,"DGS10":.1,"T10YIE":.1,"VIXCLS":3,"PAYEMS":50}
    for i in indicators:
        if i.score is None: continue
        candidates=[]
        if i.frequency=="daily" and i.change is not None: candidates.append((i.change,"1D"))
        if i.change_1w is not None: candidates.append((i.change_1w,"1W"))
        if i.change_1m is not None: candidates.append((i.change_1m,"1M"))
        for change,horizon in candidates:
            scale=scales.get(i.key,1)
            eligible_changes.append((i,change,horizon,abs(change)/scale))
    ranked=sorted(eligible_changes,key=lambda row:row[3],reverse=True)
    selected=[]
    # Keep the strongest change at each horizon visible, then fill to five.
    for horizon in ("1D","1W","1M"):
        row=next((r for r in ranked if r[2]==horizon and r not in selected),None)
        if row: selected.append(row)
    for row in ranked:
        if row not in selected and len(selected)<5: selected.append(row)
    for i,change,horizon,_ in selected:
        unit="bn" if i.key in {"WALCL","WRESBAL","WTREGEN","RRPONTSYD"} else "bp" if i.key in {"SOFR_EFFR","BAMLH0A0HYM2","SOFR","EFFR","DGS2","DGS10","T10YIE"} else "pts" if i.key in {"VIXCLS","NFCI","STLFSI4"} else "pp" if i.key in {"CPIAUCSL","CPILFESL","PCEPI","PCEPILFE","UNRATE"} else "k" if i.key=="PAYEMS" else "%" if i.key in {"SPY","QQQ","IWM","RSP"} else ""
        if i.key in {"WALCL","WRESBAL","WTREGEN"}: change=round(change/1000,1)
        if unit=="bp" and i.key!="SOFR_EFFR": change=round(change*100,1)
        changed.append(MarketChange(label=i.label,change=change,unit=unit,horizon=horizon,as_of=i.as_of,source=i.source))
    desks={
      "liquidity":Desk(score=liq_score,status="supportive" if liq_score and liq_score>=60 else "tightening" if liq_score and liq_score<40 else "mixed" if liq_score is not None else "partial data",summary="Balance-sheet and funding proxies; net-liquidity components are not treated as an accounting identity.",indicators=liquidity,coverage=sum(i.score is not None for i in liquidity)),
      "stress":Desk(score=stress_score,status="contained" if stress_score and stress_score>=60 else "elevated" if stress_score and stress_score<40 else "mixed" if stress_score is not None else "partial data",summary="Financial and credit stress measures. Volatility alone does not imply systemic stress.",indicators=stress,coverage=sum(i.score is not None for i in stress)),
      "market_internals":Desk(score=internals_score,status="confirming" if internals_score and internals_score>=60 else "weakening" if internals_score and internals_score<40 else "mixed" if internals_score is not None else "partial data",summary="ETF trend confirmation only; not a constituent-level breadth measure.",indicators=internals,coverage=sum(i.score is not None for i in internals)),
    }
    return MarketDeskResponse(market_regime=MarketRegime(score=total,label=grade,direction=direction,status=status,components={"liquidity":liq_score,"stress":stress_score,"macro":macro_score,"market_internals":internals_score},method="30% liquidity, 30% stress/credit, 20% macro, 20% market internals; available component weights are renormalized when data are missing."),liquidity=desks["liquidity"],stress=desks["stress"],macro=macro,market_internals=desks["market_internals"],cross_asset_signals=cross,desk_call=call[:3],what_changed=changed,watch_next=[],confidence=confidence,coverage={"available":available,"expected":required_count},sources=sorted({i.source for i in indicators if i.value is not None}),updated_at=datetime.now(timezone.utc).isoformat())


def get_market_desk() -> MarketDeskResponse:
    with _lock:
        now=time.time()
        if _cache["data"] is not None and now-_cache["at"]<TTL_SECONDS:
            return _cache["data"]
        data=build_market_desk()
        _cache.update(data=data,at=now)
        return data
