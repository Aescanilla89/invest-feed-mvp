from __future__ import annotations


LOOKBACK_WEEKS = (13, 26, 52)


def passes_relative_strength(ticker_closes: list[float], benchmark_closes: list[float], min_passes: int = 2) -> bool:
    """Return true when the ticker beats its benchmark on enough lookbacks."""
    if len(ticker_closes) != len(benchmark_closes):
        return False
    passes = 0
    for window in LOOKBACK_WEEKS:
        if len(ticker_closes) <= window:
            continue
        ticker_return = ticker_closes[-1] / ticker_closes[-1 - window] - 1
        benchmark_return = benchmark_closes[-1] / benchmark_closes[-1 - window] - 1
        passes += ticker_return > benchmark_return
    return passes >= min_passes
