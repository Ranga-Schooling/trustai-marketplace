# Release Strategy

This project uses **semantic-release** on `main` for automated versioning and release management during active development.

## Development Versioning

The project starts at version **0.1.0** and follows **semantic versioning** with 0.x.y numbering until feature-complete:

- `0.1.0`, `0.2.0`, `0.3.0`, ... (development releases)
- Later graduates to `1.0.0+` for production-ready stable releases

## How It Works

### Conventional Commits Trigger Releases

All commits must follow [conventional commit](https://www.conventionalcommits.org/) format:

- `feat:` → minor version bump (e.g., `0.1.0` → `0.2.0`)
- `fix:` → patch version bump (e.g., `0.2.0` → `0.2.1`)
- `BREAKING CHANGE:` → major version bump (e.g., `0.2.0` → `1.0.0`)
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
6. Tags the commit with the version (e.g., `v0.2.0`)
7. Commits version bump + changelog back to `main`

## Workflow Examples

### Example 1: Adding a Feature

```bash
git checkout -b feat/new-risk-analysis
# Make changes with "feat: add risk score analysis" commits
git push origin feat/new-risk-analysis
# Create PR, review, merge
# → GitHub Actions automatically creates v0.2.0 release
```

### Example 2: Fixing a Bug

```bash
git checkout -b fix/critical-timeout
# Make fix with "fix: resolve AI provider timeout" commit
git push origin fix/critical-timeout
# Create PR, review, merge
# → GitHub Actions automatically creates v0.2.1 patch release
```

### Example 3: Breaking Changes

When making API-breaking changes, use `BREAKING CHANGE:` in commit:

```
feat: redesign analysis API

BREAKING CHANGE: /analyze endpoint now requires authentication
```

This triggers a major version bump (e.g., `0.2.0` → `1.0.0`).

## Important Notes

- **No manual versioning**: Never edit `package.json` version manually. Let semantic-release handle it.
- **Every push to `main` may trigger a release**: Make sure all commits follow conventional format.
- **Prerelease strategy**: Once the app is production-ready, merge the commit that bumps to `1.0.0+` to transition out of 0.x.y versioning.
- **Changelog**: Review `CHANGELOG.md` after each release—it's auto-generated but should read clearly.

## For Contributors

1. Always use conventional commit format: `type(scope): message`
   - Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
   - Example: `feat(api): add listing recommendation endpoint`

2. Submit PRs to `main` for review.

3. Once approved and merged, GitHub Actions creates a release automatically—no manual tagging needed.

4. If you need to revoke a release, delete the tag and GitHub Release manually, then reset or amend the commit.

## GitHub Token Permissions

The workflow requires `contents: write` to:
- Create releases and tags
- Commit version + changelog updates back to `main`

This uses the default `GITHUB_TOKEN` and requires no additional secrets.

