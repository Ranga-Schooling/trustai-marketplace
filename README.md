# TrustAI Marketplace

TrustAI Marketplace is an AI-assisted web application designed to help online buyers make safer and more informed purchasing decisions.

Users will be able to submit a marketplace listing, product description, or URL and receive a structured assessment that highlights potential scam indicators, evaluates whether the asking price appears plausible, and provides practical guidance before contacting the seller or making a payment.

This project is being developed as part of the Quantic Master of Science in Software Engineering (MSSE) Capstone Project.

> TrustAI Marketplace is a decision-support tool. It does not guarantee that a listing or seller is legitimate, and users should still perform their own checks before completing a transaction.

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

The first working version of TrustAI Marketplace is expected to include:

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

### Outside the Initial MVP

The following features may be considered later if the core application is complete and stable:

- Image-based listing analysis
- Browser extensions
- Direct marketplace integrations
- Mobile applications
- Payment processing
- Real-time seller monitoring
- Precise market-value estimates based on large-scale marketplace scraping

---

## Planned Architecture

The MVP will use a containerized architecture consisting of:

- A React frontend
- A FastAPI backend
- A PostgreSQL database
- Docker Compose for running the application services together
- Caddy as the reverse proxy and HTTPS manager
- A single VPS for the initial deployed environment

The deployment setup will be documented and stored in this repository so that it can be reproduced by more than one team member.

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

- React
- TypeScript
- Vite

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

- Pytest
- API and integration testing
- Frontend testing
- End-to-end testing
- Automated quality checks through GitHub Actions

### Deployment and Infrastructure

- Docker
- Docker Compose
- Caddy
- Hetzner VPS for the MVP
- GitHub Actions for CI/CD

### Project Management and Collaboration

- GitHub
- Trello
- Slack

---

## Repository Structure

The repository is organized into the following main areas:

```text
trustai-marketplace/
├── frontend/               # React web application
├── backend/                # FastAPI application and business logic
├── docs/                   # Project and engineering documentation
│   ├── architecture/
│   ├── decisions/
│   ├── meeting-minutes/
│   ├── requirements/
│   ├── sprint-reports/
│   └── testing/
├── .github/
│   └── workflows/          # CI/CD workflows
├── docker-compose.yml      # Local and deployed service orchestration
├── README.md
└── LICENSE