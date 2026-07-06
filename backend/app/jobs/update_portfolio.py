"""Job diario: mantiene la cartera pública de picks (social proof) -- ver
PortfolioPosition en app/models/orm.py. Se ejecuta después de run_screener
en cada corrida (mismo run_date, misma foto de Opportunity/PriceSnapshot).

Entrada (una vez al día, por método, solo si el top-1 de ese método
cumple su umbral "excepcional"):
  - early_stage2: Weinstein Stage 2 recién confirmado (<=6 semanas) Y
    signal_type == "both" (CAN SLIM completo también en verde) -- la
    configuración más sólida del método.
  - minervini / berkshire: el top-1 por score de ese método tiene
    score == 100 (TODOS los sub-criterios en verde, no solo el umbral
    de "passed" que exige la pestaña normal).
  - lynch / dividendos: el top-1 por score de ese método tiene
    passed == True (son pasa/no-pasa único; no hay umbral más estricto
    posible que ese).

Un ticker con una posición abierta (de cualquier método) no genera una
segunda entrada aunque vuelva a salir en el top-1 de otro método el
mismo día o un día distinto.

Salida: la posición se cierra automáticamente el día que el ticker deja
de estar en Weinstein Stage 2 (rompe a Stage 3 o Stage 4), fijando el
retorno final tanto del ticker como del S&P 500 en el mismo periodo.

Uso manual:
    python -m app.jobs.update_portfolio
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.core.db import SessionLocal, init_db
from app.jobs.run_screener import BENCHMARK_SYMBOL
from app.models.orm import Opportunity, PortfolioPosition, PriceSnapshot, Ticker

logger = logging.getLogger("update_portfolio")

_STRATEGY_METHODS = ("minervini", "lynch", "berkshire", "dividendos")
_EARLY_STAGE2 = "early_stage2"
_EARLY_STAGE2_MAX_WEEKS = 6
_WEINSTEIN_MAX_WEEKS = 8  # mismo umbral que _compute_signal_type en opportunities.py


def _compute_signal_type(opp: Opportunity) -> str | None:
    """Réplica de la lógica en api/routes/opportunities.py -- se duplica aquí
    (en vez de importar de un módulo de rutas) para no acoplar el job HTTP-API."""
    is_weinstein = bool(opp.weinstein_transition) and opp.weeks_in_stage <= _WEINSTEIN_MAX_WEEKS
    criteria = opp.canslim_criteria or {}
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


def _strategy_result(opp: Opportunity, method: str) -> dict | None:
    raw = opp.strategies or {}
    data = raw.get(method)
    return data if isinstance(data, dict) else None


def _is_exceptional(opp: Opportunity, method: str) -> bool:
    """Umbral "excepcional" por método -- ver docstring del módulo."""
    if method == _EARLY_STAGE2:
        return _compute_signal_type(opp) == "both"
    result = _strategy_result(opp, method)
    if result is None:
        return False
    if method in ("minervini", "berkshire"):
        return result.get("score") == 100
    return result.get("passed") is True


def _pick_top_for_method(opportunities: list[Opportunity], method: str) -> Opportunity | None:
    if method == _EARLY_STAGE2:
        candidates = [
            o for o in opportunities
            if o.weinstein_stage == 2 and o.weeks_in_stage <= _EARLY_STAGE2_MAX_WEEKS
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda o: (o.weeks_in_stage, -o.combined_score))
        return candidates[0]

    scored = [
        (o, r) for o in opportunities
        if (r := _strategy_result(o, method)) is not None and r.get("score") is not None
    ]
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[1]["score"], reverse=True)
    return scored[0][0]


def _latest_price(db: Session, ticker_id: int, on_or_before: date) -> float | None:
    row = (
        db.query(PriceSnapshot.close)
        .filter(PriceSnapshot.ticker_id == ticker_id, PriceSnapshot.date <= on_or_before)
        .order_by(PriceSnapshot.date.desc())
        .first()
    )
    return float(row[0]) if row else None


def run(run_date: date | None = None) -> dict:
    init_db()
    db = SessionLocal()
    try:
        target_date = run_date or db.query(Opportunity.run_date).order_by(Opportunity.run_date.desc()).limit(1).scalar()
        if target_date is None:
            logger.warning("Sin corridas de Opportunity en BD, nada que hacer")
            return {"opened": 0, "closed": 0}

        spy_ticker = db.query(Ticker).filter_by(symbol=BENCHMARK_SYMBOL).one_or_none()
        if spy_ticker is None:
            logger.warning("Sin ticker benchmark %s en BD, no se puede abrir/cerrar posiciones", BENCHMARK_SYMBOL)
            return {"opened": 0, "closed": 0}

        stats = {"opened": 0, "closed": 0}

        # 1. Cerrar posiciones que ya no están en Weinstein Stage 2
        for pos in db.query(PortfolioPosition).filter_by(status="open").all():
            latest_opp = (
                db.query(Opportunity)
                .filter(Opportunity.ticker_id == pos.ticker_id, Opportunity.run_date <= target_date)
                .order_by(Opportunity.run_date.desc())
                .first()
            )
            if latest_opp is None or latest_opp.weinstein_stage == 2:
                continue
            exit_price = _latest_price(db, pos.ticker_id, latest_opp.run_date)
            exit_spy_price = _latest_price(db, spy_ticker.id, latest_opp.run_date)
            if exit_price is None or exit_spy_price is None:
                logger.warning("Ticker_id %s salió de Stage 2 pero sin precio para cerrar, se omite", pos.ticker_id)
                continue
            pos.status = "closed"
            pos.exit_date = latest_opp.run_date
            pos.exit_price = exit_price
            pos.exit_spy_price = exit_spy_price
            pos.exit_reason = f"weinstein_stage_{latest_opp.weinstein_stage}"
            stats["closed"] += 1
            logger.info("Cerrada posición %s (ticker_id=%s): Stage -> %s", pos.method, pos.ticker_id, latest_opp.weinstein_stage)

        # 2. Abrir nuevas posiciones para el top-1 "excepcional" de cada método
        todays_opps = db.query(Opportunity).filter_by(run_date=target_date).all()
        tickers_with_open = {
            row[0] for row in db.query(PortfolioPosition.ticker_id).filter_by(status="open").all()
        }
        spy_entry_price = _latest_price(db, spy_ticker.id, target_date)

        for method in (_EARLY_STAGE2, *_STRATEGY_METHODS):
            top = _pick_top_for_method(todays_opps, method)
            if top is None or not _is_exceptional(top, method):
                continue
            if top.ticker_id in tickers_with_open:
                continue
            entry_price = _latest_price(db, top.ticker_id, target_date)
            if entry_price is None or spy_entry_price is None:
                logger.warning("%s: sin precio de entrada para ticker_id=%s, se omite", method, top.ticker_id)
                continue
            db.add(PortfolioPosition(
                ticker_id=top.ticker_id,
                method=method,
                status="open",
                entry_date=target_date,
                entry_price=entry_price,
                entry_spy_price=spy_entry_price,
            ))
            tickers_with_open.add(top.ticker_id)
            stats["opened"] += 1
            logger.info("Nueva posición %s: ticker_id=%s a %.2f", method, top.ticker_id, entry_price)

        db.commit()
        logger.info("update_portfolio completado: %s", stats)
        return stats
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(run())
