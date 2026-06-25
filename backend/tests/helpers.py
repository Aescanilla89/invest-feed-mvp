"""Generadores de datos sintéticos OHLCV semanales para tests del screener."""
from __future__ import annotations

import numpy as np
import pandas as pd


def make_weekly_df(closes: list[float], volumes: list[float] | None = None, start: str = "2022-01-07") -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range(start=start, periods=n, freq="W-FRI")
    if volumes is None:
        volumes = [1_000_000.0] * n
    closes_arr = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {
            "Open": closes_arr,
            "High": closes_arr * 1.01,
            "Low": closes_arr * 0.99,
            "Close": closes_arr,
            "Volume": volumes,
        },
        index=idx,
    )


def steady_uptrend(n: int = 90, start_price: float = 50, end_price: float = 150) -> list[float]:
    return list(np.linspace(start_price, end_price, n))


def steady_downtrend(n: int = 90, start_price: float = 150, end_price: float = 50) -> list[float]:
    return list(np.linspace(start_price, end_price, n))


def flat_sideways(n: int = 90, level: float = 100, noise_std: float = 0.5, seed: int = 42) -> list[float]:
    rng = np.random.default_rng(seed)
    return list(level + rng.normal(0, noise_std, n))
