from app.screener.canslim import (
    evaluate_a,
    evaluate_c,
    evaluate_i,
    evaluate_l,
    evaluate_m,
    evaluate_n,
    evaluate_s,
)
from app.screener.data_source import FundamentalData
from app.screener.sec_edgar import SupplySignal
from app.screener.weinstein import WeinsteinResult
from tests.helpers import make_weekly_df, steady_uptrend, flat_sideways


def test_evaluate_c_passes_above_threshold():
    fundamentals = FundamentalData(0.30, 0.10, [], [])
    result = evaluate_c(fundamentals)
    assert result.value is True


def test_evaluate_c_fails_below_threshold():
    fundamentals = FundamentalData(0.05, 0.10, [], [])
    result = evaluate_c(fundamentals)
    assert result.value is False


def test_evaluate_c_none_when_no_data():
    fundamentals = FundamentalData(None, None, [], [])
    assert evaluate_c(fundamentals).value is None


def test_evaluate_a_passes_above_threshold():
    fundamentals = FundamentalData(0.10, 0.40, [], [])
    assert evaluate_a(fundamentals).value is True


def test_evaluate_n_new_high_with_volume_passes():
    closes = steady_uptrend(n=52, start_price=100, end_price=150)
    volumes = [1_000_000.0] * 51 + [2_500_000.0]
    df = make_weekly_df(closes, volumes)
    result = evaluate_n(df)
    assert result.value is True


def test_evaluate_n_far_from_high_fails():
    closes = flat_sideways(n=52, level=100, noise_std=0.2)
    df = make_weekly_df(closes)
    # forzamos que el último cierre esté lejos del máximo de 52 semanas
    df.loc[df.index[-1], "Close"] = 80.0
    result = evaluate_n(df)
    assert result.value is False


def test_evaluate_l_outperformance():
    ticker_df = make_weekly_df(steady_uptrend(n=60, start_price=100, end_price=200))
    benchmark_df = make_weekly_df(steady_uptrend(n=60, start_price=100, end_price=120))
    result = evaluate_l(ticker_df, benchmark_df)
    assert result.value is True


def test_evaluate_s_buyback_trend():
    signal = SupplySignal(is_buyback_trend=True, shares_outstanding_change_pct=-0.05, quarters_compared=4)
    assert evaluate_s(signal).value is True


def test_evaluate_s_none_when_no_sec_data():
    signal = SupplySignal(is_buyback_trend=None, shares_outstanding_change_pct=None, quarters_compared=0)
    assert evaluate_s(signal).value is None


def test_evaluate_i_always_none():
    # Criterio explícitamente no verificable en el MVP (ver docstring de canslim.py)
    result = evaluate_i()
    assert result.value is None
    assert "13F" in result.detail


def test_evaluate_m_stage2_benchmark_passes():
    benchmark_result = WeinsteinResult(stage=2, weeks_in_stage=5, ma_slope_pct=0.02, relative_volume=1.2, is_transition_1_to_2=False)
    assert evaluate_m(benchmark_result).value is True


def test_evaluate_m_stage4_benchmark_fails():
    benchmark_result = WeinsteinResult(stage=4, weeks_in_stage=5, ma_slope_pct=-0.02, relative_volume=1.2, is_transition_1_to_2=False)
    assert evaluate_m(benchmark_result).value is False
