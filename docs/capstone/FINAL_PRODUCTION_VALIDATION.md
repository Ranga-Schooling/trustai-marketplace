# Final Production Validation — TrustAI Marketplace v1.20.0

## Scope and evidence standard

This record separates release/deployment evidence from a controlled,
secret-free browser validation performed on September 4, 2026. A green
deployment health check proves that the released containers started and that a
container-local request traversed Caddy, nginx, and the backend health
endpoint. It does not establish public DNS, TLS, browser, or provider behavior;
the later browser observations below establish only their explicitly stated
boundaries.

No credential value, credential fingerprint, authorization header, raw
provider response, or personal test data belongs in this document.

## Release identity

| Field | Value | Status |
|---|---|---|
| Release | [`v1.20.0`](https://github.com/Ranga-Schooling/trustai-marketplace/releases/tag/v1.20.0) | VERIFIED |
| Commit | [`5ebc757ba66ff647944602245c18bedf6631680e`](https://github.com/Ranga-Schooling/trustai-marketplace/commit/5ebc757ba66ff647944602245c18bedf6631680e) | VERIFIED |
| Release timestamp | 2026-09-02 20:14:27 UTC | VERIFIED |
| Documented domain | [https://trustai.mandalawi.ca](https://trustai.mandalawi.ca) | VERIFIED in a logged-out browser on 2026-09-04 |
| Repository | [Ranga-Schooling/trustai-marketplace](https://github.com/Ranga-Schooling/trustai-marketplace) | VERIFIED PUBLIC |

## Automated release validation

[CI run 33678086754](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/33678086754)
ran against the immutable release commit and recorded:

| Gate | Result |
|---|---|
| Contract selection | 70 passed; 379 deselected; 8 warnings |
| Complete backend suite | 449 passed; 140 warnings |
| Backend coverage | 96.49% |
| Required backend gate | 85% — passed |
| Frontend tests | 76 passed in 9 test files |
| Frontend production build | Passed; 39 modules transformed |

The automated test environment uses deterministic/mocked provider boundaries;
the CI result is not evidence of a provider charge or live provider behavior.

## Deployment evidence

The release was activated by the repository's production deployment workflow:

| Run | Trigger | Result | Evidence |
|---|---|---|---|
| [33678086731](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/33678086731) | Push of the release commit | Success | Activated release SHA and passed health |
| [33686287354](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/33686287354) | Manual dispatch | Success | Reactivated the same SHA and passed health |
| [33687682316](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/33687682316) | Manual dispatch | Success | Latest recorded activation of the same SHA; health passed on attempt 1/30 |

The latest run reports backend and frontend images tagged
`5ebc757ba66ff647944602245c18bedf6631680e`, healthy Caddy and PostgreSQL
containers, successful Compose validation, and successful post-deploy cleanup.
No newer application deployment was used as evidence for this record.

## Production architecture validated by the deployment

The deployed release consists of:

1. Caddy on ports 80/443 for HTTPS and public reverse proxying.
2. An nginx-served React application behind Caddy.
3. A FastAPI backend reachable only through the internal Compose network.
4. PostgreSQL 16 with a persistent Docker volume.
5. Alembic migration execution before Uvicorn starts.
6. Backend and frontend images built in GitHub Actions, stored in ECR, and
   activated by immutable commit SHA.
7. AWS Systems Manager Run Command for deployment without inbound SSH.
8. Compose, Caddy, image-pull, and full Caddy-to-backend health gates before a
   deployment is declared successful.

The deploy workflow does not provide automatic rollback. It preserves the
database volume and does not run `docker compose down -v`.

## Terra production text path

### Established by committed source

- `AI_PROVIDER=gpt` selects the production OpenAI adapter.
- The repository's default OpenAI model setting for this path is
  `gpt-5.6-terra`.
- The adapter uses `POST https://api.openai.com/v1/responses`.
- Prompt version is `v4`.
- The request asks for strict JSON Schema output, medium reasoning, a maximum
  of 2,048 output tokens, no storage, no streaming, disabled truncation, and
  no tools/search.
- The response must pass strict UTF-8 JSON parsing, duplicate-key/resource
  checks, exact shape validation, Pydantic validation, deterministic cross-
  field validation, and the evidence-policy gate.
- Only timeouts, transport failures, and HTTP 429/500/502/503/504 may use the
  second and final production attempt. Deterministic, configuration, contract,
  security, and other HTTP failures are terminal.
- The public `AIAnalysisResult` contract, deterministic Trust score, database
  response, and frontend result shape remain stable.

### Established by the September 4 browser validation

- An authorized non-personal demo account completed three synthetic listing
  analyses through the deployed UI.
- The benign case returned `Buy`, Trust score `4`, and `Plausible`; the
  suspicious case returned `Avoid`, Trust score `100`, and `Too good to be
  true`; the recent-product case returned `Buy`, Trust score `4`, and
  `Plausible` without claiming a verified current price.
- Every result rendered the text-only and model-knowledge limitations,
  structured risk indicators, seller questions, and the application-visible
  label `Model used: gpt-5.6-terra`.
- The three analyses appeared newest-first in authenticated history, and a
  reopened result materially matched its original result.

**Live Terra E2E status: VERIFIED at the deployed application boundary.** The
successful browser transactions and application-reported model label prove
that the deployed application returned Terra-labelled structured results. The
private host `.env`, provider request/response bodies, and provider endpoint
were not inspected, so this record does not independently attest those private
transport details.

## Visual Inspection path

### Established by committed source

- Visual Inspection is an authenticated endpoint on an existing analysis.
- The server exposes only `visual_inspection_available` through the
  authenticated capability endpoint.
- Availability requires the supported `openai` provider plus non-empty
  configured key and model values. The capability endpoint does not validate
  the credential or provider-side model usability; those can be established
  only by an attempted provider request.
- The frontend hides the feature on unavailable or failed capability fetch.
- Users must explicitly consent before uploading one to three JPEG, PNG, or
  WebP images.
- Per-image and aggregate source-byte limits, format checks, dimension/pixel
  limits, animation rejection, metadata stripping, and normalization precede
  provider processing.
- The provider request uses strict structured output and `store=false`.
- Photos and Visual Inspection findings are not persisted by the TrustAI
  application; request-scoped uploads are closed after processing.
  Provider-side handling is governed by the provider's applicable data policy.
- Findings are advisory and cannot change the original risk result, Trust
  score, or recommendation.
- The nginx 11 MiB allowance is scoped only to the Visual Inspection route.

### Established by the September 4 browser validation

- Visual Inspection was visible on an authenticated completed analysis.
- Before consent, the submit control remained disabled. The user-authorized
  test selected one synthetic 640×480 PNG and explicitly enabled consent.
- The deployed Visual flow completed and returned one advisory, photo-grounded
  observation: Photo 1 visibly contained the words `DEMO UNIT`.
- The original Trust score (`4`), risk level (`low`), recommendation (`Buy`),
  and price-plausibility result (`Plausible`) remained unchanged.
- The UI displayed the authenticity/ownership/hidden-condition and current-
  price limitations, identified OpenAI as the photo recipient, and exposed no
  provider raw body.
- After navigation through History and reopening the analysis, the text result
  remained but the Visual finding did not; a fresh upload form was shown.

**Live Visual E2E status: VERIFIED at the deployed application boundary.** The
application-visible disclosure establishes OpenAI as the photo recipient, but
the exact Visual model was not exposed and therefore remains unverified. The
non-persistence observation applies to the TrustAI application; provider-side
handling remains governed by the applicable provider policy.

## September 4 public-browser and critical-path record

The controlled validation used only synthetic, non-sensitive data and retained
no credential, session material, authorization header, or provider raw body.

| Boundary | Result |
|---|---|
| Public DNS | Resolved to the production host during the validation |
| HTTP to HTTPS | `308` redirect to the canonical HTTPS URL |
| HTTPS/browser | HTTP `200`; certificate accepted by the browser; no certificate or mixed-content warning observed |
| Logged-out application | Sign-in/register surface rendered without an immediate 4xx/5xx |
| Authentication | User-assisted sign-in with an authorized non-personal account; authenticated shell and session-after-reload verified |
| Account view | Profile fields and save/delete controls present; values were not recorded and no change was made |
| Text analysis | Three synthetic analyses completed and rendered structured results |
| History | Three results persisted newest-first; reopened result matched materially |
| Visual Inspection | One synthetic-image inspection completed after consent; score/recommendation separation and application-level non-persistence verified |
| Responsive views | Authenticated form, result, history, navigation, and Visual areas showed no horizontal overflow at desktop and a 390×844 viewport override (354-pixel document client width) |
| Themes | Light and dark were legible; light is recommended for projected presentation; the original dark state was restored |
| Browser console | No warning or error entry observed during the controlled flows |

Remaining browser boundaries are explicit: registration was not repeated;
logout/relogin was not attempted because the validation agent did not receive
credentials; failed-listing recovery was not forced; logged-out mobile layout
was not rechecked; exact provider physical-attempt counts and private transport
details were not browser-observable.

## Failure handling and rollback

- Provider failures are mapped to safe application-owned messages; raw
  provider errors are not returned to users.
- A failed text analysis preserves the listing and makes it available for an
  owner-scoped retry from History.
- Non-retryable Visual HTTP/client failures terminate after one request.
  Network failures, timeouts, HTTP 429, and selected 5xx failures may receive
  a bounded second attempt. Schema or evidence-policy failures may also receive
  one corrective second attempt. No Visual operation exceeds two provider
  requests.
- Unknown/missing Visual configuration hides the capability and fails closed.
- Text-provider rollback is a private configuration change to
  `AI_PROVIDER=mock` followed by process recreation; existing persisted
  analyses require no rewrite.
- Application rollback uses a previously known-good immutable release SHA via
  the normal deploy workflow. Database volumes must not be deleted.
- Because the deploy workflow has no automatic rollback, the operator must
  preserve the previous configuration and release identity before activation.

## Known production limitations

- The product does not retrieve authoritative current market pricing during
  text analysis.
- URL preview is bounded best-effort extraction rather than a guaranteed
  marketplace integration.
- Visual Inspection cannot certify authenticity, ownership, or hidden/internal
  condition. Photos and findings are not persisted by the TrustAI application;
  provider-side handling is governed by the provider's applicable data policy.
- Runtime provider switching is not implemented; configuration changes require
  process restart.
- Password reset, email verification, MFA, and refresh-token rotation are out
  of scope.
- The scheduled PostgreSQL backup workflow currently fails closed because the
  required bucket configuration is absent; recovery verification remains open
  under [issue #88](https://github.com/Ranga-Schooling/trustai-marketplace/issues/88).
- Production-scale load testing and a browser-automation suite are not part of
  the recorded release evidence.

## Validation conclusion

| Question | Answer |
|---|---|
| Is `v1.20.0` an immutable, tested release? | **YES** |
| Did release CI pass? | **YES** |
| Was the release activated and health-gated successfully? | **YES** |
| Does the release contain the final Terra and Visual architectures? | **YES** |
| Was the public HTTPS application verified from a logged-out browser? | **YES — 2026-09-04** |
| Does repository evidence expose private provider configuration? | **NO — intentionally not inspected** |
| Does the controlled browser record prove live Terra-labelled text and Visual application flows? | **YES, at the application boundary** |
| Does it independently prove provider transport details or the exact Visual model? | **NO** |
| Is production backup/recovery fully verified? | **NO — OPEN, issue #88** |

The defensible final statement is: **TrustAI Marketplace v1.20.0 passed its
automated quality gates and was deployed successfully by immutable SHA. The
September 4 controlled browser validation verified public HTTPS reachability,
Terra-labelled structured text analyses, authenticated history, and a
successful application-non-persistent Visual Inspection without changing the
original score or recommendation. Private transport details, the exact Visual
model, and backup recovery remain outside the proven boundary.**
