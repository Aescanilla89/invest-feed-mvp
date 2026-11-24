from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes import opportunities
from app.models.orm import Base, Explanation, Ticker
from tests.test_opportunity_detection_date import _opportunity

TODAY = date(2026, 11, 24)


@pytest.fixture
def db(monkeypatch):
    class FrozenDate(date):
        @classmethod
        def today(cls):
            return TODAY

    monkeypatch.setattr(opportunities, 'date', FrozenDate)
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def add(db, symbol, observations, risk='medio', sector='Technology'):
    ticker = Ticker(symbol=symbol, universe='sp500', sector=sector)
    db.add(ticker)
    db.flush()
    for days_ago, score in observations:
        row = _opportunity(ticker.id, TODAY - timedelta(days=days_ago), score)
        row.risk_bucket = risk
        db.add(row)
    db.commit()
    return ticker


def feed(db, **filters):
    return opportunities.opportunity_feed(featured_limit=100, strategy_limit=6, risk=filters.get('risk'), sector=filters.get('sector'), db=db)


def test_retains_dropped_and_missing_opportunities_with_latest_analysis(db):
    active = add(db, 'ACTIVE', [(10, 85), (0, 82)])
    inactive = add(db, 'INACTIVE', [(12, 90), (0, 65)])
    add(db, 'MISSING', [(2, 83)])
    db.add_all([
        Explanation(ticker_id=inactive.id, run_date=TODAY - timedelta(days=12), combined_score_at_generation=90, text='Old positive explanation', model_used='test'),
        Explanation(ticker_id=active.id, run_date=TODAY, combined_score_at_generation=82, text='Current explanation', model_used='test'),
    ])
    db.commit()
    result = feed(db)
    assert [o.ticker for o in result.featured] == ['ACTIVE']
    recent = {o.ticker: o for o in result.recent}
    assert set(recent) == {'ACTIVE', 'INACTIVE', 'MISSING'}
    assert recent['ACTIVE'].tracking_status == 'active'
    assert recent['ACTIVE'].explanation == 'Current explanation'
    assert recent['INACTIVE'].tracking_status == 'inactive'
    assert recent['INACTIVE'].combined_score == 65
    assert recent['INACTIVE'].detected_score == 90
    assert recent['INACTIVE'].explanation is None
    assert recent['INACTIVE'].last_detected_date == TODAY - timedelta(days=12)
    assert recent['MISSING'].tracking_status == 'pending'
    assert recent['MISSING'].last_updated == TODAY - timedelta(days=2)


def test_window_boundaries_deduplication_and_repeat_detections(db):
    add(db, 'BOUNDARY', [(14, 80), (0, 70)])
    add(db, 'EXPIRED', [(15, 90), (0, 70)])
    add(db, 'REPEAT', [(40, 90), (4, 82), (1, 85), (0, 83)])
    add(db, 'NEVER', [(0, 79)])
    add(db, 'FUTURE', [(-1, 90)])
    result = feed(db)
    assert [o.ticker for o in result.recent] == ['REPEAT', 'BOUNDARY']
    assert result.recent[0].first_detected_date == TODAY - timedelta(days=40)
    assert result.recent[0].last_detected_date == TODAY


def test_history_uses_calendar_today_when_pipeline_is_stale(db):
    add(db, 'STALE', [(16, 90)])
    assert feed(db).recent == []


def test_old_active_opportunity_remains_in_history_but_is_pending_update(db):
    add(db, 'OLD', [(40, 90), (3, 83)])
    result = feed(db)
    assert len(result.recent) == 1
    assert result.recent[0].tracking_status == 'pending'


def test_filters_apply_to_history_using_current_risk(db):
    add(db, 'TECH', [(1, 90), (0, 70)], risk='alto')
    add(db, 'HEALTH', [(0, 85)], risk='bajo', sector='Healthcare')
    assert [o.ticker for o in feed(db, risk='alto', sector='Technology').recent] == ['TECH']
    assert feed(db, risk='bajo', sector='Technology').recent == []


def test_history_is_not_limited_by_current_featured_ranking(db):
    for i in range(25):
        add(db, f'T{i:02}', [(0, 80)])
    result = opportunities.opportunity_feed(featured_limit=2, strategy_limit=1, risk=None, sector=None, db=db)
    assert len(result.featured) == 2
    assert len(result.recent) == 25


def test_empty_feed_has_explicit_empty_history(db):
    result = feed(db)
    assert result.recent == []
    assert result.featured == []
