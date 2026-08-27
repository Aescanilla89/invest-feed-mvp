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

Salida: dos stops técnicos distintos según el tipo de estrategia --
- early_stage2 / minervini (momentum puro): ver _exit_signal -- se sale
  cuando el precio cierra por debajo de la media móvil de 30 semanas
  (Stage 1 o 4), nunca en Stage 3 (desaceleración con precio todavía por
  encima de la MA30, no una ruptura real).
- lynch / berkshire / dividendos (tesis de calidad/valor): ver
  _fundamentals_exit_signal -- ruptura de la media móvil de 40 semanas
  (más lenta, da más margen a una tesis de plazo más largo). NO salen
  por dejar de cumplir su propio criterio (probado y revertido, ver
  commit 3e9b737: exigir 7/7 sin margen cortaba ganadoras al primer
  criterio que fallara, p.ej. un RS Rating que cae de 71 a 69).
Ambos exigen 2 semanas CONSECUTIVAS por debajo de su media antes de
confirmar la ruptura (ruido de una sola semana no cuenta). La ruptura
se detecta con el cierre de `exit_signal_date`, y la venta se ejecuta a
la apertura del día hábil siguiente (`exit_date`) -- mismo criterio
anti-look-ahead que la entrada. El retorno final del ticker y del S&P
500 se fijan en ese mismo `exit_date`.

Uso manual:
    python -m app.jobs.update_portfolio
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.ai import cache as ai_cache
from app.ai.explainer import ClaudeExplainer, ExplanationError
from app.core.db import SessionLocal, init_db
from app.jobs.run_screener import BENCHMARK_SYMBOL
from app.models.orm import Opportunity, PortfolioPosition, PriceSnapshot, Ticker
from app.screener.canslim import CriterionResult
from app.screener.weinstein import InsufficientDataError, WeinsteinResult, analyze

logger = logging.getLogger("update_portfolio")

_STRATEGY_METHODS = ("minervini", "lynch", "berkshire", "dividendos")
_EARLY_STAGE2 = "early_stage2"
# Stop de momentum (MA30, ver _exit_signal) vs stop de tesis larga (MA40,
# ver _fundamentals_exit_signal) -- early_stage2/minervini son señales de
# rotura de corto plazo, lynch/berkshire/dividendos son tesis de calidad/
# valor/dividendo que necesitan más margen (ver docstring del módulo).
_MOMENTUM_METHODS = (_EARLY_STAGE2, "minervini")
_EARLY_STAGE2_MAX_WEEKS = 6
_WEINSTEIN_MAX_WEEKS = 8  # mismo umbral que _compute_signal_type en opportunities.py

# Semanas de "enfriamiento" tras un stop-loss antes de permitir que el mismo
# ticker vuelva a entrar (por cualquier método). Sin esto, un ticker que
# cotiza pegado a su MA30 puede entrar/salir varias veces en pocos meses
# (visto en producción: IMMR 6 veces, CLMB 7 veces en lo que va de año) --
# cada ronda es ruido puro, no aporta retorno neto y diluye a los ganadores
# reales en la rentabilidad equiponderada de la cartera.
_REENTRY_COOLDOWN_WEEKS = 4

# Filtro de régimen de mercado (Weinstein / O'Neil: solo comprar roturas
# cuando el índice general también está en tendencia alcista). Sin esto se
# abren posiciones nuevas aunque el S&P 500 esté en techo o en caída, lo que
# va contra la propia lógica del método que se está usando para elegir cada
# pick.
_MARKET_REGIME_OK_STAGES = (2,)


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


