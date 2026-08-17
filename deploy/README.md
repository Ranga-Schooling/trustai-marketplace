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
| `BACKUP_S3_BUCKET` | S3 bucket for scheduled Postgres backups (see "Database backups" below) — used by `.github/workflows/backup.yml` only, not `deploy.yml` |

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
8. For backups (see below): create an S3 bucket and grant the **EC2 instance's own IAM
   role** (not the `github-actions-deployer` user) `s3:PutObject` on it. The backup command
   runs *on* the instance via SSM, so it authenticates as the instance role, not as
   GitHub Actions.

Local development still uses the root `docker-compose.yml` (builds from source, plain HTTP,
no Caddy).

## Database backups

The `pgdata` Docker volume (declared in `deploy/docker-compose.yml`) survives every normal
redeploy — `deploy.yml`'s remote script only ever runs `docker compose pull`/`up -d` (plus config
validation and health checks), never `down -v` — but
it lives on this one EC2 instance's disk. If the instance is ever replaced, or the disk
fails, there's no recovery path without a separate backup.

`.github/workflows/backup.yml` runs daily (03:00 UTC) plus on-demand via
**Actions → Postgres backup → Run workflow**. It uses the same zero-trust SSM
`send-command` pattern as `deploy.yml` (no SSH, no inbound access): `pg_dump | gzip`
inside the `db` container, upload to `s3://$BACKUP_S3_BUCKET/postgres-backups/`, done.
The workflow fails loudly (a red Action run) if the dump or upload fails — a silent
backup failure is worse than an obvious one.

**Retention** is deliberately not scripted (a bug in a delete-old-backups script is a way
to lose backups, not protect them) — set an [S3 lifecycle
rule](https://docs.aws.amazon.com/AmazonS3/latest/userguide/intro-lifecycle-rules.html) on
the bucket instead, e.g. expire objects under `postgres-backups/` after 30 days.

**To restore** a backup (via `aws ssm start-session --target $EC2_INSTANCE_ID`, then):
```bash
aws s3 cp s3://$BACKUP_S3_BUCKET/postgres-backups/<file>.sql.gz - \
  | gunzip \
  | docker compose exec -T db psql -U trustai -d trustai
```
This replays the dump's `COPY`/`INSERT` statements into the existing database — for a
full disaster-recovery restore into an *empty* database (e.g. after standing up a
replacement instance), create the empty `trustai` database first, same as `docker-compose.yml`'s
`db` service does automatically on first boot.

## Disk cleanup

Every deploy pulls a uniquely commit-SHA-tagged image (`IMAGE_TAG`, see above), so old
images were never `<none>`/dangling — `docker image prune` without `-a` only removes
dangling images, so it silently never touched them, and they piled up on the instance's
disk indefinitely. Two fixes, since they address different growth sources:

1. **Stale images/containers/volumes/networks.** `deploy.yml`'s remote script now runs
   `docker image prune -af` (the `-a` is the fix — removes *any* image with zero
   containers referencing it, not just untagged ones), plus `container`/`volume`/`network
   prune -f`, right after the health check confirms the new stack is up — so only the
   previous deploy's now-genuinely-unused resources are removed, never anything the live
   stack is using. This runs on **every deploy**, not on a separate schedule — disk usage
   never has a chance to grow across more than one deploy's worth of images. Logs
   `docker system df` before/after and `df -h /`, so reclaimed space is visible in the
   Action run.
2. **Unbounded container logs.** Docker's default `json-file` log driver has no size cap
   on its own — a chatty service (Caddy/nginx access logs, uvicorn access logs) grows
   without bound over weeks and is a common real-world cause of a small instance quietly
   filling up, independent of images entirely. `deploy/docker-compose.yml` now caps every
   service at 10MB × 3 rotated files (30MB ceiling each) via a shared `x-logging` anchor —
   this is a standing structural limit, not something deploy-time cleanup needs to act on.
