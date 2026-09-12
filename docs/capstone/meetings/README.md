# TrustAI Marketplace — Meeting Records

This directory contains the six authoritative TrustAI Marketplace meeting-minute
PDFs supplied for the Capstone record. The PDFs are preserved byte-for-byte;
this index summarizes them for navigation without replacing the original
minutes or treating plans as proof of later implementation.

Together, the records document project selection, planning, sprint alignment,
architecture and ownership evolution, risks and blockers, integration and
deployment direction, release readiness, evidence closeout, and presentation
preparation. They document team meetings and recorded decisions; they are not
substitutes for dedicated sprint-end application demonstrations. No dedicated
TrustAI sprint-end application-demo recording is currently verified.

Git history, pull requests, reviews, issues, CI, releases, and deployment runs
remain the authoritative evidence for delivered engineering work. Meeting
minutes establish that a discussion, decision, assignment, or plan was
recorded at that point in the project. Later outcomes are identified separately
in the [project timeline](../PROJECT_TIMELINE.md).

## Meeting chronology

| Record | Date | Meeting | Source |
|---|---|---|---|
| 00 | 2026-07-01 | Capstone kickoff | [PDF](00_TrustAI_Capstone_Kickoff_Meeting_2026-07-01.pdf) |
| 01 | 2026-07-08 | Sprint planning and project initiation | [PDF](01_TrustAI_Sprint_Planning_and_Project_Initiation_Meeting_2026-07-08.pdf) |
| 02 | 2026-07-15 | Sprint 0 review and Sprint 1 alignment | [PDF](02_TrustAI_Sprint_0_Review_and_Sprint_1_Alignment_Meeting_2026-07-15.pdf) |
| 03A | 2026-07-22 | Sprint 1 progress stand-up | [Combined PDF](03_TrustAI_Sprint_1_Progress_and_Sprint_Recovery_Integration_and_Deployment_Alignment_Meetings_2026-07-22_and_2026-08-06.pdf) |
| 03B | 2026-08-06 | Sprint recovery, integration, and deployment alignment | [Combined PDF](03_TrustAI_Sprint_1_Progress_and_Sprint_Recovery_Integration_and_Deployment_Alignment_Meetings_2026-07-22_and_2026-08-06.pdf) |
| 04 | 2026-08-26 | Final release readiness, feature freeze, and presentation planning | [PDF](04_TrustAI_Final_Release_Readiness_Feature_Freeze_and_Presentation_Planning_Meeting_2026-08-26.pdf) |
| 05 | 2026-09-03 | Final production validation, evidence closeout, and presentation readiness | [PDF](05_TrustAI_Final_Production_Validation_Evidence_Closeout_and_Presentation_Readiness_Meeting_2026-09-03.pdf) |

The canonical kickoff date is **July 1, 2026**, as stated by record 00. Record
01 contains one retrospective reference to a “July 4 kickoff”; that source
wording is preserved in the PDF, but it is not used as the project chronology.

## Name reconciliation

The confirmed final roster uses the official names **Adrin Kudakwashe
Muchatibaya**, **Mulima Chibuye**, **Samar Salah Elghandour**, **Rangarirai
Revivalist Nyamadzawo**, and **Ahmed Al-Mandalawi**. The PDFs and chronological
summaries below preserve historical forms such as “Adrian Muchatibaya,”
“Ranga Nyamadzawo,” “Ranga,” “Samar El Ghandour,” and “Samar”; those forms map
to Adrin, Rangarirai, and Samar respectively and do not identify additional
team members.

## Detailed meeting index

## 00 — Capstone kickoff, July 1

**Purpose.** Select the team’s Capstone topic, establish Agile leadership,
agree on an initial delivery approach, and identify the work needed before
Sprint 1.

**Topics.** The team compared four product ideas: Mulima Chibuye’s AI-assisted
online proctoring concept, Ranga Nyamadzawo’s AgriScout crop-disease concept,
Ahmed Al-Mandalawi’s TrustAI Marketplace concept, and Adrian Muchatibaya’s
real-estate decision-support concept. The discussion also covered feasibility,
scope, GitHub collaboration, project-board options, sprints, documentation,
early deployment, and an initial service-oriented direction that was not yet a
final architecture.

**Decisions and ownership.** TrustAI Marketplace was selected. Ahmed
Al-Mandalawi became Product Owner, responsible for product vision, personas,
user stories, backlog, acceptance criteria, and functional direction. Mulima
Chibuye became Scrum Master, responsible for cadence, the project board,
timeline, blockers, and coordination. Ranga Nyamadzawo, Adrian Muchatibaya,
Samar El Ghandour, and Abdallah Mohmoud were recorded as the Development Team,
with detailed technical ownership deferred to refinement.

