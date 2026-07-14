"""TrustAI Marketplace API entrypoint."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.models.db import init_db

app = FastAPI(
    title="TrustAI Marketplace API",
    description=(
        "AI-assisted decision support for online marketplace listings. "
        "This tool provides heuristic risk analysis — it does not detect "
        "every scam and makes no financial guarantees."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the deployed frontend origin in prod
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
