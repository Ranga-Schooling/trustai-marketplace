# TrustAI Marketplace — project rules for Claude Code

MSSE capstone, 5-person team, deadline 31 Aug 2026. Graded partly on
process evidence (Git history, decision records), not just working code.

## Contracts are frozen — do not modify without being asked

- `backend/app/schemas/schemas.py` is contract v1 (SCHEMA-0 freeze).
  Route paths, status codes and response models in `routes.py`, and the
  `AIProvider` protocol in `services/ai.py`, are part of the same contract.
  Never change any of these as a side effect of another task. If a task
  seems to require a contract change, stop and say so — it needs a PR of
  its own plus a decision-log entry in `docs/DESIGN_NOTES.md`.
- Risk is categorical (`RiskLevel` enum), never numeric — this is decision
  D-05 and it is deliberate. `AIAnalysisResult` (what every `AIProvider`
  must return) has no numeric field and never will; no provider is ever
  asked for or returns a score, percentage, or confidence number. Always
  reference the `RiskLevel` and `Recommendation` enums; never hardcode
  label strings, including in tests.
  - One narrow, already-decided exception (D-09,
    `docs/DESIGN_NOTES.md`): `AnalysisOut.risk_score` is a 0-100 value
    computed server-side by the pure function in `services/scoring.py`
    from the already-validated categorical result — never by an LLM, never
    part of `AIAnalysisResult`. Don't extend this pattern to other numeric
    fields (e.g. a "confidence score") without the same stop-and-flag
    process as any other contract change.

## Definition of Done

- Each story's tests exist in `backend/tests/test_api.py` as skipped tests;
  the skip reason names the story. Done = un-skipped and green.
- Never weaken, delete, or skip-around a test to make it pass. If a test
  seems wrong, stop and flag it for team discussion.
- CI runs on the MockProvider only — nothing may require a network call
  or an API key to pass tests.

## Conventions

- Branches: `type/story-id-short-description` (e.g. `feat/us-1.2-login-jwt`).
  All work via PR to `main`; never commit to `main` directly.
- Commits: conventional style (`feat:`, `chore:`, `test:`, `docs:`, `ci:`),
  one concern per commit, compressed single-line messages preferred.
- No secrets in the repo, ever. Config comes from env vars via
  `app/core/config.py`; `.env` is gitignored, `.env.example` is the map.
- Update docs in the same PR as the code they describe.

## Pitfalls

- `ListingIn.description` has no max_length in the schema on purpose —
  the size cap is enforced in the route (413) from settings. Do not "fix".
- `ListingIn.currency` validates shape (any 3-letter code), not a currency
  whitelist, on purpose. Do not "fix".
- `HttpUrl` values need `str()` before DB persistence.
- Logout is client-side token discard; there is no server-side revocation
  in MVP. Do not invent a token blacklist.
- Analysis flow is synchronous: persist listing, then analyze, in one
  request. Do not add lifecycle/status columns or async queues.

## Run / verify

- Backend tests: `cd backend && python -m pytest tests/ -v --cov=app --cov-report=term-missing`
  (baseline varies as stories land; CI enforces `--cov-fail-under=85` as a
  floor, not a target — see docs/DESIGN_NOTES.md).
- Full stack: `docker compose up --build`.