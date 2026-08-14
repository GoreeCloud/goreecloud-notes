#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:8000/api/v1"
target_cookies="/tmp/goreecloud-notes-memos-import-target-cookies.txt"
isolation_cookies="/tmp/goreecloud-notes-memos-import-isolation-cookies.txt"
target_password='ci-memos-import-target-password-12345'
isolation_password='ci-memos-import-isolation-password-12345'
host_manifest="/tmp/goreecloud-notes-memos-import-manifest.json"
host_evidence="/tmp/goreecloud-notes-memos-import-evidence.json"
host_map="/tmp/goreecloud-notes-memos-import-map.json"
host_result="/tmp/goreecloud-notes-memos-import-result.json"
host_verify="/tmp/goreecloud-notes-memos-import-verify.json"
container_source="/tmp/goreecloud-notes-memos-import-source.json"
container_manifest="/tmp/goreecloud-notes-memos-import-manifest.json"
container_evidence="/tmp/goreecloud-notes-memos-import-evidence.json"
container_map="/tmp/goreecloud-notes-memos-import-map.json"
container_evidence_root="/tmp/goreecloud-notes-memos-import-evidence-root"

rm -f "$target_cookies" "$isolation_cookies" "$host_manifest" "$host_evidence" "$host_map" "$host_result" "$host_verify"

# The migration source is the repository's synthetic schema-v1 fixture. No live Memos
# service, database, API, or attachment directory is contacted by this gate.
docker compose cp backend/tests/fixtures/memos_export_v1.json "api:$container_source"
docker compose exec -T api python -m app.migration build-memos-manifest "$container_source" > "$host_manifest"

cat > "$host_map" <<'EOF'
{
  "format": "goreecloud-notes-attachment-map",
  "schemaVersion": 1,
  "attachments": [
    {"sourceName": "attachments/200", "relativePath": "fixture.png"}
  ]
}
EOF

docker compose cp "$host_manifest" "api:$container_manifest"
docker compose cp "$host_map" "api:$container_map"
docker compose exec -T api rm -rf "$container_evidence_root"
docker compose exec -T api mkdir -p "$container_evidence_root"
docker compose exec -T api python - "$container_evidence_root/fixture.png" <<'PY'
import base64
import sys
from pathlib import Path

Path(sys.argv[1]).write_bytes(
    base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z8XcAAAAASUVORK5CYII='
    )
)
PY

docker compose exec -T api python -m app.migration verify-attachment-binaries \
  "$container_manifest" "$container_map" "$container_evidence_root" > "$host_evidence"
docker compose cp "$host_evidence" "api:$container_evidence"

python - "$host_evidence" <<'PY'
import json
import sys

with open(sys.argv[1], encoding='utf-8') as handle:
    evidence = json.load(handle)
assert evidence['verification']['complete'] is True
assert evidence['verification']['sourceMutationPerformed'] is False
assert evidence['verification']['targetMutationPerformed'] is False
assert evidence['attachments'][0]['sourceName'] == 'attachments/200'
assert evidence['attachments'][0]['verifiedSizeBytes'] == 68
assert evidence['attachments'][0]['sha256'] == '489b326e81d3ef516100495b2b2ea91199dafa1f57b7e78bcebddda1bbe36e13'
PY

printf '%s\n' "$target_password" | docker compose exec -T api python -m app.cli create-user \
  --username memos-import-target \
  --display-name 'Memos Import Target' \
  --password-stdin

# The target-writing command must require an explicit confirmation flag.
if docker compose exec -T api python -m app.migration import-memos-manifest \
  "$container_manifest" "$container_evidence" "$container_evidence_root" \
  --username memos-import-target > /tmp/goreecloud-notes-memos-import-no-confirm.txt 2>&1; then
  echo 'Memos importer unexpectedly wrote without --confirm-empty-target.' >&2
  exit 1
fi
grep -F -- '--confirm-empty-target is required' /tmp/goreecloud-notes-memos-import-no-confirm.txt

