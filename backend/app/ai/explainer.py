"""Cliente Claude para generar la explicación en lenguaje natural de cada
oportunidad. max_tokens deliberadamente bajo (la explicación son 2-3
frases) para mantener el coste por llamada mínimo; el control de CUÁNTAS
llamadas se hacen por corrida vive en cache.py / run_screener.py, no aquí.
"""
from __future__ import annotations

import logging

import anthropic

from app.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from app.core.config import settings
from app.screener.canslim import CriterionResult
from app.screener.weinstein import WeinsteinResult

logger = logging.getLogger("ai.explainer")

MAX_TOKENS = 350


class ExplanationError(RuntimeError):
    pass


class ClaudeExplainer:
    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise ExplanationError(
                "ANTHROPIC_API_KEY no configurada. Añádela como variable de entorno "
                "(nunca hardcodeada) para generar explicaciones."
            )
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    def generate(
        self,
        symbol: str,
        name: str | None,
        sector: str | None,
        combined_score: int,
        weinstein: WeinsteinResult,
        criteria: dict[str, CriterionResult],
        signal_type: str | None = None,
    ) -> str:
        user_prompt = build_user_prompt(symbol, name, sector, combined_score, weinstein, criteria, signal_type)
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.APIError as exc:
            raise ExplanationError(f"Fallo llamando a la API de Claude para {symbol}: {exc}") from exc

        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise ExplanationError(f"Respuesta vacía de Claude para {symbol}")
        return text
