# Zero-Trust CI/CD Pipeline

This document records the TrustAI Marketplace transition from direct SSH-based deployment to a **zero-trust** model using **AWS Systems Manager (SSM)**. GitHub Actions no longer opens SSH connections to the EC2 host; instead, it queues a remote command through the AWS API and waits for a verifiable success status before completing the workflow.

**Related artifacts**

| Artifact | Location |
|----------|----------|
| Deploy workflow | `.github/workflows/deploy.yml` |
| EC2 production stack | `deploy/docker-compose.yml` |
| Operational runbook (ECR, `.env`, first-time setup) | `deploy/README.md` |
| Migration-on-start decision | `docs/DESIGN_NOTES.md` (D-11) |

---

## End-to-end architecture

The diagram below matches the **current** implementation in `.github/workflows/deploy.yml` and `deploy/docker-compose.yml`.

> **Note on auth:** GitHub Actions authenticates with the IAM user **`github-actions-deployer`** using **access keys** stored in GitHub Secrets (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`). This is **not** OIDC role assumption — if you maintain a separate PNG/draw.io diagram, label it accordingly (see [Diagram revision checklist](#diagram-revision-checklist) below).

```mermaid
flowchart LR
  subgraph Dev["Development"]
    DEV[Developer]
    DEV -->|1. Push / merge to main| GH[(GitHub Repository)]
  end

  subgraph GHA["GitHub Actions — Deploy workflow"]
    GH -->|2. Trigger| WF[Deploy job]
    WF --> CHK[Checkout]
    CHK --> AWS[Configure AWS credentials\nIAM user access keys]
    AWS --> ECRLOGIN[Login to ECR]
    ECRLOGIN --> BUILD[Build & push Docker images\nbackend + frontend]
    BUILD --> SSM[SSM send-command]
    SSM --> WAIT[Wait command-executed\n+ fail if Status ≠ Success]
  end

  subgraph AWS["AWS Cloud — eu-north-1"]
    IAM[(IAM user\ngithub-actions-deployer)]
    ECR[(Amazon ECR\ntrustaimarketplace/backend\ntrustaimarketplace/frontend)]
    EC2[(EC2 instance\nSSM agent)]

    AWS -->|3. Authenticate| IAM
    BUILD -->|4. Push images :latest + :SHA| ECR
    WAIT -->|5. RunShellScript via SSM| EC2
    ECR -->|6. docker compose pull| EC2
  end

  subgraph EC2Stack["EC2 — /opt/trustai"]
    ENV[docker-compose.yml + .env\nJWT_SECRET, POSTGRES_PASSWORD]
    FE[Frontend container\nNginx :80]
    BE[Backend container\nFastAPI :8000 internal]
    DB[(Postgres\npgdata volume)]
    ENV --> FE
    FE -->|"/api proxy"| BE
    BE --> DB
    BE -->|startup| ALEMBIC[alembic upgrade head]
  end

  EC2 --> EC2Stack
  USER[Browser / HTTP :80] --> FE
```

### Diagram revision checklist

If you export a PNG (e.g. for slides or the architecture folder), **revise the current draft** before committing it:

| Item | Current draft issue | Correct for TrustAI |
|------|---------------------|---------------------|
| **Title** | Says "via OIDC" | Use **"via IAM + SSM"** (or "access keys + SSM") — OIDC is not configured in `deploy.yml`. |
| **GitHub → AWS auth** | OIDC provider, temp tokens, IAM role | **IAM user `github-actions-deployer`** + secrets `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`. |
| **Deploy to EC2** | SSM command ✓ | Keep — matches `aws ssm send-command`. |
| **Post-SSM step** | Missing | Add **SSM waiter** + `GetCommandInvocation` — job fails unless status is `Success`. |
| **Backend port** | Implies public `:8000` | Backend is **internal only** (`expose: 8000`); users hit **Nginx :80**, which proxies `/api`. |
| **Backend startup** | Missing | Add **`alembic upgrade head`** before Uvicorn (see D-11). |
| **ECR image names** | Mostly correct | Full repos: `trustaimarketplace/backend`, `trustaimarketplace/frontend` (registry `585142511013.dkr.ecr.eu-north-1.amazonaws.com`). |
| **Secrets removed** | Not shown | Drop `EC2_SSH_KEY`, `EC2_HOST`, `EC2_USER`; use **`EC2_INSTANCE_ID`**. |

**Recommended location for a revised PNG:** `docs/ci-cd/trustai-cicd-architecture.png` (link from this file after export).

---

## Architecture shift

### Before: SSH from GitHub Actions

The initial deploy workflow used [`appleboy/ssh-action`](https://github.com/appleboy/ssh-action) to connect directly to the EC2 instance:

- Required a long-lived **private SSH key** stored in GitHub Secrets (`EC2_SSH_KEY`).
- Required the instance **host** and **SSH user** (`EC2_HOST`, `EC2_USER`).
- Implied either an **open inbound SSH port** (typically TCP 22) or equivalent direct network reachability from the GitHub Actions runner to the server.

This model couples deployment security to key rotation, port exposure, and trust in a shared credential that grants shell access.

### After: AWS Systems Manager (SSM)

The workflow now deploys through **`aws ssm send-command`**:

- GitHub Actions authenticates to **AWS** (IAM access keys), not to the EC2 host over SSH.
- The command is delivered to the instance by the **SSM agent**, using AWS's control plane.
- No GitHub-stored SSH key and no requirement for GitHub runners to reach the instance on port 22.

```text
  push to main
       │
       ▼
  GitHub Actions (Deploy workflow)
       │
       ├── Build & push images ──► Amazon ECR
       │
       └── aws ssm send-command ──► EC2 (SSM agent)
                │
                └── remote script: ECR login → docker compose pull → up -d
```

**Security outcomes**

- Eliminates direct server access from GitHub via SSH.
- Removes the need to expose SSH to the public internet for CI/CD.
- Centralizes deploy permissions in **IAM policies** (auditable, revocable).
- Deployment success is verified via SSM invocation status, not merely "command queued."

---

## GitHub Secrets management

### Removed (SSH path)

| Secret | Former purpose |
|--------|----------------|
| `EC2_SSH_KEY` | PEM private key for SSH authentication |
| `EC2_HOST` | Public IP or DNS of the EC2 instance |
| `EC2_USER` | SSH login user (`ubuntu`, `ec2-user`, etc.) |

These secrets are **no longer used** by `.github/workflows/deploy.yml`.

### Added / retained (SSM path)

| Secret | Purpose |
|--------|---------|
| `EC2_INSTANCE_ID` | **New.** Target instance for SSM (`i-…`). Replaces host/user/key targeting. |
| `EC2_APP_DIR` | Absolute path on the instance containing `docker-compose.yml` (e.g. `/opt/trustai`). |
| `AWS_ACCESS_KEY_ID` | IAM user credentials for GitHub Actions (`github-actions-deployer`). |
| `AWS_SECRET_ACCESS_KEY` | Paired secret for the IAM user. |
| `AWS_REGION` | AWS region (e.g. `eu-north-1`). |
| `ECR_BACKEND_REPO` | ECR repository name for the API image (`trustaimarketplace/backend`). |
| `ECR_FRONTEND_REPO` | ECR repository name for the UI image (`trustaimarketplace/frontend`). |

Configure under **Repository → Settings → Secrets and variables → Actions**.

---

## AWS IAM configuration

Deploy permissions for GitHub Actions are granted to the IAM user **`github-actions-deployer`** via an **inline policy** attached to that user.

### Required SSM permissions

The policy grants the GitHub Actions principal permission to:

| Action | Purpose |
|--------|---------|
| `ssm:SendCommand` | Queue the remote deploy shell script on the target instance. |
| `ssm:GetCommandInvocation` | Read stdout/stderr and final status after the command runs. |
| `ssm:ListCommandInvocations` | List invocation metadata (supporting status checks and troubleshooting). |

These actions must be scoped to:

- The **target EC2 instance** (`EC2_INSTANCE_ID`), and
- The **SSM documents** used for execution (e.g. `AWS-RunShellScript`).

### Additional permissions (same deployer user)

The same IAM user typically also requires:

- **ECR**: push images from GitHub Actions (`GetAuthorizationToken`, `BatchCheckLayerAvailability`, `PutImage`, etc.).
- **SSM messaging** (if using the standard SSM document): `ssm:UpdateInstanceInformation` is handled by the **instance role**, not GitHub.

### EC2 instance requirements

The EC2 host must:

1. Run the **SSM agent** (preinstalled on Amazon Linux / Ubuntu AMIs from AWS).
2. Have an **instance IAM role** allowing ECR pull and any local AWS CLI calls used in the deploy script.
3. Have **`deploy/docker-compose.yml`** and a local **`.env`** at `EC2_APP_DIR` (secrets are never committed to the repository).

---

## Workflow execution

Workflow file: `.github/workflows/deploy.yml`

**Trigger:** push to `main`, or manual `workflow_dispatch`.

### Phase 1 — Build and publish (GitHub Actions runner)

1. Checkout repository.
2. Configure AWS credentials (`aws-actions/configure-aws-credentials`).
3. Log in to Amazon ECR (`aws-actions/amazon-ecr-login`).
4. Build and push **backend** and **frontend** Docker images.
   - Tags: `latest` and `${GITHUB_SHA}` (immutable traceability per commit).

### Phase 2 — Deploy on EC2 (SSM)

The **Deploy on EC2 via SSM** step:

1. Calls `aws ssm send-command` with document **`AWS-RunShellScript`**.
2. Runs a remote script on the instance:
   ```bash
   set -e
   cd $EC2_APP_DIR
   aws ecr get-login-password … | docker login …
   docker compose pull
   docker compose up -d
   docker image prune -f
   ```
3. Captures the returned **`CommandId`**.

### Phase 3 — Wait and fail closed

Because `send-command` only **queues** work, the workflow implements an explicit waiter:

1. **`aws ssm wait command-executed`** — blocks until the invocation completes or times out.
2. **`aws ssm get-command-invocation`** — emits stdout, stderr, and status to the Actions log.
3. **Job failure** if the waiter exits non-zero or invocation `Status` is not **`Success`**.

This prevents a green GitHub Actions run when `docker compose pull` or container restart fails on the server.

---

## Database migrations

Schema changes are applied automatically at **container startup**, not as a separate manual deploy step.

The backend `Dockerfile` runs:

```dockerfile
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

**Behavior**

- Every backend container start executes `alembic upgrade head` before Uvicorn serves traffic.
- If the database is already at the latest revision, Alembic is a **no-op**.
- Prevents **schema drift** between code (migrations in `backend/alembic/versions/`) and the live Postgres volume on EC2.

**One-time repair (legacy databases)**

If a database was created before Alembic was wired into the Docker image (bootstrapped only via `Base.metadata.create_all()`), it may lack an `alembic_version` table. In that case, stamp the database at the revision matching its actual schema before the first auto-upgrade — see **D-11** in `docs/DESIGN_NOTES.md`.

---

## Verification checklist

After merging deploy changes or rotating secrets:

- [ ] GitHub Actions **Deploy** workflow completes with SSM status **Success**.
- [ ] ECR shows new images tagged with the merge commit SHA.
- [ ] EC2 containers are running: `docker compose ps` under `EC2_APP_DIR`.
- [ ] API health: `GET /api/health` via the frontend/nginx proxy (port 80).
- [ ] Backend logs show Alembic upgrade (or "already at head") before Uvicorn startup.
- [ ] No SSH secrets remain in GitHub Actions for deployment.

---

## Revision history

| Date | Change |
|------|--------|
| 2026-08-12 | Initial documentation of SSH → SSM zero-trust deploy model. |
