#!/usr/bin/env bash
set -euo pipefail

container_export="/tmp/goreecloud-notes-memos-import-portable.zip"

# This gate intentionally runs after ci_validate_memos_import.sh in the same disposable
# Compose stack. The imported synthetic account and its provenance must already exist.
docker compose exec -T api rm -f "$container_export"
docker compose exec -T api python -m app.cli export-library \
  --username memos-import-target \
  --output "$container_export" \
  > /tmp/goreecloud-notes-memos-import-portable-cli.txt

grep -F 'Notes: 2' /tmp/goreecloud-notes-memos-import-portable-cli.txt
grep -F 'Attachments: 1' /tmp/goreecloud-notes-memos-import-portable-cli.txt

docker compose exec -T api python -m app.cli verify-library-export \
  --input "$container_export" \
  > /tmp/goreecloud-notes-memos-import-portable-verify.txt
grep -F 'Notes: 2' /tmp/goreecloud-notes-memos-import-portable-verify.txt
grep -F 'Attachments: 1' /tmp/goreecloud-notes-memos-import-portable-verify.txt

# Inspect the portable library and prove the exact source semantics intentionally deferred
# during native projection are still present as migration provenance.
docker compose exec -T api python - <<'PY'
import hashlib
import json
import zipfile

path = '/tmp/goreecloud-notes-memos-import-portable.zip'
with zipfile.ZipFile(path) as archive:
    library_raw = archive.read('library.json')
    library = json.loads(library_raw)
    bundle = json.loads(archive.read('bundle.json'))

    assert library['format'] == 'goreecloud-notes-native-export'
    assert library['schemaVersion'] == 1
    assert library['summary']['notes'] == 2
    assert library['summary']['attachments'] == 1
    assert library['summary']['migrationImports'] == 1
    assert library['summary']['migrationNoteRecords'] == 2
    assert len(library['migrationImports']) == 1
    assert len(library['migrationNoteRecords']) == 2

    migration = library['migrationImports'][0]
    assert migration['provider'] == 'memos'
    assert migration['sourceNoteCount'] == 2
    assert migration['importedNoteCount'] == 2
    assert migration['conversionProfile'] == 'literal-markdown-lines-v1'
    assert len(migration['sourceExportSha256']) == 64
    assert len(migration['manifestSha256']) == 64
    assert len(migration['evidenceSha256']) == 64

    records = {record['sourceName']: record for record in library['migrationNoteRecords']}
    assert set(records) == {'memos/100', 'memos/101'}

    active = records['memos/100']
    assert active['importId'] == migration['id']
    assert active['sourceUid'] == 'fixture-uid-100'
    assert active['sourceOrder'] == 0
    assert active['sourceRecord']['recordSha256'] == active['recordSha256']
    assert active['sourceRecord']['content']['markdown'] == '# Migration fixture\n\nNative migration inventory.'
    assert active['sourceRecord']['metadata']['color'] == 'blue'
    assert active['sourceRecord']['metadata']['location'] == {
        'latitude': 32.3668,
        'longitude': -86.3,
        'placeholder': 'Montgomery',
    }
    assert active['sourceRecord']['relations'] == [
        {
            'relatedMemo': 'memos/101',
            'relatedMemoUid': 'fixture-uid-101',
            'type': 'REFERENCE',
        }
    ]

    trashed = records['memos/101']
    assert trashed['importId'] == migration['id']
    assert trashed['sourceOrder'] == 1
    assert trashed['sourceRecord']['recordSha256'] == trashed['recordSha256']
    assert trashed['sourceRecord']['lifecycle']['state'] == 'trashed'
    assert trashed['sourceRecord']['lifecycle']['sourceState'] == 'TRASH'
    assert trashed['sourceRecord']['lifecycle']['restoreTarget'] == 'archived'

    note_ids = {note['id'] for note in library['notes']}
    assert {record['noteId'] for record in library['migrationNoteRecords']} == note_ids

    attachment = library['attachments'][0]
    payload = archive.read(attachment['archivePath'])
    assert attachment['sha256'] == '489b326e81d3ef516100495b2b2ea91199dafa1f57b7e78bcebddda1bbe36e13'
    assert attachment['sizeBytes'] == 68
    assert hashlib.sha256(payload).hexdigest() == attachment['sha256']
    assert len(payload) == 68

    assert bundle['library']['sha256'] == hashlib.sha256(library_raw).hexdigest()
    assert bundle['summary']['migrationImports'] == 1
    assert bundle['summary']['migrationNoteRecords'] == 2

    serialized = json.dumps(library, sort_keys=True)
    assert 'password_hash' not in serialized
    assert 'goreecloud_notes_session' not in serialized
    assert 'storage_key' not in serialized
PY

# The export is owned by the non-root API user and can be cleaned within the hardened
# cap_drop=ALL/no-new-privileges container boundary.
docker compose exec -T api rm -f "$container_export"