def _exit_signal(recent_opps: list[Opportunity]) -> str | None:
    """Determina si las Opportunity más recientes de un ticker (ordenadas
    de más a menos reciente) disparan la salida, devolviendo el
    `exit_reason` o None si sigue en pie.

    Stop-loss dinámico único para las 5 estrategias, al estilo Weinstein:
    se sale cuando el precio cierra por debajo de la media móvil de 30
    semanas (Stage 1 o 4) -- nunca en Stage 3, que es solo desaceleración
    del momentum con el precio TODAVÍA por encima de la MA30, no una
    ruptura real.

    Requiere confirmación de 2 semanas CONSECUTIVAS por debajo de la MA30
    antes de disparar la venta -- una sola semana marginal por debajo de
    la media no es una ruptura real, es ruido. Sin esta confirmación,
    acciones que cotizan pegadas a su MA30 generan churn real: CMCSA entró
    y salió del portfolio 11 veces en un año con el stop de una sola
    semana, sin ganar ni perder nada en conjunto. Con datos insuficientes
    (menos de 2 semanas de histórico para el ticker) se mantiene la
    posición -- nunca se confirma una ruptura con una sola muestra."""
    if len(recent_opps) < 2:
        return None
    latest, prior = recent_opps[0], recent_opps[1]
    if latest.weinstein_stage in (1, 4) and prior.weinstein_stage in (1, 4):
        return f"weinstein_stage_{latest.weinstein_stage}"
    return None


_FUNDAMENTALS_MA_WINDOW_WEEKS = 40


def _closes_below_ma(closes: list[float], window_weeks: int) -> bool | None:
    """Decisión pura: ¿las 2 últimas velas semanales de `closes` (ascendente
    por fecha) cierran por debajo de su media móvil de `window_weeks`
    semanas? None si no hay histórico suficiente para calcular la MA en
    ambas semanas -- no se puede confirmar una ruptura sin datos."""
    if len(closes) < window_weeks + 1:
        return None
    series = pd.Series(closes)
    ma = series.rolling(window_weeks).mean()
    below = series < ma
    if pd.isna(ma.iloc[-1]) or pd.isna(ma.iloc[-2]):
        return None
    return bool(below.iloc[-1]) and bool(below.iloc[-2])


def _fundamentals_exit_signal(db: Session, ticker_id: int, as_of: date) -> tuple[date, str] | None:
    """Stop de las estrategias de tesis larga (lynch/berkshire/dividendos):
    ruptura de la media móvil de 40 semanas (más lenta que la MA30 de
    momentum, da más margen a una tesis de calidad/valor) -- NO salen por
    dejar de cumplir su propio criterio (ver docstring del módulo: probado
    y revertido, cortaba ganadoras al primer sub-criterio que fallara).
    Misma confirmación de 2 semanas consecutivas que el stop de momentum."""
    rows = (
        db.query(PriceSnapshot.date, PriceSnapshot.close)
        .filter(PriceSnapshot.ticker_id == ticker_id, PriceSnapshot.date <= as_of)
        .order_by(PriceSnapshot.date.asc())
        .all()
    )
    if len(rows) < _FUNDAMENTALS_MA_WINDOW_WEEKS + 1:
        return None
    dates = [r[0] for r in rows]
    closes = [float(r[1]) for r in rows]
    if _closes_below_ma(closes, _FUNDAMENTALS_MA_WINDOW_WEEKS) is not True:
        return None
    return dates[-1], "ma40_break"


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


def _tickers_in_cooldown(db: Session, as_of: date) -> set[int]:
    """Tickers que salieron por stop-loss (weinstein_stage_*) en las últimas
    `_REENTRY_COOLDOWN_WEEKS` semanas -- se bloquea su reentrada por
    cualquier método hasta que pase el enfriamiento. Solo aplica a salidas
    por stop, no a cualquier otro motivo de cierre futuro."""
    cutoff = as_of - timedelta(weeks=_REENTRY_COOLDOWN_WEEKS)
    rows = (
        db.query(PortfolioPosition.ticker_id)
        .filter(
            PortfolioPosition.status == "closed",
            PortfolioPosition.exit_reason.like("weinstein_stage_%"),
            PortfolioPosition.exit_date >= cutoff,
            PortfolioPosition.exit_date <= as_of,
        )
        .all()
    )
    return {row[0] for row in rows}


