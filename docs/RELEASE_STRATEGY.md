# Release Strategy

This project uses **semantic-release** on `main` for automated versioning and release management during active development.

## Versioning

The project starts at **1.0.0** and follows standard **semantic versioning**
from there:

- `1.0.0`, `1.1.0`, `1.2.0`, ... (`feat:` → minor)
- `1.0.1`, `1.0.2`, ... (`fix:` → patch)
- `2.0.0`, ... (`BREAKING CHANGE:` → major)

This project originally planned to start at `0.1.0` and stay in `0.x.y`
during active development, but semantic-release does not support an initial
release below `1.0.0` — with no prior tag, its first release is always
`1.0.0` regardless of commit type ([semantic-release
FAQ](https://semantic-release.org/support/faq/)). Rather than fight the
tool with a custom initial-version override, the project accepted `1.0.0`
as its actual starting point (see [ADR-002](decisions/ADR-002-branch-protection-ruleset.md)
for the related branch-protection work that unblocked the first release).

## How It Works

### Conventional Commits Trigger Releases

All commits must follow [conventional commit](https://www.conventionalcommits.org/) format:

- `feat:` → minor version bump (e.g., `1.0.0` → `1.1.0`)
- `fix:` → patch version bump (e.g., `1.1.0` → `1.1.1`)
- `BREAKING CHANGE:` → major version bump (e.g., `1.1.0` → `2.0.0`)
- `chore:`, `docs:`, `style:`, `test:` → no version bump (if only these)

### Merge Workflow

```
feature branch → PR to main → approve & merge → auto-release
```

When commits are merged to `main`, GitHub Actions automatically:
1. Analyzes commit messages since last release
2. Determines next semantic version
3. Updates `package.json` version
4. Generates `CHANGELOG.md` from commit messages
5. Creates a GitHub Release with auto-generated notes
6. Tags the commit with the version (e.g., `v1.1.0`)
7. Commits version bump + changelog back to `main`

## Workflow Examples

### Example 1: Adding a Feature

```bash
git checkout -b feat/new-risk-analysis
# Make changes with "feat: add risk score analysis" commits
git push origin feat/new-risk-analysis
# Create PR, review, merge
# → GitHub Actions automatically creates a minor release (e.g., v1.1.0)
```

### Example 2: Fixing a Bug

```bash
git checkout -b fix/critical-timeout
# Make fix with "fix: resolve AI provider timeout" commit
git push origin fix/critical-timeout
# Create PR, review, merge
# → GitHub Actions automatically creates a patch release (e.g., v1.1.1)
```

### Example 3: Breaking Changes

When making API-breaking changes, use `BREAKING CHANGE:` in commit:

```
feat: redesign analysis API

BREAKING CHANGE: /analyze endpoint now requires authentication
```

This triggers a major version bump (e.g., `1.1.0` → `2.0.0`).

## Important Notes

- **No manual versioning**: Never edit `package.json` version manually. Let semantic-release handle it.
- **Every push to `main` may trigger a release**: Make sure all commits follow conventional format.
- **Changelog**: Review `CHANGELOG.md` after each release—it's auto-generated but should read clearly.

## For Contributors

1. Always use conventional commit format: `type(scope): message`
   - Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
   - Example: `feat(api): add listing recommendation endpoint`

2. Submit PRs to `main` for review.

3. Once approved and merged, GitHub Actions creates a release automatically—no manual tagging needed.

4. If you need to revoke a release, delete the tag and GitHub Release manually, then reset or amend the commit.

## GitHub Token Permissions

The workflow needs to push the version-bump commit and tag directly to
protected `main`, which the default `GITHUB_TOKEN` cannot do. It instead
authenticates as the `trustai-release-bot` GitHub App (`tibdex/github-app-token`
in `release.yml`, secrets `RELEASE_APP_ID` / `RELEASE_APP_PRIVATE_KEY`),
which is the only actor allowed to bypass `main`'s ruleset — see
[ADR-002](decisions/ADR-002-branch-protection-ruleset.md).

