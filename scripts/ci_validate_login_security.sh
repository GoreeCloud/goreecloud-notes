#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:8000/api/v1"
password='ci-only-rate-password-13579'
cookie_file="/tmp/goreecloud-notes-rate-cookies.txt"
headers_file="/tmp/goreecloud-notes-rate-headers.txt"
normalized_headers_file="/tmp/goreecloud-notes-rate-headers-normalized.txt"

clear_rate_state() {
  docker compose exec -T db sh -c \
    'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "TRUNCATE login_rate_buckets"' \
    >/dev/null
}

cleanup() {
  clear_rate_state || true
  rm -f "$cookie_file" "$headers_file" "$normalized_headers_file"
}
trap cleanup EXIT

clear_rate_state

printf '%s\n' "$password" | \
  docker compose exec -T api python -m app.cli create-user \
    --username rate-user \
    --display-name 'Rate User' \
    --password-stdin

wrong_login() {
  local username="$1"
  curl \
    --silent \
    --show-error \
    --output /dev/null \
    --write-out '%{http_code}' \
    --header 'Content-Type: application/json' \
    --data "{\"username\":\"$username\",\"password\":\"definitely-wrong-password\"}" \
    "$base_url/auth/login"
}

# CI overrides set the source+account threshold to 3. The first two generic
# failures remain 401; the threshold-reaching failure becomes bounded 429.
test "$(wrong_login rate-user)" = "401"
test "$(wrong_login ' RATE-USER ')" = "401"

third_status=$(curl \
  --silent \
  --show-error \
  --dump-header "$headers_file" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --data '{"username":"rate-user","password":"definitely-wrong-password"}' \
  "$base_url/auth/login")
test "$third_status" = "429"
tr -d '\r' < "$headers_file" > "$normalized_headers_file"
grep -Eiq '^retry-after: [1-9][0-9]*$' "$normalized_headers_file"
grep -Eiq '^cache-control: no-store$' "$normalized_headers_file"

# A correct password cannot bypass an active cooldown.
immediate_correct=$(curl \
  --silent \
  --show-error \
  --output /dev/null \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"rate-user\",\"password\":\"$password\"}" \
  "$base_url/auth/login")
test "$immediate_correct" = "429"

sleep 3

# Cooldown expiry is automatic and does not require an administrator unlock.
post_cooldown=$(curl \
  --silent \
  --show-error \
  --cookie-jar "$cookie_file" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"rate-user\",\"password\":\"$password\"}" \
  "$base_url/auth/login")
test "$post_cooldown" = "200"

# Successful login clears the matching source+account bucket, but source-wide
# history remains. Rotating unknown usernames therefore cannot evade the
# source-wide threshold (configured to 6 in CI).
test "$(wrong_login unknown-user-one)" = "401"
test "$(wrong_login unknown-user-two)" = "401"
test "$(wrong_login unknown-user-three)" = "429"

# The direct CI peer is not configured as a trusted proxy. A spoofed forwarded
# address must not create a fresh source bucket or bypass the source cooldown.
spoof_status=$(curl \
  --silent \
  --show-error \
  --output /dev/null \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --header 'X-Forwarded-For: 203.0.113.200' \
  --data "{\"username\":\"rate-user\",\"password\":\"$password\"}" \
  "$base_url/auth/login")
test "$spoof_status" = "429"

sleep 3

final_status=$(curl \
  --silent \
  --show-error \
  --output /dev/null \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"rate-user\",\"password\":\"$password\"}" \
  "$base_url/auth/login")
test "$final_status" = "200"

# Persisted rate state contains only opaque digest keys and bounded state. Clear
# the disposable CI state so later integration gates start from a clean source.
clear_rate_state
