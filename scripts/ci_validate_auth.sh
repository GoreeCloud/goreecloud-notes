#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:8000/api/v1"
cookie_file="/tmp/goreecloud-notes-auth-cookies.txt"

printf '%s\n' 'ci-only-auth-password-12345' | \
  docker compose exec -T api python -m app.cli create-user \
    --username ci-user \
    --display-name 'CI User' \
    --password-stdin

login_status=$(curl \
  --silent \
  --show-error \
  --cookie-jar "$cookie_file" \
  --output /tmp/goreecloud-notes-login.json \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --data '{"username":"ci-user","password":"ci-only-auth-password-12345"}' \
  "$base_url/auth/login")
test "$login_status" = "200"
grep -F '"username":"ci-user"' /tmp/goreecloud-notes-login.json

csrf_token=$(awk '$6 == "goreecloud_notes_csrf" { print $7 }' "$cookie_file")
test -n "$csrf_token"

curl \
  --fail \
  --silent \
  --show-error \
  --cookie "$cookie_file" \
  "$base_url/auth/me" | grep -F '"username":"ci-user"'

no_csrf_status=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_file" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --request POST \
  "$base_url/auth/logout")
test "$no_csrf_status" = "403"

logout_status=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_file" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --header "X-CSRF-Token: $csrf_token" \
  --request POST \
  "$base_url/auth/logout")
test "$logout_status" = "204"

revoked_status=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_file" \
  --output /dev/null \
  --write-out '%{http_code}' \
  "$base_url/auth/me")
test "$revoked_status" = "401"
