# Architecture & Board Alignment Review — 2026-08-01

Reviewer stance: principal-architect pass over the Trello board (export dated
2026-08-01) against the decisions already on record in this repo —
`CLAUDE.md`, `docs/DESIGN_NOTES.md` (the closest thing this project has to an
ADR log), `docs/BACKLOG.md`, and the actual code in `backend/app`. Produced on
a dedicated branch, no app code touched.

Every finding below cites the specific decision it conflicts with and the
specific card/file it conflicts against, so it can be checked independently
rather than taken on faith.

**Update:** §0 below extends this review to the 9 PRs already open against
`main` at review time (#20, #21, #24, #25, #26, #29, #30, #31, #32) — work
already done, not just planned. One finding there is more urgent than
anything in §1: the numeric-score conflict isn't hypothetical, it's already
implemented and open for merge.

---

## 0. Open PR audit — work already done, checked against the same decisions

All 9 non-review, non-infra PRs open at review time were pulled and diffed
against `main`. Headline result: two of them already ship the D-05 conflict
as working code, not just a backlog card.

### 0.1 🔴 PR #31 and PR #32 (amooch) already implement the numeric risk score — do not merge as-is

- **PR #31** "refactor: analysis result" (`frontend/src/components/AnalysisResult.jsx`): replaces the existing, correct `<span className={\`badge ${riskLevel}\`}>{riskLevel}</span>` categorical badge with a new "Risk score … / 100" tile reading `analysis.risk_score`.
- **PR #32** "feat(history): replace card list with a filterable table" (`frontend/src/components/History.jsx`): same swap — replaces `<span className={\`badge ${item.risk_level}\`}>{item.risk_level}</span>` with `<td>{item.risk_score ?? '—'}</td>`.
- **The problem:** `risk_score` does not exist anywhere in the backend contract. `AnalysisOut`/`AnalysisWithListingOut` in `schemas/schemas.py` only expose `risk_level: RiskLevel` (categorical, three values) — this is D-05, deliberately, precisely because LLM-invented numeric scores aren't calibrated. Both PRs' own fallback code (`typeof analysis.risk_score === 'number' ? … : null`, `item.risk_score ?? '—'`) proves the authors already knew the field might not exist — it doesn't, and per D-05 it never will unless the team explicitly overturns that decision.
- **Concrete effect if merged today:** every user sees "— / 100" where they currently see a working `low`/`medium`/`high` badge. This is a shipped regression, not a future risk.
- **Root cause:** this is almost certainly downstream of Trello card #27 ("0–100 risk score combining rule-based and AI signals," §1.1) — the frontend was built to a card that itself contradicts a standing decision. Fixing the card without checking the two PRs already built against it would have missed this.
- **Action:** Before merging #31 or #32, revert the `risk_score` UI back to the categorical badge (the diffs show exactly what to restore). If the team wants a numeric score badly enough to justify overturning D-05, that decision has to happen first, in the open, with a new decision-log entry and a corresponding backend contract change (new PR, `AIAnalysisResult` amendment) — not by merging frontend code that quietly assumes it.

### 0.2 🟢 PR #21 and PR #24 — model examples of compliant contract-adjacent work

Both add new functionality that touches the frozen files (`routes.py`, `schemas.py`) without violating SCHEMA-0, and both explicitly document why:
- **PR #21** (US-2.3, URL fetch preview) adds `POST /listings/preview` as a wholly new, additive endpoint with its own schemas (`ListingUrlIn`, `ListingPreviewOut`) that never touch `ListingIn`/`POST /analyses`. Documents the choice as decision **D-06** in `DESIGN_NOTES.md`, including a real SSRF threat-model writeup (private/loopback/link-local rejection, redirect-count cap, response-size cap) — this is the level of rigor §1's conflicts should have gotten before landing on the board.
- **PR #24** (US-1.4, profile edit) adds `PATCH /auth/me` as an additive endpoint with its own `UserUpdate` schema, leaves `UserOut`/`UserRegister`/`UserLogin` untouched, correctly updates the ownership docstring, and ships tests for every branch (auth-required, name update, email update, duplicate-email 409, empty-body 400).
- **Action:** none — hold these up as the template for how §1's conflicts should be resolved if the team decides they're worth pursuing (i.e., additive endpoint + decision-log entry, not a frozen-contract edit).

### 0.3 🟡 All 9 open PRs are stale relative to `main` — rebase before further review

Checked via `git rev-list` against `origin/main`:

| PR | Ahead | Behind |
|---|---|---|
| #20 | 4 | 3 |
| #21 | 2 | 3 |
| #24 | 1 | 3 |
| #25 | 1 | 3 |
| #26 | 1 | 3 |
| #29 | 2 | 2 |
| #30 | 1 | 3 |
| #31 | 1 | 3 |
| #32 | 1 | 3 |

None of them include the E3 merge (`PR #12`) or the two release commits after it. Practically: any CI runs already recorded on these PRs did **not** validate against the current `main`, including the E3 code these PRs' UI renders against — which is exactly how #31/#32 (§0.1) shipped against a field that was never real. Rebase (or merge `main` in) before the next round of review on any of them.

### 0.4 ⚪ PR #20 is a phantom — close it

`git diff origin/main...pr20-check` is **empty** — its content ("build sign-in/register form for auth flow") already landed on `main` through some other path (most likely superseded by #25's wireframe-alignment work on the same component). Nothing left to merge. Close it rather than leaving it open indefinitely as false signal of pending work.

---

## 1. Critical conflicts — stop before building these as currently worded

### 1.1 Card #27 "As a buyer, I see a 0–100 risk score combining rule-based and AI signals" — violates D-05

- **Where:** Trello card `LtJvJrjo` (idShort 27), list: **Current Sprint**, unassigned.
- **Conflicts with:** `docs/DESIGN_NOTES.md` → *"Categorical risk, not numeric… Risk is therefore low/medium/high… This is testable… in a way a free-floating number is not."* Also `CLAUDE.md`: *"Risk is categorical (`RiskLevel` enum), never numeric. Do not add scores, percentages, or confidence numbers anywhere — this is decision D-05 and it is deliberate."*
- **Why it matters:** `AIAnalysisResult` (the frozen contract in `schemas/schemas.py`) has no numeric field, and `RiskLevel` is a three-value enum by design — LLM-invented scores aren't calibrated (a re-run can drift 20 points with no substantive change), which is exactly why D-05 exists. A card literally titled "0–100 risk score" reopens a decision that was made for a specific, tested reason.
- **Action:** Don't build this as worded. Either reword the card to match what's actually shipped (`risk_level` badge + named indicators), or if the team genuinely wants a numeric score, that's a SCHEMA-0 amendment — needs its own PR and a new decision-log entry overturning D-05, not a sprint card.

### 1.2 Card #17 "Listings persist in Postgres with lifecycle status (submitted → processing → analysed)" — violates the synchronous-flow decision

- **Where:** Trello card `h0GkdcEV` (idShort 17), list: **In Progress**, assigned to `mulima`.
- **Conflicts with:** `CLAUDE.md` pitfalls: *"Analysis flow is synchronous: persist listing, then analyze, in one request. Do not add lifecycle/status columns or async queues."* Also the actual `Listing` model in `backend/app/models/db.py` has no status column, and `routes.create_analysis` persists the listing and runs the provider in the same request — there is no "processing" state to represent.
- **Why it matters:** This is already **In Progress**, which is the most urgent conflict on the board — someone may be actively adding a status column and/or a background worker to a codebase whose contract, tests (`test_ai_failure_returns_502_and_saves_listing`), and error-handling design all assume synchronous request/response.
- **Action:** Talk to `mulima` today. If a lifecycle status is genuinely wanted (e.g., for a future async pipeline), that's an architecture change bigger than a card — needs a decision-log entry and probably a new story, not silent work against the current contract.

### 1.3 Card #32 "Currency handling: detect listing currency and normalise using a reliable data source" — conflicts with the currency-shape-only decision

- **Where:** Trello card `sWnBXnEo` (idShort 32), list: **In Progress**, assigned to you (Ranga), moved there 2026-07-31.
- **Conflicts with:** `CLAUDE.md` pitfalls: *"`ListingIn.currency` validates shape (any 3-letter code), not a currency whitelist, on purpose. Do not 'fix'."* And `backend/app/services/ai.py`: *"This mock intentionally does not perform live exchange-rate conversion"* — precisely to keep CI network-free per the CI rule that nothing may require a network call to pass tests.
- **Action:** Already flagged in this session. Since it's now active, pause before writing code — this needs either a decision-log entry re-opening the currency decision, or a rescoped card that doesn't touch live FX/`ListingIn`.

---

## 2. Process/documentation conflicts

### 2.1 Deployment target mismatch: Render (decided) vs. GitHub Pages (still on two cards)

- **Decision on record:** `docs/DESIGN_NOTES.md` → *"Cloud, free tier: Render web service for the API (Docker), Render static site for the frontend, managed Postgres on Neon/Supabase."* Card #9 was already corrected to say "Deploy frontend skeleton to **Render** and link to the custom domain."
- **Still wrong:** Card #23 "CD: auto-deploy frontend to **GitHub Pages** and backend services on merge to main" (In Progress) and card #44 "Repo README: deployed app link (**GitHub Pages** custom domain)…" (Next-up) were never updated to match.
- **Action:** Cheap fix — rename #23 and #44 to Render, and confirm the actual CD workflow (GitHub Actions → Render deploy hook, not a `gh-pages` publish action) before #23 is built. If CD is built against GitHub Pages by mistake, the frontend deploys to the wrong place and the "custom domain" work on #9 is wasted.

### 2.2 Ownership comments in code reference a team member not on the Trello board

- **Finding:** `backend/app/models/db.py` line 4 names **"Abdallah"** as the E2 (Listing Ingestion) owner. The Trello board's member list is: Ranga Nyamadzawo, Ahmed Al-Mandalawi, Adrian Muchatibaya, Mulima Chibuye, Samar El Ghandour, Samar Salah. There is no Abdallah.
- **Compounding issue:** `backend/tests/test_api.py` line 3 assigns test-suite ownership to **"Samar"** — ambiguous, since there are two Samars on the board (El Ghandour and Salah).
- **Why it matters:** `routes.py`'s docstring assigns `GET /analyses*` (US-4.1, the biggest functional gap — see §3) to this same "Abdallah." If that person isn't actually on the team anymore, US-4.1 has no real owner, which likely explains why it's sat unassigned in Current Sprint since 2026-07-30 while PR #32 (frontend history UI) is already built and waiting on it.
- **Action:** Team sync to confirm current ownership map, then fix the comments in `db.py`, `ai.py`, and `test_api.py` to name real people (or roles) so this doesn't happen again. Whoever is picked, claim card #30 in Trello today.

### 2.3 `docs/BACKLOG.md` overstates delivery status

- **Finding:** `docs/BACKLOG.md` marks **US-4.1 as "Implemented"** and lists it under **"Must (shipped)"**, citing `test_history_is_per_user` as a passing test.
- **Reality:** `GET /api/analyses` and `GET /api/analyses/{id}` both still `raise NotImplementedError("E2/US-4.1")` in `routes.py`, and `test_history_is_per_user` is still `@pytest.mark.skip`.
- **Action:** Fix the doc in the same PR that implements US-4.1 — don't let "shipped" claims outlive the code, especially in a document graders will read as the project's system of record.

### 2.4 Test hygiene: hardcoded label strings vs. D-05's enum rule

- Already raised during PR #12 review and unresolved: `test_low_risk_listing_gets_buy` / `test_high_risk_listing_gets_avoid` assert on raw `"low"`/`"buy"`/`"high"`/`"avoid"` strings instead of `RiskLevel`/`Recommendation` members, contradicting *"Always reference the RiskLevel and Recommendation enums; never hardcode label strings, including in tests."* Low urgency but cheap to fix — bundle it with whoever next touches `test_api.py`.

---

## 3. The actual priority gap (confirmed against both code and board)

**US-4.1 — View history** (Trello card #30, `wxz1aAaA`) is the highest-priority
piece of unstarted work:
- Code: both history endpoints are stubs.
- Board: unassigned, sitting in Current Sprint since 2026-07-30, no ownership.
- Downstream impact: PR #32 (frontend history table, already built by `amooch`)
  is blocked waiting on this.
- Compounding: the ownership comment pointing at it (§2.2) may be stale.

This should be the very next thing picked up, once §2.2 resolves who owns it.

---

## 4. Not conflicts — sanity-checked and fine as-is

- Card #28 (price plausibility) — matches the already-shipped `price_assessment` field.
- Card #20 (multi-provider abstraction: Groq/Gemini/GPT) — the `AIProvider` Protocol + `get_provider()` strategy pattern already supports adding providers this way; no rework needed, just more `elif` branches and providers.
- Card #21 (deterministic mock LLM) — already fully shipped (`MockProvider`); the card is just stale and should move to Done.
- Card #36 (robust input handling for URL fetch) — consistent with the already-open URL-fetch story (PR #21, US-2.3); no contract conflict.
- Card #31 (integration tests + contract tests in CI) — matches a named gap in `DESIGN_NOTES.md`'s "Not yet covered" list; good pick, already covered in an earlier review this session.
- Card #37 (E2E happy-path suite in CI) — overlaps card #31 in scope; not a conflict, just worth consolidating into one card so the same test suite isn't built twice.

---

## 5. The map — how to build this correctly from here

This is a sequencing guide, not a rewrite of the backlog. Each phase assumes
the previous one's guardrails hold.

### Phase 0 — Realign (do this before writing more code)
1. **Most urgent:** fix or hold PR #31 and #32 (§0.1) — revert the `risk_score` UI to `risk_level` before either merges. This is the one item here with a real, immediate user-facing regression sitting in review right now.
2. Rebase all 9 open PRs onto current `main` (§0.3) so future review actually validates against the E3 code; close PR #20 (§0.4) as superseded.
3. Team sync on §1.1–§1.3: get explicit yes/no on the three critical conflicts. Any "yes, we want this" becomes a decision-log entry in `DESIGN_NOTES.md` *before* code, not after.
4. Fix ownership comments (§2.2) and confirm who owns US-4.1.
5. Correct the Render/GitHub Pages cards (§2.1).
6. Correct `docs/BACKLOG.md`'s US-4.1 status (§2.3).

### Phase 1 — Close the last Must-have gap
7. Implement US-4.1 (`GET /analyses`, `GET /analyses/{id}`), un-skip `test_history_is_per_user`. This unblocks PR #32 (once its §0.1 fix lands) and completes EPIC 4.
8. Fix the D-05 string-literal test hygiene issue (§2.4) in the same pass if convenient — it's a one-line-per-assertion change.

### Phase 2 — Harden what's shipped (all named as gaps in `DESIGN_NOTES.md` already — don't rediscover them, just schedule them)
9. Rate limiting on `POST /analyses` (currently: none — a deployed instance exposes the Groq key's quota).
10. Tighten CORS from `allow_origins=["*"]` to the deployed frontend origin.
11. Trello card #31 (Current Sprint, "Integration tests… contract tests in CI" — not to be confused with PR #31 above): replay a recorded Groq response through `AIAnalysisResult` validation, and add one Postgres-backed integration test (SQLite JSON behavior differs subtly from Postgres — this is the only place that gap can bite before submission).

### Phase 3 — Ship the infra story correctly
12. Resolve §2.1: decide Render vs. GitHub Pages once, update the three affected cards, then build CD against the real target.
13. Wire `alembic upgrade head` into deploy/container start (named as a Sprint 3 candidate in `DESIGN_NOTES.md` already).
14. Merge PR #33 (docker-compose dev-startup fix) if not already done — it's a pure infra fix, no contract risk, unblocks clean onboarding.

### Phase 4 — Only after Phase 0–3: net-new scope
15. Anything that touches `ListingIn`, `AIAnalysisResult`, `AIProvider`, or route signatures (currency normalization for real, image uploads/#41, numeric scoring if the team overturns D-05, listing-status lifecycle if the team overturns the sync-flow decision) goes through the SCHEMA-0 change-control process explicitly: **its own PR + a decision-log entry**, never bundled into an unrelated story.

### Standing guardrails (apply at every phase, not just once)
- Before starting any card that touches a frozen file (`schemas/schemas.py`, route signatures/status codes in `routes.py`, the `AIProvider` protocol), check `CLAUDE.md`'s pitfalls list and `DESIGN_NOTES.md`'s decisions section first — five minutes of reading versus a rebuilt feature.
- Every un-skip in `test_api.py` is a Definition-of-Done signal — if a card is "done" but its test is still skipped, it isn't done.
- Keep `docs/BACKLOG.md`'s implementation status truthful in the same PR as the code — graders and teammates both use it as the map of what's real.
- When a Trello card's wording contradicts a decision already in `DESIGN_NOTES.md`, the card is wrong until the team explicitly re-decides it — decisions don't get silently overridden by whoever writes the next card.
