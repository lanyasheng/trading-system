# Moltbook Setup

## Description

Set up Moltbook login email for bot owners using Moltbook's real HTTP API.

## Usage

In Discord, send:
```
Set up my email for Moltbook login: your@email.com
```

or the short version:
```
setup-moltbook your@email.com
```

## Requirement

- `MOLTBOOK_API_KEY` environment variable (value starts with `moltbook_`)

## Response

- ✅ Success: Confirmation email sent
- ❌ Invalid email: Format error
- ⚠️ API error: actionable diagnostics returned

## API Endpoint

- URL: `POST https://www.moltbook.com/api/v1/agents/me/setup-owner-email`
- Auth: `Authorization: Bearer $MOLTBOOK_API_KEY`
- Body: `{"email": "user@example.com"}`

## Development

Script entrypoint:

```bash
bash scripts/setup_owner_email.sh your@email.com
```

## License

Internal skill for trading workspace.
