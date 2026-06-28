"""Modelos SQLAlchemy 2.0. Tipos elegidos para ser portables a Postgres
sin reescritura: nada de tipos específicos de SQLite, JSON vía
`sqlalchemy.JSON` (compila a TEXT en SQLite y a jsonb en Postgres).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
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

    # {"C": {"value": true, "detail": "Crecimiento EPS trimestral YoY: 30.0% ..."}, ...}
    canslim_criteria: Mapped[dict] = mapped_column(JSON, nullable=False)
    canslim_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-50
    canslim_verifiable_count: Mapped[int] = mapped_column(Integer, nullable=False)
    canslim_passed_count: Mapped[int] = mapped_column(Integer, nullable=False)

    combined_score: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    risk_bucket: Mapped[str] = mapped_column(String(16), nullable=False)

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
    shares: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    value_usd_k: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Explanation(Base):
    __tablename__ = "explanations"
    __table_args__ = (UniqueConstraint("ticker_id", "run_date", name="uq_explanation_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), nullable=False, index=True)
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    combined_score_at_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(String(1000), nullable=False)
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    ticker: Mapped["Ticker"] = relationship(back_populates="explanations")
