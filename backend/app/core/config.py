from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./invest_feed.db"

    def __init__(self, **data):
        super().__init__(**data)
        # Railway entrega postgres:// (legacy); SQLAlchemy 2.0 requiere postgresql://
        if self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace("postgres://", "postgresql://", 1)

    # Nunca hardcodear -- se inyecta vía variable de entorno ANTHROPIC_API_KEY.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"

    # Control de coste: solo se generan explicaciones para las mejores
    # oportunidades de la corrida, no para todo el universo escaneado.
    explanation_min_score: int = 40
    explanation_max_per_run: int = 50

    cors_allow_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3010",
        "https://frontend-inky-nine-48.vercel.app",
        "https://frontend-reputafyseo-2857s-projects.vercel.app",
    ]

    # Scheduler: el screener diario corre automáticamente si enabled=True.
    # screener_schedule_hour/minute en UTC (06:00 UTC = 08:00 CEST).
    screener_schedule_enabled: bool = True
    screener_schedule_hour: int = 6
    screener_schedule_minute: int = 0


settings = Settings()
