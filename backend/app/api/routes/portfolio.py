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


def _price_on_or_after(db: Session, ticker_id: int, on_or_after: date) -> float | None:
    """Primer cierre disponible a partir de `on_or_after` (inclusive) -- se
    usa como precio base para calcular la rentabilidad YTD sin necesitar que
    exista un snapshot exacto del 1 de enero."""
    row = (
        db.query(PriceSnapshot.close)
        .filter(PriceSnapshot.ticker_id == ticker_id, PriceSnapshot.date >= on_or_after)
        .order_by(PriceSnapshot.date.asc())
        .first()
    )
    return float(row[0]) if row else None


def _latest_price(db: Session, ticker_id: int, ticker: Ticker | None = None) -> float | None:
    """Precio "actual" para la cartera pública: prioriza el último cierre DIARIO
    (Ticker.last_daily_close, ver app/jobs/run_screener.py) sobre el cierre
    semanal de PriceSnapshot -- así el retorno se refleja día a día y no solo
    cada viernes, que es la cadencia que usa el análisis Weinstein/CAN SLIM."""
    if ticker is not None and ticker.last_daily_close is not None:
        return float(ticker.last_daily_close)
    row = (
        db.query(PriceSnapshot.close)
        .filter(PriceSnapshot.ticker_id == ticker_id)
        .order_by(PriceSnapshot.date.desc())
        .first()
    )
    return float(row[0]) if row else None


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
    current_spy_price = _latest_price(db, spy_ticker.id, spy_ticker) if spy_ticker else None

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
            _year_start_price_cache[ticker_id] = _price_on_or_after(db, ticker_id, year_start)
        return _year_start_price_cache[ticker_id]

    spy_year_start_price = _year_start_price(spy_ticker.id) if spy_ticker else None
    ytd_spy_return_pct = (
        round((current_spy_price / spy_year_start_price - 1) * 100, 2)
        if current_spy_price and spy_year_start_price
        else None
    )

    positions: list[PortfolioPositionSchema] = []
    ytd_position_returns: list[float] = []
    for pos, ticker in rows:
        if pos.status == "closed":
            current_price = pos.exit_price or pos.entry_price
            spy_price_now = pos.exit_spy_price or pos.entry_spy_price
        else:
            current_price = _latest_price(db, pos.ticker_id, ticker) or pos.entry_price
            spy_price_now = current_spy_price or pos.entry_spy_price

        return_pct = (current_price / pos.entry_price - 1) * 100
        spy_return_pct = (spy_price_now / pos.entry_spy_price - 1) * 100
        signal_key = (pos.ticker_id, pos.signal_date or pos.entry_date)
        if pos.method == _EARLY_STAGE2:
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
                ytd_position_returns.append((current_price / base_price - 1) * 100)

    total = len(positions)
    open_count = sum(1 for p in positions if p.status == "open")

    if total:
        avg_return = round(sum(p.return_pct for p in positions) / total, 2)
        avg_spy_return = round(sum(p.spy_return_pct for p in positions) / total, 2)
        best = max(positions, key=lambda p: p.return_pct)
        worst = min(positions, key=lambda p: p.return_pct)
    else:
        avg_return = avg_spy_return = None
        best = worst = None

    ytd_return_pct = round(sum(ytd_position_returns) / len(ytd_position_returns), 2) if ytd_position_returns else None

    stats = PortfolioStatsSchema(
        total_positions=total,
        open_positions=open_count,
        closed_positions=total - open_count,
        avg_return_pct=avg_return,
        avg_spy_return_pct=avg_spy_return,
        ytd_return_pct=ytd_return_pct,
        ytd_spy_return_pct=ytd_spy_return_pct,
        best=best,
        worst=worst,
    )
    return PortfolioSchema(stats=stats, positions=positions)