# Perform the explicit write into the empty synthetic target account.
docker compose exec -T api python -m app.migration import-memos-manifest \
  "$container_manifest" "$container_evidence" "$container_evidence_root" \
  --username ' MEMOS-IMPORT-TARGET ' \
  --confirm-empty-target > "$host_result"

import_id=$(python - "$host_result" <<'PY'
import json
import sys
with open(sys.argv[1], encoding='utf-8') as handle:
    result = json.load(handle)
assert result['format'] == 'goreecloud-notes-memos-import-result'
assert result['schemaVersion'] == 1
assert result['counts'] == {
    'attachments': 1,
    'notes': 2,
    'provenanceRecords': 2,
    'tags': 2,
}
assert result['equivalence']['sourceRecordsPreserved'] is True
assert result['equivalence']['attachmentBytesVerifiedAndCopied'] is True
assert result['equivalence']['sourceMutationPerformed'] is False
assert result['equivalence']['targetMutationPerformed'] is True
assert result['equivalence']['nativeSemanticEquivalenceComplete'] is False
assert result['equivalence']['deferred'] == {
    'locations': 1,
    'markdownRichFormatting': 2,
    'relations': 1,
    'trashRestoreTargets': 1,
    'unmappedNamedColors': 1,
}
print(result['import']['id'])
PY
)
test -n "$import_id"

# Re-verify the committed native target independently from the source/evidence inputs.
docker compose exec -T api python -m app.migration verify-memos-import \
  --username memos-import-target \
  --import-id "$import_id" > "$host_verify"
python - "$host_verify" "$import_id" <<'PY'
import json
import sys
with open(sys.argv[1], encoding='utf-8') as handle:
    report = json.load(handle)
assert report['format'] == 'goreecloud-notes-memos-import-verification'
assert report['import']['id'] == sys.argv[2]
assert report['verification'] == {
    'attachmentByteIntegrityValid': True,
    'databaseProvenanceValid': True,
    'nativeNoteProjectionValid': True,
    'notes': 2,
    'sourceMutationPerformed': False,
    'tagAssignmentsValid': True,
    'tags': 2,
    'targetVerificationMutationPerformed': False,
    'attachments': 1,
}
assert report['equivalence']['sourceRecordsPreserved'] is True
assert report['equivalence']['nativeSemanticEquivalenceComplete'] is False
PY

# A second import into the same account must be refused rather than merge or duplicate data.
if docker compose exec -T api python -m app.migration import-memos-manifest \
  "$container_manifest" "$container_evidence" "$container_evidence_root" \
  --username memos-import-target \
  --confirm-empty-target > /tmp/goreecloud-notes-memos-import-duplicate.txt 2>&1; then
  echo 'Memos importer unexpectedly allowed a second import into a non-empty account.' >&2
  exit 1
fi
grep -F 'Target account is not empty' /tmp/goreecloud-notes-memos-import-duplicate.txt

# Validate the imported data through the same authenticated API a browser uses.
curl --fail --silent --show-error \
  --cookie-jar "$target_cookies" \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"memos-import-target\",\"password\":\"$target_password\"}" \
  "$base_url/auth/login" > /tmp/goreecloud-notes-memos-import-login.json

curl --fail --silent --show-error --cookie "$target_cookies" \
  "$base_url/notes?state=normal" > /tmp/goreecloud-notes-memos-import-normal.json
curl --fail --silent --show-error --cookie "$target_cookies" \
  "$base_url/notes?state=trashed" > /tmp/goreecloud-notes-memos-import-trashed.json
curl --fail --silent --show-error --cookie "$target_cookies" \
  "$base_url/tags" > /tmp/goreecloud-notes-memos-import-tags.json

