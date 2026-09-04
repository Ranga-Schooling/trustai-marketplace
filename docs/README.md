# TrustAI Marketplace Documentation

Project documentation for the TrustAI Marketplace MSSE Capstone Project.

## Start here

| If you are looking for | Read |
|---|---|
| **The design and testing document** (architecture decisions, patterns, deployment options and costs, testing strategy) | [DESIGN_NOTES.md](DESIGN_NOTES.md) |
| How to run the tests, and what they cover | [testing/README.md](testing/README.md) |
| User stories, acceptance criteria and delivery status | [BACKLOG.md](BACKLOG.md) |
| What happened in each sprint | [sprint-reports/](sprint-reports/) |
| Why the platform choices were made | [decisions/](decisions/) |
| How deployment works | [ci-cd/zero-trust-pipeline.md](ci-cd/zero-trust-pipeline.md), [deploy/README.md](../deploy/README.md) |

## Directory structure

- `architecture/` – system, bounded-context and end-to-end architecture diagrams
- `ci-cd/` – zero-trust deploy pipeline (SSM, ECR, EC2) and architecture diagram
- `decisions/` – architecture decision records
- `meeting-minutes/` – where the team's decision record actually lives (see the note there)
- `requirements/` – index of the product definition
- `sprint-reports/` – per-sprint planning, delivery and retrospective
- `testing/` – testing strategy, procedure and quality evidence

## Standalone documents

- [BACKLOG.md](BACKLOG.md) – epics, user stories, acceptance criteria, status
- [DESIGN_NOTES.md](DESIGN_NOTES.md) – the design and testing document
- [GIT_WORKFLOW.md](GIT_WORKFLOW.md) – branching, commits, review
- [RELEASE_STRATEGY.md](RELEASE_STRATEGY.md) – semantic-release and versioning
- [INTEGRATION_CHECKLIST.md](INTEGRATION_CHECKLIST.md) / [INTEGRATION_VERIFICATION_REPORT.md](INTEGRATION_VERIFICATION_REPORT.md)
- [architecture-review-2026-08-01.md](architecture-review-2026-08-01.md) – recorded architecture review
- [TrustAI Wireframes.pdf](TrustAI%20Wireframes.pdf) – approved wireframes

Documentation is updated in the same pull request as the code it describes.
