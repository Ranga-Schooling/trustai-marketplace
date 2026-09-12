# TrustAI Marketplace: Capstone Design and Testing Report

## Document status and evidence standard

This report describes TrustAI Marketplace at the final Capstone release,
`v1.20.0`, whose immutable source commit is
`5ebc757ba66ff647944602245c18bedf6631680e`. It is a synthesis of the
implemented system, its engineering rationale, and the evidence used to assess
it. Current source and tests establish implementation; a release identifies an
immutable source state; and a successful deployment workflow establishes image
identity and its configured health checks. None of those, by itself, proves a
complete public-browser journey or a real provider transaction.

The repository also contains chronological records written before the final
release. In particular, [ADR-001](../decisions/ADR-001-deployment-platform.md)
and the early [architecture diagrams](../architecture/) describe a planned
Render/Groq deployment, while the August
[integration report](../INTEGRATION_VERIFICATION_REPORT.md) records a time when
History and profile work were incomplete. Those records are retained as
evidence of the design process. They are not descriptions of the final AWS,
OpenAI-capable implementation.

The terms used below are deliberately distinct:

- **planned** means an intention appears in a backlog, decision record, or
  design artifact;
- **implemented** means the behavior is present in source and tests;
- **released** means the source is included in the immutable `v1.20.0` tag;
- **deployment-health verified** means GitHub Actions activated the release
  images and passed the configured container-local health path; and
- **production E2E verified** requires separate, sanitized evidence from the
  public application and, where relevant, the configured provider.

## 1. Executive design overview

TrustAI Marketplace is an authenticated decision-support application for
buyers assessing online marketplace listings. A buyer can enter a listing
manually or use a guarded URL preview to obtain editable suggestions. The
application returns a structured text assessment: a summary, categorical risk
level, named risk indicators, qualitative price plausibility, seller questions,
a Buy/Caution/Avoid recommendation, and a deterministic 0–100 Trust score. It
also retains owner-scoped analysis history and makes a listing recoverable when
provider analysis fails.

Optional Visual Inspection is a second, explicitly separated evidence channel.
It evaluates one to three user-selected photos for visible observations after
consent. It does not change the text assessment, Trust score, categorical risk,
or recommendation, and the TrustAI application does not persist the photos or
visual findings.

The principal system boundary is therefore not “AI decides whether a listing is
safe.” The model proposes a bounded structured assessment from supplied listing
content. Application-owned parsing, schemas, cross-field rules, evidence
policies, ownership checks, scoring, persistence, and user-facing limitations
remain authoritative. TrustAI cannot establish that a seller is honest, that an
item is authentic or owned by the seller, that hidden components work, or that
an asking price matches a verified current market price.

The final release is a small modular monolith rather than a distributed system:
a React client, one FastAPI service, and PostgreSQL, packaged as separate
containers behind nginx and Caddy. This keeps deployment and debugging
tractable for a small Capstone team while preserving explicit boundaries around
identity, listing management, text analysis, visual evidence, and external
providers.

## 2. Requirements translated into design

The [user-story backlog](../BACKLOG.md) is the detailed requirements-to-code
traceability record. The following table summarizes the final relationship
between the major story groups and the design that supports them.

| Requirement group | Released design response | Architectural consequence |
|---|---|---|
| Accounts and sessions | Registration, login, profile update, account deletion, bcrypt password hashes, and expiring JWT bearer tokens | Authentication is centralized in FastAPI dependencies; analysis data is always tied to an authenticated owner |
| Listing submission | Validated manual input plus an additive URL-preview endpoint | Preview suggestions cannot bypass `ListingIn`; the buyer reviews the values before analysis or persistence |
| Structured analysis | Provider adapters must return `AIAnalysisResult`; application validation precedes persistence | Provider-specific protocols are isolated from the public API and database contract |
| Explainable risk | Categorical risk, named indicators, deterministic recommendation, and application-computed Trust score | The model supplies no numeric score; score/recommendation consistency is enforceable and testable |
| Price guidance | Categorical plausibility plus a qualitative explanation | The product can flag supplied-context concerns without claiming live market valuation |
| History and recovery | Owner-scoped history/detail, persisted listing before analysis, failed-listing view, and retry endpoint | Provider failure does not discard the buyer’s input; recovery reuses the stored listing rather than duplicating it |
| Optional image evidence | Capability-gated, consented, transient Visual Inspection on an existing owned analysis | Images and findings remain outside the text contract, score, history schema, and database |
| Administration | Admin-only aggregate analytics and a separate promotion script | Operational visibility does not create a self-service privilege-escalation route or expose raw user submissions |
| Delivery and quality | Pull-request CI, contract and full test gates, semantic releases, SHA-tagged images, SSM activation, and health checks | Release identity is reproducible and deployment does not depend on inbound SSH |

Several omissions are intentional scope decisions, not hidden incomplete user
stories. Password reset, email verification, multifactor authentication,
refresh-token rotation, runtime provider switching, history search, PDF export,
automatic marketplace-photo retrieval, authoritative live price research, and
asynchronous job processing are deferred. The application follows the system
theme until a user selects light or dark; it does not expose a separate
user-selectable “system” mode after an explicit choice.

## 3. Final system architecture