**Transition.** Ahmed was to prepare the product and repository foundations;
Mulima was to establish the board and cadence; the team was to review the
initial backlog before the July 8 planning meeting.

[Open the authoritative PDF](00_TrustAI_Capstone_Kickoff_Meeting_2026-07-01.pdf).

## 01 — Sprint planning and project initiation, July 8

**Purpose.** Convert the selected concept into an executable plan by refining
the MVP, sprint sequence, technical direction, risks, ownership, and immediate
Sprint 0 work.

**Topics.** Five active members proceeded after Abdallah Mohmoud no longer
participated. The team retained authentication and history, placed image
analysis outside the initial MVP unless core work became stable, chose Trello
for work tracking, adopted the existing repository and pull-request workflow,
and aligned on React, FastAPI, PostgreSQL, Docker, pytest, and GitHub Actions.
The external model was to sit behind a configurable provider abstraction with
deterministic mocks in development and CI. Price plausibility was preferred to
an unsupported claim of factual market value.

**Decisions and ownership.** Ahmed continued as Product Owner and AI Analysis
Lead; Mulima as Project Manager/Scrum Master; Ranga as backend lead for
authentication, listings, and data; Adrian as frontend lead; and Samar as
QA/DevOps lead. Ownership meant accountability with pairing at boundaries, not
isolated work.

**Transition.** The immediate sequence was to share repository and Trello
access, publish the revised backlog, assign Sprint 0 cards, complete the
architecture/wireframes/Docker/CI/schema/model spike, and enter Sprint 1 with
agreed contracts and owners.

[Open the authoritative PDF](01_TrustAI_Sprint_Planning_and_Project_Initiation_Meeting_2026-07-08.pdf).

## 02 — Sprint 0 review and Sprint 1 alignment, July 15

**Purpose.** Close Sprint 0, review architecture and open work, settle the
active repository and collaboration controls, and align the team for Sprint 1.

**Topics.** The meeting reviewed the end-to-end and bounded-context diagrams,
React/FastAPI/PostgreSQL direction, shared Pydantic/API contracts, frontend
design consistency, Trello/GitHub roles, test and CI expectations, and the
boundary between TrustAI and an external model. The team challenged an
unsupported probability-style risk score and selected explainable categorical
risk labels instead.

**Decisions and ownership.** The external model would remain behind a provider
adapter. Identity and Access, Listing Management, and Risk Analysis remained
the principal capability boundaries. Ranga drove backend/platform work,
Adrian led frontend and wireframes, Samar covered QA/DevOps and backend support,
Ahmed owned product direction and AI analysis, and Mulima coordinated the
project while supporting frontend work. Active development continued in the
shared repository through story branches, pull requests, reviews, CI, and
branch protection.

**Transition.** Sprint 1 priorities included repository access and controls,
approved API contracts, authentication and listing foundations, deterministic
analysis before live-model dependency, core React-to-API integration, and a
demonstrable end-to-end increment.

[Open the authoritative PDF](02_TrustAI_Sprint_0_Review_and_Sprint_1_Alignment_Meeting_2026-07-15.pdf).

## 03A — Sprint 1 progress stand-up, July 22

**Purpose.** Inspect Sprint 1 progress, surface blockers, and coordinate
parallel backend, frontend, data, and provider work against shared contracts.

**Topics.** The team reviewed schema and migration work, login/frontend
progress, the still-open provider choice, wireframes as the UI contract,
repository guardrails, branch-conflict avoidance, Trello ownership, regression
safety, and asynchronous coordination.

**Decisions and ownership.** Work was to follow the agreed architecture and
contracts; changes that affected another workstream required early
coordination; Trello and pull-request state needed to reflect the real work.
Ranga was driving backend/architecture, Adrian frontend implementation, Mulima
sprint/Trello coordination, Samar QA/DevOps and deployment, and Ahmed product,
AI, integration, testing, and release coordination.

**Transition.** The team moved from repository setup toward integrated
capability work, while keeping provider selection, history integration, and
deployment as visible dependencies.

[Open the combined authoritative PDF](03_TrustAI_Sprint_1_Progress_and_Sprint_Recovery_Integration_and_Deployment_Alignment_Meetings_2026-07-22_and_2026-08-06.pdf).

## 03B — Sprint recovery, integration, and deployment alignment, August 6

**Purpose.** Recover schedule and board accuracy, unblock integration, and turn
deployment from a late-stage risk into an active workstream.

**Topics.** The group discussed missed ceremony time, competing academic work,
slow merge flow, architecture drift, the remaining History gap, Trello
inaccuracy, and the need to deploy early. Render was reconsidered, followed by
an emerging AWS path using GitHub Actions, OIDC, ECR, and EC2. Cost and final
operational details were not all settled in this meeting.

