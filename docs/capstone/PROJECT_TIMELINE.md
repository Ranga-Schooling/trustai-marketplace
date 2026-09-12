# TrustAI Marketplace Project Timeline

This timeline reconstructs project evolution from the July Project Management
Plan and Sprint Backlog planning baselines, repository history, and the
authoritative meeting records indexed below. A plan establishes intent. A
meeting record establishes the discussion, decisions, and actions documented
at that time; it does not prove that a planned feature was later delivered.
Delivered behavior is tied to merged code, tests, releases, or deployment
evidence. The detailed planned-versus-actual reconciliation is in the
[sprint history](sprints/README.md).

## Evidence conventions

- **Meeting record:** an imported source documents the meeting at that point in
  time; implementation outcomes require independent repository evidence.
- **Planning source:** the external Project Management Plan v1.1 and Sprint
  Backlog v1.1 establish the original schedule and intended scope; neither was
  copied into this repository, and neither proves delivery.
- **Planned:** evidence of intent or prioritization only.
- **Implemented:** merged source and tests establish the behavior.
- **Released:** semantic-release tagged the corresponding main-branch state.
- **Deployed-health verified:** GitHub Actions recorded successful activation
  and application health; this is narrower than a live user/provider E2E test.

## July 2026 — foundation and architecture

| Date | State | Evidence-based milestone |
|---|---|---|
| July 1 | Meeting record | [Capstone kickoff](meetings/00_TrustAI_Capstone_Kickoff_Meeting_2026-07-01.pdf): TrustAI Marketplace was selected from four concepts; Ahmed Al-Mandalawi became Product Owner, Mulima Chibuye became Scrum Master, and the team agreed on Agile delivery, GitHub collaboration, formal work tracking, and early deployment. The service-oriented direction remained preliminary. |
| July 8 | Meeting record | [Sprint planning and project initiation](meetings/01_TrustAI_Sprint_Planning_and_Project_Initiation_Meeting_2026-07-08.pdf): five active members refined the MVP, Sprint 0/cadence, ownership, Trello, repository workflow, technology direction, provider abstraction, and qualitative price plausibility. Planned work is not treated as delivered here. |
| July 9 | Planning baseline | Project Management Plan v1.1 and Sprint Backlog v1.1 documented Sprint 0 (July 7–12), Sprint 1 (July 13–26), Sprint 2 (July 27–August 9), Sprint 3 (August 10–23), and a final week (August 24–31). The workbook contains 47 estimated items, but all supplied Status cells remain `Backlog` and all Owner cells are blank; it is not a final execution record. |
| July 10 | Planned/documented | Repository documentation areas were created and [ADR-001](../decisions/ADR-001-deployment-platform.md) recorded Render as the original deployment choice. The final implementation later moved incrementally to AWS; ADR-001 remains historical, and [ADR-003](../decisions/ADR-003-aws-ec2-deployment.md) records the released architecture retrospectively. |
| July 15 | Meeting record and implemented foundation | [Sprint 0 review/retrospective and Sprint 1 alignment](meetings/02_TrustAI_Sprint_0_Review_and_Sprint_1_Alignment_Meeting_2026-07-15.pdf) reviewed completed and open setup, bounded contexts, shared API contracts, categorical rather than unsupported probability-style risk, repository governance, and ownership. It moved the practical Sprint 0 close from the planned July 12 to July 15 and carried unfinished setup into Sprint 1. React/Vite and FastAPI scaffolds, Pydantic contracts, story-mapped API stubs, skipped acceptance tests, Docker Compose, CI, backlog, and design-note foundations also entered Git history. |
| July 20–24 | Implemented | Architecture diagrams, branch-protection verification, review automation, authentication and auth UI, PR/title controls, persistence models, and Alembic migrations entered `main`. The [July 22 progress record](meetings/03_TrustAI_Sprint_1_Progress_and_Sprint_Recovery_Integration_and_Deployment_Alignment_Meetings_2026-07-22_and_2026-08-06.pdf) documents coordination, integration dependencies, provider uncertainty, repository discipline, and blockers at that time. |
| July 26–31 | Integrated | Frontend/API Compose integration, semantic-release automation, repository-ruleset documentation, the wireframe-led UI, and the core deterministic-mock/Groq E3 analysis implementation converged on `main`. The first tag, `v1.0.0`, was created July 27; release `v1.2.0` followed the E3 merge on July 31. Profile and deeper testing work had not yet landed. |

## August 2026 — product completion, quality, and deployment

