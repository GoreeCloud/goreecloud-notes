#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:8000/api/v1"
owner_cookies="/tmp/goreecloud-notes-attachment-owner-cookies.txt"
other_cookies="/tmp/goreecloud-notes-attachment-other-cookies.txt"
source_file="/tmp/goreecloud-notes-attachment-source.txt"
download_file="/tmp/goreecloud-notes-attachment-download.txt"
image_file="/tmp/goreecloud-notes-attachment-preview.png"
preview_file="/tmp/goreecloud-notes-attachment-preview-download.png"
preview_headers="/tmp/goreecloud-notes-attachment-preview-headers.txt"

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

printf '%s\n' 'ci-attachment-owner-password-12345' | docker compose exec -T api python -m app.cli create-user \
  --username attachment-owner --display-name 'Attachment Owner' --password-stdin
printf '%s\n' 'ci-attachment-other-password-12345' | docker compose exec -T api python -m app.cli create-user \
  --username attachment-other --display-name 'Attachment Other' --password-stdin

login_user attachment-owner ci-attachment-owner-password-12345 "$owner_cookies" /tmp/attachment-owner-login.json
login_user attachment-other ci-attachment-other-password-12345 "$other_cookies" /tmp/attachment-other-login.json
owner_csrf=$(csrf_from "$owner_cookies")
other_csrf=$(csrf_from "$other_cookies")
test -n "$owner_csrf"
test -n "$other_csrf"

curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' \
  --data '{"title":"Attachment validation note"}' "$base_url/notes" > /tmp/attachment-note.json
note_id=$(json_field /tmp/attachment-note.json id)

printf '%s' 'GoreeCloud private attachment validation payload' > "$source_file"
expected_sha=$(sha256sum "$source_file" | awk '{print $1}')
expected_size=$(wc -c < "$source_file" | tr -d ' ')

curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --header 'Content-Type: text/plain' \
  --data-binary "@$source_file" \
  "$base_url/notes/$note_id/attachments?filename=validation.txt" > /tmp/attachment.json
attachment_id=$(json_field /tmp/attachment.json id)
test "$(json_field /tmp/attachment.json filename)" = "validation.txt"
test "$(json_field /tmp/attachment.json media_type)" = "text/plain"
test "$(json_field /tmp/attachment.json size_bytes)" = "$expected_size"
test "$(json_field /tmp/attachment.json sha256)" = "$expected_sha"

curl --fail --silent --show-error --cookie "$owner_cookies" \
  "$base_url/notes/$note_id/attachments" > /tmp/attachments-list.json
python - "$attachment_id" "$expected_sha" <<'PY'
import json, sys
with open('/tmp/attachments-list.json', encoding='utf-8') as handle:
    items = json.load(handle)
assert len(items) == 1
assert items[0]['id'] == sys.argv[1]
assert items[0]['sha256'] == sys.argv[2]
PY

curl --fail --silent --show-error --cookie "$owner_cookies" \
  "$base_url/attachments/$attachment_id" > "$download_file"
cmp "$source_file" "$download_file"

# The preview endpoint rejects generic/active document types rather than rendering them inline.
test "$(status_of --cookie "$owner_cookies" "$base_url/attachments/$attachment_id/preview")" = "415"

# Upload a known tiny PNG and prove owner-scoped inline raster preview behavior.
python - "$image_file" <<'PY'
import base64, sys
# 1x1 transparent PNG.
payload = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLzNwAAAABJRU5ErkJggg=='
)
with open(sys.argv[1], 'wb') as handle:
    handle.write(payload)
PY
image_sha=$(sha256sum "$image_file" | awk '{print $1}')

curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --header 'Content-Type: image/png' \
  --data-binary "@$image_file" \
  "$base_url/notes/$note_id/attachments?filename=preview.png" > /tmp/image-attachment.json
image_attachment_id=$(json_field /tmp/image-attachment.json id)
test "$(json_field /tmp/image-attachment.json media_type)" = "image/png"
test "$(json_field /tmp/image-attachment.json sha256)" = "$image_sha"

curl --fail --silent --show-error --cookie "$owner_cookies" \
  --dump-header "$preview_headers" \
  --output "$preview_file" \
  "$base_url/attachments/$image_attachment_id/preview"
cmp "$image_file" "$preview_file"
grep -i -F 'content-type: image/png' "$preview_headers"
grep -i -F 'cache-control: private, no-store' "$preview_headers"
grep -i -F 'cross-origin-resource-policy: same-origin' "$preview_headers"
grep -i -F 'x-content-type-options: nosniff' "$preview_headers"

# Owner isolation must make another user's note, download, and preview identifiers opaque.
test "$(status_of --cookie "$other_cookies" "$base_url/attachments/$attachment_id")" = "404"
test "$(status_of --cookie "$other_cookies" "$base_url/attachments/$image_attachment_id/preview")" = "404"
test "$(status_of --cookie "$other_cookies" "$base_url/notes/$note_id/attachments")" = "404"
test "$(status_of --cookie "$other_cookies" --header "X-CSRF-Token: $other_csrf" \
  --header 'Content-Type: text/plain' --data-binary "@$source_file" \
  "$base_url/notes/$note_id/attachments?filename=cross-user.txt")" = "404"

# A client filename can never become a path.
test "$(status_of --cookie "$owner_cookies" --header "X-CSRF-Token: $owner_csrf" \
  --header 'Content-Type: text/plain' --data-binary "@$source_file" \
  "$base_url/notes/$note_id/attachments?filename=..%2Fescape.txt")" = "422"

# Mutation requires CSRF and persisted bytes are owned by the non-root API account.
test "$(status_of --cookie "$owner_cookies" --request DELETE "$base_url/attachments/$attachment_id")" = "403"
docker compose exec -T api sh -c \
  'test "$(find /var/lib/goreecloud-notes/attachments -type f -user goreecloud | wc -l)" -ge 2'

test "$(status_of --cookie "$owner_cookies" --header "X-CSRF-Token: $owner_csrf" \
  --request DELETE "$base_url/attachments/$attachment_id")" = "204"
test "$(status_of --cookie "$owner_cookies" --header "X-CSRF-Token: $owner_csrf" \
  --request DELETE "$base_url/attachments/$image_attachment_id")" = "204"
test "$(status_of --cookie "$owner_cookies" "$base_url/attachments/$attachment_id")" = "404"
test "$(status_of --cookie "$owner_cookies" "$base_url/attachments/$image_attachment_id/preview")" = "404"
docker compose exec -T api sh -c \
  'test "$(find /var/lib/goreecloud-notes/attachments -type f | wc -l)" -eq 0'