```text
Buyer browser
    |
    | HTTPS / JSON / multipart images
    v
Caddy (public 80/443, TLS and reverse proxy)
    v
nginx (static React application; /api proxy; scoped 11 MiB visual route)
    v
FastAPI modular monolith
    |-- authentication and owner/admin authorization
    |-- listing preview and SSRF controls
    |-- text-analysis provider boundary and deterministic validation
    |-- transient Visual Inspection boundary
    |-- SQLAlchemy persistence and Alembic migration startup
    |
    +--> PostgreSQL 16 named volume
    +--> configured text provider (only when explicitly selected)
    +--> independently configured visual provider (only when available)

GitHub Actions --> backend/frontend images in ECR --> EC2 activation via SSM
```

### 3.1 Frontend

The browser client is implemented in React with JavaScript/JSX and built by
Vite. A small API module owns bearer-token attachment, `401` session-expiry
handling, JSON error handling, and multipart Visual Inspection calls. React
components separate authentication, listing entry, analysis rendering, risk
gauge, history/retry, and visual findings. Theme state uses the browser’s color
scheme when no preference is stored, and stores an explicit light/dark choice
in `localStorage`. The authentication token is held in `sessionStorage`.

The client is not trusted to enforce security rules. Its validation, consent,
loading locks, capability hiding, and safe error messages improve interaction,
but the backend repeats all authoritative authentication, ownership, input,
image, and provider checks. The production frontend is compiled in a Node 18
Docker build stage and served by nginx; CI and documented local development use
Node 22.

### 3.2 Backend and API

FastAPI exposes the HTTP application, Pydantic defines request/response
contracts, and dependency injection supplies database sessions and current-user
or admin checks. Synchronous analysis deliberately persists the listing first,
then calls a provider, validates the result, computes the Trust score, and
persists the analysis. This is simpler than a queue for Capstone scale and gives
the failure path a concrete recovery record.

The service layer contains policy-bearing operations rather than placing them
in React or database models: provider calls and validation, deterministic
scoring, URL fetching, Visual Inspection, and image normalization. Routes
orchestrate those services and map failures to application-owned HTTP details.

### 3.3 Persistence

[SQLAlchemy models](../../backend/app/models/db.py) map the domain records and
[Alembic revisions](../../backend/alembic/versions/) own production schema
evolution. The backend container runs the migration wrapper before Uvicorn
starts. Tests use disposable SQLite tables for speed; production uses
PostgreSQL 16. This is an explicit testing trade-off: SQLite provides
deterministic isolated tests, but it does not prove every PostgreSQL-specific
behavior.

### 3.4 Production edge and containers

[Caddy](../../deploy/Caddyfile) is the public 80/443 entry point. It proxies to
nginx, which serves the compiled single-page application and routes `/api` to
FastAPI over the internal [Compose network](../../deploy/docker-compose.yml).
FastAPI has no host-published production port. The nginx body allowance for
Visual Inspection is 11 MiB and applies only to that route; the application
separately enforces its 10 MiB combined source-image limit.

Backend, frontend, Caddy, and database services use bounded Docker JSON-log
rotation. PostgreSQL and Caddy state use named volumes. Application deployments
do not delete those volumes.

### 3.5 Build, release, and deployment flow

The [CI workflow](../../.github/workflows/ci.yml) runs on pull requests and
pushes to `main`. The [release workflow](../../.github/workflows/release.yml)
uses conventional commits and semantic-release to version the project, update
the changelog, create a tag, and publish a GitHub release. The narrow release-bot
bypass and human `main` rules are documented in
[ADR-002](../decisions/ADR-002-branch-protection-ruleset.md).

The [deployment workflow](../../.github/workflows/deploy.yml) builds backend and
frontend images, publishes `latest` and immutable commit-SHA tags to Amazon ECR,
and uses AWS Systems Manager Run Command to activate the SHA on EC2. It validates
Compose and Caddy configuration, pulls before activation, waits for Caddy’s
health check, then removes unused images, containers, and networks without
pruning volumes. GitHub Actions currently authenticates to AWS using a
restricted IAM user’s credentials stored in GitHub Secrets, not OIDC; SSM
removes the need for a GitHub-held SSH private key or inbound SSH from runners.

## 4. Architecture evolution and significant decisions

TrustAI’s architecture evolved through implementation feedback rather than
following the initial diagram unchanged.

| Period | Evidence state | Evolution |
|---|---|---|
| July planning | **Decided at the time** | ADR-001 selected Render for a static frontend, Docker API, and managed PostgreSQL. Early diagrams also showed Groq as the external model. |
| July foundation | **Implemented** | React/FastAPI scaffolds, shared Pydantic contracts, authentication, SQLAlchemy models, deterministic mock analysis, Compose, CI, and semantic-release established the modular-monolith baseline. |
| August integration | **Implemented and hardened** | URL preview gained SSRF controls; deterministic scoring resolved the conflict between a desired number and uncalibrated model output; history, profile, migrations, admin analytics, recovery, tests, and AWS deployment matured. |
| Late August | **Implemented** | Knowledge and image limitations moved from prompt wording into deterministic evidence-policy checks; SSM deployment, log rotation, disk cleanup, and backup automation addressed operating concerns. |
| September finalization | **Implemented and released** | Dark mode, mobile/risk-gauge corrections, Visual Inspection, per-listing retry isolation, strict response validation, and the OpenAI Responses/Terra text path entered `v1.20.0`. |

