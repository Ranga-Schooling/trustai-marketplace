"""API routes — the HTTP surface of the system.

The route signatures, paths, status codes and response models below are the
agreed API contract (they generate the OpenAPI docs at /docs that the
frontend builds against). Keep the signatures; implement the bodies.

Ownership:
- /auth/*            E1 (Ranga)     US-1.1, US-1.2, US-1.3
- POST /analyses     E2 + E3 pair   US-2.1, US-2.2, US-3.1
- GET /analyses*     E2 (Abdallah)  US-4.1

Agreed behaviors (docs/DESIGN_NOTES.md):
- The listing row is committed BEFORE the AI call, so a provider outage
  never loses user input; on AnalysisFailure return 502 with a message that
  the listing was saved. [US-2.2]
- History queries are scoped to the authenticated user; fetching another
  user's analysis by id returns 404, not 403. [US-1.3 AC2]
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import get_current_user
from app.models.db import User, get_db
from app.schemas.schemas import (
    AnalysisOut,
    AnalysisWithListingOut,
    ListingIn,
    TokenResponse,
    UserLogin,
    UserOut,
    UserRegister,
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
    raise NotImplementedError("E1/US-1.1")


@router.post("/auth/login", response_model=TokenResponse)
def login(body: UserLogin, db: Session = Depends(get_db)):
    """[US-1.2] Verify credentials, return a bearer token; 401 on failure
    without revealing which field was wrong."""
    raise NotImplementedError("E1/US-1.2")


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    """[US-1.3] Return the authenticated user's profile."""
    raise NotImplementedError("E1/US-1.3")


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
    raise NotImplementedError("E2+E3 integration story")


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
