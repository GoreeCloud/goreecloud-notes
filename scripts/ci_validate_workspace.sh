#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:8000/api/v1"
owner_cookies="/tmp/goreecloud-notes-owner-cookies.txt"
other_cookies="/tmp/goreecloud-notes-other-cookies.txt"

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

printf '%s\n' 'ci-owner-password-12345' | docker compose exec -T api python -m app.cli create-user \
  --username workspace-owner --display-name 'Workspace Owner' --password-stdin
printf '%s\n' 'ci-other-password-12345' | docker compose exec -T api python -m app.cli create-user \
  --username workspace-other --display-name 'Workspace Other' --password-stdin

login_user workspace-owner ci-owner-password-12345 "$owner_cookies" /tmp/owner-login.json
login_user workspace-other ci-other-password-12345 "$other_cookies" /tmp/other-login.json
owner_csrf=$(csrf_from "$owner_cookies")
other_csrf=$(csrf_from "$other_cookies")
test -n "$owner_csrf"
test -n "$other_csrf"

# Notebook hierarchy and cycle rejection.
curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' \
  --data '{"name":"Owner Notebook"}' "$base_url/notebooks" > /tmp/owner-notebook.json
notebook_id=$(json_field /tmp/owner-notebook.json id)

curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' \
  --data "{\"name\":\"Nested Notebook\",\"parent_id\":\"$notebook_id\"}" \
  "$base_url/notebooks" > /tmp/nested-notebook.json
nested_notebook_id=$(json_field /tmp/nested-notebook.json id)

cycle_status=$(status_of --cookie "$owner_cookies" --header "X-CSRF-Token: $owner_csrf" \
  --header 'Content-Type: application/json' --request PATCH \
  --data "{\"parent_id\":\"$nested_notebook_id\"}" "$base_url/notebooks/$notebook_id")
test "$cycle_status" = "409"

# Normalized user-local tags.
curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' \
  --data '{"name":"Docker Research"}' "$base_url/tags" > /tmp/owner-tag.json
tag_id=$(json_field /tmp/owner-tag.json id)

duplicate_tag_status=$(status_of --cookie "$owner_cookies" --header "X-CSRF-Token: $owner_csrf" \
  --header 'Content-Type: application/json' --data '{"name":"  docker   research  "}' "$base_url/tags")
test "$duplicate_tag_status" = "409"

# Create a note and prove content_version starts at 1.
curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' \
  --data "{\"title\":\"Owner Original Note\",\"notebook_id\":\"$notebook_id\",\"document\":{\"format\":\"goreecloud.blocks\",\"version\":1,\"blocks\":[{\"type\":\"paragraph\",\"text\":\"Original body\"}]}}" \
  "$base_url/notes" > /tmp/owner-note.json
note_id=$(json_field /tmp/owner-note.json id)
test "$(json_field /tmp/owner-note.json content_version)" = "1"

# Tag assignment/filtering.
test "$(status_of --cookie "$owner_cookies" --header "X-CSRF-Token: $owner_csrf" --request PUT "$base_url/notes/$note_id/tags/$tag_id")" = "204"
curl --fail --silent --show-error --cookie "$owner_cookies" "$base_url/notes/$note_id/tags" > /tmp/note-tags.json
grep -F '"name":"Docker Research"' /tmp/note-tags.json
curl --fail --silent --show-error --cookie "$owner_cookies" "$base_url/notes?state=normal&tag_id=$tag_id" > /tmp/tag-filtered.json
grep -F '"title":"Owner Original Note"' /tmp/tag-filtered.json

# First content edit creates a snapshot of version 1 and advances to version 2.
curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' --request PATCH \
  --data '{"expected_content_version":1,"title":"Owner Updated Note","document":{"format":"goreecloud.blocks","version":1,"blocks":[{"type":"paragraph","text":"Updated body"}]},"is_pinned":true}' \
  "$base_url/notes/$note_id" > /tmp/update-v2.json
test "$(json_field /tmp/update-v2.json content_version)" = "2"
grep -F '"is_pinned":true' /tmp/update-v2.json

curl --fail --silent --show-error --cookie "$owner_cookies" "$base_url/notes/$note_id/revisions" > /tmp/revisions-v2.json
python - <<'PY'
import json
with open('/tmp/revisions-v2.json', encoding='utf-8') as handle:
    revisions = json.load(handle)
assert len(revisions) == 1
assert revisions[0]['revision_number'] == 1
assert revisions[0]['content_version'] == 1
assert revisions[0]['title'] == 'Owner Original Note'
PY

# Immediate second autosave advances content version but coalesces revision history.
curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' --request PATCH \
  --data '{"expected_content_version":2,"title":"Owner Autosaved Note","document":{"format":"goreecloud.blocks","version":1,"blocks":[{"type":"paragraph","text":"Autosaved body"}]}}' \
  "$base_url/notes/$note_id" > /tmp/update-v3.json