**Decisions and ownership.** Approved pull requests should move promptly;
deployment, integration, testing, documentation, and the task board had to
describe the same system. Samar’s deployment workstream and Ranga’s platform
input fed the AWS direction; Ahmed owned release integration and production
testing; Adrian continued frontend integration; Mulima coordinated sprint
recovery and Trello reconciliation.

**Transition.** The recorded direction was to finish release-critical merges,
extend Actions to build and publish images, authenticate to AWS through OIDC,
activate ECR images on EC2, configure production privately, connect the domain,
and begin smoke testing early. Later repository and deployment evidence—not
these minutes—establishes what was ultimately implemented.

[Open the combined authoritative PDF](03_TrustAI_Sprint_1_Progress_and_Sprint_Recovery_Integration_and_Deployment_Alignment_Meetings_2026-07-22_and_2026-08-06.pdf).

## 04 — Final release readiness, August 26

**Purpose.** Establish the remaining release-critical scope, prepare for
feature freeze, reconcile evidence, and organize the final group presentation.

**Topics.** Four members participated; Samar joined after the discussion began,
and Adrian was absent. The team covered the deployed-application walkthrough,
presentation structure and timed rehearsals, issue #86/PR #90 evidence-policy
hardening, an EC2 disk-space deployment problem, Trello reconciliation, rubric
priorities, and a final repository/documentation/access review.

**Decisions and ownership.** The team entered release/submission mode, retained
legitimate open issues, and agreed to freeze new scope after remaining critical
work. Ahmed was to close the analysis-policy work and retain the meeting
record; Ranga and Samar were to address EC2 cleanup; Mulima and the team were to
reconcile Trello and grader access; Adrian was to prepare the frontend segment;
and the whole team was to conduct a walkthrough and timed rehearsals.

**Transition.** The next session was framed as a release walkthrough and
presentation rehearsal, not an open-ended development meeting. Statements here
describe August 26 readiness and plans; they do not prove the later September
release or live provider outcomes.

[Open the authoritative PDF](04_TrustAI_Final_Release_Readiness_Feature_Freeze_and_Presentation_Planning_Meeting_2026-08-26.pdf).

## 05 — Final production validation and evidence closeout, September 3

**Purpose.** Review the latest production-testing report, stop discretionary
feature development, close submission evidence gaps, and turn the presentation
plan into a rehearsal schedule.

**Topics.** Ahmed, Ranga, Mulima, and Adrian participated; Samar was absent from
the substantive discussion. Ahmed reported his production testing of the text
and Visual Inspection paths, while other team members were asked to test the
latest release independently. The team reviewed model-selection evidence,
Trello reconciliation, meeting and sprint evidence, the Group Project
Agreement, rubric expectations, the final 15–20 minute presentation, presenter
participation/identification, and rehearsal logistics.

**Decisions and ownership.** Broad feature work stopped unless a serious defect
appeared. Model evaluation would support the engineering explanation without
being presented as a guarantee of correctness. Each member was responsible for
reconciling their Trello work; the team would locate authentic sprint and
agreement evidence before considering any reconstruction. Ahmed would prepare
the presentation skeleton and maintain the record; each presenter would prepare
a distinct segment; the team scheduled a coordinated rehearsal.

**Transition.** The project moved from implementation into evidence closeout,
rehearsal, recording, and submission readiness. The minutes record Ahmed’s
reported production observations; separate sanitized technical evidence is
required before repository documentation can classify those provider/browser
paths as independently verified.

[Open the authoritative PDF](05_TrustAI_Final_Production_Validation_Evidence_Closeout_and_Presentation_Readiness_Meeting_2026-09-03.pdf).

## Meeting records versus demonstration recordings

These six PDFs document seven dated team meetings because record 03 covers two
dates. They are not dedicated sprint-end working-software demonstration
recordings. No dedicated TrustAI sprint-end application-demo recording has been
verified for this repository package. Unrelated externally supplied recordings
are intentionally excluded.

Planned walkthroughs, rehearsals, and demonstrations remain accurately labeled
as plans unless a separate authentic recording and its contents are verified.

## Integrity and handling

- The PDFs retain their supplied filenames and bytes.
- The July 22 and August 6 discussions remain one combined source file but are
  indexed as two chronology entries.
- Internal historical statements are not silently rewritten to match the final
  application.
- No meeting record is used on its own to claim a feature was implemented,
  released, deployed, or production-verified.
- Credentials, private chat transcripts, personal contact details, and
  unrelated recordings are not part of this directory.
