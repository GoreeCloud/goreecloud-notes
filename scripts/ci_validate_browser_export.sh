#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:8000/api/v1"
cookies="/tmp/goreecloud-notes-browser-export-cookies.txt"
headers="/tmp/goreecloud-notes-browser-export-headers.txt"
archive="/tmp/goreecloud-notes-browser-export.zip"
source_file="/tmp/goreecloud-notes-browser-export.png"
password='ci-browser-export-password-12345'

json_field() {
  python - "$1" "$2" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)[sys.argv[2]])
PY
}

rm -f "$cookies" "$headers" "$archive" "$source_file"

printf '%s\n' "$password" | docker compose exec -T api python -m app.cli create-user \
  --username browser-export-user \
  --display-name 'Browser Export User' \
  --password-stdin

# The export route is private even before CSRF validation is considered.
test "$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  --request POST \
  "$base_url/exports/library")" = "401"

curl --fail --silent --show-error \
  --cookie-jar "$cookies" \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"browser-export-user\",\"password\":\"$password\"}" \
  "$base_url/auth/login" > /tmp/goreecloud-notes-browser-export-login.json
csrf=$(awk '$6 == "goreecloud_notes_csrf" { print $7 }' "$cookies")
test -n "$csrf"

# An authenticated browser cannot generate an export without the double-submit CSRF proof.
test "$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  --cookie "$cookies" \
  --request POST \
  "$base_url/exports/library")" = "403"

curl --fail --silent --show-error --cookie "$cookies" \
  --header "X-CSRF-Token: $csrf" --header 'Content-Type: application/json' \
  --data '{"title":"Browser export source","document":{"format":"goreecloud.blocks","version":1,"blocks":[{"type":"paragraph","content":[{"type":"text","text":"Browser-delivered portable export"}]}]}}' \
  "$base_url/notes" > /tmp/goreecloud-notes-browser-export-note.json
note_id=$(json_field /tmp/goreecloud-notes-browser-export-note.json id)

python - "$source_file" <<'PY'
import base64, sys
payload = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLzNwAAAABJRU5ErkJggg=='
)
with open(sys.argv[1], 'wb') as handle:
    handle.write(payload)
PY
expected_sha=$(sha256sum "$source_file" | awk '{print $1}')
expected_size=$(wc -c < "$source_file" | tr -d ' ')

curl --fail --silent --show-error --cookie "$cookies" \
  --header "X-CSRF-Token: $csrf" \
  --header 'Content-Type: image/png' \
  --data-binary "@$source_file" \
  "$base_url/notes/$note_id/attachments?filename=browser-export.png" \
  > /tmp/goreecloud-notes-browser-export-attachment.json
attachment_id=$(json_field /tmp/goreecloud-notes-browser-export-attachment.json id)
test "$(json_field /tmp/goreecloud-notes-browser-export-attachment.json sha256)" = "$expected_sha"
test "$(json_field /tmp/goreecloud-notes-browser-export-attachment.json size_bytes)" = "$expected_size"

curl --fail --silent --show-error \
  --cookie "$cookies" \
  --request POST \
  --header "X-CSRF-Token: $csrf" \
  --dump-header "$headers" \
  --output "$archive" \
  "$base_url/exports/library"

grep -i '^content-type: application/zip' "$headers"
grep -i '^cache-control: no-store, max-age=0' "$headers"
grep -i '^pragma: no-cache' "$headers"
grep -i '^x-content-type-options: nosniff' "$headers"
grep -i '^content-disposition: attachment;' "$headers"

archive_sha=$(sha256sum "$archive" | awk '{print $1}')
header_sha=$(awk 'BEGIN{IGNORECASE=1} /^X-GoreeCloud-Export-SHA256:/ {gsub("\r", "", $2); print $2}' "$headers")
test -n "$header_sha"
test "$archive_sha" = "$header_sha"

EXPECTED_NOTE_ID="$note_id" \
EXPECTED_ATTACHMENT_ID="$attachment_id" \
EXPECTED_ATTACHMENT_SHA="$expected_sha" \
EXPECTED_ATTACHMENT_SIZE="$expected_size" \
python - "$archive" <<'PY'
import hashlib
import json
import os
import sys
import zipfile

path = sys.argv[1]
with zipfile.ZipFile(path) as bundle:
    library_raw = bundle.read('library.json')
    library = json.loads(library_raw)
    metadata = json.loads(bundle.read('bundle.json'))

    assert library['format'] == 'goreecloud-notes-native-export'
    assert library['schemaVersion'] == 1
    assert library['source']['sourceMutationPerformed'] is False
    assert library['account']['username'] == 'browser-export-user'
    assert library['summary']['notes'] == 1
    assert library['summary']['attachments'] == 1
    assert library['summary']['migrationImports'] == 0
    assert library['summary']['migrationNoteRecords'] == 0

    note = library['notes'][0]
    assert note['id'] == os.environ['EXPECTED_NOTE_ID']
    assert note['title'] == 'Browser export source'
    assert note['document']['blocks'][0]['content'][0]['text'] == 'Browser-delivered portable export'

    attachment = library['attachments'][0]
    assert attachment['id'] == os.environ['EXPECTED_ATTACHMENT_ID']
    assert attachment['sha256'] == os.environ['EXPECTED_ATTACHMENT_SHA']
    assert attachment['sizeBytes'] == int(os.environ['EXPECTED_ATTACHMENT_SIZE'])
    payload = bundle.read(attachment['archivePath'])
    assert hashlib.sha256(payload).hexdigest() == os.environ['EXPECTED_ATTACHMENT_SHA']
    assert len(payload) == int(os.environ['EXPECTED_ATTACHMENT_SIZE'])

    assert metadata['library']['sha256'] == hashlib.sha256(library_raw).hexdigest()
    assert metadata['attachments'][0]['sha256'] == os.environ['EXPECTED_ATTACHMENT_SHA']

    serialized = json.dumps(library, sort_keys=True)
    for forbidden in (
        'password_hash',
        'csrf_token_hash',
        'token_hash',
        'storage_key',
        'login_rate',
    ):
        assert forbidden not in serialized
PY

# FileResponse cleanup must leave no generated browser-export directory behind.
sleep 1
if docker compose exec -T api sh -c 'find /tmp -maxdepth 1 -type d -name "goreecloud-notes-export-*" -print -quit' | grep -q .; then
  echo 'Browser export left a temporary server-side export directory behind.' >&2
  exit 1
fi

rm -f "$cookies" "$headers" "$archive" "$source_file"
