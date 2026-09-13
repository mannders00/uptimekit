#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ENVIRONMENT=${1:?Pass dev or prod}
[[ "$ENVIRONMENT" == dev || "$ENVIRONMENT" == prod ]] || { echo 'Invalid environment' >&2; exit 2; }
export ENVIRONMENT APP_ENV_FILE="/etc/uptimekit/$ENVIRONMENT.env"
STATE="/var/lib/uptimekit/$ENVIRONMENT"
mkdir -p "$STATE"
compose() { docker compose --env-file "$APP_ENV_FILE" -f "$ROOT/compose.yaml" "$@"; }
load_release() {
  test -s "$STATE/current.image"
  APP_IMAGE=$(<"$STATE/current.image")
  export APP_IMAGE
}
