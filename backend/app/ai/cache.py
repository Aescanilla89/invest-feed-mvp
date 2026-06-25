"""Cache de explicaciones por ticker/día/score: si el combined_score de
hoy es igual al de la última corrida con explicación para ese ticker, se
reutiliza el texto sin llamar a la API de Claude. Esto es lo que evita
gastar dinero regenerando una explicación que diría lo mismo."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.ai.explainer import ClaudeExplainer, ExplanationError
from app.models.orm import Explanation, Ticker
from app.screener.canslim import CriterionResult
from app.screener.weinstein import WeinsteinResult
from datetime import date

logger = logging.getLogger("ai.cache")


def get_or_create_explanation(
    db: Session,
    ticker: Ticker,
    run_date: date,
    combined_score: int,
    weinstein: WeinsteinResult,
    criteria: dict[str, CriterionResult],
    explainer: ClaudeExplainer,
) -> Explanation | None:
    existing_today = db.query(Explanation).filter_by(ticker_id=ticker.id, run_date=run_date).one_or_none()
    if existing_today is not None:
        return existing_today

    last = (
        db.query(Explanation)
        .filter(Explanation.ticker_id == ticker.id, Explanation.run_date < run_date)
        .order_by(Explanation.run_date.desc())
        .first()
    )
    if last is not None and last.combined_score_at_generation == combined_score:
        logger.info("%s: score sin cambios (%d), reutilizando explicación del %s", ticker.symbol, combined_score, last.run_date)
        reused = Explanation(
            ticker_id=ticker.id,
            run_date=run_date,
            combined_score_at_generation=combined_score,
            text=last.text,
            model_used=last.model_used,
        )
        db.add(reused)
        db.flush()
        return reused

    try:
        text = explainer.generate(ticker.symbol, ticker.name, ticker.sector, combined_score, weinstein, criteria)
    except ExplanationError as exc:
        logger.warning("No se pudo generar explicación para %s: %s", ticker.symbol, exc)
        return None

    new_explanation = Explanation(
        ticker_id=ticker.id,
        run_date=run_date,
        combined_score_at_generation=combined_score,
        text=text,
        model_used=explainer.model,
    )
    db.add(new_explanation)
    db.flush()
    return new_explanation
