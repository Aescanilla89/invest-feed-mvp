from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.orm import Base

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
# pool_pre_ping: Neon (Postgres serverless) cierra conexiones inactivas tras un
# rato -- sin esto, una sesión abierta mucho tiempo sin usarse (p.ej. durante
# una fase de un job que solo hace peticiones HTTP, no BD) revienta con
# "SSL connection has been closed unexpectedly" al primer query siguiente.
# pre_ping hace un SELECT 1 barato antes de reusar la conexión del pool y la
# reconecta transparentemente si ya no es válida.
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Columns added after initial deploy that create_all() won't add to existing tables.
_ADD_COLUMN_MIGRATIONS = [
    "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS weinstein_rsi FLOAT NOT NULL DEFAULT 50.0",
    "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS weinstein_ma_slope_pct FLOAT NOT NULL DEFAULT 0.0",
    "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS weinstein_relative_volume FLOAT NOT NULL DEFAULT 0.0",
    "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS strategies JSONB DEFAULT '{}'",
    "ALTER TABLE portfolio_positions ADD COLUMN IF NOT EXISTS signal_date DATE",
    "ALTER TABLE portfolio_positions ADD COLUMN IF NOT EXISTS exit_signal_date DATE",
    "ALTER TABLE tickers ADD COLUMN IF NOT EXISTS last_daily_close FLOAT",
    "ALTER TABLE tickers ADD COLUMN IF NOT EXISTS last_daily_price_date DATE",
    "ALTER TABLE explanations ADD COLUMN IF NOT EXISTS catalyst_ids_at_generation VARCHAR(255)",
    # Las explicaciones IA a veces superan 1000 caracteres (visto en producción,
    # p.ej. ~1800 para BNY) y el varchar(1000) truncaba con
    # StringDataRightTruncation, abortando el job diario antes de update_portfolio.
    "ALTER TABLE explanations ALTER COLUMN text TYPE TEXT",
]


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _run_column_migrations()


def _run_column_migrations() -> None:
    """Idempotent ALTER TABLE statements for columns added after initial deploy.
    IF NOT EXISTS makes each statement a no-op on Postgres if the column already exists;
    SQLite doesn't support IF NOT EXISTS, so we skip silently on error there."""
    is_sqlite = settings.database_url.startswith("sqlite")
    with engine.begin() as conn:
        for stmt in _ADD_COLUMN_MIGRATIONS:
            if is_sqlite:
                try:
                    conn.execute(text(stmt.replace(" IF NOT EXISTS", "")))
                except Exception:
                    pass  # column already exists
            else:
                conn.execute(text(stmt))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
