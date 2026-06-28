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


class CanslimCriterionSchema(BaseModel):
    value: bool | None
    detail: str


class CanslimSchema(BaseModel):
    criteria: dict[str, CanslimCriterionSchema]
    score: str  # ej. "4/6 verificables"


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
    signal_type: str | None = None  # "weinstein" | "canslim" | "both"

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