The final AWS design therefore supersedes ADR-001 operationally without
rewriting it historically. The reason is visible in the final artifacts rather
than a replacement ADR: the team implemented container-image control through
ECR, host control through EC2, deployment without inbound SSH through SSM, and
same-origin TLS/proxying through Caddy and nginx. This increased operational
responsibility but provided immutable image activation and direct control over
the complete stack.

Other important design changes were evidence-driven:

- **Numeric risk without model calibration:** D-09 retained D-05’s prohibition
  on model-generated numbers while adding a deterministic score derived from
  validated categories.
- **Persisted recovery:** storing the listing before analysis became useful to
  the buyer only after failed listings and a retry route were added.
- **Prompt plus deterministic safeguards:** observed limitations of prompt-only
  grounding led to strict response parsing, cross-field validation, and bounded
  evidence policies.
- **Separate visual evidence:** photos were not added to `AIAnalysisResult` or
  the database because their provenance, privacy, and lifecycle differ from
  text input.
- **Model selection:** the recorded evaluation ended in “tie/no clear winner”
  under its formal threshold. D-21 separately records the engineering decision
  to select GPT-5.6 Terra for the Capstone text workload; it does not rewrite
  the experiment as a formal win.

The [project timeline](PROJECT_TIMELINE.md) maps these transitions to repository
history. The early [architecture review](../architecture-review-2026-08-01.md)
is especially useful as evidence that planned cards and open branches were
challenged against stable contracts before integration.

## 5. Architecture and design patterns actually used

| Pattern or boundary | Concrete implementation | Problem solved | Trade-off |
|---|---|---|---|
| Modular monolith with layers | React client; FastAPI routes; service modules; Pydantic schemas; SQLAlchemy models | Keeps one deployable backend while separating transport, policy, and persistence responsibilities | Module boundaries are conventional rather than independently deployable |
| Strategy-style provider abstraction | `AIProvider` protocol and configuration-selected mock, Groq, GPT, and Gemini implementations in [`ai.py`](../../backend/app/services/ai.py) | Gives the application one `ListingIn -> AIAnalysisResult` boundary despite different provider transports | Provider-specific configuration and response extraction still require explicit adapters |
| Contract-driven boundary | Pydantic schemas, strict provider JSON Schema, contract tests, exact response parsing | Prevents provider output shape from silently becoming application state | Strictness rejects “nearly correct” model output rather than repairing it |
| Validation boundary | UTF-8/JSON parsing, resource limits, exact fields, Pydantic validation, cross-field rules, evidence policy | Converts untrusted generative output into either a complete accepted result or a safe failure | Bounded text-pattern policies cannot prove full semantic grounding |
| Deterministic derivation | Recommendation consistency checks and [`compute_risk_score`](../../backend/app/services/scoring.py) | Keeps risk presentation repeatable and prevents a numeric score from contradicting its category | Score reflects the designed formula, not a statistically calibrated probability |
| Dependency injection | FastAPI `Depends` for sessions, current user, and administrator | Centralizes lifecycle and authorization rules used by routes | The application still depends on framework conventions rather than a separate DI container |
| Configuration-selected behavior | Environment-backed settings for database and independent text/visual providers | One image can run locally, in CI, or production without embedded secrets | Changes require a process restart; runtime provider switching is deferred |
| Fail-closed optional capability | Server-owned Visual availability predicate and frontend hiding on `false` or fetch failure | Prevents incomplete configuration from exposing a broken upload flow | Availability checks configuration completeness, not credential validity or model usability |
| Immutable delivery identity | Semantic tag plus ECR commit-SHA image tags and `IMAGE_TAG` activation | Connects a deployment to reviewed source and supports selecting a known image | Rollback is operator-driven; database compatibility still needs attention |

The validation pipeline can reasonably be described as an anti-corruption
boundary in the general architectural sense: provider wire formats and prose
cannot enter application state until translated into the project’s strict
contract. It is not presented as a separate framework or independently
deployed anti-corruption service.

## 6. Data architecture

The central relational chain is `User -> Listing -> Analysis -> RiskIndicator`.
An `AnalysisFailureLog` also belongs to a listing. Users own listings; listings
own analyses and failure logs; analyses own indicators. ORM cascade rules
delete those dependent records when an account is deleted.

`User` stores identity, a bcrypt password hash, and the buyer/admin role.
`Listing` stores the reviewed title, price, three-letter currency, source,
description, and optional URL. `Analysis` stores the categorical result,
deterministic score, qualitative price fields, questions, model identity,
prompt version, and raw provider response for auditability. Risk indicators are
separate rows so their category, severity, and explanation remain structured.
Failure logs store safe provider/failure classifications to support aggregate
admin analytics.

Every history and detail query joins through the authenticated user’s listing.
An unknown analysis and another user’s analysis both produce a not-found
response, avoiding an ownership oracle. Admin analytics is the deliberate
exception: it aggregates counts across users behind an admin dependency but
does not return raw listing or analysis text. There is no self-service role
promotion endpoint.

