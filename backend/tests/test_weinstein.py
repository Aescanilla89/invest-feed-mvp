import pytest

from app.screener.weinstein import analyze, InsufficientDataError
from tests.helpers import make_weekly_df, steady_uptrend, steady_downtrend, flat_sideways


def test_steady_uptrend_is_stage2():
    df = make_weekly_df(steady_uptrend())
    result = analyze(df)
    assert result.stage == 2


def test_steady_downtrend_is_stage4():
    df = make_weekly_df(steady_downtrend())
    result = analyze(df)
    assert result.stage == 4


def test_flat_sideways_is_stage1_or_3():
    df = make_weekly_df(flat_sideways())
    result = analyze(df)
    assert result.stage in (1, 3)


def test_insufficient_data_raises():
    df = make_weekly_df([100.0] * 10)
    with pytest.raises(InsufficientDataError):
        analyze(df)


def test_transition_1_to_2_detected_on_breakout_with_volume():
    base = flat_sideways(n=45, level=100, noise_std=0.3)
    # start_price por encima del ruido de la base para garantizar que el
    # cruce sobre la MA ocurra justo en la semana del pico de volumen.
    breakout = steady_uptrend(n=20, start_price=108, end_price=160)
    closes = base + breakout
    volumes = [1_000_000.0] * 45 + [3_500_000.0] + [1_200_000.0] * 19

    df = make_weekly_df(closes, volumes)
    result = analyze(df)

    assert result.stage == 2
    assert result.is_transition_1_to_2 is True


def test_breakout_without_volume_is_not_flagged_as_transition():
    base = flat_sideways(n=45, level=100, noise_std=0.3)
    breakout = steady_uptrend(n=20, start_price=108, end_price=160)
    closes = base + breakout
    # mismo precio que el test anterior, pero sin spike de volumen en el cruce
    volumes = [1_000_000.0] * 65

    df = make_weekly_df(closes, volumes)
    result = analyze(df)

    assert result.stage == 2
    assert result.is_transition_1_to_2 is False


def test_weeks_in_stage_counts_consecutive_weeks():
    df = make_weekly_df(steady_uptrend())
    result = analyze(df)
    assert result.weeks_in_stage >= 1
