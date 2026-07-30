"""Punto de entrada para el workflow diario de GitHub Actions.
Sustituye al BackgroundScheduler (app/main.py), que no puede correr en el
backend serverless de Vercel. Ejecuta, en orden, el screener, la
actualización de la cartera pública, la detección de catalizadores y (solo
los lunes) la comprobación trimestral de holdings institucionales.
"""
import logging
import sys
from datetime import date

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("daily_jobs")


def main() -> None:
    from app.core.db import init_db
    from app.jobs import detect_catalysts, run_screener, update_institutional, update_portfolio
    from app.screener import universe

    init_db()

    failed = False

    logger.info("Iniciando corrida diaria del screener")
    try:
        symbols_by_universe = universe.get_universe()
        run_screener.run(symbols_by_universe)
    except Exception:
        logger.exception("Error durante la corrida del screener")
        failed = True
    else:
        try:
            update_portfolio.run()
        except Exception:
            logger.exception("Error actualizando la cartera pública")
            failed = True

    logger.info("Iniciando detección de catalizadores")
    try:
        detect_catalysts.run()
    except Exception:
        logger.exception("Error durante la detección de catalizadores")
        failed = True

    # 13F-HR solo se publica ~1 vez por trimestre; comprobar los lunes basta
    # y update_institutional.run() se salta el trabajo si el trimestre ya
    # está cargado (ver _quarter_already_loaded).
    if date.today().weekday() == 0:
        logger.info("Comprobando actualización trimestral de institutional_holdings")
        try:
            update_institutional.run()
        except Exception:
            logger.exception("Error actualizando institutional_holdings")
            failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
