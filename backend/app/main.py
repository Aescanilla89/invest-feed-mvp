import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin, catalysts, health, meta, opportunities, portfolio
from app.core.config import settings
from app.core.db import init_db
from app.jobs import detect_catalysts, run_screener, update_institutional, update_portfolio
from app.screener import universe

logger = logging.getLogger("invest_feed")


def _run_weekly_institutional_update() -> None:
    """13F-HR solo se publica ~1 vez por trimestre (deadline: 45 días tras cierre),
    así que revisar semanalmente es más que suficiente para no perderse el día en
    que el trimestre nuevo esté disponible. Sin efecto si el trimestre ya está
    cargado -- update_institutional.run() lo comprueba por institución y se salta
    el trabajo (ver _quarter_already_loaded en app/jobs/update_institutional.py)."""
    logger.info("Scheduler: comprobando actualización trimestral de institutional_holdings")
    try:
        update_institutional.run()
    except Exception:
        logger.exception("Scheduler: error actualizando institutional_holdings")


def _run_daily_screener() -> None:
    logger.info("Scheduler: iniciando corrida diaria del screener")
    try:
        symbols_by_universe = universe.get_universe()
        run_screener.run(symbols_by_universe)
    except Exception:
        logger.exception("Scheduler: error durante la corrida diaria")
        return
    try:
        update_portfolio.run()
    except Exception:
        logger.exception("Scheduler: error actualizando la cartera pública")


def _run_daily_catalysts() -> None:
    logger.info("Scheduler: iniciando detección diaria de catalizadores")
    try:
        detect_catalysts.run()
    except Exception:
        logger.exception("Scheduler: error durante la detección de catalizadores")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    scheduler: BackgroundScheduler | None = None
    if settings.screener_schedule_enabled:
        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(
            _run_daily_screener,
            "cron",
            hour=settings.screener_schedule_hour,
            minute=settings.screener_schedule_minute,
            id="daily_screener",
            replace_existing=True,
        )
        # Catalysts corren 30 min después del screener
        catalysts_hour = settings.screener_schedule_hour
        catalysts_minute = (settings.screener_schedule_minute + 30) % 60
        if settings.screener_schedule_minute + 30 >= 60:
            catalysts_hour = (catalysts_hour + 1) % 24
        scheduler.add_job(
            _run_daily_catalysts,
            "cron",
            hour=catalysts_hour,
            minute=catalysts_minute,
            id="daily_catalysts",
            replace_existing=True,
        )
        # Corre 45 min después del screener, mismo día que catalysts pero solo lunes
        institutional_hour = settings.screener_schedule_hour
        institutional_minute = (settings.screener_schedule_minute + 45) % 60
        if settings.screener_schedule_minute + 45 >= 60:
            institutional_hour = (institutional_hour + 1) % 24
        scheduler.add_job(
            _run_weekly_institutional_update,
            "cron",
            day_of_week="mon",
            hour=institutional_hour,
            minute=institutional_minute,
            id="weekly_institutional_update",
            replace_existing=True,
        )
        scheduler.start()
        logger.info(
            "Scheduler iniciado: screener corre cada día a las %02d:%02dZ",
            settings.screener_schedule_hour,
            settings.screener_schedule_minute,
        )

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido")


app = FastAPI(title="Invest Feed MVP", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(opportunities.router, prefix="/api")
app.include_router(catalysts.router, prefix="/api")
app.include_router(meta.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(portfolio.router, prefix="/api")
