# TrustAI Marketplace — Authoritative Capstone Requirements and Evidence Matrix

## Purpose and source rule

This is the final submission-control matrix for TrustAI Marketplace. Assignment
requirements come from the **MSSE70+ Capstone Handbook**; implementation claims
come from the repository; process claims come from the evidence named in each
row. A plan proves intent, source proves implementation, a release identifies
immutable source, and deployment health does not by itself prove a public
browser or provider transaction.

Handbook citations use the PDF file's one-based page index: **Handbook PDF p.
N**. The cover is PDF page 1 and has no printed page number; the printed footer
numbers on PDF pages 2–15 match those PDF page indexes. The audited source is
identified in the [Handbook requirements index](HANDBOOK_REQUIREMENTS_INDEX.md).

Status key:

- **PASS** — the named evidence directly supports the requirement.
- **PARTIAL** — relevant evidence exists, but part of the requirement or its
  access/verification remains incomplete.
- **OPEN** — the required artifact, act, or verification has not been found or
  completed.
- **NOT APPLICABLE** — an optional or conditional item does not need closure.
- **NOT STATED** — the Handbook does not impose the claimed requirement.

## 1. Mandatory project deliverables

| ID | Handbook requirement | Page | TrustAI evidence and status | Remaining action |
|---|---|---|---|---|
| P-01 | Deliver a working, high-quality software or AI system that meets its user requirements. | Handbook PDF p. 4 | **PASS** — release `v1.20.0` at `5ebc757ba66ff647944602245c18bedf6631680e`, its source/tests, and CI establish the implemented system. Deployment and final-demo evidence are tracked separately. | Preserve the immutable release and demonstrate it in the final presentation. |
| P-02 | Provide an accessible GitHub repository containing all developed code, appropriately documented. | Handbook PDF pp. 4, 8 | **PASS** — the public [TrustAI repository](https://github.com/Ranga-Schooling/trustai-marketplace), release, source, and grader-facing documentation are accessible. | Pin final submission links to the repository and immutable release. |
| P-03 | Share the GitHub repository with the named account `quantic-grader`. | Handbook PDF pp. 4, 8 | **OPEN** — the direct collaborator lookup did not find that account. Public visibility does not remove the Handbook's separate sharing instruction. | Add/share with `quantic-grader`, then verify the account has repository access. The Handbook does not state a permission level or retention period. |
| P-04 | Include in the repository a link to the deployed version for a web application. | Handbook PDF pp. 4, 8 | **PASS** — [https://trustai.mandalawi.ca](https://trustai.mandalawi.ca) is documented and loaded successfully in a logged-out HTTPS browser check on 2026-09-04; the separate deployment-health evidence remains narrower. | Preserve the canonical URL and final validation record. |
| P-05 | Include in the repository an accessible agile task-board link documenting tasks and delivered features/user stories. Trello is typical, but another suitable board is allowed. | Handbook PDF pp. 4, 8 | **PARTIAL** — the [canonical Trello board](https://trello.com/b/wUqCGA2T) is linked and reconciled to `v1.20.0`, but it is Private and logged-out access is unavailable. | Make the existing link accessible to the grader and test access. The Handbook does not require a public board or name a Trello grader account. |
| P-06 | Provide a detailed design/testing document covering design and architecture decisions, technologies and choices with reasons, software/architecture patterns with reasons, deployment recommendation including relative cost, all testing, automated tests, testing methods, and reasons for them. | Handbook PDF pp. 4, 8 | **PASS** — [`CAPSTONE_DESIGN_AND_TESTING.md`](CAPSTONE_DESIGN_AND_TESTING.md) covers each element and preserves the pre-validation evidence boundary; [`FINAL_PRODUCTION_VALIDATION.md`](FINAL_PRODUCTION_VALIDATION.md) records the later September 4 browser result. | Preserve both reports and their chronology. |
| P-07 | Provide a recorded final demonstration/presentation of the working system. | Handbook PDF pp. 4, 8–9 | **OPEN** — the [presentation runbook](PRESENTATION_RUNBOOK.md) is authored and ready for team rehearsal, but no completed final recording is indexed. | Close the runbook's human confirmations, rehearse, record, validate, host, and submit the final presentation. |

## 2. Mandatory team and Agile process

| ID | Handbook requirement | Page | TrustAI evidence and status | Remaining action |
|---|---|---|---|---|
| A-01 | Work in a group of no more than six, or individually; the group agrees on the project. | Handbook PDF pp. 4–5 | **PASS** — the July 1 and July 8 meeting records identify the selected project, and final closeout confirmation establishes exactly five members. | Verify that the final Group Project Agreement lists the confirmed roster and contains every required signature. |
| A-02 | Assign a Product Owner, who develops the initial user stories. | Handbook PDF p. 5 | **PASS** — the July 1 record names Ahmed Al-Mandalawi as Product Owner; planning records and `docs/BACKLOG.md` preserve the story set. | Preserve the role/story evidence; Agreement verification remains separate. |
| A-03 | Nominate a Scrum Master in the first sprint meeting. | Handbook PDF p. 6 | **PASS** — the kickoff record names Mulima Chibuye as Scrum Master and the July 8 record preserves that role. | Preserve the role evidence; Agreement verification remains separate. |
| A-04 | At the initial meeting, discuss scope/stories, develop a prioritized product backlog, select tools/technologies, establish the sprint timeline, select the first sprint backlog, and assign work. | Handbook PDF p. 6 | **PASS** — the July plan, backlog, July 1/8 records, and sprint index document those decisions while preserving their planned status. | No further Handbook artifact is stated; retain the sources. |
| A-05 | Complete at least three development sprints. | Handbook PDF p. 6 | **PARTIAL** — the plan defines Sprint 0–3 and Git/PR/release history shows sustained increments across the sprint windows, but the complete formal sprint review record is not preserved. | Use the sprint index honestly; add only authentic missing review evidence if located. |
| A-06 | Maintain a web-based Scrum board with the product backlog, stories implemented in each sprint and their tasks, and completion status. | Handbook PDF p. 6 | **PARTIAL** — the final Trello state is reconciled, but meetings document historical drift and late reconciliation is not proof of continuous maintenance. | Preserve the disclosed drift and ensure grader access to the final board. |
| A-07 | Use CI/CD during each sprint while collaboratively updating, testing, and developing code in the shared GitHub repository. | Handbook PDF p. 6 | **PASS** — Git/PR history and GitHub Actions establish collaborative commits, reviews, automated tests, releases, images, and deployments. | Select concise examples for the final presentation/report. |
| A-08 | At the end of every sprint, provide the Product Owner a recording of a working-software demonstration for sprint review. | Handbook PDF pp. 7, 10 | **OPEN** — meeting records exist, but no dedicated TrustAI sprint-end working-software recording has been verified. Meetings and rehearsals are not relabeled as demos. | Locate and authenticate any existing sprint recordings. The Handbook does not say these recordings must be linked or uploaded with the final submission. |
| A-09 | Hold planning at the start of each new sprint; every member must attend. | Handbook PDF p. 7 | **PARTIAL** — July 8 and July 15 planning/alignment are documented, with later recovery planning on August 6; a complete all-sprints attendance series is not preserved. | Add only authentic attendance/planning evidence if available. |
| A-10 | Use Product Owner, Scrum Master, team-member, and one-or-more Code Owner roles; Code Owners approve pull requests, and the Product Owner/Scrum Master contribute equally to development. | Handbook PDF p. 7 | **PASS** — meetings identify PO/SM/team roles; CODEOWNERS, protected reviews, authorship, commits, and PRs establish code ownership and development contribution. | Select representative, current-head review evidence; Agreement verification remains separate. |

### Recommended or optional process guidance

| ID | Handbook guidance | Page | TrustAI status | Submission effect |
|---|---|---|---|---|
| G-01 | Meet in regular time-boxed Scrum meetings, around once per week. | Handbook PDF p. 7 | **PASS as documented guidance** — six PDFs index seven dated meetings; this does not prove a perfect weekly cadence. | Recommended practice, not a stated mandatory submission artifact. |
| G-02 | Attend as many Capstone webinars/facilitated events as possible. | Handbook PDF pp. 7, 10 | **NOT APPLICABLE / optional** — attendance evidence was not audited. | The checklist labels this optional; it is not a submission blocker. |
| G-03 | For a web application, deploy to a production host, with free-tier services given as examples. | Handbook PDF pp. 4, 7 | **PASS** — TrustAI uses AWS EC2/ECR rather than the examples. | A free-tier provider is not mandated; the deployed link and demonstration still must work. |

The Handbook does **not** state mandatory daily standups, retrospectives,
role rotation, a fixed sprint length, or a formal Definition of Done. TrustAI's
planning documents may record those as project conventions, but they are not
Handbook submission requirements.

## 3. Design and testing compliance

| ID | Required report content | Page | Status and evidence |
|---|---|---|---|
| D-01 | Design and architecture decisions | Handbook PDF pp. 4, 8 | **PASS** — report §§2–9 and 14–16. |
| D-02 | Technologies and architectural choices, with reasons | Handbook PDF pp. 4, 8 | **PASS** — report §§3–5 and 14. |
| D-03 | Software and architecture patterns, with reasons for use | Handbook PDF pp. 4, 8 | **PASS** — report §5 and the provider/validation/scoring/ownership sections. |
| D-04 | Deployment recommendation, including relative cost | Handbook PDF p. 8 | **PASS** — report §14 recommends the implemented AWS path and provides a bounded qualitative comparison without unsupported billing figures. |
| D-05 | Details of all testing, including automated tests, testing methods, and reasons | Handbook PDF pp. 4, 8 | **PASS** — report §§10–13 map test layers, rationale, immutable CI results, production-health scope, and limitations. |

The Handbook does not specify a required diagram, document template, or
minimum/maximum report length. The current report contains architecture
diagrams and traceability as supporting evidence, not as invented mandates.

## 4. Final presentation requirements

| ID | Handbook requirement | Page | TrustAI status | Remaining action |
|---|---|---|---|---|
| V-01 | Submit one recorded final demonstration/presentation with screen capture and voiceover. | Handbook PDF pp. 8–9 | **OPEN** | Create and quality-check one final video. |
| V-02 | Summarize the solution and demonstrate all functional capabilities of the working deployed deliverable by screen share. | Handbook PDF p. 9 | **OPEN** | Map the released user stories to a timed deployed-app demonstration. |
| V-03 | All group members must speak, be present, and be visible/on camera. | Handbook PDF pp. 8–9 | **OPEN** — the exact five-person presenter roster is confirmed; attendance and recording evidence do not yet exist. | Ensure all five confirmed presenters speak, remain present, and are visible in the final recording. |
| V-04 | Each presenter must show a government-issued ID with name and picture clearly visible and legible. | Handbook PDF p. 9 | **OPEN** | Use the five confirmed official names in the privacy-conscious ID segment; do not store ID images here. |
| V-05 | Duration must be 15–20 minutes. | Handbook PDF pp. 8–9 | **OPEN** | Time and rehearse the final script. |
| V-06 | Submit one single video file; `.mp4` is strongly recommended and `.mov` is accepted. Do not submit slideshows, separate clips, PowerPoint, PDF, or ZIP instead. | Handbook PDF p. 9 | **OPEN** | Export and review one compliant final file. |
| V-07 | Host the recording on Google Drive and set access to “Anyone with the link can view.” | Handbook PDF p. 9 | **OPEN** | Upload the final file and test access from a logged-out/private browser. |

The Handbook does **not** state that slides are required, that faces must
remain visible throughout every moment, that the recording must be unedited,
that a Q&A is required, or that a filename convention applies.

## 5. Presentation scoring — highest-score readiness

Presentation scores of 2–5 pass; scores 0–1 require revision/resubmission
(Handbook PDF pp. 14–15). To earn score 5, the presentation must:

| Score-5 criterion | Page | TrustAI status | Closure |
|---|---|---|---|
| Thoroughly, clearly, and concisely demonstrate implemented user stories for a range of inputs. | Handbook PDF p. 14 | **OPEN** | Select representative synthetic normal, suspicious, safe-failure, recovery, and visual inputs without turning this into another evaluation. |
| Operate correctly throughout the demonstration. | Handbook PDF p. 14 | **OPEN** | Complete final E2E, rehearse, and retain safe recovery material. |
| Be professional, with a clear and legible screen share. | Handbook PDF p. 14 | **OPEN** | Rehearse browser state, zoom, transitions, and narration. |
| Keep students clearly visible and audible. | Handbook PDF p. 14 | **OPEN** | Verify camera, layout, microphones, and final export. |
| Remain within 15–20 minutes. | Handbook PDF p. 14 | **OPEN** | Time the final edit and verify duration. |

Score 4 allows only minor operational exceptions and a marginal timing miss;
score 3 allows a few exceptions, covers a majority rather than all stories,
and may be significantly outside the duration. Scores 2–0 reflect increasing
omissions, failures, presentation-quality problems, or incompleteness
(Handbook PDF pp. 14–15).

## 6. Project scoring — highest-score readiness

Project scores of 3–5 pass; scores 0–2 require revision/resubmission
(Handbook PDF pp. 11–13). The score-5 criteria and TrustAI state are:

| Score-5 criterion | Page | Status | Gap/risk |
|---|---|---|---|
| Address all Capstone requirements. | Handbook PDF p. 11 | **PARTIAL** | Repository sharing, board access, sprint-demo evidence, agreement, presentation, and final submission remain open. |
| Provide all developed code in an appropriately documented repository. | Handbook PDF p. 11 | **PASS** | Preserve immutable release/documentation links. |
| Provide a deployed web-application link. | Handbook PDF p. 11 | **PASS** | Preserve the canonical URL and September 4 logged-out browser record. |
| Show all agreed user stories/tasks complete on an up-to-date task board. | Handbook PDF p. 11 | **PARTIAL** | Content is reconciled; grader access is open and historical drift must remain disclosed. |
| Provide detailed design/testing evidence, including pattern rationale and all testing methods. | Handbook PDF pp. 11–12 | **PASS** | Preserve the completed report. |
| Use appropriate methodology and collaborative tools, including CI/CD. | Handbook PDF p. 12 | **PASS** | Select concise Git/PR/Actions examples. |
| Provide an outstanding recorded demo that clearly shows an outstanding system. | Handbook PDF p. 12 | **OPEN** | Produce the final presentation to the score-5 presentation criteria. |
| Show good initiative above the minimum requirements. | Handbook PDF p. 12 | **PASS** | Use a small evidence-backed set: deterministic scoring, strict generated-output validation, privacy-bounded Visual Inspection, and immutable deployment. |

Scores 4 and 3 progressively permit “most” or “some” requirements and board
items, less complete design/testing evidence, and lower demo/system quality.
Scores 2–0 represent few, missing, or seriously incomplete elements
(Handbook PDF pp. 11–13).

## 7. Submission and access controls

| ID | Handbook requirement/instruction | Page | TrustAI status | Remaining action |
|---|---|---|---|---|
| S-01 | Submit accessible links to the required deliverables using the “Submit Project” buttons on the Quantic dashboard. | Handbook PDF p. 9 | **OPEN** | Complete final access checks, then use the dashboard. The Handbook does not enumerate its exact form fields. |
| S-02 | For a group, exactly one member submits on the group's behalf. | Handbook PDF p. 9 | **OPEN** | Designate the submitter before submission. |
| S-03 | Upload the final page of the Group Project Agreement, completed and signed by every group member. | Handbook PDF p. 9 | **OPEN** — a filename-scoped search of the repository, expected Capstone source folder, and known download location found no Capstone agreement artifact. | Locate the authoritative agreement and verify the final page and all signatures; do not fabricate a replacement. Electronic-signature acceptance is not stated. |
| S-04 | Submit the final presentation link through the Quantic dashboard after hosting the compliant file on Google Drive with link-view access. | Handbook PDF p. 9 | **OPEN** | Complete, host, test, and submit the recording. |
| S-05 | Make the repository, deployed link, task board, and recording accessible through the required repository/submission links. | Handbook PDF pp. 4, 8–9 | **PARTIAL** | The deployed link passes; close repository sharing, Trello access, and recording access. |

The Handbook states no score penalty for late submission, but warns that
feedback and grading will be delayed, generally by about four weeks
(Handbook PDF p. 9). It does not state the specific project deadline, timezone,
form field inventory, link-retention period, or an upload naming convention.

## 8. Academic integrity, attribution, and learning outcomes

| ID | Handbook statement | Page | Status and action |
|---|---|---|---|
| I-01 | Academic integrity applies; representing others' work as one's own is plagiarism, including accidental plagiarism. Cite external software code and other sources appropriately. | Handbook PDF p. 10 | **PARTIAL** — repository license, dependency manifests, links, and source history exist; a final submission-wide attribution review is not recorded. Complete that review before submission. |
| I-02 | The Capstone learning outcomes include demonstrating appropriate use of AI tooling to support software development. | Handbook PDF p. 3 | **PASS** — project history and the provider-evaluation provenance document bounded AI-assisted engineering work. Select an honest, concise example for the final narrative. |

The Handbook does not state a separate generative-AI disclosure artifact,
third-party-service register, or required dependency bibliography. Those may be
good documentation practices but are not added here as mandatory requirements.

## 9. TrustAI evidence controls that are not Handbook requirements

The following are project-specific evidence controls. They improve confidence
but must not be confused with submission requirements:

- the completed logged-out production access check and sanitized Terra/Visual
  application-path evidence;
- explicit backup/restore readiness tracking;
- immutable CI/deployment run references and release-SHA traceability;
- preserving historical Trello drift and planning-versus-delivery distinctions;
- a final local-link, privacy, secret, and factual-claim audit; and
- preserving sprint retrospectives if authentic records exist.

## 10. Ordered closure sequence

1. Share the repository with `quantic-grader` and verify access (P-03).
2. Make the Private Trello board accessible to the grader and test the link
   without changing its history (P-05/A-06).
3. Locate the signed final Group Project Agreement page (S-03).
4. Locate and authenticate any sprint-end software-demo recordings; preserve
   OPEN if they do not exist (A-08).
5. Preserve the completed September 4 logged-out production and live
   application critical-path evidence and its provider-identity boundaries.
6. Close the [presentation runbook](PRESENTATION_RUNBOOK.md) confirmations and
   rehearse the 15–20 minute all-member recording.
7. Record one compliant final video, show each presenter's government-issued
   ID as required, host it on Google Drive, and verify link-view access.
8. Designate one submitter, complete attribution and final access checks, upload
   the signed agreement page, and submit all accessible links through Quantic.
