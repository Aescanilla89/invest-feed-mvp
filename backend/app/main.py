from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, meta, opportunities
from app.core.config import settings
from app.core.db import init_db

app = FastAPI(title="Invest Feed MVP", version="0.1.0")

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


@app.on_event("startup")
def on_startup() -> None:
    init_db()
