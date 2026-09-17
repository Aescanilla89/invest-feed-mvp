"""100 reproducible walk-forward scenarios for method selection.

This lab varies the information window and the training statistic, while
keeping the test data strictly out of the selection step. It is intentionally
separate from production portfolio rules: its output is evidence for a
future rule change, not an automatic trading decision.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median, mean

from app.jobs.walkforward import TradeObservation, load_api_trades
from app.portfolio_metrics import max_drawdown, performance_metrics
from app.core.config import settings


@dataclass(frozen=True)
class Scenario:
    name: str
    train_weeks: int
    test_weeks: int
    policy: str
    min_trades: int = 3


POLICIES = ("mean_alpha", "median_alpha", "ewma_alpha", "sharpe", "conservative")


def scenario_grid() -> list[Scenario]:
    """Return exactly 100 combinations: 4 train x 5 test x 5 policies."""
    scenarios = []
    for train in (13, 26, 39, 52):
        for test in (4, 8, 13, 26, 39):
            for policy in POLICIES:
                scenarios.append(Scenario(f"train{train}_test{test}_{policy}", train, test, policy))
    return scenarios


def _training_score(values: list[TradeObservation], policy: str) -> float:
    alphas = [t.return_fraction - t.benchmark_fraction for t in values]
    metrics = performance_metrics([t.return_fraction for t in values], [t.benchmark_fraction for t in values], settings.portfolio_cost_bps)
    if policy == "mean_alpha":
        return mean(alphas)
    if policy == "median_alpha":
        return median(alphas)
    if policy == "ewma_alpha":
        ordered = sorted(values, key=lambda t: t.exit_date)
        weights = [0.7 ** (len(ordered) - i - 1) for i in range(len(ordered))]
        return sum(w * (t.return_fraction - t.benchmark_fraction) for w, t in zip(weights, ordered)) / sum(weights)
    if policy == "sharpe":
        return float(metrics["sharpe"] or 0.0)
    if policy == "conservative":
        return (float(metrics["alpha_pct"] or 0.0) / 100.0) - abs(max_drawdown([t.return_fraction for t in values])) * 0.5
    raise ValueError(f"Política desconocida: {policy}")


def _select_methods(trades: list[TradeObservation], start: date, end: date, policy: str, min_trades: int) -> list[str]:
    grouped: dict[str, list[TradeObservation]] = {}
    for trade in trades:
        if start <= trade.entry_date and trade.exit_date <= end:
            grouped.setdefault(trade.method, []).append(trade)
    return sorted(method for method, values in grouped.items() if len(values) >= min_trades and _training_score(values, policy) > 0)


def run_scenario(trades: list[TradeObservation], scenario: Scenario) -> dict:
    if not trades:
        return {"scenario": scenario.name, "valid": False, "reason": "no_trades", "out_of_sample": performance_metrics([]), "windows": []}
    first = min(t.entry_date for t in trades)
    last = max(t.exit_date for t in trades)
    train_delta = timedelta(weeks=scenario.train_weeks)
    test_delta = timedelta(weeks=scenario.test_weeks)
    start = first
    oos: list[float] = []
    oos_benchmark: list[float] = []
    windows = []
    while start + train_delta + test_delta <= last:
        train_end = start + train_delta
        test_start = train_end + timedelta(days=1)
        test_end = train_end + test_delta
        selected = _select_methods(trades, start, train_end, scenario.policy, scenario.min_trades)
        tested = [t for t in trades if test_start <= t.entry_date and t.exit_date <= test_end and t.method in selected]
        returns = [t.return_fraction for t in tested]
        benchmark = [t.benchmark_fraction for t in tested]
        metrics = performance_metrics(returns, benchmark, settings.portfolio_cost_bps)
        oos.extend(returns)
        oos_benchmark.extend(benchmark)
        windows.append({"train_end": train_end.isoformat(), "test_end": test_end.isoformat(), "selected_methods": selected, "test_trades": len(tested), "metrics": metrics})
        start += test_delta
    result = performance_metrics(oos, oos_benchmark, settings.portfolio_cost_bps)
    return {"scenario": scenario.name, "valid": result["observations"] >= 5, "reason": None if result["observations"] >= 5 else "insufficient_oos_trades", "out_of_sample": result, "windows": windows}


def rank_results(results: list[dict]) -> list[dict]:
    return sorted(results, key=lambda r: (r["valid"], r["out_of_sample"].get("alpha_pct") or -10_000, -(abs(r["out_of_sample"].get("max_drawdown_pct") or 0))), reverse=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ejecuta 100 escenarios walk-forward fuera de muestra")
    parser.add_argument("--api-url", required=True)
    args = parser.parse_args()
    trades = load_api_trades(args.api_url)
    results = rank_results([run_scenario(trades, scenario) for scenario in scenario_grid()])
    print(json.dumps({"scenarios": len(results), "trades": len(trades), "results": results}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
