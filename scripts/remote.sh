#!/usr/bin/env bash
set -Eeuo pipefail
ENVIRONMENT=${1:?}
ACTION=${2:?}
IMAGE=${3:-}
[[ "$ENVIRONMENT" == dev || "$ENVIRONMENT" == prod || "$ENVIRONMENT" == ops ]]
[[ "$ACTION" =~ ^(deploy|backup|restore-drill|status|smoke|rollback|worker-drill|redis-drill|db-drill|restart|observability)$ ]]
[[ -z "$IMAGE" || "$IMAGE" =~ ^ghcr.io/mannders00/uptimekit@sha256:[a-f0-9]{64}$ ]]
: "${SSH_HOST:?}" "${SSH_USER:?}" "${SSH_KEY:?}" "${SSH_KNOWN_HOSTS:?}"
[[ "$SSH_HOST" =~ ^[a-zA-Z0-9.-]+$ && "$SSH_USER" =~ ^[a-zA-Z0-9_-]+$ ]]
TEMP=$(mktemp -d)
trap 'rm -rf "$TEMP"' EXIT
printf '%s\n' "$SSH_KEY" > "$TEMP/key"
printf '%s\n' "$SSH_KNOWN_HOSTS" > "$TEMP/known_hosts"
chmod 600 "$TEMP/key" "$TEMP/known_hosts"
SSH=(ssh -i "$TEMP/key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$TEMP/known_hosts")
TARGET="$SSH_USER@$SSH_HOST"
REVISION=$(git rev-parse HEAD)
[[ "$REVISION" =~ ^[a-f0-9]{40}$ ]]
DEST="/opt/uptimekit/releases/$REVISION"
"${SSH[@]}" "$TARGET" "mkdir -p '$DEST'"
git archive HEAD | "${SSH[@]}" "$TARGET" "tar -x -C '$DEST'"
case "$ACTION" in
  deploy) "${SSH[@]}" "$TARGET" "bash '$DEST/scripts/deploy.sh' '$ENVIRONMENT' '$IMAGE'" ;;
  backup|restore-drill) "${SSH[@]}" "$TARGET" "bash '$DEST/scripts/$ACTION.sh' '$ENVIRONMENT'" ;;
  observability) "${SSH[@]}" "$TARGET" "docker compose -f '$DEST/ops/compose.yaml' up -d" ;;
  *) "${SSH[@]}" "$TARGET" "bash '$DEST/scripts/operate.sh' '$ENVIRONMENT' '$ACTION'" ;;
esac
