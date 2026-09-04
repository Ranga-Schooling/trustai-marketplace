# Sprint 1 — Foundations

**Dates:** 15 July – 1 August 2026
**Merged pull requests:** 24
**Contributors:** all five team members

> Reconstructed from repository history on 2026-09-04. See the
> [note on how these reports were produced](README.md#a-note-on-how-these-reports-were-produced).

## Sprint goal

Establish everything the team needed in order to work in parallel without
blocking each other: a governed repository, an automated pipeline, the data
model, authentication, and a containerized environment that every member
could run identically.

## Selected backlog items

| Story | Description |
|---|---|
| US-1.1 | Register with email and password |
| US-1.2 | Sign in and remain signed in for the session |
| US-5.1 | Containerized local development environment |
| US-5.2 | Continuous integration on every push and pull request |
| US-6.1 | Repository governance: branch protection, PR template, code owners |

## Completed work

**Repository governance and CI/CD**
- Branch protection verified and then formalized as a ruleset — 1 required
  review, required status checks, linear history (PR #4, #19,
  [ADR-002](../decisions/ADR-002-branch-protection-ruleset.md))
- Automatic reviewer assignment via the Developers team (PR #5)
- PR template and conventional-commit title linting (PR #9)
- semantic-release automation, producing versioned releases and a changelog
  from commit messages alone (PR #14)

**Product foundations**
- User registration, login and the authentication dependency (PR #6)
- Sign-in / register UI (PR #7)
- Listings and analyses schema with Alembic migrations (PR #8)
- First AI analysis and risk-scoring implementation (PR #12)
- Wireframes and the skeleton frontend UI (PR #23), followed by supporting
  styles for the auth, submit, results and history screens (PR #27)

**Environment**
- Frontend added to Docker Compose and wired to the API (PR #11)
- Postgres adopted for local Compose in place of SQLite (PR #2)

## Incomplete at sprint end

- AI analysis existed but was not yet behind a provider-independent
  interface — it could not be exercised in CI without network access. Carried
  into Sprint 2.
- No deployed environment existed yet.

## Blockers and how they were resolved

The sprint's most instructive difficulty was that **the release automation
took five pull requests to stabilize** (#14, #15, #16, #17, #18). Each failure
was a different integration detail: a missing
`conventional-changelog-conventionalcommits` dependency, then GitHub App
token action versioning, then resolving the App installation by repository
rather than by ID, then making the workflow able to push to a protected
`main` at all. This was real cost, but it bought a release process that
required no further attention for the remainder of the project.

A second blocker surfaced at the very end of the sprint: a teammate cloning
the repository from scratch could not start the stack (PR #33). Two distinct
causes — Vite binding to `localhost` inside a container, and the API
container racing the database — were fixed together. This is the reason the
team later adopted a written smoke-test checklist.

## Demonstration evidence

No sprint demonstration was recorded. Working state at sprint end is
evidenced by release tags and by CI passing on `main`.

## Retrospective

**What worked.** Front-loading governance meant that from PR #4 onward every
change was reviewed and CI-gated. No work was ever committed directly to
`main`.

**What did not.** Configuring release automation against a protected branch
consumed a disproportionate share of the sprint. In hindsight the team would
have merged a simpler release process first and hardened it later.

**Action taken into Sprint 2.** Put the AI provider behind an interface so
tests never require a network call or an API key — carried out as the
`AIProvider` protocol and `MockProvider`.
