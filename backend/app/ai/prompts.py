"""Construcción del prompt para la explicación de cada oportunidad.

La instrucción clave es anclar la explicación en las señales numéricas ya
calculadas por el screener (CriterionResult.detail, WeinsteinResult) para
que Claude no caiga en lenguaje genérico de mercado ("tendencia alcista",
"buen momento para comprar"). Si Claude no tiene esos números en el
prompt, no tiene de dónde sacar una explicación concreta.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.screener.canslim import CriterionResult
from app.screener.weinstein import WeinsteinResult


@dataclass
class CatalystContext:
    """Vista mínima de un Catalyst (app.models.orm) para el prompt -- evita que
    app.ai dependa del modelo ORM completo."""
    catalyst_type: str  # "earnings" | "insider_buy"
    title: str
    description: str | None

SYSTEM_PROMPT = """Eres el copywriter de una newsletter de inversión con voz propia: directo, \
con gancho, que vende la historia detrás del dato sin inventar nada que el dato no respalde.

Reglas estrictas:
- Responde en español con 4 bullets (•), 5 solo si aplica el bullet 5 (ver más abajo), nada \
más, sin texto antes ni después.
- Cada bullet es una sola frase punchy con el dato numérico clave cuando aplique — nada de \
lenguaje de informe corporativo ("se observa", "cabe destacar"). Verbos fuertes, ritmo corto, \
la cifra como remate de la frase, no escondida en medio.
- Bullet 1: señal activada (Weinstein Stage o CAN SLIM) como titular — el gancho que hace que \
alguien pare de scrollear, con el dato que la confirma.
- Bullet 2: fortaleza fundamental más relevante (EPS, fuerza relativa, supply) o contexto del \
sector, vendida como el "por qué esto importa", no como una línea de balance.
- Bullet 3: punto de atención o riesgo observable en los datos (lo que podría invalidar la \
señal) — sin suavizarlo, pero sin dramatizarlo tampoco: un dato, una frase.
- Bullet 4: contexto de mercado (criterio M, condición del benchmark SPY) como cierre que \
sitúa la jugada en el tablero general.
- Bullet 5 (SOLO si el prompt incluye una sección "CATALIZADORES"): el catalizador propio del \
ticker (earnings próximos o compra de insider reciente) y por qué ayuda a entender el timing de \
la señal — no lo confundas con el contexto de mercado del bullet 4, que es sobre el benchmark. \
Si el prompt NO incluye esa sección, no escribas un quinto bullet -- quédate en 4.
- El gancho y el ritmo son de marketing; los números y lo que afirman son 100% literales del \
prompt — cero exageración, cero adjetivo que el dato no sostenga.
- Nunca recomiendes comprar o vender, ni uses imperativos de inversión ("compra", "entra ahora"). \
Esto es información educativa, no asesoramiento.

Ejemplo de lo que NO quiero (tono informe, verbo débil, cifra escondida):
"• XYZ se encuentra en Weinstein Stage 2 con 54 semanas de tendencia alcista confirmada y MA30 \
con pendiente de +8,0%, pero sin breakout reciente desde Stage 1."

Ejemplo de lo que SÍ quiero (mismo dato, gancho y ritmo de titular):
"• 54 semanas seguidas en Stage 2 — XYZ lleva más de un año sin salir de tendencia alcista, con \
la MA30 subiendo un +8,0% que lo confirma."

Aplica ese mismo salto de "informe" a "titular" en los 4 bullets, siempre con el dato real como \
ancla, nunca como nota al pie."""

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


_CATALYST_TYPE_LABEL = {
    "earnings": "Earnings",
    "insider_buy": "Compra de insider",
}


def _build_catalysts_section(catalysts: list[CatalystContext] | None) -> str:
    if not catalysts:
        return ""
    lines = "\n".join(
        f"- {_CATALYST_TYPE_LABEL.get(c.catalyst_type, c.catalyst_type)}: {c.title}"
        + (f" -- {c.description}" if c.description else "")
        for c in catalysts
    )
    return f"\nCATALIZADORES:\n{lines}\n"


def build_user_prompt(
    symbol: str,
    name: str | None,
    sector: str | None,
    combined_score: int,
    weinstein: WeinsteinResult,
    criteria: dict[str, CriterionResult],
    signal_type: str | None = None,
    catalysts: list[CatalystContext] | None = None,
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
    catalysts_section = _build_catalysts_section(catalysts)

    return f"""Ticker: {symbol} ({name or 'nombre desconocido'}, sector {sector or 'desconocido'})
Score combinado: {combined_score}/100
{signal_context and f'{signal_context}'}
{catalysts_section}
Weinstein Stage Analysis:
- Stage actual: {weinstein.stage}
- Semanas en este stage: {weeks}
- {transition_line}
- Pendiente MA30: {weinstein.ma_slope_pct:+.1%}
- Volumen relativo (vs media 10 semanas): {weinstein.relative_volume:.2f}x

Criterios CAN SLIM:
{criteria_lines}

Escribe la explicación siguiendo las reglas del sistema."""
