from types import SimpleNamespace

from app.jobs.update_portfolio import _exit_signal, _is_exceptional, _pick_top_for_method


def _opp(**kwargs):
    defaults = dict(
        ticker_id=1,
        weinstein_stage=2,
        weinstein_transition=False,
        weeks_in_stage=10,
        combined_score=50,
        canslim_criteria={},
        strategies={},
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_minervini_exceptional_requires_score_100():
    weak = _opp(strategies={"minervini": {"passed": True, "score": 86}})
    strong = _opp(strategies={"minervini": {"passed": True, "score": 100}})
    assert _is_exceptional(weak, "minervini") is False
    assert _is_exceptional(strong, "minervini") is True


def test_berkshire_exceptional_requires_score_100():
    weak = _opp(strategies={"berkshire": {"passed": True, "score": 80}})
    strong = _opp(strategies={"berkshire": {"passed": True, "score": 100}})
    assert _is_exceptional(weak, "berkshire") is False
    assert _is_exceptional(strong, "berkshire") is True


def test_lynch_and_dividendos_use_plain_passed():
    passing = _opp(strategies={"lynch": {"passed": True, "score": 55}})
    failing = _opp(strategies={"lynch": {"passed": False, "score": 20}})
    assert _is_exceptional(passing, "lynch") is True
    assert _is_exceptional(failing, "lynch") is False


def test_early_stage2_requires_signal_both():
    weinstein_only = _opp(weinstein_transition=True, weeks_in_stage=2, canslim_criteria={
        "N": {"value": False}, "C": {"value": True},
    })
    both = _opp(weinstein_transition=True, weeks_in_stage=2, canslim_criteria={
        "N": {"value": True}, "C": {"value": True}, "A": {"value": True},
    })
    assert _is_exceptional(weinstein_only, "early_stage2") is False
    assert _is_exceptional(both, "early_stage2") is True


def test_pick_top_for_method_picks_highest_score():
    low = _opp(ticker_id=1, strategies={"lynch": {"passed": True, "score": 40}})
    high = _opp(ticker_id=2, strategies={"lynch": {"passed": True, "score": 90}})
    top = _pick_top_for_method([low, high], "lynch")
    assert top.ticker_id == 2


def test_pick_top_for_method_early_stage2_prefers_fewer_weeks():
    older = _opp(ticker_id=1, weeks_in_stage=5, combined_score=90)
    newer = _opp(ticker_id=2, weeks_in_stage=1, combined_score=40)
    top = _pick_top_for_method([older, newer], "early_stage2")
    assert top.ticker_id == 2


def test_pick_top_for_method_returns_none_without_candidates():
    assert _pick_top_for_method([], "minervini") is None
    assert _pick_top_for_method([_opp(weinstein_stage=1)], "early_stage2") is None


def test_exit_signal_early_stage2_follows_weinstein_stage():
    still_stage2 = _opp(weinstein_stage=2)
    broke_stage2 = _opp(weinstein_stage=3)
    assert _exit_signal(still_stage2, "early_stage2") is None
    assert _exit_signal(broke_stage2, "early_stage2") == "weinstein_stage_3"


def test_exit_signal_other_methods_ignore_weinstein_stage():
    # Rompe Stage 2 pero lynch sigue pasando -- no debe salir por eso, es el
    # bug real que generaba churn (entradas/salidas cada ~2 semanas en el
    # mismo ticker sin ganar ni perder nada en conjunto).
    still_passing = _opp(weinstein_stage=3, strategies={"lynch": {"passed": True, "score": 80}})
    assert _exit_signal(still_passing, "lynch") is None


def test_exit_signal_other_methods_exit_when_strategy_stops_passing():
    no_longer_passing = _opp(weinstein_stage=2, strategies={"berkshire": {"passed": False, "score": 40}})
    assert _exit_signal(no_longer_passing, "berkshire") == "berkshire_no_longer_passes"


def test_exit_signal_other_methods_hold_when_data_missing():
    # passed=None (no verificable) nunca se trata como señal negativa --
    # mismo principio que el resto del screener (canslim.py, strategies.py).
    no_data = _opp(strategies={})
    assert _exit_signal(no_data, "dividendos") is None
