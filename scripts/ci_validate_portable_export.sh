#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:8000/api/v1"
cookies="/tmp/goreecloud-notes-portable-export-cookies.txt"
password='ci-portable-export-password-12345'
source_file="/tmp/goreecloud-notes-portable-export.png"
container_export="/tmp/goreecloud-notes-portable-export.zip"

json_field() {
  python - "$1" "$2" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)[sys.argv[2]])
PY
}

rm -f "$cookies" "$source_file"

printf '%s\n' "$password" | docker compose exec -T api python -m app.cli create-user \
  --username portable-export-user \
  --display-name 'Portable Export User' \
  --password-stdin

curl --fail --silent --show-error \
  --cookie-jar "$cookies" \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"portable-export-user\",\"password\":\"$password\"}" \
  "$base_url/auth/login" > /tmp/goreecloud-notes-portable-export-login.json
csrf=$(awk '$6 == "goreecloud_notes_csrf" { print $7 }' "$cookies")
test -n "$csrf"

curl --fail --silent --show-error --cookie "$cookies" \
  --header "X-CSRF-Token: $csrf" --header 'Content-Type: application/json' \
  --data '{"name":"Portable Export Notebook"}' \
  "$base_url/notebooks" > /tmp/goreecloud-notes-portable-export-notebook.json
notebook_id=$(json_field /tmp/goreecloud-notes-portable-export-notebook.json id)

curl --fail --silent --show-error --cookie "$cookies" \
  --header "X-CSRF-Token: $csrf" --header 'Content-Type: application/json' \
  --data '{"name":"Portable Export","color":"#4263eb"}' \
  "$base_url/tags" > /tmp/goreecloud-notes-portable-export-tag.json
tag_id=$(json_field /tmp/goreecloud-notes-portable-export-tag.json id)

curl --fail --silent --show-error --cookie "$cookies" \
  --header "X-CSRF-Token: $csrf" --header 'Content-Type: application/json' \
  --data "{\"title\":\"Portable export source\",\"notebook_id\":\"$notebook_id\",\"document\":{\"format\":\"goreecloud.blocks\",\"version\":1,\"blocks\":[{\"type\":\"paragraph\",\"content\":[{\"type\":\"text\",\"text\":\"Before portable export edit\"}]}]}}" \
  "$base_url/notes" > /tmp/goreecloud-notes-portable-export-note.json
note_id=$(json_field /tmp/goreecloud-notes-portable-export-note.json id)

test "$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  --cookie "$cookies" --header "X-CSRF-Token: $csrf" --request PUT \
  "$base_url/notes/$note_id/tags/$tag_id")" = "204"

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
  "$base_url/notes/$note_id/attachments?filename=portable-export.png" \
  > /tmp/goreecloud-notes-portable-export-attachment.json
attachment_id=$(json_field /tmp/goreecloud-notes-portable-export-attachment.json id)
test "$(json_field /tmp/goreecloud-notes-portable-export-attachment.json sha256)" = "$expected_sha"
test "$(json_field /tmp/goreecloud-notes-portable-export-attachment.json size_bytes)" = "$expected_size"

python - "$attachment_id" <<'PY' > /tmp/goreecloud-notes-portable-export-patch.json
import json, sys
json.dump(
    {
        'expected_content_version': 1,
        'title': 'Portable export validated note',
        'document': {
            'format': 'goreecloud.blocks',
            'version': 1,
            'blocks': [
                {
                    'type': 'paragraph',
                    'content': [{'type': 'text', 'text': 'Portable export body'}],
                },
                {
                    'type': 'attachmentImage',
                    'attachment_id': sys.argv[1],
                    'alt': 'Portable export image',
                },
            ],
        },
        'is_pinned': True,
        'color': '#f4b400',
    },
    sys.stdout,
)
PY

curl --fail --silent --show-error --cookie "$cookies" \
  --request PATCH \
  --header "X-CSRF-Token: $csrf" \
  --header 'Content-Type: application/json' \
  --data-binary @/tmp/goreecloud-notes-portable-export-patch.json \
  "$base_url/notes/$note_id" > /tmp/goreecloud-notes-portable-export-updated.json
test "$(json_field /tmp/goreecloud-notes-portable-export-updated.json content_version)" = "2"

# Build and independently verify a full-library bundle inside the API container.
docker compose exec -T api rm -f "$container_export"
docker compose exec -T api python -m app.cli export-library \
  --username ' PORTABLE-EXPORT-USER ' \
  --output "$container_export" \
  > /tmp/goreecloud-notes-portable-export-cli.txt
