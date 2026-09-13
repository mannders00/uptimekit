# Reticle live evidence

The local Go/Wails refactor at `~/doc/dev/pro/reticle` supplies the daemon binary.
Its private source and commercial binary are not published in this public repo.
Build an ARM64 Linux daemon using its documented build command, record version,
source revision/worktree status and binary SHA-256, and upload via SCP.

Install to `/usr/local/bin/reticle-daemon`. Create a system user `reticle`, install
`ops/reticle/topology.yaml` at `/etc/reticle/uptimekit.yaml`, and install the supplied
systemd service. `/etc/uptimekit/reticle.env` contains a generated viewer token.
No editor token, `--open`, custom commands, Docker socket or action definitions
are supplied. The daemon binds Docker's default bridge address `172.17.0.1`;
the EC2 security group must not expose port 8788.

Caddy strips `/reticle/` for relative frontend assets and routes `/ws`,
`/api/graph`, `/api/history`, `/mcp` to the same daemon. It injects only the viewer
token. These paths are intentionally public read-only evidence. Reticle's current
frontend uses root-relative websocket paths, hence those explicit routes.
The infrastructure page embeds `/reticle/` on the same origin.

Collectors use fixed HTTP probes against readiness and Prometheus, not arbitrary
shell commands. `jq` predicates require a nonempty result and enforce freshness
thresholds. Reticle history is transient in-memory; Prometheus owns longer-lived
metrics. A green graph does not prove an unconfigured email/S3 integration.

When replacing the binary: validate `--check-config`, record the digest, restart
the service, inspect the graph and test that viewer mutation attempts are refused.
