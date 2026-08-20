#!/usr/bin/env bash
set -euo pipefail

# This script is intentionally destructive to the disposable CI Compose volumes.
# It must never be pointed at a production Compose project or production data.

base_url="http://127.0.0.1:8000/api/v1"
backup_dir="/tmp/goreecloud-notes-backup-restore"
cookie_before="/tmp/goreecloud-notes-recovery-before-cookies.txt"
cookie_after="/tmp/goreecloud-notes-recovery-after-cookies.txt"
image_file="/tmp/goreecloud-notes-recovery.png"
restored_file="/tmp/goreecloud-notes-recovery-restored.png"
password='ci-only-recovery-password-97531'

rm -rf "$backup_dir"
mkdir -p "$backup_dir"
rm -f "$cookie_before" "$cookie_after" "$image_file" "$restored_file"

json_field() {
  python - "$1" "$2" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    print(json.load(handle)[sys.argv[2]])
PY
}

csrf_from() {
  awk '$6 == "goreecloud_notes_csrf" { print $7 }' "$1"
}

wait_for_db() {
  # The official PostgreSQL image starts a temporary local server while an empty
  # data directory is initialized, then shuts it down before exec'ing the final
  # postgres process as PID 1. pg_isready can therefore briefly succeed too
  # early. Require both the final PID 1 process and database readiness so a
  # destructive restore never races the bootstrap server shutdown.
  for attempt in $(seq 1 60); do
    if docker compose exec -T db sh -c \
      '[ "$(cat /proc/1/comm)" = "postgres" ] && pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
      >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo 'PostgreSQL final server did not become ready.' >&2
  return 1
}

wait_for_api() {
  for attempt in $(seq 1 30); do
    if curl --fail --silent --show-error http://127.0.0.1:8000/ready >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo 'GoreeCloud Notes API did not become ready.' >&2
  return 1
}

# Create a dedicated recovery fixture with a native inline image so the recovery
# proves both relational state and private attachment bytes survive together.
printf '%s\n' "$password" | \
  docker compose exec -T api python -m app.cli create-user \
    --username recovery-user \
    --display-name 'Recovery User' \
    --password-stdin

curl --fail --silent --show-error \
  --cookie-jar "$cookie_before" \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"recovery-user\",\"password\":\"$password\"}" \
  "$base_url/auth/login" > /tmp/goreecloud-notes-recovery-login-before.json
csrf_before=$(csrf_from "$cookie_before")
test -n "$csrf_before"

curl --fail --silent --show-error \
  --cookie "$cookie_before" \
  --header "X-CSRF-Token: $csrf_before" \
  --header 'Content-Type: application/json' \
  --data '{"title":"Recovery validation note"}' \
  "$base_url/notes" > /tmp/goreecloud-notes-recovery-note.json
note_id=$(json_field /tmp/goreecloud-notes-recovery-note.json id)

python - "$image_file" <<'PY'
import base64, sys
payload = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLzNwAAAABJRU5ErkJggg=='
)
with open(sys.argv[1], 'wb') as handle:
    handle.write(payload)
PY
image_sha=$(sha256sum "$image_file" | awk '{print $1}')

curl --fail --silent --show-error \
  --cookie "$cookie_before" \
  --header "X-CSRF-Token: $csrf_before" \
  --header 'Content-Type: image/png' \
  --data-binary "@$image_file" \
  "$base_url/notes/$note_id/attachments?filename=recovery.png" \
  > /tmp/goreecloud-notes-recovery-attachment.json
attachment_id=$(json_field /tmp/goreecloud-notes-recovery-attachment.json id)

python - "$attachment_id" <<'PY' > /tmp/goreecloud-notes-recovery-patch.json
import json, sys
json.dump({
    'document': {
        'format': 'goreecloud.blocks',
        'version': 1,
        'blocks': [
            {
                'type': 'paragraph',
                'content': [{'type': 'text', 'text': 'Database and attachment recovery marker.'}],
            },
            {
                'type': 'attachmentImage',
                'attachment_id': sys.argv[1],
                'alt': 'Recovery validation image',
            },
        ],
    },
    'expected_content_version': 1,
}, sys.stdout)
PY

curl --fail --silent --show-error \
  --cookie "$cookie_before" \
  --request PATCH \
  --header "X-CSRF-Token: $csrf_before" \
  --header 'Content-Type: application/json' \
  --data-binary @/tmp/goreecloud-notes-recovery-patch.json \
  "$base_url/notes/$note_id" > /tmp/goreecloud-notes-recovery-note-patched.json
test "$(json_field /tmp/goreecloud-notes-recovery-note-patched.json content_version)" = "2"

# Capture a database-native custom dump and a filesystem archive independently.
docker compose exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-privileges' \
  > "$backup_dir/database.dump"