grep -F 'Notes: 1' /tmp/goreecloud-notes-portable-export-cli.txt
grep -F 'Attachments: 1' /tmp/goreecloud-notes-portable-export-cli.txt

docker compose exec -T api python -m app.cli verify-library-export \
  --input "$container_export" \
  > /tmp/goreecloud-notes-portable-export-verify.txt
grep -F 'Notes: 1' /tmp/goreecloud-notes-portable-export-verify.txt
grep -F 'Attachments: 1' /tmp/goreecloud-notes-portable-export-verify.txt

# Existing destinations are protected unless overwrite is explicitly approved.
if docker compose exec -T api python -m app.cli export-library \
  --username portable-export-user \
  --output "$container_export" \
  > /tmp/goreecloud-notes-portable-export-refusal.txt 2>&1; then
  echo 'Portable export unexpectedly overwrote an existing destination without approval.' >&2
  exit 1
fi
grep -F 'already exists' /tmp/goreecloud-notes-portable-export-refusal.txt

# Inspect the portable schema and prove the actual exported attachment bytes are intact.
docker compose exec -T \
  -e EXPECTED_NOTE_ID="$note_id" \
  -e EXPECTED_NOTEBOOK_ID="$notebook_id" \
  -e EXPECTED_TAG_ID="$tag_id" \
  -e EXPECTED_ATTACHMENT_ID="$attachment_id" \
  -e EXPECTED_ATTACHMENT_SHA="$expected_sha" \
  -e EXPECTED_ATTACHMENT_SIZE="$expected_size" \
  api python - <<'PY'
import hashlib
import json
import os
import zipfile

path = '/tmp/goreecloud-notes-portable-export.zip'
with zipfile.ZipFile(path) as archive:
    library_raw = archive.read('library.json')
    library = json.loads(library_raw)
    bundle = json.loads(archive.read('bundle.json'))

    assert library['format'] == 'goreecloud-notes-native-export'
    assert library['schemaVersion'] == 1
    assert library['source']['sourceMutationPerformed'] is False
    assert library['account']['username'] == 'portable-export-user'
    assert library['summary'] == {
        'attachments': 1,
        'noteTagRelationships': 1,
        'notebooks': 1,
        'notes': 1,
        'revisions': 1,
        'tags': 1,
    }

    note = library['notes'][0]
    assert note['id'] == os.environ['EXPECTED_NOTE_ID']
    assert note['notebookId'] == os.environ['EXPECTED_NOTEBOOK_ID']
    assert note['title'] == 'Portable export validated note'
    assert note['contentVersion'] == 2
    assert note['isPinned'] is True
    assert note['color'] == '#f4b400'
    assert note['document']['blocks'][1]['attachment_id'] == os.environ['EXPECTED_ATTACHMENT_ID']

    relationship = library['noteTags'][0]
    assert relationship['noteId'] == os.environ['EXPECTED_NOTE_ID']
    assert relationship['tagId'] == os.environ['EXPECTED_TAG_ID']
    assert library['revisions'][0]['title'] == 'Portable export source'

    attachment = library['attachments'][0]
    assert attachment['id'] == os.environ['EXPECTED_ATTACHMENT_ID']
    assert attachment['sha256'] == os.environ['EXPECTED_ATTACHMENT_SHA']
    assert attachment['sizeBytes'] == int(os.environ['EXPECTED_ATTACHMENT_SIZE'])
    payload = archive.read(attachment['archivePath'])
    assert hashlib.sha256(payload).hexdigest() == os.environ['EXPECTED_ATTACHMENT_SHA']
    assert len(payload) == int(os.environ['EXPECTED_ATTACHMENT_SIZE'])

    assert bundle['library']['sha256'] == hashlib.sha256(library_raw).hexdigest()
    assert bundle['attachments'][0]['sha256'] == os.environ['EXPECTED_ATTACHMENT_SHA']

    serialized = json.dumps(library, sort_keys=True)
    assert 'storage_key' not in serialized
    assert 'password_hash' not in serialized
    assert 'auth_sessions' not in serialized
    assert 'login_rate' not in serialized
PY

# Explicit overwrite must still produce another independently verifiable bundle.
docker compose exec -T api python -m app.cli export-library \
  --username portable-export-user \
  --output "$container_export" \
  --overwrite \
  > /tmp/goreecloud-notes-portable-export-overwrite.txt
docker compose exec -T api python -m app.cli verify-library-export \
  --input "$container_export" \
  > /tmp/goreecloud-notes-portable-export-overwrite-verify.txt

docker compose exec -T api rm -f "$container_export"
