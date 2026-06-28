"""Stage Analysis de Stan Weinstein sobre velas semanales.

Reglas (heurística estándar del método, sobre MA de 30 semanas):
- Stage 2 (avance):     Close > MA30 y MA30 con pendiente claramente positiva.
- Stage 4 (declive):    Close < MA30 y MA30 con pendiente claramente negativa.
- Stage 3 (techo):      Close > MA30 pero MA30 ya aplanada (tras haber subido).
- Stage 1 (base):       Close < MA30 pero MA30 aplanada (tras haber bajado).

La pendiente se mide como variación porcentual de la MA en los últimos
`slope_lookback_weeks`. Un slope con |valor| <= slope_threshold se
considera "aplanada".

La transición 1->2 (la señal de compra clásica) se marca cuando el stage
actual es 2, el stage inmediatamente anterior a la racha actual era 1,
y la semana de cruce tuvo volumen relativo >= breakout_volume_ratio.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

MA_WINDOW_WEEKS = 30
SLOPE_LOOKBACK_WEEKS = 5
SLOPE_FLAT_THRESHOLD = 0.005  # 0.5% de variación de la MA en slope_lookback_weeks
BREAKOUT_VOLUME_RATIO = 1.5
VOLUME_AVG_WINDOW = 10
MIN_WEEKS_REQUIRED = MA_WINDOW_WEEKS + SLOPE_LOOKBACK_WEEKS + 1


class InsufficientDataError(ValueError):
    pass


@dataclass
class WeinsteinResult:
    stage: int  # 1, 2, 3 o 4
    weeks_in_stage: int
    ma_slope_pct: float
    relative_volume: float
    is_transition_1_to_2: bool


def _stage_series(close: pd.Series, ma: pd.Series, slope_pct: pd.Series) -> pd.Series:
    above = close > ma
    rising = slope_pct > SLOPE_FLAT_THRESHOLD
    falling = slope_pct < -SLOPE_FLAT_THRESHOLD

    stage = pd.Series(index=close.index, dtype="float64")
    stage[above & rising] = 2
    stage[~above & falling] = 4
    stage[above & ~rising & ~falling] = 3
    stage[~above & ~falling & ~rising] = 1
    # Casos mixtos no cubiertos arriba (p.ej. above & falling: precio por
    # encima de una MA que ya cae -- transición tardía de 2 a 4): se
    # tratan como continuación del último stage válido conocido.
    stage = stage.ffill()
    return stage


def analyze(weekly_prices: pd.DataFrame) -> WeinsteinResult:
    """weekly_prices: DataFrame con columnas Close, Volume, índice fecha
    ascendente, una fila por semana."""
    if len(weekly_prices) < MIN_WEEKS_REQUIRED:
        raise InsufficientDataError(
            f"Se necesitan al menos {MIN_WEEKS_REQUIRED} semanas de histórico, "
            f"se recibieron {len(weekly_prices)}"
        )

    close = weekly_prices["Close"]
    volume = weekly_prices["Volume"]
    ma = close.rolling(MA_WINDOW_WEEKS).mean()
    slope_pct = ma.pct_change(periods=SLOPE_LOOKBACK_WEEKS)
    avg_volume = volume.rolling(VOLUME_AVG_WINDOW).mean()
    relative_volume_series = volume / avg_volume

    stages = _stage_series(close, ma, slope_pct).dropna()
    if stages.empty:
        raise InsufficientDataError("No se pudo calcular ningún stage con el histórico disponible")

    current_stage = int(stages.iloc[-1])

    weeks_in_stage = 1
    for s in stages.iloc[-2::-1]:
        if int(s) == current_stage:
            weeks_in_stage += 1
        else:
            break

    is_transition = False
    if current_stage == 2:
        # La clasificación de stage usa una MA con ventana de slope, así que
        # tiene lag respecto al cruce real del precio sobre la MA. Para
        # detectar la transición 1->2 se busca el cruce real más reciente
        # (close pasa de <= MA a > MA) y se valida que el stage justo antes
        # de ese cruce fuera 1, y que el volumen relativo en ese cruce (o
        # poco después, mientras dura el cruce) confirme el breakout.
        above = close > ma
        crossover = above & ~above.shift(1, fill_value=False)
        crossover = crossover.loc[stages.index]  # restringido a semanas con stage calculable
        crossover_dates = stages.index[crossover]

        if len(crossover_dates) > 0:
            last_crossover = crossover_dates[-1]
            idx_pos = stages.index.get_loc(last_crossover)
            if idx_pos > 0:
                prior_stage = int(stages.iloc[idx_pos - 1])
                # Volumen confirmatorio exigido en la semana exacta del cruce
                # (no en ventana amplia, para evitar falsos positivos)
                crossover_vol = (
                    relative_volume_series.loc[last_crossover]
                    if last_crossover in relative_volume_series.index
                    else float("nan")
                )
                if prior_stage == 1 and pd.notna(crossover_vol) and crossover_vol >= BREAKOUT_VOLUME_RATIO:
                    is_transition = True

    return WeinsteinResult(
        stage=current_stage,
        weeks_in_stage=weeks_in_stage,
        ma_slope_pct=float(slope_pct.iloc[-1]) if pd.notna(slope_pct.iloc[-1]) else 0.0,
        relative_volume=float(relative_volume_series.iloc[-1]) if pd.notna(relative_volume_series.iloc[-1]) else float("nan"),
        is_transition_1_to_2=is_transition,
    )
