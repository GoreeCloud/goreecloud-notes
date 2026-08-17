#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:8000/api/v1"
owner_cookies="/tmp/goreecloud-notes-link-owner-cookies.txt"
other_cookies="/tmp/goreecloud-notes-link-other-cookies.txt"

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
  local username="$1" password="$2" cookie_file="$3"
  curl --fail --silent --show-error \
    --cookie-jar "$cookie_file" \
    --header 'Content-Type: application/json' \
    --data "{\"username\":\"$username\",\"password\":\"$password\"}" \
    "$base_url/auth/login" > /dev/null
}

csrf_from() {
  awk '$6 == "goreecloud_notes_csrf" { print $7 }' "$1"
}

create_note() {
  local cookie_file="$1" csrf="$2" title="$3" output="$4"
  curl --fail --silent --show-error --cookie "$cookie_file" \
    --header "X-CSRF-Token: $csrf" --header 'Content-Type: application/json' \
    --data "{\"title\":\"$title\",\"document\":{\"format\":\"goreecloud.blocks\",\"version\":1,\"blocks\":[]}}" \
    "$base_url/notes" > "$output"
}

printf '%s\n' 'ci-link-owner-password-12345' | docker compose exec -T api python -m app.cli create-user \
  --username link-owner --display-name 'Link Owner' --password-stdin
printf '%s\n' 'ci-link-other-password-12345' | docker compose exec -T api python -m app.cli create-user \
  --username link-other --display-name 'Link Other' --password-stdin

login_user link-owner ci-link-owner-password-12345 "$owner_cookies"
login_user link-other ci-link-other-password-12345 "$other_cookies"
owner_csrf=$(csrf_from "$owner_cookies")
other_csrf=$(csrf_from "$other_cookies")
test -n "$owner_csrf"
test -n "$other_csrf"

create_note "$owner_cookies" "$owner_csrf" 'Link Target' /tmp/link-target.json
create_note "$owner_cookies" "$owner_csrf" 'Link Source' /tmp/link-source.json
create_note "$other_cookies" "$other_csrf" 'Private Other Target' /tmp/link-other-target.json

target_id=$(json_field /tmp/link-target.json id)
source_id=$(json_field /tmp/link-source.json id)
other_target_id=$(json_field /tmp/link-other-target.json id)

# A normal same-owner internal link is stored in the authoritative document and resolved
# into the derived relationship index by PostgreSQL.
curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' --request PATCH \
  --data "{\"expected_content_version\":1,\"document\":{\"format\":\"goreecloud.blocks\",\"version\":1,\"blocks\":[{\"type\":\"paragraph\",\"content\":[{\"type\":\"text\",\"text\":\"See Link Target\",\"marks\":[{\"type\":\"noteLink\",\"note_id\":\"$target_id\"}]}]}]}}" \
  "$base_url/notes/$source_id" > /tmp/link-source-updated.json

grep -F '"type":"noteLink"' /tmp/link-source-updated.json
grep -F "\"note_id\":\"$target_id\"" /tmp/link-source-updated.json

curl --fail --silent --show-error --cookie "$owner_cookies" "$base_url/notes/$source_id/links" > /tmp/source-links.json
curl --fail --silent --show-error --cookie "$owner_cookies" "$base_url/notes/$target_id/links" > /tmp/target-links.json
python - "$source_id" "$target_id" <<'PY'
import json, sys
source_id, target_id = sys.argv[1:]
with open('/tmp/source-links.json', encoding='utf-8') as handle:
    source = json.load(handle)
with open('/tmp/target-links.json', encoding='utf-8') as handle:
    target = json.load(handle)
assert [item['id'] for item in source['outgoing']] == [target_id]
assert source['backlinks'] == []
assert [item['id'] for item in target['backlinks']] == [source_id]
assert target['outgoing'] == []
PY

# Another account cannot discover link metadata for an owner note.
test "$(status_of --cookie "$other_cookies" "$base_url/notes/$target_id/links")" = "404"

# A syntactically valid UUID belonging to another account remains an unresolved portable
# reference and must never enter the same-owner relationship index.
curl --fail --silent --show-error --cookie "$owner_cookies" \
  --header "X-CSRF-Token: $owner_csrf" --header 'Content-Type: application/json' --request PATCH \
  --data "{\"expected_content_version\":2,\"document\":{\"format\":\"goreecloud.blocks\",\"version\":1,\"blocks\":[{\"type\":\"paragraph\",\"content\":[{\"type\":\"text\",\"text\":\"Unresolved private reference\",\"marks\":[{\"type\":\"noteLink\",\"note_id\":\"$other_target_id\"}]}]}]}}" \
  "$base_url/notes/$source_id" > /tmp/link-cross-owner-document.json

curl --fail --silent --show-error --cookie "$owner_cookies" "$base_url/notes/$source_id/links" > /tmp/source-links-after-cross-owner.json
python - <<'PY'
import json
with open('/tmp/source-links-after-cross-owner.json', encoding='utf-8') as handle:
    links = json.load(handle)
assert links['outgoing'] == []
assert links['backlinks'] == []
PY

# Invalid note-link identifiers are rejected by the shared server document contract.
test "$(status_of --cookie "$owner_cookies" --header "X-CSRF-Token: $owner_csrf" \
  --header 'Content-Type: application/json' --request PATCH \
  --data '{"expected_content_version":3,"document":{"format":"goreecloud.blocks","version":1,"blocks":[{"type":"paragraph","content":[{"type":"text","text":"bad","marks":[{"type":"noteLink","note_id":"not-a-uuid"}]}]}]}}' \
  "$base_url/notes/$source_id")" = "422"
