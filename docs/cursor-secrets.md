# Cursor API keys and secrets (TAK-135)

KashiwaaS Bot on ubuntu24 uses a **personal User API key** to call the Cloud Agents API and route runs to My Machines workers.

## Key type

| Environment | Key type | Notes |
|-------------|----------|-------|
| Production (ubuntu24, `env.type=machine`) | **User API key** | e.g. dashboard key named `forKashiwaas` |
| Team pool (`env.type=pool`) | Service Account | **Not used** — pool is out of scope (see [private-worker.md](private-worker.md)) |

Generate keys: [Cursor Dashboard → Integrations / API Keys](https://cursor.com/dashboard/integrations).

Verify a key:

```bash
curl -u "$CURSOR_API_KEY:" https://api.cursor.com/v1/me
curl -u "$CURSOR_API_KEY:" "https://api.cursor.com/v0/private-workers?status=all&limit=5"
```

Both should return HTTP 200 for a valid user key with self-hosted access enabled.

## Placement on ubuntu24

| Secret | Location | Committed to git? |
|--------|----------|-------------------|
| `CURSOR_API_KEY` | Host `.env` (e.g. `/home/ubuntu/ghq/github.com/takak2166/KashiwaaS/.env`) | **No** — `.env` is gitignored |
| `SLACK_APP_TOKEN`, `SLACK_BOT_TOKEN` | Same `.env` | **No** |
| `VALKEY_URL` | Same `.env` (e.g. `redis://127.0.0.1:6379/0`) | **No** |

- Never commit API keys, tokens, or `.env` to the repository.
- Copy from [`.env.example`](../.env.example); fill values on the host only.
- For systemd, use `EnvironmentFile=/path/to/.env` (see [bot.md](bot.md)).

## 403 triage

When the Bot or curl receives **403 Forbidden**:

1. **Wrong key type** — Service Account keys start pool workers, not My Machines. Use a **user** API key for `machine`.
2. **Key expired or revoked** — Regenerate in the dashboard and update host `.env`; restart Bot.
3. **Self-hosted not allowed** — Team admin must enable *Allow Self-Hosted Machines* in Cloud Agents settings.
4. **Wrong `CURSOR_ENV_NAME`** — Must match the worker's internal label (`cursor-agent-worker-…`), not the UI display name.

## Related

- [private-worker.md](private-worker.md) — worker names and launch policy
- [runtime-config.md](runtime-config.md) — full environment variable list