The analysis flow commits the listing before invoking the provider. If the
provider or validation path fails, the route records the failure and returns a
safe `502`; the listing remains visible through `GET /listings/failed` and can
be retried through `POST /listings/{id}/retry`. Retry reconstructs `ListingIn`
from the owner’s stored row and uses the same analysis path. Per-listing client
state prevents one retry’s loading/error state from affecting another card.

Visual Inspection intentionally has no table. No image or visual-finding record
is added to PostgreSQL or object storage, and visual findings do not enter
History. This is an application-persistence claim only: multipart handling may
use request-scoped temporary spooling, and provider-side handling is governed
by the provider’s applicable data policy.

## 7. AI text-analysis architecture

### 7.1 Provider boundary and production source path

At `v1.20.0`, configuration supports `mock`, `groq`, `gpt`, and `gemini` text
providers behind the same protocol. The mock is deterministic and is the CI
default. Groq uses an OpenAI-compatible Chat Completions shape, Gemini uses its
own `generateContent` shape, and the final GPT adapter uses OpenAI Responses.
Missing keys fail real-provider construction; an unrecognized text-provider
value logs a warning and falls back to the mock. That fallback is convenient
for development but means text-provider typo handling is not strictly
fail-closed.

The intended source-level production selection is `AI_PROVIDER=gpt` with the
default `OPENAI_MODEL=gpt-5.6-terra`. The adapter posts to `/v1/responses`,
sends prompt version `v4`, requests strict JSON Schema output, caps output at
2,048 tokens, uses medium reasoning, disables storage, streaming, truncation,
and redirects, and configures no tools or search. The listing is rendered as
deterministic JSON and explicitly treated as untrusted content rather than
instructions.

This proves the implemented/default path, not the contents of the private EC2
environment. The repository does not currently prove that production was
privately configured to activate Terra or that a Terra request succeeded
through the deployed browser/API path.

### 7.2 Structured output and acceptance pipeline

The provider contract contains only:

- summary;
- `low`/`medium`/`high` risk level;
- at most ten structured risk indicators;
- price assessment and `plausible`/`suspicious`/`too_good_to_be_true` category;
- one to eight seller questions; and
- `buy`/`caution`/`avoid` recommendation.

For the Responses path, acceptance is all-or-nothing. The service requires a
successful, JSON-typed response with the expected model/status/output envelope
and exactly one completed output-text item. It strictly decodes UTF-8 JSON,
rejects duplicate keys, non-finite values, malformed Unicode, trailing data,
resource-limit violations, missing or extra fields, and invalid field types.
Pydantic validates the domain schema. A deterministic cross-field validator
requires the risk level to match the highest indicator severity and the
recommendation to match low/buy, medium/caution, or high/avoid. Finally, the
evidence policy rejects known unsupported reasoning families. The application
does not silently repair a partial or contradictory response.

The evidence boundary instructs and checks that unrecognized or recent product
knowledge, absent image evidence, generic platform reputation, assumed payment
protection, and unsupported market comparisons do not become adverse facts.
These controls reduce known failure modes; they are not proof that every model
statement is factually correct.

### 7.3 Deterministic Trust score and recommendation

The provider never returns the numeric Trust score. After validation, the
application computes it from the categorical risk level and indicator
severities. Risk tiers own non-overlapping ranges: low `0–33`, medium `34–66`,
and high `67–100`. Indicator severities carry weights `1`, `2`, and `3`; the
sum is capped at a weighted signal of `8` and linearly locates the score within
the selected tier before rounding. Consequently the same structured input
produces the same score, and a low result can never numerically outrank medium
or high. This is a deterministic presentation index, not a probability of
fraud or a calibrated confidence measure.

The recommendation is equally constrained: low maps to buy, medium to caution,
and high to avoid. A provider response that contradicts that rule is rejected.

### 7.4 Price and audit boundaries

Price plausibility is qualitative. TrustAI does not call a market-data source,
perform comprehensive product research, or verify a current price. The URL
preview can extract a price/currency string from page content, but that is an
editable suggestion from the submitted page, not independent market truth.

Successful analyses persist `model_used`, `prompt_version`, and the raw
generated JSON text alongside the normalized structured fields. This supports
later diagnosis but also makes that provider-generated text sensitive
application data that should not be exposed casually. The public result returns
the model used but not the prompt version or stored raw text.

### 7.5 Retry and failure behavior

The Terra Responses adapter allows no more than two physical attempts. Only
timeouts, transport failures, and HTTP `429`, `500`, `502`, `503`, or `504` may
reach the second attempt. Configuration errors, strict parsing, schema,
cross-field, evidence-policy, and deterministic client/HTTP failures are
terminal for that path. Other supported legacy providers retain their
historical bounded two-attempt validation flow; the report does not claim that
all adapters share Terra’s exact classification.

Failures are converted to application-owned exceptions and safe client output.
Provider bodies and credentials are not placed in those user-facing errors.

## 8. Visual Inspection architecture

Visual Inspection is invoked only for an existing completed analysis owned by
the authenticated caller. The frontend first requests the authenticated
`GET /api/capabilities` endpoint. Its response contains one boolean,
`visual_inspection_available`. Availability requires the supported `openai`
provider and non-empty configured key and model values. It does not validate
the credential or provider-side model availability; only an attempted provider
request can establish those. Missing/unsupported configuration, or a failed
capability fetch, leaves the feature hidden.

