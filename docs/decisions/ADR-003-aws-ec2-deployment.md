# ADR-003: AWS EC2 Deployment via ECR and Systems Manager

## Status

Accepted as a retrospective record of the architecture released in
`v1.20.0`. Supersedes [ADR-001](ADR-001-deployment-platform.md) operationally
while preserving ADR-001 as the historical July deployment decision.

## Date

September 4, 2026

This ADR documents an incremental implementation from August 8 through the
September 2 final release. It does not assert that the complete final topology
was decided or operating on the first implementation date.

## Context

ADR-001 selected Render for a planned React static site, FastAPI service, and
managed PostgreSQL database. The implemented system later moved to AWS. The
repository evolved through separately reviewed changes rather than one
replacement decision:

| Date | Evidence | State established | Not yet established by that change |
|---|---|---|---|
| August 8 | [PR #37](https://github.com/Ranga-Schooling/trustai-marketplace/pull/37), [run 31262632194](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/31262632194) | Introduced ECR builds/tags, EC2 activation, a production-specific Compose definition, and nginx; the initial push run failed at AWS credential configuration before build or deployment | A successful deployment, Systems Manager activation, Caddy-managed HTTPS, backup automation, and the final health gate |
| August 10–12 | [PR #50](https://github.com/Ranga-Schooling/trustai-marketplace/pull/50), [run 31399309258](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/31399309258) | Remote deployment activation moved from an SSH action to AWS Systems Manager Run Command; the associated deployment run later completed successfully | Caddy-managed HTTPS and later operational hardening |
| August 17 | [PR #63](https://github.com/Ranga-Schooling/trustai-marketplace/pull/63), [run 32020887177](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/32020887177) | Caddy became the public TLS edge; nginx continued to serve the frontend and proxy the API; deployment gained Compose, Caddy, and application-health validation; the deployment run passed | Demonstrated off-instance backup and restore readiness |
| August 17–21 | [PR #76](https://github.com/Ranga-Schooling/trustai-marketplace/pull/76), [PR #89](https://github.com/Ranga-Schooling/trustai-marketplace/pull/89) | A scheduled/on-demand PostgreSQL-to-S3 backup workflow was added and hardened to fail closed when configuration is incomplete | A successful production backup, retention verification, and isolated restore test |
| August 23–28 | [PR #84](https://github.com/Ranga-Schooling/trustai-marketplace/pull/84), [failed run 32632207027](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/32632207027), [PR #93](https://github.com/Ranga-Schooling/trustai-marketplace/pull/93), [successful run 33210480909](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/33210480909) | Container log rotation and deployment cleanup addressed the observed EC2 disk-pressure failure mode; the first cleanup deployment failed, and the repaired workflow later passed | Automatic application rollback or database rollback compatibility |
| September 2 | [`v1.20.0`](https://github.com/Ranga-Schooling/trustai-marketplace/releases/tag/v1.20.0), [run 33678086731](https://github.com/Ranga-Schooling/trustai-marketplace/actions/runs/33678086731) | The final release combined the AWS deployment path with the completed application and passed release CI and deployment health | Public-browser and provider-path observations, which were recorded separately on September 4 |

The chronology above records implementation evidence. It does not infer that
every motivation or consequence was documented contemporaneously.

## Decision

TrustAI Marketplace uses one EC2 host running the production-specific
[`deploy/docker-compose.yml`](../../deploy/docker-compose.yml) stack:

1. Caddy listens on ports 80 and 443, manages TLS, and forwards traffic to the
   frontend container.
2. nginx serves the built React frontend and proxies `/api` to FastAPI over the
   internal Compose network.
3. The FastAPI backend has no host port in the production Compose definition.
4. PostgreSQL 16 runs on the same host and stores data in the named `pgdata`
   Docker volume.
5. Backend and frontend images are built in GitHub Actions and stored in ECR.
6. AWS Systems Manager Run Command performs remote deployment activation. This
   deployment workflow does not require inbound SSH.

Local development uses the separate root `docker-compose.yml`, which builds
from source and exposes development ports. CI runs backend and frontend gates;
it does not run the production Compose topology. These environments share
application containers and contracts where applicable, but they are not one
identical Compose deployment.

## Delivery behavior

The [deployment workflow](../../.github/workflows/deploy.yml) runs on a push to
`main` and can also be started manually. It:

- builds backend and frontend images;
- pushes both `latest` and commit-SHA tags to ECR;
- binds production activation to the commit SHA rather than `latest`;
- sends the next production Compose and Caddy definitions through Systems
  Manager;
- validates Compose configuration and the Caddyfile before activation;
- pulls the selected images and starts the stack;
- waits for the Caddy container health check, which traverses Caddy, nginx,
  and the backend health endpoint; and
- fails the workflow if activation or health validation fails.

The health gate establishes that the released containers started and that a
container-local request crossed the configured proxy path. It does not by
itself prove public DNS, browser TLS, authentication, or provider behavior.
Those later observations are bounded separately in the
[final production validation](../capstone/FINAL_PRODUCTION_VALIDATION.md).

The workflow preserves previous Compose and Caddy files before replacement,
but it does not automatically restore them or reactivate an earlier image after
failure. Rollback is an operator-controlled deployment of an earlier compatible
release. Database migrations and data compatibility must be evaluated before
such a rollback; no universal database rollback guarantee is made.

## Security and data boundaries

- Deployment uses Systems Manager for remote activation and operations instead
  of requiring inbound SSH for that workflow.
- Deployment configuration and credentials are supplied outside committed
  source through repository secrets and the private host environment. This ADR
  contains no secret values or account-specific registry identifier.
- The backend and database are not directly published as host ports by the
  production Compose file.
- Caddy is the public edge; nginx and FastAPI remain behind it in the Compose
  network.
- Deployments do not remove the `pgdata` volume.

These controls reduce exposure but do not prove every AWS-account audit or
network-control property. No CloudTrail verification is claimed here.

## Backup and recovery boundary

The repository contains a scheduled and manually dispatchable
[backup workflow](../../.github/workflows/backup.yml) that is designed to dump
PostgreSQL and upload the compressed result to S3 through Systems Manager. The
workflow deliberately fails when `BACKUP_S3_BUCKET` is absent.

Current repository and production evidence does not establish a successful
off-instance production backup, retention/lifecycle enforcement, or an
isolated restore. Backup and disaster-recovery readiness therefore remain
**OPEN** under [issue #88](https://github.com/Ranga-Schooling/trustai-marketplace/issues/88).
The existence of workflow code is not treated as proof that backups are
operational.

## Alternatives and relative cost

| Option | Relative cost and operations | Disposition |
|---|---|---|
| Managed frontend/API/database platform | Lower infrastructure ownership; service tiers, managed database, bandwidth, and always-on requirements determine monetary cost | ADR-001's original direction; not the released implementation |
| Single EC2 host with ECR and local PostgreSQL containers | Compute, disk, image storage/transfer, DNS/bandwidth, and optional backup storage are team-owned; operational responsibility is higher | Selected and implemented for the Capstone release |
| Simple VPS/container host | Similar single-host responsibility without the repository's implemented AWS automation | Portable alternative, not selected |
| Orchestrated multi-host platform | Additional control-plane and operational complexity that is disproportionate to the demonstrated Capstone workload | Deferred |

Exact recurring prices depend on region, account eligibility, service tiers,
storage, and traffic. This ADR intentionally makes no unsourced monthly-cost or
free-tier guarantee.

## Consequences

### Positive

- Every deployment activation is bound to an immutable commit-SHA image tag.
- The release workflow, ECR images, SSM command result, and health outcome form
  a traceable deployment path.
- Public TLS and proxying are represented in committed Caddy/nginx
  configuration.
- Application containers remain portable even though the current automation is
  AWS-specific.

### Trade-offs and limitations

- The EC2 host and its local database volume are single-host failure domains.
- The team owns host capacity, disk cleanup, container lifecycle, and recovery
  operations that a managed platform could absorb.
- The deployment workflow fails closed but does not provide automatic rollback.
- Backup and restore readiness is unresolved until issue #88's external
  configuration and production/restore verification are complete.

## Verification evidence

- [Deployment workflow](../../.github/workflows/deploy.yml)
- [Production Compose definition](../../deploy/docker-compose.yml)
- [Caddy configuration](../../deploy/Caddyfile)
- [Deployment and recovery guide](../../deploy/README.md)
- [CI/CD and Systems Manager design](../ci-cd/zero-trust-pipeline.md)
- [Final production validation](../capstone/FINAL_PRODUCTION_VALIDATION.md)
- [`v1.20.0` release](https://github.com/Ranga-Schooling/trustai-marketplace/releases/tag/v1.20.0)
- [Backup/recovery issue #88](https://github.com/Ranga-Schooling/trustai-marketplace/issues/88)
