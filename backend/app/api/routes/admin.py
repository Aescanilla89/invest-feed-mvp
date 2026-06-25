"""Endpoints de administración para operaciones manuales.
Protegidos por ADMIN_SECRET — no exponer públicamente sin token."""
import threading

from fastapi import APIRouter, Depends, HTTPException, Header

from app.core.config import settings
from app.jobs import run_screener
from app.screener import universe

router = APIRouter(prefix="/admin", tags=["admin"])


def _verify_token(x_admin_secret: str | None = Header(default=None)) -> None:
    if not settings.admin_secret or x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/run-screener")
def trigger_screener(
    limit: int | None = None,
    _: None = Depends(_verify_token),
) -> dict:
    """Lanza el screener en background. Devuelve inmediatamente."""
    def _job():
        symbols = universe.get_universe()
        if limit:
            symbols = {k: v[:limit] for k, v in symbols.items()}
        run_screener.run(symbols)

    thread = threading.Thread(target=_job, daemon=True)
    thread.start()
    tickers_approx = limit * 2 if limit else "~600"
    return {"status": "started", "tickers": tickers_approx}