def _market_regime_stage_ok(stage: int) -> bool:
    """Decisión pura: ¿el stage actual del S&P 500 permite abrir posiciones
    nuevas? Solo Stage 2 (avance) -- ver _MARKET_REGIME_OK_STAGES."""
    return stage in _MARKET_REGIME_OK_STAGES


def _market_regime_ok(db: Session, spy_ticker_id: int, as_of: date) -> bool:
    """Régimen de mercado: solo se abren posiciones nuevas si el S&P 500
    también está en Weinstein Stage 2 (avance) en `as_of`. Sin histórico
    suficiente se deja pasar (fail-open) -- no bloquear el arranque en frío
    de una BD nueva por falta de datos, no por señal de mercado real."""
    rows = (
        db.query(PriceSnapshot.date, PriceSnapshot.close, PriceSnapshot.volume)
        .filter(PriceSnapshot.ticker_id == spy_ticker_id, PriceSnapshot.date <= as_of)
        .order_by(PriceSnapshot.date.asc())
        .all()
    )
    if not rows:
        return True
    weekly = pd.DataFrame(rows, columns=["date", "Close", "Volume"]).set_index("date")
    try:
        result = analyze(weekly)
    except InsufficientDataError:
        return True
    return _market_regime_stage_ok(result.stage)


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

        # 1. Cerrar posiciones que rompen el stop-loss dinámico (ver
        #    _exit_signal: 2 semanas consecutivas por debajo de la MA30).
        #    Misma lógica anti-look-ahead que la entrada, en dos fases: se
        #    detecta la ruptura el día de `exit_signal_date` (con su
        #    cierre), y se ejecuta la venta a la primera apertura disponible
        #    después de esa fecha -- nunca al mismo cierre que confirmó la
        #    ruptura. Si esa apertura aún no existe, la posición queda
        #    pendiente y se reintenta en el próximo run (sin volver a
        #    re-detectar).
        for pos in db.query(PortfolioPosition).filter_by(status="open").all():
            if pos.exit_signal_date is None:
                if pos.method in _MOMENTUM_METHODS:
                    recent_opps = (
                        db.query(Opportunity)
                        .filter(Opportunity.ticker_id == pos.ticker_id, Opportunity.run_date <= target_date)
                        .order_by(Opportunity.run_date.desc())
                        .limit(2)
                        .all()
                    )
                    exit_reason = _exit_signal(recent_opps)
                    exit_signal_date = recent_opps[0].run_date if exit_reason else None
                else:
                    fundamentals_exit = _fundamentals_exit_signal(db, pos.ticker_id, target_date)
                    exit_signal_date, exit_reason = fundamentals_exit if fundamentals_exit else (None, None)
                if exit_reason is None:
                    continue
                pos.exit_signal_date = exit_signal_date
                pos.exit_reason = exit_reason
                logger.info("Posición %s (ticker_id=%s) disparó salida (%s) el %s, pendiente de ejecutar", pos.method, pos.ticker_id, exit_reason, exit_signal_date)

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
        elif not _market_regime_ok(db, spy_ticker.id, signal_date):
            logger.info(
                "S&P 500 fuera de Stage 2 en %s, no se abren posiciones nuevas esta corrida "
                "(filtro de régimen de mercado)", signal_date,
            )
        else:
            signal_opps = db.query(Opportunity).filter_by(run_date=signal_date).all()
            tickers_with_open = {
                row[0] for row in db.query(PortfolioPosition.ticker_id).filter_by(status="open").all()
            }
            tickers_cooling_down = _tickers_in_cooldown(db, target_date)
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
                if top.ticker_id in tickers_cooling_down:
                    logger.info(
                        "%s: ticker_id=%s en enfriamiento tras stop-loss reciente, se omite",
                        method, top.ticker_id,
                    )
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
