#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:8000/api/v1"
owner_cookies="/tmp/goreecloud-notes-owner-cookies.txt"
other_cookies="/tmp/goreecloud-notes-other-cookies.txt"

json_field() {
  python - "$1" "$2" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle)
print(value[sys.argv[2]])
PY
}

login_user() {
  local username="$1"
  local password="$2"
  local cookie_file="$3"
  local output_file="$4"

  curl \
    --fail \
    --silent \
    --show-error \
    --cookie-jar "$cookie_file" \
    --header 'Content-Type: application/json' \
    --data "{\"username\":\"$username\",\"password\":\"$password\"}" \
    "$base_url/auth/login" > "$output_file"
}

csrf_from() {
  awk '$6 == "goreecloud_notes_csrf" { print $7 }' "$1"
}

printf '%s\n' 'ci-owner-password-12345' | \
  docker compose exec -T api python -m app.cli create-user \
    --username workspace-owner \
    --display-name 'Workspace Owner' \
    --password-stdin
printf '%s\n' 'ci-other-password-12345' | \
  docker compose exec -T api python -m app.cli create-user \
    --username workspace-other \
    --display-name 'Workspace Other' \
    --password-stdin

login_user workspace-owner ci-owner-password-12345 "$owner_cookies" /tmp/owner-login.json
owner_csrf=$(csrf_from "$owner_cookies")
test -n "$owner_csrf"

login_user workspace-other ci-other-password-12345 "$other_cookies" /tmp/other-login.json
other_csrf=$(csrf_from "$other_cookies")
test -n "$other_csrf"

# Create a notebook hierarchy.
curl \
  --fail \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --header 'Content-Type: application/json' \
  --data '{"name":"Owner Notebook"}' \
  "$base_url/notebooks" > /tmp/owner-notebook.json
notebook_id=$(json_field /tmp/owner-notebook.json id)

test -n "$notebook_id"

curl \
  --fail \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --header 'Content-Type: application/json' \
  --data "{\"name\":\"Nested Notebook\",\"parent_id\":\"$notebook_id\"}" \
  "$base_url/notebooks" > /tmp/nested-notebook.json
nested_notebook_id=$(json_field /tmp/nested-notebook.json id)

test -n "$nested_notebook_id"

# Reject hierarchy cycles.
cycle_status=$(curl \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --header 'Content-Type: application/json' \
  --output /dev/null \
  --write-out '%{http_code}' \
  --request PATCH \
  --data "{\"parent_id\":\"$nested_notebook_id\"}" \
  "$base_url/notebooks/$notebook_id")
test "$cycle_status" = "409"

# Create a normalized tag and reject a case/spacing duplicate.
curl \
  --fail \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --header 'Content-Type: application/json' \
  --data '{"name":"Docker Research"}' \
  "$base_url/tags" > /tmp/owner-tag.json
tag_id=$(json_field /tmp/owner-tag.json id)

test -n "$tag_id"

duplicate_tag_status=$(curl \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --header 'Content-Type: application/json' \
  --output /dev/null \
  --write-out '%{http_code}' \
  --data '{"name":"  docker   research  "}' \
  "$base_url/tags")
test "$duplicate_tag_status" = "409"

# Create the owner's note in the owner's notebook.
curl \
  --fail \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --header 'Content-Type: application/json' \
  --data "{\"title\":\"Owner Original Note\",\"notebook_id\":\"$notebook_id\",\"document\":{\"format\":\"goreecloud.blocks\",\"version\":1,\"blocks\":[{\"type\":\"paragraph\",\"text\":\"Original body\"}]}}" \
  "$base_url/notes" > /tmp/owner-note.json
note_id=$(json_field /tmp/owner-note.json id)

test -n "$note_id"

# Assign the tag and prove tag filtering and per-note tag retrieval.
assign_status=$(curl \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --request PUT \
  "$base_url/notes/$note_id/tags/$tag_id")
test "$assign_status" = "204"

curl \
  --fail \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  "$base_url/notes/$note_id/tags" > /tmp/owner-note-tags.json
grep -F '"name":"Docker Research"' /tmp/owner-note-tags.json

curl \
  --fail \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  "$base_url/notes?state=normal&tag_id=$tag_id" > /tmp/tag-filtered-notes.json
grep -F '"title":"Owner Original Note"' /tmp/tag-filtered-notes.json

# Update content and prove the original state became revision 1.
curl \
  --fail \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --header 'Content-Type: application/json' \
  --request PATCH \
  --data '{"title":"Owner Updated Note","document":{"format":"goreecloud.blocks","version":1,"blocks":[{"type":"paragraph","text":"Updated body"}]},"is_pinned":true}' \
  "$base_url/notes/$note_id" > /tmp/owner-updated-note.json
