#!/usr/bin/env bash
set -euo pipefail

container_export="/tmp/goreecloud-notes-memos-import-portable.zip"
container_reexport="/tmp/goreecloud-notes-memos-import-portable-reimported.zip"
target_password='ci-memos-import-target-password-12345'

# This gate intentionally runs after ci_validate_memos_import.sh in the same disposable
# Compose stack. The imported synthetic account and its provenance must already exist.
docker compose exec -T api rm -f "$container_export" "$container_reexport"
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

# Inspect the portable library and prove the exact normalized source semantics intentionally
# deferred during native projection are still present as migration provenance. Capture the
# preserved import ID for the later destructive native re-import verification.
import_id=$(docker compose exec -T api python - <<'PY'
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
    assert active['sourceUid'] == '100'
    assert active['sourceOrder'] == 0
    assert active['sourceRecord']['recordSha256'] == active['recordSha256']
    assert active['sourceRecord']['source']['state'] == 'normal'
    assert active['sourceRecord']['content']['markdown'] == '# Migration fixture\n\nNative migration inventory.'
    assert active['sourceRecord']['metadata']['color'] == 'blue'
    assert active['sourceRecord']['metadata']['location'] is None
    assert active['sourceRecord']['relations'] == [
        {
            'source': {'memo': 'memos/100', 'order': 0, 'provider': 'memos'},
            'targetExported': True,
            'targetSourceMemo': 'memos/101',
            'type': 'REFERENCE',
        }
    ]

    trashed = records['memos/101']
    assert trashed['importId'] == migration['id']
    assert trashed['sourceUid'] == '101'
    assert trashed['sourceOrder'] == 1
    assert trashed['sourceRecord']['recordSha256'] == trashed['recordSha256']
    assert trashed['sourceRecord']['source']['state'] == 'trash'
    assert trashed['sourceRecord']['source']['restoreTarget'] == 'archived'
    assert trashed['sourceRecord']['lifecycle']['state'] == 'trashed'
    assert trashed['sourceRecord']['lifecycle']['restoreTarget'] == 'archived'
    assert trashed['sourceRecord']['metadata']['location'] == {
        'latitude': 0,
        'longitude': 0,
        'placeholder': '',
    }

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
    print(migration['id'])
PY
)
test -n "$import_id"

source_bundle_sha=$(docker compose exec -T api sha256sum "$container_export" | awk '{print $1}')
source_user_id=$(docker compose exec -T api python - <<'PY'
from sqlalchemy import select
from app.database import SessionLocal
from app.models import User

with SessionLocal() as db:
    user = db.scalar(select(User).where(User.username_normalized == 'memos-import-target'))
    assert user is not None
    print(user.id)
PY
)
test -n "$source_user_id"

# Destructively remove only the disposable native target rows and owner-scoped attachment
# bytes after the verified ZIP exists. This proves the portable artifact can reconstruct both
# native projection and exact deferred Memos provenance rather than merely re-exporting the
# still-live database.
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
    assert user is not None
    db.delete(user)
    db.commit()

root = Path(get_settings().attachment_root).expanduser().resolve()
owner_path = (root / str(user_id)).resolve()
owner_path.relative_to(root)
shutil.rmtree(owner_path, ignore_errors=True)
PY

# Credentials are intentionally not part of the portable library. Recreate the empty account
# separately and prove it has a new account UUID before importing user knowledge.
printf '%s\n' "$target_password" | docker compose exec -T api python -m app.cli create-user \
  --username memos-import-target \
  --display-name 'Memos Import Portable Restore' \
  --password-stdin
restored_user_id=$(docker compose exec -T api python - <<'PY'
from sqlalchemy import select
from app.database import SessionLocal
from app.models import User

with SessionLocal() as db:
    user = db.scalar(select(User).where(User.username_normalized == 'memos-import-target'))
    assert user is not None
    print(user.id)
PY
)
test -n "$restored_user_id"
test "$restored_user_id" != "$source_user_id"

# Reconstruct the native library through the new explicit empty-target path.
docker compose exec -T api python -m app.cli import-library \
  --username memos-import-target \
  --input "$container_export" \
  --confirm-empty-target \
  --json > /tmp/goreecloud-notes-memos-portable-reimport.json

