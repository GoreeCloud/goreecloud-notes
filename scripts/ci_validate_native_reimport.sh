#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:8000/api/v1"
source_cookies="/tmp/goreecloud-notes-native-reimport-source-cookies.txt"
target_cookies="/tmp/goreecloud-notes-native-reimport-target-cookies.txt"
other_cookies="/tmp/goreecloud-notes-native-reimport-other-cookies.txt"
source_bundle="/tmp/goreecloud-notes-native-roundtrip-source.zip"
target_bundle="/tmp/goreecloud-notes-native-roundtrip-target.zip"
source_image="/tmp/goreecloud-notes-native-roundtrip.png"
password='ci-native-reimport-password-12345'
other_password='ci-native-reimport-other-password-12345'

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
  local username="$1" user_password="$2" cookie_file="$3" output_file="$4"
  curl --fail --silent --show-error \
    --cookie-jar "$cookie_file" \
    --header 'Content-Type: application/json' \
    --data "{\"username\":\"$username\",\"password\":\"$user_password\"}" \
    "$base_url/auth/login" > "$output_file"
}

csrf_from() {
  awk '$6 == "goreecloud_notes_csrf" { print $7 }' "$1"
}

rm -f "$source_cookies" "$target_cookies" "$other_cookies" "$source_image"

docker compose exec -T api rm -f "$source_bundle" "$target_bundle"

printf '%s\n' "$password" | docker compose exec -T api python -m app.cli create-user \
  --username native-roundtrip --display-name 'Native Roundtrip Source' --password-stdin
login_user native-roundtrip "$password" "$source_cookies" /tmp/native-roundtrip-source-login.json
source_csrf=$(csrf_from "$source_cookies")
source_user_id=$(json_field /tmp/native-roundtrip-source-login.json id)
test -n "$source_csrf"

# Build nested organization that must survive the portable boundary exactly.
curl --fail --silent --show-error --cookie "$source_cookies" \
  --header "X-CSRF-Token: $source_csrf" --header 'Content-Type: application/json' \
  --data '{"name":"Recovery Parent"}' "$base_url/notebooks" > /tmp/native-roundtrip-parent.json
parent_id=$(json_field /tmp/native-roundtrip-parent.json id)

curl --fail --silent --show-error --cookie "$source_cookies" \
  --header "X-CSRF-Token: $source_csrf" --header 'Content-Type: application/json' \
  --data "{\"name\":\"Recovery Child\",\"parent_id\":\"$parent_id\"}" \
  "$base_url/notebooks" > /tmp/native-roundtrip-child.json
child_id=$(json_field /tmp/native-roundtrip-child.json id)

curl --fail --silent --show-error --cookie "$source_cookies" \
  --header "X-CSRF-Token: $source_csrf" --header 'Content-Type: application/json' \
  --data '{"name":"Portable Recovery","color":"#336699"}' "$base_url/tags" \
  > /tmp/native-roundtrip-tag.json
tag_id=$(json_field /tmp/native-roundtrip-tag.json id)

# Create the primary note before its attachment so the first rich edit becomes immutable history.
curl --fail --silent --show-error --cookie "$source_cookies" \
  --header "X-CSRF-Token: $source_csrf" --header 'Content-Type: application/json' \
  --data "{\"title\":\"Native Roundtrip Note\",\"notebook_id\":\"$child_id\",\"document\":{\"format\":\"goreecloud.blocks\",\"version\":1,\"blocks\":[{\"type\":\"paragraph\",\"content\":[{\"type\":\"text\",\"text\":\"Before portable edit\"}]}]}}" \
  "$base_url/notes" > /tmp/native-roundtrip-note-v1.json
note_id=$(json_field /tmp/native-roundtrip-note-v1.json id)

test "$(status_of --cookie "$source_cookies" --header "X-CSRF-Token: $source_csrf" \
  --request PUT "$base_url/notes/$note_id/tags/$tag_id")" = "204"

python - "$source_image" <<'PY'
import base64, sys
payload = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLzNwAAAABJRU5ErkJggg=='
)
with open(sys.argv[1], 'wb') as handle:
    handle.write(payload)
PY
expected_attachment_sha=$(sha256sum "$source_image" | awk '{print $1}')
expected_attachment_size=$(wc -c < "$source_image" | tr -d ' ')

curl --fail --silent --show-error --cookie "$source_cookies" \
  --header "X-CSRF-Token: $source_csrf" \
  --header 'Content-Type: image/png' \
  --data-binary "@$source_image" \
  "$base_url/notes/$note_id/attachments?filename=native-roundtrip.png" \
  > /tmp/native-roundtrip-attachment.json
attachment_id=$(json_field /tmp/native-roundtrip-attachment.json id)
test "$(json_field /tmp/native-roundtrip-attachment.json sha256)" = "$expected_attachment_sha"
test "$(json_field /tmp/native-roundtrip-attachment.json size_bytes)" = "$expected_attachment_size"

