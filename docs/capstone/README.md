# TrustAI Marketplace Project Documentation

This directory indexes the design, testing, delivery and process records for
TrustAI Marketplace, and points to the implementation and historical records
that support them.

## Project at a glance

TrustAI Marketplace is a deployed, authenticated web application that helps a
buyer review an online marketplace listing before proceeding with a purchase.
It returns a structured risk assessment, deterministic Trust score, qualitative
price-plausibility assessment, recommendation, and questions for the seller.
An optional Visual Inspection channel evaluates user-selected photos separately
from the text result and does not change the Trust score or recommendation.

TrustAI is decision support, not a guarantee that a listing, product, or seller
is legitimate. It does not independently establish ownership, authenticity,
hidden condition, or a verified current market price.

## Final release and access

| Item | Evidence status | Location |
|---|---|---|
| Final application release used for submission | **VERIFIED** — `v1.21.0` | [GitHub release](https://github.com/Ranga-Schooling/trustai-marketplace/releases/tag/v1.21.0) |
| Immutable application-release commit | **VERIFIED** — `9eb7253e47cd54dd7a3084ce47c0df1747d16948` | [Commit](https://github.com/Ranga-Schooling/trustai-marketplace/commit/9eb7253e47cd54dd7a3084ce47c0df1747d16948) |
| Historical production-validation baseline | **VERIFIED** — `v1.20.0` | [Final production validation](FINAL_PRODUCTION_VALIDATION.md) |
| Source repository | **VERIFIED PUBLIC** | [Ranga-Schooling/trustai-marketplace](https://github.com/Ranga-Schooling/trustai-marketplace) |
| Quantic repository access | **VERIFIED** — `quantic-grader` has read access | [Source repository](https://github.com/Ranga-Schooling/trustai-marketplace) |
| Documented production URL | **VERIFIED** — logged-out HTTPS/browser reachability checked on 2026-09-04 | [https://trustai.mandalawi.ca](https://trustai.mandalawi.ca) |
| Agile task board | **VERIFIED** — readable without signing in | [TrustAI Marketplace Trello board](https://trello.com/b/wUqCGA2T/trustai-marketplace-sprint-retrospective-board) |
| Sprint demonstrations | **VERIFIED** — Sprint 1 and Sprint 2 recordings | [Sprint demonstration recordings](sprints/README.md#sprint-demonstration-recordings) |
| Final presentation | **COMPLETED** — 19:58 | [Final Capstone Presentation (19:58) — Google Drive](https://drive.google.com/file/d/12FEx0J6LJ7DSQhFx62VkCf6raG5ijkon/view?usp=sharing). For the original 4K-quality video, download the file from Google Drive; browser playback may use a lower-resolution stream. |
| Submission closeout | **SUBMITTED** — September 13 | [Submission closeout](SUBMISSION_CLOSEOUT.md) |

## Delivered product evidence

The implemented story-level traceability is in the
[user-story backlog](../BACKLOG.md). The final release includes:

- registration, sign-in, authenticated profile update, and account deletion;
- owner-scoped listing analysis and history;
- manual listing entry plus guarded URL preview and best-effort field extraction;
- structured text analysis with strict response parsing, schema validation,
  cross-field validation, and evidence-policy checks;
- a server-computed, deterministic 0–100 Trust score that is not supplied by
  the language model;
- qualitative price plausibility without claiming independently verified
  current market value;
- failed-listing recovery and per-listing retry state;
- dark, light, and system theme preferences and responsive layouts;
- optional, capability-gated Visual Inspection with explicit consent, bounded
  image validation, and no application persistence of photos or findings;
- admin-only aggregate analytics with no self-service privilege escalation; and
- containerized deployment with release automation and health gating.

## Evidence map

| Area | Primary evidence | What it establishes |
|---|---|---|
| Submission closeout | [Submission closeout](SUBMISSION_CLOSEOUT.md) | Final presentation identity, access, reported submission chronology, Agreement privacy boundary and post-submission documentation changes |
| AI disclosure | [AI disclosure](AI_DISCLOSURE.md) | Project-level AI-assisted development scopes, review automation, product-model boundaries and privacy-safe reference handling |
| Requirements and delivery | [Backlog](../BACKLOG.md) | User stories, acceptance criteria, implementation pointers, and deliberate deferrals |
| Project evolution | [Project timeline](PROJECT_TIMELINE.md) | Chronological separation of planning, implementation, hardening, and release |
| Architecture and decisions | [Design notes](../DESIGN_NOTES.md), [architecture artifacts](../architecture/), [ADRs](../decisions/) | Architectural boundaries, decisions, alternatives, and historical context |
| Detailed design/testing report | [Capstone design and testing report](CAPSTONE_DESIGN_AND_TESTING.md) | Final architecture and technology rationale, design patterns, testing methods and rationale, deployment recommendation, and bounded relative deployment-cost analysis |
| Testing | [Testing guide](../testing/README.md), [CI workflow](../../.github/workflows/ci.yml) | Test layers, commands, deterministic provider isolation, and the 85% coverage gate |
| CI/CD and deployment | [Pipeline guide](../ci-cd/zero-trust-pipeline.md), [deploy workflow](../../.github/workflows/deploy.yml), [production Compose](../../deploy/docker-compose.yml) | ECR images, SSM deployment, immutable commit tags, migrations, HTTPS, and health checks |
| Production validation | [Final production validation](FINAL_PRODUCTION_VALIDATION.md) | Release, CI, deployment, public-browser reachability, Terra-labelled text results, history, Visual Inspection, and remaining evidence boundaries |
| Final presentation | [Presentation runbook](PRESENTATION_RUNBOOK.md), [submission closeout](SUBMISSION_CLOSEOUT.md) | Five-person rehearsal plan and the later final recording/submission state |
| AI/model decision | [D-21](../DESIGN_NOTES.md), [research PR #103](https://github.com/Ranga-Schooling/trustai-marketplace/pull/103) | Why Terra was selected for the Capstone production workload; research history remains separate from production |
| Team meetings | [Meeting index](meetings/README.md) | Six authoritative PDFs covering seven dated meetings, with source-grounded chronology and evidence boundaries |
| Sprint/process evidence | [Sprint history](sprints/README.md), [Git workflow](../GIT_WORKFLOW.md) | July planning baseline, actual Git/PR/release progression, carryover, and the Sprint 1 and Sprint 2 demonstration recordings |
| Agile task board | [Trello board](https://trello.com/b/wUqCGA2T/trustai-marketplace-sprint-retrospective-board) | Public final board covering delivered, deferred, superseded and cancelled work, with retrospective closeout items clearly identified |

The backlog, design notes, architecture artifacts, ADRs, and testing guide are
chronological engineering records and contain some planning or pre-release
state. They are preserved rather than rewritten. Use this portal and the
[submission closeout](SUBMISSION_CLOSEOUT.md) for the current submission state,
and the [final production validation](FINAL_PRODUCTION_VALIDATION.md) for the
historical `v1.20.0` validation boundary. ADR-001 remains evidence of the original
Render decision before the implementation later evolved to AWS. The final AWS
path is recorded retrospectively in
[ADR-003](../decisions/ADR-003-aws-ec2-deployment.md).

## Architecture summary

The final implementation uses React with JavaScript/JSX and Vite in the
browser, FastAPI and Pydantic in the API, SQLAlchemy/Alembic with PostgreSQL,
and provider adapters behind a shared analysis contract. Production runs as
Docker Compose services on AWS EC2. Caddy terminates HTTPS, nginx serves the
frontend and proxies `/api`, GitHub Actions publishes SHA-tagged images to ECR,
and AWS Systems Manager activates the selected commit without inbound SSH.

The initial Render decision in ADR-001 is retained as historical evidence. The
implemented AWS architecture is documented by ADR-003, the current Compose and
workflow definitions, and the CI/CD guide.

The final application release, `v1.21.0`, added the D-22 cross-origin and
per-user provider-spend bounds after the `v1.20.0` production-validation
baseline. Documentation-only PRs #116 and #117 landed after the September 13
submission; current `main` may therefore be newer without representing a newer
application release.

## Testing and release evidence

For release `v1.20.0`, [CI run 33678086754](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/33678086754)
recorded:

- 70 contract tests passed;
- 449 backend tests passed;
- 96.49% backend coverage against an 85% gate;
- 76 frontend tests passed across 9 files; and
- a successful frontend production build.

[Deployment run 33687682316](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/33687682316)
subsequently activated the immutable release SHA and passed the Caddy-to-
backend health gate. These records prove automated and deployment health. They
do not, by themselves, prove a live provider transaction or complete browser
E2E walkthrough. A separate September 4 controlled browser check recorded the
live application-level text, history, and Visual outcomes in the
[production validation record](FINAL_PRODUCTION_VALIDATION.md).

For final application release `v1.21.0`,
[CI run 34706000817](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/34706000817)
recorded 70 contract tests, 457 backend tests at 96.52% coverage, 76 frontend
tests across 9 files, and a successful frontend production build. This later
run establishes the automated state of the D-22-hardened release; it does not
rewrite the earlier production-validation observations as `v1.21.0` evidence.

## Known limitations and deferred work

- TrustAI does not perform comprehensive live marketplace-price research, so
  price plausibility is qualitative and bounded by supplied evidence.
- Listing URL preview is best-effort HTML extraction, not a marketplace API
  integration.
- Visual Inspection is advisory, inspects only uploaded photos, and cannot
  establish authenticity, ownership, or hidden/internal condition.
- Visual photos and findings are not persisted by the TrustAI application in
  V1; provider-side handling is governed by the provider's applicable data
  policy.
- Authentication intentionally omits password reset, email verification, MFA,
  and refresh-token rotation.
- Runtime AI-provider switching requires deployment configuration and process
  restart; the admin analytics endpoint does not expose secrets or change
  providers.
- Production backup recovery remains operationally OPEN under
  [issue #88](https://github.com/Ranga-Schooling/trustai-marketplace/issues/88).
- The non-production Gemini default is tracked for replacement under
  [issue #97](https://github.com/Ranga-Schooling/trustai-marketplace/issues/97).

## Evidence-handling rule

Only committed source, Git/GitHub records, approved project artifacts, and
observed validation results count as evidence. Credentials, authorization
headers, raw provider bodies, personal test data, and private operational
records do not belong in this package.
