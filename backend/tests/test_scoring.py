from app.screener.canslim import CriterionResult
from app.screener.scoring import compute_combined_score, compute_risk_bucket
from app.screener.weinstein import WeinsteinResult
from tests.helpers import make_weekly_df, steady_uptrend, steady_downtrend, flat_sideways


def _all_pass_criteria() -> dict[str, CriterionResult]:
    return {k: CriterionResult(True, "ok") for k in ["C", "A", "N", "S", "L", "M"]} | {
        "I": CriterionResult(None, "no verificable")
    }


def _all_fail_criteria() -> dict[str, CriterionResult]:
    return {k: CriterionResult(False, "no") for k in ["C", "A", "N", "S", "L", "M"]} | {
        "I": CriterionResult(None, "no verificable")
    }


def test_stage2_transition_with_all_canslim_passing_scores_high():
    weinstein = WeinsteinResult(stage=2, weeks_in_stage=2, ma_slope_pct=0.03, relative_volume=2.0, is_transition_1_to_2=True)
    df = make_weekly_df(steady_uptrend())
    score = compute_combined_score(weinstein, _all_pass_criteria(), df)
    assert score.combined_score == 100
    assert score.canslim_verifiable_count == 6
    assert score.canslim_passed_count == 6


def test_stage4_with_all_canslim_failing_scores_zero():
    weinstein = WeinsteinResult(stage=4, weeks_in_stage=10, ma_slope_pct=-0.03, relative_volume=0.8, is_transition_1_to_2=False)
    df = make_weekly_df(steady_downtrend())
    score = compute_combined_score(weinstein, _all_fail_criteria(), df)
    assert score.combined_score == 0


def test_i_criterion_excluded_from_canslim_denominator():
    weinstein = WeinsteinResult(stage=2, weeks_in_stage=2, ma_slope_pct=0.03, relative_volume=2.0, is_transition_1_to_2=False)
    df = make_weekly_df(steady_uptrend())
    criteria = _all_pass_criteria()
    score = compute_combined_score(weinstein, criteria, df)
    # 6 criterios verificables (todo menos I), todos pasan -> 50/50 puntos CAN SLIM
    assert score.canslim_component == 50
    assert score.canslim_verifiable_count == 6


def test_no_verifiable_criteria_gives_zero_canslim_component():
    weinstein = WeinsteinResult(stage=2, weeks_in_stage=2, ma_slope_pct=0.03, relative_volume=2.0, is_transition_1_to_2=False)
    df = make_weekly_df(steady_uptrend())
    criteria = {k: CriterionResult(None, "sin datos") for k in ["C", "A", "N", "S", "L", "I", "M"]}
    score = compute_combined_score(weinstein, criteria, df)
    assert score.canslim_component == 0
    assert score.canslim_verifiable_count == 0


def test_risk_bucket_low_volatility():
    df = make_weekly_df(flat_sideways(n=20, level=100, noise_std=0.05))
    assert compute_risk_bucket(df) == "bajo"


def test_risk_bucket_unknown_with_insufficient_history():
    df = make_weekly_df([100.0, 101.0, 102.0])
    assert compute_risk_bucket(df) == "desconocido"
