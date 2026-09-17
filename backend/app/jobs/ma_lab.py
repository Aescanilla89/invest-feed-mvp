"""Walk-forward lab for real benchmark moving-average regimes."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from urllib.request import urlopen

from app.core.config import settings
from app.jobs.walkforward import TradeObservation, load_api_trades
from app.portfolio_metrics import performance_metrics


MA_PERIODS = (None, 20, 50, 100, 200)


@dataclass(frozen=True)
class MAScenario:
    name: str
    train_weeks: int
    test_weeks: int
    ma_weeks: int | None
    min_trades: int = 3


def scenario_grid() -> list[MAScenario]:
    return [
        MAScenario(f"train{train}_test{test}_sma{ma or 'none'}", train, test, ma)
        for train in (13, 26, 39, 52)
        for test in (4, 8, 13, 26, 39)
        for ma in MA_PERIODS
    ]


def sma_gate(entry_date: date, prices: dict[date, float], period: int | None) -> bool:
    if period is None:
        return True
    history = [close for day, close in sorted(prices.items()) if day <= entry_date]
    if len(history) < period:
        return False
    return history[-1] > sum(history[-period:]) / period


def _select_methods(trades: list[TradeObservation], start: date, end: date, prices: dict[date, float], ma_weeks: int | None, min_trades: int) -> list[str]:
    grouped: dict[str, list[TradeObservation]] = {}
    for trade in trades:
        if start <= trade.entry_date and trade.exit_date <= end and sma_gate(trade.entry_date, prices, ma_weeks):
            grouped.setdefault(trade.method, []).append(trade)
    selected = []
    for method, values in grouped.items():
        if len(values) < min_trades:
            continue
        alpha = sum(t.return_fraction - t.benchmark_fraction for t in values) / len(values)
        if alpha > 0:
            selected.append(method)
    return sorted(selected)


def run_scenario(trades: list[TradeObservation], scenario: MAScenario, prices: dict[date, float]) -> dict:
    if not trades:
        return {"scenario": scenario.name, "valid": False, "reason": "no_trades", "out_of_sample": performance_metrics([]), "windows": []}
    first = min(t.entry_date for t in trades)
    last = max(t.exit_date for t in trades)
    train_delta = timedelta(weeks=scenario.train_weeks)
    test_delta = timedelta(weeks=scenario.test_weeks)
    start = first
    returns: list[float] = []
    benchmark: list[float] = []
    windows = []
    while start + train_delta + test_delta <= last:
        train_end = start + train_delta
        test_start = train_end + timedelta(days=1)
        test_end = train_end + test_delta
        selected = _select_methods(trades, start, train_end, prices, scenario.ma_weeks, scenario.min_trades)
        tested = [t for t in trades if test_start <= t.entry_date <= test_end and t.exit_date <= test_end and t.method in selected and sma_gate(t.entry_date, prices, scenario.ma_weeks)]
        test_returns = [t.return_fraction for t in tested]
        test_benchmark = [t.benchmark_fraction for t in tested]
        metrics = performance_metrics(test_returns, test_benchmark, settings.portfolio_cost_bps)
        returns.extend(test_returns)
        benchmark.extend(test_benchmark)
        windows.append({"test_end": test_end.isoformat(), "selected_methods": selected, "test_trades": len(tested), "metrics": metrics})
        start += test_delta
    result = performance_metrics(returns, benchmark, settings.portfolio_cost_bps)
    return {"scenario": scenario.name, "valid": result["observations"] >= 5, "reason": None if result["observations"] >= 5 else "insufficient_oos_trades", "out_of_sample": result, "windows": windows}


def _prices_from_yahoo(symbol: str = "SPY", range_: str = "5y") -> dict[date, float]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_}&interval=1d"
    with urlopen(url, timeout=120) as response:
        payload = json.load(response)["chart"]["result"][0]
    closes = payload["indicators"]["quote"][0]["close"]
    return {datetime.fromtimestamp(ts).date(): float(close) for ts, close in zip(payload["timestamp"], closes) if close is not None}


def main() -> None:
    parser = argparse.ArgumentParser(description="100 walk-forward escenarios con SMA reales de SPY")
    parser.add_argument("--api-url", required=True)
    args = parser.parse_args()
    trades = load_api_trades(args.api_url)
    prices = _prices_from_yahoo()
    results = [run_scenario(trades, scenario, prices) for scenario in scenario_grid()]
    results.sort(key=lambda r: (r["valid"], r["out_of_sample"].get("alpha_pct") or -10_000), reverse=True)
    print(json.dumps({"scenarios": len(results), "trades": len(trades), "price_points": len(prices), "results": results}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