| Date | State | Evidence-based milestone |
|---|---|---|
| August 1–6 | Review and implementation | The architecture review compared Trello work with contracts and exposed integration gaps. Auth, profile, listing, and layout work merged, while unit-test foundations and the backend coverage gate became part of CI. The [August 6 recovery/alignment record](meetings/03_TrustAI_Sprint_1_Progress_and_Sprint_Recovery_Integration_and_Deployment_Alignment_Meetings_2026-07-22_and_2026-08-06.pdf) documents Trello drift, integration pressure, and the emerging Actions/OIDC/ECR/EC2 direction; later source and deployment records establish the final implementation. |
| August 8–10 | Deployment and history | GitHub Actions began building and deploying ECR images to EC2. Deterministic risk scoring, migration-on-start, the testing guide, history list/detail, and the transition from SSH to SSM were implemented. Releases advanced through `v1.8.0`. |
| August 16–17 | MVP breadth and production hardening | Account deletion, integration/contract tests, URL preview, price plausibility, multi-provider abstraction, frontend API-call tests, HTTPS/Caddy, self-healing migration handling, scheduled backup workflow, enhanced listing extraction, and production session/analysis fixes merged. Releases advanced through `v1.15.1`. |
| August 18–23 | Trust and operations | Text-only evidence wording, stale-model-knowledge guardrails, backup workflow repair, automated disk cleanup, log rotation, and initial gitStream automation were added. Production backup recovery nevertheless remained operationally unresolved under issue #88. |
| August 26 | Meeting record | [Final release-readiness meeting](meetings/04_TrustAI_Final_Release_Readiness_Feature_Freeze_and_Presentation_Planning_Meeting_2026-08-26.pdf): the team prioritized release-critical work, honest treatment of open issues, Trello/rubric reconciliation, a deployed-application walkthrough, feature freeze, and timed presentation rehearsals. It records the August 26 position and does not prove the later September release. |
| August 28–29 | Security, admin, and session quality | Admin RBAC/aggregate analytics, unsupported-evidence rejection, deployment cleanup repair, auth contrast, and mid-session expiry synchronization merged. Release `v1.16.4` became the final August release. |
| August 30–September 2 | Research and production extraction | Provider-neutral evaluation work began on the separate research branch preserved in PR #103. It was not merged wholesale. Strict validation and the selected Terra production integration were extracted through the smaller stacked PR #108 and main-target PR #107. |

## September 2026 — final integration and release

| Date | State | Evidence-based milestone |
|---|---|---|
| September 2 | Implemented/released | Risk-gauge geometry and mobile responsiveness fixes merged, followed by refreshed CI/CD documentation, Visual Inspection deployment preparation, failed-listing recovery, dark mode, Visual Inspection with application-level transient state, isolated per-listing retry state, and strict Terra production text integration. |
| September 2, 20:14 UTC | Released | Semantic release created `v1.20.0` at `5ebc757ba66ff647944602245c18bedf6631680e`. The release contains the merged strict-validation/Terra integration from PR #107. |
| September 2, 20:14–20:17 UTC | Automated validation/deployment | CI passed 449 backend tests at 96.49% coverage, 76 frontend tests, and the frontend build. The automatic deployment activated the immutable release SHA and passed application health. |
| September 2, 21:39 and 21:54 UTC | Deployment-health verified | Two manual deployment runs reactivated the same immutable SHA and passed the health gate. GitHub evidence establishes successful activation, not the contents of private host configuration or a live provider result. |
| September 3 | Meeting record | [Final production validation and evidence-closeout meeting](meetings/05_TrustAI_Final_Production_Validation_Evidence_Closeout_and_Presentation_Readiness_Meeting_2026-09-03.pdf): the team stopped discretionary feature work, reviewed production-testing reports and model-selection evidence, identified Trello/agreement/demonstration evidence gaps, and scheduled presentation preparation and rehearsal. Reported production observations remain distinct from independently preserved technical evidence. |
| September 3 | Documentation synthesis | This grader-facing evidence package was prepared from `v1.20.0`. Live public-access, Terra E2E, Visual E2E, Trello grader access, sprint-demonstration evidence, and final-presentation evidence remain separately tracked OPEN items. |
| September 3–4 | Final board reconciliation | The authenticated [canonical Trello board](https://trello.com/b/wUqCGA2T) was inventoried and reconciled against repository, pull-request, issue, and release evidence. Stale delivered items were corrected; deferred, superseded, cancelled, and unresolved work remained visible; retrospective delivery records were explicitly labelled as closeout records. This establishes the final board state, not the historical date of every card movement. The board remains Private, so grader access is still OPEN. The Handbook requires an accessible board link but does not prescribe public visibility or a named Trello account. |
| September 4 | Live application validation | A controlled browser check verified logged-out HTTPS reachability, user-assisted authenticated session persistence, three synthetic Terra-labelled text results, newest-first saved history, one consented synthetic-image Visual Inspection, score/recommendation separation, and application-level Visual non-persistence. Private environment values and provider raw bodies were not inspected; exact provider transport details and the Visual model remain outside the evidence boundary. |

## Delivered final system

By `v1.20.0`, repository evidence supports an authenticated marketplace-risk
application with listing entry and guarded URL preview, strict structured text
analysis, deterministic scoring, history and recovery, admin aggregate
analytics, responsive themes, optional Visual Inspection whose photos/findings
are not persisted by the TrustAI application, automated
testing, semantic releases, and an AWS/ECR/EC2/SSM deployment pipeline.

The committed OpenAI text adapter uses the Responses API, defaults its explicit
model setting to Terra, and uses prompt v4. The selection rationale is recorded
in D-21. The September 4 browser validation observed successful structured
results labelled `Model used: gpt-5.6-terra`; it did not inspect the private
production environment or provider transport. The provider-neutral evaluation
work remains preserved separately in PR #103 and was not merged wholesale into
production.

## Evidence still needed to complete the chronology

1. Independent grader access to the reconciled Private [Trello board](https://trello.com/b/wUqCGA2T); final disposition is now visible to authorized members, but the closeout state does not reconstruct historical movement dates.
2. Any authentic TrustAI sprint-end working-software demonstration recording,
   if one is located; no dedicated recording is currently verified.
3. Any authentic later-sprint review or retrospective records. The Handbook
   requires an end-of-sprint recorded software demonstration for the Product
   Owner's review, but does not state that retrospectives are mandatory; only
   the Sprint 0 review/retrospective is directly documented.
4. The final presentation and submission timestamp after they occur.
