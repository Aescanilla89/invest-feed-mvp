"""Diagnóstico puntual de espacio en BD -- solo lectura, no modifica nada.
Uso: python -m scripts.db_diagnostics
"""
from __future__ import annotations

from sqlalchemy import text

from app.core.db import engine


def main() -> None:
    with engine.connect() as conn:
        total = conn.execute(text("SELECT pg_size_pretty(pg_database_size(current_database()))")).scalar()
        print(f"Tamaño total de la BD: {total}")
        print()
        rows = conn.execute(text("""
            SELECT
                relname AS table_name,
                pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
                pg_size_pretty(pg_relation_size(relid)) AS table_size,
                pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) AS index_size,
                n_live_tup AS live_rows,
                n_dead_tup AS dead_rows
            FROM pg_catalog.pg_statio_user_tables
            JOIN pg_stat_user_tables USING (relid)
            ORDER BY pg_total_relation_size(relid) DESC
        """)).fetchall()
        print(f"{'tabla':<28} {'total':>10} {'tabla':>10} {'índices':>10} {'vivas':>10} {'muertas':>10}")
        for r in rows:
            print(f"{r.table_name:<28} {r.total_size:>10} {r.table_size:>10} {r.index_size:>10} {r.live_rows:>10} {r.dead_rows:>10}")


if __name__ == "__main__":
    main()
