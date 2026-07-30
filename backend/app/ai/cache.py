"""Cache de explicaciones por ticker/día/score: si el combined_score de
hoy es igual al de la última corrida con explicación para ese ticker, se
reutiliza el texto sin llamar a la API de Claude. Esto es lo que evita
gastar dinero regenerando una explicación que diría lo mismo."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.ai.explainer import ClaudeExplainer, ExplanationError
from app.ai.prompts import CatalystContext
from app.models.orm import Catalyst, Explanation, Ticker
from app.screener.canslim import CriterionResult
from app.screener.weinstein import WeinsteinResult
from datetime import date, timedelta

logger = logging.getLogger("ai.cache")

# Earnings quedan relevantes unos días antes/después del evento; insider buys
# se consideran una señal fresca durante un par de semanas. 14 días cubre
# ambos sin arrastrar catalizadores ya obsoletos a la explicación.
_CATALYST_LOOKBACK_DAYS = 14


def _get_recent_catalysts(db: Session, ticker_id: int, today: date) -> list[Catalyst]:
    since = today - timedelta(days=_CATALYST_LOOKBACK_DAYS)
    return (
        db.query(Catalyst)
        .filter(Catalyst.ticker_id == ticker_id, Catalyst.detected_date >= since)
        .order_by(Catalyst.detected_date.desc())
        .all()
    )


def get_or_create_explanation(
    db: Session,
    ticker: Ticker,
    run_date: date,
    combined_score: int,
    weinstein: WeinsteinResult,
    criteria: dict[str, CriterionResult],
    explainer: ClaudeExplainer,
    signal_type: str | None = None,
) -> Explanation | None:
    existing_today = db.query(Explanation).filter_by(ticker_id=ticker.id, run_date=run_date).one_or_none()
    if existing_today is not None:
        return existing_today

    catalysts = _get_recent_catalysts(db, ticker.id, run_date)
    catalyst_ids = ",".join(str(c.id) for c in sorted(catalysts, key=lambda c: c.id))

    last = (
        db.query(Explanation)
        .filter(Explanation.ticker_id == ticker.id, Explanation.run_date < run_date)
        .order_by(Explanation.run_date.desc())
        .first()
    )
    if (
        last is not None
        and last.combined_score_at_generation == combined_score
        and (last.catalyst_ids_at_generation or "") == catalyst_ids
    ):
        logger.info("%s: score y catalizadores sin cambios, reutilizando explicación del %s", ticker.symbol, last.run_date)
        reused = Explanation(
            ticker_id=ticker.id,
            run_date=run_date,
            combined_score_at_generation=combined_score,
            text=last.text,
            model_used=last.model_used,
            catalyst_ids_at_generation=catalyst_ids,
        )
        db.add(reused)
        db.flush()
        return reused

    catalyst_context = [
        CatalystContext(catalyst_type=c.catalyst_type, title=c.title, description=c.description)
        for c in catalysts
    ]

    try:
        text = explainer.generate(
            ticker.symbol, ticker.name, ticker.sector, combined_score, weinstein, criteria,
            signal_type, catalyst_context,
        )
    except ExplanationError as exc:
        logger.warning("No se pudo generar explicación para %s: %s", ticker.symbol, exc)
        return None

    new_explanation = Explanation(
        ticker_id=ticker.id,
        run_date=run_date,
        combined_score_at_generation=combined_score,
        text=text,
        model_used=explainer.model,
        catalyst_ids_at_generation=catalyst_ids,
    )
    db.add(new_explanation)
    db.flush()
    return new_explanation
