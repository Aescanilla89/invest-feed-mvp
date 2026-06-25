from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./invest_feed.db"

    # Nunca hardcodear -- se inyecta vía variable de entorno ANTHROPIC_API_KEY.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"

    # Control de coste: solo se generan explicaciones para las mejores
    # oportunidades de la corrida, no para todo el universo escaneado.
    explanation_min_score: int = 40
    explanation_max_per_run: int = 50

    cors_allow_origins: list[str] = ["http://localhost:3000", "http://localhost:3010"]


settings = Settings()
