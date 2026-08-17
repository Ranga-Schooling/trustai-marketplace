"""API routes — the HTTP surface of the system.

The route signatures, paths, status codes and response models below are the
agreed API contract (they generate the OpenAPI docs at /docs that the
frontend builds against). Keep the signatures; implement the bodies.

Ownership:
- /auth/*            E1 (Ranga)     US-1.1, US-1.2, US-1.3, US-1.4, US-1.5
- POST /analyses     E2 + E3 pair   US-2.1, US-2.2, US-3.1
- GET /analyses*     E2 (Abdallah)  US-4.1
- POST /listings/preview  E2        US-2.3 (URL fetch preview — see below)

Agreed behaviors (docs/DESIGN_NOTES.md):
- The listing row is committed BEFORE the AI call, so a provider outage
  never loses user input; on AnalysisFailure return 502 with a message that
  the listing was saved. [US-2.2]
- History queries are scoped to the authenticated user; fetching another
  user's analysis by id returns 404, not 403. [US-1.3 AC2]
- POST /listings/preview is additive, not a change to the frozen
  ListingIn/POST /analyses contract (CLAUDE.md SCHEMA-0): it only suggests
  values, the user still submits through the unchanged endpoint. [US-2.3]
- PATCH /auth/me is additive to the frozen register/login contract
  (CLAUDE.md SCHEMA-0): profile editing (name/email), no password change,
  consistent with the existing minimal-auth stance. [US-1.4]
- DELETE /auth/me is additive to the frozen contract (D-12): hard-deletes
  the user and cascades to their listings/analyses/risk_indicators via the
  ORM relationships in models/db.py. No soft-delete, no confirmation step
  server-side (the client owns confirming intent), no re-auth/password
  check -- consistent with the existing minimal-auth stance. [US-1.5]
- AnalysisOut.risk_score (D-09) is computed server-side by
  services/scoring.py from the already-validated risk_level/
  risk_indicators; no AIProvider returns it, AIAnalysisResult is
  unchanged. [Trello #27]
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.models.db import Analysis, Listing, RiskIndicator, User, get_db
from app.services.ai import AnalysisFailure, get_provider
from app.services.scoring import compute_risk_score
from app.schemas.schemas import (
    AnalysisOut,
    AnalysisWithListingOut,
    ListingIn,
    ListingPreviewOut,
    ListingUrlIn,
    TokenResponse,
    UserLogin,
    UserOut,
    UserRegister,
    UserUpdate,
)
from app.services.listing_fetch import FetchError, fetch_listing_preview

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


@router.get("/health")
def health() -> dict:
    """Liveness probe — already done, used by the Sprint 1 deploy skeleton."""
    return {"status": "ok"}


@router.post("/auth/register", response_model=UserOut, status_code=201)
def register(body: UserRegister, db: Session = Depends(get_db)):
    """[US-1.1] Create a user; 409 on duplicate email (store emails lowercased)."""
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(email=email, name=body.name, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/auth/login", response_model=TokenResponse)
def login(body: UserLogin, db: Session = Depends(get_db)):
    """[US-1.2] Verify credentials, return a bearer token; 401 on failure
    without revealing which field was wrong."""
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
    )
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise invalid_credentials

    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    """[US-1.3] Return the authenticated user's profile."""
    return user


@router.post("/listings/preview", response_model=ListingPreviewOut)
def preview_listing_url(
    body: ListingUrlIn,
    user: User = Depends(get_current_user),
):
    """[US-2.3] Fetch a listing URL server-side and suggest title/description
    values for the submission form. Does not persist anything and does not
    touch the frozen ListingIn/POST /analyses contract — the user still
    reviews and submits manually. 422 if the URL cannot be safely or
    successfully fetched."""
    try:
        return fetch_listing_preview(str(body.url))
    except FetchError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.patch("/auth/me", response_model=UserOut)
