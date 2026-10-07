from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.orm import Explanation, Opportunity, PriceSnapshot, Ticker
from app.models.schemas import CanslimSchema, OpportunityDetailSchema, OpportunitySchema, StrategyResultSchema, WeinsteinSchema
from app.stock_selection import stock_selection_score

_STRATEGY_NAMES = {"minervini", "lynch", "berkshire", "dividendos"}
_EARLY_STAGE2 = "early_stage2"
_EARLY_STAGE2_MAX_WEEKS = 6
_FEATURED_MIN_SCORE = 80

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _latest_run_date(db: Session) -> date | None:
    return db.query(func.max(Opportunity.run_date)).scalar()


_WEINSTEIN_MAX_WEEKS = 8


def _compute_signal_type(opp: Opportunity) -> str | None:
    is_weinstein = bool(opp.weinstein_transition) and opp.weeks_in_stage <= _WEINSTEIN_MAX_WEEKS
    criteria = _normalise_criteria(opp.canslim_criteria)
    n_passes = criteria.get("N", {}).get("value") is True
    all_verifiable_pass = all(v["value"] is True for v in criteria.values() if v.get("value") is not None)
    is_canslim = n_passes and all_verifiable_pass
    if is_weinstein and is_canslim:
        return "both"
    if is_weinstein:
        return "weinstein"
    if is_canslim:
        return "canslim"
    return None


def _normalise_criteria(raw: dict | None) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for letter in ("C", "A", "N", "S", "L", "I", "M"):
        item = (raw or {}).get(letter) or (raw or {}).get(letter.lower())
        if not isinstance(item, dict):
            continue
        value = item.get("value", item.get("passed"))
        if isinstance(value, str):
            value = value.strip().lower() in {"true", "1", "cumple", "passed"}
        if value not in (True, False, None):
            value = None
        result[letter] = {"value": value, "detail": item.get("detail") or item.get("description") or "Sin datos."}
    return result


def _strategies_to_schema(raw: dict) -> dict[str, StrategyResultSchema]:
    result = {}
    for name, data in (raw or {}).items():
        if isinstance(data, dict):
            result[name] = StrategyResultSchema(passed=data.get("passed"), score=data.get("score"), details=data.get("details", ""))
    return result


def _parse_strategies(opp: Opportunity) -> dict:
    raw = getattr(opp, "strategies", None)
    if not raw:
        return {}
    if isinstance(raw, str):
        import json as _json
        try:
            raw = _json.loads(raw)
        except Exception:
            return {}
    return raw if isinstance(raw, dict) else {}


def _has_strategy_signal(opp: Opportunity, strategy: str) -> bool:
    return bool((_parse_strategies(opp).get(strategy) or {}).get("passed"))


def _first_detected_performance(db: Session, rows: list[tuple[Opportunity, Ticker]], first_detected: dict[int, date]) -> dict[int, dict[str, float | None]]:
    if not rows:
        return {}

    detection_dates = {ticker_id: detected for ticker_id, detected in first_detected.items() if detected is not None}
    performance: dict[int, dict[str, float | None]] = {
        opp.ticker_id: {
            "first_detected_price": None,
            "current_price": None,
            "return_since_first_detected_pct": None,
        }
        for opp, _ in rows
    }
    if not detection_dates:
        return performance

    ticker_ids = list(detection_dates)
    first_date_expression = case(detection_dates, value=PriceSnapshot.ticker_id, else_=date.max)
    ranked_snapshots = (
        db.query(
            PriceSnapshot.ticker_id.label("ticker_id"),
            PriceSnapshot.close.label("close"),
            func.row_number().over(
                partition_by=PriceSnapshot.ticker_id,
                order_by=PriceSnapshot.date.asc(),
            ).label("first_rank"),
            func.row_number().over(
                partition_by=PriceSnapshot.ticker_id,
                order_by=PriceSnapshot.date.desc(),
            ).label("latest_rank"),
        )
        .filter(
            PriceSnapshot.ticker_id.in_(ticker_ids),
            PriceSnapshot.date >= first_date_expression,
        )
        .subquery()
    )
    snapshots = db.query(
        ranked_snapshots.c.ticker_id,
        ranked_snapshots.c.close,
        ranked_snapshots.c.first_rank,
        ranked_snapshots.c.latest_rank,
    ).filter(or_(ranked_snapshots.c.first_rank == 1, ranked_snapshots.c.latest_rank == 1)).all()

    first_prices: dict[int, float] = {}
    latest_prices: dict[int, float] = {}
    for ticker_id, close, first_rank, latest_rank in snapshots:
        if first_rank == 1:
            first_prices[ticker_id] = close
        if latest_rank == 1:
            latest_prices[ticker_id] = close

    for opp, ticker in rows:
        ticker_id = opp.ticker_id
        detected_on = detection_dates.get(ticker_id)
        if detected_on is None:
            continue
        first_price = first_prices.get(ticker_id)
        daily_date = ticker.last_daily_price_date
        daily_price_is_current = (
            ticker.last_daily_close is not None
            and (daily_date is None or daily_date >= detected_on)
        )
        current_price = ticker.last_daily_close if daily_price_is_current else latest_prices.get(ticker_id)
        return_pct = (
            round((current_price / first_price - 1) * 100, 2)
            if first_price is not None and first_price > 0 and current_price is not None
            else None
        )
        performance[ticker_id] = {
            "first_detected_price": first_price,
            "current_price": current_price,
            "return_since_first_detected_pct": return_pct,
        }
    return performance


