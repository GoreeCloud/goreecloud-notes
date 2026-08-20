#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:8000/api/v1"
owner_cookies="/tmp/goreecloud-notes-quota-owner-cookies.txt"
other_cookies="/tmp/goreecloud-notes-quota-other-cookies.txt"
owner_first="/tmp/goreecloud-notes-quota-owner-first.bin"
owner_overflow="/tmp/goreecloud-notes-quota-owner-overflow.bin"
other_file="/tmp/goreecloud-notes-quota-other.bin"

json_field() {
  python - "$1" "$2" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)[sys.argv[2]])
PY
}

status_of() {
  curl --silent --show-error --output /dev/null --write-out '%{http_code}' "$@"
}

login_user() {
  local username="$1" password="$2" cookie_file="$3" output_file="$4"
  curl --fail --silent --show-error \
    --cookie-jar "$cookie_file" \
    --header 'Content-Type: application/json' \
    --data "{\"username\":\"$username\",\"password\":\"$password\"}" \
    "$base_url/auth/login" > "$output_file"
}

csrf_from() {
  awk '$6 == "goreecloud_notes_csrf" { print $7 }' "$1"
}

printf '%s\n' 'ci-quota-owner-password-12345' | docker compose exec -T api python -m app.cli create-user \
  --username quota-owner --display-name 'Quota Owner' --password-stdin
printf '%s\n' 'ci-quota-other-password-12345' | docker compose exec -T api python -m app.cli create-user \
  --username quota-other --display-name 'Quota Other' --password-stdin

login_user quota-owner ci-quota-owner-password-12345 "$owner_cookies" /tmp/quota-owner-login.json
login_user quota-other ci-quota-other-password-12345 "$other_cookies" /tmp/quota-other-login.json
owner_csrf=$(csrf_from "$owner_cookies")
other_csrf=$(csrf_from "$other_cookies")
test -n "$owner_csrf"
test -n "$other_csrf"

curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' \
  --data '{"title":"Owner quota validation"}' "$base_url/notes" > /tmp/quota-owner-note.json
owner_note_id=$(json_field /tmp/quota-owner-note.json id)

curl --fail --silent --show-error --cookie "$other_cookies" \
  --header "X-CSRF-Token: $other_csrf" --header 'Content-Type: application/json' \
  --data '{"title":"Other quota validation"}' "$base_url/notes" > /tmp/quota-other-note.json
other_note_id=$(json_field /tmp/quota-other-note.json id)

python - "$owner_first" "$owner_overflow" "$other_file" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_bytes(b"a" * 40_000)
Path(sys.argv[2]).write_bytes(b"b" * 30_000)
Path(sys.argv[3]).write_bytes(b"c" * 40_000)
PY

curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/octet-stream' \
  --data-binary "@$owner_first" \
  "$base_url/notes/$owner_note_id/attachments?filename=owner-first.bin" > /tmp/quota-owner-first.json

# The CI stack configures a 65,536-byte owner quota. The first 40,000 bytes fit;
# another 30,000-byte object stays below the per-file 50 MiB limit but must exceed
# the owner's aggregate quota. This distinguishes quota enforcement from file-size enforcement.
test "$(status_of --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/octet-stream' \
  --data-binary "@$owner_overflow" \
  "$base_url/notes/$owner_note_id/attachments?filename=owner-overflow.bin")" = "413"

curl --fail --silent --show-error --cookie "$owner_cookies" \
  "$base_url/notes/$owner_note_id/attachments" > /tmp/quota-owner-list.json
python - <<'PY'
import json
with open('/tmp/quota-owner-list.json', encoding='utf-8') as handle:
    items = json.load(handle)
assert len(items) == 1
assert items[0]['filename'] == 'owner-first.bin'
assert items[0]['size_bytes'] == 40_000
PY

# Quotas are owner-scoped rather than global. A second user still has an independent
# 65,536-byte allowance and can persist a 40,000-byte attachment.
curl --fail --silent --show-error --cookie "$other_cookies" \
  --header "X-CSRF-Token: $other_csrf" --header 'Content-Type: application/octet-stream' \
  --data-binary "@$other_file" \
  "$base_url/notes/$other_note_id/attachments?filename=other.bin" > /tmp/quota-other.json

test "$(json_field /tmp/quota-other.json size_bytes)" = "40000"

# A rejected upload must not leave temporary or final orphan bytes behind.
docker compose exec -T api sh -c \
  'test "$(find /var/lib/goreecloud-notes/attachments -type f -name "*.part" | wc -l)" -eq 0'
