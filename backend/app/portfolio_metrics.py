from __future__ import annotations

from datetime import date
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


def slot_performance_metrics(trades: list[dict], max_slots: int = 15, cost_bps: float = 0.0) -> dict[str, float | int | None]:
    """Compound sequential trades in reusable capital slots.

    Overlapping trades consume different slots; a later trade can reuse a
    slot only after the previous trade exits. This avoids compounding the
    same benchmark period multiple times.
    """
    if max_slots <= 0:
        raise ValueError("max_slots debe ser positivo")
    slots = [{"available": date.min, "equity": 1.0 / max_slots, "benchmark": 1.0 / max_slots} for _ in range(max_slots)]
    ordered = sorted(trades, key=lambda t: (t["entry_date"], t["exit_date"]))
    used = 0
    for trade in ordered:
        available = next((slot for slot in slots if slot["available"] <= trade["entry_date"]), None)
        if available is None:
            continue
        available["equity"] *= 1 + net_return(trade["return_fraction"], cost_bps)
        available["benchmark"] *= 1 + trade["benchmark_fraction"]
        available["available"] = trade["exit_date"]
        used += 1
    equity = sum(slot["equity"] for slot in slots)
    benchmark = sum(slot["benchmark"] for slot in slots)
    return {"observations": used, "total_return_pct": (equity - 1) * 100, "benchmark_return_pct": (benchmark - 1) * 100, "alpha_pct": (equity - benchmark) * 100}

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
