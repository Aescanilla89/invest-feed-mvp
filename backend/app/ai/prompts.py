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
- Responde en español, 2-3 frases, nada más.
- Cita al menos un dato numérico concreto de los que se te dan (stage, semanas, \
porcentaje de crecimiento, volumen relativo, etc.).
- Explica qué señal técnica y/o fundamental se ha activado y POR QUÉ importa para \
esa empresa en concreto -- no frases genéricas de mercado.
- Nunca recomiendes comprar o vender, ni uses imperativos de inversión ("compra", "entra ahora"). \
Esto es información educativa, no asesoramiento ni una orden de ejecución.
- Si los criterios CAN SLIM verificables son pocos o débiles, dilo explícitamente en vez de \
inflar la explicación."""


def build_user_prompt(
    symbol: str,
    name: str | None,
    sector: str | None,
    combined_score: int,
    weinstein: WeinsteinResult,
    criteria: dict[str, CriterionResult],
) -> str:
    criteria_lines = "\n".join(
        f"- {key}: {'cumple' if c.value is True else 'no cumple' if c.value is False else 'no verificable'} -- {c.detail}"
        for key, c in criteria.items()
    )

    weeks = weinstein.weeks_in_stage
    if weinstein.is_transition_1_to_2 and weeks <= 4:
        transition_line = f"Breakout Stage 1→2 reciente (hace {weeks} semana{'s' if weeks != 1 else ''})"
    elif weinstein.is_transition_1_to_2:
        transition_line = f"Breakout Stage 1→2 confirmado en su momento (lleva {weeks} semanas en Stage 2, NO es reciente)"
    else:
        transition_line = "Sin señal de breakout Stage 1→2"

    return f"""Ticker: {symbol} ({name or 'nombre desconocido'}, sector {sector or 'desconocido'})
Score combinado: {combined_score}/100

Weinstein Stage Analysis:
- Stage actual: {weinstein.stage}
- Semanas en este stage: {weeks}
- {transition_line}
- Pendiente de la media móvil de 30 semanas: {weinstein.ma_slope_pct:+.1%}
- Volumen relativo (vs media 10 semanas): {weinstein.relative_volume:.2f}x

Criterios CAN SLIM:
{criteria_lines}

Escribe la explicación siguiendo las reglas del sistema."""
