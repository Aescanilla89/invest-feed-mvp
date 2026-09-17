from datetime import date, timedelta

from app.jobs.ma_lab import MAScenario, scenario_grid, sma_gate


def test_ma_grid_has_one_hundred_scenarios():
    assert len(scenario_grid()) == 100


def test_sma_gate_requires_real_history_and_trend():
    start = date(2025, 1, 1)
    rising = {start + timedelta(days=i): 100 + i for i in range(20)}
    falling = {start + timedelta(days=i): 100 - i for i in range(20)}
    assert sma_gate(start + timedelta(days=19), rising, 5) is True
    assert sma_gate(start + timedelta(days=19), falling, 5) is False
    assert sma_gate(start + timedelta(days=2), rising, 5) is False


def test_scenario_is_immutable():
    scenario = MAScenario("x", 13, 4, 50)
    assert scenario.ma_weeks == 50
