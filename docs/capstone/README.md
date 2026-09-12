# TrustAI Marketplace Capstone Evidence Portal

This directory is the grader-facing evidence index for the TrustAI Marketplace
Quantic MSSE Capstone. It points to the authoritative implementation and
historical records without treating plans as proof that work was delivered.
The [Handbook requirements index](HANDBOOK_REQUIREMENTS_INDEX.md) identifies the
audited assignment source and exact PDF pages; the
[requirements/evidence matrix](RUBRIC_EVIDENCE_MATRIX.md) is the authoritative
submission-control view derived from it.

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
| Final production release | **VERIFIED** — `v1.20.0` | [GitHub release](https://github.com/Ranga-Schooling/trustai-marketplace/releases/tag/v1.20.0) |
| Immutable release commit | **VERIFIED** — `5ebc757ba66ff647944602245c18bedf6631680e` | [Commit](https://github.com/Ranga-Schooling/trustai-marketplace/commit/5ebc757ba66ff647944602245c18bedf6631680e) |
| Source repository | **VERIFIED PUBLIC** | [Ranga-Schooling/trustai-marketplace](https://github.com/Ranga-Schooling/trustai-marketplace) |
| Documented production URL | **VERIFIED** — logged-out HTTPS/browser reachability checked on 2026-09-04 | [https://trustai.mandalawi.ca](https://trustai.mandalawi.ca) |
| Agile task board | **PARTIAL** — the [canonical board](https://trello.com/b/wUqCGA2T) and final closeout state are verified; the board is Private and no grader member was present during the access audit | Make the board link accessible to the grader and verify access before submission; the Handbook does not prescribe public visibility or a named Trello account |
| Final presentation | **OPEN** — the [runbook](PRESENTATION_RUNBOOK.md) is ready with human confirmations; recording/hosting/submission have not occurred | Add the reviewed recording link only after it exists |

The repository is public, but the Handbook separately requires sharing it with
the named `quantic-grader` account (Handbook PDF pp. 4 and 8). That access step
is still OPEN; the current collaborator lookup does not find the account. The
Handbook does not state the required permission level or retention period.

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
| Authoritative assignment source | [Handbook requirements index](HANDBOOK_REQUIREMENTS_INDEX.md) | Source identity, page convention, required deliverables, process rules, presentation/submission requirements, and maximum-score criteria |
| Requirements and delivery | [Backlog](../BACKLOG.md) | User stories, acceptance criteria, implementation pointers, and deliberate deferrals |
| Project evolution | [Project timeline](PROJECT_TIMELINE.md) | Chronological separation of planning, implementation, hardening, and release |
| Architecture and decisions | [Design notes](../DESIGN_NOTES.md), [architecture artifacts](../architecture/), [ADRs](../decisions/) | Architectural boundaries, decisions, alternatives, and historical context |
| Detailed design/testing report | [Capstone design and testing report](CAPSTONE_DESIGN_AND_TESTING.md) | Final architecture and technology rationale, design patterns, testing methods and rationale, deployment recommendation, and bounded relative deployment-cost analysis |
| Testing | [Testing guide](../testing/README.md), [CI workflow](../../.github/workflows/ci.yml) | Test layers, commands, deterministic provider isolation, and the 85% coverage gate |
| CI/CD and deployment | [Pipeline guide](../ci-cd/zero-trust-pipeline.md), [deploy workflow](../../.github/workflows/deploy.yml), [production Compose](../../deploy/docker-compose.yml) | ECR images, SSM deployment, immutable commit tags, migrations, HTTPS, and health checks |
| Production validation | [Final production validation](FINAL_PRODUCTION_VALIDATION.md) | Release, CI, deployment, public-browser reachability, Terra-labelled text results, history, Visual Inspection, and remaining evidence boundaries |
| Final presentation plan | [Presentation runbook](PRESENTATION_RUNBOOK.md) | Five-person roles, exact 17:30 timing, deployed demo sequence, fallbacks, rehearsal, Handbook controls, and post-recording QA |
| AI/model decision | [D-21](../DESIGN_NOTES.md), [research PR #103](https://github.com/Ranga-Schooling/trustai-marketplace/pull/103) | Why Terra was selected for the Capstone production workload; research history remains separate from production |
| Team meetings | [Meeting index](meetings/README.md) | Six authoritative PDFs covering seven dated meetings, with source-grounded chronology and evidence boundaries |
| Sprint/process evidence | [Sprint history](sprints/README.md), [Git workflow](../GIT_WORKFLOW.md) | July planning baseline, actual Git/PR/release progression, carryover, sprint drift, and missing ceremony/demo boundaries |
| Agile task board | [Canonical Trello board](https://trello.com/b/wUqCGA2T) | Active/Done/deferred/cancelled work reconciled against `v1.20.0` during submission closeout; historical drift and late reconciliation remain explicit |
| Rubric closure | [Authoritative requirements/evidence matrix](RUBRIC_EVIDENCE_MATRIX.md) | Handbook-page-grounded PASS/PARTIAL/OPEN status and remaining submission actions |

The backlog, design notes, architecture artifacts, ADRs, and testing guide are
chronological engineering records and contain some planning or pre-release
state. They are preserved rather than rewritten. Use this portal and the
[final production validation](FINAL_PRODUCTION_VALIDATION.md) record for the
final-release synthesis, while retaining ADR-001 as evidence of the original
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

## Final submission checklist

- [x] Public GitHub repository identified.
- [x] Final release and immutable commit identified.
- [x] Automated CI and deployment-health evidence linked.
- [x] Authoritative Handbook, requirements, architecture, testing, process, and timeline indexes created.
- [x] Verify the production URL from a logged-out browser and record the result.
- [x] Import and index the six authoritative meeting records without changing their historical content.
- [x] Reconcile the external Project Management Plan and Sprint Backlog planning baselines against actual Git/PR/release history without importing them.
- [ ] Locate and verify any authentic TrustAI sprint-end working-software demonstration recordings; the Handbook requires one at every sprint end for the Product Owner's sprint review, but does not state that these recordings are final-submission links.
- [x] Reconcile the final Trello state against `v1.20.0` and add the canonical board URL.
- [ ] Make the Private Trello board accessible to the grader and independently verify access. Membership is the minimally disruptive option, but the Handbook does not prescribe a specific Trello account or public visibility.
- [x] Complete the final-release [design and testing report](CAPSTONE_DESIGN_AND_TESTING.md).
- [x] Record a secret-free final Terra-labelled text and Visual application-level E2E validation with its evidence boundaries.
- [x] Author the final presentation runbook with exact timing, five-person participation, demo fallbacks, rehearsal, and Handbook QA controls.
- [ ] Resolve or explicitly accept the production-backup limitation in issue #88.
- [ ] Share the repository with `quantic-grader` and verify the account's access.
- [ ] Locate and verify the final Group Project Agreement page completed and signed by every member.
- [ ] Close the runbook's recording-role/demo-state confirmations, verify the Agreement and signatures, rehearse, then record one 15–20 minute all-member presentation, complete the required government-ID checks, host the compliant video on Google Drive with link-view access, and submit its link.
- [ ] Confirm the designated group submitter and complete the final link/access audit.

## Evidence-handling rule

Only committed source, Git/GitHub records, approved project artifacts, and
observed validation results count as evidence. Credentials, authorization
headers, raw provider bodies, personal test data, and private operational
records do not belong in this package.