def _to_schema(opp: Opportunity, ticker: Ticker, explanation_text: str | None, first_detected_date: date | None = None, requested_strategy: str | None = None, performance: dict[str, float | None] | None = None) -> OpportunitySchema:
    verifiable = opp.canslim_verifiable_count
    passed = opp.canslim_passed_count
    raw_strategies = _parse_strategies(opp)
    selection_scores = {method: round(stock_selection_score(opp, method), 2) for method, result in raw_strategies.items() if isinstance(result, dict) and result.get("passed") is True}
    selection_method = requested_strategy if requested_strategy in selection_scores else (max(selection_scores, key=selection_scores.get) if selection_scores else None)
    return OpportunitySchema(
        ticker=ticker.symbol, name=ticker.name, sector=ticker.sector, combined_score=opp.combined_score, risk_bucket=opp.risk_bucket,
        weinstein=WeinsteinSchema(stage=opp.weinstein_stage, is_transition=opp.weinstein_transition, weeks_in_stage=opp.weeks_in_stage, ma_slope_pct=opp.weinstein_ma_slope_pct, relative_volume=opp.weinstein_relative_volume, rsi=opp.weinstein_rsi if opp.weinstein_rsi is not None else 50.0),
        canslim=CanslimSchema(criteria=_normalise_criteria(opp.canslim_criteria), score=f"{passed}/{verifiable} verificables"),
        explanation=explanation_text, last_updated=opp.run_date, first_detected_date=first_detected_date,
        first_detected_price=(performance or {}).get("first_detected_price"),
        current_price=(performance or {}).get("current_price"),
        return_since_first_detected_pct=(performance or {}).get("return_since_first_detected_pct"),
        signal_type=_compute_signal_type(opp), strategies=_strategies_to_schema(raw_strategies), selection_score=selection_scores.get(selection_method) if selection_method else None, selection_method=selection_method,
    )


def _first_detected_dates(db: Session, ticker_ids: set[int]) -> dict[int, date]:
    if not ticker_ids:
        return {}
    rows = (
        db.query(Opportunity.ticker_id, func.min(Opportunity.run_date))
        .filter(
            Opportunity.ticker_id.in_(ticker_ids),
            Opportunity.combined_score >= _FEATURED_MIN_SCORE,
        )
        .group_by(Opportunity.ticker_id)
        .all()
    )
    return {tid: first_date for tid, first_date in rows}


