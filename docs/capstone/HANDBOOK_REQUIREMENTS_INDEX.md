# MSSE Capstone Handbook Requirements Index

## Source and citation convention

This index is a concise traceability aid for the TrustAI Marketplace
submission. It does not replace or reproduce the source Handbook.

| Source property | Audited value |
|---|---|
| Title | *MSSE70+ Capstone Handbook* |
| Source filename | `MSSE_Capstone_Handbook.pdf` |
| SHA-256 | `2e1c75d176144c49cdc4531add7cfca34fe0e34920daad5c96143b22ded05bad` |
| Size | 293,655 bytes |
| PDF pages | 15 |
| Audit date | 2026-09-03 |

References use **Handbook PDF p. N**, where `N` is the one-based PDF page.
The cover is PDF page 1 and has no printed page number. Footer numbers on PDF
pages 2–15 match the PDF indexes, so this convention avoids an off-by-one
interpretation. The source file remains external to the repository and was not
copied or modified during the audit.

## Page-indexed structure

| PDF page | Relevant content | Requirement kind |
|---|---|---|
| 1 | Cover | Informational |
| 2 | Contents; project overview | Informational context |
| 3 | Project setting, shared repository, and learning outcomes | Software/collaboration outcomes |
| 4 | Required deliverables and assignment requirements | Mandatory project/submission requirements |
| 5 | Project selection, team formation, and Product Owner | Mandatory team-process requirements plus topic guidance |
| 6 | Initial meeting, backlog, sprint plan, minimum sprint count, board, and CI/CD | Mandatory Agile-process requirements |
| 7 | End-of-sprint recordings, team roles, sprint planning/attendance, meeting and deployment guidance | Mandatory process requirements and recommendations |
| 8 | Required repository, deployed link, board, design/testing report, and final recording | Mandatory reporting requirements |
| 9 | Final demonstration, presenter identity, file/hosting/submission mechanics, and Group Project Agreement | Mandatory presentation/submission requirements |
| 10 | Academic integrity and journey checklist | Integrity requirement and process summary |
| 11–13 | Capstone Project rubric | Project scoring criteria; pass threshold and score 5–0 distinctions |
| 14–15 | Capstone Presentation rubric | Presentation scoring criteria; pass threshold and score 5–0 distinctions |

## Capstone Project requirements

| Requirement | Handbook page | Strength | TrustAI status | Remaining action |
|---|---|---|---|---|
| Deliver working, high-quality software or an AI system meeting user requirements. | Handbook PDF p. 4 | Required | **PASS** — implemented and released as `v1.20.0`; final presentation is separate. | Demonstrate the released system. |
| Provide an accessible GitHub repository containing all developed and appropriately documented code. | Handbook PDF pp. 4, 8 | Required | **PASS** — public repository and immutable release available. | Preserve final links. |
| Share the repository with `quantic-grader`. | Handbook PDF pp. 4, 8 | Required | **OPEN** — named collaborator not found. | Share with the named account and verify access; access level is not stated. |
| Include a deployed-version link for a web application. | Handbook PDF pp. 4, 8 | Required | **PASS** — the documented URL loaded successfully in a logged-out HTTPS browser check on 2026-09-04. | Preserve the canonical URL and final validation record. |
| Include an accessible agile board link documenting tasks and delivered features/user stories. Trello is an example, not the only allowed tool. | Handbook PDF pp. 4, 8 | Required | **PARTIAL** — final Trello content reconciled; Private board access remains open. | Make the link accessible to the grader and verify it. |
| Provide the detailed design/testing report. | Handbook PDF pp. 4, 8 | Required | **PASS** — [`CAPSTONE_DESIGN_AND_TESTING.md`](CAPSTONE_DESIGN_AND_TESTING.md) covers every stated content category. | Preserve the report. |
| Provide a recorded final demonstration/presentation of the working system. | Handbook PDF pp. 4, 8–9 | Required | **OPEN** | Prepare and submit the final recording. |

## Agile and team-process requirements

| Requirement | Handbook page | Strength | TrustAI status | Remaining action |
|---|---|---|---|---|
| Team of at most six, or individual work; team agrees on the selected project. | Handbook PDF pp. 4–5 | Required | **PASS** — the final roster is confirmed as exactly five members. | Verify that the final Agreement lists those five members and contains every required signature. |
| Assign a Product Owner who develops the initial user stories. | Handbook PDF p. 5 | Required | **PASS** | Preserve role/story evidence. |
| At the initial meeting, nominate a Scrum Master; discuss scope/stories; prioritize the backlog; choose tools; establish a sprint timeline; select and assign the first sprint backlog. | Handbook PDF p. 6 | Required | **PASS** | Preserve planning sources. |
| Complete at least three sprints. | Handbook PDF p. 6 | Required | **PARTIAL** — delivery increments exist, but the complete formal review record is not preserved. | Keep the evidence boundary explicit. |
| Maintain a web Scrum board with backlog, stories/tasks per sprint, and completion status. | Handbook PDF p. 6 | Required | **PARTIAL** — final state is reconciled; historical drift is documented. | Preserve disclosure and close grader access. |
| Use CI/CD each sprint while collaboratively updating/testing/developing in the shared repository. | Handbook PDF p. 6 | Required | **PASS** | Select concise Git/PR/CI evidence. |
| At each sprint end, provide the Product Owner a recording of the working-software demonstration for sprint review. | Handbook PDF pp. 7, 10 | Required | **OPEN** — no dedicated TrustAI sprint-demo recording is verified. | Locate authentic recordings; do not substitute meeting records. |
| Hold planning at each new sprint's start, attended by every member. | Handbook PDF p. 7 | Required | **PARTIAL** | Add only authentic missing attendance/planning evidence. |
| Use PO, Scrum Master, team, and Code Owner roles; Code Owners approve PRs; PO/SM also contribute to development. | Handbook PDF p. 7 | Required | **PASS** | Preserve role, authorship, and review evidence. |
| Meet regularly in time-boxed Scrum sessions, around weekly. | Handbook PDF p. 7 | Recommended | **Documented, cadence incomplete** | Not a mandatory submission blocker. |
| Attend available webinars/facilitated events when possible. | Handbook PDF pp. 7, 10 | Recommended/optional | **NOT APPLICABLE** | No mandatory closure. |

