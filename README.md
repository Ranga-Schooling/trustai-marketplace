# TrustAI Marketplace

TrustAI Marketplace is an AI-assisted web application designed to help online buyers make safer and more informed purchasing decisions.

Users will be able to submit a marketplace listing, product description, or URL and receive a structured assessment that highlights potential scam indicators, evaluates whether the asking price appears plausible, and provides practical guidance before contacting the seller or making a payment.

This project is being developed as part of the Quantic Master of Science in Software Engineering (MSSE) Capstone Project.

> TrustAI Marketplace is a decision-support tool. It does not guarantee that a listing or seller is legitimate, and users should still perform their own checks before completing a transaction.

---

## Capstone Deliverables

| Deliverable | Link |
|---|---|
| **Live application** | **https://trustai.mandalawi.ca** |
| **Agile task board** (Trello) | **https://trello.com/b/wUqCGA2T/trustai-marketplace-sprint-retrospective-board** |
| Design & testing document | [docs/DESIGN_NOTES.md](docs/DESIGN_NOTES.md) — architecture decisions, patterns, deployment recommendation and cost analysis, testing strategy |
| Testing guide and evidence | [docs/testing/README.md](docs/testing/README.md) |
| User story backlog | [docs/BACKLOG.md](docs/BACKLOG.md) |
| Sprint reports | [docs/sprint-reports/](docs/sprint-reports/) |
| Architecture decision records | [docs/decisions/](docs/decisions/) |

The live application is deployed on AWS EC2 behind Caddy, which terminates
HTTPS with an automatically renewed Let's Encrypt certificate. Deployment is
fully automated from `main` — see [deploy/README.md](deploy/README.md) and
[docs/ci-cd/zero-trust-pipeline.md](docs/ci-cd/zero-trust-pipeline.md).

---

## Product Goals

The project aims to:

- Help buyers identify suspicious or high-risk marketplace listings
- Present scam indicators in a clear and understandable way
- Assess whether an asking price appears plausible based on the available listing information
- Provide an overall risk score and purchasing recommendation
- Suggest useful questions for buyers to ask sellers
- Maintain a history of previous analyses for registered users
- Demonstrate the software engineering practices covered throughout the MSSE program

---

## MVP Scope

The MVP is complete and deployed. It includes:

- User registration and login
- Submission of listing text, URLs, or structured product details
- Listing validation, normalization, and storage
- AI-assisted scam and risk analysis
- A risk score with an explanation of the main warning signs
- Price-plausibility classification
- An overall recommendation such as:
  - Proceed
  - Proceed with caution
  - Avoid
- Suggested questions and next steps for the buyer
- User analysis history
- Automated testing and continuous integration
- A publicly accessible deployed application

### Optional Visual Inspection

Authenticated users can optionally add one to three JPEG, PNG, or WebP photos
to an existing completed analysis. Visual Inspection reports observations
grounded in visible photo evidence as a separate advisory channel; it does not
change the text analysis, Trust score, risk level, or Buy/Caution/Avoid
recommendation. TrustAI does not persist uploaded photos or Visual Inspection
findings.

Visual Inspection is merged to `main` and validated through automated tests and
deterministic local frontend QA. It is **disabled by default**
(`VISUAL_INSPECTION_PROVIDER=disabled`) and is not enabled on the deployed
instance, because it has not completed credentialed provider evaluation. See
[D-20 in the design notes](docs/DESIGN_NOTES.md) for the detailed architecture,
privacy, and security rationale.

### Outside the Initial MVP

The following features may be considered later if the core application is complete and stable:

- Automatic retrieval, scraping, or inspection of marketplace listing photos;
  V1 requires users to explicitly select and upload photos
- Browser extensions
- Direct marketplace integrations
- Mobile applications
- Payment processing
- Real-time seller monitoring
- Precise market-value estimates based on large-scale marketplace scraping

---

## Architecture

The MVP uses a containerized architecture consisting of:

- A React frontend, served by nginx
- A FastAPI backend
- A PostgreSQL database
- Docker Compose for running the application services together
- Caddy as the reverse proxy and HTTPS manager
- A single AWS EC2 instance for the deployed environment

The deployment setup is documented in this repository ([deploy/README.md](deploy/README.md))
so that it can be reproduced by more than one team member. Architecture
diagrams are in [docs/architecture/](docs/architecture/), and the decisions
behind these choices — including why the platform moved from Render to AWS —
are recorded in [docs/decisions/](docs/decisions/).

GitHub will remain the source of truth for:

- Source code
- Branches and pull requests
- Peer reviews
- Project documentation
- Automated testing
- CI/CD workflows
- Deployment configuration

---

## Technology Stack

### Frontend

- React (JavaScript/JSX)
- Vite
- Vitest + React Testing Library

### Backend

- Python
- FastAPI

### Database

- PostgreSQL

### AI Integration

- Provider-independent LLM integration
- Deterministic mock responses for development and automated testing
- Structured prompts and rule-based indicators for explainable results

### Testing

- Pytest (unit, acceptance, integration and contract layers)
- Vitest + React Testing Library for frontend component tests
- Automated quality checks through GitHub Actions, with a coverage floor

### Deployment and Infrastructure

- Docker
- Docker Compose
- Caddy (HTTPS termination, automatic Let's Encrypt certificates)
- AWS EC2 for the deployed MVP, with images published to Amazon ECR
- AWS Systems Manager (SSM) for keyless deployment — no inbound SSH
- GitHub Actions for CI/CD

### Project Management and Collaboration

- GitHub
- Trello
- Slack

---

## Development & Testing

Quick start — full walkthrough (manual smoke test checklist, Docker
gotchas, etc.) is in [docs/testing/README.md](docs/testing/README.md).

**Backend tests:**
```bash
cd backend
python -m venv .venv && pip install -r requirements-dev.txt
python -m pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=85
```

**Frontend tests and build:**
```bash
cd frontend
npm install && npm run test:ci && npm run build
```

**Full stack (Docker Compose):**
```bash
docker compose up --build
```
Then visit `http://localhost:5173`.

CI (`.github/workflows/ci.yml`) runs both the backend suite (against the
mock AI provider, no secrets required) and the frontend build on every
push and pull request; a PR can't merge with either red.

---

## Repository Structure

The repository is organized into the following main areas:

```text
trustai-marketplace/
├── frontend/               # React web application
├── backend/                # FastAPI application and business logic
├── docs/                   # Project and engineering documentation
│   ├── architecture/       # System, bounded-context and E2E diagrams
│   ├── ci-cd/              # Zero-trust deploy pipeline documentation
│   ├── decisions/          # Architecture decision records (ADRs)
│   ├── requirements/       # Product requirements index
│   ├── sprint-reports/     # Per-sprint planning, delivery and retrospective
│   └── testing/            # Testing strategy and quality evidence
├── deploy/                 # Production Compose file, Caddyfile, deploy runbook
├── .github/
│   └── workflows/          # CI/CD workflows
├── docker-compose.yml      # Local development service orchestration
├── README.md
└── LICENSE