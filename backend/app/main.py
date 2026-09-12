"""TrustAI Marketplace API entrypoint."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.models.db import init_db

settings = get_settings()

app = FastAPI(
    title="TrustAI Marketplace API",
    description=(
        "AI-assisted decision support for online marketplace listings. "
        "This tool provides heuristic risk analysis — it does not detect "
        "every scam and makes no financial guarantees."
    ),
    version="0.1.0",
)

# The deployed frontend is served from the same origin as the API, so this
# list only has to cover browsers calling the API cross-origin -- the Vite
# dev server by default (D-22). Configured via CORS_ALLOW_ORIGINS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
