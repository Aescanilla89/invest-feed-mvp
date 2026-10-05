from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.jobs import detect_catalysts, run_screener, update_institutional, update_portfolio
from app.screener import universe
from scripts import run_daily_jobs


@pytest.fixture
def pipeline(monkeypatch):
    # No database, network, portfolio or institutional writes.
    from app.core import db
    monkeypatch.setattr(db, "init_db", Mock())
    monkeypatch.setattr(run_daily_jobs, "date", SimpleNamespace(today=lambda: date(2026, 10, 4)))
    monkeypatch.setenv("FORCE_INSTITUTIONAL", "false")
    calls = []
    monkeypatch.setattr(detect_catalysts, "run", lambda: calls.append("catalysts"))
    monkeypatch.setattr(universe, "get_universe", lambda: {"test": ["TEST"]})
    monkeypatch.setattr(run_screener, "run", lambda symbols: calls.append(("screener", symbols)))
    portfolio = Mock(side_effect=AssertionError("Retired portfolio must not run"))
    monkeypatch.setattr(update_portfolio, "run", portfolio)
    monkeypatch.setattr(update_institutional, "run", Mock())
    return calls, portfolio


def test_daily_pipeline_runs_dashboard_without_portfolio(pipeline):
    calls, portfolio = pipeline
    run_daily_jobs.main()
    assert calls == ["catalysts", ("screener", {"test": ["TEST"]})]
    portfolio.assert_not_called()


def test_dashboard_failure_still_fails_the_daily_job(pipeline, monkeypatch):
    monkeypatch.setattr(run_screener, "run", Mock(side_effect=RuntimeError("Screener failed")))
    with pytest.raises(SystemExit) as exc:
        run_daily_jobs.main()
    assert exc.value.code == 1


def test_explanations_receive_computed_strategy_details(monkeypatch):
    details = {"lynch": {"passed": True, "score": 80, "details": "Test evidence"}}
    item = run_screener.ScreenedTicker(
        ticker=SimpleNamespace(symbol="TEST"),
        score=SimpleNamespace(combined_score=80),
        weinstein_result=SimpleNamespace(stage=2),
        criteria={}, signal_type="weinstein", strategies=details,
    )
    explainer = object()
    monkeypatch.setattr(run_screener, "ClaudeExplainer", lambda: explainer)
    generate = Mock(return_value="Explanation")
    monkeypatch.setattr(run_screener.ai_cache, "get_or_create_explanation", generate)
    db = Mock()
    run_screener._generate_explanations(db, date(2026, 10, 4), [item])
    generate.assert_called_once_with(
        db, item.ticker, date(2026, 10, 4), 80,
        item.weinstein_result, item.criteria, explainer,
        signal_type="weinstein", strategy_details=details,
    )
    db.commit.assert_called_once()
    db.rollback.assert_not_called()
