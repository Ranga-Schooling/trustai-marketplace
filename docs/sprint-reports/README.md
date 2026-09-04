# Sprint Reports

TrustAI Marketplace ran **three sprints** between 15 July and 2 September 2026.

| Sprint | Dates | Goal | Merged PRs | Report |
|---|---|---|---|---|
| 1 | 15 Jul – 1 Aug 2026 | Foundations: repository, CI/CD, authentication, data model, containerized dev environment | 24 | [sprint-1.md](sprint-1.md) |
| 2 | 2 Aug – 17 Aug 2026 | The product itself: AI analysis, risk scoring, history, and a real deployment | 37 | [sprint-2.md](sprint-2.md) |
| 3 | 18 Aug – 2 Sep 2026 | Hardening and depth: admin RBAC, provider robustness, UI polish, production incident fixes | 20 | [sprint-3.md](sprint-3.md) |

## A note on how these reports were produced

These reports were **written on 2026-09-04 by reconstructing each sprint from
the repository's own records** — merged pull requests and their review
threads, the release history produced by semantic-release, the architecture
decision records, and the dated design decisions in
[DESIGN_NOTES.md](../DESIGN_NOTES.md).

They were not written contemporaneously at each sprint boundary. The team
planned and reviewed each sprint on the
[Trello board](https://trello.com/b/wUqCGA2T/trustai-marketplace-sprint-retrospective-board)
and in weekly calls, but did not produce written sprint reports at the time.
This is recorded here rather than presented as though the documents had
always existed.

Every fact in these reports is traceable to an artifact in this repository or
its GitHub project — PR numbers, issue numbers, release tags and commit dates
are cited throughout so any claim can be checked.

## Retrospective on the team's own process

The gap that produced this note is itself the clearest process finding of the
project. The team's *engineering* process evidence is unusually strong —
every change went through a pull request with review, CI gated every merge,
releases were automated, and decisions were recorded as they were made. The
*ceremony* evidence was weaker: sprint boundaries were real and observable in
the history, but they were never written down, and no sprint demonstration
was recorded.

The practical lesson, stated plainly because it is the honest one: a team
that documents decisions well can still fail to document process, because
decisions feel like engineering work and ceremony does not. A recurring
calendar item that produces a dated file — however short — would have cost
minutes per sprint and removed the need to reconstruct anything.
