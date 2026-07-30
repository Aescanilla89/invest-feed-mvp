import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin, catalysts, health, meta, opportunities, portfolio
from app.core.config import settings
from app.core.db import init_db

logger = logging.getLogger("invest_feed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Los jobs diarios (screener, cartera, catalizadores, institucional) corren
    # vía GitHub Actions (.github/workflows/daily-jobs.yml), no en proceso: un
    # BackgroundScheduler no sobrevive entre invocaciones de una función serverless.
    init_db()
    yield


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
