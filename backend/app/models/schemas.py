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
    score: str  # ej. "4/6 verificables"


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
    # Primera vez que este ticker apareció como oportunidad (MIN(run_date) de
    # todo su histórico en `opportunities`) -- separa "oportunidades de la
    # semana" (detectadas hace <7 días) de las que llevan más tiempo pero
    # siguen cumpliendo el criterio hoy. Ver list_opportunities.
    first_detected_date: date | None = None
    signal_type: str | None = None  # "weinstein" | "canslim" | "both"
    strategies: dict[str, StrategyResultSchema] = {}

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
    status: str  # "open" | "closed"
    explanation: str | None = None  # por qué se eligió, misma explicación AI del feed para ese ticker/día
    signal_date: date | None = None  # día en que se detectó la señal (cierre); entry_date es el día siguiente
    entry_date: date
    entry_price: float
    current_price: float  # precio actual si abierta, precio de salida si cerrada
    return_pct: float
    spy_return_pct: float  # retorno del S&P 500 en el mismo periodo exacto
    exit_signal_date: date | None = None  # día en que se detectó la ruptura de Stage 2; exit_date es el día siguiente
    exit_date: date | None = None
    exit_reason: str | None = None

    model_config = {"from_attributes": True}


class PortfolioStatsSchema(BaseModel):
    total_positions: int
    open_positions: int
    closed_positions: int
    # Única métrica de rentabilidad de cartera: ponderada por volatilidad
    # (ver _atr_pct/_position_weights en la ruta), año en curso, vs S&P 500 en
    # el mismo periodo. Se descartó promediar return_pct de TODAS las
    # posiciones (histórico completo, cualquier antigüedad) por mezclar
    # periodos de tenencia muy distintos (posiciones de hace casi 2 años junto
    # a otras de la semana pasada) -- inflaba el promedio con ganadoras muy
    # antiguas y no reflejaba cómo se comporta la cartera como conjunto ahora.
    ytd_return_pct: float | None
    ytd_spy_return_pct: float | None
    best: PortfolioPositionSchema | None
    worst: PortfolioPositionSchema | None


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
    classification: str | None  # "oro" | "plata" | "bronce"
    explanation: str | None

    model_config = {"from_attributes": True}


class FearGreedPointSchema(BaseModel):
    date: str
    score: float
    rating: str


class FearGreedSchema(BaseModel):
    score: float
    rating: str  # "extreme fear" | "fear" | "neutral" | "greed" | "extreme greed"
    timestamp: str
    previous_close: float
    previous_1_week: float
    previous_1_month: float
    previous_1_year: float
    history: list[FearGreedPointSchema] = []
