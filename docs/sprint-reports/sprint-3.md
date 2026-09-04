# Sprint 3 — Hardening and depth

**Dates:** 18 August – 2 September 2026
**Merged pull requests:** 20
**Contributors:** four of five team members (@amooch's contributions
concluded in Sprint 2)

> Reconstructed from repository history on 2026-09-04. See the
> [note on how these reports were produced](README.md#a-note-on-how-these-reports-were-produced).

## Sprint goal

Move from "it works" to "it holds up": constrain what the AI is allowed to
claim, add administrative capability, fix the production issues the live
deployment had begun to surface, and raise frontend quality to the level of
the backend.

## Selected backlog items

| Item | Tracked as |
|---|---|
| Admin RBAC + analytics dashboard | issue #42, D-15 |
| AI evidence and knowledge-boundary policy | D-17, D-19 |
| Recover listings after a failed analysis | issue #80 |
| Production reliability: disk exhaustion, backup repair | D-16, D-18 |
| UI quality: dark mode, mobile, contrast, gauge geometry | — |

## Completed work

**Constraining the AI — the sprint's intellectual core.** Three related
changes tightened what the analysis is permitted to assert: clarifying
text-only analysis evidence so the model cannot imply it inspected images
(PR #85), guarding against stale model knowledge (PR #87), and rejecting
unsupported risk evidence outright (PR #90). This line of work concluded with
the Terra integration and its strict response validation (PR #107, #108,
D-21), backed by a dedicated 377-line validation test module.

**Admin capability.** Role-based access control with an analytics dashboard
(PR #91, D-15), closing the larger part of issue #42. Runtime provider
switching was split out as issue #92 and deliberately left open.

**Visual Inspection** (PR #99, D-20) — optional, transient photo analysis
that never persists images and never alters the text analysis, risk level or
recommendation. Merged **disabled by default** pending credentialed provider
evaluation, and documented as such rather than quietly shipped.

**Production reliability.** Automated EC2 disk cleanup on every deployment
(PR #84, D-16) after accumulated SHA-tagged images filled the instance disk;
a follow-up repair to the cleanup itself (PR #93); and repair of the Postgres
backup workflow (PR #89).

**Frontend quality.** Dark mode (PR #105), mobile responsiveness (PR #95),
auth tab contrast (PR #96), risk gauge geometry (PR #94), listing retry state
isolation (PR #106), and mid-session token expiry state sync (PR #98). Each
shipped with component tests — the Sprint 2 retrospective action, carried
out.

**Process automation.** gitStream configuration for PR routing (PR #83).

## Incomplete at sprint end

Four items were consciously left open rather than rushed, and are recorded in
[BACKLOG.md](../BACKLOG.md#known-open-items-at-submission):

| Item | Issue | Why left open |
|---|---|---|
| Retired `gemini-2.0-flash` default | #97 | Provider-lifecycle defect; production does not use Gemini |
| Runtime provider switching | #92 | Split from #42; needs its own design |
| Backup recovery verification | #88 | Backups run; a restore has not been rehearsed |
| Password change + re-authentication | #66 | Security-sensitive; not MVP scope |

## Blockers and how they were resolved

**The production instance ran out of disk.** Every deploy left behind a
uniquely SHA-tagged image, and the original cleanup step (`docker image prune
-f`) removed only *dangling* images — so nothing was ever reclaimed. Fixed in
PR #84 and hardened in PR #93 by pruning before pull, so a full host can
recover enough space to download the next images. Recorded as D-16 and D-18.

## Demonstration evidence

No sprint demonstration was recorded. The application was continuously live
at **https://trustai.mandalawi.ca** throughout the sprint.

## Retrospective

**What worked.** The Sprint 2 action item held: every UI change in this
sprint shipped with component tests, and frontend coverage went from
smoke-level to 76 tests across 9 files. Final measured state is 449 backend
tests at 96% coverage plus 76 frontend tests.

**What worked less well.** Contribution became uneven — 11 of 20 PRs came
from one member, and one member did not contribute during the sprint. The
team did not redistribute work in response.

**What the team would do differently.** Record sprint demonstrations. Three
sprints produced a genuinely demonstrable product at every boundary and none
of it was captured, which is the one process requirement the project did not
meet.
