from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes.opportunities import _first_detected_dates
from app.models.orm import Base, Opportunity, Ticker


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
