#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:8000/api/v1"
cookie_a="/tmp/goreecloud-notes-auth-cookies-a.txt"
cookie_b="/tmp/goreecloud-notes-auth-cookies-b.txt"
cookie_c="/tmp/goreecloud-notes-auth-cookies-c.txt"
initial_password='ci-only-auth-password-12345'
rotated_password='ci-only-rotated-password-67890'
recovered_password='ci-only-recovered-password-24680'

rm -f "$cookie_a" "$cookie_b" "$cookie_c"

printf '%s\n' "$initial_password" | \
  docker compose exec -T api python -m app.cli create-user \
    --username ci-user \
    --display-name 'CI User' \
    --password-stdin

login_a_status=$(curl \
  --silent \
  --show-error \
  --cookie-jar "$cookie_a" \
  --output /tmp/goreecloud-notes-login-a.json \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"ci-user\",\"password\":\"$initial_password\"}" \
  "$base_url/auth/login")
test "$login_a_status" = "200"
grep -F '"username":"ci-user"' /tmp/goreecloud-notes-login-a.json

login_b_status=$(curl \
  --silent \
  --show-error \
  --cookie-jar "$cookie_b" \
  --output /tmp/goreecloud-notes-login-b.json \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"ci-user\",\"password\":\"$initial_password\"}" \
  "$base_url/auth/login")
test "$login_b_status" = "200"

csrf_a=$(awk '$6 == "goreecloud_notes_csrf" { print $7 }' "$cookie_a")
test -n "$csrf_a"

curl \
  --fail \
  --silent \
  --show-error \
  --cookie "$cookie_a" \
  "$base_url/auth/me" | grep -F '"username":"ci-user"'

sessions_before_status=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_a" \
  --output /tmp/goreecloud-notes-sessions-before.json \
  --write-out '%{http_code}' \
  "$base_url/auth/sessions")
test "$sessions_before_status" = "200"
test "$(grep -o '"id":' /tmp/goreecloud-notes-sessions-before.json | wc -l)" -eq 2
test "$(grep -o '"current":true' /tmp/goreecloud-notes-sessions-before.json | wc -l)" -eq 1

revoke_others_without_csrf=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_a" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --request POST \
  "$base_url/auth/sessions/revoke-others")
test "$revoke_others_without_csrf" = "403"

revoke_others_status=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_a" \
  --output /tmp/goreecloud-notes-revoke-others.json \
  --write-out '%{http_code}' \
  --header "X-CSRF-Token: $csrf_a" \
  --request POST \
  "$base_url/auth/sessions/revoke-others")
test "$revoke_others_status" = "200"
grep -F '"revoked":1' /tmp/goreecloud-notes-revoke-others.json

current_after_selective_revoke=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_a" \
  --output /dev/null \
  --write-out '%{http_code}' \
  "$base_url/auth/me")
test "$current_after_selective_revoke" = "200"

other_after_selective_revoke=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_b" \
  --output /dev/null \
  --write-out '%{http_code}' \
  "$base_url/auth/me")
test "$other_after_selective_revoke" = "401"

sessions_after_status=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_a" \
  --output /tmp/goreecloud-notes-sessions-after.json \
  --write-out '%{http_code}' \
  "$base_url/auth/sessions")
test "$sessions_after_status" = "200"
test "$(grep -o '"id":' /tmp/goreecloud-notes-sessions-after.json | wc -l)" -eq 1
grep -F '"current":true' /tmp/goreecloud-notes-sessions-after.json

password_without_csrf=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_a" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --data "{\"current_password\":\"$initial_password\",\"new_password\":\"$rotated_password\"}" \
  "$base_url/auth/password")
test "$password_without_csrf" = "403"

wrong_current_status=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_a" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --header "X-CSRF-Token: $csrf_a" \
  --data "{\"current_password\":\"wrong-current-password\",\"new_password\":\"$rotated_password\"}" \
  "$base_url/auth/password")
test "$wrong_current_status" = "400"

same_password_status=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_a" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --header "X-CSRF-Token: $csrf_a" \
  --data "{\"current_password\":\"$initial_password\",\"new_password\":\"$initial_password\"}" \
  "$base_url/auth/password")
test "$same_password_status" = "400"

rotate_status=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_a" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --header "X-CSRF-Token: $csrf_a" \
  --data "{\"current_password\":\"$initial_password\",\"new_password\":\"$rotated_password\"}" \
  "$base_url/auth/password")
test "$rotate_status" = "204"

revoked_a_status=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_a" \
  --output /dev/null \
  --write-out '%{http_code}' \
  "$base_url/auth/me")
test "$revoked_a_status" = "401"

revoked_b_status=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_b" \
  --output /dev/null \
  --write-out '%{http_code}' \
  "$base_url/auth/me")
test "$revoked_b_status" = "401"

old_password_status=$(curl \
  --silent \
  --show-error \
  --output /dev/null \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"ci-user\",\"password\":\"$initial_password\"}" \
  "$base_url/auth/login")
test "$old_password_status" = "401"

rotated_login_status=$(curl \
  --silent \
  --show-error \
  --cookie-jar "$cookie_c" \
  --output /tmp/goreecloud-notes-login-c.json \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"ci-user\",\"password\":\"$rotated_password\"}" \
  "$base_url/auth/login")
