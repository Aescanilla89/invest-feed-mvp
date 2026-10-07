from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.market_desk import MarketDeskResponse, WatchEvent, get_market_desk
from app.models.orm import Catalyst

router = APIRouter(prefix="/market-desk", tags=["market-desk"])


@router.get("", response_model=MarketDeskResponse)
def market_desk(db: Session = Depends(get_db)) -> MarketDeskResponse:
    """Return a cached, independently failing market briefing."""
    result = get_market_desk()
    try:
        upcoming = (db.query(Catalyst)
                    .filter(Catalyst.catalyst_type == "macro_data", Catalyst.detected_date >= date.today(), Catalyst.detected_date <= date.today() + timedelta(days=30))
                    .order_by(Catalyst.detected_date.asc()).limit(6).all())
    except Exception:
        upcoming = []
    result.watch_next = [WatchEvent(date=c.detected_date.isoformat(), title=c.title, source="FRED release calendar") for c in upcoming]
    return result
