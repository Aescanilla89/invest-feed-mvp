"""Diagnóstico puntual: vuelca el desglose completo del cálculo YTD de la
cartera pública (todas las posiciones que entran en el promedio, no solo las
"destacadas" que muestra el frontend) para investigar por qué la cifra
agregada parece baja pese a haber posiciones individuales muy ganadoras.

Uso: python -m scripts.debug_ytd
"""
from __future__ import annotations

from datetime import date

from app.core.db import SessionLocal, init_db
from app.jobs.run_screener import BENCHMARK_SYMBOL
from app.models.orm import PortfolioPosition, PriceSnapshot, Ticker


def _price_on_or_after(db, ticker_id: int, on_or_after: date) -> float | None:
    row = (
        db.query(PriceSnapshot.close)
        .filter(PriceSnapshot.ticker_id == ticker_id, PriceSnapshot.date >= on_or_after)
        .order_by(PriceSnapshot.date.asc())
        .first()
    )
    return float(row[0]) if row else None


def _latest_price(db, ticker_id: int, ticker: Ticker | None = None) -> float | None:
    if ticker is not None and ticker.last_daily_close is not None:
        return float(ticker.last_daily_close)
    row = (
        db.query(PriceSnapshot.close)
        .filter(PriceSnapshot.ticker_id == ticker_id)
        .order_by(PriceSnapshot.date.desc())
        .first()
    )
    return float(row[0]) if row else None


def main() -> None:
    init_db()
    db = SessionLocal()

    spy_ticker = db.query(Ticker).filter_by(symbol=BENCHMARK_SYMBOL).one_or_none()
    current_spy_price = _latest_price(db, spy_ticker.id, spy_ticker) if spy_ticker else None

    rows = (
        db.query(PortfolioPosition, Ticker)
        .join(Ticker, PortfolioPosition.ticker_id == Ticker.id)
        .order_by(PortfolioPosition.entry_date.desc())
        .all()
    )

    year_start = date(date.today().year, 1, 1)
    _cache: dict[int, float | None] = {}

    def year_start_price(ticker_id: int) -> float | None:
        if ticker_id not in _cache:
            _cache[ticker_id] = _price_on_or_after(db, ticker_id, year_start)
        return _cache[ticker_id]

    spy_year_start_price = year_start_price(spy_ticker.id) if spy_ticker else None
    print(f"year_start={year_start} SPY current={current_spy_price} SPY year_start={spy_year_start_price}")
    if current_spy_price and spy_year_start_price:
        print(f"SPY YTD = {(current_spy_price/spy_year_start_price-1)*100:.2f}%")

    print(f"\ntotal PortfolioPosition rows: {len(rows)}")

    included: list[tuple] = []
    excluded_not_alive = 0
    excluded_no_base_price = 0

    for pos, ticker in rows:
        was_alive = pos.exit_date is None or pos.exit_date >= year_start
        if not was_alive:
            excluded_not_alive += 1
            continue

        if pos.status == "closed":
            current_price = pos.exit_price or pos.entry_price
        else:
            current_price = _latest_price(db, pos.ticker_id, ticker) or pos.entry_price

        base_price = pos.entry_price if pos.entry_date >= year_start else year_start_price(pos.ticker_id)
        if not base_price:
            excluded_no_base_price += 1
            print(f"  SIN base_price: {ticker.symbol} entry={pos.entry_date} status={pos.status}")
            continue

        ret = (current_price / base_price - 1) * 100
        included.append((ticker.symbol, pos.status, pos.entry_date, pos.exit_date, base_price, current_price, ret))

    print(f"incluidas en YTD: {len(included)}  |  excluidas (no vigentes en YTD): {excluded_not_alive}  |  excluidas (sin base_price): {excluded_no_base_price}")

    included.sort(key=lambda r: r[-1])
    print("\n--- todas las posiciones incluidas en el promedio YTD, ordenadas por retorno ---")
    for symbol, status, entry_date, exit_date, base_price, current_price, ret in included:
        print(f"  {symbol:6s} {status:6s} entry={entry_date} exit={exit_date}  base={base_price:.2f} -> now={current_price:.2f}  = {ret:+7.2f}%")

    if included:
        avg = sum(r[-1] for r in included) / len(included)
        print(f"\nAVG (equal-weighted) = {avg:.2f}%  sobre {len(included)} posiciones")

    db.close()


if __name__ == "__main__":
    main()
