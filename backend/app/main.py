import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin, health, meta, opportunities
from app.core.config import settings
from app.core.db import init_db
from app.jobs import run_screener
from app.screener import universe

logger = logging.getLogger("invest_feed")


def _run_daily_screener() -> None:
    logger.info("Scheduler: iniciando corrida diaria del screener")
    try:
        symbols_by_universe = universe.get_universe()
        run_screener.run(symbols_by_universe)
    except Exception:
        logger.exception("Scheduler: error durante la corrida diaria")


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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(opportunities.router, prefix="/api")
app.include_router(meta.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
