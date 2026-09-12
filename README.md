# TrustAI Marketplace

TrustAI Marketplace is an AI-assisted decision-support application for assessing online marketplace listings. It combines structured text analysis, deterministic risk scoring, saved history and recovery, and optional photo inspection whose photos and findings are not persisted by the TrustAI application.

> TrustAI does not determine whether a seller or listing is legitimate, provide financial advice, or guarantee a safe transaction. Its output is advisory and should be combined with independent checks.

## Final Capstone release

| Item | Evidence |
|---|---|
| Release | `v1.20.0` |
| Immutable source | `5ebc757ba66ff647944602245c18bedf6631680e` |
| Repository | [Ranga-Schooling/trustai-marketplace](https://github.com/Ranga-Schooling/trustai-marketplace) |
| Documented production URL | [https://trustai.mandalawi.ca](https://trustai.mandalawi.ca) |
| Agile task board | [TrustAI Marketplace Trello board](https://trello.com/b/wUqCGA2T) — Private; grader access must be established before submission |
| Capstone evidence portal | [docs/capstone/README.md](docs/capstone/README.md) |

The release's automated CI and deployment health gates passed. A separate September 4 controlled browser check verified logged-out HTTPS reachability and the application-level Terra-labelled text, History, and Visual paths within the evidence boundaries recorded in [the production-validation record](docs/capstone/FINAL_PRODUCTION_VALIDATION.md).

## Delivered product

The `v1.20.0` codebase implements:

- registration, login, profile update, account deletion, JWT sessions, and per-user ownership controls;
- manual listing entry and server-side URL preview with SSRF guardrails and user confirmation;
- structured AI text analysis with a summary, categorical risk, price-plausibility guidance, named indicators, seller questions, and a Buy/Caution/Avoid recommendation;
- an application-computed 0–100 Trust score that remains consistent with the categorical risk result;
- saved per-user history, retained failed listings, and isolated retry/recovery behavior;
- responsive desktop/mobile layouts plus light, dark, and system theme preferences;
- optional Visual Inspection for one to three JPEG, PNG, or WebP uploads, protected by explicit consent, strict image validation, capability gating, and no TrustAI application persistence of photos or findings; and
- an administrative aggregate-analytics API protected by role-based access.

Price plausibility is categorical and based on the submitted listing context. TrustAI does not yet perform live market-price research or claim a precise market valuation.

## AI behavior and safety boundaries

Text analysis is provider-independent at the application boundary. The implemented OpenAI adapter targets GPT-5.6 Terra through the Responses API and uses prompt version `v4`, strict structured output, deterministic cross-field validation, evidence-policy checks, and transient-only retry classification. Source code establishes that implementation and default; it does not prove the contents of private production configuration. CI uses the deterministic mock provider, and provider tests require no provider credentials and make no live provider requests.

Visual Inspection is configured independently from text analysis. Availability requires the supported `openai` provider plus non-empty configured key and model values. The authenticated capabilities endpoint does not validate the credential or provider-side model usability; those can be established only by an attempted provider request. When the local availability predicate fails, the endpoint reports only `visual_inspection_available: false`, and the frontend hides the feature. Provider names, models, and keys are not exposed through that response.

Visual results are a separate advisory channel: they do not change the text analysis, Trust score, categorical risk, or recommendation. Uploaded photos and visual findings are not persisted by the TrustAI application; provider-side handling is governed by the provider's applicable data policy.

## Architecture

```text
Browser
  │ HTTPS
  ▼
Caddy reverse proxy
  ▼
nginx / React + JavaScript (Vite)
  │ /api
  ▼
FastAPI / Pydantic / SQLAlchemy / Alembic
  ├── PostgreSQL
  ├── configured text-analysis provider
  └── independently configured Visual Inspection provider
```

Production images are built by GitHub Actions, stored in Amazon ECR, and activated on EC2 through AWS Systems Manager. Deployments use immutable commit-SHA image tags and gate success on the Caddy → nginx → backend health path. PostgreSQL data is stored in a named Docker volume. The scheduled S3 backup workflow exists, but its latest observed run failed because `BACKUP_S3_BUCKET` was not configured; backup/restore readiness remains open in [issue #88](https://github.com/Ranga-Schooling/trustai-marketplace/issues/88).

Detailed engineering records are in [docs/DESIGN_NOTES.md](docs/DESIGN_NOTES.md), [docs/decisions](docs/decisions), [docs/ci-cd](docs/ci-cd), and [deploy/README.md](deploy/README.md).

## Verified automated quality gates

The authoritative CI run for release `v1.20.0` is [GitHub Actions run 33678086754](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/33678086754):

- contract gate: 70 passed, 379 deselected, 8 warnings;
- full backend: 449 passed, 140 warnings;
- backend coverage: 96.49%, above the required 85% gate;
- frontend: 76 passed across 9 test files; and
- frontend production build: passed, 39 modules transformed.

The latest observed deployment run for this SHA, [run 33687682316](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/33687682316), passed image-identity and service-health checks. These results do not, by themselves, prove a complete logged-out browser journey or a real-provider transaction.

## Local development

### Prerequisites

- Python 3.12
- Node.js 22 for CI and local frontend development; the production frontend
  image currently builds its static assets with Node.js 18
- Docker with the Compose plugin (for the full stack)

### Backend

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=85
```

The application defaults to local SQLite and the deterministic mock AI provider when deployment-specific settings are absent. Copy `backend/.env.example` to `backend/.env` only when local environment configuration is needed. Never commit credentials.

### Frontend

```bash
cd frontend
npm ci
npm run test:ci
npm run build
```

### Full local stack

```bash
docker compose up --build
```

Then open `http://localhost:5173`. The root Compose stack loads `backend/.env` if present and supplies its own local PostgreSQL connection.

## Configuration overview

The primary runtime settings are environment-driven:

| Setting | Purpose | Safe default |
|---|---|---|
| `DATABASE_URL` | Database connection | Local SQLite outside Compose |
| `JWT_SECRET` | JWT signing secret | Development placeholder; must be replaced in production |
| `AI_PROVIDER` | `mock`, `groq`, `gpt`, or `gemini` text provider | `mock` |
| `OPENAI_API_KEY` | OpenAI credential for explicitly selected OpenAI-backed features | Empty |
| `OPENAI_MODEL` | OpenAI text model | `gpt-5.6-terra` |
| `VISUAL_INSPECTION_PROVIDER` | Independent visual provider control | `disabled` |
| `VISUAL_INSPECTION_MODEL` | Required explicit visual model when enabled | Empty in application/production defaults |

Production secrets belong only in the private host environment described by [deploy/README.md](deploy/README.md). `IMAGE_TAG` is supplied by the deployment workflow and must not be stored in the host `.env`.

## Repository guide

```text
backend/                 FastAPI application, migrations, scripts, and tests
frontend/                React/Vite application, nginx configuration, and tests
deploy/                  Production Compose, Caddy, and EC2/ECR runbook
docs/                    Requirements, decisions, architecture, testing, and Capstone evidence
.github/workflows/       CI, release, deployment, and backup automation
docker-compose.yml       Local development stack
```

Useful entry points:

- [Capstone evidence portal](docs/capstone/README.md)
- [Canonical Trello board](https://trello.com/b/wUqCGA2T) — final state reconciled during submission closeout; grader access remains OPEN
- [User-story backlog and implementation traceability](docs/BACKLOG.md)
- [Design decisions](docs/DESIGN_NOTES.md)
- [Testing guide](docs/testing/README.md)
- [Deployment runbook](deploy/README.md)
- [Git and review workflow](docs/GIT_WORKFLOW.md)

## Known limitations and deferred work

- The September 4 browser record verifies the deployed application boundary; it does not independently attest private provider transport details or the exact Visual model.
- Scheduled database backups are not operational until the S3 bucket and associated IAM/lifecycle configuration are completed and restore-tested.
- CORS currently permits all origins and should be restricted for a hardened production service.
- Password change and admin-controlled runtime provider switching remain deferred.
- Visual Inspection is user-initiated, photo-limited, and advisory. Photos and findings are not persisted by the TrustAI application; provider-side handling is governed by the provider's applicable data policy. It does not inspect marketplace media automatically.
- The repository contains historical plan-era documents that do not all describe the final release. The [Capstone evidence portal](docs/capstone/README.md) identifies the authoritative final evidence and remaining access/validation work.

## License

See [LICENSE](LICENSE).