def update_me(
    body: UserUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[US-1.4] Update the authenticated user's name and/or email.
    400 if neither field is provided; 409 on duplicate email (store emails
    lowercased, matching register)."""
    if body.name is None and body.email is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    if body.email is not None:
        new_email = body.email.lower()
        if new_email != user.email:
            if db.query(User).filter(User.email == new_email).first() is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
            user.email = new_email

    if body.name is not None:
        user.name = body.name

    db.commit()
    db.refresh(user)
    return user


@router.delete("/auth/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[US-1.5] Permanently delete the authenticated user and every listing/
    analysis/risk_indicator they own (hard delete, cascaded via the ORM
    relationships in models/db.py -- no soft-delete, no undo). The client
    is responsible for confirming intent before calling this; the token
    used to authenticate stops working immediately after (get_current_user
    401s on an unknown user id)."""
    db.delete(user)
    db.commit()


@router.post("/analyses", response_model=AnalysisOut, status_code=201)
def create_analysis(
    body: ListingIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[US-2.1, US-2.2, US-3.1] Persist the listing, run the AI provider,
    persist the validated analysis with audit columns, return it.
    Enforce settings.max_description_chars with 413. 502 on AnalysisFailure
    (listing already saved)."""
    if len(body.description) > settings.max_description_chars:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Description exceeds {settings.max_description_chars} characters",
        )
    listing = Listing(
        user_id=user.id,
        title=body.title,
        price=body.price,
        currency=body.currency,
        source=body.source,
        description=body.description,
        url=str(body.url) if body.url is not None else None,
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    try:
        provider = get_provider()
        result, raw_response = provider.analyze(body)
    except AnalysisFailure as exc:
        cause_type = type(exc.__cause__).__name__ if exc.__cause__ is not None else "none"
        logger.error(
            "AI analysis failed listing_id=%s provider=%s "
            "failure_type=%s cause_type=%s",
            listing.id,
            settings.ai_provider,
            type(exc).__name__,
            cause_type,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI analysis failed; the listing was saved.",
        ) from exc
    analysis = Analysis(
        listing_id=listing.id,
        risk_level=result.risk_level.value,
        risk_score=compute_risk_score(result.risk_level, result.risk_indicators),
        summary=result.summary,
        price_assessment=result.price_assessment,
        price_plausibility=result.price_plausibility.value,
        recommendation=result.recommendation.value,
        seller_questions=result.seller_questions,
        model_used=provider.model_name,
        prompt_version=settings.prompt_version,
        raw_response=raw_response,
    )
    db.add(analysis)
    analysis.risk_indicators = [
        RiskIndicator(
            category=indicator.category,
            severity=indicator.severity.value,
            explanation=indicator.explanation,
        )
        for indicator in result.risk_indicators
    ]
    db.commit()
    db.refresh(analysis)
    return analysis


def _to_analysis_with_listing(analysis: Analysis) -> AnalysisWithListingOut:
    """Flatten an Analysis (with .listing and .risk_indicators loaded) into
    the joined response shape. AnalysisWithListingOut.listing_* fields live
    on the related Listing row, not on Analysis itself, so from_attributes
    alone can't produce them -- built explicitly instead."""
    return AnalysisWithListingOut(
        id=analysis.id,
        listing_id=analysis.listing_id,
        risk_level=analysis.risk_level,
        risk_score=analysis.risk_score,
        summary=analysis.summary,
        price_assessment=analysis.price_assessment,
        price_plausibility=analysis.price_plausibility,
        recommendation=analysis.recommendation,
        seller_questions=analysis.seller_questions,
        risk_indicators=analysis.risk_indicators,
        model_used=analysis.model_used,
        created_at=analysis.created_at,
        listing_title=analysis.listing.title,
        listing_price=analysis.listing.price,
        listing_currency=analysis.listing.currency,
    )


@router.get("/analyses", response_model=list[AnalysisWithListingOut])
def list_analyses(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """[US-4.1 AC1] The authenticated user's analyses, newest first, joined
    with listing title/price/currency."""
    analyses = (
        db.query(Analysis)
        .join(Listing)
        .filter(Listing.user_id == user.id)
        .options(joinedload(Analysis.listing), selectinload(Analysis.risk_indicators))
        .order_by(Analysis.created_at.desc())
        .all()
    )
    return [_to_analysis_with_listing(analysis) for analysis in analyses]


@router.get("/analyses/{analysis_id}", response_model=AnalysisWithListingOut)
def get_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[US-4.1 AC2] Full analysis with indicators; 404 if not found OR not
    owned by this user."""
    analysis = (
        db.query(Analysis)
        .join(Listing)
        .filter(Analysis.id == analysis_id, Listing.user_id == user.id)
        .options(joinedload(Analysis.listing), selectinload(Analysis.risk_indicators))
        .first()
    )
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return _to_analysis_with_listing(analysis)
