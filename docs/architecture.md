# Architecture and boundaries

## From customer outcome to implementation

- Checks must run when no browser is open: Beat emits a dispatcher every 15s.
- Queue loss must not silently abandon work: PostgreSQL CheckJob is the durable
  outbox; Redis delivery is retried after two minutes. Jobs are locked, completed
  transactionally and deduplicated by database constraints.
- Failures must form meaningful events: a monitor-row lock serializes incident
  transitions, with one open incident enforced by PostgreSQL. Old results cannot
  reopen recovered incidents. Thirty-day check retention nulls incident references
  while retaining timestamps and notification records.
- Email failure must not erase incidents: transitions create durable notification
  rows. Delivery uses capped exponential retry. SMTP is at-least-once: a crash after
  SMTP acceptance but before database commit can duplicate email.
- Customers must not read each other's state: monitor/report/billing views query
  through the authenticated workspace membership. Billing actions require owner.
- Payment redirects are not authority: signed raw-body webhooks are deduplicated;
  current matching-price subscriptions are reconciled under an account lock.
  Periodic reconciliation repairs missed events. Only active subscriptions allow
  customer scheduling; workers check entitlement again before outbound work.

## SSRF

URL forms reject credentials, non-HTTP schemes, unusual ports and obvious private
destinations. Execution validates DNS addresses and disables redirects. Production
checks require an explicit Squid proxy which rejects private, loopback, metadata,
reserved and multicast destinations at connection time, including HTTPS CONNECT.
The proxy is private to each environment; it is not a public forward proxy.

Application workers still need private PostgreSQL/Redis and provider connectivity.
This is an outbound-request safety boundary, not a sandbox against arbitrary code
execution in a compromised worker. An even stronger deployment would isolate the
HTTP fetcher into a network-only probe role with no database/provider credentials.

## Observability and recovery

Web readiness checks PostgreSQL only. Redis failure does not incorrectly declare
the interactive application unready. Private metrics cover broker depth,
durable backlog age, dispatcher/worker/canary freshness, notification failures,
billing projection freshness and HTTP latency/error counts. Host and public TLS
probes augment these. Metric labels contain routes/environments, not tenant URLs.

Prometheus alerts flow to Alertmanager and a curated public read-only page.
Grafana stays private. Reticle reads real health/Prometheus results and displays
dependencies and runbook notes. No public shell/actions are enabled.

Logs are structured stdout with bounded Docker rotation. Prometheus retains
15 days or 2 GB. There is no separate log-search database in this small deployment.
The entire monitoring stack shares EC2's failure domain; the scheduled GitHub
HTTPS check provides a best-effort external signal, not a paging SLA.

Database backups use custom-format pg_dump. Restore drills create a fresh isolated
PostgreSQL container, restore, run Django checks and validate application state.
Redis is ephemeral. Reports require S3 for host-independent durability. Caddy
certificates and observability history are local volumes and can be reconstructed
or deliberately preserved according to the recovery runbook.
