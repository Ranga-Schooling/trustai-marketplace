# TrustAI Marketplace

AI-assisted decision support for online marketplace buyers. Paste a listing or its URL and TrustAI returns a structured risk assessment — named scam indicators, a price-plausibility judgement, a deterministic 0–100 Trust score, a Buy / Caution / Avoid recommendation, and questions to ask the seller before paying.

[![CI](https://github.com/Ranga-Schooling/trustai-marketplace/actions/workflows/ci.yml/badge.svg)](https://github.com/Ranga-Schooling/trustai-marketplace/actions/workflows/ci.yml)
[![Deploy](https://github.com/Ranga-Schooling/trustai-marketplace/actions/workflows/deploy.yml/badge.svg)](https://github.com/Ranga-Schooling/trustai-marketplace/actions/workflows/deploy.yml)
[![Release](https://img.shields.io/github/v/release/Ranga-Schooling/trustai-marketplace)](https://github.com/Ranga-Schooling/trustai-marketplace/releases)

| | |
|---|---|
| **Live application** | **https://trustai.mandalawi.ca** |
| **Final Capstone presentation** | [Final Capstone Presentation (19:58) — Google Drive](https://drive.google.com/file/d/12FEx0J6LJ7DSQhFx62VkCf6raG5ijkon/view?usp=sharing). For the original 4K-quality video, download the file from Google Drive; browser playback may use a lower-resolution stream. |
| **Agile task board** | [Trello — TrustAI Marketplace Sprint Board](https://trello.com/b/wUqCGA2T/trustai-marketplace-sprint-retrospective-board) |
| **Design and testing report** | [docs/capstone/CAPSTONE_DESIGN_AND_TESTING.md](docs/capstone/CAPSTONE_DESIGN_AND_TESTING.md) |
| **AI disclosure** | [docs/capstone/AI_DISCLOSURE.md](docs/capstone/AI_DISCLOSURE.md) |
| **Capstone documentation portal** | [docs/capstone/README.md](docs/capstone/README.md) |
| **Sprint history and demo recordings** | [docs/capstone/sprints/README.md](docs/capstone/sprints/README.md) |
| **Team meeting records** | [docs/capstone/meetings/README.md](docs/capstone/meetings/README.md) |
| **Full documentation** | [docs/README.md](docs/README.md) |

Built by a five-person team as the Quantic MSSE capstone project.

---

## Features

**Listing analysis**
- Submit a listing by pasting its details, or paste a URL and have the title, price, currency, description and seller details extracted and pre-filled for review
- Structured AI analysis: plain-English summary, categorical risk level, named indicators with severities, price plausibility, seller questions, and a recommendation
- A 0–100 Trust score computed server-side by `compute_risk_score` from the validated categorical result — the model never produces a number
- Every provider response passes strict JSON parsing, schema validation, cross-field consistency checks and an evidence policy before it is stored

**Visual Inspection**
- Optionally add one to three JPEG, PNG or WebP photos to a completed analysis for photo-grounded observations
- Explicit consent before upload; images are validated, normalised and stripped of metadata; photos and findings are not persisted by the TrustAI application, while provider-side handling follows the applicable provider policy

**Accounts and history**
- Registration, sign-in, profile editing and account deletion
- Per-user analysis history, with failed analyses retained and retryable individually
- Admin-only aggregate analytics behind role-based access

**Experience**
- Responsive desktop and mobile layouts
- Light, dark and system themes

---

## Architecture

```text
Browser ── HTTPS ──▶ Caddy (TLS, Let's Encrypt)
                       │
                       ▼
                     nginx ── serves React build
                       │ /api
                       ▼
                     FastAPI ── Pydantic ── SQLAlchemy / Alembic ──▶ PostgreSQL 16
                       │
                       ├──▶ AIProvider  (mock · Groq · OpenAI · Gemini)
                       └──▶ Visual Inspection provider
```

| Layer | Technology |
|---|---|
| Frontend | React 18, JavaScript (JSX), Vite, Vitest + React Testing Library |
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Database | PostgreSQL 16 (SQLite for tests) |
| AI | Provider-agnostic `AIProvider` protocol; production text analysis on OpenAI GPT-5.6 Terra via the Responses API, prompt `v4` |
| Edge | Caddy (automatic HTTPS), nginx |
| Infrastructure | Docker Compose on AWS EC2, images in Amazon ECR, deployment via AWS Systems Manager |
| CI/CD | GitHub Actions, semantic-release, gitStream |

### Key design decisions

| Decision | Implementation | Why |
|---|---|---|
| Risk is categorical, never model-generated as a number | `AIAnalysisResult` has no numeric field; pinned by `test_contract.py` (D-05) | LLM-produced scores are uncalibrated and drift between runs |
| Deterministic Trust score | `compute_risk_score` in `services/scoring.py`, disjoint tier bands 0–33 / 34–66 / 67–100 (D-09) | The number can never contradict the risk level it derives from |
| Provider abstraction | `AIProvider` protocol, selected by `AI_PROVIDER` | Swap providers without touching the API contract; automated provider tests use controlled transports and make no live provider requests |
| Fail-closed output validation | `services/ai_response_validation.py` | Malformed model output is rejected rather than repaired or guessed at |
| Ownership on every query | `Depends(get_current_user)` plus `.filter(Listing.user_id == user.id)` | One user can never read another user's analysis by guessing an ID |
| Persist before analyse | Listing committed before the provider call | A provider outage never loses user input |
| SSRF-guarded URL preview | `services/listing_fetch.py` resolves and validates every redirect hop, then pins the connection to that IP | Stops a pasted URL reaching internal infrastructure |
| Bounded public API | `CORS_ALLOW_ORIGINS` allow-list and a rolling 24-hour per-user analysis quota (D-22) | Protects provider spend on a publicly reachable deployment |
| SSH-keyless deployment | GitHub Actions → ECR → Systems Manager Run Command | No inbound SSH and no SSH keys stored in GitHub; AWS workflow credentials remain managed as GitHub Actions secrets |

Full rationale: [design and testing report](docs/capstone/CAPSTONE_DESIGN_AND_TESTING.md) · [decision log](docs/DESIGN_NOTES.md) · [ADRs](docs/decisions/)

---

## Quality

Release [`v1.21.0`](https://github.com/Ranga-Schooling/trustai-marketplace/releases/tag/v1.21.0) — [CI run 34706000817](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/34706000817):

| Suite | Result |
|---|---|
| Backend (pytest) | **457 passed** |
| Backend coverage | **96.52%** — enforced floor `--cov-fail-under=85` |
| Contract tests | **70 passed** |
| Frontend (Vitest) | **76 passed** across 9 files |
| Frontend build | Passed |

Tests are layered as unit, acceptance, integration and contract suites. CI runs the application against a deterministic mock provider, and provider adapters are tested against mocked transports, so the automated suite needs no provider credential and makes no live provider request. See the [testing guide](docs/testing/README.md).

---

## Getting started

### Prerequisites

- Python 3.12
- Node.js 22
- Docker with the Compose plugin

### Run the full stack

```bash
docker compose up --build
```

Open http://localhost:5173. With no configuration the backend uses the deterministic mock AI provider, so the app works end to end without an API key.

### Backend

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=85
```

### Frontend

```bash
cd frontend
npm ci
npm run test:ci
npm run build
```

### Configuration

Copy `backend/.env.example` to `backend/.env` to override defaults. Never commit `.env`.

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Database connection | Local SQLite |
| `JWT_SECRET` | JWT signing secret | Development placeholder |
| `AI_PROVIDER` | Text provider: `mock`, `groq`, `gpt`, `gemini` | `mock` |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | OpenAI credential and text model | — / `gpt-5.6-terra` |
| `VISUAL_INSPECTION_PROVIDER` / `VISUAL_INSPECTION_MODEL` | Visual Inspection provider and model | `disabled` / — |
| `CORS_ALLOW_ORIGINS` | Comma-separated allowed browser origins | Local dev origins |
| `MAX_ANALYSES_PER_DAY` | Rolling 24-hour analysis quota per user | `50` |

---

## Deployment

Every merge to `main` runs [`deploy.yml`](.github/workflows/deploy.yml):

1. Build backend and frontend images and push them to Amazon ECR, tagged with the commit SHA
2. Send the production Compose and Caddy configuration to the EC2 host through AWS Systems Manager
3. Validate the configuration, pull the pinned images and start the stack
4. Gate success on a health check that traverses Caddy → nginx → FastAPI

Releases are versioned automatically by [semantic-release](docs/RELEASE_STRATEGY.md) from conventional commits. Runbook: [deploy/README.md](deploy/README.md) · pipeline design: [docs/ci-cd/zero-trust-pipeline.md](docs/ci-cd/zero-trust-pipeline.md).

---

## Project structure

```text
backend/               FastAPI application, Alembic migrations, tests
frontend/              React application, nginx config, tests
deploy/                Production Compose file, Caddyfile, deployment runbook
docs/                  Design and testing report, decisions, sprints, meetings
.github/workflows/     CI, release, deploy and backup automation
docker-compose.yml     Local development stack
```

---

## How we worked

- **Scrum** across Sprint 0–3 and a final release phase, planned and tracked on the [Trello board](https://trello.com/b/wUqCGA2T/trustai-marketplace-sprint-retrospective-board)
- **Sprint demonstrations** recorded for Sprint 1 and Sprint 2 — [linked in the sprint history](docs/capstone/sprints/README.md#sprint-demonstration-recordings)
- **Meeting records** from kickoff on 1 July 2026 through 3 September 2026 — [indexed here](docs/capstone/meetings/README.md)
- **Pull requests and automated gates** — changes are integrated through pull requests and required CI. The current `main` ruleset requires an approving review, code-owner review, resolved conversations, required checks and linear history. See [GIT_WORKFLOW.md](docs/GIT_WORKFLOW.md) and [ADR-002](docs/decisions/ADR-002-branch-protection-ruleset.md)
- **Decisions recorded as they were made** — numbered D-01 onward in the [decision log](docs/DESIGN_NOTES.md), with platform-level choices as [ADRs](docs/decisions/)

### Team

| Name | Role |
|---|---|
| Ahmed Al-Mandalawi | Product Owner · AI Analysis Lead |
| Mulima Chibuye | Project Manager · Scrum Master |
| Rangarirai Revivalist Nyamadzawo | Backend Lead — Auth, Listings & Data |
| Adrin Kudakwashe Muchatibaya | Frontend Lead |
| Samar Salah Elghandour | QA & DevOps Lead |

---

## License

See [LICENSE](LICENSE).
