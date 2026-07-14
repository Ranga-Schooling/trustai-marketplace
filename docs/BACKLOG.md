# TrustAI Marketplace — User Story Backlog

This backlog records the user stories and tasks that produced the MVP in this
repository. Stories are grouped by epic (matching the kickoff pack), carry
Must/Should/Could priority, and each includes acceptance criteria. The
"Implemented" column maps each story to concrete code so the task board and
the repository stay traceable to each other.

Scope decisions applied throughout: risk is **categorical** (low/medium/high)
derived from named indicators — never a raw LLM-invented number; the AI
provider sits behind an interface so tests and CI run without network access
or API keys; a listing is persisted even when analysis fails, matching the
error branch added to the sequence diagram during design review.

---

## EPIC 1 — User Accounts (Must)

**US-1.1 — Register**
As a buyer, I want to create an account with my email and a password, so my
analysis history is private to me.
- AC1: Registration requires a valid email, a name, and a password of 8+ characters.
- AC2: Registering an already-used email returns a clear conflict error.
- AC3: Passwords are stored only as bcrypt hashes.
- Implemented: `POST /api/auth/register`, `core/security.py`, tests `test_register_login_me`, `test_duplicate_registration_rejected`.

**US-1.2 — Sign in**
As a returning buyer, I want to sign in and stay signed in during my session.
- AC1: Valid credentials return a bearer token (JWT, 24h expiry).
- AC2: Invalid credentials return 401 without revealing which field was wrong.
- Implemented: `POST /api/auth/login`, test `test_bad_credentials_rejected`.

**US-1.3 — Protected access**
As the product team, we want all analysis endpoints to require authentication,
so one user's history is never visible to another.
- AC1: Unauthenticated requests to /analyses return 401.
- AC2: A user cannot fetch another user's analysis by guessing its id (404).
- Implemented: `get_current_user` dependency, tests `test_analyses_requires_auth`, `test_history_is_per_user`.

Tasks completed: bcrypt hashing utility · JWT create/verify · FastAPI auth
dependency · register/login/me routes · auth UI (login + register modes) ·
session token storage and 401 auto-signout in the frontend API client.

---

## EPIC 2 — Listing Submission (Must)

**US-2.1 — Submit a listing manually**
As a buyer, I want to paste a listing's title, price, currency, marketplace,
and description (URL optional), so I can get it analyzed without any scraping.
- AC1: All fields except URL are required; price must be positive; currency is a 3-letter code.
- AC2: Invalid input returns a 422 with field-level detail before any AI call is made.
- AC3: Descriptions are capped (4,000 chars) to protect the AI endpoint from abuse.
- Implemented: `ListingIn` schema, `POST /api/analyses`, test `test_invalid_listing_rejected`.

**US-2.2 — Listing survives analysis failure**
As a buyer, if the AI service is down, I want my submission kept so I can
retry without retyping everything.
- AC1: The listing row is committed before the AI call.
- AC2: On AI failure the API returns 502 with a message stating the listing was saved.
- Implemented: commit-before-analyze in `routes.create_analysis`, test `test_ai_failure_returns_502_and_saves_listing`.

Tasks completed: Listing ORM model · input schema with currency normalization ·
description length guard · submission form UI with inline errors.

---

## EPIC 3 — AI Analysis (Must)

**US-3.1 — Structured risk analysis**
As a buyer, I want a plain-English summary, a categorical risk level with
named reasons, a price assessment, seller questions, and a
Buy/Caution/Avoid recommendation.
- AC1: Every analysis conforms to the `AIAnalysisResult` schema; non-conforming LLM output is rejected, retried once, then surfaced as a failure.
- AC2: Risk level is low/medium/high, derived from indicator severities (no uncalibrated numeric scores).
- AC3: Recommendation maps deterministically: low→buy, medium→caution, high→avoid.
- AC4: At least one seller question is always returned.
- Implemented: `services/ai.py` (system prompt, GroqProvider with JSON mode + retry, MockProvider), tests `test_low_risk_listing_gets_buy`, `test_high_risk_listing_gets_avoid`.

