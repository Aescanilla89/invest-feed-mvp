from datetime import date, timedelta

import pytest

from app.jobs.walkforward import TradeObservation, select_methods, walk_forward


def _trade(method: str, start: date, ret: float, spy: float) -> TradeObservation:
    return TradeObservation(method, start, start + timedelta(days=6), ret, spy)


def test_selector_uses_only_training_window_and_positive_alpha():
    start = date(2025, 1, 1)
    trades = [_trade("good", start + timedelta(days=14 * i), .10, .01) for i in range(3)]
    trades += [_trade("bad", start + timedelta(days=14 * i), -.02, .01) for i in range(3)]
    assert select_methods(trades, start, start + timedelta(days=60), min_trades=3) == ["good"]


def test_walkforward_reports_only_unseen_test_windows():
    start = date(2025, 1, 1)
    trades = []
    for i in range(12):
        # Six training observations select good; six later observations are OOS.
        method = "good"
        ret = .10 if i < 6 else .05
        trades.append(_trade(method, start + timedelta(days=7 * i), ret, .01))
    result = walk_forward(trades, train_weeks=5, test_weeks=5, min_trades=2)
    assert result["windows"]
    assert result["out_of_sample"]["observations"] > 0
    assert all("metrics" in window for window in result["windows"])


def test_walkforward_rejects_invalid_windows():
    with pytest.raises(ValueError):
        walk_forward([], train_weeks=0)
