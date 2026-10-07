"""Endpoints de catalizadores de inversión.

GET /api/catalysts — devuelve catalizadores detectados en los últimos N días,
enriquecidos con el score de oportunidad si el ticker está en nuestro universo.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.orm import Catalyst, Explanation, Opportunity, Ticker
from app.models.schemas import CatalystSchema

router = APIRouter(prefix="/catalysts", tags=["catalysts"])

_SCORE_THRESHOLDS = [
    (85, "oro"),
    (70, "plata"),
    (50, "bronce"),
]


def _classify(score: int | None) -> str | None:
    if score is None:
        return None
    for threshold, label in _SCORE_THRESHOLDS:
        if score >= threshold:
            return label
    return None


@router.get("", response_model=list[CatalystSchema])
def get_catalysts(
    days: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db),
) -> list[CatalystSchema]:
    """Catalizadores detectados en los últimos `days` días, ordenados por score desc."""
    cutoff = date.today() - timedelta(days=days)
    latest_run = db.query(func.max(Opportunity.run_date)).scalar()

    catalysts = (
        db.query(Catalyst)
        .filter(Catalyst.detected_date >= cutoff)
        .order_by(Catalyst.detected_date.desc(), Catalyst.id.desc())
        .all()
    )

    result: list[CatalystSchema] = []
    for cat in catalysts:
        ticker: Ticker | None = cat.ticker
        symbol = ticker.symbol if ticker else None
        company_name = ticker.name if ticker else None
        sector = ticker.sector if ticker else None

        combined_score: int | None = None
        explanation_text: str | None = None

        if ticker and latest_run:
            opp = (
                db.query(Opportunity)
                .filter_by(ticker_id=ticker.id, run_date=latest_run)
                .one_or_none()
            )
            if opp:
                combined_score = opp.combined_score

            exp = (
                db.query(Explanation)
                .filter_by(ticker_id=ticker.id, run_date=latest_run)
                .one_or_none()
            )
            if exp:
                explanation_text = exp.text

        result.append(CatalystSchema(
            id=cat.id,
            ticker=symbol,
            company_name=company_name,
            sector=sector,
            catalyst_type=cat.catalyst_type,
            title=cat.title,
            description=cat.description,
            detected_date=cat.detected_date,
            extra=cat.extra or {},
            combined_score=combined_score,
            classification=_classify(combined_score),
            explanation=explanation_text,
        ))

    # Ordenar: primero los que tienen score (oportunidades), luego eventos
    result.sort(key=lambda c: (c.combined_score is None, -(c.combined_score or 0)))
    return result
