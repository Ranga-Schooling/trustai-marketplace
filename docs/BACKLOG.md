# TrustAI Marketplace — User Story Backlog

This backlog records the user stories and tasks that produced the MVP in this
repository. Stories are grouped by epic (matching the kickoff pack), carry
Must/Should/Could priority, and each includes acceptance criteria. The
"Implemented" column maps each story to concrete code so the task board and
the repository stay traceable to each other.

Scope decisions applied throughout: risk is **categorical** (low/medium/high)
derived from named indicators — never a raw LLM-invented number; the AI
provider sits behind an interface so CI and provider-boundary tests require no
provider credentials and make no live provider requests; a listing is
persisted even when analysis fails, matching the error branch added to the
sequence diagram during design review.

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

**US-1.4 — View and edit profile**
As a user, I want to view my profile and edit my name/email, so my account
details stay current.
- AC1: `GET /auth/me` returns the current name/email (already implemented under US-1.3).
- AC2: `PATCH /auth/me` updates name and/or email; at least one field required (400 otherwise).
- AC3: Changing to an already-registered email returns 409, same as registration.
- Implemented: `UserUpdate` schema, `PATCH /api/auth/me`, the account
  section in `App.jsx` (`Profile.jsx` was retired in favor of this — see
  the "Fixed" note in `docs/DESIGN_NOTES.md`), `api.updateMe`, tests
  `test_update_profile_*`.

**US-1.5 — Delete account**
As a user, I want to permanently delete my account, so my data isn't kept
once I no longer want to use the product.
- AC1: `DELETE /auth/me` deletes the authenticated user and all listings/
  analyses/risk indicators they own (hard delete, no undo).
- AC2: The bearer token used to authenticate no longer works after
  deletion (any further request with it returns 401).
- AC3: Deleting one user's account never affects another user's listings
  or analyses.
- Implemented: `DELETE /api/auth/me`, cascade relationships in
  `models/db.py`, `api.deleteMe`, tests `test_delete_account_*` (D-12).

Tasks completed: bcrypt hashing utility · JWT create/verify · FastAPI auth
dependency · register/login/me routes · auth UI (login + register modes) ·
session token storage and 401 auto-signout in the frontend API client ·
profile view/edit route and UI (US-1.4) · delete-account backend route and
cascade delete (US-1.5).

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

**US-2.3 — Submit a listing URL and get suggested details**
As a buyer, I want to paste just a listing URL and have the title,
price, currency, and description suggested for me, so I don't have to
retype them by hand.
- AC1: `POST /listings/preview` fetches the URL server-side and returns suggested title/description/price/currency; the user still reviews and edits before submitting.
- AC2: Non-HTTP(S) URLs, and URLs resolving to a private/loopback/link-local address, are rejected (SSRF guardrail) with a 422.
- AC3: This does not change the frozen `ListingIn`/`POST /analyses` contract (see docs/DESIGN_NOTES.md D-06, extended by D-14).
- AC4: Price/currency/seller-signal extraction is best-effort — a missed match leaves the field for the user to fill in by hand, never a wrong guess passed through as fact.
- Implemented: `ListingUrlIn`/`ListingPreviewOut` schemas, `services/listing_fetch.py` (`_extract_price`/`_extract_seller_details`, D-14), `POST /api/listings/preview`, `ListingForm.jsx` price/currency prefill, tests `test_url_preview_returns_suggested_fields`, `test_extract_price_formats`, `test_fetch_listing_preview_populates_price_currency_and_seller_details`.

Tasks completed: Listing ORM model · input schema with currency normalization ·
description length guard · submission form UI with inline errors · URL fetch
preview endpoint with SSRF guardrails (US-2.3).

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
As the team, we want provider tests and CI to run without provider credentials
or live provider requests.
- AC1: `AI_PROVIDER=mock` selects a deterministic heuristic provider satisfying the same contract.
- Implemented: `MockProvider`, provider selection in `get_provider()`, CI env config.

