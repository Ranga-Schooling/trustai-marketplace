# EC2 + ECR continuous deployment

On every push to `main`, `.github/workflows/deploy.yml`:

1. Builds and pushes `trustaimarketplace/backend` and `trustaimarketplace/frontend` to ECR
   (tags: `latest` and the commit SHA)
2. SSHs to EC2 and runs `docker compose pull && docker compose up -d`

## Image names (must match ECR)

| Service  | ECR repository                 | Full image |
|----------|--------------------------------|------------|
| Backend  | `trustaimarketplace/backend`   | `585142511013.dkr.ecr.eu-north-1.amazonaws.com/trustaimarketplace/backend:latest` |
| Frontend | `trustaimarketplace/frontend`  | `585142511013.dkr.ecr.eu-north-1.amazonaws.com/trustaimarketplace/frontend:latest` |

## GitHub Actions secrets

| Secret | Value |
|--------|--------|
| `AWS_ACCESS_KEY_ID` | IAM access key (ECR push) |
| `AWS_SECRET_ACCESS_KEY` | IAM secret |
| `AWS_REGION` | `eu-north-1` |
| `ECR_BACKEND_REPO` | `trustaimarketplace/backend` |
| `ECR_FRONTEND_REPO` | `trustaimarketplace/frontend` |
| `EC2_HOST` | EC2 public IP or DNS |
| `EC2_USER` | `ubuntu` or `ec2-user` |
| `EC2_SSH_KEY` | Private PEM key contents |
| `EC2_APP_DIR` | Dir containing compose file, e.g. `/opt/trustai` |

## One-time EC2 setup

1. Install Docker, Compose plugin, and AWS CLI.
2. Give the instance (or `~/.aws`) permission to pull from both ECR repos.
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
6. Manual first run: ECR login → `docker compose pull && up -d`.

Local development still uses the root `docker-compose.yml` (builds from source).
