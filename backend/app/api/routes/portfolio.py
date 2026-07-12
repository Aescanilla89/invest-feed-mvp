"""Cartera pública (social proof): expone las posiciones que abre/cierra
automáticamente app/jobs/update_portfolio.py."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.jobs.run_screener import BENCHMARK_SYMBOL
from app.models.orm import PortfolioPosition, PriceSnapshot, Ticker
from app.models.schemas import PortfolioPositionSchema, PortfolioSchema, PortfolioStatsSchema

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _latest_price(db: Session, ticker_id: int) -> float | None:
    row = (
        db.query(PriceSnapshot.close)
        .filter(PriceSnapshot.ticker_id == ticker_id)
        .order_by(PriceSnapshot.date.desc())
        .first()
    )
    return float(row[0]) if row else None


@router.get("", response_model=PortfolioSchema)
def get_portfolio(db: Session = Depends(get_db)) -> PortfolioSchema:
    spy_ticker = db.query(Ticker).filter_by(symbol=BENCHMARK_SYMBOL).one_or_none()
    current_spy_price = _latest_price(db, spy_ticker.id) if spy_ticker else None

    rows = (
        db.query(PortfolioPosition, Ticker)
        .join(Ticker, PortfolioPosition.ticker_id == Ticker.id)
        .order_by(PortfolioPosition.entry_date.desc())
        .all()
    )

    positions: list[PortfolioPositionSchema] = []
    for pos, ticker in rows:
        if pos.status == "closed":
            current_price = pos.exit_price or pos.entry_price
            spy_price_now = pos.exit_spy_price or pos.entry_spy_price
        else:
            current_price = _latest_price(db, pos.ticker_id) or pos.entry_price
            spy_price_now = current_spy_price or pos.entry_spy_price

        return_pct = (current_price / pos.entry_price - 1) * 100
        spy_return_pct = (spy_price_now / pos.entry_spy_price - 1) * 100

        positions.append(PortfolioPositionSchema(
            ticker=ticker.symbol,
            name=ticker.name,
            sector=ticker.sector,
            method=pos.method,
            status=pos.status,
            signal_date=pos.signal_date,
            entry_date=pos.entry_date,
            entry_price=pos.entry_price,
            current_price=current_price,
            return_pct=round(return_pct, 2),
            spy_return_pct=round(spy_return_pct, 2),
            exit_date=pos.exit_date,
            exit_reason=pos.exit_reason,
        ))

    total = len(positions)
    open_count = sum(1 for p in positions if p.status == "open")

    if total:
        win_rate = round(sum(1 for p in positions if p.return_pct > 0) / total * 100, 1)
        avg_return = round(sum(p.return_pct for p in positions) / total, 2)
        avg_spy_return = round(sum(p.spy_return_pct for p in positions) / total, 2)
        best = max(positions, key=lambda p: p.return_pct)
        worst = min(positions, key=lambda p: p.return_pct)
    else:
        win_rate = avg_return = avg_spy_return = None
        best = worst = None

    stats = PortfolioStatsSchema(
        total_positions=total,
        open_positions=open_count,
        closed_positions=total - open_count,
        win_rate=win_rate,
        avg_return_pct=avg_return,
        avg_spy_return_pct=avg_spy_return,
        best=best,
        worst=worst,
    )
    return PortfolioSchema(stats=stats, positions=positions)
