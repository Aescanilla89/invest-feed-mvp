import pytest
from fastapi import HTTPException

from app.api.routes import health
from app.core.config import Settings


def test_health_liveness():
    assert health.health() == {"status": "ok"}


def test_health_readiness_checks_database(monkeypatch):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, statement):
            assert "SELECT 1" in str(statement)

    class Engine:
        def connect(self):
            return Connection()

    monkeypatch.setattr(health, "engine", Engine())
    assert health.readiness() == {"status": "ok", "database": "ok"}


def test_health_readiness_returns_503_when_database_fails(monkeypatch):
    class Engine:
        def connect(self):
            raise RuntimeError("database down")

    monkeypatch.setattr(health, "engine", Engine())
    with pytest.raises(HTTPException) as error:
        health.readiness()
    assert error.value.status_code == 503


def test_cors_accepts_comma_separated_environment_value():
    settings = Settings(cors_allow_origins="https://one.example, https://two.example")
    assert settings.cors_allow_origins == ["https://one.example", "https://two.example"]


def test_cors_rejects_wildcard():
    with pytest.raises(ValueError):
        Settings(cors_allow_origins="*")