A user must select and consent to sending one to three JPEG, PNG, or WebP files.
The client provides early checks; the backend is authoritative. Limits are 4
MiB per source image, 10 MiB combined source bytes, 8,000 pixels on either
source dimension, and 25 million decoded pixels. Corrupt, truncated,
MIME-mismatched, unsupported, and animated inputs are rejected. EXIF
orientation is applied, transparency is flattened, the longest edge is reduced
to at most 1,600 pixels, metadata is cleared, and the provider receives an RGB
JPEG. Decode/normalization and the synchronous provider call run outside the
async request loop.

The visual provider receives normalized inline images at high detail with a
strict private schema, `store=false`, and a 2,048-token completion cap. A
result contains one to eight findings, each with a closed visible-evidence
category, bounded observation, and references only to submitted photo numbers.
The deterministic policy rejects claims of authenticity/counterfeit status,
ownership/stolen status, hidden/internal condition, and current market price,
while allowing qualified limitations and literal visible text.

Retry classification is deliberately bounded:

- non-retryable HTTP/client failures terminate after one request;
- network failures, timeouts, HTTP `429`, and selected `5xx` failures may
  receive a second attempt; and
- schema or evidence-policy failures may receive one corrective second attempt
  using only safe application-owned codes.

No operation exceeds two provider requests. The validated result remains React
state. It has no score, recommendation, or persistence fields and cannot alter
the stored text analysis. The application closes uploads after the request and
does not persist photos, Base64 data, or visual findings. The UI accurately
qualifies third-party processing rather than equating `store=false` with a
guarantee of zero provider retention.

## 9. Security and privacy design

Security is implemented as layered risk reduction rather than an absolute
claim.

### Identity and authorization

- Passwords are salted bcrypt hashes; plaintext passwords are neither stored
  nor logged by the password service.
- JWT bearer tokens use HS256 and a configured expiry (24 hours by default).
  Missing, malformed, expired, and unknown-user tokens fail with the same `401`
  boundary.
- Analysis, history, failed-listing, retry, capability, and visual routes
  require authentication. Ownership is applied in database queries, not only
  checked in the browser.
- Administrator access composes an additional role dependency. The application
  has no self-service admin promotion path; its analytics endpoint returns
  aggregates rather than raw listings.
- The browser clears its session token and authenticated state when any active
  request discovers an expired session.

The minimal authentication scope leaves password reset, account verification,
MFA, token refresh/rotation, and forced re-authentication before account deletion
as known future hardening work.

### URL preview and SSRF controls

The [URL-preview service](../../backend/app/services/listing_fetch.py) accepts
HTTP(S), resolves each hostname itself, rejects
non-global/private/loopback/link-local/multicast/reserved targets, connects to
the validated IP while retaining the original host for HTTP/TLS identity, and
manually repeats the process for each redirect. Redirects are capped at three.
The service accepts HTML only and bounds response bytes, total time, per-read
stall time, and concurrent fetches. These measures materially reduce DNS
rebinding, redirect-to-private-host, resource exhaustion, and non-HTML parsing
risk, but they are described as best-effort defenses rather than exhaustive
SSRF prevention.

### Provider and generated-data boundaries

- Provider inputs are treated as untrusted content, and provider output is
  untrusted until strict validation succeeds.
- Real-provider construction requires its key; Visual availability also
  requires explicit complete configuration.
- Provider tests use mocked transports and make no live provider requests.
- Safe error mappings avoid returning raw provider bodies.
- Visual uploads are normalized and stripped of metadata before provider use;
  the application does not persist source images or visual findings.
- Visual consent is per inspection. Provider-side processing remains subject to
  the applicable provider policy.

### Configuration and delivery controls

Runtime settings are environment-driven. Application runtime secrets belong in
the private EC2 `.env`; deployment credentials and target configuration belong
in GitHub Actions secrets, never source control. The repository’s deployment
instructions do not require printing them. The deploy path uses SSM rather than
inbound SSH, validates configuration before activation, uses commit-SHA images,
and waits for application health. Branch controls and required CI are described
in ADR-002. These are observable controls, not a claim that the environment is
invulnerable.

Two material security/operations limitations remain. CORS currently allows all
origins and should be restricted for a more hardened service. The text-provider
selector falls back to mock on an unknown value rather than failing startup.

## 10. Testing strategy and rationale

The testing design mirrors the risk boundaries: deterministic business rules
are tested directly; contracts are tested structurally; routes are tested over
HTTP; multi-step ownership and persistence behavior is tested as integration;
provider transports are mocked; and deployment has a separate runtime-health
gate. The practical commands and layer definitions are in the
[testing guide](../testing/README.md).

