from __future__ import annotations

from math import sqrt
from statistics import mean, pstdev
from typing import Iterable


def net_return(gross_return: float, cost_bps: float = 0.0) -> float:
    return (1.0 + gross_return) * (1.0 - cost_bps / 10_000.0) - 1.0


def compound(returns: Iterable[float]) -> float:
    equity = 1.0
    for value in returns:
        equity *= 1.0 + value
    return equity - 1.0


def max_drawdown(returns: Iterable[float]) -> float:
    equity = peak = 1.0
    worst = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1.0)
    return worst


def performance_metrics(returns: Iterable[float], benchmark: Iterable[float] = (), cost_bps: float = 0.0) -> dict[str, float | int | None]:
    gross = list(returns)
    net = [net_return(value, cost_bps) for value in gross]
    bench = list(benchmark)
    wins = [value for value in net if value > 0]
    losses = [value for value in net if value < 0]
    avg = mean(net) if net else 0.0
    volatility = pstdev(net) if len(net) > 1 else 0.0
    downside = pstdev([min(value, 0.0) for value in net]) if len(net) > 1 else 0.0
    total = compound(net)
    benchmark_total = compound(bench) if bench else 0.0
    beta = None
    if len(net) > 1 and len(net) == len(bench):
        bm_avg = mean(bench)
        covariance = sum((a - avg) * (b - bm_avg) for a, b in zip(net, bench)) / len(net)
        variance = sum((b - bm_avg) ** 2 for b in bench) / len(bench)
        beta = covariance / variance if variance else None
    return {
        "observations": len(net), "total_return_pct": total * 100,
        "benchmark_return_pct": benchmark_total * 100 if bench else None,
        "alpha_pct": (total - benchmark_total) * 100 if bench else None,
        "win_rate_pct": len(wins) / len(net) * 100 if net else None,
        "average_return_pct": avg * 100 if net else None,
        "average_win_pct": mean(wins) * 100 if wins else None,
        "average_loss_pct": mean(losses) * 100 if losses else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "expectancy_pct": avg * 100 if net else None,
        "volatility_pct": volatility * sqrt(52) * 100 if net else None,
        "sharpe": avg / volatility * sqrt(52) if volatility else None,
        "sortino": avg / downside * sqrt(52) if downside else None,
        "max_drawdown_pct": max_drawdown(net) * 100,
        "beta": beta,
    }
