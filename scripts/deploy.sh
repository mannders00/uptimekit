#!/usr/bin/env bash
source "$(dirname "$0")/common.sh" "${1:-}"
IMAGE=${2:?Pass immutable image digest}
[[ "$IMAGE" =~ ^ghcr.io/mannders00/uptimekit@sha256:[a-f0-9]{64}$ ]] || { echo 'Invalid image digest' >&2; exit 2; }
exec 9>"$STATE/operation.lock"
flock -w 900 9
if [[ "$ENVIRONMENT" == prod ]]; then
  test "$(</var/lib/uptimekit/dev/verified.image)" = "$IMAGE" || { echo 'Production requires the currently verified dev digest' >&2; exit 1; }
fi
OLD=''
[[ ! -f "$STATE/current.image" ]] || OLD=$(<"$STATE/current.image")
export APP_IMAGE="$IMAGE"
rollback_on_error() {
  trap - ERR
  echo 'Release failed; restoring previous application artifact (schema is not reversed).'
  if [[ -n "$OLD" ]]; then
    export APP_IMAGE="$OLD"
    compose up -d --no-deps web worker beat
    compose run --rm --no-deps web python manage.py runtime_check
  fi
  exit 1
}
trap rollback_on_error ERR
compose pull
compose up -d db redis check-proxy
if [[ -n "$OLD" ]]; then
  # The operation lock is already held by this process.
  bash "$ROOT/scripts/backup.sh" "$ENVIRONMENT" --locked
fi
compose run --rm --no-deps web python manage.py check --deploy --fail-level WARNING
compose run --rm --no-deps web python manage.py migrate --noinput
compose up -d --no-deps web worker beat
compose run --rm --no-deps web python manage.py seed_canary
compose run --rm --no-deps web python manage.py check_egress
compose run --rm --no-deps web python manage.py runtime_check
[[ -z "$OLD" ]] || printf '%s\n' "$OLD" > "$STATE/previous.image"
printf '%s\n' "$IMAGE" > "$STATE/current.image"
printf '%s\n' "$IMAGE" > "$STATE/verified.image"
printf '{"environment":"%s","image":"%s","verified_at":"%s"}\n' "$ENVIRONMENT" "$IMAGE" "$(date -u +%FT%TZ)" | tee "$STATE/release.json"
