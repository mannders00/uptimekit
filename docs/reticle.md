# Reticle live evidence

The local Go/Wails refactor at `~/doc/dev/pro/reticle` supplies the daemon binary.
Its private source and commercial binary are not published in this public repo.
Build an ARM64 Linux daemon using its documented build command, record version,
source revision/worktree status and binary SHA-256, and upload via SCP.
Use `sudo bash scripts/install-reticle.sh /path/to/uploaded/reticle-daemon`
from an uploaded release bundle to install the supplied topology/service.

The current local build includes a WebSocket bearer-authentication fix in
`internal/daemon/websocket.go` and a dedicated regression test in
`internal/daemon/websocket_bearer_test.go`. HTTP and WebSocket now both honor the
proxy's viewer authorization header ahead of caller query tokens.

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
The inspected daemon's static CSP hash differed from its embedded import map.
Caddy supplies the measured SHA-256 hash for that one inline import map and routes
its root-relative `/vendor/*` imports. This compatibility shim must be rechecked
on daemon upgrades; it does not enable arbitrary inline script. Cloudflare's
injected analytics script remains blocked by that policy.

Collectors use fixed HTTP probes against readiness and Prometheus, not arbitrary
shell commands. `jq` predicates require a nonempty result and enforce freshness
thresholds. Reticle history is transient in-memory; Prometheus owns longer-lived
metrics. A green graph does not prove an unconfigured email/S3 integration.

When replacing the binary: validate `--check-config`, record the digest, restart
the service, inspect the graph and test that viewer mutation attempts are refused.