The Handbook does not mandate retrospectives, daily standups, role rotation, a
fixed sprint length, or a formal Definition of Done. It also does not say the
sprint-demo recordings must be linked or submitted with the final deliverables.

## Design and testing requirements

| Required content | Handbook page | TrustAI status | Evidence |
|---|---|---|---|
| Design and architecture decisions | Handbook PDF pp. 4, 8 | **PASS** | Design/testing report §§2–9 and 14–16 |
| Technologies and architectural choices with reasons | Handbook PDF pp. 4, 8 | **PASS** | Report §§3–5 and 14 |
| Software/architecture patterns and reasons for use | Handbook PDF pp. 4, 8 | **PASS** | Report §5 and detailed boundary sections |
| Deployment recommendation including relative cost | Handbook PDF p. 8 | **PASS** | Report §14 |
| All testing, including automated tests, methods, and reasons | Handbook PDF pp. 4, 8 | **PASS** | Report §§10–13 |

No diagram, template, or document-length requirement is stated.

## Presentation requirements

| Requirement | Handbook page | Strength | TrustAI status |
|---|---|---|---|
| Record a final presentation with screen capture and voiceover. | Handbook PDF pp. 8–9 | Required | **OPEN** |
| Summarize the solution and demonstrate all functional capabilities of the deployed deliverable by screen share. | Handbook PDF p. 9 | Required | **OPEN** |
| Every group member speaks, is present, and is visible/on camera. | Handbook PDF pp. 8–9 | Required | **OPEN** |
| Every presenter shows government-issued ID with name/photo clearly legible. | Handbook PDF p. 9 | Required | **OPEN** |
| Run 15–20 minutes. | Handbook PDF pp. 8–9 | Required | **OPEN** |
| Submit one video file; `.mp4` is strongly recommended and `.mov` accepted; do not submit slideshows, separate clips, PowerPoint, PDF, or ZIP instead. | Handbook PDF p. 9 | Required format | **OPEN** |
| Host on Google Drive with “Anyone with the link can view.” | Handbook PDF p. 9 | Required access | **OPEN** |

Slides, Q&A, an unedited continuous take, all-moment face visibility, and a
file-naming convention are not stated as requirements.

## Submission and access requirements

| Requirement | Handbook page | TrustAI status | Remaining action |
|---|---|---|---|
| Submit accessible deliverable links with the Quantic dashboard's “Submit Project” buttons. | Handbook PDF p. 9 | **OPEN** | Complete access checks and submit. |
| One group member submits for the group. | Handbook PDF p. 9 | **OPEN** | Designate the submitter. |
| Upload only the final page of the Group Project Agreement, completed and signed by every member. | Handbook PDF p. 9 | **OPEN** | Locate the agreement and verify final-page signatures. |
| Submit the compliant Google Drive presentation link. | Handbook PDF p. 9 | **OPEN** | Record, host, and test the file first. |

The Handbook does not state a deadline/timezone, dashboard field inventory,
link-retention period, electronic-signature rule, or file naming convention. It
states no late-score penalty, but says late work delays feedback/grading,
usually by about four weeks (Handbook PDF p. 9).

## Academic integrity and attribution

Academic integrity applies, including accidental plagiarism. External code and
other sources must be cited appropriately (Handbook PDF p. 10). The Handbook
does not state a separate generative-AI disclosure, dependency bibliography, or
third-party-service register. Its learning outcomes do include demonstrating
appropriate use of AI tooling to support software development (Handbook PDF p.
3).

## Maximum-score criteria

### Capstone Project

Scores 3–5 pass; scores 0–2 require revision/resubmission. Score 5 requires all
Capstone requirements, all developed and documented code, the deployed link,
an up-to-date board showing all agreed stories/tasks complete, detailed
design/testing with pattern and method rationale, appropriate collaborative
methodology including CI/CD, an outstanding recorded demo/system, and
initiative above the minimum (Handbook PDF pp. 11–12). Lower levels
progressively permit only most, some, few, or missing elements (Handbook PDF
pp. 12–13).

### Capstone Presentation

Scores 2–5 pass; scores 0–1 require revision/resubmission. Score 5 requires a
thorough, clear, concise demonstration of implemented stories across a range of
inputs; correct operation throughout; professional and legible screen share;
clearly visible/audible students; and 15–20 minute duration (Handbook PDF p.
14). Lower levels progressively permit minor or more numerous operational,
coverage, presentation-quality, visibility/audio, and timing exceptions
(Handbook PDF pp. 14–15).

See the [authoritative evidence matrix](RUBRIC_EVIDENCE_MATRIX.md) for the
complete TrustAI status and ordered closure actions.
