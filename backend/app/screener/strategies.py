"""Estrategias de inversión adicionales: Minervini, Lynch, Berkshire, Dividendos.

Cada evaluador devuelve un StrategyResult con:
  passed: bool | None  — None = datos insuficientes para evaluar
  score:  int | None   — 0-100, None si no calculable
  details: str         — explicación concisa de por qué pasa/no pasa

Principio compartido con CAN SLIM: nunca convertir None en False.
Un dato faltante no es una señal negativa, es una limitación de la fuente.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.screener.data_source import DividendData, FundamentalData, _yoy_growth
from app.screener.sec_edgar import QualityMetrics, SupplySignal

# ---------------------------------------------------------------------------
# Resultado común a todas las estrategias
# ---------------------------------------------------------------------------

@dataclass
class StrategyResult:
    passed: bool | None   # None = datos insuficientes
    score: int | None     # 0-100, None si no calculable
    details: str


def _to_dict(r: StrategyResult) -> dict:
    return {"passed": r.passed, "score": r.score, "details": r.details}


# ---------------------------------------------------------------------------
# Minervini SEPA (Specific Entry Point Analysis)
# Trend Template de Mark Minervini en versión semanal
# ---------------------------------------------------------------------------

_MINERVINI_PASS_THRESHOLD = 6   # de 7 criterios debe pasar al menos 6
_MINERVINI_RS_MIN = 70          # RS Rating mínimo (percentil vs universo)


def evaluate_minervini(
    weekly: pd.DataFrame,
    universe_returns: list[float] | None = None,
) -> StrategyResult:
    """Trend Template semanal (equivalente a MA50d/150d/200d diarios):
      MA10w ≈ MA50d · MA30w ≈ MA150d · MA40w ≈ MA200d
    Necesita al menos 40 semanas de datos."""
    if len(weekly) < 52:
        return StrategyResult(None, None, "Menos de 52 semanas de histórico")

    closes = weekly["Close"]
    ma10 = closes.rolling(10).mean().iloc[-1]
    ma30 = closes.rolling(30).mean().iloc[-1]
    ma40 = closes.rolling(40).mean().iloc[-1]
    ma40_4w_ago = closes.rolling(40).mean().iloc[-5] if len(weekly) >= 45 else None

    current = closes.iloc[-1]
    high_52w = closes.tail(52).max()
    low_52w = closes.tail(52).min()

    criteria: list[tuple[bool, str]] = []

    # 1. Precio sobre MA10w (≈MA50d)
    passed = bool(current > ma10)
    criteria.append((passed, f"Precio {current:.2f} {'>' if passed else '<='} MA10w {ma10:.2f}"))

    # 2. MA10w sobre MA30w (≈MA150d)
    passed = bool(ma10 > ma30)
    criteria.append((passed, f"MA10w {ma10:.2f} {'>' if passed else '<='} MA30w {ma30:.2f}"))

    # 3. MA30w sobre MA40w (≈MA200d)
    passed = bool(ma30 > ma40)
    criteria.append((passed, f"MA30w {ma30:.2f} {'>' if passed else '<='} MA40w {ma40:.2f}"))

    # 4. MA40w con pendiente alcista (últimas 4 semanas)
    if ma40_4w_ago is not None and ma40_4w_ago > 0:
        passed = bool(ma40 > ma40_4w_ago)
        criteria.append((passed, f"MA40w {'subiendo' if passed else 'bajando'} ({ma40:.2f} vs {ma40_4w_ago:.2f} hace 4 sem)"))
    else:
        criteria.append((False, "Sin datos para verificar pendiente MA40w"))

    # 5. Precio al menos 30% sobre mínimo 52 semanas
    pct_above_low = (current / low_52w - 1) if low_52w > 0 else 0
    passed = bool(pct_above_low >= 0.30)
    criteria.append((passed, f"Precio {pct_above_low:.0%} sobre mínimo 52w (umbral 30%)"))

    # 6. Precio dentro del 25% del máximo 52 semanas
    pct_from_high = (1 - current / high_52w) if high_52w > 0 else 1
    passed = bool(pct_from_high <= 0.25)
    criteria.append((passed, f"Precio a {pct_from_high:.0%} del máximo 52w (umbral ≤25%)"))

    # 7. Fuerza relativa (RS Rating >= 70 si hay datos de universo)
    if universe_returns and len(universe_returns) >= 10:
        ticker_return = (current / closes.iloc[-52] - 1) if len(weekly) >= 52 else 0
        rs = round(sum(1 for r in universe_returns if ticker_return > r) / len(universe_returns) * 100)
        passed = rs >= _MINERVINI_RS_MIN
        criteria.append((passed, f"RS Rating {rs} (umbral {_MINERVINI_RS_MIN})"))
    else:
        criteria.append((False, "Sin datos de universo para RS Rating"))

    n_passed = sum(1 for ok, _ in criteria if ok)
    score = round(n_passed / len(criteria) * 100)
    details_parts = [msg for _, msg in criteria]
    signal_passed = n_passed >= _MINERVINI_PASS_THRESHOLD

    details = (
        f"Trend Template Minervini: {n_passed}/{len(criteria)} criterios. "
        + "; ".join(details_parts)
    )
    return StrategyResult(passed=signal_passed, score=score, details=details)


# ---------------------------------------------------------------------------
# Lynch GARP (Growth At a Reasonable Price)
# PEG ratio como señal principal; tipos: fast grower y stalwart
# ---------------------------------------------------------------------------

_LYNCH_FAST_GROWER_EPS_MIN = 0.15   # crecimiento EPS anual mínimo para fast grower
_LYNCH_PEG_FAST_MAX = 1.5           # PEG máximo para fast grower
_LYNCH_PEG_STALWART_MAX = 2.0       # PEG máximo para stalwart


def evaluate_lynch(weekly: pd.DataFrame, fundamentals: FundamentalData) -> StrategyResult:
    """GARP de Peter Lynch: PEG < 1.5 (fast grower) o < 2.0 (stalwart)
    con EPS positivo y creciendo."""
    eps_q = fundamentals.raw_quarterly_eps
    eps_a = fundamentals.raw_annual_eps

    if len(eps_q) < 4:
        return StrategyResult(None, None, "Menos de 4 trimestres de EPS para calcular TTM")

    ttm_eps = sum(eps_q[-4:])
    if ttm_eps <= 0:
        return StrategyResult(
            False, 10,
            f"EPS TTM negativo ({ttm_eps:.2f}); Lynch requiere beneficios reales"
        )

    current_price = float(weekly["Close"].iloc[-1])
    pe = current_price / ttm_eps

    growth_rate = fundamentals.eps_annual_growth
    if growth_rate is None and len(eps_a) >= 2:
        growth_rate = _yoy_growth(eps_a, 1)

    if growth_rate is None or growth_rate <= 0:
        return StrategyResult(
            False, 15,
            f"P/E {pe:.1f}; crecimiento EPS anual no positivo o sin datos (Lynch requiere crecimiento)"
        )

    growth_pct = growth_rate * 100
    peg = pe / growth_pct

    if growth_rate >= _LYNCH_FAST_GROWER_EPS_MIN and peg <= _LYNCH_PEG_FAST_MAX:
        score = max(40, round(100 - (peg / _LYNCH_PEG_FAST_MAX) * 60))
        return StrategyResult(
            True, score,
            f"Fast Grower Lynch: P/E {pe:.1f}, crecimiento EPS {growth_pct:.0f}%, PEG {peg:.2f} (umbral {_LYNCH_PEG_FAST_MAX})"
        )

    if peg <= _LYNCH_PEG_STALWART_MAX:
        score = max(20, round(50 - (peg - _LYNCH_PEG_FAST_MAX) / (_LYNCH_PEG_STALWART_MAX - _LYNCH_PEG_FAST_MAX) * 30))
        return StrategyResult(
            True, score,
            f"Stalwart Lynch: P/E {pe:.1f}, crecimiento EPS {growth_pct:.0f}%, PEG {peg:.2f} (umbral stalwart {_LYNCH_PEG_STALWART_MAX})"
        )

    return StrategyResult(
        False, max(5, round(50 - (peg - _LYNCH_PEG_STALWART_MAX) * 10)),
        f"PEG {peg:.2f} fuera de rango Lynch (P/E {pe:.1f}, crecimiento {growth_pct:.0f}%)"
    )


# ---------------------------------------------------------------------------
# Berkshire Quality (inspirado en los criterios de calidad del repo ai-berkshire)
# ROE, márgenes, OCF/NI, no dilución, consistencia EPS
# ---------------------------------------------------------------------------

_BERK_GROSS_MARGIN_MIN = 0.30    # margen bruto >= 30% (pricing power)
_BERK_NET_MARGIN_MIN = 0.10      # margen neto >= 10% (resistencia a ciclos)
_BERK_OCF_TO_NI_MIN = 0.70       # OCF/NI >= 0.7 (calidad del beneficio)
_BERK_ROE_MIN = 0.15             # ROE >= 15% (eficiencia del capital)
_BERK_PASS_THRESHOLD = 0.60      # debe pasar >= 60% de criterios verificables


def evaluate_berkshire(
    fundamentals: FundamentalData,
    quality: QualityMetrics,
    supply_signal: SupplySignal,
) -> StrategyResult:
    """Calidad estilo Berkshire: márgenes, OCF/NI, ROE, sin dilución, EPS consistente."""
    criteria: list[tuple[bool | None, str]] = []

    # 1. Margen bruto >= 30%
    if quality.gross_margin is not None:
        ok = quality.gross_margin >= _BERK_GROSS_MARGIN_MIN
        criteria.append((ok, f"Margen bruto {quality.gross_margin:.0%} (umbral {_BERK_GROSS_MARGIN_MIN:.0%})"))
    else:
        criteria.append((None, "Margen bruto no disponible en EDGAR"))

    # 2. Margen neto >= 10%
    if quality.net_margin is not None:
        ok = quality.net_margin >= _BERK_NET_MARGIN_MIN
        criteria.append((ok, f"Margen neto {quality.net_margin:.0%} (umbral {_BERK_NET_MARGIN_MIN:.0%})"))
    else:
        criteria.append((None, "Margen neto no disponible en EDGAR"))

    # 3. OCF/NI >= 0.7 (beneficio respaldado por caja)
    if quality.ocf_to_ni is not None:
        ok = quality.ocf_to_ni >= _BERK_OCF_TO_NI_MIN
        criteria.append((ok, f"OCF/Beneficio neto {quality.ocf_to_ni:.2f} (umbral {_BERK_OCF_TO_NI_MIN})"))
    else:
        criteria.append((None, "OCF no disponible en EDGAR"))

    # 4. ROE >= 15%
    if quality.roe is not None:
        ok = quality.roe >= _BERK_ROE_MIN
        criteria.append((ok, f"ROE {quality.roe:.0%} (umbral {_BERK_ROE_MIN:.0%})"))
    else:
        criteria.append((None, "ROE no disponible en EDGAR"))

    # 5. Sin dilución de acciones
    if supply_signal.is_buyback_trend is not None:
        criteria.append((supply_signal.is_buyback_trend, "Reducción de acciones (buyback)" if supply_signal.is_buyback_trend else "Dilución de acciones detectada"))
    else:
        criteria.append((None, "Datos de shares outstanding no disponibles"))

    # 6. Consistencia EPS (>= 3 de los últimos 5 años con beneficio creciente)
    eps_a = fundamentals.raw_annual_eps
    if len(eps_a) >= 5:
        positive_years = sum(1 for i in range(-1, -6, -1) if eps_a[i - 1] != 0 and eps_a[i] > eps_a[i - 1])
        ok = positive_years >= 3
        criteria.append((ok, f"Consistencia EPS: {positive_years}/5 años positivos (umbral 3)"))
    else:
        criteria.append((None, "Menos de 5 años de EPS anual para evaluar consistencia"))

    verifiable = [(ok, msg) for ok, msg in criteria if ok is not None]
    if not verifiable:
        return StrategyResult(None, None, "Datos insuficientes para evaluar calidad Berkshire")

    passed_v = sum(1 for ok, _ in verifiable if ok)
    score = round(passed_v / len(verifiable) * 100)
    signal_passed = score >= round(_BERK_PASS_THRESHOLD * 100)
    details = (
        f"Berkshire Quality: {passed_v}/{len(verifiable)} verificables. "
        + "; ".join(msg for _, msg in criteria if msg)
    )
    return StrategyResult(passed=signal_passed, score=score, details=details)


# ---------------------------------------------------------------------------
# Dividendos
# ---------------------------------------------------------------------------

_DIV_YIELD_MIN = 0.025       # yield mínimo 2.5%
_DIV_PAYOUT_MIN = 0.15       # payout mínimo 15% (señal de compromiso real)
_DIV_PAYOUT_MAX = 0.80       # payout máximo 80% (sostenibilidad)


def evaluate_dividendos(
    dividend_data: DividendData,
    fundamentals: FundamentalData,
) -> StrategyResult:
    """Oportunidad de dividendo: yield >= 2.5%, payout sostenible, EPS positivo."""
    if dividend_data.yield_pct is None or dividend_data.yield_pct <= 0:
        return StrategyResult(False, 0, "Sin dividendo o yield no disponible en la fuente de datos")

    y = dividend_data.yield_pct
    if y < _DIV_YIELD_MIN:
        return StrategyResult(
            False, round(y / _DIV_YIELD_MIN * 30),
            f"Yield {y:.1%} por debajo del umbral {_DIV_YIELD_MIN:.1%}"
        )

    details_parts: list[str] = [f"Yield {y:.1%}"]
    score = 40

    # Payout ratio sostenible
    payout = dividend_data.payout_ratio
    if payout is not None:
        if _DIV_PAYOUT_MIN <= payout <= _DIV_PAYOUT_MAX:
            details_parts.append(f"payout {payout:.0%} (sostenible)")
            score += 25
        else:
            reason = "demasiado bajo (posible reducción futura)" if payout < _DIV_PAYOUT_MIN else "demasiado alto (riesgo de recorte)"
            details_parts.append(f"payout {payout:.0%} {reason}")
            score -= 10
    else:
        details_parts.append("payout no disponible")

    # EPS positivo
    eps_a = fundamentals.raw_annual_eps
    if eps_a and eps_a[-1] > 0:
        details_parts.append("EPS positivo")
        score += 20
        # EPS creciente → dividendo tiene margen de crecer
        if len(eps_a) >= 2 and eps_a[-1] > eps_a[-2]:
            details_parts.append("EPS creciente")
            score += 15
    elif eps_a and eps_a[-1] <= 0:
        details_parts.append("EPS negativo (riesgo dividendo)")
        score -= 20

    score = max(0, min(100, score))
    passed = y >= _DIV_YIELD_MIN and (payout is None or _DIV_PAYOUT_MIN <= payout <= _DIV_PAYOUT_MAX)

    return StrategyResult(
        passed=passed,
        score=score,
        details="; ".join(details_parts),
    )


# ---------------------------------------------------------------------------
# Evaluación conjunta
# ---------------------------------------------------------------------------

def evaluate_all_strategies(
    weekly: pd.DataFrame,
    fundamentals: FundamentalData,
    supply_signal: SupplySignal,
    quality: QualityMetrics,
    dividend_data: DividendData,
    universe_returns: list[float] | None = None,
) -> dict[str, dict]:
    return {
        "minervini": _to_dict(evaluate_minervini(weekly, universe_returns)),
        "lynch": _to_dict(evaluate_lynch(weekly, fundamentals)),
        "berkshire": _to_dict(evaluate_berkshire(fundamentals, quality, supply_signal)),
        "dividendos": _to_dict(evaluate_dividendos(dividend_data, fundamentals)),
    }