docker compose exec -T api python - <<'PY'
from pathlib import Path
import tarfile
root = Path('/var/lib/goreecloud-notes/attachments')
with tarfile.open('/tmp/goreecloud-notes-attachments.tar.gz', 'w:gz') as archive:
    if root.exists():
        for path in sorted(root.rglob('*')):
            if path.is_file():
                archive.add(path, arcname=path.relative_to(root))
PY

docker compose cp api:/tmp/goreecloud-notes-attachments.tar.gz "$backup_dir/attachments.tar.gz" >/dev/null
(
  cd "$backup_dir"
  sha256sum database.dump attachments.tar.gz > SHA256SUMS
  sha256sum --check SHA256SUMS
)

# Record the expected fixture identifiers outside the disposable volumes.
printf '%s\n' "$note_id" > "$backup_dir/note_id"
printf '%s\n' "$attachment_id" > "$backup_dir/attachment_id"
printf '%s\n' "$image_sha" > "$backup_dir/image_sha256"

# Destroy both primary persistence volumes. This is the destructive evidence step.
docker compose down --volumes --remove-orphans

# Recreate only PostgreSQL, then restore the database dump into the clean volume.
docker compose up --detach db
wait_for_db
cat "$backup_dir/database.dump" | docker compose exec -T db sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges'

# A historical database restore can contain browser sessions and short-lived rate
# state that were valid when the backup was taken. Fail closed by invalidating
# those restored ephemeral authorization records before the application starts.
docker compose exec -T db sh -c \
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "TRUNCATE auth_sessions, login_rate_buckets"' \
  >/dev/null

# Restore attachment bytes into the newly created named attachment volume without
# starting the API against an incomplete filesystem. Archive members are checked
# for absolute/path-traversal names before extraction.
docker compose run --rm --no-deps \
  --volume "$backup_dir:/backup:ro" \
  api python - <<'PY'
from pathlib import Path, PurePosixPath
import tarfile
archive_path = Path('/backup/attachments.tar.gz')
root = Path('/var/lib/goreecloud-notes/attachments')
root.mkdir(parents=True, exist_ok=True)
with tarfile.open(archive_path, 'r:gz') as archive:
    members = archive.getmembers()
    for member in members:
        name = PurePosixPath(member.name)
        if name.is_absolute() or '..' in name.parts or not member.isfile():
            raise SystemExit(f'unsafe attachment archive member: {member.name!r}')
    archive.extractall(root, members=members, filter='data')
PY

# Start the restored application only after both persistence layers exist.
docker compose up --detach api
wait_for_api

# Schema metadata must still match the recovered database.
docker compose run --rm api alembic check

# The pre-backup browser cookie must not survive the recovery-sanitization step.
restored_old_session_status=$(curl \
  --silent --show-error \
  --cookie "$cookie_before" \
  --output /dev/null \
  --write-out '%{http_code}' \
  "$base_url/auth/me")
test "$restored_old_session_status" = "401"

# The account credential remains recoverable and can establish a fresh session.
curl --fail --silent --show-error \
  --cookie-jar "$cookie_after" \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"recovery-user\",\"password\":\"$password\"}" \
  "$base_url/auth/login" > /tmp/goreecloud-notes-recovery-login-after.json

# Verify native document content and the restored attachment relationship.
curl --fail --silent --show-error \
  --cookie "$cookie_after" \
  "$base_url/notes/$note_id" > /tmp/goreecloud-notes-recovery-note-after.json
python - "$attachment_id" <<'PY'
import json, sys
with open('/tmp/goreecloud-notes-recovery-note-after.json', encoding='utf-8') as handle:
    note = json.load(handle)
assert note['title'] == 'Recovery validation note'
assert note['content_version'] == 2
blocks = note['document']['blocks']
assert blocks[0]['content'][0]['text'] == 'Database and attachment recovery marker.'
assert blocks[1] == {
    'type': 'attachmentImage',
    'attachment_id': sys.argv[1],
    'alt': 'Recovery validation image',
}
PY

curl --fail --silent --show-error \
  --cookie "$cookie_after" \
  "$base_url/attachments/$attachment_id/preview" > "$restored_file"
test "$(sha256sum "$restored_file" | awk '{print $1}')" = "$image_sha"
cmp "$image_file" "$restored_file"

# Database integrity and restored ephemeral-state sanitation remain explicit.
docker compose exec -T db sh -c \
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM auth_sessions; SELECT count(*) FROM login_rate_buckets;"' \
  > "$backup_dir/restored-security-state.txt"
grep -Eq '^ *1 *$' "$backup_dir/restored-security-state.txt"  # fresh post-restore login session
grep -Eq '^ *0 *$' "$backup_dir/restored-security-state.txt"  # no restored rate state

# Prove the recovered state can immediately produce another valid recovery point.
docker compose exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-privileges' \
  > "$backup_dir/post-restore-database.dump"
test -s "$backup_dir/post-restore-database.dump"

printf 'GoreeCloud Notes disposable backup/restore validation passed.\n'
