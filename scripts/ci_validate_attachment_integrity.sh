#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:8000/api/v1"
cookies="/tmp/goreecloud-notes-attachment-integrity-cookies.txt"
source_file="/tmp/goreecloud-notes-attachment-integrity-source.txt"
username="attachment-integrity-owner"
password="ci-attachment-integrity-password-12345"

json_field() {
  python - "$1" "$2" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)[sys.argv[2]])
PY
}

csrf_from() {
  awk '$6 == "goreecloud_notes_csrf" { print $7 }' "$1"
}

printf '%s\n' "$password" | docker compose exec -T api python -m app.cli create-user \
  --username "$username" --display-name 'Attachment Integrity Owner' --password-stdin

curl --fail --silent --show-error \
  --cookie-jar "$cookies" \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"$username\",\"password\":\"$password\"}" \
  "$base_url/auth/login" > /tmp/attachment-integrity-login.json
csrf=$(csrf_from "$cookies")
test -n "$csrf"

curl --fail --silent --show-error --cookie "$cookies" \
  --header "X-CSRF-Token: $csrf" --header 'Content-Type: application/json' \
  --data '{"title":"Attachment integrity audit note"}' \
  "$base_url/notes" > /tmp/attachment-integrity-note.json
note_id=$(json_field /tmp/attachment-integrity-note.json id)

printf '%s' 'GoreeCloud attachment integrity live validation payload' > "$source_file"
curl --fail --silent --show-error --cookie "$cookies" \
  --header "X-CSRF-Token: $csrf" \
  --header 'Content-Type: text/plain' \
  --data-binary "@$source_file" \
  "$base_url/notes/$note_id/attachments?filename=integrity.txt" \
  > /tmp/attachment-integrity-record.json
attachment_id=$(json_field /tmp/attachment-integrity-record.json id)

# A healthy store must audit cleanly and report the expected record as verified.
docker compose exec -T api python -m app.cli audit-attachments \
  --username "$username" --json > /tmp/attachment-integrity-clean.json
python - <<'PY'
import json
with open('/tmp/attachment-integrity-clean.json', encoding='utf-8') as handle:
    report = json.load(handle)
assert report['format'] == 'goreecloud-notes-attachment-audit'
assert report['schemaVersion'] == 1
assert report['clean'] is True
assert report['summary']['attachmentRecords'] == 1
assert report['summary']['verifiedAttachments'] == 1
assert report['summary']['orphanFiles'] == 0
assert report['summary']['issues'] == 0
PY

# Corrupt the disposable attachment bytes directly. The audit must detect the mismatch and
# return exit code 3 without repairing or mutating the record.
docker compose exec -T api python - "$attachment_id" <<'PY'
from pathlib import Path
import sys
from uuid import UUID
from sqlalchemy import select
from app.config import get_settings
from app.database import SessionLocal
from app.models import Attachment

with SessionLocal() as db:
    attachment = db.scalar(select(Attachment).where(Attachment.id == UUID(sys.argv[1])))
    assert attachment is not None
    path = Path(get_settings().attachment_root) / attachment.storage_key
    original = path.read_bytes()
    Path('/tmp/goreecloud-notes-integrity-original.bin').write_bytes(original)
    path.write_bytes(b'corrupted attachment bytes')
PY

set +e
docker compose exec -T api python -m app.cli audit-attachments \
  --username "$username" --json > /tmp/attachment-integrity-corrupt.json
audit_status=$?
set -e
test "$audit_status" = "3"
python - <<'PY'
import json
with open('/tmp/attachment-integrity-corrupt.json', encoding='utf-8') as handle:
    report = json.load(handle)
codes = {issue['code'] for issue in report['issues']}
assert report['clean'] is False
assert 'size_mismatch' in codes or 'sha256_mismatch' in codes
PY

# Restore the known-good disposable bytes and prove the audit returns to clean state.
docker compose exec -T api python - "$attachment_id" <<'PY'
from pathlib import Path
import sys
from uuid import UUID
from sqlalchemy import select
from app.config import get_settings
from app.database import SessionLocal
from app.models import Attachment

backup = Path('/tmp/goreecloud-notes-integrity-original.bin')
with SessionLocal() as db:
    attachment = db.scalar(select(Attachment).where(Attachment.id == UUID(sys.argv[1])))
    assert attachment is not None
    path = Path(get_settings().attachment_root) / attachment.storage_key
    path.write_bytes(backup.read_bytes())
