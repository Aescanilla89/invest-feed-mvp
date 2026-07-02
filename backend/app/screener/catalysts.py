"""Detección de catalizadores de inversión via yfinance.

Fuentes:
- Earnings: ticker.earnings_dates — EPS publicados en los últimos N días
- Insider buying: ticker.insider_transactions — compras de directivos en los últimos N días

Se ejecuta sobre un subset de tickers (los que tienen oportunidades recientes),
no sobre el universo completo, para mantener el tiempo de ejecución manejable.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

logger = logging.getLogger("catalysts")


@dataclass
class CatalystData:
    catalyst_type: str  # "earnings" | "insider_buy"
    symbol: str
    title: str
    source_id: str
    description: str | None = None
    extra: dict = field(default_factory=dict)


def detect_earnings(symbols: list[str], lookback_days: int = 3) -> list[CatalystData]:
    """Detecta earnings publicados en los últimos `lookback_days` días."""
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance no está instalado")
        return []

    cutoff = date.today() - timedelta(days=lookback_days)
    results: list[CatalystData] = []

    for symbol in symbols:
        try:
            t = yf.Ticker(symbol)
            dates_df = t.earnings_dates
            if dates_df is None or dates_df.empty:
                continue

            for dt_idx in dates_df.index:
                d = _to_date(dt_idx)
                if d is None or d < cutoff or d > date.today():
                    continue

                row = dates_df.loc[dt_idx]
                eps_est = _safe_float(row.get("EPS Estimate"))
                eps_act = _safe_float(row.get("Reported EPS"))
                surprise = _safe_float(row.get("Surprise(%)"))

                # Si no hay EPS real publicado, no es un earnings ya ocurrido
                if eps_act is None:
                    continue

                if eps_est is not None and eps_act > eps_est:
                    pct = round(((eps_act - eps_est) / abs(eps_est)) * 100, 1) if eps_est != 0 else None
                    title = "Earnings beat" + (f" +{pct}%" if pct is not None else "")
                elif eps_est is not None and eps_act < eps_est:
                    title = "Earnings miss"
                else:
                    title = "Resultados publicados"

                desc_parts = []
                if eps_est is not None:
                    desc_parts.append(f"EPS estimado: {eps_est:.2f}")
                if eps_act is not None:
                    desc_parts.append(f"EPS real: {eps_act:.2f}")
                if surprise is not None:
                    desc_parts.append(f"Sorpresa: {surprise:+.1f}%")

                results.append(CatalystData(
                    catalyst_type="earnings",
                    symbol=symbol,
                    title=title,
                    source_id=f"earnings_{symbol}_{d.isoformat()}",
                    description=", ".join(desc_parts) if desc_parts else None,
                    extra={
                        "earnings_date": d.isoformat(),
                        "eps_estimated": eps_est,
                        "eps_actual": eps_act,
                        "surprise_pct": surprise,
                    },
                ))
                break  # solo el más reciente por ticker

        except Exception:
            logger.debug("Error obteniendo earnings de %s", symbol, exc_info=True)

    logger.info("Earnings detectados: %d de %d tickers", len(results), len(symbols))
    return results


def detect_insider_buys(symbols: list[str], lookback_days: int = 14) -> list[CatalystData]:
    """Detecta compras de insiders (directivos/CEO) en los últimos `lookback_days` días."""
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance no está instalado")
        return []

    cutoff = date.today() - timedelta(days=lookback_days)
    results: list[CatalystData] = []

    for symbol in symbols:
        try:
            t = yf.Ticker(symbol)
            tx = t.insider_transactions
            if tx is None or tx.empty:
                continue

            for _, row in tx.iterrows():
                # Normaliza nombre de columna de fecha (varía según versión de yfinance)
                tx_date = _to_date(row.get("Start Date") or row.get("Date") or row.get("date"))
                if tx_date is None or tx_date < cutoff:
                    continue

                # Filtrar solo compras (no ventas ni ejercicio de opciones)
                transaction_type = str(row.get("Transaction", "") or row.get("transaction", "")).lower()
                text_col = str(row.get("Text", "") or row.get("text", "")).lower()
                is_purchase = (
                    "purchase" in transaction_type
                    or "bought" in text_col
                    or "purchase" in text_col
                )
                is_sale = "sale" in transaction_type or "sold" in text_col
                if not is_purchase or is_sale:
                    continue

                insider = str(row.get("Insider") or row.get("insider") or "Directivo")
                position = str(row.get("Position") or row.get("Title") or "")
                shares = _safe_int(row.get("Shares") or row.get("shares"))
                value = _safe_int(row.get("Value") or row.get("value"))

                title = f"Compra insider: {insider}"
                if position:
                    title += f" ({position})"

                desc_parts = []
                if shares:
                    desc_parts.append(f"{shares:,} acciones")
                if value:
                    desc_parts.append(f"${value:,}")

                source_key = insider[:30].replace(" ", "_")
                results.append(CatalystData(
                    catalyst_type="insider_buy",
                    symbol=symbol,
                    title=title[:255],
                    source_id=f"insider_{symbol}_{tx_date.isoformat()}_{source_key}",
                    description=", ".join(desc_parts) if desc_parts else None,
                    extra={
                        "transaction_date": tx_date.isoformat(),
                        "insider": insider,
                        "position": position,
                        "shares": shares,
                        "value_usd": value,
                    },
                ))
                break  # solo la compra más reciente por ticker

        except Exception:
            logger.debug("Error obteniendo insider transactions de %s", symbol, exc_info=True)

    logger.info("Insider buys detectados: %d de %d tickers", len(results), len(symbols))
    return results


def _to_date(val) -> date | None:
    if val is None:
        return None
    if hasattr(val, "date"):
        return val.date()
    if hasattr(val, "to_pydatetime"):
        return val.to_pydatetime().date()
    if isinstance(val, date):
        return val
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(val)).date()
    except Exception:
        return None


def _safe_float(val) -> float | None:
    try:
        if val is None:
            return None
        f = float(val)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> int | None:
    f = _safe_float(val)
    return int(f) if f is not None else None