cat > /tmp/native-roundtrip-v2.json <<EOF
{
  "expected_content_version": 1,
  "title": "Native Roundtrip Note — Rich",
  "document": {
    "format": "goreecloud.blocks",
    "version": 1,
    "blocks": [
      {"type":"heading","level":2,"content":[{"type":"text","text":"Portable recovery heading","marks":[{"type":"bold"}]}]},
      {"type":"paragraph","content":[{"type":"text","text":"This content must remain searchable after native re-import."}]},
      {"type":"attachmentImage","attachment_id":"$attachment_id","alt":"Native roundtrip image"}
    ]
  },
  "is_pinned": true,
  "color": "#123456"
}
EOF
curl --fail --silent --show-error --cookie "$source_cookies" \
  --header "X-CSRF-Token: $source_csrf" --header 'Content-Type: application/json' --request PATCH \
  --data-binary @/tmp/native-roundtrip-v2.json "$base_url/notes/$note_id" \
  > /tmp/native-roundtrip-note-v2.json
test "$(json_field /tmp/native-roundtrip-note-v2.json content_version)" = "2"

# Archive the primary note without changing its content version.
curl --fail --silent --show-error --cookie "$source_cookies" \
  --header "X-CSRF-Token: $source_csrf" --header 'Content-Type: application/json' --request PATCH \
  --data '{"state":"archived"}' "$base_url/notes/$note_id" > /tmp/native-roundtrip-note-archived.json
grep -F '"state":"archived"' /tmp/native-roundtrip-note-archived.json
test "$(json_field /tmp/native-roundtrip-note-archived.json content_version)" = "2"

# A separate trashed note proves lifecycle state is not flattened during the round trip.
curl --fail --silent --show-error --cookie "$source_cookies" \
  --header "X-CSRF-Token: $source_csrf" --header 'Content-Type: application/json' \
  --data '{"title":"Native Roundtrip Trash","document":{"format":"goreecloud.blocks","version":1,"blocks":[{"type":"paragraph","content":[{"type":"text","text":"Recoverable trash state"}]}]}}' \
  "$base_url/notes" > /tmp/native-roundtrip-trash.json
trash_note_id=$(json_field /tmp/native-roundtrip-trash.json id)
test "$(status_of --cookie "$source_cookies" --header "X-CSRF-Token: $source_csrf" \
  --request DELETE "$base_url/notes/$trash_note_id")" = "204"

curl --fail --silent --show-error --cookie "$source_cookies" "$base_url/notes/$note_id/revisions" \
  > /tmp/native-roundtrip-revisions-source.json
python - <<'PY'
import json
with open('/tmp/native-roundtrip-revisions-source.json', encoding='utf-8') as handle:
    revisions = json.load(handle)
assert len(revisions) == 1
assert revisions[0]['revision_number'] == 1
assert revisions[0]['content_version'] == 1
assert revisions[0]['title'] == 'Native Roundtrip Note'
PY

# Create and independently verify the source artifact.
docker compose exec -T api python -m app.cli export-library \
  --username native-roundtrip --output "$source_bundle"
docker compose exec -T api python -m app.cli verify-library-export --input "$source_bundle"
source_bundle_sha=$(docker compose exec -T api sha256sum "$source_bundle" | awk '{print $1}')

# Re-import must require explicit empty-target confirmation.
set +e
docker compose exec -T api python -m app.cli import-library \
  --username native-roundtrip --input "$source_bundle" >/tmp/native-roundtrip-no-confirm.out 2>&1
no_confirm_status=$?
set -e
test "$no_confirm_status" = "2"
grep -F -- '--confirm-empty-target' /tmp/native-roundtrip-no-confirm.out

# Delete only the disposable source account/database rows and its owner-scoped attachment
# directory. The ZIP remains in /tmp, proving the import reconstructs bytes from the portable
# artifact rather than accidentally reusing source storage.
docker compose exec -T api python - "$source_user_id" <<'PY'
import shutil
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import User

user_id = UUID(sys.argv[1])
with SessionLocal() as db:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise SystemExit('disposable native roundtrip source user not found')
    db.delete(user)
    db.commit()

root = Path(get_settings().attachment_root).expanduser().resolve()
owner_path = (root / str(user_id)).resolve()
owner_path.relative_to(root)
shutil.rmtree(owner_path, ignore_errors=True)
PY

# Recreate only the account credential/identity. Portable user knowledge must come from ZIP.
printf '%s\n' "$password" | docker compose exec -T api python -m app.cli create-user \
  --username native-roundtrip --display-name 'Native Roundtrip Restored' --password-stdin