grep -F '"title":"Owner Updated Note"' /tmp/owner-updated-note.json
grep -F '"is_pinned":true' /tmp/owner-updated-note.json

curl \
  --fail \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  "$base_url/notes/$note_id/revisions" > /tmp/owner-revisions.json
grep -F '"revision_number":1' /tmp/owner-revisions.json
grep -F '"title":"Owner Original Note"' /tmp/owner-revisions.json

# Cross-user object access and organizational references must not leak.
other_get_status=$(curl \
  --silent \
  --show-error \
  --cookie "$other_cookies" \
  --output /dev/null \
  --write-out '%{http_code}' \
  "$base_url/notes/$note_id")
test "$other_get_status" = "404"

other_patch_status=$(curl \
  --silent \
  --show-error \
  --cookie "$other_cookies" \
  --header "X-CSRF-Token: $other_csrf" \
  --header 'Content-Type: application/json' \
  --output /dev/null \
  --write-out '%{http_code}' \
  --request PATCH \
  --data '{"title":"Cross-user overwrite attempt"}' \
  "$base_url/notes/$note_id")
test "$other_patch_status" = "404"

other_notebook_status=$(curl \
  --silent \
  --show-error \
  --cookie "$other_cookies" \
  --header "X-CSRF-Token: $other_csrf" \
  --header 'Content-Type: application/json' \
  --output /dev/null \
  --write-out '%{http_code}' \
  --data "{\"title\":\"Cross-user notebook attempt\",\"notebook_id\":\"$notebook_id\"}" \
  "$base_url/notes")
test "$other_notebook_status" = "404"

other_tag_filter_status=$(curl \
  --silent \
  --show-error \
  --cookie "$other_cookies" \
  --output /dev/null \
  --write-out '%{http_code}' \
  "$base_url/notes?state=normal&tag_id=$tag_id")
test "$other_tag_filter_status" = "404"

curl \
  --fail \
  --silent \
  --show-error \
  --cookie "$other_cookies" \
  "$base_url/notes" > /tmp/other-notes.json
! grep -F 'Owner Updated Note' /tmp/other-notes.json

# Removing a notebook preserves the note and promotes its child notebook.
delete_notebook_status=$(curl \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --request DELETE \
  "$base_url/notebooks/$notebook_id")
test "$delete_notebook_status" = "204"

curl \
  --fail \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  "$base_url/notes/$note_id" > /tmp/note-after-notebook-delete.json
grep -F '"notebook_id":null' /tmp/note-after-notebook-delete.json

curl \
  --fail \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  "$base_url/notebooks" > /tmp/notebooks-after-parent-delete.json
python - "$nested_notebook_id" <<'PY'
import json
import sys
with open('/tmp/notebooks-after-parent-delete.json', encoding='utf-8') as handle:
    notebooks = json.load(handle)
child = next(item for item in notebooks if item['id'] == sys.argv[1])
assert child['parent_id'] is None
PY

# Remove and reassign the tag idempotently, then delete it and confirm cleanup.
remove_tag_status=$(curl \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --request DELETE \
  "$base_url/notes/$note_id/tags/$tag_id")
test "$remove_tag_status" = "204"

assign_again_status=$(curl \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --request PUT \
  "$base_url/notes/$note_id/tags/$tag_id")
test "$assign_again_status" = "204"

assign_idempotent_status=$(curl \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --request PUT \
  "$base_url/notes/$note_id/tags/$tag_id")
test "$assign_idempotent_status" = "204"

delete_tag_status=$(curl \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --request DELETE \
  "$base_url/tags/$tag_id")
test "$delete_tag_status" = "204"

curl \
  --fail \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  "$base_url/notes/$note_id/tags" > /tmp/tags-after-delete.json
python - <<'PY'
import json
with open('/tmp/tags-after-delete.json', encoding='utf-8') as handle:
    assert json.load(handle) == []
PY

# Archive/restore, then recoverable Trash.
curl \
  --fail \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --header 'Content-Type: application/json' \
  --request PATCH \
  --data '{"state":"archived"}' \
  "$base_url/notes/$note_id" > /tmp/archived-note.json
grep -F '"state":"archived"' /tmp/archived-note.json

curl \
  --fail \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --header 'Content-Type: application/json' \
  --request PATCH \
  --data '{"state":"normal"}' \
  "$base_url/notes/$note_id" > /tmp/restored-note.json
grep -F '"state":"normal"' /tmp/restored-note.json

trash_status=$(curl \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --request DELETE \
  "$base_url/notes/$note_id")
test "$trash_status" = "204"

curl \
  --fail \
  --silent \
  --show-error \
  --cookie "$owner_cookies" \
  "$base_url/notes?state=trashed" > /tmp/owner-trash.json
grep -F '"title":"Owner Updated Note"' /tmp/owner-trash.json
