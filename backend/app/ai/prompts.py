"""Construcción del prompt para la explicación de cada oportunidad.

La instrucción clave es anclar la explicación en las señales numéricas ya
calculadas por el screener (CriterionResult.detail, WeinsteinResult) para
que Claude no caiga en lenguaje genérico de mercado ("tendencia alcista",
"buen momento para comprar"). Si Claude no tiene esos números en el
prompt, no tiene de dónde sacar una explicación concreta.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.screener.canslim import CriterionResult
from app.screener.weinstein import WeinsteinResult


@dataclass
class CatalystContext:
    """Vista mínima de un Catalyst (app.models.orm) para el prompt -- evita que
    app.ai dependa del modelo ORM completo."""
    catalyst_type: str  # "earnings" | "insider_buy"
    title: str
    description: str | None
    extra: dict = field(default_factory=dict)

SYSTEM_PROMPT = """Eres el analista narrativo de Tradefinder, un radar privado de oportunidades para una comunidad cerrada. Tu trabajo es explicar por qué un valor merece atención AHORA, no emitir una orden de compra o venta.

Responde en español con 6 bullets (•), nada más. Cada bullet debe ser una sola frase clara, pero puede ser relativamente completa. El conjunto debe leerse como una tesis breve y entretenida: gancho, contexto, evidencia, catalizadores, tensión y conclusión.

Reglas:
- Usa únicamente los datos del prompt. No inventes noticias, cifras, declaraciones, fechas, resultados ni causalidades.
- Separa hechos de interpretación. Puedes decir "esto sugiere" o "la lectura es", pero no presentes una inferencia como hecho.
- Incluye la fecha de corte cuando ayude a entender la actualidad de la señal.
- No uses lenguaje de recomendación: nunca "compra", "vende", "entra", "sal", "objetivo" ni "garantiza".
- No uses jerga sin traducir: evita Stage, MA20/MA30/MA50, RSI, RS Rating, CAN SLIM, benchmark y volumen relativo; tradúcelos a lenguaje cotidiano y conserva el número importante.
- No menciones una fuente o dato si llega como "no verificable"; en ese caso explica brevemente qué parte del análisis queda pendiente.

Estructura obligatoria:
- Bullet 1 — Gancho: qué está ocurriendo con la acción ahora y qué señal concreta hace que aparezca hoy.
- Bullet 2 — Mercado: si el entorno general acompaña o dificulta la tesis, usando el estado del mercado, su tendencia y el sentimiento disponible.
- Bullet 3 — Negocio y pasado: qué dicen los beneficios, crecimiento, calidad, fuerza relativa, resultados publicados o comportamiento reciente; compara pasado y presente solo cuando el prompt dé ambos datos.
- Bullet 4 — Catalizadores: próximos resultados, resultados pasados, compras de insiders, noticias, presentaciones o declaraciones disponibles; explica por qué podrían cambiar la atención del mercado, sin afirmar que necesariamente lo harán.
- Bullet 5 — Tensión: el principal riesgo, contradicción o dato que impide que esto sea una historia perfecta.
- Bullet 6 — Cierre: por qué la combinación de señal, contexto y catalizadores merece seguimiento ahora y qué dato habría que vigilar para confirmar o invalidar la lectura.

El tono debe tener ritmo y storytelling, como explicárselo a un amigo inteligente que no conoce el análisis técnico. El gancho puede ser atractivo, pero los datos son literales y no se exageran. Esto es discovery educativo, no asesoramiento financiero."""

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
    "news": "Noticia",
    "sec_filing": "Presentación SEC",
    "macro_data": "Dato macro",
}


def _build_catalysts_section(catalysts: list[CatalystContext] | None) -> str:
    if not catalysts:
        return ""
    lines = "\n".join(
        f"- {_CATALYST_TYPE_LABEL.get(c.catalyst_type, c.catalyst_type)}: {c.title}"
        + (f" -- {c.description}" if c.description else "")
        + (f" -- Datos adicionales: {c.extra}" if c.extra else "")
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
    strategy_details: dict | None = None,
    as_of: date | None = None,
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
    strategy_lines = "\n".join(
        f"- {method}: {data.get('details', '')}"
        for method, data in (strategy_details or {}).items()
        if isinstance(data, dict) and data.get('details')
    ) or "Sin análisis adicional de estrategias."
    strategy_section = f"\\nESTRATEGIAS COMPLEMENTARIAS:\\n{strategy_lines}\\n"
    cutoff = as_of.isoformat() if as_of else "no disponible"

    return f"""Ticker: {symbol} ({name or 'nombre desconocido'}, sector {sector or 'desconocido'})
Fecha de corte: {cutoff}
Score combinado: {combined_score}/100
{signal_context and f'{signal_context}'}
{strategy_section}
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
