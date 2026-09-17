import pytest

from app.portfolio_metrics import compound, max_drawdown, net_return, performance_metrics


def test_compound_and_costs():
    assert compound([0.10, -0.10]) == pytest.approx(-0.01)
    assert net_return(0.10, 100) == pytest.approx(0.089)


def test_drawdown_is_peak_to_trough():
    assert max_drawdown([0.10, -0.20, 0.05]) == pytest.approx(-0.20)


def test_metrics_include_alpha_and_trade_quality():
    result = performance_metrics([0.10, -0.05, 0.02], [0.04, -0.02, 0.01])
    assert result["observations"] == 3
    assert result["total_return_pct"] == pytest.approx(6.59)
    assert result["benchmark_return_pct"] == pytest.approx(2.9392)
    assert result["alpha_pct"] > 3
    assert result["win_rate_pct"] == pytest.approx(66.6666667)
    assert result["profit_factor"] == pytest.approx(2.4)
    assert result["max_drawdown_pct"] == pytest.approx(-5)