test "$(json_field /tmp/update-v3.json content_version)" = "3"

curl --fail --silent --show-error --cookie "$owner_cookies" "$base_url/notes/$note_id/revisions" > /tmp/revisions-v3.json
python - <<'PY'
import json
with open('/tmp/revisions-v3.json', encoding='utf-8') as handle:
    revisions = json.load(handle)
assert len(revisions) == 1
assert revisions[0]['content_version'] == 1
PY

# A stale editor must fail rather than overwrite version 3.
stale_status=$(status_of --cookie "$owner_cookies" --header "X-CSRF-Token: $owner_csrf" \
  --header 'Content-Type: application/json' --request PATCH \
  --data '{"expected_content_version":1,"title":"Stale overwrite attempt"}' "$base_url/notes/$note_id")
test "$stale_status" = "409"
curl --fail --silent --show-error --cookie "$owner_cookies" "$base_url/notes/$note_id" > /tmp/after-stale.json
grep -F '"title":"Owner Autosaved Note"' /tmp/after-stale.json
test "$(json_field /tmp/after-stale.json content_version)" = "3"

# Cross-user object and organization access must remain opaque.
test "$(status_of --cookie "$other_cookies" "$base_url/notes/$note_id")" = "404"
test "$(status_of --cookie "$other_cookies" --header "X-CSRF-Token: $other_csrf" \
  --header 'Content-Type: application/json' --request PATCH \
  --data '{"expected_content_version":3,"title":"Cross-user overwrite"}' "$base_url/notes/$note_id")" = "404"
test "$(status_of --cookie "$other_cookies" --header "X-CSRF-Token: $other_csrf" \
  --header 'Content-Type: application/json' --data "{\"title\":\"Cross-user notebook attempt\",\"notebook_id\":\"$notebook_id\"}" "$base_url/notes")" = "404"
test "$(status_of --cookie "$other_cookies" "$base_url/notes?state=normal&tag_id=$tag_id")" = "404"

# Notebook deletion preserves note and promotes child notebook.
test "$(status_of --cookie "$owner_cookies" --header "X-CSRF-Token: $owner_csrf" --request DELETE "$base_url/notebooks/$notebook_id")" = "204"
curl --fail --silent --show-error --cookie "$owner_cookies" "$base_url/notes/$note_id" > /tmp/after-notebook-delete.json
grep -F '"notebook_id":null' /tmp/after-notebook-delete.json
curl --fail --silent --show-error --cookie "$owner_cookies" "$base_url/notebooks" > /tmp/notebooks-after-delete.json
python - "$nested_notebook_id" <<'PY'
import json, sys
with open('/tmp/notebooks-after-delete.json', encoding='utf-8') as handle:
    child = next(item for item in json.load(handle) if item['id'] == sys.argv[1])
assert child['parent_id'] is None
PY

# Tag assignment remains idempotent and deleting tag does not delete note.
test "$(status_of --cookie "$owner_cookies" --header "X-CSRF-Token: $owner_csrf" --request DELETE "$base_url/notes/$note_id/tags/$tag_id")" = "204"
test "$(status_of --cookie "$owner_cookies" --header "X-CSRF-Token: $owner_csrf" --request PUT "$base_url/notes/$note_id/tags/$tag_id")" = "204"
test "$(status_of --cookie "$owner_cookies" --header "X-CSRF-Token: $owner_csrf" --request PUT "$base_url/notes/$note_id/tags/$tag_id")" = "204"
test "$(status_of --cookie "$owner_cookies" --header "X-CSRF-Token: $owner_csrf" --request DELETE "$base_url/tags/$tag_id")" = "204"
curl --fail --silent --show-error --cookie "$owner_cookies" "$base_url/notes/$note_id/tags" > /tmp/tags-after-delete.json
python - <<'PY'
import json
with open('/tmp/tags-after-delete.json', encoding='utf-8') as handle:
    assert json.load(handle) == []
PY

# Metadata-only lifecycle changes do not require or advance content_version.
curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' --request PATCH \
  --data '{"state":"archived"}' "$base_url/notes/$note_id" > /tmp/archived.json
grep -F '"state":"archived"' /tmp/archived.json
test "$(json_field /tmp/archived.json content_version)" = "3"

curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' --request PATCH \
  --data '{"state":"normal"}' "$base_url/notes/$note_id" > /tmp/restored.json
grep -F '"state":"normal"' /tmp/restored.json
test "$(json_field /tmp/restored.json content_version)" = "3"

test "$(status_of --cookie "$owner_cookies" --header "X-CSRF-Token: $owner_csrf" --request DELETE "$base_url/notes/$note_id")" = "204"
curl --fail --silent --show-error --cookie "$owner_cookies" "$base_url/notes?state=trashed" > /tmp/trash.json
grep -F '"title":"Owner Autosaved Note"' /tmp/trash.json