test "$rotated_login_status" = "200"

printf '%s\n' "$recovered_password" | \
  docker compose exec -T api python -m app.cli reset-password \
    --username ' CI-USER ' \
    --password-stdin

recovery_revoked_status=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_c" \
  --output /dev/null \
  --write-out '%{http_code}' \
  "$base_url/auth/me")
test "$recovery_revoked_status" = "401"

rotated_password_status=$(curl \
  --silent \
  --show-error \
  --output /dev/null \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"ci-user\",\"password\":\"$rotated_password\"}" \
  "$base_url/auth/login")
test "$rotated_password_status" = "401"

rm -f "$cookie_c"
recovered_login_status=$(curl \
  --silent \
  --show-error \
  --cookie-jar "$cookie_c" \
  --output /tmp/goreecloud-notes-login-recovered.json \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"ci-user\",\"password\":\"$recovered_password\"}" \
  "$base_url/auth/login")
test "$recovered_login_status" = "200"

# Administrative lifecycle status is non-sensitive and reflects the live session.
docker compose exec -T api python -m app.cli account-status \
  --username ' CI-USER ' \
  --json > /tmp/goreecloud-notes-account-status-active.json
grep -F '"isActive":true' /tmp/goreecloud-notes-account-status-active.json
grep -F '"activeSessions":1' /tmp/goreecloud-notes-account-status-active.json

# Disabling requires an explicit acknowledgement rather than a bare account name.
if docker compose exec -T api python -m app.cli disable-user \
  --username ci-user > /tmp/goreecloud-notes-disable-without-confirmation.txt 2>&1; then
  echo "disable-user unexpectedly succeeded without --confirm-disable" >&2
  exit 1
fi
grep -F -- '--confirm-disable' /tmp/goreecloud-notes-disable-without-confirmation.txt

docker compose exec -T api python -m app.cli disable-user \
  --username ci-user \
  --confirm-disable > /tmp/goreecloud-notes-disable-confirmed.txt
grep -F 'Disabled GoreeCloud Notes account: ci-user' /tmp/goreecloud-notes-disable-confirmed.txt
grep -F 'revoked 1 session(s)' /tmp/goreecloud-notes-disable-confirmed.txt

docker compose exec -T api python -m app.cli account-status \
  --username ci-user \
  --json > /tmp/goreecloud-notes-account-status-disabled.json
grep -F '"isActive":false' /tmp/goreecloud-notes-account-status-disabled.json
grep -F '"activeSessions":0' /tmp/goreecloud-notes-account-status-disabled.json

disabled_session_status=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_c" \
  --output /dev/null \
  --write-out '%{http_code}' \
  "$base_url/auth/me")
test "$disabled_session_status" = "401"

disabled_login_status=$(curl \
  --silent \
  --show-error \
  --output /tmp/goreecloud-notes-disabled-login.json \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"ci-user\",\"password\":\"$recovered_password\"}" \
  "$base_url/auth/login")
test "$disabled_login_status" = "401"
grep -F '"detail":"invalid username or password"' /tmp/goreecloud-notes-disabled-login.json
if grep -Eiq 'disabled|inactive|deactivated' /tmp/goreecloud-notes-disabled-login.json; then
  echo "disabled-account login disclosed lifecycle state" >&2
  exit 1
fi

docker compose exec -T api python -m app.cli enable-user \
  --username ci-user > /tmp/goreecloud-notes-enable.txt
grep -F 'Enabled GoreeCloud Notes account: ci-user' /tmp/goreecloud-notes-enable.txt
grep -F 'fresh sign-in required' /tmp/goreecloud-notes-enable.txt

docker compose exec -T api python -m app.cli account-status \
  --username ci-user \
  --json > /tmp/goreecloud-notes-account-status-reenabled.json
grep -F '"isActive":true' /tmp/goreecloud-notes-account-status-reenabled.json
grep -F '"activeSessions":0' /tmp/goreecloud-notes-account-status-reenabled.json

# Re-enabling must not resurrect the pre-disable browser cookie.
stale_after_reenable_status=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_c" \
  --output /dev/null \
  --write-out '%{http_code}' \
  "$base_url/auth/me")
test "$stale_after_reenable_status" = "401"

rm -f "$cookie_c"
reenabled_login_status=$(curl \
  --silent \
  --show-error \
  --cookie-jar "$cookie_c" \
  --output /tmp/goreecloud-notes-login-reenabled.json \
  --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --data "{\"username\":\"ci-user\",\"password\":\"$recovered_password\"}" \
  "$base_url/auth/login")
test "$reenabled_login_status" = "200"

csrf_c=$(awk '$6 == "goreecloud_notes_csrf" { print $7 }' "$cookie_c")
test -n "$csrf_c"

no_csrf_status=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_c" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --request POST \
  "$base_url/auth/logout")
test "$no_csrf_status" = "403"

logout_status=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_c" \
  --output /dev/null \
  --write-out '%{http_code}' \
  --header "X-CSRF-Token: $csrf_c" \
  --request POST \
  "$base_url/auth/logout")
test "$logout_status" = "204"

revoked_status=$(curl \
  --silent \
  --show-error \
  --cookie "$cookie_c" \
  --output /dev/null \
  --write-out '%{http_code}' \
  "$base_url/auth/me")
test "$revoked_status" = "401"
