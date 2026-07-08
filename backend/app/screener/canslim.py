"""Criterios CAN SLIM de William O'Neil, calculables con las fuentes de
datos gratuitas elegidas (yfinance + SEC EDGAR).

Cobertura real (ver README para la tabla completa):
  C - Current quarterly EPS growth   -> calculable; incluye aceleración YoY
  A - Annual EPS growth              -> calculable; incluye consistencia 3/5 años
  N - New highs con volumen          -> ATH desde price_snapshots acumulado
  S - Supply/demand (buybacks)       -> calculable (SEC EDGAR shares outstanding)
  L - Leader (fuerza relativa)       -> RS Rating percentil vs universo
  I - Institutional sponsorship      -> calculable (top-30 instituciones vía 13F-HR de SEC EDGAR)
  M - Market direction               -> calculable (Weinstein sobre el benchmark)

Cada función devuelve un CriterionResult con value=True/False/None.
value=None siempre significa "no verificable", nunca se interpreta como False.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.screener.data_source import FundamentalData, _yoy_growth
from app.screener.sec_edgar import SupplySignal
from app.screener.weinstein import WeinsteinResult

EPS_GROWTH_THRESHOLD = 0.25  # 25%, umbral clásico de O'Neil
NEW_HIGH_PROXIMITY_PCT = 0.98  # cierre dentro del 2% del ATH
NEW_HIGH_VOLUME_RATIO = 1.5
RS_RATING_THRESHOLD = 80  # percentil mínimo vs universo (IBD style)
ANNUAL_CONSISTENCY_MIN_YEARS = 3  # mínimo años positivos de los últimos 5
ANNUAL_CONSISTENCY_LOOKBACK = 5


@dataclass
class CriterionResult:
    value: bool | None
    detail: str


def evaluate_c(fundamentals: FundamentalData) -> CriterionResult:
    """Criterio C: crecimiento EPS trimestral YoY >= 25% Y acelerando."""
    growth = fundamentals.eps_quarterly_yoy_growth
    if growth is None:
        return CriterionResult(None, "Sin suficiente histórico de EPS trimestral")

    if growth < EPS_GROWTH_THRESHOLD:
        return CriterionResult(
            False,
            f"Crecimiento EPS trimestral YoY: {growth:.1%} (umbral {EPS_GROWTH_THRESHOLD:.0%})",
        )

    eps = fundamentals.raw_quarterly_eps
    if len(eps) >= 7:
        # growth_prev = crecimiento YoY del trimestre anterior al más reciente
        growth_prev = _yoy_growth(eps[:-1], periods_back=4)
        if growth_prev is not None:
            accelerating = growth > growth_prev
            direction = "acelerando" if accelerating else "desacelerando"
            detail = (
                f"Crecimiento EPS trimestral YoY: {growth:.1%} (umbral {EPS_GROWTH_THRESHOLD:.0%}); "
                f"{direction} ({growth:.1%} vs {growth_prev:.1%} trimestre anterior)"
            )
            return CriterionResult(accelerating, detail)

    return CriterionResult(
        True,
        f"Crecimiento EPS trimestral YoY: {growth:.1%} (umbral {EPS_GROWTH_THRESHOLD:.0%}); "
        "sin datos suficientes para verificar aceleración",
    )


def evaluate_a(fundamentals: FundamentalData) -> CriterionResult:
    """Criterio A: crecimiento EPS anual >= 25% Y consistente (3/5 años positivos)."""
    growth = fundamentals.eps_annual_growth
    if growth is None:
        return CriterionResult(None, "Sin suficiente histórico de EPS anual")

    if growth < EPS_GROWTH_THRESHOLD:
        return CriterionResult(
            False,
            f"Crecimiento EPS anual: {growth:.1%} (umbral {EPS_GROWTH_THRESHOLD:.0%})",
        )

    eps = fundamentals.raw_annual_eps
    if len(eps) >= ANNUAL_CONSISTENCY_LOOKBACK + 1:
        positive_years = sum(
            1
            for i in range(-1, -(ANNUAL_CONSISTENCY_LOOKBACK + 1), -1)
            if eps[i - 1] != 0 and eps[i] > eps[i - 1]
        )
        consistent = positive_years >= ANNUAL_CONSISTENCY_MIN_YEARS
        detail = (
            f"Crecimiento EPS anual: {growth:.1%} (umbral {EPS_GROWTH_THRESHOLD:.0%}); "
            f"consistencia: {positive_years}/{ANNUAL_CONSISTENCY_LOOKBACK} años positivos "
            f"(mínimo {ANNUAL_CONSISTENCY_MIN_YEARS})"
        )
        return CriterionResult(consistent, detail)

    return CriterionResult(
        True,
        f"Crecimiento EPS anual: {growth:.1%} (umbral {EPS_GROWTH_THRESHOLD:.0%}); "
        "sin datos suficientes para verificar consistencia",
    )


def evaluate_n(weekly_prices: pd.DataFrame, all_time_high: float | None = None) -> CriterionResult:
    """Criterio N: rotura de máximo 52 semanas con volumen confirmatorio.
    Usamos el máximo de 52 semanas (no el ATH histórico) para capturar breakouts reales
    desde una base — muchos stocks válidos nunca recuperan su ATH de años anteriores."""
    if len(weekly_prices) < 52:
        return CriterionResult(None, "Menos de 52 semanas de histórico, no se puede evaluar")

    high_52w = float(weekly_prices["High"].tail(52).max())
    current_close = weekly_prices["Close"].iloc[-1]
    avg_volume_10w = weekly_prices["Volume"].tail(10).mean()
    # Volumen confirmatorio: media de las últimas 4 semanas vs media 10 semanas
    recent_vol = weekly_prices["Volume"].tail(4).mean()
    rel_volume = (recent_vol / avg_volume_10w) if avg_volume_10w > 0 else 0

    near_high = current_close >= high_52w * NEW_HIGH_PROXIMITY_PCT
    volume_confirms = rel_volume >= NEW_HIGH_VOLUME_RATIO
    passed = bool(near_high and volume_confirms)

    ath_str = f" (ATH histórico: {all_time_high:.2f})" if all_time_high and all_time_high > high_52w * 1.05 else ""
    detail = (
        f"Cierre {current_close:.2f} vs máx 52w {high_52w:.2f} "
        f"({current_close / high_52w:.1%} del máximo){ath_str}; "
        f"volumen relativo 4w {rel_volume:.2f}x (umbral {NEW_HIGH_VOLUME_RATIO}x). "
        "Solo evalúa precio+volumen; el catalizador cualitativo de O'Neil "
        "('nuevo producto/gestión') no se verifica aquí."
    )
    return CriterionResult(passed, detail)


def evaluate_l(
    ticker_weekly: pd.DataFrame,
    benchmark_weekly: pd.DataFrame,
    lookback_weeks: int = 52,
    universe_returns: list[float] | None = None,
) -> CriterionResult:
    """Criterio L: RS Rating >= 80 (percentil vs universo) cuando está disponible;
    si no, comparación simple vs benchmark SPY."""
    if len(ticker_weekly) < lookback_weeks:
        return CriterionResult(None, f"Menos de {lookback_weeks} semanas de histórico")

    ticker_return = ticker_weekly["Close"].iloc[-1] / ticker_weekly["Close"].iloc[-lookback_weeks] - 1

    if universe_returns and len(universe_returns) >= 10:
        rs_rating = round(sum(1 for r in universe_returns if ticker_return > r) / len(universe_returns) * 100)
        passed = rs_rating >= RS_RATING_THRESHOLD
        detail = (
            f"RS Rating: {rs_rating} (percentil vs {len(universe_returns)} tickers del universo); "
            f"retorno {lookback_weeks}sem: {ticker_return:.1%} (umbral percentil {RS_RATING_THRESHOLD})"
        )
        return CriterionResult(passed, detail)

    # Fallback: comparación vs benchmark
    if len(benchmark_weekly) < lookback_weeks:
        return CriterionResult(None, f"Menos de {lookback_weeks} semanas de histórico del benchmark")
    benchmark_return = benchmark_weekly["Close"].iloc[-1] / benchmark_weekly["Close"].iloc[-lookback_weeks] - 1
    outperformance = ticker_return - benchmark_return
    passed = bool(outperformance > 0)
    detail = (
        f"Retorno {lookback_weeks}sem: ticker {ticker_return:.1%} vs benchmark {benchmark_return:.1%} "
        f"(diff {outperformance:+.1%}) — sin datos de universo para RS Rating percentil"
    )
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


INSTITUTIONAL_MIN_HOLDERS = 3   # mínimo fondos top-30 con posición abierta
INSTITUTIONAL_MIN_PCT = 0.15   # fallback: <15% = insuficiente respaldo
INSTITUTIONAL_MAX_PCT = 0.90   # fallback: >90% = sobre-poseído


@dataclass
class InstitutionalData:
    """Datos de tenencia institucional para el trimestre actual y el anterior."""
    current_holders: int       # fondos del top-30 con posición este trimestre
    prior_holders: int | None  # ídem trimestre anterior (None si no hay datos)
    current_shares: int
    prior_shares: int | None


def evaluate_i(
    institutional_data: InstitutionalData | None = None,
    institutional_pct: float | None = None,
) -> CriterionResult:
    """Criterio I: acumulación institucional detectada via 13F-HR de SEC EDGAR.

    Prioridad:
    1. institutional_data (datos reales de 13F trimestral) si está disponible
    2. institutional_pct (% de tenencia) como fallback
    3. None si no hay ningún dato
    """
    if institutional_data is not None:
        count = institutional_data.current_holders
        prior = institutional_data.prior_holders

        if count < INSTITUTIONAL_MIN_HOLDERS:
            return CriterionResult(
                False,
                f"Solo {count} instituciones top con posición (mínimo {INSTITUTIONAL_MIN_HOLDERS}); "
                "insuficiente respaldo institucional.",
            )

        if prior is not None:
            delta = count - prior
            if delta > 0:
                trend = f"acumulando ↑ (+{delta} fondos)"
                passed = True
            elif delta == 0:
                trend = "estable →"
                passed = True
            else:
                trend = f"distribuyendo ↓ ({delta} fondos)"
                passed = False
            return CriterionResult(
                passed,
                f"Tenencia institucional (top-30 fondos): {count} fondos este trimestre "
                f"vs {prior} anterior — {trend}.",
            )

        return CriterionResult(
            True,
            f"Tenencia institucional (top-30 fondos): {count} fondos con posición "
            "(sin dato de trimestre anterior para comparar tendencia).",
        )

    # Fallback: % de tenencia institucional genérico
    if institutional_pct is not None:
        passed = INSTITUTIONAL_MIN_PCT <= institutional_pct <= INSTITUTIONAL_MAX_PCT
        return CriterionResult(
            passed,
            f"Tenencia institucional: {institutional_pct:.1%} "
            f"(umbral {INSTITUTIONAL_MIN_PCT:.0%}–{INSTITUTIONAL_MAX_PCT:.0%}). "
            "Proxy de criterio I; sin desglose trimestral de posiciones.",
        )

    return CriterionResult(
        None,
        "Sin datos de tenencia institucional. Ejecutar /admin/update-institutional para cargar 13F de SEC.",
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
    all_time_high: float | None = None,
    universe_returns: list[float] | None = None,
    institutional_data: InstitutionalData | None = None,
) -> dict[str, CriterionResult]:
    return {
        "C": evaluate_c(fundamentals),
        "A": evaluate_a(fundamentals),
        "N": evaluate_n(ticker_weekly, all_time_high=all_time_high),
        "S": evaluate_s(supply_signal),
        "L": evaluate_l(ticker_weekly, benchmark_weekly, universe_returns=universe_returns),
        "I": evaluate_i(institutional_data=institutional_data, institutional_pct=institutional_pct),
        "M": evaluate_m(benchmark_weinstein),
    }