python - "$source_bundle_sha" "$source_user_id" "$restored_user_id" "$import_id" <<'PY'
import json
import sys
with open('/tmp/goreecloud-notes-memos-portable-reimport.json', encoding='utf-8') as handle:
    result = json.load(handle)
assert result['format'] == 'goreecloud-notes-native-import-result'
assert result['source']['bundleSha256'] == sys.argv[1]
assert result['source']['accountId'] == sys.argv[2]
assert result['target']['accountId'] == sys.argv[3]
assert result['counts'] == {
    'notebooks': 0,
    'notes': 2,
    'tags': 2,
    'noteTagRelationships': 2,
    'attachments': 1,
    'revisions': 0,
    'migrationImports': 1,
    'migrationNoteRecords': 2,
}
assert result['identity']['nativeObjectUuidsPreserved'] is True
assert result['identity']['targetAccountCredentialImported'] is False
assert result['validation']['bundleVerifiedBeforeMutation'] is True
assert result['validation']['attachmentBytesRehashedWhileStaging'] is True
assert result['validation']['targetWasEmptyAtCommitBoundary'] is True
assert result['validation']['uuidCollisionsRefused'] is True
PY

# The existing Memos-import verifier must still understand the provenance after it has crossed
# native export and native re-import boundaries.
docker compose exec -T api python -m app.migration verify-memos-import \
  --username memos-import-target \
  --import-id "$import_id" > /tmp/goreecloud-notes-memos-portable-reimport-verify.json
python - "$import_id" <<'PY'
import json
import sys
with open('/tmp/goreecloud-notes-memos-portable-reimport-verify.json', encoding='utf-8') as handle:
    report = json.load(handle)
assert report['import']['id'] == sys.argv[1]
assert report['verification']['databaseProvenanceValid'] is True
assert report['verification']['nativeNoteProjectionValid'] is True
assert report['verification']['tagAssignmentsValid'] is True
assert report['verification']['attachmentByteIntegrityValid'] is True
assert report['verification']['sourceMutationPerformed'] is False
assert report['verification']['targetVerificationMutationPerformed'] is False
assert report['equivalence']['sourceRecordsPreserved'] is True
assert report['equivalence']['nativeSemanticEquivalenceComplete'] is False
PY

# Re-export the reconstructed account and compare every portable user-knowledge collection,
# including the exact deferred source records and attachment bytes. Account identity is not
# expected to match because credentials/target account identity are intentionally outside the
# portable data restore boundary.
docker compose exec -T api python -m app.cli export-library \
  --username memos-import-target \
  --output "$container_reexport" >/tmp/goreecloud-notes-memos-portable-reexport-cli.txt
docker compose exec -T api python -m app.cli verify-library-export \
  --input "$container_reexport" >/tmp/goreecloud-notes-memos-portable-reexport-verify.txt

docker compose exec -T api python - "$container_export" "$container_reexport" <<'PY'
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
    assert source['account']['username'] == target['account']['username'] == 'memos-import-target'

    source_attachment = source['attachments'][0]
    target_attachment = target['attachments'][0]
    assert source_attachment['archivePath'] == target_attachment['archivePath']
    assert source_zip.read(source_attachment['archivePath']) == target_zip.read(target_attachment['archivePath'])

    source_records = {item['sourceName']: item for item in source['migrationNoteRecords']}
    target_records = {item['sourceName']: item for item in target['migrationNoteRecords']}
    assert target_records == source_records
    assert target_records['memos/100']['sourceRecord']['content']['markdown'] == '# Migration fixture\n\nNative migration inventory.'
    assert target_records['memos/100']['sourceRecord']['relations'][0]['type'] == 'REFERENCE'
    assert target_records['memos/101']['sourceRecord']['lifecycle']['restoreTarget'] == 'archived'
    assert target_records['memos/101']['sourceRecord']['metadata']['location'] == {
        'latitude': 0,
        'longitude': 0,
        'placeholder': '',
    }
PY

# Both ZIPs are owned by the non-root API user and can be cleaned within the hardened
# cap_drop=ALL/no-new-privileges container boundary.
docker compose exec -T api rm -f "$container_export" "$container_reexport"
