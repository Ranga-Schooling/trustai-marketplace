# TrustAI Marketplace — Git Workflow

**Audience:** whole team 
**Status:** agreed for team use — please follow from the next task onward

This document defines how we branch, review, and merge. The goal is a simple, consistent process that protects `main`.

---

## 1. Branch model

We use **one long-lived branch**:

| Branch | Purpose |
|--------|---------|
| `main` | Shared integration branch. Only merged, reviewed code goes here. |

There is **no `develop` branch** for now.

**Work flow:**

```text
Trello card
  → create a short-lived branch from main
  → open a Pull Request into main
  → get 1 review + green CI
  → squash-merge
```

**Rules:**

- Do **not** commit or push directly to `main`.
- Every change goes through a Pull Request.
- Branches are short-lived. Delete them after merge.

---

## 2. Branch naming

Our tasks live on **Trello** (no ticket numbers), so branch names use a **short version of the card title**.

### Format

```text
<type>/<short-description>
```

### Types

| Type | Use for |
|------|---------|
| `feature/` | New functionality |
| `fix/` | Bug fix |
| `chore/` | Tooling, deps, cleanup (no user-facing change) |
| `docs/` | Documentation only |
| `ci/` | CI/CD or GitHub Actions changes |
| `test/` | Tests only |

### Rules

- Lowercase only
- Words separated by hyphens (`-`)
- Keep it short (about 3–6 words)
- Match the Trello card closely so the team can recognize the work

### Examples

| Trello card | Branch name |
|-------------|-------------|
| User login and registration | `feature/user-login` |
| Submit marketplace listing | `feature/listing-submit` |
| Risk score crashes on empty price | `fix/risk-score-empty-price` |
| Update CI Python version | `ci/python-version` |
| Git workflow document | `docs/git-workflow` |

---

## 3. Starting work (checklist)

1. Take / confirm the Trello card.
2. Update local `main`:

   ```bash
   git checkout main
   git pull origin main
   ```

3. Create your branch:

   ```bash
   git checkout -b feature/short-description
   ```

4. Commit as you work (see section 4).
5. Push and open a Pull Request into `main`.
6. Paste the **Trello card link** in the PR description.
7. Request review from at least one teammate.
8. Wait for CI to pass.
9. After approval, squash-merge and move the Trello card.

---

## 4. Commit messages

Prefer [Conventional Commits](https://www.conventionalcommits.org/) so history stays readable:

```text
<type>: <short summary>
```

Examples:

- `feat: add JWT login endpoint`
- `fix: handle missing price in risk score`
- `docs: add git workflow for the team`
- `ci: run frontend build on pull requests`
- `chore: update postgres compose settings`

Keep the summary short and focused on **why** the change exists.

---

## 5. Pull Requests and review

### Required before merge

- [ ] PR targets `main`
- [ ] Branch name follows the convention above
- [ ] Trello card link is in the PR description
- [ ] At least **one approving review**
- [ ] **CI is green** (backend tests + frontend build)
- [ ] No secrets committed (`.env` stays local)

### Merge style

- Use **Squash and merge**
- Delete the branch after merge

### What reviewers should check

- Does the change match the Trello card?
- Are tests updated or un-skipped where this story requires it?
- Does anything break the shared API contract / schemas?
- Is the PR small enough to review?

---

## 6. Continuous Integration

GitHub Actions runs on:

- every Pull Request
- every push to `main`

Current checks:

- Backend: `pytest`
- Frontend: production build

**Do not merge with failing CI.**

Deployment hosting (for example GitHub Pages, Render, or a VPS) will be decided and documented separately. This workflow only requires that changes reach `main` through review + CI.

---

## 7. What not to do

- Do not push straight to `main`
- Do not merge your own PR without a review (except documented emergencies — ask DevOps first)
- Do not leave feature branches open for multiple sprints
- Do not commit `.env`, API keys, or credentials
- Do not weaken failing tests just to get CI green — fix the code or bring it to the team

---

## 8. Quick reference

| Topic | Decision |
|-------|----------|
| Long-lived branch | `main` only |
| Task tracking | Trello |
| Branch name | `type/short-trello-name` |
| Review | At least 1 approval |
| CI | Must be green |
| Merge | Squash and merge |

---
