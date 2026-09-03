"""Fear & Greed Index de CNN Business -- gauge de sentimiento de mercado
(0=miedo extremo, 100=codicia extrema), media de 7 indicadores (momentum,
fuerza de precio, amplitud de mercado, put/call, demanda de bonos basura,
volatilidad, demanda de refugio).

Sin API oficial: se consume el mismo endpoint JSON que usa la propia web de
CNN (production.dataviz.cnn.io) -- mismo patrón "no oficial pero estable" ya
usado en el proyecto (Vanguard para Russell 2000 en su día, slickcharts para
Nasdaq100). Requiere Referer/Origin de cnn.com en la petición o responde
418 "I'm a teapot" (bloqueo anti-bot, no un error real del servicio)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests

_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.cnn.com/markets/fear-and-greed",
    "Origin": "https://www.cnn.com",
}


class FearGreedFetchError(RuntimeError):
    """Se lanza si el endpoint de CNN no devuelve un dato plausible."""


@dataclass
class FearGreedPoint:
    date: str  # ISO date (solo fecha, la serie es diaria)
    score: float
    rating: str


@dataclass
class FearGreedData:
    score: float
    rating: str
    timestamp: str
    previous_close: float
    previous_1_week: float
    previous_1_month: float
    previous_1_year: float
    history: list[FearGreedPoint] = field(default_factory=list)


def get_fear_greed_index(history_days: int = 30) -> FearGreedData:
    """`history_days` recorta la serie histórica (CNN devuelve ~1 año) a los
    últimos N puntos -- de sobra para un sparkline, sin arrastrar el año
    completo en cada petición."""
    resp = requests.get(_URL, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    current = data.get("fear_and_greed")
    if not current or "score" not in current:
        raise FearGreedFetchError("Respuesta de CNN sin 'fear_and_greed.score' -- ¿cambió el formato del endpoint?")

    raw_history = (data.get("fear_and_greed_historical") or {}).get("data") or []
    history = [
        FearGreedPoint(
            date=datetime.fromtimestamp(point["x"] / 1000, tz=timezone.utc).date().isoformat(),
            score=round(float(point["y"]), 1),
            rating=point.get("rating", ""),
        )
        for point in raw_history[-history_days:]
    ]

    return FearGreedData(
        score=round(float(current["score"]), 1),
        rating=current.get("rating", ""),
        timestamp=current.get("timestamp", ""),
        previous_close=round(float(current.get("previous_close", current["score"])), 1),
        previous_1_week=round(float(current.get("previous_1_week", current["score"])), 1),
        previous_1_month=round(float(current.get("previous_1_month", current["score"])), 1),
        previous_1_year=round(float(current.get("previous_1_year", current["score"])), 1),
        history=history,
    )
