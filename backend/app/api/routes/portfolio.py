"""Cartera pública (social proof): expone las posiciones que abre/cierra
automáticamente app/jobs/update_portfolio.py."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.jobs.run_screener import BENCHMARK_SYMBOL
from app.models.orm import Explanation, Opportunity, PortfolioPosition, PriceSnapshot, Ticker
from app.models.schemas import PortfolioPositionSchema, PortfolioSchema, PortfolioStatsSchema

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

_EARLY_STAGE2 = "early_stage2"
_MEAN_REVERSION = "mean_reversion"
# early_stage2 y mean_reversion se explican con el narrador AI (ver
# update_portfolio._ensure_explanation) -- ninguno de los dos tiene un
# "details" factual propio en Opportunity.strategies.
_AI_EXPLAINED_METHODS = (_EARLY_STAGE2, _MEAN_REVERSION)

# Position sizing por volatilidad: cada posición pesa según el inverso de su
# ATR%(14 semanas) en el momento de la entrada (más volátil = menos peso,
# para que cada posición aporte un riesgo similar a la cartera en vez de un
# capital idéntico), normalizado para que el peso medio siga siendo 1 y
# limitado a [0.5x, 2.0x] para que ni una acción ultra-tranquila domine ni
# una ultra-volátil quede casi a cero.
_ATR_WINDOW_WEEKS = 14
_WEIGHT_CAP_MIN = 0.5
_WEIGHT_CAP_MAX = 2.0


def _load_price_history(db: Session, ticker_ids: set[int]) -> dict[int, list[tuple[date, float, float, float]]]:
    """Trae TODO el histórico de precio (date, high, low, close) de todos los
    `ticker_ids` en UNA sola consulta, agrupado en memoria -- antes _atr_pct y
    _price_on_or_after hacían una consulta por ticker dentro de un bucle
    (visto en producción: ~90 tickers distintos en la cartera == ~90
    round-trips de red a Supabase == /api/portfolio tardando >10s). La
    cadencia es semanal, así que el volumen total por ticker es pequeño --
    cabe de sobra en memoria, y una sola consulta grande es muchísimo más
    barata en latencia de red que N consultas pequeñas."""
    if not ticker_ids:
        return {}
    rows = (
        db.query(PriceSnapshot.ticker_id, PriceSnapshot.date, PriceSnapshot.high, PriceSnapshot.low, PriceSnapshot.close)
        .filter(PriceSnapshot.ticker_id.in_(ticker_ids))
        .order_by(PriceSnapshot.ticker_id, PriceSnapshot.date.asc())
        .all()
    )
    result: dict[int, list[tuple[date, float, float, float]]] = {}
    for tid, d, h, l, c in rows:
        result.setdefault(tid, []).append((d, float(h), float(l), float(c)))
    return result


def _atr_pct(history_by_ticker: dict[int, list[tuple[date, float, float, float]]], ticker_id: int, as_of: date) -> float | None:
    """ATR%(14 semanas) = ATR / Close, con velas <= as_of -- nunca posteriores,
    para no usar volatilidad "futura" que un trader real no habría visto al
    abrir la posición. None si no hay histórico suficiente. Opera sobre el
    histórico ya cargado en memoria (ver _load_price_history), no consulta la BD."""
    rows = [r for r in history_by_ticker.get(ticker_id, []) if r[0] <= as_of]
    if len(rows) < _ATR_WINDOW_WEEKS + 1:
        return None
    highs = [r[1] for r in rows]
    lows = [r[2] for r in rows]
    closes = [r[3] for r in rows]
    true_ranges = [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        for i in range(1, len(rows))
    ]
    atr = sum(true_ranges[-_ATR_WINDOW_WEEKS:]) / _ATR_WINDOW_WEEKS
    last_close = closes[-1]
    return atr / last_close if last_close > 0 else None


def _position_weights(raw_weights: dict[int, float | None]) -> dict[int, float]:
    """Decisión pura: normaliza pesos brutos (1/ATR%, o None si no hay ATR)
    para que la media sea 1 y aplica el cap [0.5x, 2.0x]. Los tickers sin
    ATR disponible reciben el peso medio de los que sí lo tienen (peso
    neutro tras normalizar, fail-open en vez de excluir la posición)."""
    known = [w for w in raw_weights.values() if w is not None]
    fallback = (sum(known) / len(known)) if known else 1.0
    filled = {tid: (w if w is not None else fallback) for tid, w in raw_weights.items()}
    mean_raw = sum(filled.values()) / len(filled) if filled else 1.0
    if mean_raw <= 0:
        return {tid: 1.0 for tid in filled}
    return {
        tid: min(max(w / mean_raw, _WEIGHT_CAP_MIN), _WEIGHT_CAP_MAX)
        for tid, w in filled.items()
    }


def _price_on_or_after(history_by_ticker: dict[int, list[tuple[date, float, float, float]]], ticker_id: int, on_or_after: date) -> float | None:
    """Primer cierre disponible a partir de `on_or_after` (inclusive) -- se
    usa como precio base para calcular la rentabilidad YTD sin necesitar que
    exista un snapshot exacto del 1 de enero. Opera sobre el histórico ya
    cargado en memoria (ver _load_price_history), no consulta la BD."""
    for d, _h, _l, c in history_by_ticker.get(ticker_id, []):  # ya viene ordenado ascendente
        if d >= on_or_after:
            return c
    return None


def _latest_price(
    history_by_ticker: dict[int, list[tuple[date, float, float, float]]], ticker_id: int, ticker: Ticker | None = None,
) -> float | None:
    """Precio "actual" para la cartera pública: prioriza el último cierre DIARIO
    (Ticker.last_daily_close, ver app/jobs/run_screener.py) sobre el cierre
    semanal de PriceSnapshot -- así el retorno se refleja día a día y no solo
    cada viernes, que es la cadencia que usa el análisis Weinstein/CAN SLIM.
    El fallback semanal usa el histórico ya cargado en memoria, no consulta la BD."""
    if ticker is not None and ticker.last_daily_close is not None:
        return float(ticker.last_daily_close)
    history = history_by_ticker.get(ticker_id)
    return history[-1][3] if history else None


def _strategy_details(opp: Opportunity, method: str) -> str | None:
    """Réplica de _strategy_result en app/jobs/update_portfolio.py (misma razón:
    no acoplar la capa HTTP-API a los jobs). Devuelve el `details` factual que
    ya calculó la estrategia -- el "porqué" correcto para minervini/lynch/
    berkshire/dividendos, en vez del narrador AI de Weinstein+CAN SLIM."""
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
    return data.get("details") if isinstance(data, dict) else None


@router.get("", response_model=PortfolioSchema)
def get_portfolio(db: Session = Depends(get_db)) -> PortfolioSchema:
    spy_ticker = db.query(Ticker).filter_by(symbol=BENCHMARK_SYMBOL).one_or_none()

    rows = (
        db.query(PortfolioPosition, Ticker)
        .join(Ticker, PortfolioPosition.ticker_id == Ticker.id)
        .order_by(PortfolioPosition.entry_date.desc())
        .all()
    )

    # El "porqué se eligió": para early_stage2 (literalmente Weinstein+CAN SLIM)
    # se reutiliza la explicación AI del feed; para los otros 4 métodos se usa
    # el `details` factual que ya calculó su propia estrategia -- describir ahí
    # el momentum Weinstein en vez de las métricas de calidad/GARP/dividendo
    # reales sería una explicación cierta pero equivocada para el pick.
    # signal_date es None en posiciones creadas antes del fix anti-look-ahead;
    # para esas, la señal y la entrada antigua ocurrieron el mismo día.
    ticker_ids = {pos.ticker_id for pos, _ in rows}
    explanations = {
        (e.ticker_id, e.run_date): e.text
        for e in db.query(Explanation).filter(Explanation.ticker_id.in_(ticker_ids)).all()
    } if ticker_ids else {}
    opportunities = {
        (o.ticker_id, o.run_date): o
        for o in db.query(Opportunity).filter(Opportunity.ticker_id.in_(ticker_ids)).all()
    } if ticker_ids else {}

    # Histórico de precio de todos los tickers implicados (posiciones + SPY)
    # en una sola consulta -- ver _load_price_history.
    price_history_ticker_ids = set(ticker_ids)
    if spy_ticker:
        price_history_ticker_ids.add(spy_ticker.id)
    history_by_ticker = _load_price_history(db, price_history_ticker_ids)

    current_spy_price = _latest_price(history_by_ticker, spy_ticker.id, spy_ticker) if spy_ticker else None

    # Rentabilidad YTD: solo tiene sentido para posiciones que estuvieron
    # vigentes en algún momento del año en curso (abiertas ahora, o cerradas
    # dentro de este año). El precio base es el de entrada si la posición se
    # abrió este año, o el primer cierre disponible desde el 1 de enero si
    # viene de un año anterior -- así no se cuenta la parte de la ganancia
    # ya generada antes de que empezara el año.
    year_start = date(date.today().year, 1, 1)
    _year_start_price_cache: dict[int, float | None] = {}

    def _year_start_price(ticker_id: int) -> float | None:
        if ticker_id not in _year_start_price_cache:
            _year_start_price_cache[ticker_id] = _price_on_or_after(history_by_ticker, ticker_id, year_start)
        return _year_start_price_cache[ticker_id]

    spy_year_start_price = _year_start_price(spy_ticker.id) if spy_ticker else None
    ytd_spy_return_pct = (
        round((current_spy_price / spy_year_start_price - 1) * 100, 2)
        if current_spy_price and spy_year_start_price
        else None
    )

    positions: list[PortfolioPositionSchema] = []
    # (ticker_id -> [(entry_date, return_fraction), ...]) -- se agrupa por
    # ticker porque un mismo nombre puede entrar y salir varias veces en el
    # año (p.ej. IMMR o CLMB, que "chopean" cada 2-4 semanas): contar cada
    # entrada/salida como una posición más con el mismo peso que un ganador
    # de una sola operación (p.ej. AMAT +78%) diluía brutalmente a los
    # ganadores reales -- 6-7 operaciones de un ticker que apenas se mueve
    # pesaban tanto en la media como 6-7 ganadores distintos. Equiponderar
    # de verdad significa un peso por TICKER, componiendo sus operaciones
    # sucesivas dentro del año (como si fueras reinvirtiendo ese hueco de
    # cartera cada vez que la señal se repite).
    ytd_returns_by_ticker: dict[int, list[tuple[date, float]]] = {}
    for pos, ticker in rows:
        if pos.status == "closed":
            current_price = pos.exit_price or pos.entry_price
            spy_price_now = pos.exit_spy_price or pos.entry_spy_price
        else:
            current_price = _latest_price(history_by_ticker, pos.ticker_id, ticker) or pos.entry_price
            spy_price_now = current_spy_price or pos.entry_spy_price

        return_pct = (current_price / pos.entry_price - 1) * 100
        spy_return_pct = (spy_price_now / pos.entry_spy_price - 1) * 100
        signal_key = (pos.ticker_id, pos.signal_date or pos.entry_date)
        if pos.method in _AI_EXPLAINED_METHODS:
            explanation = explanations.get(signal_key)
        else:
            opp = opportunities.get(signal_key)
            explanation = _strategy_details(opp, pos.method) if opp else None

        positions.append(PortfolioPositionSchema(
            ticker=ticker.symbol,
            name=ticker.name,
            sector=ticker.sector,
            method=pos.method,
            status=pos.status,
            explanation=explanation,
            signal_date=pos.signal_date,
            entry_date=pos.entry_date,
            entry_price=pos.entry_price,
            current_price=current_price,
            return_pct=round(return_pct, 2),
            spy_return_pct=round(spy_return_pct, 2),
            exit_signal_date=pos.exit_signal_date,
            exit_date=pos.exit_date,
            exit_reason=pos.exit_reason,
        ))

        was_alive_in_ytd = pos.exit_date is None or pos.exit_date >= year_start
        if was_alive_in_ytd:
            base_price = pos.entry_price if pos.entry_date >= year_start else _year_start_price(pos.ticker_id)
            if base_price:
                ret_fraction = current_price / base_price - 1
                ytd_returns_by_ticker.setdefault(pos.ticker_id, []).append((pos.entry_date, ret_fraction))

    total = len(positions)
    open_count = sum(1 for p in positions if p.status == "open")

    if total:
        best = max(positions, key=lambda p: p.return_pct)
        worst = min(positions, key=lambda p: p.return_pct)
    else:
        best = worst = None

    ytd_ticker_returns: dict[int, float] = {}
    raw_weights: dict[int, float | None] = {}
    for ticker_id, trades in ytd_returns_by_ticker.items():
        trades.sort(key=lambda t: t[0])
        compounded = 1.0
        for _, ret_fraction in trades:
            compounded *= 1 + ret_fraction
        ytd_ticker_returns[ticker_id] = (compounded - 1) * 100
        # Peso por la volatilidad en la PRIMERA entrada del año para este
        # ticker -- el riesgo que un trader real habría visto al abrir la
        # posición, no el actual (evita look-ahead).
        raw_weights[ticker_id] = _atr_pct(history_by_ticker, ticker_id, trades[0][0])
        raw_weights[ticker_id] = 1 / raw_weights[ticker_id] if raw_weights[ticker_id] else None

    weights = _position_weights(raw_weights)
    weight_total = sum(weights[tid] for tid in ytd_ticker_returns)
    ytd_return_pct = (
        round(sum(weights[tid] * ret for tid, ret in ytd_ticker_returns.items()) / weight_total, 2)
        if ytd_ticker_returns and weight_total
        else None
    )

    stats = PortfolioStatsSchema(
        total_positions=total,
        open_positions=open_count,
        closed_positions=total - open_count,
        ytd_return_pct=ytd_return_pct,
        ytd_spy_return_pct=ytd_spy_return_pct,
        best=best,
        worst=worst,
    )
    return PortfolioSchema(stats=stats, positions=positions)
