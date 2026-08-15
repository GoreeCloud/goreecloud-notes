#!/usr/bin/env bash
set -euo pipefail

username='ci-audit-user'
initial_password='ci-only-admin-audit-password-12345'
recovered_password='ci-only-admin-audit-recovery-67890'
operator='ci-admin-audit-validation'
audit_output='/tmp/goreecloud-notes-admin-audit.json'

printf '%s\n' "$initial_password" | \
  docker compose exec -T api python -m app.cli create-user \
    --username "$username" \
    --display-name 'CI Audit User' \
    --password-stdin \
    --operator "$operator" \
    --reason 'Create isolated account for administrative audit validation.'

printf '%s\n' "$recovered_password" | \
  docker compose exec -T api python -m app.cli reset-password \
    --username "$username" \
    --password-stdin \
    --operator "$operator" \
    --reason 'Validate audited administrative credential recovery.'

docker compose exec -T api python -m app.cli disable-user \
  --username "$username" \
  --confirm-disable \
  --operator "$operator" \
  --reason 'Validate audited reversible account suspension.'

docker compose exec -T api python -m app.cli enable-user \
  --username "$username" \
  --operator "$operator" \
  --reason 'Validate audited account reinstatement with fresh-session boundary.'

docker compose exec -T api python -m app.cli admin-audit \
  --username "$username" \
  --limit 10 \
  --json > "$audit_output"

python - "$audit_output" "$operator" "$initial_password" "$recovered_password" <<'PY'
import json
import sys
from pathlib import Path

path, operator, initial_password, recovered_password = sys.argv[1:]
raw = Path(path).read_text(encoding="utf-8")
report = json.loads(raw)

assert report["schemaVersion"] == 1
assert len(report["events"]) == 4
assert {event["action"] for event in report["events"]} == {
    "account.create",
    "credential.reset",
    "account.disable",
    "account.enable",
}
assert all(event["operator"] == operator for event in report["events"])
assert all(event["targetUsername"] == "ci-audit-user" for event in report["events"])
assert all(event["reason"].strip() == event["reason"] for event in report["events"])
assert all(event["reason"] for event in report["events"])
assert initial_password not in raw
assert recovered_password not in raw
assert "password_hash" not in raw
assert "csrf" not in raw.casefold()
assert "session_token" not in raw.casefold()
PY

# The database must reject ordinary mutation of an audit event after it is
# committed. Test both UPDATE and DELETE so the trigger contract is explicit.
if docker compose exec -T db sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "UPDATE admin_audit_events SET reason = '\''tampered'\'' WHERE target_username = '\''ci-audit-user'\'';"' \
  > /tmp/goreecloud-notes-admin-audit-update.txt 2>&1; then
  echo 'Administrative audit UPDATE unexpectedly succeeded.' >&2
  exit 1
fi
grep -F 'admin audit events are append-only' /tmp/goreecloud-notes-admin-audit-update.txt

if docker compose exec -T db sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "DELETE FROM admin_audit_events WHERE target_username = '\''ci-audit-user'\'';"' \
  > /tmp/goreecloud-notes-admin-audit-delete.txt 2>&1; then
  echo 'Administrative audit DELETE unexpectedly succeeded.' >&2
  exit 1
fi
grep -F 'admin audit events are append-only' /tmp/goreecloud-notes-admin-audit-delete.txt

# Failed tampering must leave all four committed records intact.
docker compose exec -T api python -m app.cli admin-audit \
  --username "$username" \
  --limit 10 \
  --json > /tmp/goreecloud-notes-admin-audit-after-tamper.json
python - <<'PY'
import json
from pathlib import Path

report = json.loads(Path('/tmp/goreecloud-notes-admin-audit-after-tamper.json').read_text(encoding='utf-8'))
assert len(report['events']) == 4
PY
