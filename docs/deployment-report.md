# Deployment report — work in progress

This document is updated from observed deployments and workflow results.

## Implemented

- Django authentication, workspace isolation, monitor CRUD and incident history.
- Signed/deduplicated Stripe webhooks and current-state subscription reconciliation.
- Durable scheduling/notification outboxes, bounded checks and raw-data retention.
- CSV reports through Django storage, including optional S3 backend.
- Separate dev/prod Compose projects, SSH release/promotion/rollback workflows.
- Prometheus/Grafana/Alertmanager, host/TLS probes and curated public alert state.
- Backup/restore scripts, dev component drills, Reticle read-only integration config.

## Verified so far

- EC2 SSH access and Debian Docker/Compose bootstrap.
- PostgreSQL-backed application boundary tests (13 tests).

## Pending verification / configuration

- Public deployment, CI build, runtime canary, Reticle graph, measured restore/drills.
- Stripe sandbox credentials/product/price/portal and end-to-end Checkout evidence.
- S3 bucket/credentials and off-host backup/download recovery.
- SMTP intentionally disabled at operator request. No email-delivery claims.

## Evidence policy

Only publish measured outcomes and sanitized operational records. Do not publish
database dumps, secrets, customer URLs/email, session/reset tokens, or private
Reticle source. A component being configured is not proof it was exercised.
