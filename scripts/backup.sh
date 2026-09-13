#!/usr/bin/env bash
source "$(dirname "$0")/common.sh" "${1:-}"
if [[ "${2:-}" != --locked ]]; then exec 9>"$STATE/operation.lock"; flock -w 900 9; fi
load_release
umask 077
mkdir -p "$STATE/backups"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
FILE="$STATE/backups/$STAMP.dump"
compose exec -T db pg_dump -U uptimekit -d uptimekit --format=custom > "$FILE.partial"
test -s "$FILE.partial"
mv "$FILE.partial" "$FILE"
(cd "$STATE/backups" && sha256sum "$STAMP.dump" > "$STAMP.dump.sha256")
compose exec -T db pg_restore --list < "$FILE" >/dev/null
printf 'uptimekit_backup_timestamp_seconds{environment="%s"} %s\n' "$ENVIRONMENT" "$(date +%s)" > "/var/lib/uptimekit/metrics/backup-$ENVIRONMENT.prom.tmp"
chmod 644 "/var/lib/uptimekit/metrics/backup-$ENVIRONMENT.prom.tmp"
mv "/var/lib/uptimekit/metrics/backup-$ENVIRONMENT.prom.tmp" "/var/lib/uptimekit/metrics/backup-$ENVIRONMENT.prom"
set -a
source /etc/uptimekit/backup.env
set +a
if [[ -n "${BACKUP_BUCKET:-}" ]]; then
  aws s3 cp "$FILE" "s3://$BACKUP_BUCKET/$ENVIRONMENT/$STAMP.dump" --sse AES256 --only-show-errors
  aws s3 cp "$FILE.sha256" "s3://$BACKUP_BUCKET/$ENVIRONMENT/$STAMP.dump.sha256" --sse AES256 --only-show-errors
  printf 'uptimekit_offhost_backup_timestamp_seconds{environment="%s"} %s\n' "$ENVIRONMENT" "$(date +%s)" > "/var/lib/uptimekit/metrics/offhost-$ENVIRONMENT.prom.tmp"
  chmod 644 "/var/lib/uptimekit/metrics/offhost-$ENVIRONMENT.prom.tmp"
  mv "/var/lib/uptimekit/metrics/offhost-$ENVIRONMENT.prom.tmp" "/var/lib/uptimekit/metrics/offhost-$ENVIRONMENT.prom"
else
  echo 'Off-host backup NOT configured; local backup only.' >&2
fi
# Retain local daily/pre-release dumps for seven days; S3 lifecycle is independent.
find "$STATE/backups" -type f -mtime +7 -delete
echo "Backup complete: $ENVIRONMENT $STAMP"
