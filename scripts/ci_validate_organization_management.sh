#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:8000/api/v1"
owner_cookies="/tmp/goreecloud-notes-organization-owner-cookies.txt"
other_cookies="/tmp/goreecloud-notes-organization-other-cookies.txt"

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

printf '%s\n' 'ci-organization-owner-password-12345' | docker compose exec -T api python -m app.cli create-user \
  --username organization-owner --display-name 'Organization Owner' --password-stdin
printf '%s\n' 'ci-organization-other-password-12345' | docker compose exec -T api python -m app.cli create-user \
  --username organization-other --display-name 'Organization Other' --password-stdin

login_user organization-owner ci-organization-owner-password-12345 "$owner_cookies" /tmp/organization-owner-login.json
login_user organization-other ci-organization-other-password-12345 "$other_cookies" /tmp/organization-other-login.json
owner_csrf=$(csrf_from "$owner_cookies")
other_csrf=$(csrf_from "$other_cookies")
test -n "$owner_csrf"
test -n "$other_csrf"

# Create two notebooks, then prove rename, re-parent, and explicit ordering.
curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' \
  --data '{"name":"Research"}' "$base_url/notebooks" > /tmp/organization-parent.json
parent_id=$(json_field /tmp/organization-parent.json id)

curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' \
  --data "{\"name\":\"Drafts\",\"parent_id\":\"$parent_id\"}" "$base_url/notebooks" > /tmp/organization-child.json
child_id=$(json_field /tmp/organization-child.json id)

curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' --request PATCH \
  --data '{"name":"Knowledge Base","sort_order":20}' "$base_url/notebooks/$parent_id" > /tmp/organization-parent-updated.json
grep -F '"name":"Knowledge Base"' /tmp/organization-parent-updated.json
test "$(json_field /tmp/organization-parent-updated.json sort_order)" = "20"

curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' --request PATCH \
  --data '{"parent_id":null,"sort_order":10}' "$base_url/notebooks/$child_id" > /tmp/organization-child-updated.json
grep -F '"parent_id":null' /tmp/organization-child-updated.json
test "$(json_field /tmp/organization-child-updated.json sort_order)" = "10"

curl --fail --silent --show-error --cookie "$owner_cookies" "$base_url/notebooks" > /tmp/organization-notebooks.json
python - "$child_id" "$parent_id" <<'PY'
import json, sys
with open('/tmp/organization-notebooks.json', encoding='utf-8') as handle:
    notebooks = json.load(handle)
ids = [item['id'] for item in notebooks]
assert ids.index(sys.argv[1]) < ids.index(sys.argv[2])
child = next(item for item in notebooks if item['id'] == sys.argv[1])
parent = next(item for item in notebooks if item['id'] == sys.argv[2])
assert child['parent_id'] is None and child['sort_order'] == 10
assert parent['name'] == 'Knowledge Base' and parent['sort_order'] == 20
PY

# Re-parent the child beneath the renamed notebook and preserve the explicit order value.
curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' --request PATCH \
  --data "{\"parent_id\":\"$parent_id\"}" "$base_url/notebooks/$child_id" > /tmp/organization-child-reparented.json
grep -F "\"parent_id\":\"$parent_id\"" /tmp/organization-child-reparented.json
test "$(json_field /tmp/organization-child-reparented.json sort_order)" = "10"

# Another user must not be able to rename, reorder, or re-parent the owner's notebook.
test "$(status_of --cookie "$other_cookies" --header "X-CSRF-Token: $other_csrf" \
  --header 'Content-Type: application/json' --request PATCH \
  --data '{"name":"Cross-user notebook rename","sort_order":1}' "$base_url/notebooks/$parent_id")" = "404"

# Create tags, then prove rename, recolor, normalization, assignment propagation, duplicate rejection, and clear-color behavior.
curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' \
  --data '{"name":"Infrastructure","color":"#2255aa"}' "$base_url/tags" > /tmp/organization-tag.json
tag_id=$(json_field /tmp/organization-tag.json id)

curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' \
  --data '{"name":"Operations"}' "$base_url/tags" > /tmp/organization-tag-duplicate-target.json

curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' --request PATCH \
  --data '{"name":"Platform Infrastructure","color":"#7b61ff"}' "$base_url/tags/$tag_id" > /tmp/organization-tag-updated.json
grep -F '"name":"Platform Infrastructure"' /tmp/organization-tag-updated.json
grep -F '"normalized_name":"platform infrastructure"' /tmp/organization-tag-updated.json
grep -F '"color":"#7b61ff"' /tmp/organization-tag-updated.json

curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' \
  --data '{"title":"Organization Tag Note"}' "$base_url/notes" > /tmp/organization-note.json
note_id=$(json_field /tmp/organization-note.json id)
test "$(status_of --cookie "$owner_cookies" --header "X-CSRF-Token: $owner_csrf" --request PUT "$base_url/notes/$note_id/tags/$tag_id")" = "204"
curl --fail --silent --show-error --cookie "$owner_cookies" "$base_url/notes/$note_id/tags" > /tmp/organization-note-tags.json
grep -F '"name":"Platform Infrastructure"' /tmp/organization-note-tags.json
grep -F '"color":"#7b61ff"' /tmp/organization-note-tags.json

duplicate_status=$(status_of --cookie "$owner_cookies" --header "X-CSRF-Token: $owner_csrf" \
  --header 'Content-Type: application/json' --request PATCH --data '{"name":"  OPERATIONS  "}' "$base_url/tags/$tag_id")
test "$duplicate_status" = "409"

curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' --request PATCH \
  --data '{"color":null}' "$base_url/tags/$tag_id" > /tmp/organization-tag-cleared.json
grep -F '"color":null' /tmp/organization-tag-cleared.json

# Another user must not be able to rename or recolor the owner's tag.
test "$(status_of --cookie "$other_cookies" --header "X-CSRF-Token: $other_csrf" \
  --header 'Content-Type: application/json' --request PATCH \
  --data '{"name":"Cross-user tag rename","color":"#ff0000"}' "$base_url/tags/$tag_id")" = "404"
