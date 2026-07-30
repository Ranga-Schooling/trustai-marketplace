# ADR-002: Repository Ruleset for `main` (Replacing Classic Branch Protection)

## Status

Accepted

## Date

July 27, 2026

## Context

ADR-001 anticipated the release bot needing to bypass branch protection:
"Configure the branch protection rule for `main` so the app/user can bypass
required status checks for automated release commits." That configuration
was implemented using GitHub's **classic branch protection rules**, with the
`trustai-release-bot` GitHub App added to `required_pull_request_reviews.
bypass_pull_request_allowances` and to the push `restrictions` allow-list.

In practice this was not sufficient. `@semantic-release/git` needs to push a
version-bump commit (`CHANGELOG.md`, `package.json`, `package-lock.json`)
directly to `main` after a successful run. Every attempt failed with `GH006:
Protected branch update failed`, citing both the PR requirement and the 2
required status checks (`backend`, `frontend`).

Investigation established that classic branch protection has no per-actor
bypass for required status checks — `bypass_pull_request_allowances` only
exempts an actor from the pull-request/review requirement, never from status
checks. This is a documented GitHub platform limitation, not a
misconfiguration: see [GitHub Community Discussion
#43460](https://github.com/orgs/community/discussions/43460) and [#48232](https://github.com/orgs/community/discussions/48232).
It's also structurally unsatisfiable for this use case regardless of bypass
settings — a commit freshly created by the release job has never run through
CI, so it can never have already-passing status checks before the push that
creates it.

GitHub's newer **Repository Rulesets** feature supports a bypass list that
covers *all* rules in the ruleset, including required status checks, for a
named actor.

## Decision

Replace classic branch protection on `main` with a Repository Ruleset
(`main-protection`, id `19802987`) enforcing the same rules — require a
pull request with 1 approval, require the `backend` and `frontend` status
checks, linear history, no force-pushes, no deletions — plus a bypass entry
for the `trustai-release-bot` GitHub App (`bypass_mode: always`). The
classic branch protection rule on `main` was deleted so it no longer
double-enforces status checks the ruleset already governs.

## Rationale

- Preserves every protection ADR-001 intended for human/PR-driven changes:
  humans and non-bypassed actors still cannot push directly to `main`,
  still need 1 approval and 2 green checks.
- Grants the one automated actor that legitimately needs to push directly
  (the release bot, immediately after CI has already validated the commits
  it's bundling) an explicit, auditable, narrowly-scoped exception, rather
  than weakening the checks for everyone.
- Keeps `main-protection` as the single source of truth for `main`'s rules;
  running classic protection and a ruleset simultaneously would not have
  worked, since classic protection has no bypass mechanism for status
  checks and would still reject the release bot's push on its own.

## Consequences

### Positive

- Automated releases work end-to-end: verified live by re-running the
  previously-failing workflow, which pushed `chore(release): 1.0.0`, tagged
  `v1.0.0`, and published the [GitHub
  Release](https://github.com/Ranga-Schooling/trustai-marketplace/releases/tag/v1.0.0).
- No reduction in protection for any other actor — the ruleset is a 1:1
  translation of the prior classic rules plus the one bypass entry.

### Trade-offs

- Rulesets and classic branch protection are configured through different
  GitHub UI screens (Settings → Rules → Rulesets, not Settings → Branches);
  future contributors changing `main`'s protection need to know to look
  there.
- The bypass is `always`, not scoped to `chore(release):`-shaped commits
  specifically — GitHub rulesets bypass by actor, not by commit content.
  The release bot's only write access is via its installation token used
  in `release.yml`, so the practical exposure is limited to that workflow.

## Verification

- `gh api repos/Ranga-Schooling/trustai-marketplace/rulesets/19802987`
  confirms the ruleset is `active` with the bypass actor attached.
- `gh api repos/Ranga-Schooling/trustai-marketplace/branches/main/protection`
  returns 404 (`Branch not protected`), confirming classic protection was
  removed and is not silently still enforcing anything.
- Release workflow run
  [30229824455](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/30229824455)
  succeeded after this change; the resulting `chore(release): 1.0.0` push
  triggered a normal green CI run
  ([30250878723](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/30250878723)).

## Related

- ADR-001 (Deployment Platform) — originated the bypass requirement this
  ADR resolves.
