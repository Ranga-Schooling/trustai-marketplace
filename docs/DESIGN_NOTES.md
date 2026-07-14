# TrustAI Marketplace — Design & Testing Notes (working draft)

A starting point for the capstone design and testing document. Expand each
section as the project evolves; the rubric requires reasons for choices, not
just the choices themselves.

## Architecture decisions

**FastAPI over Flask.** The product's central risk ("AI inconsistency") is
mitigated by schema validation, and FastAPI makes Pydantic models the native
request/response mechanism. The same `AIAnalysisResult` model validates LLM
output, drives the OpenAPI docs at `/docs`, and serves as the team's API
contract.

**Categorical risk, not numeric.** LLM-emitted numeric scores are not
calibrated; two runs on the same listing can differ by 20 points with no
change in substance. Risk is therefore low/medium/high, derived from the
severities of named indicators, with a deterministic mapping to
Buy/Caution/Avoid. This is testable (see `test_high_risk_listing_gets_avoid`)
in a way a free-floating number is not.

**Provider interface (strategy pattern).** `AIProvider` is a Protocol with
two implementations: `GroqProvider` (JSON mode, 30s timeout, one retry on
invalid output) and `MockProvider` (deterministic keyword/price heuristics).
Tests and CI run entirely on the mock — no network, no secrets. The mock also
serves as executable documentation of the fraud signals the product targets.

**Persist-before-analyze.** The listing row is committed before the AI call
so a provider outage never loses user input. The API returns 502 with an
explicit "your listing was saved" message. This is the error branch that was
missing from the original sequence diagram.

**Audit columns.** Each analysis stores `model_used`, `prompt_version`, and
`raw_response`. Prompt changes are a known source of silent regressions;
these columns make regressions diffable.

**Auth.** JWT bearer tokens (24h), bcrypt password hashing, everything
analysis-related behind `get_current_user`. Deliberately minimal: no refresh
tokens, no password reset, no email verification — out of scope for a
2-month capstone and documented as such.

**Patterns used (for the rubric):** layered architecture (api / services /
models / schemas), strategy (AI providers), dependency injection (FastAPI
`Depends` for DB sessions and auth), repository-lite via SQLAlchemy sessions.

## Deployment recommendation (rubric-required section)

Cloud, free tier: Render web service for the API (Docker), Render static
site for the frontend, managed Postgres on Neon/Supabase. Relative cost:
$0/month at capstone scale versus meaningful fixed cost and ops burden for
on-premises; the trade-off is cold starts and modest resource limits, both
acceptable here. If this were a production product, the first paid steps
would be a dedicated Postgres instance and an always-on API instance.

## Testing strategy

- **Framework:** pytest + FastAPI TestClient; fresh SQLite database per test.
- **What is tested and why:**
  - Auth lifecycle and failure modes (register, duplicate, bad credentials) — the security boundary.
  - Authorization isolation (users cannot read each other's analyses, even by id) — the most common real-world API vulnerability class (IDOR).
  - Analysis happy paths for a benign and a scam-signal listing — verifies categorical derivation end to end.
  - Input validation (negative price, bad currency) — confirms bad input is rejected before any AI spend.
  - AI failure branch — confirms the 502 + saved-listing behavior.
- **CI:** GitHub Actions runs the suite (mock provider) and a frontend
  production build on every push/PR. No secrets in CI by design.
- **Not yet covered (candidates for Sprint 3):** frontend component tests,
  a contract test replaying recorded Groq responses through the validator,
  and load-testing the analysis endpoint.

## Known limitations (state these honestly in the final doc)

- Heuristic/LLM analysis can miss scams and flag legitimate listings.
- No rate limiting yet on `/api/analyses`; a deployed instance exposes the
  LLM key's quota to abuse. Planned: simple per-user daily cap.
- CORS is wide open for development; restrict to the deployed frontend origin.
- SQLite JSON column behavior differs subtly from Postgres; integration tests
  against Postgres (via compose) are worth adding before final submission.
