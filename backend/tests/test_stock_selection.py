from types import SimpleNamespace

from app.stock_selection import stock_selection_score


def _opportunity(**kwargs):
    values = {
        "combined_score": 70,
        "strategies": {"minervini": {"score": 80}},
        "weinstein_stage": 2,
        "weinstein_ma_slope_pct": 4,
        "weinstein_relative_volume": 1.5,
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


def test_stock_selection_prefers_quality_and_trend_confirmation():
    strong = _opportunity(combined_score=85, weinstein_ma_slope_pct=6, weinstein_relative_volume=2)
    weak = _opportunity(combined_score=60, weinstein_stage=1, weinstein_ma_slope_pct=-2)
    assert stock_selection_score(strong, "minervini") > stock_selection_score(weak, "minervini")


def test_stock_selection_handles_missing_strategy():
    opportunity = _opportunity(strategies={})
    assert stock_selection_score(opportunity, "berkshire") > 0
