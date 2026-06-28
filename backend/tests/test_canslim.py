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


# ---------------------------------------------------------------------------
# Criterio C — EPS trimestral + aceleración
# ---------------------------------------------------------------------------

def test_evaluate_c_passes_above_threshold_no_accel_data():
    # Sin raw_quarterly_eps suficiente: solo se verifica el nivel de crecimiento
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


def test_evaluate_c_passes_with_acceleration():
    # Q0: EPS 1.50 vs Q0-4: EPS 1.00 → +50% YoY
    # Q1: EPS 1.30 vs Q1-4: EPS 1.00 → +30% YoY
    # Aceleración: 50% > 30% → True
    eps = [1.00, 1.00, 1.00, 1.00, 1.00, 1.30, 1.50]
    fundamentals = FundamentalData(
        eps_quarterly_yoy_growth=(1.50 - 1.00) / 1.00,
        eps_annual_growth=None,
        raw_quarterly_eps=eps,
        raw_annual_eps=[],
    )
    assert evaluate_c(fundamentals).value is True


def test_evaluate_c_fails_decelerating_eps():
    # Q0: EPS 1.30 vs Q0-4: EPS 1.00 → +30% YoY (supera umbral)
    # Q1: EPS 1.50 vs Q1-4: EPS 1.00 → +50% YoY (más que Q0)
    # Desaceleración: 30% < 50% → False
    eps = [1.00, 1.00, 1.00, 1.00, 1.00, 1.50, 1.30]
    fundamentals = FundamentalData(
        eps_quarterly_yoy_growth=(1.30 - 1.00) / 1.00,
        eps_annual_growth=None,
        raw_quarterly_eps=eps,
        raw_annual_eps=[],
    )
    assert evaluate_c(fundamentals).value is False


# ---------------------------------------------------------------------------
# Criterio A — EPS anual + consistencia 3/5 años
# ---------------------------------------------------------------------------

def test_evaluate_a_passes_above_threshold_no_consistency_data():
    # Sin raw_annual_eps suficiente: solo se verifica el nivel
    fundamentals = FundamentalData(0.10, 0.40, [], [])
    assert evaluate_a(fundamentals).value is True


def test_evaluate_a_fails_below_threshold():
    fundamentals = FundamentalData(0.10, 0.10, [], [])
    assert evaluate_a(fundamentals).value is False


def test_evaluate_a_passes_with_3_of_5_positive_years():
    # Últimos 6 valores: 3 de 5 pares YoY son positivos
    # pares: (80,70)→+, (70,80)→-, (80,60)→+, (60,50)→+, (50,60)→-  => 3/5
    eps = [60.0, 50.0, 60.0, 80.0, 70.0, 80.0]
    growth = (80.0 - 70.0) / 70.0  # ≈ 14% -- por debajo del umbral 25%
    # Ajustamos para que growth >= 25%
    eps = [1.0, 1.0, 1.5, 2.0, 1.5, 2.0]
    growth = (2.0 - 1.5) / 1.5  # ≈ 33%
    fundamentals = FundamentalData(0.10, growth, [], eps)
    result = evaluate_a(fundamentals)
    assert result.value is True


def test_evaluate_a_fails_with_only_2_of_5_positive_years():
    # 2/5 años positivos → False (aunque crecimiento último año >= 25%)
    # Pares (2,1)→+, (1,2)→-, (2,3)→-, (3,2)→+, (2,1)→+... necesito exactamente 2
    # eps[-6...-1]: valores donde solo 2 de 5 pares sean positivos
    # pares [-1,-2], [-2,-3], [-3,-4], [-4,-5], [-5,-6]
    # eps = [3, 2, 1, 2, 1, 1.30]  → pares: (1.30,1)→+, (1,2)→-, (2,1)→+, (1,2)→-, (2,3)→-  = 2/5
    eps = [3.0, 2.0, 1.0, 2.0, 1.0, 1.30]
    growth = (1.30 - 1.0) / 1.0  # 30% >= 25%
    fundamentals = FundamentalData(0.10, growth, [], eps)
    result = evaluate_a(fundamentals)
    assert result.value is False


# ---------------------------------------------------------------------------
# Criterio N — ATH desde price_snapshots
# ---------------------------------------------------------------------------

def test_evaluate_n_new_high_with_volume_passes():
    closes = steady_uptrend(n=52, start_price=100, end_price=150)
    volumes = [1_000_000.0] * 51 + [2_500_000.0]
    df = make_weekly_df(closes, volumes)
    result = evaluate_n(df)
    assert result.value is True


