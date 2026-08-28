from datetime import date
from types import SimpleNamespace

import pytest

from app.jobs.update_portfolio import (
    _closes_below_ma,
    _exit_signal,
    _is_exceptional,
    _market_regime_stage_ok,
    _pick_top_for_method,
    _trailing_stop_pct,
    _trailing_stop_signal,
)


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
    # encima de la MA30 -- no es una ruptura real, no debe disparar salida.
    stage2 = _opp(weinstein_stage=2)
    stage3 = _opp(weinstein_stage=3)
    assert _exit_signal([stage2, stage2]) is None
    assert _exit_signal([stage3, stage3]) is None


def test_exit_signal_requires_two_consecutive_weeks_below_ma30():
    # Una sola semana por debajo de la MA30 (ruido, no ruptura real) no basta
    # -- es el bug real que generaba churn: CMCSA entró y salió 11 veces en
    # un año porque su precio cotiza pegado a la MA30 y la cruza a menudo
    # por una sola semana. Hacen falta 2 semanas CONSECUTIVAS por debajo.
    stage4 = _opp(weinstein_stage=4)
    stage2 = _opp(weinstein_stage=2)
    assert _exit_signal([stage4, stage2]) is None  # solo la última semana rompió
    assert _exit_signal([stage4, stage4]) == "weinstein_stage_4"  # 2 semanas seguidas


def test_exit_signal_holds_with_insufficient_history():
    # Con menos de 2 Opportunity para el ticker no se puede confirmar una
    # ruptura -- se mantiene la posición.
    assert _exit_signal([]) is None
    assert _exit_signal([_opp(weinstein_stage=4)]) is None


def test_closes_below_ma_requires_two_consecutive_weeks():
    # Mismo criterio anti-ruido que el stop de momentum (MA30): una sola
    # semana marginal por debajo de la media no confirma ruptura.
    window = 10
    steady = [100.0] * window  # MA estable en 100
    only_last_week_below = steady + [95.0]  # 1 semana por debajo
    two_weeks_below = steady + [95.0, 94.0]  # 2 semanas consecutivas
    assert _closes_below_ma(only_last_week_below, window) is False
    assert _closes_below_ma(two_weeks_below, window) is True


def test_closes_below_ma_insufficient_history_returns_none():
    assert _closes_below_ma([100.0, 99.0], window_weeks=40) is None


def test_trailing_stop_pct_momentum_vs_fundamentals():
    # 8% para roturas momentum (early_stage2/minervini, el stop clásico no
    # negociable de Minervini/O'Neil) vs 15% para tesis de calidad/valor a
    # más plazo (lynch/berkshire/dividendos).
    assert _trailing_stop_pct("early_stage2") == 0.08
    assert _trailing_stop_pct("minervini") == 0.08
    assert _trailing_stop_pct("lynch") == 0.15
    assert _trailing_stop_pct("berkshire") == 0.15
    assert _trailing_stop_pct("dividendos") == 0.15


@pytest.fixture
def db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models.orm import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _add_snapshot(db_session, ticker_id, snap_date, close):
    from app.models.orm import PriceSnapshot

    db_session.add(PriceSnapshot(
        ticker_id=ticker_id, date=snap_date, open=close, high=close, low=close, close=close, volume=1.0,
    ))
    db_session.commit()


def test_trailing_stop_signal_triggers_at_threshold_from_entry(db_session):
    # Entrada a 100, stop momentum al 8% -> sin subidas previas, el "máximo
    # desde la entrada" sigue siendo el propio entry_price, así que dispara
    # con cierre <= 92, sin esperar confirmación de 2 semanas (a diferencia
    # del stop de tendencia).
    _add_snapshot(db_session, 1, date(2026, 1, 5), 92.0)
    result = _trailing_stop_signal(
        db_session, ticker_id=1, entry_price=100.0, entry_date=date(2026, 1, 5), method="minervini", as_of=date(2026, 1, 5),
    )
    assert result == (date(2026, 1, 5), "trailing_stop_8pct")


def test_trailing_stop_signal_does_not_trigger_above_threshold(db_session):
    _add_snapshot(db_session, 1, date(2026, 1, 5), 93.0)
    assert _trailing_stop_signal(
        db_session, ticker_id=1, entry_price=100.0, entry_date=date(2026, 1, 5), method="minervini", as_of=date(2026, 1, 5),
    ) is None


def test_trailing_stop_signal_uses_wider_threshold_for_fundamentals(db_session):
    # lynch/berkshire/dividendos: 15% de margen, un cierre a -10% no dispara.
    _add_snapshot(db_session, 1, date(2026, 1, 5), 90.0)
    assert _trailing_stop_signal(
        db_session, ticker_id=1, entry_price=100.0, entry_date=date(2026, 1, 5), method="lynch", as_of=date(2026, 1, 5),
    ) is None
    _add_snapshot(db_session, 1, date(2026, 1, 12), 84.0)
    result = _trailing_stop_signal(
        db_session, ticker_id=1, entry_price=100.0, entry_date=date(2026, 1, 5), method="lynch", as_of=date(2026, 1, 12),
    )
    assert result == (date(2026, 1, 12), "trailing_stop_15pct")


def test_trailing_stop_signal_no_history_returns_none(db_session):
    assert _trailing_stop_signal(
        db_session, ticker_id=1, entry_price=100.0, entry_date=date(2026, 1, 5), method="minervini", as_of=date(2026, 1, 5),
    ) is None


def test_trailing_stop_signal_follows_the_high_not_the_entry(db_session):
    # El caso que motiva el trailing stop: la acción sube 50% desde la
    # entrada y luego cae un 8% desde ese máximo (no desde la entrada) --
    # debe disparar aunque el precio siga muy por encima del entry_price,
    # para proteger la ganancia ya conseguida en vez de dejarla evaporarse.
    _add_snapshot(db_session, 1, date(2026, 1, 5), 100.0)   # entrada
    _add_snapshot(db_session, 1, date(2026, 2, 2), 150.0)   # sube 50%
    _add_snapshot(db_session, 1, date(2026, 2, 9), 137.0)   # cae 8.7% desde el máximo (150), sigue +37% vs entrada
    result = _trailing_stop_signal(
        db_session, ticker_id=1, entry_price=100.0, entry_date=date(2026, 1, 5), method="minervini", as_of=date(2026, 2, 9),
    )
    assert result == (date(2026, 2, 9), "trailing_stop_8pct")


def test_trailing_stop_signal_holds_if_pullback_from_high_is_small(db_session):
    # Misma subida a 150, pero un pullback pequeño (150 -> 140, -6.7%) no
    # dispara el 8% -- la posición sigue abierta.
    _add_snapshot(db_session, 1, date(2026, 1, 5), 100.0)
    _add_snapshot(db_session, 1, date(2026, 2, 2), 150.0)
    _add_snapshot(db_session, 1, date(2026, 2, 9), 140.0)
    assert _trailing_stop_signal(
        db_session, ticker_id=1, entry_price=100.0, entry_date=date(2026, 1, 5), method="minervini", as_of=date(2026, 2, 9),
    ) is None


def test_market_regime_only_allows_entries_in_stage_2():
    # Filtro de régimen (Weinstein/O'Neil): solo se abren posiciones nuevas
    # si el índice general también está en tendencia alcista -- comprar
    # roturas individuales con el mercado en techo/caída va contra la propia
    # lógica del método.
    assert _market_regime_stage_ok(2) is True
    assert _market_regime_stage_ok(1) is False
    assert _market_regime_stage_ok(3) is False
    assert _market_regime_stage_ok(4) is False
