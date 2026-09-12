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

    # AI provider: "mock" (deterministic heuristics, no network), "groq",
    # "gpt" (OpenAI), or "gemini" (Card #20). Deploy-time only -- changing
    # this requires a process restart, same as it always has (see
    # docs/DESIGN_NOTES.md D-10 for why a runtime switch is separate scope).
    ai_provider: str = "mock"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-terra"
    visual_inspection_provider: str = "disabled"
    visual_inspection_model: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    prompt_version: str = "v4"

    # Basic abuse guardrails for the public analysis endpoint.
    max_description_chars: int = 4000

    # Provider-consuming attempts allowed per user per rolling 24 hours
    # (D-22). Counts both stored analyses and recorded failures, so a
    # failing provider cannot be used to bypass the cap.
    max_analyses_per_day: int = 50

    # Comma-separated browser origins allowed to call the API cross-origin
    # (D-22). The default covers the Vite dev server; the deployed frontend
    # is served from the same origin as the API and needs no entry here.
    # Set CORS_ALLOW_ORIGINS="*" to restore the previous open behaviour.
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        """Parsed, whitespace-tolerant view of `cors_allow_origins`."""
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    class Config:
        env_file = ".env"
        # pydantic-settings forbids unrecognized keys by default, so any
        # var in .env that isn't (yet) a declared field here crashes the
        # whole app at startup instead of being harmlessly ignored -- hit
        # this directly while testing (D-11). "ignore" is the intuitive
        # behavior for a settings file: unknown keys are just unused.
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
