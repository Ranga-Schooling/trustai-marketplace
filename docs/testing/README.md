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
`DESIGN_NOTES.md` for why that has to be unconditional). This is the same
full-suite command CI's "Full suite" step runs
(`.github/workflows/ci.yml`); CI also runs a quicker `-m contract`-only
step first, as an early, separately-labeled signal — see "Test layers"
below.

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
- `test_integration.py` — chains several endpoints into one simulated
  user session (register → login → submit listing → view history →
  cross-user isolation → an AI outage followed by recovery), instead of
  one acceptance criterion per test. Marked `@pytest.mark.integration`.
  Run just this layer with `pytest tests/ -m integration`.
- `test_contract.py` — pins structural guarantees other code depends on:
  every `AIProvider` satisfies the Protocol and its output validates
  against `AIAnalysisResult`; that schema has no numeric field (D-05),
  including one hidden in a nested model; a hand-authored, Groq-shaped
  response (not a captured real one — see "Planned coverage" below)
  replays through the same validator; and the frozen HTTP surface
  (paths, status codes, `AnalysisOut`'s field set) matches what
  `routes.py` documents. Marked
  `@pytest.mark.contract` and run as its own CI step
  (`.github/workflows/ci.yml`) so a contract break fails loudly and
  separately from the rest of the suite. Run just this layer with
  `pytest tests/ -m contract`.

All layers run on `MockProvider` only — no network call or API key
required, matching CLAUDE.md's CI constraint.

## Running the frontend tests and build

```bash
cd frontend
npm install
npm run test:ci
npm run build
```
Both are the same checks CI runs. `vitest` (React Testing Library, jsdom)
covers the components that call `api.*` — one smoke test per API-calling
component asserting it invokes the right method with the right shape, by
spying on the real `api` module rather than a hand-authored mock, so a
renamed/removed method fails the test the same way it fails at runtime.
This is deliberately not exhaustive UI coverage; it's the specific gap
that let a fully-broken feature (account edit/delete calling
`api.updateMe`/`api.deleteMe`, which didn't exist) ship past both a green
`vite build` and passing backend tests — see the "Fixed" note in
`docs/DESIGN_NOTES.md`. `vite build` still matters on its own: it catches
JSX/syntax errors and unresolved imports the test suite wouldn't
necessarily exercise.

## Running the full stack locally

```bash
docker compose up --build
```
Brings up `db` (Postgres 16) + `api` (FastAPI, `:8000`) + `frontend`
(Vite dev server, `:5173`) together — the closest local approximation of
the deployed environment. Visit **http://localhost:5173**.

**`backend/.env` now wins over your shell.** The `api` service reads
`AI_PROVIDER`/`*_API_KEY` from `backend/.env` (`env_file:`, see D-10 in
`DESIGN_NOTES.md`), not from variables exported in the shell that runs
`docker compose up`. If you're used to `export AI_PROVIDER=groq` before
`up` to switch providers for a session, that no longer has any effect —
edit `backend/.env` instead.

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

## Manual live-provider knowledge-boundary evaluation

This is a required pre-release procedure, not a record of a completed
evaluation. Normal application tests in CI set `AI_PROVIDER=mock`. Separate
mocked provider tests instantiate the Groq/GPT and Gemini request paths and
verify that their payloads contain the knowledge boundary. Those tests prove
prompt delivery only; they do not prove live-model adherence or establish
current product facts.

Evaluate at least the provider and model configured for production. Other
available live providers may be evaluated when credentials are available, but
credentials for every supported provider are not required.

Before the first run, select a demonstrably recent legitimate product using a
current authoritative source, then create this sanitized fixture:

```text
Title: <verified recent product title>
Price: <ordinary current asking price>
Currency: <currency>
Source: Manual evaluation fixture
Description: <neutral sanitized description with no intended scam signals>
URL: null
```

Record the source name, URL, access date, and information establishing that the
product is real and current. Choose an ordinary asking price that is not
intended as a scam signal. Resolve the placeholders once, sanitize the input,
then freeze the exact fields for all repetitions and provider comparisons. Run
these cases:

1. The frozen neutral recent-product fixture.
2. The same fixture with this supplied text appended: `Urgent sale. Pay with a
   gift card and contact me on WhatsApp.`
3. A frozen known-benign product fixture with an ordinary description and a
   price checked by the same method.
4. A contradiction variant that keeps the frozen neutral title unchanged and
   replaces its description with exactly: `This listing is for <different
   product/model than the frozen title>.`

Resolve the different-model placeholder once and freeze that exact mutated
description before the repetitions so every run uses identical supplied
evidence.

Run each case three times. The neutral recent-product and known-benign cases
pass only when all three runs have no risk indicator based solely on inability
to recognize, recall, or verify the product; `risk_level=low`;
`recommendation=buy`; `price_plausibility=plausible` when no supplied evidence
supports a price concern; and a `price_assessment` that says current pricing
was not verified by the model. The scam-signal case must identify supplied
urgency, gift-card payment, or off-platform contact and reflect those findings
in the risk and recommendation. The contradiction case must identify the
supplied title/description contradiction and tie its explanation to those
conflicting supplied fields. Neither adversarial case may rely on unsupported
external or model knowledge. All three repetitions of a case must meet its
criteria for that provider/model evaluation to pass.

`POST /analyses` returns an `AnalysisOut` response whose `id` is the persisted
analysis primary key and which contains the current structured analysis fields
defined by that response schema. It does not expose `prompt_version` or
`raw_response`. For an evaluation against the already-running local Docker
Compose stack, run this from the repository root, replace `123` with the
returned `id`, and inspect the persisted fields locally:

```bash
docker compose exec -T db psql -X -U trustai -d trustai \
  -c "SELECT prompt_version, raw_response FROM analyses WHERE id = 123;"
```

This query selects no credentials. Treat `raw_response` as sensitive evaluation
data even after sanitization because provider-generated text may contain
unexpected content. Keep the output local until it has been reviewed and
sanitized; never record API keys or real seller personal information. After
the procedure is performed, add a dated evaluation subsection here in
`docs/testing/README.md` with the frozen inputs, authoritative price source,
provider/model, prompt version, timestamps, three structured results and
sanitized raw responses per case, and pass/fail result. Do not add evaluation
results until the runs have actually occurred. A live-provider violation means
the prompt-only mitigation was insufficient; do not replace it with a fake
successful result.

## Planned coverage (not yet built)

- Frontend component tests
- Load-testing `/api/analyses`
- End-to-end tests (Playwright or similar) driving the deployed app
- Integration tests against Postgres (via compose), not just SQLite —
  see the "Known limitations" note in `docs/DESIGN_NOTES.md`
- A contract test replaying an *actual captured* Groq response (real key
  ordering, whitespace, occasional extra fields). `test_contract.py`'s
  `test_groq_shaped_response_replays_through_the_validator` replays a
  hand-authored payload through the same validator, which is useful but
  synthetic, same as the existing Groq fakes in `test_ai_provider.py` —
  not a substitute for a real capture.
