"""Endpoints de catalizadores de inversión.

GET /api/catalysts — devuelve catalizadores detectados en los últimos N días,
enriquecidos con el score de oportunidad si el ticker está en nuestro universo.
"""
from __future__ import annotations

import time
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.orm import Catalyst, Explanation, Opportunity, Ticker
from app.models.schemas import CatalystSchema, FearGreedPointSchema, FearGreedSchema
from app.screener.fear_greed import get_fear_greed_index

router = APIRouter(prefix="/catalysts", tags=["catalysts"])

# Caché en memoria de 30 min -- el índice no se mueve más rápido que eso en
# la práctica, y sin esto CADA visita a la home dispararía una petición a
# CNN (que además bloquea con 418 si detecta demasiado tráfico repetido
# desde la misma IP en poco tiempo). WEB_CONCURRENCY=1 en producción, así
# que un dict a nivel de módulo es seguro sin locks.
_FEAR_GREED_TTL_SECONDS = 1800
_fear_greed_cache: dict[str, object] = {}

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


@router.get("/fear-greed", response_model=FearGreedSchema)
def get_fear_greed() -> FearGreedSchema:
    """Fear & Greed Index de CNN (0=miedo extremo, 100=codicia extrema).
    Cacheado 30 min en memoria -- ver _FEAR_GREED_TTL_SECONDS."""
    cached = _fear_greed_cache.get("data")
    cached_at = _fear_greed_cache.get("at")
    if cached is not None and isinstance(cached_at, float) and time.time() - cached_at < _FEAR_GREED_TTL_SECONDS:
        return cached  # type: ignore[return-value]

    try:
        data = get_fear_greed_index()
    except Exception as exc:
        # Si hay algo cacheado (aunque haya caducado el TTL), mejor servir
        # ese dato algo viejo que un error duro -- CNN puede bloquear
        # puntualmente por tráfico y el índice no cambia tan rápido como
        # para que unos minutos de más importen.
        if cached is not None:
            return cached  # type: ignore[return-value]
        raise HTTPException(status_code=502, detail=f"No se pudo obtener el Fear & Greed Index: {exc}") from exc

    schema = FearGreedSchema(
        score=data.score,
        rating=data.rating,
        timestamp=data.timestamp,
        previous_close=data.previous_close,
        previous_1_week=data.previous_1_week,
        previous_1_month=data.previous_1_month,
        previous_1_year=data.previous_1_year,
        history=[FearGreedPointSchema(date=p.date, score=p.score, rating=p.rating) for p in data.history],
    )
    _fear_greed_cache["data"] = schema
    _fear_greed_cache["at"] = time.time()
    return schema
