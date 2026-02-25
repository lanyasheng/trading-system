# GitHub Ops

## Capability

Use `openclaw-github-assistant` skill for repository operations (including create repo).

## Credentials

Required (one of these locations):

1. OpenClaw config `~/.openclaw/openclaw.json`:
```json
{
  "github": {
    "username": "YOUR_GITHUB_USERNAME",
    "token": "YOUR_GITHUB_PAT"
  }
}
```

2. Environment variables (fallback):
- `GITHUB_USERNAME`
- `GITHUB_TOKEN`

## PAT scopes (minimum)

- `repo` (for private/public repo create + issue ops)
- `read:user`

## Validation checklist

1. Verify auth by calling GitHub API through skill (`list_repos`).
2. Test create repo with a temporary private repository.
3. Report created URL back to user.