# Target account is empty before the explicit import.
login_user native-roundtrip "$password" "$target_cookies" /tmp/native-roundtrip-target-before.json
target_user_id=$(json_field /tmp/native-roundtrip-target-before.json id)
test "$target_user_id" != "$source_user_id"
curl --fail --silent --show-error --cookie "$target_cookies" "$base_url/notes?state=normal" \
  > /tmp/native-roundtrip-target-empty.json
python - <<'PY'
import json
with open('/tmp/native-roundtrip-target-empty.json', encoding='utf-8') as handle:
    assert json.load(handle) == []
PY

# Logout the newly created empty account before administrative reconstruction. Import does not
# rely on browser credentials and the target workspace remains quiescent during restoration.
target_csrf_before=$(csrf_from "$target_cookies")
test "$(status_of --cookie "$target_cookies" --header "X-CSRF-Token: $target_csrf_before" \
  --request POST "$base_url/auth/logout")" = "204"
rm -f "$target_cookies"

docker compose exec -T api python -m app.cli import-library \
  --username native-roundtrip --input "$source_bundle" --confirm-empty-target --json \
  > /tmp/native-roundtrip-import-result.json

python - "$source_bundle_sha" "$source_user_id" "$target_user_id" <<'PY'
import json, sys
with open('/tmp/native-roundtrip-import-result.json', encoding='utf-8') as handle:
    result = json.load(handle)
assert result['format'] == 'goreecloud-notes-native-import-result'
assert result['schemaVersion'] == 1
assert result['source']['bundleSha256'] == sys.argv[1]
assert result['source']['accountId'] == sys.argv[2]
assert result['target']['accountId'] == sys.argv[3]
assert result['counts'] == {
    'notebooks': 2,
    'notes': 2,
    'tags': 1,
    'noteTagRelationships': 1,
    'attachments': 1,
    'revisions': 1,
    'migrationImports': 0,
    'migrationNoteRecords': 0,
}
assert result['identity']['nativeObjectUuidsPreserved'] is True
assert result['identity']['targetAccountCredentialImported'] is False
assert result['validation']['bundleVerifiedBeforeMutation'] is True
assert result['validation']['attachmentBytesRehashedWhileStaging'] is True
assert result['validation']['targetWasEmptyAtCommitBoundary'] is True
assert result['validation']['uuidCollisionsRefused'] is True
PY

# The imported account authenticates only through the separately created target credential.
login_user native-roundtrip "$password" "$target_cookies" /tmp/native-roundtrip-target-login.json
target_csrf=$(csrf_from "$target_cookies")
test -n "$target_csrf"

curl --fail --silent --show-error --cookie "$target_cookies" "$base_url/notebooks" \
  > /tmp/native-roundtrip-notebooks-target.json
python - "$parent_id" "$child_id" <<'PY'
import json, sys
with open('/tmp/native-roundtrip-notebooks-target.json', encoding='utf-8') as handle:
    notebooks = {item['id']: item for item in json.load(handle)}
assert set(notebooks) == {sys.argv[1], sys.argv[2]}
assert notebooks[sys.argv[2]]['parent_id'] == sys.argv[1]
assert notebooks[sys.argv[1]]['name'] == 'Recovery Parent'
assert notebooks[sys.argv[2]]['name'] == 'Recovery Child'
PY

curl --fail --silent --show-error --cookie "$target_cookies" "$base_url/notes/$note_id" \
  > /tmp/native-roundtrip-note-target.json
python - "$attachment_id" "$child_id" <<'PY'
import json, sys
with open('/tmp/native-roundtrip-note-target.json', encoding='utf-8') as handle:
    note = json.load(handle)
assert note['id']
assert note['notebook_id'] == sys.argv[2]
assert note['title'] == 'Native Roundtrip Note — Rich'
assert note['content_version'] == 2
assert note['state'] == 'archived'
assert note['is_pinned'] is True
assert note['color'] == '#123456'
assert note['document']['blocks'][2]['attachment_id'] == sys.argv[1]
assert note['document']['blocks'][1]['content'][0]['text'] == 'This content must remain searchable after native re-import.'
PY

curl --fail --silent --show-error --cookie "$target_cookies" "$base_url/notes/$trash_note_id" \
  > /tmp/native-roundtrip-trash-target.json
grep -F '"state":"trashed"' /tmp/native-roundtrip-trash-target.json

curl --fail --silent --show-error --cookie "$target_cookies" "$base_url/notes/$note_id/tags" \
  > /tmp/native-roundtrip-tags-target.json
python - "$tag_id" <<'PY'
import json, sys
with open('/tmp/native-roundtrip-tags-target.json', encoding='utf-8') as handle:
    tags = json.load(handle)
assert len(tags) == 1
assert tags[0]['id'] == sys.argv[1]
assert tags[0]['name'] == 'Portable Recovery'
assert tags[0]['color'] == '#336699'
PY