@router.get("", response_model=list[OpportunitySchema])
def list_opportunities(limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0, le=10000), min_score: int = Query(_FEATURED_MIN_SCORE, ge=0, le=100), risk: str | None = Query(None, pattern="^(bajo|medio|alto)$"), sector: str | None = None, sort: str = Query("score", pattern="^(score|stage)$"), strategy: str | None = Query(None), db: Session = Depends(get_db)) -> list[OpportunitySchema]:
    run_date = _latest_run_date(db)
    if run_date is None:
        return []
    apply_score_filter = not (strategy and (strategy in _STRATEGY_NAMES or strategy == _EARLY_STAGE2))
    query = db.query(Opportunity, Ticker).join(Ticker, Opportunity.ticker_id == Ticker.id).filter(Opportunity.run_date == run_date)
    if apply_score_filter:
        query = query.filter(Opportunity.combined_score >= min_score)
    if risk:
        query = query.filter(Opportunity.risk_bucket == risk)
    if sector:
        query = query.filter(Ticker.sector == sector)
    query = query.order_by(Opportunity.combined_score.desc()) if sort == "score" else query.order_by(Opportunity.weinstein_stage.asc(), Opportunity.combined_score.desc())
    rows = query.all()
    if strategy == _EARLY_STAGE2:
        rows = [(opp, ticker) for opp, ticker in rows if opp.weinstein_stage == 2 and opp.weeks_in_stage <= _EARLY_STAGE2_MAX_WEEKS and opp.weinstein_transition]
        rows.sort(key=lambda pair: (pair[0].weeks_in_stage, -pair[0].combined_score))
    elif strategy and strategy in _STRATEGY_NAMES:
        rows = [(opp, ticker) for opp, ticker in rows if _has_strategy_signal(opp, strategy)]
        rows.sort(key=lambda pair: (-float((_parse_strategies(pair[0]).get(strategy) or {}).get("score") or 0), -pair[0].combined_score))
    else:
        rows = [(opp, ticker) for opp, ticker in rows if opp.combined_score >= _FEATURED_MIN_SCORE]
    rows = rows[offset : offset + limit]
    explanations = {e.ticker_id: e.text for e in db.query(Explanation).filter(Explanation.run_date == run_date).all()}
    first_detected = _first_detected_dates(db, {opp.ticker_id for opp, _ in rows})
    performance = _first_detected_performance(db, rows, first_detected)
    return [_to_schema(opp, ticker, explanations.get(opp.ticker_id), first_detected.get(opp.ticker_id), requested_strategy=strategy if strategy in _STRATEGY_NAMES else None, performance=performance.get(opp.ticker_id)) for opp, ticker in rows]


@router.get("/{symbol}", response_model=OpportunityDetailSchema)
def get_opportunity_detail(symbol: str, db: Session = Depends(get_db)) -> OpportunityDetailSchema:
    ticker = db.query(Ticker).filter_by(symbol=symbol.upper()).one_or_none()
    if ticker is None:
        raise HTTPException(status_code=404, detail=f"Ticker {symbol} no encontrado")
    opp = db.query(Opportunity).filter(Opportunity.ticker_id == ticker.id).order_by(Opportunity.run_date.desc()).first()
    if opp is None:
        raise HTTPException(status_code=404, detail=f"Sin datos de screener para {symbol} todavia")
    explanation = db.query(Explanation).filter(Explanation.ticker_id == ticker.id, Explanation.run_date == opp.run_date).one_or_none()
    first_detected_date = _first_detected_dates(db, {ticker.id}).get(ticker.id)
    base = _to_schema(opp, ticker, explanation.text if explanation else None, first_detected_date=first_detected_date)
    snapshots = db.query(PriceSnapshot).filter(PriceSnapshot.ticker_id == ticker.id).order_by(PriceSnapshot.date.desc()).limit(130).all()
    snapshots = list(reversed(snapshots))
    price_history = [{"date": s.date.isoformat(), "open": s.open, "high": s.high, "low": s.low, "close": s.close, "volume": s.volume} for s in snapshots]
    first_snapshot = (
        db.query(PriceSnapshot)
        .filter(PriceSnapshot.ticker_id == ticker.id, PriceSnapshot.date >= first_detected_date)
        .order_by(PriceSnapshot.date.asc())
        .first()
        if first_detected_date
        else None
    )
    first_detected_price = first_snapshot.close if first_snapshot else None
    current_price = ticker.last_daily_close or (snapshots[-1].close if snapshots else None)
    return_since_first_detected_pct = round((current_price / first_detected_price - 1) * 100, 2) if first_detected_price and current_price else None
    base_data = base.model_dump()
    base_data.update(first_detected_price=first_detected_price, current_price=current_price, return_since_first_detected_pct=return_since_first_detected_pct)
    return OpportunityDetailSchema(**base_data, price_history=price_history)
