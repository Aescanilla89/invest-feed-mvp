from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes.opportunities import _first_detected_dates, _first_detected_performance
from app.models.orm import Base, Opportunity, PriceSnapshot, Ticker


def _opportunity(ticker_id: int, run_date: date, score: int) -> Opportunity:
    return Opportunity(
        ticker_id=ticker_id,
        run_date=run_date,
        weinstein_stage=2,
        weinstein_transition=False,
        weeks_in_stage=10,
        canslim_criteria={},
        canslim_score=0,
        canslim_verifiable_count=0,
        canslim_passed_count=0,
        combined_score=score,
        risk_bucket="medio",
        strategies={},
    )


def test_first_detected_date_ignores_initial_screening_below_opportunity_cutoff():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Ticker(symbol="TEST", name="Test", universe="sp500"))
        db.flush()
        db.add_all([
            _opportunity(1, date(2025, 9, 5), 62),
            _opportunity(1, date(2025, 10, 3), 79),
            _opportunity(1, date(2025, 11, 5), 82),
        ])
        db.commit()
        assert _first_detected_dates(db, {1}) == {1: date(2025, 11, 5)}


def test_first_detected_performance_uses_first_close_on_or_after_detection():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        ticker = Ticker(
            symbol="TEST",
            name="Test",
            universe="sp500",
            last_daily_close=120.0,
            last_daily_price_date=date(2025, 11, 21),
        )
        db.add(ticker)
        db.flush()
        opportunity = _opportunity(ticker.id, date(2025, 11, 21), 82)
        db.add(opportunity)
        db.add_all([
            PriceSnapshot(ticker_id=ticker.id, date=date(2025, 11, 4), open=90, high=90, low=90, close=90, volume=1),
            PriceSnapshot(ticker_id=ticker.id, date=date(2025, 11, 7), open=100, high=100, low=100, close=100, volume=1),
            PriceSnapshot(ticker_id=ticker.id, date=date(2025, 11, 14), open=115, high=115, low=115, close=115, volume=1),
        ])
        db.commit()

        result = _first_detected_performance(
            db,
            [(opportunity, ticker)],
            {ticker.id: date(2025, 11, 5)},
        )

        assert result[ticker.id] == {
            "first_detected_price": 100.0,
            "current_price": 120.0,
            "return_since_first_detected_pct": 20.0,
        }


def test_first_detected_performance_returns_no_percentage_without_price_history():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        ticker = Ticker(symbol="TEST", name="Test", universe="sp500")
        db.add(ticker)
        db.flush()
        opportunity = _opportunity(ticker.id, date(2025, 11, 5), 82)
        db.add(opportunity)
        db.commit()

        result = _first_detected_performance(db, [(opportunity, ticker)], {})

        assert result[ticker.id] == {
            "first_detected_price": None,
            "current_price": None,
            "return_since_first_detected_pct": None,
        }
