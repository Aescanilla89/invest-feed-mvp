from datetime import date, timedelta

import pytest

from app.portfolio_metrics import slot_performance_metrics


def test_slots_do_not_compound_overlapping_trades_as_sequential():
    start = date(2025, 1, 1)
    trades = [
        {"entry_date": start, "exit_date": start + timedelta(days=10), "return_fraction": .10, "benchmark_fraction": .05},
        {"entry_date": start + timedelta(days=1), "exit_date": start + timedelta(days=9), "return_fraction": .10, "benchmark_fraction": .05},
    ]
    result = slot_performance_metrics(trades, max_slots=2)
    assert result["observations"] == 2
    assert result["total_return_pct"] == pytest.approx(10.0)
    assert result["benchmark_return_pct"] == pytest.approx(5.0)


def test_slots_reuse_capital_after_exit():
    start = date(2025, 1, 1)
    trades = [
        {"entry_date": start, "exit_date": start + timedelta(days=2), "return_fraction": .10, "benchmark_fraction": .05},
        {"entry_date": start + timedelta(days=3), "exit_date": start + timedelta(days=5), "return_fraction": .10, "benchmark_fraction": .05},
    ]
    result = slot_performance_metrics(trades, max_slots=1)
    assert result["total_return_pct"] == pytest.approx(21.0)
