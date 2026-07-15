"""Application settings, loaded from environment variables.

All deployment-specific values (secrets, database URL, AI provider) are
injected via environment so the same image runs locally, in CI, and on Render.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "TrustAI Marketplace API"

    # SQLite by default for local dev/tests; set DATABASE_URL to a Postgres
    # DSN when running with Docker Compose or a managed Postgres service.
    # Example for Compose: postgresql+psycopg2://trustai:trustai@db:5432/trustai
    database_url: str = "sqlite:///./trustai.db"

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60 * 24

    # AI provider: "mock" (deterministic heuristics, no network) or "groq".
    ai_provider: str = "mock"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    prompt_version: str = "v1"

    # Basic abuse guardrails for the public analysis endpoint.
    max_description_chars: int = 4000

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
