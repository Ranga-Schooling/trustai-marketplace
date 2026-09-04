# Sprint 2 — The product, and a real deployment

**Dates:** 2 August – 17 August 2026
**Merged pull requests:** 37 — the project's highest-throughput sprint
**Contributors:** all five team members

> Reconstructed from repository history on 2026-09-04. See the
> [note on how these reports were produced](README.md#a-note-on-how-these-reports-were-produced).

## Sprint goal

Turn the foundations into a working product a user could actually use end to
end, and put it on the public internet over HTTPS.

## Selected backlog items

| Story | Description |
|---|---|
| US-1.4 / US-1.5 | View and edit profile; delete account |
| US-2.3 | Submit a listing by URL, with fields suggested from the page |
| US-3.1 – US-3.6 | AI analysis: categorical risk, price plausibility, recommendation, deterministic scoring |
| US-4.1 / US-4.2 | Saved analysis history, list and detail |
| US-5.3 | Automated deployment to a public environment |
| US-6.3 / US-6.4 | Integration and contract tests; coverage gate |

## Completed work

**Analysis engine.** Categorical price plausibility (PR #41), the
deterministic 0–100 risk score computed server-side from the already-validated
categorical result (PR #43, D-09), and the multi-LLM provider abstraction that
put GPT and Gemini behind one interface (PR #46, Card #20). The design
constraint that risk is categorical and never LLM-numeric (D-05) held
throughout.

**Product surface.** Login/logout (PR #20), profile view and edit (PR #24),
account deletion (PR #58), analysis history list and detail (PR #48), and
listing submission by URL with fields extracted from the page (PR #21, #77).

**Deployment — the sprint's largest thread.** ECR build/push with EC2
auto-deploy on `main` (PR #37), then a deliberate migration from SSH to AWS
Systems Manager (PR #50), removing the need for any long-lived SSH key in
GitHub. OIDC permissions were added and then removed again once found
unnecessary (PR #38, #44). HTTPS with Caddy and automatic Let's Encrypt
certificates followed (PR #63), and the pipeline was documented as a
zero-trust design (PR #51). **This is the sprint in which the deployment
platform diverged from [ADR-001](../decisions/ADR-001-deployment-platform.md)'s
choice of Render — a divergence that went unrecorded until
[ADR-003](../decisions/ADR-003-aws-ec2-deployment.md) was written on
2026-09-04.**

**Testing.** Unit-test foundations with a CI coverage gate (PR #26),
integration tests chaining auth → listing → analysis plus contract tests
(PR #57), MockProvider determinism pinned (PR #59), and the first Vitest
frontend smoke tests wired into CI (PR #74).

**Operations.** Alembic migrations on container start (PR #47), a self-healing
startup migration for pre-Alembic bootstraps (PR #73), and scheduled Postgres
backups to S3 (PR #76).

## Incomplete at sprint end

- Admin RBAC and runtime provider configuration reached design-sketch stage
  only (PR #79) and were carried into Sprint 3 as issue #42.
- Frontend test coverage was smoke-level, not component-level.

## Blockers and how they were resolved

**A recurring class of defect emerged: UI shipped disconnected from its
API.** PR #67 found the account edit/delete screens calling nothing real;
PR #72 found History's empty-state CTA wired to a dead prop. Both had passed
review. The team's response was to require that a story's Definition of Done
include an un-skipped test exercising the actual call site — which is what
made the Vitest work in PR #74 a priority rather than a nice-to-have.

**A production incident** (PR #81) broke analysis and session handling on the
deployed instance shortly after it went live, and was fixed the same day.

## Demonstration evidence

No sprint demonstration was recorded. From 17 August the working software was
continuously demonstrable at **https://trustai.mandalawi.ca**, which is
stronger evidence than a recording would have been for this sprint — but it
does not substitute for the recording the handbook asked for.

## Retrospective

**What worked.** Moving deployment to SSM early, before the team had
accumulated habits around SSH, made the zero-trust design cheap to adopt.

**What did not.** Two defects (#67, #72) shipped UI that called nothing.
Review had been treating "does the diff look right" as sufficient.

**What was missed entirely.** The deployment platform changed and no ADR was
written. The team was recording *design* decisions diligently (D-05, D-09) at
exactly the moment it failed to record its largest *infrastructure* decision.

**Actions taken into Sprint 3.** Component-level frontend tests; every UI
story to include a test through the real API client.
