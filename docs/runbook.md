# Operator runbook

Prefer the **Operate and recover** GitHub workflow; the same commands work over
SSH from a release directory under `/opt/uptimekit/releases/<commit>/`.
Host-side `flock` serializes changes even across workflow types.

## Site unavailable

1. Check public `/health/ready`, GitHub external health run, and Cloudflare mode.
2. Inspect Caddy, application and PostgreSQL container state/logs.
3. Readiness 503 means database access failed; broker failures have separate alerts.
4. If release-related, run `bash scripts/operate.sh prod rollback`.
5. Verify a fresh canary and authenticated runtime smoke before declaring recovery.

## Checks stopped

Read dispatcher age → Redis connectivity/queue depth → oldest durable job age →
worker logs → successful canary age. Run the smoke action. Repair the dependency;
the outbox republishes uncompleted work. Do not flush queues as a first response.

## Release and rollback

Deployments pull the exact CI digest, back up an existing database, check settings,
migrate, replace web/worker/singleton Beat, and run runtime smoke. Failed releases
attempt to restart the previous digest and verify it. Rollback does **not** undo
migrations. Use expand/contract migrations; destructive schema changes require a
separate explicit recovery/cutover plan. A failed rollback remains a failed workflow.
The initial deployment has no previous artifact to restore.

## Backups and restoration

`backup` runs daily via GitHub schedule and manually. Local retention is seven
days. An unset S3 bucket is logged as local-only and raises OffHostBackupMissing.
`restore-drill` runs weekly and manually; it performs a new backup and restores it
into a clean isolated PostgreSQL container with no workers or external task execution.
It records duration and row counts, then removes the disposable environment.
When S3 is configured, the drill downloads the just-uploaded backup and checksum
before restoring; its JSON evidence identifies `backup_source` as `s3` or `local`.

For real host loss:

1. Bootstrap a replacement host and restore secrets from the operator's secure copy.
2. Retrieve an off-host dump and SHA-256 file; verify its hash before restoring.
3. Start a fresh PostgreSQL volume using the matching major version.
4. Restore with `pg_restore --exit-on-error --no-owner`; run `check` and
   `verify_restore` using the intended application image against that database.
5. Restore report objects or reconnect their S3 bucket. Reconcile current Stripe
   state before reopening customer task execution; a dump may contain old entitlements.
6. Recreate Redis and monitoring; configure DNS/Elastic IP and Caddy.
7. Start application roles, run runtime smoke, verify customer login and public TLS.

Do not restore over the active production database. Preserve it for diagnosis and
perform a deliberate cutover after validating the replacement. Daily dumps target
an approximately 24-hour RPO only when jobs and off-host uploads succeed. RTO is
measured per drill, never inferred from the schedule.

## Failure drills

**Bad release rollback drill** builds an intentionally broken web command in CI
from a provided known image, deploys it only to dev, requires deployment failure
and the rollback log, then verifies the recovered runtime. No images are built
ad hoc on the production host. The broken artifact is never marked verified.

`worker-drill`, `redis-drill`, and `db-drill` are restricted to dev. Each stops one
component for four minutes, captures evaluated alert names, and uses a shell exit
trap to restart the service and require a fresh runtime canary. Operator intervention
is still needed after host failure or SIGKILL; run `restart`/`smoke` to verify recovery.

Observe public prod readiness during a dev drill. Same-host CPU/disk pressure can
still affect both environments. Capture start, alert `startsAt`, recovery and
workflow URL rather than claiming generic detection/MTTR numbers.

## Email and billing

No email delivery is enabled initially. Notification rows remain queued; enabling
SMTP may send old pending notifications, so inspect their age before enabling it.
Provider errors increment attempts and schedule retry without changing incidents.
Stripe failures remain non-2xx so Stripe retries. Fix credentials/networking, replay
from Stripe, and run reconciliation. Never grant entitlement from browser redirects.

## Disk and dependency maintenance

Review `docker system df`, PostgreSQL size, Prometheus retention, and rotated logs.
Keep current and previous app images for rollback. Do not use indiscriminate volume
pruning. Test dependency/image updates in dev, rehearse restores before PostgreSQL
major upgrades, and patch the Debian host in a scheduled maintenance window.
