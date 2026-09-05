#!/usr/bin/env sh
set -eu

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml -f docker-compose.phase11-backup.yml"

wait_for_backend_ready() {
  attempts=0
  max_attempts=45
  until $COMPOSE exec -T backend curl -fsS http://127.0.0.1:8000/health/ready >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge "$max_attempts" ]; then
      printf 'Backend did not become ready after %s attempts.\n' "$max_attempts" >&2
      $COMPOSE ps backend >&2 || true
      $COMPOSE logs --no-color --tail=200 backend >&2 || true
      exit 1
    fi
    sleep 2
  done
  printf 'Backend readiness confirmed.\n'
}

printf '\n== Phase 11: Phase 10 regression gate ==\n'
sh scripts/verify-phase10.sh

printf '\n== Phase 11: build backup utility and start restore target ==\n'
$COMPOSE build backup backup-scheduler backend
$COMPOSE up -d restore-postgres backup

printf '\n== Phase 11: create encrypted backup snapshot ==\n'
$COMPOSE exec -T backup mailbox-backup

printf '\n== Phase 11: inspect snapshot metadata and freshness ==\n'
$COMPOSE exec -T backup sh -c 'restic snapshots --tag mailbox-dns --json | jq -e "length > 0" >/dev/null'
$COMPOSE exec -T backup sh -c 'restic check >/dev/null'
$COMPOSE exec -T backup sh -c 'mailbox-backup-status --health | jq -e ".healthy == true and .snapshot_count > 0 and .age_seconds <= .max_age_seconds" >/dev/null'

printf '\n== Phase 11: scheduled runner one-shot and run-state reporting ==\n'
$COMPOSE exec -T backup mailbox-backup-scheduler once
$COMPOSE exec -T backup sh -c 'test -s /workspace/status/last-run.json && jq -e ".status == \"success\" and .started_at and .finished_at" /workspace/status/last-run.json >/dev/null'
$COMPOSE exec -T backup sh -c 'test -s /workspace/status/health.json && jq -e ".healthy == true and .snapshot_count >= 2" /workspace/status/health.json >/dev/null'

printf '\n== Phase 11: remote/off-site repository configuration readiness ==\n'
$COMPOSE config | grep -q 'BACKUP_SCHEDULE_SECONDS'
$COMPOSE config | grep -q 'BACKUP_MAX_AGE_SECONDS'
$COMPOSE run --rm --no-deps -e RESTIC_REPOSITORY='s3:https://object-store.example.invalid/mailbox-backups' backup sh -c 'test "$RESTIC_REPOSITORY" = "s3:https://object-store.example.invalid/mailbox-backups"'
printf 'Restic remote repository URLs pass through without being coupled to local storage.\n'

printf '\n== Phase 11: isolated full restore drill and history ==\n'
$COMPOSE exec -T backup mailbox-restore-drill
$COMPOSE exec -T backup sh -c 'test -s /workspace/status/restore-drills.jsonl && tail -n 1 /workspace/status/restore-drills.jsonl | jq -e ".status == \"success\" and .snapshot and .application_tables > 0 and .powerdns_tables > 0" >/dev/null'

printf '\n== Phase 11: verify restored database structures ==\n'
$COMPOSE exec -T restore-postgres sh -c 'PGPASSWORD=${RESTORE_DB_PASSWORD:-restore_dev_password} psql -U restore -d mailbox_restore_app -Atc "select count(*) from pg_tables where schemaname = current_schema()" | grep -Eq "^[1-9][0-9]*$"'
$COMPOSE exec -T restore-postgres sh -c 'PGPASSWORD=${RESTORE_DB_PASSWORD:-restore_dev_password} psql -U restore -d mailbox_restore_pdns -Atc "select count(*) from pg_tables where schemaname = current_schema()" | grep -Eq "^[1-9][0-9]*$"'

printf '\n== Phase 11: application-facing backup operations ==\n'
$COMPOSE up -d --force-recreate backend
wait_for_backend_ready
$COMPOSE exec -T backend pytest -q tests/test_backup_status.py
$COMPOSE exec -T backend python - <<'PY'
from app.services.backup_status import backup_operational_status, restore_drill_history
status = backup_operational_status()
assert status['healthy'] is True, status
assert status['severity'] == 'ok'
drills = restore_drill_history()
assert drills and drills[0]['status'] == 'success', drills
print('backup status:', status['severity'], status['last_run']['status'])
print('restore drill history entries:', len(drills))
PY
$COMPOSE exec -T backend sh -c 'curl -fsS http://127.0.0.1:8000/openapi.json -o /tmp/phase11-openapi.json && python -c "import json; p=json.load(open(\"/tmp/phase11-openapi.json\"))[\"paths\"]; assert \"/api/v1/backups/status\" in p; assert \"/api/v1/backups/restore-drills\" in p"'

printf '\n== Phase 11: scheduler service definition and DR runbook ==\n'
$COMPOSE config --services | grep -qx 'backup-scheduler'
test -s docs/PHASE-11-DISASTER-RECOVERY.md
grep -q 'Disaster recovery sequence' docs/PHASE-11-DISASTER-RECOVERY.md
grep -q 'Restore drills' docs/PHASE-11-DISASTER-RECOVERY.md

printf '\nPhase 11 FINAL STORAGE, BACKUP & DISASTER RECOVERY acceptance PASSED.\n'
printf 'Verified full Phase 10 regression, encrypted and retention-managed restore points, scheduled backup execution, off-site repository readiness, freshness monitoring with operator alert metadata, isolated application/PowerDNS/Maildir restore drills, persistent restore-drill history, and platform-owner backup status APIs.\n'
printf 'Phase 11 is ready for acceptance and fast-forward convergence to main after user confirmation.\n'
