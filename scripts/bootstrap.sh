#!/usr/bin/env bash
set -Eeuo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run with sudo' >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose curl jq rsync python3 openssl awscli
systemctl enable --now docker
usermod -aG docker admin
install -d -m 0750 -o admin -g admin /etc/uptimekit /opt/uptimekit /var/lib/uptimekit
install -d -m 0755 -o admin -g admin /var/lib/uptimekit/metrics
docker network inspect uptimekit-ops >/dev/null 2>&1 || docker network create uptimekit-ops
python3 "$(dirname "$0")/configure_host.py"
echo 'Bootstrap complete. Reconnect SSH to activate docker group membership.'
