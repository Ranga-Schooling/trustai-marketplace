# TrustAI Marketplace Documentation

This directory contains product, engineering, delivery, and Capstone evidence for TrustAI Marketplace.

## Final submission entry point

Start with [the Capstone evidence portal](capstone/README.md). It identifies the immutable final release, separates verified evidence from open submission work, and links the page-indexed [Handbook requirements](capstone/HANDBOOK_REQUIREMENTS_INDEX.md), final timeline, production-validation record, sprint/meeting indexes, and authoritative evidence matrix.

## Documentation map

- [`capstone/`](capstone/) — final grader-facing evidence package and closure status.
- [Canonical Trello board](https://trello.com/b/wUqCGA2T) — final board state reconciled during submission closeout; the board is Private and requires explicit membership.
- [`BACKLOG.md`](BACKLOG.md) — user stories, priorities, acceptance criteria, and implementation traceability.
- [`DESIGN_NOTES.md`](DESIGN_NOTES.md) — chronological design decisions and scope changes.
- [`architecture/`](architecture/) — architecture source material; some plan-era pages require historical labeling in the final report.
- [`ci-cd/`](ci-cd/) — AWS/ECR/Systems Manager deployment design and operational evidence.
- [`decisions/`](decisions/) — architecture decision records; older ADRs describe the decision at that time and are not silently rewritten to match later deployment choices. [ADR-003](decisions/ADR-003-aws-ec2-deployment.md) retrospectively records the incremental AWS deployment evolution.
- [`meeting-minutes/`](meeting-minutes/) — historical meeting-record conventions; the six canonical dated PDFs and their evidence index are under [`capstone/meetings/`](capstone/meetings/).
- [`requirements/`](requirements/) — product vision, scope, user stories, and acceptance criteria.
- [`sprint-reports/`](sprint-reports/) — sprint-planning and reporting material where present.
- [`testing/`](testing/) — test strategy and engineering evidence; the final Capstone report must reconcile any pre-release statements with `v1.20.0`.

## Evidence conventions

- A plan or decision record establishes intent, not implementation.
- Source and tests establish implemented behavior, not production deployment.
- A release identifies immutable source.
- A successful deployment workflow establishes image identity and health checks, not a complete live user journey or real-provider transaction.
- External meeting, sprint, and recording evidence is not grader-ready until it is linked or imported and its access is verified.
- The Trello board is now canonically linked and its final state has been reconciled against `v1.20.0`; this closeout work does not prove perfect contemporaneous maintenance, and grader access to the Private board remains OPEN. The Handbook requires an accessible board link but does not prescribe public visibility or a named Trello account.

The final documentation must preserve these distinctions and label historical records rather than rewriting them from the perspective of the finished product.