**US-3.5 — Price plausibility category (Trello #28)**
As a buyer, I want to know whether the asking price is plausible, suspicious,
or too good to be true, without the tool claiming to know the real market
value.
- AC1: `price_plausibility` is one of `plausible` / `suspicious` /
  `too_good_to_be_true` (categorical, no numeric score — same rationale as
  risk level, D-05).
- AC2: `price_assessment` (the existing free-text explanation) never states a
  specific figure, range, or market-data source as fact.
- AC3: Both providers populate the field; `MockProvider` derives it
  deterministically from its existing price threshold.
- Implemented: `PricePlausibility` schema, `Analysis.price_plausibility`
  column + Alembic migration `ecb69044639d`, `MockProvider`/`SYSTEM_PROMPT`
  updates, `AnalysisResult.jsx` badge, tests `test_low_risk_listing_gets_buy`,
  `test_high_risk_listing_gets_avoid`, `test_moderately_low_price_gets_suspicious_plausibility`.
  Decision log: `docs/DESIGN_NOTES.md` D-08.

**US-3.4 — Deterministic 0-100 risk score (Trello #27)**
As a buyer, I want a 0-100 risk score combining rule-based and AI signals,
without the tool inventing an uncalibrated number.
- AC1: `risk_score` is 0-100 and always falls within its `risk_level` tier's
  range (low 0-33, medium 34-66, high 67-100) — never contradicts the
  categorical badge it's derived from.
- AC2: No `AIProvider` returns or is asked for a score; `AIAnalysisResult`
  is unchanged (D-05 still applies to it in full).
- AC3: Same (risk_level, indicators) always produces the same score
  (deterministic, unit-tested, not an LLM call).
- Implemented: `services/scoring.py`, `Analysis.risk_score` column +
  Alembic migration `3cc9cb43e9e6`, `AnalysisResult.jsx`/`History.jsx`
  score display, tests `test_scoring.py`,
  `test_risk_score_never_contradicts_risk_level`. Decision log:
  `docs/DESIGN_NOTES.md` D-09 (amends D-05's scope).

**US-3.6 — Multi-LLM provider abstraction (Trello #20)**
As the team, we want the backend to switch between Groq/GPT/Gemini via
configuration, so we're not locked to one vendor.
- AC1: `AI_PROVIDER=mock|groq|gpt|gemini` selects the active provider;
  each real provider fails fast (`AnalysisFailure`) if its own API key
  isn't configured.
- AC2: All three real providers satisfy the same `AIProvider` Protocol and
  external `AIAnalysisResult` contract. Groq/Gemini retain their historical
  bounded retry flow; D-21 gives the production OpenAI path transient-only
  retries and strict deterministic failure handling.
- AC3: Groq uses the OpenAI-compatible Chat Completions base; GPT uses OpenAI
  Responses under D-21; Gemini remains distinct because its API is not
  OpenAI-shaped.
- Implemented: `OpenAICompatibleProvider`/`GroqProvider`/`GPTProvider`/
  `GeminiProvider` in `services/ai.py`, `config.py`
  gemini/openai settings, tests `test_gpt_provider_*`,
  `test_gemini_provider_*`, `test_get_provider_returns_*`. Decision log:
  `docs/DESIGN_NOTES.md` D-10.
- Out of scope (deliberately, see D-10): switching still requires an env
  var change + restart, not a live/runtime toggle — that's tracked
  separately as a GitHub issue (admin-gated runtime config + analytics).

Tasks completed: provider Protocol · system prompt with schema + honesty rules ·
Groq JSON-mode call with timeout and single retry · Pydantic validation gate ·
deterministic heuristic signal table · categorical risk derivation logic ·
categorical price plausibility derivation (US-3.5) ·
deterministic rule-based risk scoring (US-3.4) · GPT/Gemini providers behind
the same interface (US-3.6).

---

## EPIC 4 — Saved History (Must)

**US-4.1 — View past analyses**
As a buyer, I want to see my past analyses newest-first with title, price,
date, and risk badge, and open any of them in full.
- AC1: `GET /api/analyses` returns only the authenticated user's analyses, newest first.
- AC2: `GET /api/analyses/{id}` returns the full result including indicators.
- Implemented: `list_analyses`/`get_analysis` in `routes.py` (`joinedload`/
  `selectinload` to avoid N+1), `_to_analysis_with_listing` helper flattening
  `Analysis`+`Listing` into `AnalysisWithListingOut`, History and
  AnalysisResult components, tests `test_history_is_per_user`,
  `test_list_analyses_newest_first`, `test_get_analysis_returns_full_detail`,
  `test_get_analysis_unknown_id_returns_404`.

Tasks completed: listing-joined queries · history list UI with risk badges ·
detail reuse of the result view.

(This story was previously marked "Implemented" here while the routes
still raised `NotImplementedError` -- flagged in
`architecture-review-2026-08-01.md` §2.3 as overclaiming delivery status.
Now genuinely true: all backend tests un-skipped, 0 remaining skips in
`test_api.py`.)

(Deferred per 2-month scoping: history search/filter, PDF export.)

**US-4.2 — Recover a listing after a failed analysis (issue #80)**
As a buyer, if the AI check fails after my listing is saved, I want to
find it and retry without retyping everything, so "the listing was
saved" is actually true from where I'm standing.
- AC1: A listing whose analysis failed is visible to its owner (a
  "Failed listings" section on History) even though it has no completed
  analysis.
- AC2: The buyer can retry analysis on that exact listing without
  re-entering any field.
- AC3: A successful retry produces a normal `Analysis` and the listing
  drops out of the failed list.
- AC4: The 502 returned at the original failure names the listing id and
  says where to find/retry it, instead of a dead-end "was saved".
- Implemented: `FailedListingOut` schema, `GET /api/listings/failed`,
  `POST /api/listings/{id}/retry`, `_handle_analysis_failure`/
  `_persist_analysis` helpers shared with `create_analysis`, History's
  "Failed listings" section with a retry control, tests
  `test_failed_listing_appears_in_failed_listings`,
  `test_successful_listing_not_in_failed_listings`,
  `test_failed_listings_scoped_per_user`,
  `test_retry_analysis_succeeds_and_clears_failed_list`,
  `test_retry_still_failing_provider_returns_502_with_listing_id`,
  `test_retry_unknown_listing_returns_404`,
  `test_retry_listing_not_owned_returns_404`. Decision log:
  `docs/DESIGN_NOTES.md` D-20.

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
As the team, we want secrets and environment differences injected through
environment variables so deployment images contain no environment-specific
credentials.
- AC1: Database, session, provider, model, and Visual Inspection configuration
  are environment-driven; local/CI defaults do not make live provider calls.
- Implemented: `core/config.py`, `.env.example`, and
  `deploy/docker-compose.yml`.

Tasks completed: Dockerfile · compose stack · CI workflow with per-directory
defaults · settings module · env example file.

---

## EPIC 6 — Testing & Documentation (Must)

**US-6.1 — Automated test suite**
- AC1: Tests cover auth (register, login, duplicate, bad credentials), authorization isolation, analysis happy path, categorical risk derivation, input validation, and the AI failure branch.
- Initial acceptance slice: 10 tests. The immutable `v1.20.0` release record is
  70 contract-selection tests passed, 449 backend tests passed at 96.49%
  coverage, 76 frontend tests passed across 9 files, and a successful frontend
  production build with 39 modules transformed; see
  `docs/capstone/FINAL_PRODUCTION_VALIDATION.md`.

**US-6.2 — Honest product framing**
As the product owner, I want the app to state its limits, so users are not
misled into treating heuristic output as a guarantee.
- AC1: The UI shows a persistent disclaimer; the API description repeats it; the system prompt instructs the model to acknowledge uncertainty.
- Implemented: footer disclaimer in `App.jsx`, FastAPI description, `SYSTEM_PROMPT` rules.

**US-6.3 — Repo documentation**
- AC1: README covers setup, environment variables, running tests, Docker, and deployment notes.
- Implemented: `README.md`, this backlog, `docs/DESIGN_NOTES.md`.

**US-6.4 — Unit test foundations with a CI coverage gate**
As the team, we want a fast unit-test layer (not just full HTTP acceptance
tests) for the auth and listing services, with CI enforcing a coverage
floor so untested code can't silently creep in.
- AC1: `test_security.py` unit-tests `core/security.py` directly (hashing, JWT claims/expiry, `get_current_user`'s 401 cases) — no HTTP, no TestClient.
- AC2: `test_listing_schema.py` unit-tests `ListingIn` validation directly (currency shape/normalization, positive price, description length, optional URL).
- AC3: CI fails if backend coverage drops below 85% (`--cov-fail-under=85`); `app` gained `__init__.py` files so untested modules (e.g. `services/ai.py`) are honestly counted instead of silently excluded.
- Implemented: `tests/test_security.py`, `tests/test_listing_schema.py`, `backend/.coveragerc`, `.github/workflows/ci.yml`.

**US-6.5 — Frontend test coverage**
As the team, we want the frontend build step to catch a client/server API
naming mismatch, not just a JSX/syntax error, so a fully-broken feature
can't ship past CI the way #68 did (`App.jsx` calling `api.updateMe`/
`api.deleteMe`, neither of which existed on the API client).
- AC1: Every component that calls `api.*` has at least one test asserting
  it invokes the correct method, by spying on the real `api` module
  (not a hand-authored mock) so a renamed/removed method fails the test
  the same way it fails at runtime.
- AC2: CI runs the frontend test suite as its own step, separate from
  (and before) `npm run build`.
- Implemented: Vitest + React Testing Library, `App.test.jsx`,
  `AuthForm.test.jsx`, `ListingForm.test.jsx`, `History.test.jsx`,
  `.github/workflows/ci.yml`'s `frontend` job.

---

## Priority summary

This is a repository-side status summary for release `v1.20.0`. It does not
claim that Trello ownership or card movement was maintained contemporaneously;
the final board reconciliation and its evidence boundary are documented in
`docs/capstone/sprints/README.md`.

| Priority | Scope | Final repository state |
|---|---|---|
| Must | US-1.1–1.5, US-2.1–2.3, US-3.1–3.6, US-4.1–4.2, US-5.1–5.3, US-6.1–6.5 | Implemented and released in `v1.20.0` |
| Should | Admin RBAC and aggregate analytics endpoint; automated deployment; failed-analysis recovery; dark mode | Implemented and released; there is no admin dashboard or runtime provider-switching UI |
| Should — operationally open | Scheduled PostgreSQL-to-S3 backup | Workflow implemented; production backup and isolated restore verification remain OPEN under issue [#88](https://github.com/Ranga-Schooling/trustai-marketplace/issues/88) |
| Should — deferred | Saved-history search; runtime provider switching without restart; password change/re-authentication | Deferred under issues [#92](https://github.com/Ranga-Schooling/trustai-marketplace/issues/92) and [#66](https://github.com/Ranga-Schooling/trustai-marketplace/issues/66), or retained as future scope |
| Could | PDF export, browser extension, reverse image search | Deferred beyond the Capstone release |

### Selected implementation traceability

These links establish merged implementation, not historical sprint placement or
contemporaneous task-board movement.

| Delivered work | Evidence | Final-state boundary |
|---|---|---|
| ECR/EC2 deployment, Systems Manager activation, and Caddy HTTPS | PRs [#37](https://github.com/Ranga-Schooling/trustai-marketplace/pull/37), [#50](https://github.com/Ranga-Schooling/trustai-marketplace/pull/50), and [#63](https://github.com/Ranga-Schooling/trustai-marketplace/pull/63); [ADR-003](decisions/ADR-003-aws-ec2-deployment.md) | Implemented incrementally; final architecture was not complete on August 8 |
| Categorical price plausibility | Trello card #28, PR [#41](https://github.com/Ranga-Schooling/trustai-marketplace/pull/41), D-08 | Qualitative category; not verified live/current market pricing |
| Deterministic 0–100 Trust score | Trello card #27, PR [#43](https://github.com/Ranga-Schooling/trustai-marketplace/pull/43), D-09 | Computed by application code from validated categorical output; not model-generated |
| Config-selectable provider adapters | Trello card #20, PR [#46](https://github.com/Ranga-Schooling/trustai-marketplace/pull/46), D-10 | Runtime switching without configuration change/restart remains deferred |
| Admin RBAC and aggregate analytics endpoint | PR [#91](https://github.com/Ranga-Schooling/trustai-marketplace/pull/91), D-15 | Endpoint delivered; no admin dashboard or runtime provider-selection control |
| PostgreSQL-to-S3 backup automation | PRs [#76](https://github.com/Ranga-Schooling/trustai-marketplace/pull/76) and [#89](https://github.com/Ranga-Schooling/trustai-marketplace/pull/89) | Workflow exists; successful production backup/restore readiness remains OPEN in issue [#88](https://github.com/Ranga-Schooling/trustai-marketplace/issues/88) |
| Failed-listing recovery | Issue [#80](https://github.com/Ranga-Schooling/trustai-marketplace/issues/80), PR [#100](https://github.com/Ranga-Schooling/trustai-marketplace/pull/100) | Implemented and issue closed |
| Transient Visual Inspection | PR [#99](https://github.com/Ranga-Schooling/trustai-marketplace/pull/99), D-20 | Advisory and application-non-persistent; cannot change text-analysis outcomes |
| Dark mode | PR [#105](https://github.com/Ranga-Schooling/trustai-marketplace/pull/105) | Implemented with light/dark/system behavior |
| Per-listing retry-state isolation | PR [#106](https://github.com/Ranga-Schooling/trustai-marketplace/pull/106) | Frontend history retries are isolated per listing |
| Terra text path and strict response validation | PR [#108](https://github.com/Ranga-Schooling/trustai-marketplace/pull/108) merged into the `feat/ai-response-validation` branch; PR [#107](https://github.com/Ranga-Schooling/trustai-marketplace/pull/107) then merged the combined head to `main`; D-21 | Formal evaluation remained a tie/no clear winner; Terra was a later engineering selection |
