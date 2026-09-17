from datetime import date, timedelta

from app.jobs.scenario_lab import Scenario, _training_score, run_scenario, scenario_grid
from app.jobs.walkforward import TradeObservation


def _trade(method: str, day: int, ret: float, spy: float) -> TradeObservation:
    start = date(2025, 1, 1) + timedelta(days=day)
    return TradeObservation(method, start, start + timedelta(days=2), ret, spy)


def test_grid_has_one_hundred_scenarios():
    scenarios = scenario_grid()
    assert len(scenarios) == 100
    assert len({s.name for s in scenarios}) == 100


def test_ewma_prefers_recent_alpha():
    values = [_trade("x", 0, -.05, .01), _trade("x", 10, .10, .01), _trade("x", 20, .10, .01)]
    assert _training_score(values, "ewma_alpha") > _training_score(values, "mean_alpha")


def test_scenario_marks_small_oos_as_invalid():
    trades = [_trade("good", i * 7, .05, .01) for i in range(8)]
    result = run_scenario(trades, Scenario("tiny", 2, 2, "mean_alpha", min_trades=2))
    assert result["valid"] is False
    assert result["reason"] == "insufficient_oos_trades"
