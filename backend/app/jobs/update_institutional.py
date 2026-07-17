"""Job trimestral: descarga 13F-HR de las top instituciones y actualiza
institutional_holdings en Postgres.

Uso manual:
    python -m app.jobs.update_institutional
    python -m app.jobs.update_institutional --quarter 2025-12-31  # trimestre específico
    python -m app.jobs.update_institutional --institutions "Vanguard Group,BlackRock"

Normalmente se lanza desde el endpoint /admin/update-institutional.
Solo hace trabajo real si hay datos nuevos (detecta si el quarter ya está en BD).
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, init_db
from app.models.orm import InstitutionalHolding, Ticker
from app.screener.sec_13f import (
    TOP_INSTITUTION_NAMES,
    download_institution_holdings,
    latest_available_quarter,
    normalize_company_name,
    prior_quarter_end,
    search_institution_cik,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("update_institutional")


# ---------------------------------------------------------------------------
# Matching de nombre 13F → ticker de nuestra BD
# ---------------------------------------------------------------------------

def _build_name_map(db: Session) -> dict[str, int]:
    """Mapa de nombre normalizado → ticker_id para todos los tickers en BD."""
    tickers = db.query(Ticker).filter(Ticker.name.isnot(None)).all()
    result: dict[str, int] = {}
    for t in tickers:
        key = normalize_company_name(t.name or "")
        if key:
            result[key] = t.id
        # También indexar por símbolo por si el nameOfIssuer coincide
        result[t.symbol.upper()] = t.id
    return result


def _match_ticker(holding_name: str, name_map: dict[str, int]) -> int | None:
    """Busca el ticker_id más probable para un nameOfIssuer del 13F."""
    normalized = normalize_company_name(holding_name)

    # Búsqueda exacta
    if normalized in name_map:
        return name_map[normalized]

    # Búsqueda parcial: la clave del mapa es prefijo del nombre del holding o viceversa
    for key, ticker_id in name_map.items():
        if len(key) >= 4 and (normalized.startswith(key) or key.startswith(normalized)):
            return ticker_id

    return None


# ---------------------------------------------------------------------------
# Upsert en BD
# ---------------------------------------------------------------------------

def _upsert_holdings(
    db: Session,
    ticker_id: int,
    quarter: date,
    institution_cik: str,
    institution_name: str,
    shares: int,
    value_usd_k: int,
) -> None:
    existing = (
        db.query(InstitutionalHolding)
        .filter_by(ticker_id=ticker_id, quarter=quarter, institution_cik=institution_cik)
        .one_or_none()
    )
    if existing is None:
        db.add(InstitutionalHolding(
            ticker_id=ticker_id,
            quarter=quarter,
            institution_cik=institution_cik,
            institution_name=institution_name,
            shares=shares,
            value_usd_k=value_usd_k,
        ))
    else:
        existing.shares = shares
        existing.value_usd_k = value_usd_k


def _quarter_already_loaded(db: Session, quarter: date, institution_cik: str) -> bool:
    count = (
        db.query(InstitutionalHolding)
        .filter_by(quarter=quarter, institution_cik=institution_cik)
        .limit(1)
        .count()
    )
    return count > 0


# ---------------------------------------------------------------------------
# Job principal
# ---------------------------------------------------------------------------

def run(
    quarter: date | None = None,
    institution_names: list[str] | None = None,
    force: bool = False,
) -> dict:
    init_db()
    db = SessionLocal()
    target_quarter = quarter or latest_available_quarter()
    names_to_process = institution_names or TOP_INSTITUTION_NAMES

    logger.info(
        "Actualizando institutional_holdings para quarter %s (%d instituciones)",
        target_quarter,
        len(names_to_process),
    )

    name_map = _build_name_map(db)
    logger.info("Mapa de nombres: %d tickers en BD", len(name_map))

    stats = {"institutions_processed": 0, "holdings_matched": 0, "holdings_total": 0, "errors": 0}

    for inst_name in names_to_process:
        logger.info("Procesando: %s", inst_name)

        # 1. Obtener CIK
        cik = search_institution_cik(inst_name)
        if not cik:
            logger.warning("No se encontró CIK para %s, se omite", inst_name)
            stats["errors"] += 1
            continue

        # 2. Comprobar si este quarter ya está cargado para esta institución
        if not force and _quarter_already_loaded(db, target_quarter, cik):
            logger.info("%s (CIK %s): quarter %s ya en BD, se omite", inst_name, cik, target_quarter)
            stats["institutions_processed"] += 1
            continue

        # 3. Descargar y parsear 13F -- si el caller pidió un trimestre concreto
        # (`quarter` explícito, no el default "último disponible"), se busca ese
        # filing histórico específico en vez del más reciente.
        holdings, report_date = download_institution_holdings(cik, inst_name, target_quarter=quarter)
        if not holdings:
            logger.warning("%s: sin holdings descargados", inst_name)
            stats["errors"] += 1
            continue

        # Usar el report_date del filing como quarter si coincide con el esperado
        quarter_to_use = report_date if report_date else target_quarter

        # 4. Hacer match con nuestra BD y guardar. Un mismo ticker puede tener
        # varias líneas en el 13F (distintas clases de acción, p.ej. GOOGL/GOOG) —
        # se agregan por ticker_id antes de upsert para no violar la unique
        # constraint (ticker_id, quarter, institution_cik) dentro del mismo commit.
        aggregated: dict[int, tuple[int, int]] = {}
        for h in holdings:
            ticker_id = _match_ticker(h.name_issuer, name_map)
            if ticker_id is None:
                continue
            prev_shares, prev_value = aggregated.get(ticker_id, (0, 0))
            aggregated[ticker_id] = (prev_shares + h.shares, prev_value + h.value_usd_k)

        matched = 0
        for ticker_id, (shares, value_usd_k) in aggregated.items():
            _upsert_holdings(db, ticker_id, quarter_to_use, cik, inst_name, shares, value_usd_k)
            matched += 1

        db.commit()
        stats["institutions_processed"] += 1
        stats["holdings_matched"] += matched
        stats["holdings_total"] += len(holdings)
        logger.info(
            "%s: %d/%d posiciones coinciden con nuestro universo",
            inst_name, matched, len(holdings),
        )

    # Resumen de coverage
    prior_q = prior_quarter_end(target_quarter)
    coverage_sql = text("""
        SELECT t.symbol,
               COUNT(CASE WHEN ih.quarter = :current_q THEN 1 END) AS current_holders,
               COUNT(CASE WHEN ih.quarter = :prior_q THEN 1 END) AS prior_holders
        FROM tickers t
        LEFT JOIN institutional_holdings ih ON ih.ticker_id = t.id
            AND ih.quarter IN (:current_q, :prior_q)
        GROUP BY t.symbol
        HAVING COUNT(CASE WHEN ih.quarter = :current_q THEN 1 END) > 0
        ORDER BY current_holders DESC
        LIMIT 10
    """)
    top_rows = db.execute(coverage_sql, {"current_q": target_quarter, "prior_q": prior_q}).fetchall()
    top_covered = [{"symbol": r[0], "current": r[1], "prior": r[2]} for r in top_rows]

    db.close()
    stats["quarter"] = target_quarter.isoformat()
    stats["top_covered"] = top_covered
    logger.info("Actualización completada: %s", stats)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quarter", type=str, default=None, help="Fecha fin de quarter (YYYY-MM-DD)")
    parser.add_argument("--institutions", type=str, default=None, help="Nombres separados por coma")
    parser.add_argument("--force", action="store_true", help="Re-procesar aunque el quarter ya esté en BD")
    args = parser.parse_args()

    quarter = date.fromisoformat(args.quarter) if args.quarter else None
    names = [n.strip() for n in args.institutions.split(",")] if args.institutions else None
    result = run(quarter=quarter, institution_names=names, force=args.force)
    print(result)


if __name__ == "__main__":
    main()
