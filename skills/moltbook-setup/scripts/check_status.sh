#!/usr/bin/env bash
set -euo pipefail

api_key="${MOLTBOOK_API_KEY:-}"
if [[ -z "$api_key" ]]; then
  key_file="${OPENCLAW_HOME:-$HOME/.openclaw}/credentials/moltbook_api_key"
  [[ -f "$key_file" ]] || key_file="$HOME/.openclaw/credentials/moltbook_api_key"
  [[ -f "$key_file" ]] && api_key="$(tr -d '[:space:]' < "$key_file")"
fi

if [[ -z "$api_key" ]]; then
  echo "ERR MOLTBOOK_API_KEY is not set"
  exit 3
fi

resp="$(curl -sS -w '\nHTTP_STATUS:%{http_code}\n' \
  'https://www.moltbook.com/api/v1/agents/status' \
  -H "Authorization: Bearer ${api_key}")"

body="$(printf '%s' "$resp" | sed '/^HTTP_STATUS:/d')"
status="$(printf '%s' "$resp" | awk -F: '/^HTTP_STATUS:/{print $2}')"

echo "HTTP_STATUS:${status}"
echo "$body"

if [[ "$status" -ge 200 && "$status" -lt 300 ]]; then
  exit 0
fi
exit 1
