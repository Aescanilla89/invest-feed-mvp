"""Schemas Pydantic para las respuestas de la API. Estos son el contrato
real con el frontend -- cualquier cambio aquí es un cambio de contrato."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class WeinsteinSchema(BaseModel):
    stage: int
    is_transition: bool
    weeks_in_stage: int
    ma_slope_pct: float
    relative_volume: float
    rsi: float = 50.0


class CanslimCriterionSchema(BaseModel):
    value: bool | None
    detail: str


class CanslimSchema(BaseModel):
    criteria: dict[str, CanslimCriterionSchema]
    score: str


class StrategyResultSchema(BaseModel):
    passed: bool | None
    score: int | None
    details: str


class OpportunitySchema(BaseModel):
    ticker: str
    name: str | None
    sector: str | None
    combined_score: int
    risk_bucket: str
    weinstein: WeinsteinSchema
    canslim: CanslimSchema
    explanation: str | None
    last_updated: date
    first_detected_date: date | None = None
    first_detected_price: float | None = None
    current_price: float | None = None
    return_since_first_detected_pct: float | None = None
    signal_type: str | None = None
    strategies: dict[str, StrategyResultSchema] = {}
    selection_score: float | None = None
    selection_method: str | None = None

    model_config = {"from_attributes": True}


class OpportunityDetailSchema(OpportunitySchema):
    price_history: list[dict] = []


class DataLimitation(BaseModel):
    criterion: str
    verifiable: bool
    reason: str


class DataLimitationsSchema(BaseModel):
    source_notes: list[str]
    canslim_criteria: list[DataLimitation]


class PortfolioPositionSchema(BaseModel):
    ticker: str
    name: str | None
    sector: str | None
    method: str
    selection_score: float | None = None
    status: str
    explanation: str | None = None
    signal_date: date | None = None
    entry_date: date
    entry_price: float
    current_price: float
    return_pct: float
    spy_return_pct: float
    exit_signal_date: date | None = None
    exit_date: date | None = None
    exit_reason: str | None = None

    model_config = {"from_attributes": True}


class PortfolioStatsSchema(BaseModel):
    total_positions: int
    open_positions: int
    closed_positions: int
    ytd_return_pct: float | None
    ytd_spy_return_pct: float | None
    best: PortfolioPositionSchema | None
    worst: PortfolioPositionSchema | None
    performance: dict[str, float | int | None] = {}
    by_method: dict[str, dict[str, float | int | None]] = {}


class PortfolioSchema(BaseModel):
    stats: PortfolioStatsSchema
    positions: list[PortfolioPositionSchema]


class CatalystSchema(BaseModel):
    id: int
    ticker: str | None
    company_name: str | None
    sector: str | None
    catalyst_type: str
    title: str
    description: str | None
    detected_date: date
    extra: dict
    combined_score: int | None
    classification: str | None
    explanation: str | None

    model_config = {"from_attributes": True}
