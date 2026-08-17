# EC2 + ECR continuous deployment

On every push to `main`, `.github/workflows/deploy.yml`:

1. Builds and pushes `trustaimarketplace/backend` and `trustaimarketplace/frontend` to ECR
   (tags: `latest` and the commit SHA)
2. Sends an AWS SSM `send-command` to EC2 that runs
   `docker compose pull && docker compose up -d` — no SSH, no inbound port 22.

Full architecture, IAM policy, and rationale: [`docs/ci-cd/zero-trust-pipeline.md`](../docs/ci-cd/zero-trust-pipeline.md).
This page is the shorter operational runbook.

## Image names (must match ECR)

| Service  | ECR repository                 | Full image |
|----------|--------------------------------|------------|
| Backend  | `trustaimarketplace/backend`   | `585142511013.dkr.ecr.eu-north-1.amazonaws.com/trustaimarketplace/backend:latest` |
| Frontend | `trustaimarketplace/frontend`  | `585142511013.dkr.ecr.eu-north-1.amazonaws.com/trustaimarketplace/frontend:latest` |

## GitHub Actions secrets

| Secret | Value |
|--------|--------|
| `AWS_ACCESS_KEY_ID` | IAM access key for the `github-actions-deployer` IAM user |
| `AWS_SECRET_ACCESS_KEY` | Paired IAM secret |
| `AWS_REGION` | `eu-north-1` |
| `ECR_BACKEND_REPO` | `trustaimarketplace/backend` |
| `ECR_FRONTEND_REPO` | `trustaimarketplace/frontend` |
| `EC2_INSTANCE_ID` | Target instance for SSM (`i-…`) |
| `EC2_APP_DIR` | Dir containing compose file, e.g. `/opt/trustai` |

`EC2_HOST`/`EC2_USER`/`EC2_SSH_KEY` are **no longer used** — SSM targets the instance by
`EC2_INSTANCE_ID`, not by host/user/key.

## One-time EC2 setup

1. Install Docker, Compose plugin, and AWS CLI.
2. Attach an **instance IAM role** granting `AmazonSSMManagedInstanceCore` (so the SSM agent
   can register and receive commands) and ECR pull permissions. The SSM agent itself ships
   preinstalled on Amazon Linux / Ubuntu AMIs from AWS.
3. Copy `deploy/docker-compose.yml` → `$EC2_APP_DIR/docker-compose.yml`.
4. Create `$EC2_APP_DIR/.env` with strong secrets (required — compose will refuse to start without them):

   ```bash
   JWT_SECRET=replace-with-a-long-random-string
   POSTGRES_PASSWORD=replace-with-a-strong-db-password
   # optional:
   # AI_PROVIDER=mock
   # GROQ_API_KEY=
   ```

5. Open security group port **80** only (API is reached via nginx `/api`, not public `:8000`).
   Port 22 does not need to be open — SSM doesn't require inbound access.
6. Manual first run (via `aws ssm start-session --target $EC2_INSTANCE_ID`, not SSH):
   ECR login → `docker compose pull && up -d`.

Local development still uses the root `docker-compose.yml` (builds from source).
