# TrustAI Marketplace — team boilerplate

This is the starting skeleton for the TrustAI Marketplace capstone. The
architecture, module boundaries, API contract, CI pipeline and acceptance
tests are in place; the implementations are yours. Every stub cites its
story ID from `docs/BACKLOG.md`, and every story's Definition of Done is
"its tests in `backend/tests/test_api.py` are un-skipped and green in CI."

## What is already decided (contracts — change only by team decision log)

- `backend/app/schemas/schemas.py` — the Pydantic shared kernel. Request,
  response and AI-output schemas. This is the API contract the frontend and
  every backend module build against.
- `backend/app/api/routes.py` — route paths, status codes and response
  models (bodies are stubs).
- `backend/app/services/ai.py` — the AIProvider interface, failure type and
  provider selection (implementations are stubs).
- CI (`.github/workflows/ci.yml`), Docker, compose, env conventions.

## What each owner builds

| Workstream | Owner | Files | Stories |
|---|---|---|---|
| E1 Auth | Ranga | `core/security.py`, auth routes, User columns | US-1.1–1.3 |
| E2 Listings & DB | Mulima | Listing/Analysis columns, listing+history routes | US-2.1–2.2, US-4.1 |
| E3 AI Analysis | Ahmed | `services/ai.py` providers + prompt, Analysis columns | US-3.1–3.3 |
| E5 Frontend | Adrian, Mulima | `frontend/src/components/*` | UI for the above |
| E6 QA/DevOps | Ranga, Samar | test suite guardianship, deploy pipeline | all |
| E7 Full Stack Support | Ahmed, Mulima | backend + frontend assistance | cross-team |

Search the codebase for `TODO(E` to list your work items.

## Run it

Backend: `cd backend && pip install -r requirements-dev.txt && uvicorn app.main:app --reload`
(the API starts and `/api/health` works out of the box — that's the Sprint 1
deploy skeleton; stubbed endpoints return 500 until implemented).

Tests: `cd backend && python -m pytest tests/ -v` — expect 1 passed, the
rest skipped. Un-skip yours as you implement.

Frontend: `cd frontend && npm install && npm run dev` (proxies /api to :8000).

Full stack: `docker compose up --build`.

## Ground rules

- No secrets in the repo — `.env` is gitignored, use `.env.example` as the map.
- Branch per story, PR with at least one review, CI green before merge.
- Don't weaken a test to make it pass; change the implementation or bring
  the test to the team.
- Design decisions and their reasons go in `docs/DESIGN_NOTES.md` as you make
  them — the rubric grades reasons, not just choices.