backup.unlink()
PY

docker compose exec -T api python -m app.cli audit-attachments \
  --username "$username" --json > /tmp/attachment-integrity-restored.json
python - <<'PY'
import json
with open('/tmp/attachment-integrity-restored.json', encoding='utf-8') as handle:
    report = json.load(handle)
assert report['clean'] is True
assert report['summary']['verifiedAttachments'] == 1
PY

# Missing bytes must be distinguished from corruption. Preserve the disposable bytes outside
# the attachment root, remove the expected file, detect the gap, then restore it.
docker compose exec -T api python - "$attachment_id" <<'PY'
from pathlib import Path
import sys
from uuid import UUID
from sqlalchemy import select
from app.config import get_settings
from app.database import SessionLocal
from app.models import Attachment

with SessionLocal() as db:
    attachment = db.scalar(select(Attachment).where(Attachment.id == UUID(sys.argv[1])))
    assert attachment is not None
    path = Path(get_settings().attachment_root) / attachment.storage_key
    Path('/tmp/goreecloud-notes-integrity-missing-backup.bin').write_bytes(path.read_bytes())
    path.unlink()
PY

set +e
docker compose exec -T api python -m app.cli audit-attachments \
  --username "$username" --json > /tmp/attachment-integrity-missing.json
missing_status=$?
set -e
test "$missing_status" = "3"
python - <<'PY'
import json
with open('/tmp/attachment-integrity-missing.json', encoding='utf-8') as handle:
    report = json.load(handle)
assert report['clean'] is False
assert any(issue['code'] == 'missing_bytes' for issue in report['issues'])
PY

docker compose exec -T api python - "$attachment_id" <<'PY'
from pathlib import Path
import sys
from uuid import UUID
from sqlalchemy import select
from app.config import get_settings
from app.database import SessionLocal
from app.models import Attachment

backup = Path('/tmp/goreecloud-notes-integrity-missing-backup.bin')
with SessionLocal() as db:
    attachment = db.scalar(select(Attachment).where(Attachment.id == UUID(sys.argv[1])))
    assert attachment is not None
    path = Path(get_settings().attachment_root) / attachment.storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(backup.read_bytes())
backup.unlink()
PY

# Unexpected owner-scoped files must be reported as orphans and never auto-deleted.
docker compose exec -T api python - "$username" <<'PY'
from pathlib import Path
import sys
from sqlalchemy import select
from app.auth import normalize_username
from app.config import get_settings
from app.database import SessionLocal
from app.models import User

with SessionLocal() as db:
    user = db.scalar(select(User).where(User.username_normalized == normalize_username(sys.argv[1])))
    assert user is not None
    orphan = Path(get_settings().attachment_root) / str(user.id) / 'orphan-audit.bin'
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b'orphan bytes')
PY

set +e
docker compose exec -T api python -m app.cli audit-attachments \
  --username "$username" --json > /tmp/attachment-integrity-orphan.json
orphan_status=$?
set -e
test "$orphan_status" = "3"
python - <<'PY'
import json
with open('/tmp/attachment-integrity-orphan.json', encoding='utf-8') as handle:
    report = json.load(handle)
assert report['clean'] is False
assert report['summary']['orphanFiles'] == 1
assert any(issue['code'] == 'orphan_file' for issue in report['issues'])
PY

docker compose exec -T api python - "$username" <<'PY'
from pathlib import Path
import sys
from sqlalchemy import select
from app.auth import normalize_username
from app.config import get_settings
from app.database import SessionLocal
from app.models import User

with SessionLocal() as db:
    user = db.scalar(select(User).where(User.username_normalized == normalize_username(sys.argv[1])))
    assert user is not None
    orphan = Path(get_settings().attachment_root) / str(user.id) / 'orphan-audit.bin'
    assert orphan.read_bytes() == b'orphan bytes'
    orphan.unlink()
PY

# Leave the disposable store healthy so later export, migration, and recovery gates run on
# known-good attachment state.
docker compose exec -T api python -m app.cli audit-attachments \
  --username "$username" --json > /tmp/attachment-integrity-final.json
python - <<'PY'
import json
with open('/tmp/attachment-integrity-final.json', encoding='utf-8') as handle:
    report = json.load(handle)
assert report['clean'] is True
assert report['summary']['attachmentRecords'] == 1
assert report['summary']['verifiedAttachments'] == 1
assert report['summary']['orphanFiles'] == 0
assert report['summary']['issues'] == 0
PY