**US-3.2 — Auditable model output**
As the engineering team, we want every analysis to record which model and
prompt version produced it, plus the raw response, so regressions can be
diffed instead of guessed at.
- AC1: `model_used`, `prompt_version`, and `raw_response` are persisted with each analysis.
- Implemented: `Analysis` model columns, populated in `routes.create_analysis`.

**US-3.3 — Provider-independent testing**
As the team, we want tests and CI to run with zero network access and no API
keys.
- AC1: `AI_PROVIDER=mock` selects a deterministic heuristic provider satisfying the same contract.
- Implemented: `MockProvider`, provider selection in `get_provider()`, CI env config.

Tasks completed: provider Protocol · system prompt with schema + honesty rules ·
Groq JSON-mode call with timeout and single retry · Pydantic validation gate ·
deterministic heuristic signal table · categorical risk derivation logic.

---

## EPIC 4 — Saved History (Must)

**US-4.1 — View past analyses**
As a buyer, I want to see my past analyses newest-first with title, price,
date, and risk badge, and open any of them in full.
- AC1: `GET /api/analyses` returns only the authenticated user's analyses, newest first.
- AC2: `GET /api/analyses/{id}` returns the full result including indicators.
- Implemented: list/detail routes with `selectinload`, History and AnalysisResult components, test `test_history_is_per_user`.

Tasks completed: listing-joined queries · history list UI with risk badges ·
detail reuse of the result view.

(Deferred per 2-month scoping: history search/filter, PDF export.)

---

## EPIC 5 — DevOps & CI/CD (Must)

**US-5.1 — One-command local stack**
As a developer, I want `docker compose up` to give me the API plus Postgres.
- AC1: Compose file provides api + postgres:16 with a persistent volume.
- Implemented: `docker-compose.yml`, `backend/Dockerfile`.

**US-5.2 — CI on every PR**
As the team, we want every pull request to run backend tests and a frontend
production build before merge.
- AC1: GitHub Actions runs pytest (mock provider, no secrets) and `vite build` on push/PR.
- Implemented: `.github/workflows/ci.yml`.

**US-5.3 — Twelve-factor configuration**
As the team, we want all secrets and environment differences injected via env
vars so one image runs locally, in CI, and on Render.
- AC1: DATABASE_URL, JWT_SECRET, AI_PROVIDER, GROQ_API_KEY all env-driven with safe local defaults.
- Implemented: `core/config.py`, `.env.example`.

Tasks completed: Dockerfile · compose stack · CI workflow with per-directory
defaults · settings module · env example file.

---

## EPIC 6 — Testing & Documentation (Must)

**US-6.1 — Automated test suite**
- AC1: Tests cover auth (register, login, duplicate, bad credentials), authorization isolation, analysis happy path, categorical risk derivation, input validation, and the AI failure branch.
- Result: 10 tests, all passing (`pytest backend/tests`).

**US-6.2 — Honest product framing**
As the product owner, I want the app to state its limits, so users are not
misled into treating heuristic output as a guarantee.
- AC1: The UI shows a persistent disclaimer; the API description repeats it; the system prompt instructs the model to acknowledge uncertainty.
- Implemented: footer disclaimer in `App.jsx`, FastAPI description, `SYSTEM_PROMPT` rules.

**US-6.3 — Repo documentation**
- AC1: README covers setup, environment variables, running tests, Docker, and deployment notes.
- Implemented: `README.md`, this backlog, `docs/DESIGN_NOTES.md`.

---

## Priority summary

| Priority | Stories |
|---|---|
| Must (shipped) | US-1.1–1.3, 2.1–2.2, 3.1–3.3, 4.1, 5.1–5.3, 6.1–6.3 |
| Should (next sprint) | Admin/demo page, saved-history search, deploy step in CI |
| Could (future) | PDF export, URL auto-fetch, browser extension, reverse image search |
