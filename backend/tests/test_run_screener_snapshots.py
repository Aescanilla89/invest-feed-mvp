from datetime import date

import pandas as pd
import pytest

from app.jobs.run_screener import _upsert_price_snapshots
from app.models.orm import PriceSnapshot, Ticker


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


@pytest.fixture
def ticker(db_session):
    t = Ticker(symbol="TEST", universe="sp500")
    db_session.add(t)
    db_session.commit()
    return t


def _weekly_df(rows: list[tuple[str, float, float, float, float, float]]) -> pd.DataFrame:
    """rows: (fecha_iso, open, high, low, close, volume)."""
    df = pd.DataFrame(
        [{"Open": o, "High": h, "Low": l, "Close": c, "Volume": v} for _, o, h, l, c, v in rows],
        index=pd.to_datetime([d for d, *_ in rows]),
    )
    return df


class TestUpsertPriceSnapshots:

    def test_inserts_new_rows(self, db_session, ticker):
        weekly = _weekly_df([("2026-01-02", 100.0, 105.0, 99.0, 103.0, 1000.0)])
        n = _upsert_price_snapshots(db_session, ticker, weekly)
        db_session.commit()
        assert n == 1
        row = db_session.query(PriceSnapshot).filter_by(ticker_id=ticker.id).one()
        assert row.close == 103.0

    def test_updates_current_week_row_instead_of_freezing_it(self, db_session, ticker):
        # Lunes: el cron ve la semana en curso con un solo día de datos.
        monday_only = _weekly_df([("2026-01-02", 100.0, 102.0, 99.0, 101.0, 500.0)])
        _upsert_price_snapshots(db_session, ticker, monday_only)
        db_session.commit()

        # Miércoles: la MISMA fecha de semana (viernes de esa semana, sin
        # cambiar), pero ahora con 3 días de datos -- el título se desplomó.
        # Antes del fix esto se ignoraba (la fecha ya existía); ahora debe
        # ACTUALIZAR la fila con el cierre real más reciente.
        wednesday_update = _weekly_df([("2026-01-02", 100.0, 102.0, 70.0, 72.0, 900.0)])
        n = _upsert_price_snapshots(db_session, ticker, wednesday_update)
        db_session.commit()

        assert n == 1  # contó como "cambio", aunque sea un update no un insert
        row = db_session.query(PriceSnapshot).filter_by(ticker_id=ticker.id).one()
        assert row.close == 72.0  # refleja el desplome, no se quedó congelado en 101
        assert row.low == 70.0
        assert row.volume == 900.0

    def test_never_touches_a_week_once_a_newer_week_appears(self, db_session, ticker):
        week1 = _weekly_df([("2026-01-02", 100.0, 102.0, 99.0, 101.0, 500.0)])
        _upsert_price_snapshots(db_session, ticker, week1)
        db_session.commit()

        # Llega la semana siguiente -- la primera semana ya no es "la última
        # fila del batch" y debe quedar congelada para siempre, aunque el
        # batch la siga incluyendo (lookback de varias semanas).
        week1_and_2 = _weekly_df([
            ("2026-01-02", 100.0, 102.0, 99.0, 101.0, 500.0),  # semana cerrada, no debe cambiar
            ("2026-01-09", 101.0, 110.0, 95.0, 108.0, 700.0),  # semana en curso, nueva
        ])
        n = _upsert_price_snapshots(db_session, ticker, week1_and_2)
        db_session.commit()

        assert n == 1  # solo la fila nueva; la primera no se toca aunque venga en el batch
        rows = {r.date: r for r in db_session.query(PriceSnapshot).filter_by(ticker_id=ticker.id).all()}
        assert rows[date(2026, 1, 2)].close == 101.0  # intacta
        assert rows[date(2026, 1, 9)].close == 108.0  # nueva, semana en curso
