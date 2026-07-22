"""Persistence — SQLAlchemy engine, session factory and ORM models.

Workstream: E2 Listing Ingestion & Processing / database design
(owner: Abdallah, with each context owner defining their own entity's columns)

The engine/session scaffolding below is complete — do not change it.
The models are skeletons: PKs, FKs and relationships are fixed (they are the
agreed contract from the ERD); the remaining columns are each owner's work.

Reference ERD: User 1..* Listing 1..* Analysis 1..* RiskIndicator.
Design decisions already agreed (see docs/DESIGN_NOTES.md):
- Analysis stores model_used, prompt_version and raw_response (audit columns).
- Risk is categorical: risk_level in {low, medium, high} — no numeric score.
"""
import datetime as dt

from sqlalchemy import DateTime, ForeignKey, String, create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

from app.core.config import get_settings

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
    # TODO(E2/US-2.1): add listing detail columns per ListingIn schema

    user: Mapped[User] = relationship(back_populates="listings")
    analyses: Mapped[list["Analysis"]] = relationship(back_populates="listing")


class Analysis(Base):
    """E3 owner defines: risk_level, summary, price_assessment, recommendation,
    seller_questions (JSON), model_used, prompt_version, raw_response."""
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    # TODO(E3/US-3.1, US-3.2): add analysis result and audit columns

    listing: Mapped[Listing] = relationship(back_populates="analyses")
    risk_indicators: Mapped[list["RiskIndicator"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )


class RiskIndicator(Base):
    """E3 owner defines: category, severity, explanation."""
    __tablename__ = "risk_indicators"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    # TODO(E3/US-3.1): add category, severity, explanation columns

    analysis: Mapped[Analysis] = relationship(back_populates="risk_indicators")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
