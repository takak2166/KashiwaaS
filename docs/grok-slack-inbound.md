# Slack Events → Grok inbound (TAK-167)

Separate **HTTP Events API** service (not Socket Mode). Avoids conflicting with the legacy KashiwaaS `bot` Socket Mode connection. Forwards `app_mention` events to Grok as canonical JSON; optional synchronous Grok JSON reply triggers `chat.postMessage` in the same `thread_ts`.

Entry point: `python -m src.grok.slack_inbound.main`

## Environment variables (names only)

| Variable | Required | Purpose |
|----------|----------|---------|
| `GROK_TARGET_URL` | yes | Grok routine webhook URL |
| `GROK_BEARER_TOKEN` | yes | Bearer for Grok webhook |
| `SLACK_SIGNING_SECRET` | yes | Verify Slack Events API requests |
| `SLACK_BOT_TOKEN` | for replies | `chat.postMessage` as @kashiwaas app |
| `PORT` / `LISTEN_PORT` | no | Default `8090` |

## Slack app setup (panel / API)

1. Create or use a **dedicated** Slack app for Grok inbound (do not reuse Socket Mode listener on the legacy bot while it runs).
2. Enable **Event Subscriptions**; Request URL: `https://<host>/slack/events`.
3. Subscribe to `app_mention` (and bot membership in target channels).
4. Install app to workspace; set `SLACK_BOT_TOKEN` and `SLACK_SIGNING_SECRET` in the 167 secret store.

## Grok panel (manual)

- Paste the system prompt from TAK-168 / Agent Store `internal/grok-routines/system-prompt-milestone1.md`.
- Configure the routine to consume canonical JSON and assemble the leading `[meta]` block per TAK-170.

## Dedup / idempotency (TAK-170 §6)

- Inbound: `team_id` + `event_id` (fallback `client_msg_id`, then `channel`+`ts`).
- Outbound visible reply: at most one `chat.postMessage` per trigger event id.

## Health

`GET /health` → `ok`

## Tests

`pytest tests/grok/test_slack_inbound.py` (mocked Grok + Slack WebClient).
