"""Construcción del prompt para la explicación de cada oportunidad.

La instrucción clave es anclar la explicación en las señales numéricas ya
calculadas por el screener (CriterionResult.detail, WeinsteinResult) para
que Claude no caiga en lenguaje genérico de mercado ("tendencia alcista",
"buen momento para comprar"). Si Claude no tiene esos números en el
prompt, no tiene de dónde sacar una explicación concreta.
"""
from __future__ import annotations

from app.screener.canslim import CriterionResult
from app.screener.weinstein import WeinsteinResult

SYSTEM_PROMPT = """Eres un analista cuantitativo que explica señales de inversión a usuarios \
que entienden de bolsa pero no quieren jerga vacía.

Reglas estrictas:
- Responde en español con exactamente 4 bullets (•), nada más, sin texto antes ni después.
- Cada bullet es una sola frase concisa con el dato numérico clave cuando aplique.
- Bullet 1: señal activada (Weinstein Stage o CAN SLIM) con el dato que la confirma.
- Bullet 2: fortaleza fundamental más relevante (EPS, fuerza relativa, supply) o contexto del sector.
- Bullet 3: punto de atención o riesgo observable en los datos (lo que podría invalidar la señal).
- Bullet 4: contexto de mercado (criterio M, condición del benchmark SPY).
- Nunca recomiendes comprar o vender, ni uses imperativos de inversión ("compra", "entra ahora"). \
Esto es información educativa, no asesoramiento."""

_SIGNAL_CONTEXT = {
    "weinstein": (
        "SEÑAL ACTIVA — ENTRADA WEINSTEIN STAGE 1→2: "
        "El precio acaba de cruzar por encima de la media móvil de 30 semanas con volumen confirmatorio. "
        "Centra la explicación en esta señal técnica: cuántas semanas lleva en Stage 2, "
        "el volumen relativo en el cruce y la pendiente de la MA30."
    ),
    "canslim": (
        "SEÑAL ACTIVA — ROTURA CAN SLIM: "
        "El ticker está rompiendo máximos históricos con volumen Y cumple TODOS los criterios CAN SLIM verificables. "
        "Centra la explicación en los criterios fundamentales más fuertes (EPS, aceleración, fuerza relativa) "
        "y en que la rotura de ATH coincide con volumen superior al 1.5x la media."
    ),
    "both": (
        "SEÑAL DOBLE ACTIVA — WEINSTEIN + CAN SLIM: "
        "Rotura Stage 1→2 con volumen Y todos los criterios CAN SLIM verificables en verde. "
        "Destaca que ambas señales (técnica y fundamental) confirman la oportunidad simultáneamente. "
        "Es la configuración más sólida del método."
    ),
}


def build_user_prompt(
    symbol: str,
    name: str | None,
    sector: str | None,
    combined_score: int,
    weinstein: WeinsteinResult,
    criteria: dict[str, CriterionResult],
    signal_type: str | None = None,
) -> str:
    criteria_lines = "\n".join(
        f"- {key}: {'cumple' if c.value is True else 'no cumple' if c.value is False else 'no verificable'} -- {c.detail}"
        for key, c in criteria.items()
    )

    weeks = weinstein.weeks_in_stage
    if weinstein.is_transition_1_to_2 and weeks <= 4:
        transition_line = f"Breakout Stage 1→2 reciente (hace {weeks} semana{'s' if weeks != 1 else ''})"
    elif weinstein.is_transition_1_to_2:
        transition_line = f"Breakout Stage 1→2 confirmado (lleva {weeks} semanas en Stage 2)"
    else:
        transition_line = "Sin señal de breakout Stage 1→2"

    signal_context = _SIGNAL_CONTEXT.get(signal_type or "", "") if signal_type else ""

    return f"""Ticker: {symbol} ({name or 'nombre desconocido'}, sector {sector or 'desconocido'})
Score combinado: {combined_score}/100
{signal_context and f'{signal_context}'}

Weinstein Stage Analysis:
- Stage actual: {weinstein.stage}
- Semanas en este stage: {weeks}
- {transition_line}
- Pendiente MA30: {weinstein.ma_slope_pct:+.1%}
- Volumen relativo (vs media 10 semanas): {weinstein.relative_volume:.2f}x

Criterios CAN SLIM:
{criteria_lines}

Escribe la explicación siguiendo las reglas del sistema."""
