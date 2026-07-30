"""Job diario: mantiene la cartera pública de picks (social proof) -- ver
PortfolioPosition en app/models/orm.py. Se ejecuta después de run_screener
en cada corrida (mismo run_date, misma foto de Opportunity/PriceSnapshot).

Entrada (una vez al día, por método, solo si el top-1 de ese método
cumple su umbral "excepcional" en la corrida ANTERIOR, `signal_date`):
  - early_stage2: Weinstein Stage 2 recién confirmado (<=6 semanas) Y
    signal_type == "both" (CAN SLIM completo también en verde) -- la
    configuración más sólida del método.
  - minervini / berkshire: el top-1 por score de ese método tiene
    score == 100 (TODOS los sub-criterios en verde, no solo el umbral
    de "passed" que exige la pestaña normal).
  - lynch / dividendos: el top-1 por score de ese método tiene
    passed == True (son pasa/no-pasa único; no hay umbral más estricto
    posible que ese).

La señal solo se confirma con el cierre de `signal_date`, así que la
compra se ejecuta a la apertura del día hábil siguiente (`entry_date`,
normalmente el `target_date` de esta corrida) -- nunca al mismo cierre
que disparó la señal. Esto evita look-ahead bias: el precio de entrada
es siempre uno que un trader real podría haber ejecutado después de
conocer la señal.

Un ticker con una posición abierta (de cualquier método) no genera una
segunda entrada aunque vuelva a salir en el top-1 de otro método el
mismo día o un día distinto.

Cada posición de early_stage2 genera (o reutiliza, vía ai/cache.py) su
propia explicación AI en `signal_date`, sin depender de si ese ticker
entró en el top-N por combined_score que run_screener explica para el
feed. Las posiciones de los otros 4 métodos NO usan el narrador AI: su
"porqué" es el `details` factual que ya calcula cada estrategia
(app/screener/strategies.py) -- describir ahí el momentum Weinstein en
vez de las métricas de calidad/GARP/dividendo reales sería una
explicación técnicamente cierta pero equivocada para el pick.

Salida: cada método sale por la ruptura de SU PROPIA tesis (ver
_exit_signal) -- early_stage2 cuando el ticker deja Weinstein Stage 2;
minervini/lynch/berkshire/dividendos cuando su propia estrategia deja de
pasar (`passed is False` en app/screener/strategies.py), no por un cambio
de Stage de Weinstein ajeno a su tesis de PEG/calidad/dividendo/trend-
template. La ruptura se detecta con el cierre de `exit_signal_date`, y la
venta se ejecuta a la apertura del día hábil siguiente (`exit_date`) --
mismo criterio anti-look-ahead que la entrada. El retorno final del
ticker y del S&P 500 se fijan en ese mismo `exit_date`.

Uso manual:
    python -m app.jobs.update_portfolio
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.ai import cache as ai_cache
from app.ai.explainer import ClaudeExplainer, ExplanationError
from app.core.db import SessionLocal, init_db
from app.jobs.run_screener import BENCHMARK_SYMBOL
from app.models.orm import Opportunity, PortfolioPosition, PriceSnapshot, Ticker
from app.screener.canslim import CriterionResult
from app.screener.weinstein import WeinsteinResult

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
    """Réplica de _parse_strategies en api/routes/opportunities.py: la columna
    JSON puede llegar como dict ya deserializado o como string crudo según el
    driver/dialecto, nunca asumir un tipo."""
    raw = opp.strategies
    if not raw:
        return None
    if isinstance(raw, str):
        import json as _json
        try:
            raw = _json.loads(raw)
        except Exception:
            return None
    if not isinstance(raw, dict):
        return None
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


def _exit_signal(latest_opp: Opportunity, method: str) -> str | None:
    """Determina si `latest_opp` dispara la salida de una posición de `method`,
    devolviendo el `exit_reason` o None si sigue en pie. Cada método sale por
    la ruptura de SU PROPIA tesis, no todos por Weinstein:

    - early_stage2 es literalmente el método Weinstein -- sale cuando el
      ticker deja Stage 2 (comportamiento original).
    - minervini/lynch/berkshire/dividendos son estrategias de fundamentales/
      trend-template con su propio pasa/no-pasa (app/screener/strategies.py).
      Atarlas a una ruptura de Weinstein Stage 2 (un cambio técnico de corto
      plazo, no relacionado con su tesis de PEG/calidad/dividendo) generaba
      entradas y salidas cada ~2 semanas en el mismo ticker sin ganar ni
      perder nada en conjunto -- puro ruido. Ahora salen cuando SU estrategia
      dejar de pasar (`passed is False`); si el dato no es verificable
      (`passed is None`) se mantiene la posición, igual que en el resto del
      screener nunca se trata "sin datos" como señal negativa.
    """
    if method == _EARLY_STAGE2:
        if latest_opp.weinstein_stage != 2:
            return f"weinstein_stage_{latest_opp.weinstein_stage}"
        return None

    result = _strategy_result(latest_opp, method)
    if result is not None and result.get("passed") is False:
        return f"{method}_no_longer_passes"
    return None


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


def _open_price_on(db: Session, ticker_id: int, exact_date: date) -> float | None:
    """Apertura de `exact_date` exacto -- si no hay snapshot para ese día concreto
    (aún no ha llegado el precio), devuelve None y la entrada/salida se pospone
    al siguiente run en vez de usar un precio de otro día por error."""
    row = (
        db.query(PriceSnapshot.open)
        .filter(PriceSnapshot.ticker_id == ticker_id, PriceSnapshot.date == exact_date)
        .one_or_none()
    )
    return float(row[0]) if row else None


def _open_price_after(db: Session, ticker_id: int, after: date) -> tuple[date, float] | None:
    """Primera apertura disponible estrictamente después de `after`. Se usa para
    ejecutar salidas al día hábil siguiente a la detección, igual que las entradas."""
    row = (
        db.query(PriceSnapshot.date, PriceSnapshot.open)
        .filter(PriceSnapshot.ticker_id == ticker_id, PriceSnapshot.date > after)
        .order_by(PriceSnapshot.date.asc())
        .first()
    )
    return (row[0], float(row[1])) if row else None


def _ensure_explanation(db: Session, explainer: ClaudeExplainer | None, opp: Opportunity, ticker: Ticker) -> None:
    """Genera (o reutiliza) la explicación AI de `opp` para que la cartera pública
    siempre tenga un "por qué" -- independiente de si este ticker entró en el
    top-N por combined_score que run_screener explica para el feed general."""
    if explainer is None:
        return
    weinstein = WeinsteinResult(
        stage=opp.weinstein_stage,
        weeks_in_stage=opp.weeks_in_stage,
        ma_slope_pct=opp.weinstein_ma_slope_pct,
        relative_volume=opp.weinstein_relative_volume,
        is_transition_1_to_2=opp.weinstein_transition,
        rsi=opp.weinstein_rsi,
    )
    criteria = {k: CriterionResult(v["value"], v["detail"]) for k, v in (opp.canslim_criteria or {}).items()}
    ai_cache.get_or_create_explanation(
        db, ticker, opp.run_date, opp.combined_score, weinstein, criteria, explainer,
        signal_type=_compute_signal_type(opp),
    )
    db.commit()


def _prior_run_date(db: Session, before: date) -> date | None:
    return (
        db.query(Opportunity.run_date)
        .filter(Opportunity.run_date < before)
        .order_by(Opportunity.run_date.desc())
        .limit(1)
        .scalar()
    )


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

        # 1. Cerrar posiciones cuya propia tesis (no necesariamente Weinstein,
        #    ver _exit_signal) ya no se sostiene. Misma lógica anti-look-ahead
        #    que la entrada, en dos fases: se detecta la ruptura el día de
        #    `exit_signal_date` (con su cierre), y se ejecuta la venta a la
        #    primera apertura disponible después de esa fecha -- nunca al
        #    mismo cierre que confirmó la ruptura. Si esa apertura aún no
        #    existe, la posición queda pendiente y se reintenta en el próximo
        #    run (sin volver a re-detectar).
        for pos in db.query(PortfolioPosition).filter_by(status="open").all():
            if pos.exit_signal_date is None:
                latest_opp = (
                    db.query(Opportunity)
                    .filter(Opportunity.ticker_id == pos.ticker_id, Opportunity.run_date <= target_date)
                    .order_by(Opportunity.run_date.desc())
                    .first()
                )
                if latest_opp is None:
                    continue
                exit_reason = _exit_signal(latest_opp, pos.method)
                if exit_reason is None:
                    continue
                pos.exit_signal_date = latest_opp.run_date
                pos.exit_reason = exit_reason
                logger.info("Posición %s (ticker_id=%s) disparó salida (%s) el %s, pendiente de ejecutar", pos.method, pos.ticker_id, exit_reason, latest_opp.run_date)

            exit_row = _open_price_after(db, pos.ticker_id, pos.exit_signal_date)
            if exit_row is None:
                continue
            exit_date, exit_price = exit_row
            exit_spy_price = _open_price_on(db, spy_ticker.id, exit_date)
            if exit_spy_price is None:
                logger.warning("Ticker_id %s: sin apertura de SPY en %s para cerrar, se pospone", pos.ticker_id, exit_date)
                continue
            pos.status = "closed"
            pos.exit_date = exit_date
            pos.exit_price = exit_price
            pos.exit_spy_price = exit_spy_price
            stats["closed"] += 1
            logger.info("Cerrada posición %s (ticker_id=%s): señal %s, salida %.2f (apertura %s)", pos.method, pos.ticker_id, pos.exit_signal_date, exit_price, exit_date)

        # 2. Abrir nuevas posiciones para el top-1 "excepcional" detectado en la
        #    corrida ANTERIOR (signal_date) -- la señal solo se confirma con el
        #    cierre de ese día, así que la compra se ejecuta a la apertura de
        #    HOY (target_date), el primer precio realmente operable. Evita
        #    look-ahead bias: nunca se "compra" al mismo cierre que generó la señal.
        signal_date = _prior_run_date(db, target_date)
        if signal_date is None:
            logger.info("Sin corrida previa a %s todavía, no hay señales que promocionar", target_date)
        else:
            signal_opps = db.query(Opportunity).filter_by(run_date=signal_date).all()
            tickers_with_open = {
                row[0] for row in db.query(PortfolioPosition.ticker_id).filter_by(status="open").all()
            }
            spy_entry_price = _open_price_on(db, spy_ticker.id, target_date)
            try:
                explainer = ClaudeExplainer()
            except ExplanationError as exc:
                logger.warning("Generación de explicaciones desactivada: %s", exc)
                explainer = None

            for method in (_EARLY_STAGE2, *_STRATEGY_METHODS):
                top = _pick_top_for_method(signal_opps, method)
                if top is None or not _is_exceptional(top, method):
                    continue
                if top.ticker_id in tickers_with_open:
                    continue
                entry_price = _open_price_on(db, top.ticker_id, target_date)
                if entry_price is None or spy_entry_price is None:
                    logger.warning(
                        "%s: sin apertura del %s (día siguiente a la señal del %s) para ticker_id=%s, se pospone",
                        method, target_date, signal_date, top.ticker_id,
                    )
                    continue
                db.add(PortfolioPosition(
                    ticker_id=top.ticker_id,
                    method=method,
                    status="open",
                    signal_date=signal_date,
                    entry_date=target_date,
                    entry_price=entry_price,
                    entry_spy_price=spy_entry_price,
                ))
                tickers_with_open.add(top.ticker_id)
                stats["opened"] += 1
                logger.info(
                    "Nueva posición %s: ticker_id=%s señal %s, entrada %.2f (apertura %s)",
                    method, top.ticker_id, signal_date, entry_price, target_date,
                )
                # Solo early_stage2 se explica con el narrador AI de Weinstein+CAN
                # SLIM -- es literalmente su criterio. Los otros 4 métodos ya
                # tienen su propio "details" factual (ROE, PEG, payout...) en
                # Opportunity.strategies[method], que es el "porqué" correcto
                # y no requiere ninguna llamada a la API de Claude.
                if method == _EARLY_STAGE2:
                    _ensure_explanation(db, explainer, top, top.ticker)

        db.commit()
        logger.info("update_portfolio completado: %s", stats)
        return stats
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(run())
