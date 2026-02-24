#!/usr/bin/env bash
set -euo pipefail

email="${1:-}"
if [[ -z "$email" ]]; then
  echo "ERR Missing email argument"
  echo "Usage: setup_owner_email.sh user@example.com"
  exit 2
fi

if [[ ! "$email" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]]; then
  echo "ERR Invalid email format: $email"
  exit 2
fi

api_key="${MOLTBOOK_API_KEY:-}"
if [[ -z "$api_key" ]]; then
  default_key_file="${OPENCLAW_HOME:-$HOME/.openclaw}/credentials/moltbook_api_key"
  if [[ ! -f "$default_key_file" && -f "$HOME/.openclaw/credentials/moltbook_api_key" ]]; then
    default_key_file="$HOME/.openclaw/credentials/moltbook_api_key"
  fi
  if [[ -f "$default_key_file" ]]; then
    api_key="$(tr -d '[:space:]' < "$default_key_file")"
  fi
fi

if [[ -z "$api_key" ]]; then
  echo "ERR MOLTBOOK_API_KEY is not set"
  echo "Hint 1: export MOLTBOOK_API_KEY='moltbook_xxx'"
  echo "Hint 2: put key in ~/.openclaw/credentials/moltbook_api_key"
  exit 3
fi

resp="$(curl -sS -w '\nHTTP_STATUS:%{http_code}\n' \
  -X POST 'https://www.moltbook.com/api/v1/agents/me/setup-owner-email' \
  -H "Authorization: Bearer ${api_key}" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${email}\"}")"

body="$(printf '%s' "$resp" | sed '/^HTTP_STATUS:/d')"
status="$(printf '%s' "$resp" | awk -F: '/^HTTP_STATUS:/{print $2}')"

echo "HTTP_STATUS:${status}"
echo "$body"

if [[ "$status" -ge 200 && "$status" -lt 300 ]]; then
  exit 0
fi
exit 1
