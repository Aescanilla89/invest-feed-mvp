"""Ranking explicable de acciones para la cartera activa.

El benchmark solo se usa como filtro de fuerza relativa; nunca se compra.
"""
from __future__ import annotations


def _strategy_score(opportunity, method: str) -> float:
    strategies = opportunity.strategies or {}
    if isinstance(strategies, str):
        import json
        try:
            strategies = json.loads(strategies)
        except Exception:
            strategies = {}
    result = strategies.get(method, {}) if isinstance(strategies, dict) else {}
    return float(result.get("score") or 0.0) if isinstance(result, dict) else 0.0


def stock_selection_score(opportunity, method: str) -> float:
    """Ordena candidatos que ya pasan el método, sin datos futuros."""
    combined = max(0.0, min(100.0, float(getattr(opportunity, "combined_score", 0) or 0)))
    method_score = max(0.0, min(100.0, _strategy_score(opportunity, method)))
    stage2 = 5.0 if getattr(opportunity, "weinstein_stage", 0) == 2 else 0.0
    slope = max(-10.0, min(10.0, float(getattr(opportunity, "weinstein_ma_slope_pct", 0) or 0)))
    slope_component = (slope + 10.0) * 5.0
    volume = max(0.0, min(3.0, float(getattr(opportunity, "weinstein_relative_volume", 0) or 0))) / 3.0 * 100.0
    return combined * 0.60 + method_score * 0.25 + stage2 + slope_component * 0.05 + volume * 0.05
