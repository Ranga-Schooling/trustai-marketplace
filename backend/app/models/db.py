"""Persistence — SQLAlchemy engine, session factory and ORM models.

Workstream: E2 Listing Ingestion & Processing / database design
(owner: Abdallah, with each context owner defining their own entity's columns)

The engine/session scaffolding below is complete — do not change it.
Columns for Listing/Analysis/RiskIndicator were drafted from the ERD plus the
matching Pydantic schemas in schemas.py (ListingIn, AIAnalysisResult); PKs,
FKs and relationships were already fixed as the agreed ERD contract. Each
context owner should still review their entity's columns against their
story's needs before US-2.1/US-3.1 land.

Reference ERD: User 1..* Listing 1..* Analysis 1..* RiskIndicator.
Design decisions already agreed (see docs/DESIGN_NOTES.md):
- Analysis stores model_used, prompt_version and raw_response (audit columns).
- Risk is categorical: risk_level in {low, medium, high} — no numeric score.

Schema evolution for the real (Postgres) database is managed by Alembic
(`backend/alembic/`), not by hand-editing tables in place; see
docs/DESIGN_NOTES.md for why and `alembic/versions/` for the initial
revision. Tests still bootstrap via `Base.metadata.create_all` (see
`init_db` below) against a throwaway SQLite file — no migration history
needed there.
"""
import datetime as dt

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

from app.core.config import get_settings
from app.schemas.schemas import Recommendation, RiskLevel

settings = get_settings()

connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    """E1 owner defines: email (unique, indexed), name, password_hash, role."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="buyer")

    listings: Mapped[list["Listing"]] = relationship(back_populates="user")


class Listing(Base):
    """E2 owner defines: title, price, currency, source, description, url."""
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    title: Mapped[str] = mapped_column(String(255))
    # Float, not Numeric: this tool assesses risk, it doesn't move money, so
    # exact decimal precision isn't worth the Decimal<->float friction with
    # the pydantic (float) contract.
    price: Mapped[float] = mapped_column()
    currency: Mapped[str] = mapped_column(String(3))
    source: Mapped[str] = mapped_column(String(120))
    # No length cap here on purpose (see ListingIn.description) — the 4000
    # char guard lives in the route, not the schema or the column.
    description: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(2048), default=None)

    user: Mapped[User] = relationship(back_populates="listings")
    analyses: Mapped[list["Analysis"]] = relationship(back_populates="listing")


class Analysis(Base):
    """E3 owner defines: risk_level, summary, price_assessment, recommendation,
    seller_questions (JSON), model_used, prompt_version, raw_response."""
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    risk_level: Mapped[RiskLevel] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text)
    price_assessment: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[Recommendation] = mapped_column(String(20))
    seller_questions: Mapped[list[str]] = mapped_column(JSON)
    model_used: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(20))
    raw_response: Mapped[str] = mapped_column(Text)

    listing: Mapped[Listing] = relationship(back_populates="analyses")
    risk_indicators: Mapped[list["RiskIndicator"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )


class RiskIndicator(Base):
    """E3 owner defines: category, severity, explanation."""
    __tablename__ = "risk_indicators"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    category: Mapped[str] = mapped_column(String(120))
    severity: Mapped[RiskLevel] = mapped_column(String(20))
    explanation: Mapped[str] = mapped_column(Text)

    analysis: Mapped[Analysis] = relationship(back_populates="risk_indicators")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
