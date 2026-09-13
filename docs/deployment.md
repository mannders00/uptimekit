# Deployment

## Host and network

Reference host: Debian 13 ARM64, EC2 t4g.medium, 4 GiB RAM, 40 GB encrypted EBS
(verify encryption in AWS), Elastic IP configured by the operator. Allow TCP
22 for trusted operators/runners, TCP 80/443 for HTTP/TLS, optionally UDP 443.
Do not expose database, Redis, Grafana, Prometheus, Alertmanager or Reticle ports.
EC2 IMDS should require v2; do not grant broad instance-role credentials.

Cloudflare A record: `uptimekit.masoftware.net`. Use **Full (strict)** TLS, not
Flexible. Caddy manages the origin certificate. Disable caching of dynamic,
authenticated, health, billing, infrastructure and Reticle routes.

## Bootstrap

Upload `scripts/bootstrap.sh` and `scripts/configure_host.py`, then run bootstrap
with sudo. It installs Debian Docker/Compose and creates independent random
application/database secrets under `/etc/uptimekit/{dev,prod}.env`. It is idempotent
and does not replace existing configuration. Reconnect for Docker group access.

The SSH deployment user has Docker access and therefore host-level authority.
GitHub environment secrets are the deployment control-plane boundary.

## GitHub environments and secrets

Create `dev` and `prod`. Both need these secrets (repository-level fallback is
also supported):

| Name | Value |
|---|---|
| `SSH_HOST` | Elastic IP or hostname |
| `SSH_USER` | `admin` |
| `SSH_KEY` | Private deployment key, multiline |
| `SSH_KNOWN_HOSTS` | Verified OpenSSH known-hosts entry for SSH_HOST |

Do not use unchecked `ssh-keyscan` during deployments. Bootstrap establishes
host trust, and subsequent workflows fail on host-key changes. Limit environment
deployment branches to `main`. Production promotion is manually dispatched.
GHCR image visibility must be public for anonymous server pulls.

CI uses ARM64 runners matching this instance. App images are tagged with the git
SHA and deployed by digest. Infrastructure images have explicit versions (Squid
uses an ARM64 digest); upgrades are a deliberate observability/dependency change.

## First release

1. Push `main`; CI tests, builds, and deploys dev.
2. Run Operate and recover → observability to start Caddy and monitoring.
3. Copy the image digest from the successful build summary.
4. Run Promote verified image to production with that digest.
5. Install the Reticle daemon per [reticle.md](reticle.md).
6. Run backup and restore-drill, then dev component drills. Capture actual results.

Only the digest recorded as verified in dev may be promoted. Runtime smoke
performs a real authenticated dashboard request and waits for a new successful
canary produced through Beat → Redis → worker → PostgreSQL.

## Service configuration

Edit `/etc/uptimekit/dev.env` and `prod.env` on the server. Values are ordinary
environment variables, not committed files. `STRIPE_SECRET_KEY`,
`STRIPE_WEBHOOK_SECRET`, and `STRIPE_PRICE_ID` enable Stripe sandbox/live use.
Point signed Stripe events at `/billing/webhook/`; enable subscription created,
updated, deleted, and checkout completed. Configure the Stripe Customer Portal.

For SMTP, set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`,
`EMAIL_HOST`, `EMAIL_PORT=587`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and
`DEFAULT_FROM_EMAIL`. Disabled email is intentionally visible in the public UI.

For reports set `REPORT_BUCKET` and scoped AWS credentials. With no report
bucket, generated files persist in a Docker media volume (host failure risk).
For backup uploads edit `/etc/uptimekit/backup.env`: `BACKUP_BUCKET`, region and
scoped AWS credentials. Enable S3 versioning, block public access, and configure
a 30-day retention lifecycle independently of the seven-day local dump retention.
The backup identity needs PutObject; the recovery identity also needs GetObject.

## Private dashboards and dev

```sh
ssh -i /path/to/key -L 3000:127.0.0.1:3000 -L 9090:127.0.0.1:9090 \
  -L 9093:127.0.0.1:9093 -L 8001:127.0.0.1:8001 admin@HOST
```

Grafana: `http://localhost:3000`, user `admin`, password in
`/etc/uptimekit/grafana-password`. Dev readiness is available on
`http://localhost:8001/health/ready`; full UI uses production security settings
and requires an HTTPS forwarding endpoint to use secure cookies in a browser.
Dev has separate networks, database, media and secrets; host resources and the
operator account are shared. A second EC2 is needed for failure-domain isolation.
