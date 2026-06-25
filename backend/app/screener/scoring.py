"""Combina Weinstein + CAN SLIM en un único score 0-100. No se exponen
dos listas separadas: este módulo es el único punto que produce el
ranking final consumido por la API.

Reparto de peso: 50 puntos Weinstein (la fase del ciclo manda primero --
sin Stage 2 no hay oportunidad, por filosofía del propio método) + 50
puntos CAN SLIM (calculado solo sobre criterios verificables, para no
penalizar a un ticker por algo que la fuente de datos no puede confirmar).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass

from app.screener.canslim import CriterionResult
from app.screener.weinstein import WeinsteinResult

WEINSTEIN_WEIGHT = 50
CANSLIM_WEIGHT = 50

_WEINSTEIN_STAGE_POINTS = {1: 10, 2: 35, 3: 15, 4: 0}
_TRANSITION_BONUS = 15  # stage 2 + transición 1->2 reciente = señal de compra clásica

RISK_LOW_WEEKLY_VOL = 0.03
RISK_HIGH_WEEKLY_VOL = 0.06


@dataclass
class CombinedScore:
    combined_score: int
    weinstein_component: int
    canslim_component: int
    canslim_verifiable_count: int
    canslim_passed_count: int
    risk_bucket: str


def _weinstein_component(result: WeinsteinResult) -> int:
    base = _WEINSTEIN_STAGE_POINTS[result.stage]
    if result.stage == 2 and result.is_transition_1_to_2:
        base = min(base + _TRANSITION_BONUS, WEINSTEIN_WEIGHT)
    return base


def _canslim_component(criteria: dict[str, CriterionResult]) -> tuple[int, int, int]:
    verifiable = [c for c in criteria.values() if c.value is not None]
    passed = [c for c in verifiable if c.value is True]
    if not verifiable:
        return 0, 0, 0
    score = round((len(passed) / len(verifiable)) * CANSLIM_WEIGHT)
    return score, len(verifiable), len(passed)


def compute_risk_bucket(weekly_prices: pd.DataFrame, lookback_weeks: int = 12) -> str:
    if len(weekly_prices) < lookback_weeks + 1:
        return "desconocido"
    returns = weekly_prices["Close"].tail(lookback_weeks + 1).pct_change().dropna()
    weekly_vol = float(np.std(returns))
    if weekly_vol < RISK_LOW_WEEKLY_VOL:
        return "bajo"
    if weekly_vol < RISK_HIGH_WEEKLY_VOL:
        return "medio"
    return "alto"


def compute_combined_score(
    weinstein_result: WeinsteinResult,
    canslim_criteria: dict[str, CriterionResult],
    weekly_prices: pd.DataFrame,
) -> CombinedScore:
    weinstein_pts = _weinstein_component(weinstein_result)
    canslim_pts, verifiable_count, passed_count = _canslim_component(canslim_criteria)
    return CombinedScore(
        combined_score=weinstein_pts + canslim_pts,
        weinstein_component=weinstein_pts,
        canslim_component=canslim_pts,
        canslim_verifiable_count=verifiable_count,
        canslim_passed_count=passed_count,
        risk_bucket=compute_risk_bucket(weekly_prices),
    )
