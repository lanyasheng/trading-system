#!/usr/bin/env bash
set -euo pipefail

submolt="${1:-general}"
title="${2:-}"
content="${3:-}"

if [[ -z "$title" || -z "$content" ]]; then
  echo "ERR Missing args"
  echo "Usage: create_post.sh <submolt> <title> <content>"
  exit 2
fi

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

payload="$(python3 - "$submolt" "$title" "$content" <<'PY'
import json,sys
print(json.dumps({"submolt": sys.argv[1], "title": sys.argv[2], "content": sys.argv[3]}, ensure_ascii=False))
PY
)"

resp="$(curl -sS -w '\nHTTP_STATUS:%{http_code}\n' \
  -X POST 'https://www.moltbook.com/api/v1/posts' \
  -H "Authorization: Bearer ${api_key}" \
  -H 'Content-Type: application/json' \
  --data "$payload")"

body="$(printf '%s' "$resp" | sed '/^HTTP_STATUS:/d')"
status="$(printf '%s' "$resp" | awk -F: '/^HTTP_STATUS:/{print $2}')"

echo "HTTP_STATUS:${status}"
echo "$body"

if [[ "$status" -ge 200 && "$status" -lt 300 ]]; then
  exit 0
fi
exit 1
