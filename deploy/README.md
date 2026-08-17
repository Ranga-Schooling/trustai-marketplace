# EC2 + ECR continuous deployment

On every push to `main`, `.github/workflows/deploy.yml`:

1. Builds and pushes `trustaimarketplace/backend` and `trustaimarketplace/frontend` to ECR
   (tags: `latest` and the commit SHA)
2. Sends an AWS SSM `send-command` to EC2 that transfers the current `docker-compose.yml`
   and `Caddyfile`, validates both, activates them pinned to the commit SHA (not `latest`),
   and gates success on the full Caddy → nginx → backend health path — no SSH, no inbound port 22.
   Previous `docker-compose.yml`/`Caddyfile` are kept as `.previous` for manual rollback;
   **there is no automatic rollback** on a failed health check.

Full architecture, IAM policy, and rationale: [`docs/ci-cd/zero-trust-pipeline.md`](../docs/ci-cd/zero-trust-pipeline.md).
This page is the shorter operational runbook.

Public HTTPS is terminated by **Caddy** (`deploy/Caddyfile`), which automatically obtains and
renews a Let's Encrypt certificate for the configured domain and reverse-proxies to `frontend`.
nginx (`frontend/nginx.conf`) is no longer reached directly from the internet — Caddy is the
only public listener, on ports 80 (ACME challenge + HTTP→HTTPS) and 443.

## Image names (must match ECR)

| Service  | ECR repository                 | Full image |
|----------|--------------------------------|------------|
| Backend  | `trustaimarketplace/backend`   | `585142511013.dkr.ecr.eu-north-1.amazonaws.com/trustaimarketplace/backend:<commit-sha>` |
| Frontend | `trustaimarketplace/frontend`  | `585142511013.dkr.ecr.eu-north-1.amazonaws.com/trustaimarketplace/frontend:<commit-sha>` |

Both are also pushed as `:latest`, but the deploy script always activates the commit-SHA tag —
`docker-compose.yml` requires `IMAGE_TAG` to be set (`${IMAGE_TAG:?set IMAGE_TAG for deployment}`)
rather than defaulting to `latest`, so a stale or bad `latest` can't silently get pulled in.

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
3. Point DNS for the deployed domain (currently `trustai.mandalawi.ca`) at the instance's
   public IP — Caddy's automatic HTTPS depends on this resolving before the first deploy.
4. The deploy script transfers `deploy/docker-compose.yml` and `deploy/Caddyfile` itself on
   every deploy; no manual copy needed after the first run (the very first run has nothing to
   diff against, so it activates directly).
5. Create `$EC2_APP_DIR/.env` with strong secrets (required — compose will refuse to start without them):

   ```bash
   JWT_SECRET=replace-with-a-long-random-string
   POSTGRES_PASSWORD=replace-with-a-strong-db-password
   # optional:
   # AI_PROVIDER=mock
   # GROQ_API_KEY=
   ```

   `IMAGE_TAG` is supplied by the deploy script per-run and must **not** be set in `.env`.
6. Open security group ports **80 and 443**. Port 80 is still needed — Caddy uses it for the
   ACME HTTP-01 challenge and to redirect plain HTTP to HTTPS, not just historical compatibility.
   Port 22 does not need to be open — SSM doesn't require inbound access.
7. Manual first run (via `aws ssm start-session --target $EC2_INSTANCE_ID`, not SSH):
   ECR login → `IMAGE_TAG=<commit-sha> docker compose pull && IMAGE_TAG=<commit-sha> docker compose up -d`.

Local development still uses the root `docker-compose.yml` (builds from source, plain HTTP,
no Caddy).
