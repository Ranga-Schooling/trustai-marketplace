# TrustAI Marketplace – Integration Checklist

## Current Repository Status (2026-08-02)

### Merged
- [x] E3 AI Analysis
- [x] Docker startup fixes
- [x] Login / Logout UI
- [x] Frontend skeleton
- [x] API proxy refactor
- [x] CI / Release workflow

---

## Open Pull Requests

- [ ] PR #21 – Listing URL Preview
- [ ] PR #24 – View / Edit Profile
- [ ] PR #25 – Auth UI Wireframe Alignment
- [ ] PR #26 – Unit Test Foundations
- [ ] PR #29 – App Shell / Landing Page
- [ ] PR #30 – Listing Form Refactor
- [ ] PR #31 – Analysis Result Refactor
- [ ] PR #32 – History Table Refactor
- [ ] PR #34 – Architecture Review

---

## Before Deployment

### Repository

- [ ] Decide whether to transfer repository to a GitHub Organization
- [ ] Finalize repository ownership
- [ ] Protect main branch

### Integration

- [ ] Merge remaining approved PRs
- [ ] Resolve merge conflicts
- [ ] Rebase outdated branches if necessary
- [ ] Confirm GitHub Actions passes

### Functional Testing

Authentication

- [ ] Register
- [ ] Login
- [ ] Logout
- [ ] Invalid credentials

Listing Workflow

- [ ] Submit listing
- [ ] AI analysis completes
- [ ] Validation errors
- [ ] URL Preview (PR21)

History

- [ ] History page
- [ ] View previous analysis

Profile

- [ ] Edit profile
- [ ] Validation
- [ ] Duplicate email handling

Frontend

- [ ] Landing page
- [ ] Listing form
- [ ] Analysis results
- [ ] History UI
- [ ] Responsive layout

Deployment

- [ ] Configure Render
- [ ] Configure backend environment variables
- [ ] Configure frontend environment variables
- [ ] Connect custom domain
- [ ] Production smoke test

Documentation

- [ ] README
- [ ] Meeting minutes
- [ ] AI model decision log
- [ ] Deployment guide
- [ ] Final architecture review
