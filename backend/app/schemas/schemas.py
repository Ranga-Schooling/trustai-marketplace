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
import re
from enum import Enum

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator

IMAGE_DATA_URI_RE = re.compile(r"^data:image/(jpeg|png|webp|gif);base64,[A-Za-z0-9+/]+=*$")


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Recommendation(str, Enum):
    buy = "buy"
    caution = "caution"
    avoid = "avoid"


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
    # Stretch (US-2.4, D-12): optional listing photos as base64 data URIs.
    # Format is validated here; count/size caps are enforced in the route
    # from settings, same split as description's length guard (no
    # max_length here on purpose, matching that existing pattern).
    images: list[str] = Field(default_factory=list)

    @field_validator("currency")
    @classmethod
    def upper_currency(cls, v: str) -> str:
        return v.upper()

    @field_validator("images")
    @classmethod
    def validate_image_data_uris(cls, v: list[str]) -> list[str]:
        for image in v:
            if not IMAGE_DATA_URI_RE.match(image):
                raise ValueError(
                    "Each image must be a base64 data URI (image/jpeg, png, webp, or gif)"
                )
        return v


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
    seller_questions: list[str] = Field(min_length=1, max_length=8)
    recommendation: Recommendation


class AnalysisOut(BaseModel):
    id: int
    listing_id: int
    risk_level: RiskLevel
    risk_score: int = Field(ge=0, le=100)
    summary: str
    price_assessment: str
    recommendation: Recommendation
    seller_questions: list[str]
    risk_indicators: list[RiskIndicatorOut]
    model_used: str
    created_at: dt.datetime
    # Stretch (US-2.4, D-12): echoes the listing's images back so both the
    # immediate post-submit result and a reopened history entry can render
    # them, without the frontend needing two different data paths.
    listing_images: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class AnalysisWithListingOut(AnalysisOut):
    listing_title: str
    listing_price: float
    listing_currency: str
