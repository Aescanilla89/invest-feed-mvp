import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

from app.api.routes import admin, catalysts, health, meta, opportunities, portfolio
from app.core.config import settings
from app.core.db import init_db

logger = logging.getLogger("invest_feed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.app_env == "production" and not settings.database_url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("APP_ENV=production requires a PostgreSQL DATABASE_URL")
    # Los jobs diarios (screener, cartera, catalizadores, institucional) corren
    # vía GitHub Actions (.github/workflows/daily-jobs.yml), no en proceso: un
    # BackgroundScheduler no sobrevive entre invocaciones de una función serverless.
    init_db()
    yield


app = FastAPI(title="Invest Feed MVP", version="0.1.0", lifespan=lifespan)

@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed", extra={"request_id": request_id, "path": request.url.path})
        raise
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    if request.method == "GET" and request.url.path in {"/api/opportunities", "/api/portfolio", "/api/catalysts"}:
        response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    logger.info("request_complete", extra={"request_id": request_id, "method": request.method, "path": request.url.path, "status_code": response.status_code, "elapsed_ms": elapsed_ms})
    return response

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
