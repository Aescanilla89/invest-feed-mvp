"""Criterios CAN SLIM de William O'Neil, calculables con las fuentes de
datos gratuitas elegidas (yfinance + SEC EDGAR).

Cobertura real (ver README para la tabla completa):
  C - Current quarterly EPS growth   -> calculable (yfinance)
  A - Annual EPS growth              -> calculable (yfinance)
  N - New highs con volumen          -> calculable, parcial (solo precio/volumen,
                                         no la parte de "nuevo producto/gestión")
  S - Supply/demand (buybacks)       -> calculable (SEC EDGAR shares outstanding)
  L - Leader (fuerza relativa)       -> calculable (ticker vs benchmark)
  I - Institutional sponsorship      -> NO calculable en este MVP (ver sec_edgar.py)
  M - Market direction               -> calculable (Weinstein sobre el benchmark)

Cada función devuelve un CriterionResult con value=True/False/None.
value=None siempre significa "no verificable", nunca se interpreta como False.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.screener.data_source import FundamentalData
from app.screener.sec_edgar import SupplySignal
from app.screener.weinstein import WeinsteinResult

EPS_GROWTH_THRESHOLD = 0.25  # 25%, umbral clásico de O'Neil
NEW_HIGH_PROXIMITY_PCT = 0.98  # cierre dentro del 2% del máximo de 52 semanas
NEW_HIGH_VOLUME_RATIO = 1.5
RELATIVE_STRENGTH_OUTPERFORM_PCT = 0.0  # ticker debe superar al benchmark


@dataclass
class CriterionResult:
    value: bool | None
    detail: str


def evaluate_c(fundamentals: FundamentalData) -> CriterionResult:
    growth = fundamentals.eps_quarterly_yoy_growth
    if growth is None:
        return CriterionResult(None, "Sin suficiente histórico de EPS trimestral en yfinance")
    passed = growth >= EPS_GROWTH_THRESHOLD
    return CriterionResult(passed, f"Crecimiento EPS trimestral YoY: {growth:.1%} (umbral {EPS_GROWTH_THRESHOLD:.0%})")


def evaluate_a(fundamentals: FundamentalData) -> CriterionResult:
    growth = fundamentals.eps_annual_growth
    if growth is None:
        return CriterionResult(None, "Sin suficiente histórico de EPS anual en yfinance")
    passed = growth >= EPS_GROWTH_THRESHOLD
    return CriterionResult(passed, f"Crecimiento EPS anual: {growth:.1%} (umbral {EPS_GROWTH_THRESHOLD:.0%})")


def evaluate_n(weekly_prices: pd.DataFrame) -> CriterionResult:
    if len(weekly_prices) < 52:
        return CriterionResult(None, "Menos de 52 semanas de histórico, no se puede evaluar máximo anual")

    last_52 = weekly_prices.tail(52)
    high_52w = last_52["High"].max()
    current_close = weekly_prices["Close"].iloc[-1]
    current_volume = weekly_prices["Volume"].iloc[-1]
    avg_volume = weekly_prices["Volume"].tail(10).mean()

    near_high = current_close >= high_52w * NEW_HIGH_PROXIMITY_PCT
    volume_confirms = avg_volume > 0 and (current_volume / avg_volume) >= NEW_HIGH_VOLUME_RATIO
    passed = bool(near_high and volume_confirms)
    detail = (
        f"Cierre {current_close:.2f} vs máx 52sem {high_52w:.2f} "
        f"({current_close / high_52w:.1%} del máximo); volumen relativo "
        f"{(current_volume / avg_volume):.2f}x (umbral {NEW_HIGH_VOLUME_RATIO}x). "
        "No evalúa 'nuevo producto/gestión' (no verificable con datos)."
    )
    return CriterionResult(passed, detail)


def evaluate_l(ticker_weekly: pd.DataFrame, benchmark_weekly: pd.DataFrame, lookback_weeks: int = 52) -> CriterionResult:
    if len(ticker_weekly) < lookback_weeks or len(benchmark_weekly) < lookback_weeks:
        return CriterionResult(None, f"Menos de {lookback_weeks} semanas de histórico para comparar con el benchmark")

    ticker_return = ticker_weekly["Close"].iloc[-1] / ticker_weekly["Close"].iloc[-lookback_weeks] - 1
    benchmark_return = benchmark_weekly["Close"].iloc[-1] / benchmark_weekly["Close"].iloc[-lookback_weeks] - 1
    outperformance = ticker_return - benchmark_return
    passed = bool(outperformance > RELATIVE_STRENGTH_OUTPERFORM_PCT)
    detail = f"Retorno {lookback_weeks}sem: ticker {ticker_return:.1%} vs benchmark {benchmark_return:.1%} (diff {outperformance:+.1%})"
    return CriterionResult(passed, detail)


def evaluate_s(supply_signal: SupplySignal) -> CriterionResult:
    if supply_signal.is_buyback_trend is None:
        return CriterionResult(None, "Sin datos de shares outstanding en SEC EDGAR para este ticker")
    change = supply_signal.shares_outstanding_change_pct
    detail = (
        f"Shares outstanding variación {supply_signal.quarters_compared} trimestres: "
        f"{change:+.1%}" if change is not None else "Sin variación calculable"
    )
    return CriterionResult(supply_signal.is_buyback_trend, detail)


INSTITUTIONAL_MIN_PCT = 0.15   # <15% = insuficiente respaldo institucional
INSTITUTIONAL_MAX_PCT = 0.90   # >90% = sobre-poseído, riesgo de venta masiva


def evaluate_i(institutional_pct: float | None = None) -> CriterionResult:
    """Usa heldPercentInstitutions de yfinance como proxy del criterio I.
    Aproximación: O'Neil busca acumulación creciente, aquí solo medimos el
    nivel actual. Un rango 15-90% indica respaldo sin sobre-concentración."""
    if institutional_pct is None:
        return CriterionResult(
            None,
            "Sin datos de tenencia institucional disponibles vía yfinance para este ticker.",
        )
    passed = INSTITUTIONAL_MIN_PCT <= institutional_pct <= INSTITUTIONAL_MAX_PCT
    return CriterionResult(
        passed,
        f"Tenencia institucional: {institutional_pct:.1%} "
        f"(umbral {INSTITUTIONAL_MIN_PCT:.0%}-{INSTITUTIONAL_MAX_PCT:.0%}). "
        "Proxy del criterio I; no mide variacion trimestral de posiciones.",
    )


def evaluate_m(benchmark_weinstein: WeinsteinResult) -> CriterionResult:
    passed = benchmark_weinstein.stage == 2
    detail = f"Stage de Weinstein del benchmark (mercado general): {benchmark_weinstein.stage}"
    return CriterionResult(passed, detail)


def evaluate_all(
    fundamentals: FundamentalData,
    ticker_weekly: pd.DataFrame,
    benchmark_weekly: pd.DataFrame,
    benchmark_weinstein: WeinsteinResult,
    supply_signal: SupplySignal,
    institutional_pct: float | None = None,
) -> dict[str, CriterionResult]:
    return {
        "C": evaluate_c(fundamentals),
        "A": evaluate_a(fundamentals),
        "N": evaluate_n(ticker_weekly),
        "S": evaluate_s(supply_signal),
        "L": evaluate_l(ticker_weekly, benchmark_weekly),
        "I": evaluate_i(institutional_pct),
        "M": evaluate_m(benchmark_weinstein),
    }
