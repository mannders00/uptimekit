#!/usr/bin/env bash
source "$(dirname "$0")/common.sh" "${1:-}"
exec 9>"$STATE/operation.lock"
flock -w 900 9
load_release
bash "$ROOT/scripts/backup.sh" "$ENVIRONMENT" --locked
FILE=$(ls -1t "$STATE"/backups/*.dump | head -1)
SOURCE=local
DOWNLOAD=''
set -a
source /etc/uptimekit/backup.env
set +a
if [[ -n "${BACKUP_BUCKET:-}" ]]; then
  SOURCE=s3
  DOWNLOAD=$(mktemp -d "$STATE/restore-download.XXXXXX")
  BASENAME=$(basename "$FILE")
  aws s3 cp "s3://$BACKUP_BUCKET/$ENVIRONMENT/$BASENAME" "$DOWNLOAD/$BASENAME" --only-show-errors
  aws s3 cp "s3://$BACKUP_BUCKET/$ENVIRONMENT/$BASENAME.sha256" "$DOWNLOAD/$BASENAME.sha256" --only-show-errors
  FILE="$DOWNLOAD/$BASENAME"
fi
(cd "$(dirname "$FILE")" && sha256sum -c "$(basename "$FILE").sha256")
START=$(date +%s)
NAME="uptimekit-restore-$ENVIRONMENT-$$"
PASSWORD=$(openssl rand -hex 24)
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; docker network rm "$NAME" >/dev/null 2>&1 || true; [[ -z "$DOWNLOAD" ]] || rm -rf "$DOWNLOAD"; }
trap cleanup EXIT
docker network create --internal "$NAME" >/dev/null
docker run -d --name "$NAME" --network "$NAME" --network-alias db --memory 320m \
  -e POSTGRES_PASSWORD="$PASSWORD" -e POSTGRES_USER=uptimekit -e POSTGRES_DB=uptimekit postgres:17.9-bookworm >/dev/null
for attempt in {1..30}; do docker exec "$NAME" pg_isready -U uptimekit -d uptimekit && break; sleep 2; done
docker exec -i "$NAME" pg_restore -U uptimekit -d uptimekit --exit-on-error --no-owner < "$FILE"
docker run --rm --network "$NAME" --env-file "$APP_ENV_FILE" -e POSTGRES_PASSWORD="$PASSWORD" "$APP_IMAGE" python manage.py check
docker run --rm --network "$NAME" --env-file "$APP_ENV_FILE" -e POSTGRES_PASSWORD="$PASSWORD" "$APP_IMAGE" python manage.py verify_restore
DURATION=$(( $(date +%s) - START ))
printf '{"environment":"%s","backup_source":"%s","restore_seconds":%s,"verified_at":"%s"}\n' "$ENVIRONMENT" "$SOURCE" "$DURATION" "$(date -u +%FT%TZ)" | tee "$STATE/restore.json"
printf 'uptimekit_restore_timestamp_seconds{environment="%s"} %s\nuptimekit_restore_duration_seconds{environment="%s"} %s\n' "$ENVIRONMENT" "$(date +%s)" "$ENVIRONMENT" "$DURATION" > "/var/lib/uptimekit/metrics/restore-$ENVIRONMENT.prom.tmp"
mv "/var/lib/uptimekit/metrics/restore-$ENVIRONMENT.prom.tmp" "/var/lib/uptimekit/metrics/restore-$ENVIRONMENT.prom"
