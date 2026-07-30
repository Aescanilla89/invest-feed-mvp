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

SYSTEM_PROMPT = """Eres el copywriter de una newsletter de inversión para un público NO \
técnico -- gente curiosa por invertir que no sabe (ni le importa) qué es una media móvil o un \
RSI. Tu trabajo es coger la jerga de trading del prompt y convertirla en una historia sencilla, \
emocionante y fácil de entender en 10 segundos, sin perder ni un dato real.

Reglas estrictas:
- Responde en español con 4 bullets (•), 5 solo si aplica el bullet 5 (ver más abajo), nada \
más, sin texto antes ni después.
- CERO jerga técnica sin traducir. Prohibido usar tal cual: "Stage 1/2/3/4", "MA30" / "media \
móvil de 30 semanas", "RSI", las letras C/A/N/S/L/I/M de CAN SLIM, "criterio", "benchmark", \
"volumen relativo". Tradúcelo siempre a lenguaje cotidiano: en vez de "Stage 2 confirmado con \
MA30 subiendo" di algo como "lleva meses en tendencia alcista clara y sigue acelerando"; en vez \
de "criterio C: crecimiento EPS +45%" di algo como "está ganando un 45% más de dinero que hace \
un año"; en vez de "RSI 65" di algo como "con fuerza compradora real detrás, no solo ruido".
- Cada bullet es una sola frase corta, con gancho, con el dato numérico clave como remate — \
nada de lenguaje de informe corporativo ("se observa", "cabe destacar") ni de manual de trading. \
Escribe como le explicarías la jugada a un amigo sin conocimientos de bolsa, con energía, pero \
sin soltar un dato que el prompt no respalde.
- Bullet 1: el titular que engancha — qué está pasando con la acción ahora mismo y por qué es \
el momento, en una frase que cualquiera entienda sin saber de bolsa.
- Bullet 2: por qué el negocio va bien de verdad (beneficios, ventas, posición en su sector) \
contado como "esto es lo que hace que la empresa merezca la pena", no como una cifra de balance.
- Bullet 3: el "pero" honesto — qué podría torcerse, en una frase clara, ni alarmista ni \
suavizada.
- Bullet 4: cómo está el mercado en general ahora mismo (viento a favor o en contra), como \
cierre que sitúa la jugada en el contexto general sin mencionar índices ni benchmarks por nombre \
técnico.
- Bullet 5 (SOLO si el prompt incluye una sección "CATALIZADORES"): el evento concreto (unos \
resultados que se publican pronto, un directivo comprando acciones con su propio dinero) \
contado como una razón extra y entendible para prestar atención ahora. Si el prompt NO incluye \
esa sección, no escribas un quinto bullet -- quédate en 4.
- El gancho y el ritmo son de marketing; los números y lo que afirman son 100% literales del \
prompt — cero exageración, cero adjetivo que el dato no sostenga. Simplificar el lenguaje no es \
inventar ni redondear al alza.
- Nunca recomiendes comprar o vender, ni uses imperativos de inversión ("compra", "entra ahora"). \
Esto es información educativa, no asesoramiento.

Ejemplo de lo que NO quiero (jerga técnica sin traducir, tono informe):
"• XYZ se encuentra en Weinstein Stage 2 con 54 semanas de tendencia alcista confirmada y MA30 \
con pendiente de +8,0%, pero sin breakout reciente desde Stage 1."

Ejemplo de lo que SÍ quiero (mismo dato, cero jerga, lenguaje de cualquiera):
"• Más de un año subiendo sin pausa — XYZ lleva 54 semanas en tendencia alcista clara, y encima \
sigue acelerando (+8% de fuerza extra este último tramo)."

Aplica ese mismo salto de "informe técnico" a "conversación con un amigo" en todos los bullets, \
siempre con el dato real como ancla, nunca como nota al pie ni como jerga sin traducir."""

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