curl --fail --silent --show-error --cookie "$target_cookies" "$base_url/notes/$note_id/revisions" \
  > /tmp/native-roundtrip-revisions-target.json
python - <<'PY'
import json
with open('/tmp/native-roundtrip-revisions-target.json', encoding='utf-8') as handle:
    revisions = json.load(handle)
assert len(revisions) == 1
assert revisions[0]['revision_number'] == 1
assert revisions[0]['content_version'] == 1
assert revisions[0]['title'] == 'Native Roundtrip Note'
assert revisions[0]['document']['blocks'][0]['content'][0]['text'] == 'Before portable edit'
PY

curl --fail --silent --show-error --cookie "$target_cookies" "$base_url/notes/$note_id/attachments" \
  > /tmp/native-roundtrip-attachments-target.json
python - "$attachment_id" "$expected_attachment_sha" "$expected_attachment_size" <<'PY'
import json, sys
with open('/tmp/native-roundtrip-attachments-target.json', encoding='utf-8') as handle:
    attachments = json.load(handle)
assert len(attachments) == 1
item = attachments[0]
assert item['id'] == sys.argv[1]
assert item['filename'] == 'native-roundtrip.png'
assert item['media_type'] == 'image/png'
assert item['sha256'] == sys.argv[2]
assert item['size_bytes'] == int(sys.argv[3])
PY

curl --fail --silent --show-error --cookie "$target_cookies" \
  "$base_url/attachments/$attachment_id" > /tmp/native-roundtrip-restored-image.png
test "$(sha256sum /tmp/native-roundtrip-restored-image.png | awk '{print $1}')" = "$expected_attachment_sha"
test "$(wc -c < /tmp/native-roundtrip-restored-image.png | tr -d ' ')" = "$expected_attachment_size"

# Reconstructed notes must be searchable through the generated PostgreSQL search vector.
curl --fail --silent --show-error --cookie "$target_cookies" \
  "$base_url/search/notes?q=searchable&state=archived" > /tmp/native-roundtrip-search-target.json
python - "$note_id" <<'PY'
import json, sys
with open('/tmp/native-roundtrip-search-target.json', encoding='utf-8') as handle:
    notes = json.load(handle)
assert [item['id'] for item in notes] == [sys.argv[1]]
PY

# Imported IDs remain private to the selected target owner.
printf '%s\n' "$other_password" | docker compose exec -T api python -m app.cli create-user \
  --username native-roundtrip-other --display-name 'Native Roundtrip Other' --password-stdin
login_user native-roundtrip-other "$other_password" "$other_cookies" /tmp/native-roundtrip-other-login.json
test "$(status_of --cookie "$other_cookies" "$base_url/notes/$note_id")" = "404"
test "$(status_of --cookie "$other_cookies" "$base_url/attachments/$attachment_id")" = "404"

# A second import is a merge attempt and must fail closed without changing the populated target.
set +e
docker compose exec -T api python -m app.cli import-library \
  --username native-roundtrip --input "$source_bundle" --confirm-empty-target \
  >/tmp/native-roundtrip-second-import.out 2>&1
second_import_status=$?
set -e
test "$second_import_status" = "2"
grep -F 'Target account is not empty' /tmp/native-roundtrip-second-import.out

# Re-export the reconstructed target and prove every user-knowledge collection is exactly
# equivalent to the source artifact. Account identity/export timestamps are intentionally not
# compared because credentials and target account identity are not imported from the bundle.
docker compose exec -T api python -m app.cli export-library \
  --username native-roundtrip --output "$target_bundle"
docker compose exec -T api python -m app.cli verify-library-export --input "$target_bundle"

docker compose exec -T api python - "$source_bundle" "$target_bundle" <<'PY'
import json
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1]) as source_zip, zipfile.ZipFile(sys.argv[2]) as target_zip:
    source = json.loads(source_zip.read('library.json'))
    target = json.loads(target_zip.read('library.json'))

    for collection in (
        'notebooks',
        'notes',
        'tags',
        'noteTags',
        'attachments',
        'revisions',
        'migrationImports',
        'migrationNoteRecords',
    ):
        assert source.get(collection, []) == target.get(collection, []), collection

    assert source['summary'] == target['summary']
    assert source['source'] == target['source']
    assert source['account']['id'] != target['account']['id']
    assert source['account']['username'] == target['account']['username'] == 'native-roundtrip'

    source_attachment = source['attachments'][0]
    target_attachment = target['attachments'][0]
    assert source_attachment['archivePath'] == target_attachment['archivePath']
    assert source_zip.read(source_attachment['archivePath']) == target_zip.read(target_attachment['archivePath'])
PY

rm -f "$source_cookies" "$target_cookies" "$other_cookies" "$source_image"
