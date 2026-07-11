# ADR-001: Deployment Platform

## Status

Accepted

## Date

July 10, 2026

## Context

TrustAI Marketplace requires more than static web hosting. The planned application includes:

- a React frontend
- a FastAPI backend
- PostgreSQL persistence
- user authentication
- AI-assisted listing analysis
- automated testing and continuous deployment

GitHub Pages was considered initially because it is simple, free, and already familiar to the Product Owner. However, GitHub Pages is intended for static frontend content and cannot run the FastAPI backend or PostgreSQL database required by the complete application.

Using GitHub Pages for the frontend would therefore require separate platforms for the backend and database. The team wants to reduce deployment complexity and maintain a reliable environment for sprint demonstrations and final grading.

## Decision

The project will continue to use GitHub for:

- source control
- branches and pull requests
- peer reviews
- project documentation
- GitHub Actions
- collaboration and submission access

Render will be used as the deployment platform for the application.

The initial deployment will consist of:

- a React frontend deployed as a Render Static Site
- a FastAPI backend deployed as a Render Web Service
- a managed PostgreSQL database
- environment variables for credentials and service configuration

## Rationale

This approach gives the team one primary deployment platform for the frontend, backend, and database while keeping GitHub as the source of truth.

The decision is intended to:

- simplify deployment and troubleshooting
- support the complete application architecture
- enable automated deployments from GitHub
- provide a reliable environment for demonstrations
- avoid mixing the capstone project with any unrelated personal repository
- reduce the risk of late integration and hosting problems

## Consequences

### Positive

- The complete application can be hosted without forcing backend functionality into a static platform.
- GitHub remains the team's collaboration and submission platform.
- Render can deploy approved changes from the GitHub repository.
- Frontend, backend, and database resources can be managed together.
- The project can use a dedicated project URL without changing any unrelated website.

### Trade-offs

- Paid hosting will introduce a small recurring cost.
- The team must configure environment variables, database connectivity, CORS, and service health checks.
- Render configuration and ownership must be documented so the deployment is not dependent on one person's memory.
- The repository and application architecture must remain portable in case another provider is needed later.

## Ownership

- Product and architecture decision: Ahmed Al-Mandalawi
- Deployment and CI/CD implementation: QA and DevOps workstream
- Backend and database integration: Backend workstream
- Frontend deployment integration: Frontend workstream

## Review Point

The team will review this decision after the first successful end-to-end deployment and before committing to final paid service tiers.
