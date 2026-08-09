"""API routes — the HTTP surface of the system.

The route signatures, paths, status codes and response models below are the
agreed API contract (they generate the OpenAPI docs at /docs that the
frontend builds against). Keep the signatures; implement the bodies.

Ownership:
- /auth/*            E1 (Ranga)     US-1.1, US-1.2, US-1.3, US-1.4
- POST /analyses     E2 + E3 pair   US-2.1, US-2.2, US-3.1
- GET /analyses*     E2 (Abdallah)  US-4.1

Agreed behaviors (docs/DESIGN_NOTES.md):
- The listing row is committed BEFORE the AI call, so a provider outage
  never loses user input; on AnalysisFailure return 502 with a message that
  the listing was saved. [US-2.2]
- History queries are scoped to the authenticated user; fetching another
  user's analysis by id returns 404, not 403. [US-1.3 AC2]
- PATCH /auth/me is additive to the frozen register/login contract
  (CLAUDE.md SCHEMA-0): profile editing (name/email), no password change,
  consistent with the existing minimal-auth stance. [US-1.4]
- AnalysisOut.risk_score (D-09) is computed server-side by
  services/scoring.py from the already-validated risk_level/
  risk_indicators; no AIProvider returns it, AIAnalysisResult is
  unchanged. [Trello #27]
- ListingIn.images (D-12, stretch) is a list of base64 image data URIs;
  format is validated in the schema, count/size caps in this route (413),
  same split as description. Passed through to AIProvider.analyze
  unchanged -- MockProvider ignores it (stays deterministic), vision-
  capable real providers use it. AIAnalysisResult is unchanged either way.
  [US-2.4]
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

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
    TokenResponse,
    UserLogin,
    UserOut,
    UserRegister,
    UserUpdate,
)

router = APIRouter()
settings = get_settings()


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


@router.post("/analyses", response_model=AnalysisOut, status_code=201)
def create_analysis(
    body: ListingIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[US-2.1, US-2.2, US-3.1] Persist the listing, run the AI provider,
    persist the validated analysis with audit columns, return it.
    Enforce settings.max_description_chars with 413. 502 on AnalysisFailure
    (listing already saved).
    [US-2.4, D-12] Same 413 treatment for listing.images: count capped by
    settings.max_listing_images, each image's decoded size capped by
    settings.max_image_bytes. Format (valid base64 image data URI) is
    already enforced in ListingIn -- this is the size guard only, same
    split as description."""
    if len(body.description) > settings.max_description_chars:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Description exceeds {settings.max_description_chars} characters",
        )
    if len(body.images) > settings.max_listing_images:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"A maximum of {settings.max_listing_images} images is allowed",
        )
    for image in body.images:
        b64_payload = image.split(",", 1)[1]
        decoded_bytes = len(b64_payload) * 3 // 4
        if decoded_bytes > settings.max_image_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Each image must be under {settings.max_image_bytes // 1_000_000}MB",
            )
    listing = Listing(
        user_id=user.id,
        title=body.title,
        price=body.price,
        currency=body.currency,
        source=body.source,
        description=body.description,
        url=str(body.url) if body.url is not None else None,
        images=body.images or None,
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    try:
        provider = get_provider()
        result, raw_response = provider.analyze(body)
    except AnalysisFailure as exc:
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


@router.get("/analyses", response_model=list[AnalysisWithListingOut])
def list_analyses(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """[US-4.1 AC1] The authenticated user's analyses, newest first, joined
    with listing title/price/currency."""
    raise NotImplementedError("E2/US-4.1")


@router.get("/analyses/{analysis_id}", response_model=AnalysisWithListingOut)
def get_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[US-4.1 AC2] Full analysis with indicators; 404 if not found OR not
    owned by this user."""
    raise NotImplementedError("E2/US-4.1")
