"""Walk-forward evaluation of the portfolio methods.

The selector is deliberately simple and deterministic: methods are selected
only with information available before each test window, then the selected
methods are evaluated on the following unseen window.
"""
from __future__ import annotations

import argparse
import json
from urllib.request import urlopen
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.config import settings
from app.core.db import SessionLocal, init_db
from app.models.orm import PortfolioPosition
from app.portfolio_metrics import performance_metrics


@dataclass(frozen=True)
class TradeObservation:
    method: str
    entry_date: date
    exit_date: date
    return_fraction: float
    benchmark_fraction: float


def select_methods(
    trades: list[TradeObservation],
    train_start: date,
    train_end: date,
    min_trades: int = 3,
) -> list[str]:
    """Select methods using only trades fully known by ``train_end``."""
    grouped: dict[str, list[TradeObservation]] = {}
    for trade in trades:
        if train_start <= trade.entry_date and trade.exit_date <= train_end:
            grouped.setdefault(trade.method, []).append(trade)
    selected = []
    for method, values in grouped.items():
        metrics = performance_metrics(
            [t.return_fraction for t in values],
            [t.benchmark_fraction for t in values],
            settings.portfolio_cost_bps,
        )
        if len(values) >= min_trades and (metrics["alpha_pct"] or 0) > 0:
            selected.append(method)
    return sorted(selected)


def walk_forward(
    trades: list[TradeObservation],
    train_weeks: int = 26,
    test_weeks: int = 13,
    step_weeks: int | None = None,
    min_trades: int = 3,
) -> dict:
    """Run expanding-date windows and return out-of-sample-only results."""
    if train_weeks <= 0 or test_weeks <= 0:
        raise ValueError("train_weeks y test_weeks deben ser positivos")
    if not trades:
        return {"windows": [], "out_of_sample": performance_metrics([]), "selected_methods": []}
        raise ValueError("train_weeks y test_weeks deben ser positivos")
    step = timedelta(weeks=step_weeks or test_weeks)
    train_delta = timedelta(weeks=train_weeks)
    test_delta = timedelta(weeks=test_weeks)
    first = min(t.entry_date for t in trades)
    last = max(t.exit_date for t in trades)
    train_start = first
    windows: list[dict] = []
    oos_returns: list[float] = []
    oos_benchmark: list[float] = []
    all_selected: set[str] = set()
    while train_start + train_delta + test_delta <= last:
        train_end = train_start + train_delta
        test_start = train_end + timedelta(days=1)
        test_end = train_end + test_delta
        selected = select_methods(trades, train_start, train_end, min_trades)
        test_trades = [
            t for t in trades
            if test_start <= t.entry_date and t.exit_date <= test_end and t.method in selected
        ]
        returns = [t.return_fraction for t in test_trades]
        benchmark = [t.benchmark_fraction for t in test_trades]
        metrics = performance_metrics(returns, benchmark, settings.portfolio_cost_bps)
        oos_returns.extend(returns)
        oos_benchmark.extend(benchmark)
        all_selected.update(selected)
        windows.append({
            "train_start": train_start.isoformat(), "train_end": train_end.isoformat(),
            "test_start": test_start.isoformat(), "test_end": test_end.isoformat(),
            "selected_methods": selected, "test_trades": len(test_trades), "metrics": metrics,
        })
        train_start += step
    return {
        "parameters": {"train_weeks": train_weeks, "test_weeks": test_weeks, "step_weeks": step.days // 7, "min_trades": min_trades},
        "windows": windows,
        "selected_methods": sorted(all_selected),
        "out_of_sample": performance_metrics(oos_returns, oos_benchmark, settings.portfolio_cost_bps),
    }


def observations_from_payload(payload: dict) -> list[TradeObservation]:
    observations = []
    for item in payload.get("positions", []):
        if item.get("status") != "closed" or not item.get("exit_date"):
            continue
        observations.append(TradeObservation(
            method=item["method"],
            entry_date=date.fromisoformat(item["entry_date"]),
            exit_date=date.fromisoformat(item["exit_date"]),
            return_fraction=float(item["return_pct"]) / 100.0,
            benchmark_fraction=float(item["spy_return_pct"]) / 100.0,
        ))
    return observations

def load_api_trades(url: str) -> list[TradeObservation]:
    with urlopen(url, timeout=30) as response:
        return observations_from_payload(json.load(response))

def load_closed_trades() -> list[TradeObservation]:
    init_db()
    db = SessionLocal()
    try:
        rows = db.query(PortfolioPosition).filter(PortfolioPosition.status == "closed").all()
        return [TradeObservation(p.method, p.entry_date, p.exit_date, p.exit_price / p.entry_price - 1, p.exit_spy_price / p.entry_spy_price - 1)
                for p in rows if p.exit_date and p.exit_price and p.exit_spy_price and p.entry_price and p.entry_spy_price]
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluación walk-forward fuera de muestra")
    parser.add_argument("--train-weeks", type=int, default=26)
    parser.add_argument("--test-weeks", type=int, default=13)
    parser.add_argument("--step-weeks", type=int, default=None)
    parser.add_argument("--min-trades", type=int, default=3)
    parser.add_argument("--api-url", type=str, default=None, help="Cargar operaciones cerradas desde un endpoint /api/portfolio")
    args = parser.parse_args()
    trades = load_api_trades(args.api_url) if args.api_url else load_closed_trades()
    result = walk_forward(trades, args.train_weeks, args.test_weeks, args.step_weeks, args.min_trades)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
