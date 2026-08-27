"""Modelos SQLAlchemy 2.0. Tipos elegidos para ser portables a Postgres
sin reescritura: nada de tipos específicos de SQLite, JSON vía
`sqlalchemy.JSON` (compila a TEXT en SQLite y a jsonb en Postgres).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Ticker(Base):
    __tablename__ = "tickers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    universe: Mapped[str] = mapped_column(String(32), nullable=False)  # "sp500" | "nasdaq100"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Último cierre diario (no semanal) -- solo para mostrar precio/rentabilidad
    # "de hoy" en la cartera pública; el análisis Weinstein/CAN SLIM sigue usando
    # exclusivamente los cierres semanales de PriceSnapshot.
    last_daily_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_daily_price_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    opportunities: Mapped[list["Opportunity"]] = relationship(back_populates="ticker")
    explanations: Mapped[list["Explanation"]] = relationship(back_populates="ticker")


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    __table_args__ = (UniqueConstraint("ticker_id", "date", name="uq_price_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)


class FundamentalSnapshot(Base):
    __tablename__ = "fundamental_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), nullable=False, index=True)
    period_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    eps_quarterly: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_yoy_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_qoq_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (UniqueConstraint("ticker_id", "run_date", name="uq_opportunity_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), nullable=False, index=True)
    run_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    weinstein_stage: Mapped[int] = mapped_column(Integer, nullable=False)
    weinstein_transition: Mapped[bool] = mapped_column(Boolean, nullable=False)
    weeks_in_stage: Mapped[int] = mapped_column(Integer, nullable=False)
    weinstein_ma_slope_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    weinstein_relative_volume: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    weinstein_rsi: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)

    # {"C": {"value": true, "detail": "Crecimiento EPS trimestral YoY: 30.0% ..."}, ...}
    canslim_criteria: Mapped[dict] = mapped_column(JSON, nullable=False)
    canslim_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-50
    canslim_verifiable_count: Mapped[int] = mapped_column(Integer, nullable=False)
    canslim_passed_count: Mapped[int] = mapped_column(Integer, nullable=False)

    combined_score: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    risk_bucket: Mapped[str] = mapped_column(String(16), nullable=False)

    # {"minervini": {"passed": bool|None, "score": int|None, "details": str}, "lynch": {...}, ...}
    strategies: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    ticker: Mapped["Ticker"] = relationship(back_populates="opportunities")


class InstitutionalHolding(Base):
    """Posición de una institución en un ticker para un trimestre dado.
    Poblada trimestralmente por update_institutional.py desde 13F-HR de SEC EDGAR."""
    __tablename__ = "institutional_holdings"
    __table_args__ = (
        UniqueConstraint("ticker_id", "quarter", "institution_cik", name="uq_inst_holding"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), nullable=False, index=True)
    quarter: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    institution_cik: Mapped[str] = mapped_column(String(20), nullable=False)
    institution_name: Mapped[str] = mapped_column(String(200), nullable=False)
    shares: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    value_usd_k: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class Explanation(Base):
    __tablename__ = "explanations"
    __table_args__ = (UniqueConstraint("ticker_id", "run_date", name="uq_explanation_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), nullable=False, index=True)
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    combined_score_at_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    # IDs de catalysts (comma-separated) vistos en el momento de generación --
    # si cambian respecto a la última explicación cacheada, se regenera aunque
    # el combined_score no haya cambiado (ver ai/cache.py).
    catalyst_ids_at_generation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    ticker: Mapped["Ticker"] = relationship(back_populates="explanations")


class Catalyst(Base):
    """Catalizador de inversión detectado diariamente.
    Puede estar ligado a un ticker de nuestro universo o ser un evento macro (ticker_id=None).
    source_id garantiza idempotencia: mismo catalizador no se inserta dos veces."""
    __tablename__ = "catalysts"
    __table_args__ = (UniqueConstraint("source_id", name="uq_catalyst_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker_id: Mapped[int | None] = mapped_column(ForeignKey("tickers.id"), nullable=True, index=True)
    detected_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    catalyst_type: Mapped[str] = mapped_column(String(32), nullable=False)  # "earnings" | "insider_buy"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    ticker: Mapped["Ticker | None"] = relationship(foreign_keys=[ticker_id])


class PortfolioPosition(Base):
    """Pick de la cartera pública (social proof): entra automáticamente cuando el
    top-1 diario de un método (early_stage2/minervini/lynch/berkshire/dividendos)
    cumple el umbral "excepcional" de ese método en `signal_date` (ver
    app/jobs/update_portfolio.py). Para no incurrir en look-ahead bias, la
    compra se ejecuta al precio de apertura del día hábil siguiente
    (`entry_date`), que es el primer momento realmente operable tras conocer
    la señal (confirmada con el cierre de `signal_date`).
    Se cierra automáticamente en cuanto el ticker deja de estar en Weinstein
    Stage 2 (rotura detectada con el cierre de `exit_signal_date`), ejecutando
    la venta a la apertura del día hábil siguiente (`exit_date`), por el mismo
    motivo anti-look-ahead."""
    __tablename__ = "portfolio_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)

    signal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    entry_spy_price: Mapped[float] = mapped_column(Float, nullable=False)

    exit_signal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_spy_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    ticker: Mapped["Ticker"] = relationship(foreign_keys=[ticker_id])