def test_evaluate_n_far_from_high_fails():
    closes = flat_sideways(n=52, level=100, noise_std=0.2)
    df = make_weekly_df(closes)
    df.loc[df.index[-1], "Close"] = 80.0
    result = evaluate_n(df)
    assert result.value is False


def test_evaluate_n_uses_all_time_high_when_provided():
    # El cierre está cerca del máximo de las 52 semanas del DF,
    # pero lejos del ATH histórico real (200) → debe fallar
    closes = steady_uptrend(n=52, start_price=100, end_price=150)
    volumes = [1_000_000.0] * 51 + [2_500_000.0]
    df = make_weekly_df(closes, volumes)
    result = evaluate_n(df, all_time_high=200.0)
    # 150 / 200 = 75% < 98% → False (lejos del ATH histórico)
    assert result.value is False


def test_evaluate_n_passes_with_explicit_ath_match():
    # ATH = 151 (prácticamente igual al cierre actual de 150)
    closes = steady_uptrend(n=52, start_price=100, end_price=150)
    volumes = [1_000_000.0] * 51 + [2_500_000.0]
    df = make_weekly_df(closes, volumes)
    result = evaluate_n(df, all_time_high=151.0)
    # 150 / 151 = 99.3% > 98% Y volumen > 1.5x → True
    assert result.value is True


# ---------------------------------------------------------------------------
# Criterio L — RS Rating percentil vs universo
# ---------------------------------------------------------------------------

def test_evaluate_l_outperformance_fallback_benchmark():
    # Sin universe_returns: fallback a comparación vs benchmark
    ticker_df = make_weekly_df(steady_uptrend(n=60, start_price=100, end_price=200))
    benchmark_df = make_weekly_df(steady_uptrend(n=60, start_price=100, end_price=120))
    result = evaluate_l(ticker_df, benchmark_df)
    assert result.value is True


def test_evaluate_l_rs_rating_above_80_passes():
    # Ticker retorna 100%, universo con mayoría de retornos < 100% → RS Rating alto
    ticker_df = make_weekly_df(steady_uptrend(n=60, start_price=100, end_price=200))
    benchmark_df = make_weekly_df(steady_uptrend(n=60, start_price=100, end_price=110))
    # 95 tickers con retorno 0-50%, 5 con retorno > 100% → ticker en ~90 percentil
    universe_returns = [i * 0.5 / 95 for i in range(95)] + [1.1, 1.2, 1.3, 1.4, 1.5]
    result = evaluate_l(ticker_df, benchmark_df, universe_returns=universe_returns)
    assert result.value is True
    assert "RS Rating" in result.detail


def test_evaluate_l_rs_rating_below_80_fails():
    # Ticker retorna 10%, mayoría del universo retorna más → RS Rating bajo
    ticker_df = make_weekly_df(steady_uptrend(n=60, start_price=100, end_price=110))
    benchmark_df = make_weekly_df(steady_uptrend(n=60, start_price=100, end_price=110))
    # 90 tickers con retorno 20-100% (mejores que el ticker con 10%)
    universe_returns = [0.20 + i * 0.80 / 90 for i in range(90)] + [0.05] * 10
    result = evaluate_l(ticker_df, benchmark_df, universe_returns=universe_returns)
    assert result.value is False


# ---------------------------------------------------------------------------
# Criterio S / I / M — sin cambios, tests existentes se conservan
# ---------------------------------------------------------------------------

def test_evaluate_s_buyback_trend():
    signal = SupplySignal(is_buyback_trend=True, shares_outstanding_change_pct=-0.05, quarters_compared=4)
    assert evaluate_s(signal).value is True


def test_evaluate_s_none_when_no_sec_data():
    signal = SupplySignal(is_buyback_trend=None, shares_outstanding_change_pct=None, quarters_compared=0)
    assert evaluate_s(signal).value is None


def test_evaluate_i_none_when_no_data():
    assert evaluate_i(None).value is None


def test_evaluate_i_passes_in_valid_range():
    assert evaluate_i(0.60).value is True


def test_evaluate_i_fails_below_minimum():
    assert evaluate_i(0.10).value is False


def test_evaluate_i_fails_above_maximum():
    assert evaluate_i(0.95).value is False


def test_evaluate_m_stage2_benchmark_passes():
    benchmark_result = WeinsteinResult(stage=2, weeks_in_stage=5, ma_slope_pct=0.02, relative_volume=1.2, is_transition_1_to_2=False)
    assert evaluate_m(benchmark_result).value is True


def test_evaluate_m_stage4_benchmark_fails():
    benchmark_result = WeinsteinResult(stage=4, weeks_in_stage=5, ma_slope_pct=-0.02, relative_volume=1.2, is_transition_1_to_2=False)
    assert evaluate_m(benchmark_result).value is False
