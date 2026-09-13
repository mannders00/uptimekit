#!/usr/bin/env bash
set -Eeuo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run with sudo' >&2; exit 1; }
BINARY=${1:?Pass the uploaded ARM64 daemon binary path}
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
id reticle >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin reticle
install -d -m 0755 /etc/reticle
"$BINARY" --config "$ROOT/ops/reticle/topology.yaml" --check-config
systemctl stop reticle 2>/dev/null || true
install -m 0755 "$BINARY" /usr/local/bin/reticle-daemon
install -m 0644 "$ROOT/ops/reticle/topology.yaml" /etc/reticle/uptimekit.yaml
install -m 0644 "$ROOT/ops/reticle/reticle.service" /etc/systemd/system/reticle.service
systemctl daemon-reload
systemctl enable --now reticle
systemctl is-active reticle
sha256sum /usr/local/bin/reticle-daemon
