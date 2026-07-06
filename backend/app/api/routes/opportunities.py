from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.orm import Explanation, Opportunity, PriceSnapshot, Ticker
from app.models.schemas import CanslimSchema, OpportunityDetailSchema, OpportunitySchema, StrategyResultSchema, WeinsteinSchema

_STRATEGY_NAMES = {"minervini", "lynch", "berkshire", "dividendos"}
_EARLY_STAGE2 = "early_stage2"
_EARLY_STAGE2_MAX_WEEKS = 6  # ventana de "entrada temprana": recién confirmado Stage 2

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _latest_run_date(db: Session) -> date | None:
    return db.query(func.max(Opportunity.run_date)).scalar()


_WEINSTEIN_MAX_WEEKS = 8  # entrada fresca: máximo 8 semanas desde el cruce 1→2


def _compute_signal_type(opp: Opportunity) -> str | None:
    """Determina el tipo de señal de entrada según criterios estrictos:
    - weinstein: Stage 2 + transición 1→2 con volumen confirmado en <= 8 semanas
    - canslim: criterio N en verde (rotura ATH con volumen) + TODOS los criterios
               verificables en verde
    - both: ambas condiciones simultáneas
    """
    is_weinstein = bool(opp.weinstein_transition) and opp.weeks_in_stage <= _WEINSTEIN_MAX_WEEKS

    criteria = opp.canslim_criteria
    n_passes = criteria.get("N", {}).get("value") is True
    all_verifiable_pass = all(
        v["value"] is True
        for v in criteria.values()
        if v.get("value") is not None
    )
    is_canslim = n_passes and all_verifiable_pass

    if is_weinstein and is_canslim:
        return "both"
    if is_weinstein:
        return "weinstein"
    if is_canslim:
        return "canslim"
    return None


def _strategies_to_schema(raw: dict) -> dict[str, StrategyResultSchema]:
    result = {}
    for name, data in (raw or {}).items():
        if isinstance(data, dict):
            result[name] = StrategyResultSchema(
                passed=data.get("passed"),
                score=data.get("score"),
                details=data.get("details", ""),
            )
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
    raw = _parse_strategies(opp)
    return bool((raw.get(strategy) or {}).get("passed"))


def _to_schema(opp: Opportunity, ticker: Ticker, explanation_text: str | None) -> OpportunitySchema:
    verifiable = opp.canslim_verifiable_count
    passed = opp.canslim_passed_count
    raw_strategies = _parse_strategies(opp)
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
            rsi=opp.weinstein_rsi if opp.weinstein_rsi is not None else 50.0,
        ),
        canslim=CanslimSchema(
            criteria=opp.canslim_criteria,
            score=f"{passed}/{verifiable} verificables",
        ),
        explanation=explanation_text,
        last_updated=opp.run_date,
        signal_type=_compute_signal_type(opp),
        strategies=_strategies_to_schema(raw_strategies),
    )


@router.get("", response_model=list[OpportunitySchema])
def list_opportunities(
    limit: int = Query(10, ge=1, le=100),
    min_score: int = Query(0, ge=0, le=100),
    risk: str | None = Query(None, pattern="^(bajo|medio|alto)$"),
    sector: str | None = None,
    sort: str = Query("score", pattern="^(score|stage)$"),
    strategy: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[OpportunitySchema]:
    run_date = _latest_run_date(db)
    if run_date is None:
        return []

    # Cuando se filtra por estrategia específica, no aplicar min_score
    # (las estrategias tienen su propio score, independiente del combined_score Weinstein+CAN SLIM)
    apply_score_filter = not (strategy and (strategy in _STRATEGY_NAMES or strategy == _EARLY_STAGE2))

    query = (
        db.query(Opportunity, Ticker)
        .join(Ticker, Opportunity.ticker_id == Ticker.id)
        .filter(Opportunity.run_date == run_date)
    )
    if apply_score_filter:
        query = query.filter(Opportunity.combined_score >= min_score)
    if risk:
        query = query.filter(Opportunity.risk_bucket == risk)
    if sector:
        query = query.filter(Ticker.sector == sector)

    if sort == "score":
        query = query.order_by(Opportunity.combined_score.desc())
    else:
        query = query.order_by(Opportunity.weinstein_stage.asc(), Opportunity.combined_score.desc())

    rows = query.all()

    # Filtro por señal activa según la estrategia seleccionada
    if strategy == _EARLY_STAGE2:
        # No exige el bonus de transición (volumen 2x + RSI>50): el objetivo es
        # detectar actividad temprana de Stage 2 aunque no cumpla ese umbral
        # estricto, sin descartar la señal ya existente en "Destacadas".
        rows = [
            (opp, ticker) for opp, ticker in rows
            if opp.weinstein_stage == 2 and opp.weeks_in_stage <= _EARLY_STAGE2_MAX_WEEKS
        ]
        rows.sort(key=lambda pair: (pair[0].weeks_in_stage, -pair[0].combined_score))
    elif strategy and strategy in _STRATEGY_NAMES:
        rows = [(opp, ticker) for opp, ticker in rows if _has_strategy_signal(opp, strategy)]
    else:
        # Vista por defecto: señales Weinstein + CAN SLIM, más cualquiera que pase al menos una estrategia
        rows = [
            (opp, ticker) for opp, ticker in rows
            if _compute_signal_type(opp) is not None
            or any(_has_strategy_signal(opp, s) for s in _STRATEGY_NAMES)
        ]

    rows = rows[:limit]

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
        raise HTTPException(status_code=404, detail=f"Sin datos de screener para {symbol} todavia")

    explanation = (
        db.query(Explanation)
        .filter(Explanation.ticker_id == ticker.id, Explanation.run_date == opp.run_date)
        .one_or_none()
    )

    base = _to_schema(opp, ticker, explanation.text if explanation else None)

    # Historial de precios desde price_snapshots (acumulado por el screener diario)
    # 130 semanas (~2.5 años): suficiente para mostrar MA30 con contexto histórico
    snapshots = (
        db.query(PriceSnapshot)
        .filter(PriceSnapshot.ticker_id == ticker.id)
        .order_by(PriceSnapshot.date.desc())
        .limit(130)
        .all()
    )
    snapshots = list(reversed(snapshots))
    price_history = [
        {
            "date": s.date.isoformat(),
            "open": s.open,
            "high": s.high,
            "low": s.low,
            "close": s.close,
            "volume": s.volume,
        }
        for s in snapshots
    ]

    return OpportunityDetailSchema(**base.model_dump(), price_history=price_history)
