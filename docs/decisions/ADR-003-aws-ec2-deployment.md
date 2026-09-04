# ADR-003: Deploy to a single AWS EC2 instance via ECR and SSM

## Status

Accepted. Supersedes [ADR-001](ADR-001-deployment-platform.md).

## Date

August 8, 2026 (recorded retrospectively on September 4, 2026 — see
"Record-keeping note" below).

## Context

[ADR-001](ADR-001-deployment-platform.md) selected Render as the deployment
platform in July, before any deployment work had started. When Sprint 2
began the actual deployment work, three constraints emerged that ADR-001 had
not anticipated:

1. **The application is already defined as a Docker Compose stack.** Local
   development, CI and the manual smoke-test checklist all run
   `docker compose up`. Render's Static Site + Web Service + Managed
   Postgres model would have required maintaining a *second*, differently
   shaped description of the same system, and any drift between the two
   would only ever be discovered in production.

2. **The team wanted the deployment to be a teachable artifact.** A
   significant part of the capstone's learning outcomes concern CI/CD and
   infrastructure. A platform that hides the deploy behind a vendor UI would
   have removed exactly the work the team wanted to demonstrate.

3. **A team member already had AWS access and a spare domain.** This made a
   real cloud deployment — with a genuine certificate on a genuine domain —
   cheaper in effort than the managed alternative, not more expensive.

## Decision

The application is deployed to a **single AWS EC2 instance** running the
production Docker Compose stack in `deploy/docker-compose.yml`.

- **Images** are built in GitHub Actions and pushed to **Amazon ECR**
  (`585142511013.dkr.ecr.eu-north-1.amazonaws.com`), tagged with the commit
  SHA rather than `latest`, so every deployed state is traceable to an exact
  commit and a rollback is a re-pin, not a rebuild.
- **Deployment is triggered by a push to `main`** (`.github/workflows/deploy.yml`)
  and executed on the instance through **AWS Systems Manager (SSM)
  `send-command`**. There is no inbound SSH: port 22 is not required and no
  SSH key material exists in GitHub. This is documented in full in
  [docs/ci-cd/zero-trust-pipeline.md](../ci-cd/zero-trust-pipeline.md).
- **HTTPS is terminated by Caddy** (`deploy/Caddyfile`), which obtains and
  renews a Let's Encrypt certificate for `trustai.mandalawi.ca`
  automatically. nginx serves the built frontend behind Caddy and is not
  reachable directly from the internet.
- **PostgreSQL runs as a container** on the same instance, with its data in a
  named Docker volume (`pgdata`) that survives deploys. A scheduled workflow
  (`.github/workflows/backup.yml`) dumps the database to **S3** daily at
  03:00 UTC over the same SSM path.
- **Region** is `eu-north-1`.

## Rationale

The deciding factor was **one description of the system, not two**. The same
Compose topology runs locally, in the smoke-test checklist, and in
production; only the image sources and the reverse proxy differ. A bug
reproduced locally is a bug reproduced in something structurally identical to
production.

SSM over SSH was chosen deliberately. It removes the single highest-value
long-lived secret a student project would otherwise store in GitHub (a
private key with shell access to the production host) and replaces it with a
scoped, auditable, revocable IAM path. Every deploy is recorded in CloudTrail.

## Deployment options considered, and relative cost

The rubric asks for the deployment options considered and their relative cost
implications. All figures are order-of-magnitude at capstone scale (single
instance, a handful of concurrent users, no meaningful traffic).

| Option | Cost at capstone scale | Cost at production scale | Assessment |
|---|---|---|---|
| **AWS EC2 + ECR + SSM (chosen)** | Free tier eligible for the first 12 months; roughly **$10–20/month** afterwards for a small instance, EBS volume, ECR storage and S3 backups | Scales by adding instances and a load balancer; database should move to RDS (~$15–30/month more) | Chosen. Real infrastructure, full control, directly demonstrates the CI/CD learning outcomes. Highest operational burden. |
| **Render / Railway (managed PaaS)** | **$0/month** on free tiers | Roughly **$25–50/month** once the free Postgres expires and the API must stay warm | Rejected — see Context. Cheapest and simplest, but requires a second description of the system and hides the deployment mechanics. Free-tier Postgres instances also expire, which is a real risk across a multi-month capstone. |
| **On-premises / self-hosted hardware** | Hardware already owned, but **electricity, a static IP or dynamic DNS, and someone physically responsible** for the machine | Cheapest per unit of compute at large scale; most expensive in staff time | Rejected. No cost advantage at this scale, and it makes availability depend on one team member's home network — unacceptable when a grader must reach the application on demand. |
| **Kubernetes (EKS/GKE)** | **~$70+/month** for the control plane alone | Justified only with many services and a platform team | Rejected as significantly disproportionate to a single-container-per-tier application. |

**Recommendation.** For a system of this size, managed PaaS is the correct
default and we would recommend it to a team whose learning goals lay
elsewhere. We chose EC2 because demonstrating the pipeline *is* part of the
deliverable. If TrustAI were taken forward as a real product, the first two
infrastructure investments should be moving Postgres to managed RDS (removing
the single-instance data risk that the S3 backup currently only mitigates)
and adding a second application instance behind a load balancer.

## Consequences

### Positive

- One Compose topology across local, test and production.
- No long-lived SSH credentials; deploys are auditable via CloudTrail.
- Every deployed state is pinned to a commit SHA and trivially rollback-able.
- HTTPS with a real certificate on a real domain, suitable for demonstration.

### Trade-offs

- The team owns instance-level operations that a PaaS would have absorbed —
  disk exhaustion from accumulated images was a real production incident
  (see D-16/D-18 in [DESIGN_NOTES.md](../DESIGN_NOTES.md)) and is now
  automated away in `deploy.yml`.
- A single instance is a single point of failure. Accepted for the capstone;
  it is the first thing that should change in production.
- The database's durability depends on the daily S3 backup rather than on a
  managed provider's replication.
- AWS costs money after the free-tier period, where Render's free tier does
  not.

## Record-keeping note

This ADR was written on September 4, 2026 to correct the documentation
record. The **decision** it describes was made and implemented on
August 8, 2026 — see PR #37 (ECR build/push and EC2 auto-deploy), PR #50
(SSM instead of SSH) and PR #63 (Caddy HTTPS). ADR-001 was left in place
during that period and was, until this ADR, the only recorded statement of a
deployment platform; it described Render, which the project had already
stopped pursuing. Superseding it rather than editing it preserves the
history, including the fact that the team's first platform decision did not
survive implementation.
