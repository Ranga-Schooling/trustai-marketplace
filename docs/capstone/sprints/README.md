# TrustAI Marketplace — Sprint History and Evidence Index

## Purpose and evidence boundary

This index reconstructs TrustAI's delivery history without converting plans
into proof of completion. The original Project Management Plan v1.1 and Sprint
Backlog workbook establish the intended sprint model. The canonical meeting
records establish what the team discussed, reviewed, assigned, or reported at
specific points. Git commits, merged pull requests, tests, tags, releases, and
deployment records establish the engineering work that entered the repository.

These sources do not carry the same evidentiary weight:

- **Planned** means the item appears in the July planning artifacts.
- **Meeting-confirmed** means a canonical record documents the discussion or
  reported state at that time.
- **Implemented** means source and tests entered the release history.
- **Released** means semantic-release tagged the corresponding `main` state.
- **Unverified** means the expected artifact or independent evidence has not
  been located.

No dedicated TrustAI sprint-end working-software demonstration recording has
been verified. Meeting records, architectural walkthroughs, release-readiness
discussions, and presentation rehearsals are not relabeled as sprint demos.

The confirmed final roster and official names are recorded in the
[meeting-evidence name reconciliation](../meetings/README.md#name-reconciliation).
Historical planning forms such as “Ranga Nyamadzawo,” “Adrian Muchatibaya,”
and “Samar El Ghandour” remain below where the source plan used them; they map
to Rangarirai Revivalist Nyamadzawo, Adrin Kudakwashe Muchatibaya, and Samar
Salah Elghandour respectively.

The authoritative Handbook requires a recorded working-software demonstration
at the end of each sprint, provided to the Product Owner for sprint review
(Handbook PDF pp. 7 and 10). It does not say those sprint recordings must be
linked or uploaded with the final submission. The Handbook does not make
retrospectives, daily standups, a fixed sprint length, or a formal Definition
of Done mandatory; references to those below describe TrustAI's own planning
conventions or the historical meeting record.

## Sources used

| Source | What it establishes | Limitation |
|---|---|---|
| Project Management Plan v1.1, updated July 9, 2026 | Intended cadence, dates, goals, roles, Definition of Done, ceremonies, risks, quality expectations, and initial technology/deployment assumptions | A plan is evidence of intent, not execution. The source remains external and was not copied into this repository. |
| Sprint Backlog v1.1, updated July 9, 2026 | Forty-seven planned items, estimates, acceptance criteria, priorities, and expected Capstone deliverables | Every item remains `Backlog` and every Owner cell is blank in the supplied workbook, so it is a planning baseline rather than a final task-state record. |
| [Canonical meeting index](../meetings/README.md) | Six PDFs covering seven dated TrustAI meetings from July 1 to September 3 | Meetings prove discussion and reported status, not a merge, release, deployment, or dedicated demo. |
| [`main` history](https://github.com/Ranga-Schooling/trustai-marketplace/commits/5ebc757ba66ff647944602245c18bedf6631680e), [pull requests](https://github.com/Ranga-Schooling/trustai-marketplace/pulls?q=is%3Apr+is%3Amerged), and [changelog](../../../CHANGELOG.md) | Actual implementation, integration, review, and release chronology through `v1.20.0` | Git activity does not prove that a Scrum ceremony occurred. |
| [Repository backlog](../../BACKLOG.md) and [design notes](../../DESIGN_NOTES.md) | Final story-to-code traceability and chronological decisions | These living records contain later refinements and must not be read back into earlier meetings. |

## Planned sprint model

The plan defined a short Sprint 0, three two-week development sprints, and a
final review/submission week. The workbook allocated 162 points across 47
items. Its dates and item counts are reproduced as planning evidence only.

| Planned phase | Planned dates | Workbook IDs | Items / points | Intended goal and outputs | Expected closeout |
|---|---:|---|---:|---|---|
| Sprint 0 | July 7–12 | `S0-1`–`S0-11` | 11 / 33 | Establish Trello and repository access; architecture and bounded-context diagrams; schema/migration direction; wireframes; Docker and CI skeletons; model-provider spike and deterministic mocks; documentation structure; an early deployed frontend | Sprint review/demo and retrospective under the general cadence; advisor preparation |
| Sprint 1 | July 13–26 | `S1-1`–`S1-13` | 13 / 41 | Deliver authentication, listing text/URL submission and persistence, React auth/submission, provider abstraction, deterministic mock mode, unit-test foundations, coverage, and continuous deployment | Recorded Sprint 1 demo and repository sprint report |
| Sprint 2 | July 27–August 9 | `S2-1`–`S2-9` | 9 / 38 | Deliver parsing, scam indicators, deterministic risk scoring, qualitative price plausibility, results, history, integration/contract testing, and currency handling | Recorded end-to-end Sprint 2 demo and sprint report |
| Sprint 3 | August 10–23 | `S3-1`–`S3-8` | 8 / 32 | Complete recommendations/questions, robust input handling, responsive polish, E2E coverage, resilience, and a draft design/testing report; attempt image analysis only as stretch work | Recorded Sprint 3 demo and sprint report |
| Final week | August 24–31 | `FW-1`–`FW-6` | 6 / 18 | Regression, code freeze by August 28, final documentation/diagrams, access checks, production deployment, final presentation recording, and submission | Final demonstration/presentation and submission |

The source plan assigned workstream accountability to Mulima Chibuye
(Project Manager/Scrum Master), Ahmed Al-Mandalawi (Product Owner and AI
Analysis Lead), Ranga Nyamadzawo (authentication, listings, and data backend),
Adrian Muchatibaya (frontend and wireframes), and Samar El Ghandour (QA and
DevOps). That allocation is a planned responsibility model. Actual engineering
credit is established separately by commits, pull-request authorship, reviews,
and the meeting records.

### Planned cadence and Definition of Done

The plan called for two-week sprints after the short Sprint 0, Monday/
Wednesday/Friday asynchronous status updates, a weekly Sunday sync, planning
on day one, and a sprint review/demo plus retrospective on the last day. Its
Definition of Done required a reviewed pull request merged to `main` with CI
passing, a live demonstration, updated documentation, and a Trello card moved
to Done with its PR linked.

The repository verifies sustained pull-request delivery, CI, documentation,
releases, and deployment work. The live [Trello board](https://trello.com/b/wUqCGA2T)
was reconciled during final submission closeout, but that final state does not
reconstruct the historical date of every movement or prove that every original
item met the planned Definition of Done. A complete series of formal reviews/
retrospectives and dedicated sprint-demo recordings remains unverified.

### Other planned operating assumptions

- Trello would contain Backlog, Sprint Backlog, In Progress, In Review, and
  Done columns; members would update owners and states, and the workbook
  dashboard would summarize them. The capacity guide was approximately 45
  points per two-week sprint for five part-time members.
- Story branches and peer-reviewed pull requests would protect `main`.
  GitHub Actions would run lint and pytest on every pull request, deterministic
  model mocks would keep CI provider-free, and Docker would keep environments
  reproducible.
- Deployment was initially expected on GitHub Pages with a custom domain and
  later described differently in ADR-001. Both were early assumptions rather
  than evidence of the final AWS deployment.
- The risk register anticipated reduced capacity, time-zone and availability
  conflicts, integration delays, weak model output, provider cost/rate limits,
  blocked URL extraction, currency inaccuracy, scope creep, and late
  documentation. Proposed mitigations included MoSCoW de-scoping, named
  backups, shared contracts, deterministic mocks, qualitative price framing,
  provider switching, frequent integration, and continuous documentation.

## Most defensible final delivery structure

The final history retains the planned sprint names because they provide the
only dated baseline, but labels each as a **planned window**. Actual work is
mapped into those windows from Git and meetings, with explicit carryover. A
sixth row is necessary because release convergence continued after the planned
August 31 endpoint.

| Sprint / phase | Actual evidence summary | Carryover or drift | Evidence confidence |
|---|---|---|---|
| Sprint 0 — foundation and planning | July 10 repository/documentation foundation; July 15 scaffold, contracts, CI, Docker, and architecture review | Planned July 12 close moved to July 15; deployment, governance, final architecture, provider criteria, and some setup remained open | **CONFIRMED** activity and July 15 review; **PARTIAL** against the full planned scope |
| Sprint 1 — core architecture and initial implementation | July 15–26 scaffold, auth, frontend auth, schema/migrations, repository controls, and Compose integration | Listing analysis, provider work, profile, testing depth, and deployment crossed into later windows | **CONFIRMED** activity; exact commitment completion **PARTIAL** |
| Sprint 2 — core feature delivery and integration | July 27–August 9 release automation, UI, core analysis, deterministic scoring, profile, coverage gate, architecture review, first AWS deployment work, and migration-on-start | History completed August 10; URL preview, price plausibility, multi-provider support, and full integration tests landed August 16–17 | **CONFIRMED** activity and releases; original workbook completion **PARTIAL** |
| Sprint 3 — hardening, recovery, deployment and release readiness | August 10–23 history, SSM deployment, integration/contract tests, account deletion, URL preview, price plausibility, provider abstraction, frontend tests, HTTPS, backup work, and operational hardening | Image analysis, final responsive polish, recovery, and strict production-model validation remained beyond August 23 | **CONFIRMED** activity and releases; formal review/demo **UNVERIFIED** |
| Final review week — release readiness | August 24–31 release-readiness meeting, admin analytics, evidence-policy hardening, deployment cleanup, UI contrast, and session-expiry synchronization | Planned August 28 freeze and August 31 completion were not the final repository boundary | **CONFIRMED** activity through `v1.16.4`; planned submission outcome **UNVERIFIED** |
| Post-plan convergence — final release and evidence closeout | September 2 risk/mobile fixes, recovery, dark mode, Visual Inspection, retry isolation, strict validation/Terra integration, CI, deployment health, and `v1.20.0`; September 3 evidence-closeout meeting | This work completed after the original schedule and replaced broad feature work with release/evidence closure | **CONFIRMED** implementation/release; the later September 4 application-boundary browser validation is documented separately, with private transport and exact Visual model identity still bounded |

## Phase reconstruction

### Sprint 0 — foundation and planning

**Planned goal.** Make the project executable: establish the board,
repository, architecture, contracts, wireframes, Docker/CI, schema strategy,
model spike, documentation, and an early public frontend.

**What the evidence shows.** The repository began on July 10 with the project
README, documentation areas, and the historical Render decision in ADR-001.
On July 15, the boilerplate history added React/Vite and FastAPI scaffolds,
Pydantic contracts, route stubs, skipped story tests, Docker Compose, CI, a
backlog, and design-note foundations. The [July 15 record](../meetings/02_TrustAI_Sprint_0_Review_and_Sprint_1_Alignment_Meeting_2026-07-15.pdf)
reports architecture diagrams, a runnable boilerplate, an initial CI skeleton,
and Trello population as completed or substantially completed.

**Drift and blockers.** The same July 15 record says Sprint 0 closed three days
later than the plan, with design consistency, architecture review, service
packaging, repository governance, provider/risk criteria, full Dockerization,
deployment, and workflow familiarity still open. Sprint 1 began immediately
on July 16 while this setup work continued. The plan's GitHub Pages assumption
also diverged from ADR-001's Render direction and from the later AWS solution;
none should be presented as a Sprint 0 production deployment.

**Ceremony and demo status.** A Sprint 0 review/retrospective and Sprint 1
alignment meeting is directly documented. It records review findings and
carryover. No dedicated Sprint 0 working-software demo recording is verified.

### Sprint 1 — core architecture and initial implementation

**Planned goal.** Deliver an authenticated listing-submission flow, persistent
listing lifecycle, provider abstraction and deterministic mock, initial
frontend integration, stronger tests, coverage, and deployment.

**What entered the repository during the planned window.** The July 15
scaffold was followed by the architecture diagrams ([PR #3](https://github.com/Ranga-Schooling/trustai-marketplace/pull/3)),
branch-protection verification ([#4](https://github.com/Ranga-Schooling/trustai-marketplace/pull/4)),
review automation ([#5](https://github.com/Ranga-Schooling/trustai-marketplace/pull/5)),
registration/login/auth dependency ([#6](https://github.com/Ranga-Schooling/trustai-marketplace/pull/6)),
the initial auth UI ([#7](https://github.com/Ranga-Schooling/trustai-marketplace/pull/7)),
PR/title controls ([#9](https://github.com/Ranga-Schooling/trustai-marketplace/pull/9)),
database models and Alembic migrations ([#8](https://github.com/Ranga-Schooling/trustai-marketplace/pull/8)),
and frontend/API Compose integration ([#11](https://github.com/Ranga-Schooling/trustai-marketplace/pull/11)).
Semantic-release work began on July 26, with the first release following on
July 27.

The [July 22 record](../meetings/03_TrustAI_Sprint_1_Progress_and_Sprint_Recovery_Integration_and_Deployment_Alignment_Meetings_2026-07-22_and_2026-08-06.pdf)
documents active backend/frontend/schema work, shared-contract dependencies,
provider uncertainty, review discipline, and integration blockers. It does not
claim that the whole Sprint 1 workbook scope was complete.

**Carryover.** Core analysis and mock/provider behavior merged July 31 in
[PR #12](https://github.com/Ranga-Schooling/trustai-marketplace/pull/12).
Profile work and the 85% backend coverage gate merged August 6. Deployment
entered `main` on August 8, while URL preview did not merge until August 17.
This is direct evidence that the planned Sprint 1 scope crossed later windows.

**Ceremony and demo status.** Sprint 1 alignment and the July 22 progress
stand-up are documented. A separate Sprint 1 review, retrospective, sprint
report, or dedicated working-software demo recording is not verified.

### Sprint 2 — core feature delivery and integration

**Planned goal.** Deliver the buyer-facing risk-analysis value: parsed listing
signals, scam indicators, deterministic risk score, price plausibility,
results/history, currency handling, and integration/contract tests.

**What entered the repository during the planned window.** Release automation
stabilized at `v1.0.0`; the wireframe-led frontend and core E3 analysis merged;
auth/profile/listing UI work converged; the unit-test foundation and 85%
coverage gate landed; the architecture review exposed contract and status
gaps; AWS/ECR/EC2 deployment work began; deterministic 0–100 scoring was added;
and startup migrations were made reliable. Releases progressed from `v1.0.0`
through `v1.7.1` between July 27 and August 9.

The July 31 E3 result contract already included a recommendation and seller
questions, so part of the work assigned to planned Sprint 3 was delivered
early. The numeric Trust score followed on August 8 and remained an
application-owned deterministic calculation rather than a model-produced
number.

The [August 6 record](../meetings/03_TrustAI_Sprint_1_Progress_and_Sprint_Recovery_Integration_and_Deployment_Alignment_Meetings_2026-07-22_and_2026-08-06.pdf)
documents schedule pressure, stale board state, slow merges, integration risk,
the still-open History path, and the emerging Actions/OIDC/ECR/EC2 deployment
direction. It explicitly supports an overlapping recovery model rather than a
clean sprint handoff.

**Carryover.** History list/detail merged August 10 ([PR #48](https://github.com/Ranga-Schooling/trustai-marketplace/pull/48)).
Integration/contract tests, URL preview, categorical price plausibility,
multi-provider support, enhanced price/currency/seller extraction, and
frontend API-call tests merged August 16–17 ([#57](https://github.com/Ranga-Schooling/trustai-marketplace/pull/57),
[#21](https://github.com/Ranga-Schooling/trustai-marketplace/pull/21),
[#41](https://github.com/Ranga-Schooling/trustai-marketplace/pull/41),
[#46](https://github.com/Ranga-Schooling/trustai-marketplace/pull/46),
[#77](https://github.com/Ranga-Schooling/trustai-marketplace/pull/77), and
[#74](https://github.com/Ranga-Schooling/trustai-marketplace/pull/74)). The final
implementation kept price plausibility qualitative; it did not add verified
live market-price research or the workbook's proposed external currency-data
normalization.

**Ceremony and demo status.** No separate Sprint 2 review, retrospective,
sprint report, or dedicated end-to-end demo recording is verified.

### Sprint 3 — hardening, recovery, deployment and release readiness

**Planned goal.** Complete recommendations/questions, resilience, robust
input behavior, responsive polish, E2E confidence, and the draft final report;
Visual Inspection remained a stretch item.

**What entered the repository during the planned window.** History and SSM
deployment landed August 10. From August 16–17 the project added account
deletion, integration/contract tests, URL preview, price plausibility,
multi-provider support, frontend tests, HTTPS/Caddy, database-startup repair,
scheduled backups, richer preview extraction, and production session/analysis
repairs. Text-only evidence wording, stale-model-knowledge guardrails, backup
workflow repair, EC2 disk cleanup, and gitStream automation followed through
August 23. Releases progressed from `v1.7.2` through `v1.15.5`.

**Architecture and release evolution.** The initial GitHub Pages/Render ideas
gave way to GitHub Actions, ECR, EC2, and then Systems Manager deployment. The
planned microservice language also resolved into a modular FastAPI API with
clear capability boundaries rather than multiple independently deployed
backend services. The provider abstraction remained, but the plan's cost-led
Groq preference did not become the final production text-model choice.

**Carryover.** Responsive geometry/mobile corrections, failed-listing
recovery, Visual Inspection, dark mode, per-listing retry isolation, strict
response validation, and the selected Terra production path all landed after
the planned Sprint 3 and final-week boundaries. The stretch image-analysis
idea therefore became a released feature, but only during September
convergence. The planned repeat-analysis cache and a browser-level E2E suite
are not established as delivered by the final repository evidence.

**Ceremony and demo status.** The August 6 meeting is a recovery/integration
alignment record, not a Sprint 3 review. No separate Sprint 3 review,
retrospective, sprint report, or dedicated demo recording is verified.

### Final review week — release readiness

**Planned goal.** Complete regression, freeze code by August 28, finalize
documentation and diagrams, verify access, deploy, record the final
presentation, and submit by August 31.

**What the evidence shows.** The [August 26 record](../meetings/04_TrustAI_Final_Release_Readiness_Feature_Freeze_and_Presentation_Planning_Meeting_2026-08-26.pdf)
documents release-critical prioritization, evidence-policy work, an EC2
disk-space problem, Trello/rubric reconciliation, a walkthrough plan, and
presentation rehearsals. It is a readiness snapshot, not proof of the later
release or final presentation. Between August 28 and 29, admin RBAC/aggregate
analytics, unsupported-evidence rejection, deployment cleanup, auth contrast,
and session-expiry synchronization merged. The final August tag was
`v1.16.4`.

**Carryover.** The intended August 28 freeze was not the final code boundary,
and the repository does not verify an August 31 submission. The release
critical path extended to September 2.

### Post-plan convergence — release and evidence closeout

On September 2, the project merged risk-gauge and mobile corrections
([PRs #94](https://github.com/Ranga-Schooling/trustai-marketplace/pull/94)
and [#95](https://github.com/Ranga-Schooling/trustai-marketplace/pull/95)),
CI/CD documentation and Visual deployment preparation ([#101](https://github.com/Ranga-Schooling/trustai-marketplace/pull/101)
and [#104](https://github.com/Ranga-Schooling/trustai-marketplace/pull/104)),
failed-listing recovery ([#100](https://github.com/Ranga-Schooling/trustai-marketplace/pull/100)),
dark mode ([#105](https://github.com/Ranga-Schooling/trustai-marketplace/pull/105)),
transient Visual Inspection ([#99](https://github.com/Ranga-Schooling/trustai-marketplace/pull/99)),
per-listing retry isolation ([#106](https://github.com/Ranga-Schooling/trustai-marketplace/pull/106)),
and strict response validation with Terra production integration
([#107](https://github.com/Ranga-Schooling/trustai-marketplace/pull/107)).
[PR #108](https://github.com/Ranga-Schooling/trustai-marketplace/pull/108)
was a Terra-only stacked change merged into the #107 feature branch; #107 was
the main-target merge that carried the combined strict-validation/Terra result.

Provider-neutral model evaluation began on a separate research branch on
August 30 and remains preserved in open [PR #103](https://github.com/Ranga-Schooling/trustai-marketplace/pull/103).
It was not merged wholesale into production; selected production conclusions
entered through the smaller #107 path.

Semantic releases advanced from `v1.16.5` to `v1.20.0` on September 2. The
final tag points to `5ebc757ba66ff647944602245c18bedf6631680e`.
The release CI recorded 70 contract tests, 449 backend tests at 96.49%
coverage, 76 frontend tests, and a successful frontend build; deployment
health is documented separately in the [production-validation record](../FINAL_PRODUCTION_VALIDATION.md).

The [September 3 record](../meetings/05_TrustAI_Final_Production_Validation_Evidence_Closeout_and_Presentation_Readiness_Meeting_2026-09-03.pdf)
marks the transition from broad feature development to evidence closeout,
rehearsal, recording, and submission preparation. Reported live observations
remain distinct from repository-preserved provider/browser evidence.

## Release and quality progression

| Planned period | Release evidence | Quality/deployment progression |
|---|---|---|
| Sprint 0, July 7–12 | No semantic release | Repository and documentation foundation |
| Sprint 1, July 13–26 | No tag within the planned window; release automation merged on July 26 | Scaffold, CI, auth, schemas/migrations, and repository controls |
| Sprint 2, July 27–August 9 | `v1.0.0`–`v1.7.1` | Semantic release, core analysis/UI, 85% backend coverage gate, initial ECR/EC2 deployment, deterministic score, startup migrations |
| Sprint 3, August 10–23 | `v1.7.2`–`v1.15.5` | History, SSM, integration/contract and frontend tests, HTTPS, provider abstraction, preview/price work, backup and operational hardening |
| Final week, August 24–31 | `v1.16.0`–`v1.16.4` | Admin/security/deployment/session hardening |
| Post-plan convergence, September 2 | `v1.16.5`–`v1.20.0` | Recovery, themes/mobile, Visual Inspection, retry isolation, strict validation, Terra integration, final CI and deployment health |

Across the release history, 145 commits are reachable from `v1.20.0`, 79
merged pull requests targeted `main`, and 41 semantic-release tags were
created. These counts establish a substantial reviewed delivery trail; they do
not substitute for missing ceremony evidence or prove contemporaneous
task-board maintenance.

## Planned versus actual outcomes

| Planning assumption | Actual evidence-backed outcome |
|---|---|
| Sprint 0 would end July 12 | The July 15 record treats Sprint 0 as closing that day, with setup carryover. |
| The Handbook and project plan expected a recorded working-software demonstration at each sprint end | No dedicated TrustAI sprint-demo recording is verified. Meeting records are not substitutes, and the Handbook does not identify these recordings as final-submission links. |
| The project plan expected a retrospective at each sprint end | Sprint 0 review/retrospective is documented; the complete local retrospective series is not verified. Retrospectives are not stated as a Handbook requirement. |
| Trello would be the continuously updated execution record | Meetings report Trello use and later drift. The live [canonical board](https://trello.com/b/wUqCGA2T) now has a reconciled final state, while explicitly retrospective records and Git/PR dates preserve the fact that closeout reconciliation is not proof of continuous historical maintenance. The supplied workbook remains an all-`Backlog`, owner-empty planning baseline. |
| Frontend would be live on GitHub Pages from Sprint 0 | ADR-001 recorded Render as an early alternative; August recovery shifted deployment toward AWS; the released pipeline uses ECR, EC2, SSM, Caddy, nginx, and Docker Compose. |
| Backend would be organized as microservices | July 15 still treated packaging as unresolved; the final product uses one modular FastAPI API service with PostgreSQL and a separate React frontend. |
| Groq was favored for cost | A provider abstraction was delivered; after separate evaluation, the production OpenAI adapter defaulted to GPT-5.6 Terra in the September release. |
| Image analysis was post-MVP/stretch | Visual Inspection was delivered after the planned August endpoint in `v1.19.0`, capability-gated and application-transient. |
| Code freeze and submission would complete by August 28/31 | Release-critical work continued through September 2; `v1.20.0` is the defensible final repository boundary. Submission remains a separate OPEN event. |

## Ceremony and artifact status

| Evidence item | Status | Defensible statement |
|---|---|---|
| Sprint planning baseline | **CONFIRMED** | The July plan and workbook define Sprint 0–3 plus a final week. |
| Sprint 0 review/retrospective | **CONFIRMED** | The July 15 canonical record documents the meeting, review findings, and carryover. |
| Sprint 1 planning/alignment | **CONFIRMED** | July 15 documents alignment; July 22 documents progress and blockers. |
| Later sprint recovery/planning | **CONFIRMED** | August 6 documents recovery, overlapping work, deployment direction, and Trello drift. |
| Complete Sprint 1–3 review series | **UNVERIFIED** | No complete formal review record set is present. |
| Complete retrospective series | **UNVERIFIED — project convention** | Only the Sprint 0 review/retrospective is directly documented; the Handbook does not mandate retrospectives. |
| Dedicated sprint-end application demos | **UNVERIFIED** | No authentic TrustAI recording has been verified; unrelated recordings are excluded. |
| Final Trello state | **PARTIAL** | The [canonical board](https://trello.com/b/wUqCGA2T) was authenticated, inventoried, and reconciled against `v1.20.0`. It is Private and had no grader member during the access audit, so independent grader access remains OPEN. The Handbook does not require public visibility or a named Trello account. |
| Final presentation/submission | **OPEN** | Planning and rehearsal discussions exist; completion evidence does not yet. |

## Remaining evidence needed

1. Make the reconciled Private [Trello board](https://trello.com/b/wUqCGA2T)
   accessible to the grader and verify access. Membership is the minimally
   disruptive option, not a specific Handbook-prescribed mechanism.
2. Locate and verify any authentic TrustAI sprint-end application demo before
   linking it. If none exists, retain the explicit limitation.
3. Add any missing Sprint 1–3 review artifact only if it is contemporaneous and
   authentic. Preserve retrospectives if found for historical completeness,
   but do not treat them as a Handbook requirement or reconstruct ceremonies.
4. Record the final presentation and submission only after each occurs and its
   access can be verified.

This reconstruction intentionally leaves those gaps visible. The available
planning, meeting, Git, PR, CI, release, and deployment evidence is strong
enough to explain how TrustAI evolved, but not to claim a cleaner ceremony
record than the project preserved.
