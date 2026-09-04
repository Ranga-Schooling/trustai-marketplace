# Meeting Records

**The team did not keep formal written minutes.** This is stated plainly
rather than left as an empty directory implying otherwise.

Team coordination happened in weekly calls and in Slack. What was *decided*
was recorded, consistently and at the time — but in engineering artifacts
rather than in minutes. For a reader looking for the team's decision record,
these are the places it actually lives:

| Decision record | Where |
|---|---|
| Platform and governance decisions | [ADRs](../decisions/) — deployment platform (ADR-001, superseded by ADR-003), branch protection ruleset (ADR-002) |
| Design decisions, numbered and dated as taken (D-01 … D-21) | [DESIGN_NOTES.md](../DESIGN_NOTES.md) |
| A recorded architecture review with findings and actions | [architecture-review-2026-08-01.md](../architecture-review-2026-08-01.md) |
| Integration decisions and verification | [INTEGRATION_CHECKLIST.md](../INTEGRATION_CHECKLIST.md), [INTEGRATION_VERIFICATION_REPORT.md](../INTEGRATION_VERIFICATION_REPORT.md) |
| Per-change discussion, review and rationale | Pull request threads — every change to `main` went through one, with at least one required approval |
| Sprint-level planning and outcomes | [sprint-reports/](../sprint-reports/) (reconstructed 2026-09-04) |
| Task-level status and ownership | [Trello board](https://trello.com/b/wUqCGA2T/trustai-marketplace-sprint-retrospective-board) |

## Why this gap exists

The team treated a decision as recorded once it was written into an ADR, a
numbered design decision, or a PR discussion — all of which are durable,
reviewable and close to the code they affect. That reasoning is defensible
for *decisions* and produced an unusually detailed decision history. It does
not, however, produce evidence of the meetings themselves: attendance,
discussion, action items and their owners.

The honest summary is that the team documented its engineering thoroughly and
its process informally.
