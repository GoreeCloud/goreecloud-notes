#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:8000/api/v1"
owner_cookies="/tmp/goreecloud-notes-owner-cookies.txt"
other_cookies="/tmp/goreecloud-notes-other-cookies.txt"

# This validation intentionally runs after ci_validate_workspace.sh. That smoke
# leaves one updated owner note in Trash and preserves both authenticated cookie
# jars, giving search a stable dataset without creating a parallel fixture path.
test -s "$owner_cookies"
test -s "$other_cookies"

search_to() {
  local cookie_file="$1" query="$2" output_file="$3"
  curl --fail --silent --show-error --get \
    --cookie "$cookie_file" \
    --data-urlencode 'state=trashed' \
    --data-urlencode "q=$query" \
    "$base_url/search/notes" > "$output_file"
}

# Title terms are indexed and returned to the owning user.
search_to "$owner_cookies" 'Autosaved Note' /tmp/search-title.json
python - <<'PY'
import json
with open('/tmp/search-title.json', encoding='utf-8') as handle:
    notes = json.load(handle)
assert len(notes) == 1
assert notes[0]['title'] == 'Owner Autosaved Note'
PY

# String values nested in the GoreeCloud structured document are indexed too.
search_to "$owner_cookies" 'Autosaved body' /tmp/search-body.json
python - <<'PY'
import json
with open('/tmp/search-body.json', encoding='utf-8') as handle:
    notes = json.load(handle)
assert len(notes) == 1
assert notes[0]['document']['format'] == 'goreecloud.blocks'
PY

# websearch_to_tsquery supports quoted phrases and forgiving web-style OR input.
search_to "$owner_cookies" '"Autosaved body"' /tmp/search-phrase.json
search_to "$owner_cookies" 'Autosaved OR impossible' /tmp/search-web.json
python - <<'PY'
import json
for path in ('/tmp/search-phrase.json', '/tmp/search-web.json'):
    with open(path, encoding='utf-8') as handle:
        notes = json.load(handle)
    assert len(notes) == 1
    assert notes[0]['title'] == 'Owner Autosaved Note'
PY

# The generated vector must track the current row, not stale pre-edit content.
search_to "$owner_cookies" 'Original body' /tmp/search-stale.json
python - <<'PY'
import json
with open('/tmp/search-stale.json', encoding='utf-8') as handle:
    assert json.load(handle) == []
PY

# Identical search terms in another authenticated account must not disclose the
# owner's note or even reveal that a matching row exists.
search_to "$other_cookies" 'Autosaved body' /tmp/search-other.json
python - <<'PY'
import json
with open('/tmp/search-other.json', encoding='utf-8') as handle:
    assert json.load(handle) == []
PY

# Verify the migration created a stored generated vector and the intended GIN
# index in the actual ephemeral PostgreSQL instance used by this CI run.
docker compose exec -T api python - <<'PY'
from sqlalchemy import text
from app.database import engine

with engine.connect() as connection:
    generated = connection.execute(
        text(
            """
            SELECT is_generated
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'notes'
              AND column_name = 'search_vector'
            """
        )
    ).scalar_one()
    assert generated == 'ALWAYS'

    index_definition = connection.execute(
        text(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND tablename = 'notes'
              AND indexname = 'ix_notes_search_vector'
            """
        )
    ).scalar_one()
    assert 'using gin' in index_definition.lower()
    assert 'search_vector' in index_definition
PY