| Layer | Why it exists | Representative evidence |
|---|---|---|
| Unit tests | Localize failures in pure or narrow logic without a full request cycle | [`test_scoring.py`](../../backend/tests/test_scoring.py), [`test_listing_schema.py`](../../backend/tests/test_listing_schema.py), [`test_security.py`](../../backend/tests/test_security.py) |
| Strict parsing/schema tests | Prove malformed, ambiguous, oversized, contradictory, or extra provider data cannot be normalized silently | [`test_ai_response_validation.py`](../../backend/tests/test_ai_response_validation.py), [`test_contract.py`](../../backend/tests/test_contract.py) |
| API acceptance tests | Exercise routing, validation, authentication, status codes, persistence, and response shape together | [`test_api.py`](../../backend/tests/test_api.py), [`test_admin.py`](../../backend/tests/test_admin.py) |
| Integration tests | Catch state-threading defects across registration, login, submission, history, isolation, failure, and recovery | [`test_integration.py`](../../backend/tests/test_integration.py) |
| Security-focused tests | Exercise token failures, ownership, SSRF targets/redirects/deadlines, MIME spoofing, decompression limits, and safe errors | [`test_listing_fetch.py`](../../backend/tests/test_listing_fetch.py), [`test_visual_inspection_images.py`](../../backend/tests/test_visual_inspection_images.py) |
| Provider-boundary and failure-handling tests | Verify exact payload controls, transport outcomes, bounded attempts, safe failures, and no dependency on live credentials | [`test_ai_provider.py`](../../backend/tests/test_ai_provider.py), [`test_visual_inspection_openai.py`](../../backend/tests/test_visual_inspection_openai.py) |
| Evidence-policy tests | Preserve allowed uncertainty while rejecting known unsupported conclusion families | [`test_evidence_policy.py`](../../backend/tests/test_evidence_policy.py), [`test_visual_inspection.py`](../../backend/tests/test_visual_inspection.py) |
| Visual API tests | Verify auth/ownership, count/size/status contracts, capability behavior, event-loop offloading, transience, and score separation | [`test_visual_inspection_api.py`](../../backend/tests/test_visual_inspection_api.py), [`test_capabilities.py`](../../backend/tests/test_capabilities.py) |
| Frontend component/API tests | Catch client/API naming drift and user-state defects in consent, loading, capability hiding, retry isolation, theme, session expiry, and rendering | Nine test files under [`frontend/src`](../../frontend/src/) |
| Production build | Catch unresolved modules, JSX/build errors, and bundling failures not guaranteed to appear in component tests | `npm run build` in CI |
| Deployment health | Prove that the selected images started and a container-local request traversed Caddy, nginx, and FastAPI | [`deploy.yml`](../../.github/workflows/deploy.yml) and production Compose health check |

### 10.1 Determinism and isolation

`tests/conftest.py` unconditionally supplies a disposable SQLite database, mock
provider, and test JWT setting before application imports. This is necessary
because settings are cached: allowing an ambient developer configuration to win
could point a test at a real database or provider. HTTP provider tests inject
mock transports. Consequently automated CI/provider tests require no provider
credential and make no live provider requests.

The score tests assert tier ranges never overlap, repeated inputs yield the same
score, severity affects position within a tier, and saturation never exceeds
100. Contract tests independently pin the absence of a provider-generated
numeric score, provider protocol conformance, response round trips, and the
HTTP surface. These tests protect a design property, not only an example output.

### 10.2 Failure and negative-path emphasis

The suite tests invalid credentials and tokens, cross-user access, duplicate
accounts, malformed listing input, private/redirected URL targets, timeouts,
oversized responses, provider HTTP/network/timeout outcomes, malformed and
policy-invalid generated output, invalid images, MIME mismatch, decompression
bounds, unsupported visual claims, missing capability configuration, and
transient/non-persistent results. This emphasis is appropriate because the
system’s highest risks are unauthorized data access, unsafe remote fetching,
and untrusted generated output entering durable state.

### 10.3 What the automated suite does not prove

Most backend HTTP tests use SQLite rather than production PostgreSQL. Frontend
tests run in jsdom rather than a real browser. Provider-boundary tests use
mocked transports, not live provider behavior. There is no committed Playwright
suite driving the deployed application, no load test, and no automated proof of
public DNS/TLS reachability. Those gaps do not invalidate the covered behavior,
but they define the boundary of the evidence.

The testing guide contains older “planned coverage” and manual-evaluation
sections that predate parts of the final release. They remain chronological
records; the release CI results below are the current automated snapshot.

## 11. Final automated evidence for `v1.20.0`

[CI run 33678086754](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/33678086754)
executed against the immutable release source and recorded:

| Gate | Exact result |
|---|---|
| Contract selection | 70 passed, 379 deselected, 8 warnings |
| Complete backend suite | 449 passed, 140 warnings |
| Backend coverage | 96.49% |
| Required coverage floor | 85%; passed |
| Frontend suite | 76 passed across 9 test files |
| Frontend production build | Passed; 39 modules transformed |

The contract selection and full backend suite are separate signals: the former
makes contract regressions visible early, while the latter still exercises the
complete suite and enforces coverage. Coverage is treated as a floor rather than
proof of correctness. The frontend tests and build are separate for the same
reason: runtime interactions and bundling failures are different defect classes.

These exact counts are release evidence, not permanent documentation promises;
they should be updated only when a later immutable baseline replaces
`v1.20.0`.

## 12. Production validation and its boundary

