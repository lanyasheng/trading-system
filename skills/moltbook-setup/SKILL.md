---
name: moltbook-setup
description: Set up Moltbook owner email by calling Moltbook's real API. Trigger when the user says "setup-moltbook <email>" or "Set up my email for Moltbook login: <email>".
---

# Moltbook Setup Skill

Use this skill to set owner email for Moltbook login.

## Trigger

- `setup-moltbook your@email.com`
- `Set up my email for Moltbook login: your@email.com`

## Required Secret

- `MOLTBOOK_API_KEY` (must start with `moltbook_`)

Do not use `OPENCLAW` gateway token for Moltbook API. They are different systems.

## API

- Endpoint: `https://www.moltbook.com/api/v1/agents/me/setup-owner-email`
- Method: `POST`
- Header: `Authorization: Bearer $MOLTBOOK_API_KEY`
- Body: `{"email":"user@example.com"}`

## Execution

1. Parse email from user message.
2. Validate basic email format.
3. If `MOLTBOOK_API_KEY` is missing, tell user to provide/import it first.
4. Run:

```bash
bash scripts/setup_owner_email.sh user@example.com
```

5. Return concise result:
- success: tell user to check inbox and verify X account
- 401: API key missing/invalid
- other errors: include API message and next action

## Guardrails

- Never call `moltbook` CLI unless it is actually installed.
- Never call `http://localhost:18789/api/v1/agents/me/setup-owner-email` (wrong host for this API).
