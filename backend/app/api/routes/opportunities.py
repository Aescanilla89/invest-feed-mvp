from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.orm import Explanation, Opportunity, Ticker
from app.models.schemas import CanslimSchema, OpportunityDetailSchema, OpportunitySchema, WeinsteinSchema
from app.screener.data_source import YFinanceDataSource

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _latest_run_date(db: Session) -> date | None:
    return db.query(func.max(Opportunity.run_date)).scalar()


def _to_schema(opp: Opportunity, ticker: Ticker, explanation_text: str | None) -> OpportunitySchema:
    verifiable = opp.canslim_verifiable_count
    passed = opp.canslim_passed_count
    return OpportunitySchema(
        ticker=ticker.symbol,
        name=ticker.name,
        sector=ticker.sector,
        combined_score=opp.combined_score,
        risk_bucket=opp.risk_bucket,
        weinstein=WeinsteinSchema(
            stage=opp.weinstein_stage,
            is_transition=opp.weinstein_transition,
            weeks_in_stage=opp.weeks_in_stage,
            ma_slope_pct=opp.weinstein_ma_slope_pct,
            relative_volume=opp.weinstein_relative_volume,
        ),
        canslim=CanslimSchema(
            criteria=opp.canslim_criteria,
            score=f"{passed}/{verifiable} verificables",
        ),
        explanation=explanation_text,
        last_updated=opp.run_date,
    )


@router.get("", response_model=list[OpportunitySchema])
def list_opportunities(
    min_score: int = Query(0, ge=0, le=100),
    risk: str | None = Query(None, pattern="^(bajo|medio|alto)$"),
    sector: str | None = None,
    sort: str = Query("score", pattern="^(score|stage)$"),
    db: Session = Depends(get_db),
) -> list[OpportunitySchema]:
    run_date = _latest_run_date(db)
    if run_date is None:
        return []

    query = (
        db.query(Opportunity, Ticker)
        .join(Ticker, Opportunity.ticker_id == Ticker.id)
        .filter(Opportunity.run_date == run_date)
        .filter(Opportunity.combined_score >= min_score)
    )
    if risk:
        query = query.filter(Opportunity.risk_bucket == risk)
    if sector:
        query = query.filter(Ticker.sector == sector)

    if sort == "score":
        query = query.order_by(Opportunity.combined_score.desc())
    else:
        query = query.order_by(Opportunity.weinstein_stage.asc(), Opportunity.combined_score.desc())

    rows = query.all()

    explanations = {
        e.ticker_id: e.text
        for e in db.query(Explanation).filter(Explanation.run_date == run_date).all()
    }

    return [_to_schema(opp, ticker, explanations.get(opp.ticker_id)) for opp, ticker in rows]


@router.get("/{symbol}", response_model=OpportunityDetailSchema)
def get_opportunity_detail(symbol: str, db: Session = Depends(get_db)) -> OpportunityDetailSchema:
    ticker = db.query(Ticker).filter_by(symbol=symbol.upper()).one_or_none()
    if ticker is None:
        raise HTTPException(status_code=404, detail=f"Ticker {symbol} no encontrado")

    opp = (
        db.query(Opportunity)
        .filter(Opportunity.ticker_id == ticker.id)
        .order_by(Opportunity.run_date.desc())
        .first()
    )
    if opp is None:
        raise HTTPException(status_code=404, detail=f"Sin datos de screener para {symbol} todavía")

    explanation = (
        db.query(Explanation)
        .filter(Explanation.ticker_id == ticker.id, Explanation.run_date == opp.run_date)
        .one_or_none()
    )

    base = _to_schema(opp, ticker, explanation.text if explanation else None)

    # El histórico de precio para el gráfico se trae en vivo de yfinance --
    # price_snapshots existe en el esquema para una futura persistencia,
    # pero el job actual no la escribe (no hace falta para calcular el
    # score, que se recalcula desde cero en cada corrida).
    price_history: list[dict] = []
    try:
        weekly = YFinanceDataSource().get_weekly_prices(symbol.upper(), lookback_weeks=52)
        price_history = [
            {"date": idx.date().isoformat(), "close": float(row["Close"]), "volume": float(row["Volume"])}
            for idx, row in weekly.iterrows()
        ]
    except Exception:
        pass  # el detalle sigue siendo útil sin el gráfico si yfinance falla puntualmente

    return OpportunityDetailSchema(**base.model_dump(), price_history=price_history)
