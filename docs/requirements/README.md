# Product Requirements

This directory is an index. The product definition lives in the documents
below and is not duplicated here.

| Requirement artifact | Location |
|---|---|
| Consolidated design and testing report | [docs/capstone/CAPSTONE_DESIGN_AND_TESTING.md](../capstone/CAPSTONE_DESIGN_AND_TESTING.md) |
| Epics, user stories, acceptance criteria, delivery status | [BACKLOG.md](../BACKLOG.md) |
| Product vision, scope and delivered capability | [README.md](../../README.md) |
| Live task board | [Trello](https://trello.com/b/wUqCGA2T) |
| Analysis output contract (frozen, SCHEMA-0) | [`backend/app/schemas/schemas.py`](../../backend/app/schemas/schemas.py) |
| Design decision log | [DESIGN_NOTES.md](../DESIGN_NOTES.md) |
| Wireframes | [TrustAI Wireframes.pdf](../TrustAI%20Wireframes.pdf) |

## Requirements that became binding constraints

Two product requirements were frozen early and enforced in code and tests
rather than left as prose:

- **Risk is categorical, never numeric** (D-05). No AI provider is asked for
  or returns a score, percentage or confidence number. `test_contract.py`
  asserts structurally that `AIAnalysisResult` contains no numeric field,
  including in nested models, so this cannot regress silently.
- **The API surface is frozen** (SCHEMA-0). Route paths, status codes and
  response models are contract-tested; changing one requires its own pull
  request and a decision-log entry.

The single approved exception is `AnalysisOut.risk_score` (D-09), a 0–100
value computed server-side by a pure function from the already-validated
categorical result — never by a model.
