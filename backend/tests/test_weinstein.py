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


def _make_clean_stage1_to_2_data(volume_at_crossover: float) -> "pd.DataFrame":
    """Construye datos OHLCV semanales con una transición Stage 1->2 limpia.

    Diseño determinista (sin ruido) que garantiza:
    - Toda la fase base tiene close < MA30 (downtrend suaviza la MA por encima)
    - Última semana de la base: Stage 1 (slope ≈ 0%)
    - Semana del breakout: crossover precio/MA30, Stage 2
    - El spike de volumen cae exactamente en la semana del cruce
    """
    # Bajada moderada: MA30 queda por encima de 95 durante toda la base
    initial_down = steady_downtrend(n=30, start_price=120, end_price=100)
    # Base plana SIN ruido en 95 (< MA30 que desciende de ~110 a 95.0).
    # Tras 35 semanas de base, MA30 converge a 95.0 con slope ≈ 0% → Stage 1.
    flat_base = [95.0] * 35
    breakout = steady_uptrend(n=20, start_price=130, end_price=180)
    closes = initial_down + flat_base + breakout  # 85 semanas en total
    # Spike de volumen en la semana 66 (índice 65) = primera semana del breakout
    volumes = [1_000_000.0] * 65 + [volume_at_crossover] + [1_200_000.0] * 19
    return make_weekly_df(closes, volumes)


def test_transition_1_to_2_detected_on_breakout_with_volume():
    df = _make_clean_stage1_to_2_data(volume_at_crossover=3_500_000.0)
    result = analyze(df)
    assert result.stage == 2
    assert result.is_transition_1_to_2 is True


def test_breakout_without_volume_is_not_flagged_as_transition():
    # Misma estructura de precios, pero sin spike de volumen en el cruce
    df = _make_clean_stage1_to_2_data(volume_at_crossover=1_000_000.0)
    result = analyze(df)
    assert result.stage == 2
    assert result.is_transition_1_to_2 is False


def test_weeks_in_stage_counts_consecutive_weeks():
    df = make_weekly_df(steady_uptrend())
    result = analyze(df)
    assert result.weeks_in_stage >= 1


def test_breakout_with_delayed_volume_not_flagged_as_transition():
    """Volumen alto llega DESPUÉS del cruce precio/MA30 (no en la semana exacta).
    Con la lógica estricta de ventana exacta, NO debe detectarse como transición 1->2."""
    base = flat_sideways(n=45, level=100, noise_std=0.3)
    breakout = steady_uptrend(n=20, start_price=108, end_price=160)
    closes = base + breakout
    # Volumen alto en la semana 50 (5 semanas después del cruce en semana 45)
    volumes = [1_000_000.0] * 50 + [3_500_000.0] + [1_200_000.0] * 14
    df = make_weekly_df(closes, volumes)
    result = analyze(df)
    assert result.stage == 2
    assert result.is_transition_1_to_2 is False
