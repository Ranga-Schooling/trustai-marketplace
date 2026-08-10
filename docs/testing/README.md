# Testing and Quality Documentation

This directory tracks the project's quality strategy and testing evidence.
Design rationale (why coverage is gated where it is, why unit and
acceptance tests are split, etc.) lives in `docs/DESIGN_NOTES.md`
("Testing strategy" section) — this page is the practical how-to.

## Running the backend test suite

```bash
cd backend
python -m venv .venv                 # skip if already created
# Windows: .venv\Scripts\Activate.ps1   macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt

python -m pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=85
```

No `DATABASE_URL`/`AI_PROVIDER`/`JWT_SECRET` env vars are needed — `tests/conftest.py`
sets them unconditionally before any test module is imported, overriding
whatever is already in your shell (see the "Coverage gate" note in
`DESIGN_NOTES.md` for why that has to be unconditional). This is exactly
what CI runs (`.github/workflows/ci.yml`).

**Test layers:**
- `test_api.py` — acceptance-level: full HTTP round trips through FastAPI's
  `TestClient`, one story per test, matching the acceptance criteria in
  `docs/BACKLOG.md`. New stories get their test added here first, as
  `@pytest.mark.skip(reason="<story>: <what it verifies> (<owner>)")` —
  the skip reason names the story, and a story isn't done until its test
  is un-skipped and green.
- `test_security.py`, `test_listing_schema.py` — unit-level: call
  `core/security.py` and the `ListingIn` schema directly, no HTTP. Add a
  unit test here when you're testing one function's logic in isolation,
  not a whole request/response cycle.

## Running the frontend build

```bash
cd frontend
npm install
npm run build
```
This is the same check CI runs (`vite build`) — it catches JSX/syntax
errors and unresolved imports before they reach a PR.

## Running the full stack locally

```bash
docker compose up --build
```
Brings up `db` (Postgres 16) + `api` (FastAPI, `:8000`) + `frontend`
(Vite dev server, `:5173`) together — the closest local approximation of
the deployed environment. Visit **http://localhost:5173**.

**Known gotcha:** if the `api` container fails on startup with a Postgres
`DatatypeMismatch` error on `listings.user_id`, that's stale schema data
left in the `pgdata` volume from an earlier model version — wipe it and
rebuild:
```bash
docker compose down -v
docker compose up --build
```

## Manual smoke test checklist

Once the stack is up (Docker or `npm run dev` + local `uvicorn`), a
walkthrough that exercises the stories currently implemented on `main`:

1. **Register / sign in** — the two-column auth screen; toggle between
   Sign in and Register.
2. **Submit a listing** — fill in title/price/currency/source/description
   (or paste a URL and click **Fetch details** to prefill from it) and
   submit. Expect a real categorical result (`low`/`buy` for a mundane
   listing, `high`/`avoid` for one with urgency language, off-platform
   payment requests, etc. — see `MockProvider` in `app/services/ai.py`
   for the exact signal list).
3. **Account** — edit name and/or email from the nav, confirm the change
   persists after reloading.
4. **History** — not yet functional; `GET /analyses` and
   `GET /analyses/{id}` (US-4.1) are the one remaining backend stub.

## Backend-only smoke test (no Docker)

```bash
cd backend
# Windows PowerShell:
$env:AI_PROVIDER="mock"; $env:JWT_SECRET="dev-secret"; $env:DATABASE_URL="sqlite:///./devcheck.db"
# macOS/Linux:
AI_PROVIDER=mock JWT_SECRET=dev-secret DATABASE_URL=sqlite:///./devcheck.db \
uvicorn app.main:app --reload
```
Then either open **http://localhost:8000/docs** (Swagger UI — register,
log in, click "Authorize" with the returned token, try endpoints
interactively) or drive it with `curl`. Delete `devcheck.db` afterwards;
it's a throwaway SQLite file, not something to commit.

## Planned coverage (not yet built)

- Frontend component tests
- A contract test replaying recorded Groq responses through the
  `AIAnalysisResult` validator (current Groq tests use synthetic fakes,
  not recorded real responses)
- Load-testing `/api/analyses`
- End-to-end tests (Playwright or similar) driving the deployed app