normal_note_id=$(python - <<'PY'
import json

normal = json.load(open('/tmp/goreecloud-notes-memos-import-normal.json'))
trashed = json.load(open('/tmp/goreecloud-notes-memos-import-trashed.json'))
tags = json.load(open('/tmp/goreecloud-notes-memos-import-tags.json'))
assert len(normal) == 1
assert len(trashed) == 1
assert normal[0]['title'] == 'Migration fixture'
assert normal[0]['is_pinned'] is True
# Memos named color "blue" is preserved in provenance but deliberately not guessed
# into the native six-digit-hex color model.
assert normal[0]['color'] is None
assert normal[0]['content_version'] == 1
assert normal[0]['document'] == {
    'format': 'goreecloud.blocks',
    'version': 1,
    'blocks': [
        {'type': 'paragraph', 'content': [{'type': 'text', 'text': '# Migration fixture'}]},
        {'type': 'paragraph', 'content': []},
        {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Native migration inventory.'}]},
    ],
}
assert trashed[0]['title'] == ''
assert trashed[0]['state'] == 'trashed'
assert {item['normalized_name'] for item in tags} == {'goreecloud', 'migration'}
print(normal[0]['id'])
PY
)

curl --fail --silent --show-error --cookie "$target_cookies" \
  "$base_url/notes/$normal_note_id/tags" > /tmp/goreecloud-notes-memos-import-note-tags.json
python - <<'PY'
import json
assigned = json.load(open('/tmp/goreecloud-notes-memos-import-note-tags.json'))
assert {item['normalized_name'] for item in assigned} == {'goreecloud', 'migration'}
PY

curl --fail --silent --show-error --cookie "$target_cookies" \
  "$base_url/notes/$normal_note_id/attachments" > /tmp/goreecloud-notes-memos-import-attachments.json
attachment_id=$(python - <<'PY'
import json
attachments = json.load(open('/tmp/goreecloud-notes-memos-import-attachments.json'))
assert len(attachments) == 1
item = attachments[0]
assert item['filename'] == 'fixture.png'
assert item['media_type'] == 'image/png'
assert item['size_bytes'] == 68
assert item['sha256'] == '489b326e81d3ef516100495b2b2ea91199dafa1f57b7e78bcebddda1bbe36e13'
print(item['id'])
PY
)

curl --fail --silent --show-error --cookie "$target_cookies" \
  "$base_url/attachments/$attachment_id/download" \
  --output /tmp/goreecloud-notes-memos-import-downloaded.png
test "$(wc -c < /tmp/goreecloud-notes-memos-import-downloaded.png | tr -d ' ')" = "68"
test "$(sha256sum /tmp/goreecloud-notes-memos-import-downloaded.png | awk '{print $1}')" = "489b326e81d3ef516100495b2b2ea91199dafa1f57b7e78bcebddda1bbe36e13"

# Cross-user API access to the imported note and attachment must remain opaque.
printf '%s\n' "$isolation_password" | docker compose exec -T api python -m app.cli create-user \
  --username memos-import-isolation \
  --display-name 'Memos Import Isolation' \
  --password-stdin
curl --fail --silent --show-error \
  --cookie-jar "$isolation_cookies" \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"memos-import-isolation\",\"password\":\"$isolation_password\"}" \
  "$base_url/auth/login" > /tmp/goreecloud-notes-memos-import-isolation-login.json

test "$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  --cookie "$isolation_cookies" "$base_url/notes/$normal_note_id")" = "404"
test "$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  --cookie "$isolation_cookies" "$base_url/attachments/$attachment_id/download")" = "404"

# Verify persistent migration provenance exists only for the target owner/import.
docker compose exec -T db sh -c 'PGPASSWORD="$(cat /run/secrets/postgres_password)" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM migration_imports; SELECT count(*) FROM migration_note_records;"' \
  > /tmp/goreecloud-notes-memos-import-provenance-counts.txt
test "$(sed -n '1p' /tmp/goreecloud-notes-memos-import-provenance-counts.txt)" = "1"
test "$(sed -n '2p' /tmp/goreecloud-notes-memos-import-provenance-counts.txt)" = "2"

# Clean temporary migration inputs from the API container. Persisted imported target data
# intentionally remains for the rest of this disposable CI stack and is destroyed at teardown.
docker compose exec -T api rm -rf \
  "$container_source" "$container_manifest" "$container_evidence" "$container_map" "$container_evidence_root"