Semantic-release published
[`v1.20.0`](https://github.com/Ranga-Schooling/trustai-marketplace/releases/tag/v1.20.0)
at the release commit. The automatic deployment and two later manual
reactivations of the same SHA succeeded. The latest recorded run,
[33687682316](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/33687682316),
reported the release-tagged backend/frontend images, healthy Caddy and
PostgreSQL containers, and a health pass on attempt 1 of 30.

The configured health check performs a request inside the Caddy container to
its local HTTP listener; that request passes through Caddy, nginx, and the
backend `/api/health` endpoint. It therefore establishes that the released
containers started and the internal application route worked. It does **not**
establish public DNS resolution, public TLS, logged-out browser behavior,
authentication through the public site, private host provider configuration,
or a successful OpenAI request.

Accordingly, the following remain OPEN until sanitized evidence is imported or
the checks are performed and recorded:

1. public logged-out reachability over the documented HTTPS domain;
2. a browser critical path through authentication, listing analysis, result,
   history, and recovery;
3. proof that private production configuration activated GPT-5.6 Terra and a
   successful Terra transaction traversed the deployed application; and
4. proof that Visual Inspection was privately enabled and completed a safe
   synthetic-photo transaction through the deployed UI.

The detailed boundary and safe evidence checklist are maintained in
[Final Production Validation](FINAL_PRODUCTION_VALIDATION.md). External or
private operational observations are not silently promoted to repository
evidence in this report.

## 13. Failure handling and resilience

TrustAI’s primary resilience choice is to preserve a useful and truthful state
rather than hide failure:

- **Listing first:** the listing transaction completes before text analysis.
  Provider failure therefore cannot erase what the user entered.
- **Recoverable failure:** a safe `502` identifies the retained listing; the
  owner can find it and retry without retyping it. Failure logs contribute safe
  aggregate analytics.
- **Bounded provider attempts:** the Terra and Visual paths cap one operation at
  two physical provider requests. Terra retries transient infrastructure/status
  failures only; Visual also permits one corrective response for schema or
  evidence-policy failure.
- **No partial acceptance:** strict parsing, contract validation, cross-field
  checks, and evidence policy must all pass before a generated text result is
  persisted.
- **Safe HTTP mapping:** deterministic client/provider failures do not receive
  unbounded retries, and provider prose is not returned as an application error.
- **Capability failure:** incomplete Visual configuration or a capability-fetch
  failure hides the optional feature rather than exposing a known-broken action.
- **Migration gate:** schema migration runs before the API starts. The migration
  wrapper repairs only a precisely matching pre-Alembic bootstrap and fails
  loudly on an ambiguous schema rather than guessing a revision.
- **Deployment gate:** Compose/Caddy validation, immutable image pulling, and
  internal health checks must pass before the workflow reports success.

Rollback is not automatic. An operator can reactivate previously known-good
immutable image tags through the deployment process; database volumes must be
preserved, and schema compatibility must be considered. Text-provider rollback
can select the mock provider and recreate the backend process, but this is an
operational configuration action rather than a runtime UI switch.

## 14. Deployment recommendation and trade-offs

For the completed Capstone, retaining the implemented AWS container deployment
is the most defensible recommendation. It is already reproducible from source,
uses identical application images across activations, keeps the API/database
off direct host ports, avoids inbound SSH for delivery, and records deployment
status in GitHub Actions. Replatforming immediately before submission would add
risk without improving the demonstrated product.

The design is not the lowest-operations option. A small team owns EC2 patching,
capacity, Docker lifecycle, PostgreSQL backup/restore, IAM, ECR retention,
monitoring, and manual rollback. The database’s named volume survives normal
container recreation but remains tied to one host/disk. The scheduled S3
workflow exists, yet current repository/GitHub evidence records its bucket
configuration as unresolved; backup and restore readiness is therefore not
claimed.

### 14.1 Relative cost and operations comparison

No authoritative billing record in the repository supports exact monthly
figures, so the comparison is qualitative.

| Option | Infrastructure cost drivers | Operational labor | Control and portability | Scaling model | Capstone assessment |
|---|---|---|---|---|---|
| Current EC2 + ECR + local PostgreSQL containers | Always-on VM compute, ECR image storage/transfer, disk, DNS/bandwidth, and optional backup storage | Highest of the three: host, containers, database, IAM, cleanup, backups, and rollback are team-owned | High control; standard containers/Compose are portable, although AWS automation is provider-specific | Primarily vertical/manual at this scale | Appropriate because it is implemented and verified at the container-health level; operations burden is the main cost |
| Managed PaaS-style frontend/API/database | Service tiers, managed database, bandwidth, and potential always-on/cold-start upgrades | Lower: platform owns more runtime, TLS, health, and database operations | Less infrastructure control; application containers remain portable but platform configuration changes | Platform-managed within purchased limits | This was the ADR-001 direction and could reduce maintenance, but migration now would discard proven AWS work |
| Simple VPS/container host | VM/disk/bandwidth, possibly no separate registry if built on-host | Medium to high: OS, TLS, deployment, database, backups, and monitoring remain team-owned | High portability and simple topology, with fewer managed controls | Usually vertical/manual | Potentially simpler billing/topology, but less auditable image delivery and no inherent reduction in database responsibility |

Managed services may trade a higher service premium for lower engineering labor;
raw infrastructure may appear cheaper while shifting cost into maintenance and
risk. For a longer-lived product, moving PostgreSQL to a managed service and
adopting short-lived CI cloud credentials would be stronger next steps than
adding application features.

## 15. Engineering trade-offs and known limitations

The most material limitations are architectural rather than cosmetic:

- **No authoritative current-market research.** Text analysis and URL preview
  operate on supplied/extracted content; they do not verify live market prices.
- **Generated analysis remains fallible.** Strict structure and bounded evidence
  policies reject known failures but cannot guarantee factual completeness or
  detect every scam.
- **Visual scope is intentionally narrow.** It considers only uploaded images,
  cannot certify authenticity/ownership/hidden condition, and does not alter the
  Trust score. The application does not persist images/findings; provider-side
  handling remains subject to provider policy.
- **Private production activation is not repository-evidenced.** Source defaults
  show the Terra path, but private `.env` contents and successful deployed
  provider calls remain OPEN.
- **Provider switching is deployment-time.** Changing the text provider requires
  configuration and process recreation; the admin analytics endpoint does not
  change provider settings.
- **Backup recovery is unresolved.** The backup workflow fails closed when its
  bucket configuration is absent, and restore readiness is not established.
- **Single-host state and manual rollback.** PostgreSQL and the application run
  on one EC2 host; no automatic failover or rollback exists.
- **Development-oriented CORS.** All origins are currently permitted.
- **Authentication is intentionally minimal.** Password recovery/verification,
  MFA, refresh-token rotation, and account-delete re-authentication are absent.
- **Testing substitutions remain.** Automated API tests principally use SQLite,
  browser tests use jsdom, provider calls are mocked, and no committed deployed
  browser E2E suite exists.
- **URL preview is best effort.** HTML extraction and bounded SSRF controls do
  not guarantee support for every marketplace or eliminate all remote-fetch risk.

The non-production Gemini default is also tracked for future maintenance; it is
not the selected Terra production path. The provider-neutral research in
[PR #103](https://github.com/Ranga-Schooling/trustai-marketplace/pull/103)
remains research provenance and was intentionally not merged wholesale.

## 16. Why this design is appropriate for the Capstone

The final system demonstrates an end-to-end software-engineering argument
rather than an isolated model demo. User stories connect to authenticated UI
and API behavior; Pydantic and database schemas establish explicit contracts;
provider adapters isolate external protocols; deterministic application logic
keeps score and recommendation semantics testable; and negative-path tests
exercise ownership, SSRF, malformed model output, unsafe evidence, image
handling, and provider failure.

The implementation also documents meaningful evolution. The team challenged
inconsistent stories against architecture, changed deployment platforms when
the implementation moved to AWS, added migrations and recovery after concrete
integration failures, and strengthened AI acceptance from prompt instructions
to strict deterministic gates. Git/PR history establishes those engineering
changes; it should not be used as proof that undocumented meetings occurred or
that every planned ceremony was completed.

Finally, the release and deployment path connects reviewed source to an
immutable artifact and a recorded runtime-health check. The report keeps the
remaining validation boundary visible: live public/browser and provider proof
must still be supplied separately. That combination—working software,
traceable decisions, bounded AI behavior, security/privacy controls, layered
tests, immutable delivery, and honest limitations—is the relevant Capstone
evidence.

## 17. Traceability and remaining OPEN evidence

| Evidence question | Current status | Primary source |
|---|---|---|
| What was delivered and deliberately deferred? | IMPLEMENTED/RELEASED traceability | [Backlog](../BACKLOG.md), [Changelog](../../CHANGELOG.md) |
| Why were key boundaries chosen? | DOCUMENTED chronology | [Design notes](../DESIGN_NOTES.md), [ADRs](../decisions/) |
| What is the final release? | VERIFIED | [`v1.20.0`](https://github.com/Ranga-Schooling/trustai-marketplace/releases/tag/v1.20.0) |
| Did automated gates pass? | VERIFIED | [CI run 33678086754](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/33678086754) |
| Did the released stack pass configured deployment health? | VERIFIED, container-local boundary | [Deployment run 33687682316](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/33687682316) |
| Is the public browser critical path verified? | OPEN | [Final Production Validation](FINAL_PRODUCTION_VALIDATION.md) |
| Is Terra active and successful through deployed production? | OPEN in repository evidence | [Final Production Validation](FINAL_PRODUCTION_VALIDATION.md) |
| Is Visual Inspection active and successful through deployed production? | OPEN in repository evidence | [Final Production Validation](FINAL_PRODUCTION_VALIDATION.md) |
| Are backup and restore operationally verified? | OPEN | [Issue #88](https://github.com/Ranga-Schooling/trustai-marketplace/issues/88) |
| Are meeting, sprint, Trello, presentation, handbook-source, agreement, and grader-access artifacts indexed? | OPEN/PARTIAL | [Capstone portal](README.md), [Rubric matrix](RUBRIC_EVIDENCE_MATRIX.md) |

The Quantic handbook requirements recorded in the rubric matrix are treated as
authoritative project requirements based on Product Owner review. Exact page
references and evidence ownership are indexed in
`HANDBOOK_REQUIREMENTS_INDEX.md`; the authoritative Handbook PDF remains an
external submission source rather than a repository artifact.
