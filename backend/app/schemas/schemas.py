"""Pydantic schemas.

`AIAnalysisResult` is the single source of truth for what the AI provider
must return. Any LLM output that fails this validation is rejected — this
is the concrete implementation of the "AI inconsistency" safeguard from the
kickoff pack. Risk is categorical (low/medium/high) by design decision:
LLM-emitted numeric scores are not calibrated (D-05).

`AnalysisOut.risk_score` (D-09) is NOT part of that contract — no provider
returns it, and it never will (`AIAnalysisResult` above has no numeric
field). It's a display-only value computed server-side by
`services/scoring.py` from the already-validated categorical result.
"""
import datetime as dt
from enum import Enum

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Recommendation(str, Enum):
    buy = "buy"
    caution = "caution"
    avoid = "avoid"


class PricePlausibility(str, Enum):
    """Categorical price-plausibility tier (D-08, docs/DESIGN_NOTES.md).
    Deliberately not a numeric or factual market-value claim — same
    rationale as D-05's categorical RiskLevel."""

    plausible = "plausible"
    suspicious = "suspicious"
    too_good_to_be_true = "too_good_to_be_true"


# ---------- Auth ----------
class UserRegister(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    name: str

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """Input for PATCH /auth/me (US-1.4). Additive to SCHEMA-0 — profile
    editing, not a change to the frozen register/login contract. Both
    fields optional; at least one must be provided (enforced in the route).
    Password change is deliberately out of scope, consistent with the
    existing "no password reset" auth stance (docs/DESIGN_NOTES.md).
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None


# ---------- Listings / Analyses ----------
class ListingIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    price: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    source: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=10)
    url: HttpUrl | None = None

    @field_validator("currency")
    @classmethod
    def upper_currency(cls, v: str) -> str:
        return v.upper()


class ListingUrlIn(BaseModel):
    """Input for the URL-fetch preview endpoint (docs/DESIGN_NOTES.md).

    Kept separate from ListingIn on purpose: this never bypasses the frozen
    POST /analyses contract, it only produces suggestions for it.
    """

    url: HttpUrl


class ListingPreviewOut(BaseModel):
    """Best-effort suggestions extracted from a fetched listing page.

    Fields intentionally mirror a subset of ListingIn's optional-to-fill-in
    fields, not the schema itself — the user still reviews/edits these
    before they ever reach ListingIn/POST /analyses.
    """

    url: str
    title: str
    description: str
    # max_length matches ListingIn.source above -- a suggestion that can't
    # fit the field it's suggesting a value for isn't useful (PR #21 review).
    source: str | None = Field(default=None, max_length=120)


class RiskIndicatorOut(BaseModel):
    category: str
    severity: RiskLevel
    explanation: str

    model_config = {"from_attributes": True}


class AIAnalysisResult(BaseModel):
    """The structured contract every AI provider must satisfy."""

    summary: str = Field(min_length=1)
    risk_level: RiskLevel
    risk_indicators: list[RiskIndicatorOut] = Field(max_length=10)
    price_assessment: str = Field(min_length=1)
    price_plausibility: PricePlausibility
    seller_questions: list[str] = Field(min_length=1, max_length=8)
    recommendation: Recommendation


class AnalysisOut(BaseModel):
    id: int
    listing_id: int
    risk_level: RiskLevel
    risk_score: int = Field(ge=0, le=100)
    summary: str
    price_assessment: str
    price_plausibility: PricePlausibility
    recommendation: Recommendation
    seller_questions: list[str]
    risk_indicators: list[RiskIndicatorOut]
    model_used: str
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class AnalysisWithListingOut(AnalysisOut):
    listing_title: str
    listing_price: float
    listing_currency: str
