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


def test_exit_signal_holds_through_stage_2_and_3():
    # Stage 3 es solo desaceleración del momentum con el precio TODAVÍA por
    # encima de la MA30 -- no es una ruptura real, no debe disparar salida
    # para ningún método (antes sí lo hacía, y generaba churn: CMCSA entró y
    # salió 13 veces en un año bajo Lynch sin ganar ni perder nada en conjunto).
    stage2 = _opp(weinstein_stage=2)
    stage3 = _opp(weinstein_stage=3)
    for method in ("early_stage2", "minervini", "lynch", "berkshire", "dividendos"):
        assert _exit_signal(stage2, method) is None
        assert _exit_signal(stage3, method) is None


def test_exit_signal_exits_on_ma30_breakdown_for_any_method():
    # Stage 1 o 4 = cierre por debajo de la MA30 -- el stop-loss dinámico
    # único, igual para las 5 estrategias.
    stage4 = _opp(weinstein_stage=4)
    stage1 = _opp(weinstein_stage=1)
    for method in ("early_stage2", "minervini", "lynch", "berkshire", "dividendos"):
        assert _exit_signal(stage4, method) == "weinstein_stage_4"
        assert _exit_signal(stage1, method) == "weinstein_stage_1"
