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

_WEINSTEIN_STAGE_POINTS = {1: 10, 2: 28, 3: 15, 4: 0}
_TRANSITION_BONUS = 12  # stage 2 + transición 1->2 reciente = señal de compra clásica

# Bonificaciones dentro de Stage 2 usando métricas de calidad de la tendencia
# MA slope semanal (>= 0.1% = ~5% anualizado)
_SLOPE_THRESHOLDS = [(1.0, 7), (0.5, 5), (0.2, 3), (0.1, 1)]
# RSI: sweet spot 55-75; <50 o >85 penaliza implícitamente por no sumar
_RSI_BONUS = [(55, 75, 5), (50, 55, 2), (75, 82, 2)]
# Volumen relativo confirma momentum
_RVOL_THRESHOLDS = [(1.5, 5), (1.0, 2)]

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
    if result.stage != 2:
        return base

    bonus = 0
    if result.is_transition_1_to_2:
        bonus += _TRANSITION_BONUS

    # MA slope: tendencia más fuerte = más puntos (max 7)
    slope = result.ma_slope_pct or 0
    for threshold, pts in _SLOPE_THRESHOLDS:
        if slope >= threshold:
            bonus += pts
            break

    # RSI: zona óptima 55-75 (max 5)
    rsi = result.rsi or 50
    for lo, hi, pts in _RSI_BONUS:
        if lo <= rsi < hi:
            bonus += pts
            break

    # Volumen relativo: confirmación de momentum (max 5)
    rvol = result.relative_volume or 0
    for threshold, pts in _RVOL_THRESHOLDS:
        if rvol >= threshold:
            bonus += pts
            break

    return min(base + bonus, WEINSTEIN_WEIGHT)


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
