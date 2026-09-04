# Product Requirements

The product definition for TrustAI Marketplace lives in the documents below.
This directory is an index; it does not duplicate them.

| Requirement artifact | Location |
|---|---|
| Product vision and goals | [README.md — Product Goals](../../README.md#product-goals) |
| MVP scope and explicit out-of-scope items | [README.md — MVP Scope](../../README.md#mvp-scope) |
| Epics, user stories and acceptance criteria | [BACKLOG.md](../BACKLOG.md) |
| Live task board (per-task status and ownership) | [Trello](https://trello.com/b/wUqCGA2T/trustai-marketplace-sprint-retrospective-board) |
| Analysis output contract (frozen, SCHEMA-0) | [`backend/app/schemas/schemas.py`](../../backend/app/schemas/schemas.py), rationale at [DESIGN_NOTES.md](../DESIGN_NOTES.md) |
| Non-functional constraints and known limitations | [DESIGN_NOTES.md — Known limitations](../DESIGN_NOTES.md#known-limitations) |
| Wireframes | [TrustAI Wireframes.pdf](../TrustAI%20Wireframes.pdf) |

## Requirements that became binding constraints

Two product requirements were frozen early and enforced in code and tests,
rather than left as prose:

- **Risk is categorical, never numeric** (D-05). No AI provider is ever asked
  for or returns a score, percentage or confidence number. `test_contract.py`
  asserts structurally that `AIAnalysisResult` contains no numeric field,
  including in nested models — so this requirement cannot regress silently.
- **The API surface is frozen** (SCHEMA-0). Route paths, status codes and
  response models are contract-tested; changing one is a deliberate act
  requiring its own pull request and a decision-log entry.

The single approved exception is `AnalysisOut.risk_score` (D-09), a 0–100
value computed server-side by a pure function from the already-validated
categorical result — never by an LLM.
