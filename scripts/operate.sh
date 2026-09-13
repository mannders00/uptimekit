#!/usr/bin/env bash
source "$(dirname "$0")/common.sh" "${1:-}"
ACTION=${2:?Pass status, smoke, rollback, worker-drill, redis-drill, db-drill, or restart}
load_release
case "$ACTION" in
  status) compose ps; compose run --rm --no-deps web python manage.py check ;;
  smoke) compose run --rm --no-deps web python manage.py runtime_check ;;
  rollback)
    exec 9>"$STATE/operation.lock"; flock -w 900 9
    IMAGE=$(<"$STATE/previous.image")
    [[ "$IMAGE" =~ ^ghcr.io/mannders00/uptimekit@sha256:[a-f0-9]{64}$ ]]
    OLD=$APP_IMAGE
    export APP_IMAGE="$IMAGE"
    compose up -d --no-deps web worker beat
    compose run --rm --no-deps web python manage.py runtime_check
    printf '%s\n' "$OLD" > "$STATE/previous.image"
    printf '%s\n' "$IMAGE" > "$STATE/current.image"
    ;;
  worker-drill|redis-drill|db-drill)
    [[ "$ENVIRONMENT" == dev ]] || { echo 'Failure drills run in dev' >&2; exit 2; }
    exec 9>"$STATE/operation.lock"; flock -w 900 9
    SERVICE=${ACTION%-drill}
    case "$SERVICE" in
      worker) EXPECTED=MonitoringCanaryStale ;;
      redis) EXPECTED=BrokerUnavailable ;;
      db) EXPECTED=DatabaseUnavailable ;;
    esac
    trap 'compose start "$SERVICE"; compose run --rm --no-deps web python manage.py runtime_check' EXIT
    echo "Drill start: $ACTION $(date -u +%FT%TZ)"
    compose stop "$SERVICE"
    sleep 240
    # Preserve actual evaluated alert names as workflow evidence.
    curl --fail --silent http://localhost:9093/api/v2/alerts | python3 -c 'import json,sys; alerts=[{"name":a["labels"].get("alertname"), "environment":a["labels"].get("environment"), "since":a["startsAt"]} for a in json.load(sys.stdin)]; print(json.dumps(alerts)); assert any(a["name"] == sys.argv[1] and a["environment"] == "dev" for a in alerts), "Expected dev alert did not fire"' "$EXPECTED"
    echo "Drill end: $ACTION $(date -u +%FT%TZ)"
    ;;
  restart)
    exec 9>"$STATE/operation.lock"; flock -w 900 9
    compose restart web worker beat
    compose run --rm --no-deps web python manage.py runtime_check
    ;;
  *) echo 'Unsupported action' >&2; exit 2 ;;
esac
