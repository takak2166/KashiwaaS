# Mattermost → Grok HTTPS relay

Mattermost Outgoing Webhook cannot send `Authorization: Bearer`. This service accepts MM webhooks, validates shared secrets, normalizes **canonical JSON**, and POSTs to the Grok routine webhook with Bearer auth. **Does not** return chat text in the MM webhook HTTP response body.

Entry point: `python -m src.grok.mattermost_relay.main`

## Environment variables (names only)

| Variable | Required | Purpose |
|----------|----------|---------|
| `GROK_TARGET_URL` | yes | Grok routine webhook URL |
| `GROK_BEARER_TOKEN` | yes | Grok webhook Bearer key (same as Grok panel `key`) |
| `RELAY_SHARED_SECRET` | yes | Query/header secret on relay URL |
| `MM_OUTGOING_WEBHOOK_TOKEN` | yes | Must match MM outgoing webhook `token` field |
| `PORT` / `LISTEN_PORT` | no | Default `8080` |
| `LISTEN_HOST` | no | Default `0.0.0.0` |
| `MAX_BODY_BYTES` | no | Default 262144 |
| `INBOUND_DEDUP_TTL_SECONDS` | no | Dedup window for `post_id` (+ optional `trigger_id`) |

Server-side **correlation** (`post_id` → `channel_id` + `thread_id`) is kept in-process for Bot PAT replies; outbound PAT posting is coordinated separately.

## TLS and callback URL

Deploy behind a **TLS-terminating reverse proxy** (HTTPS only on the public URL). Mattermost must POST to:

`https://<relay-host>/mm?secret=<RELAY_SHARED_SECRET>` (POST, JSON or form body).

Access logs must not record the query `secret`; the relay strips query strings from its own request log path.

## Health

`GET /health` or `GET /healthz` → `ok`

## Alerts

Wire process health and 5xx rates to existing KashiwaaS alerter / platform monitoring when deployed (no secrets in logs).

## Tests

`pytest tests/grok/test_mattermost_relay.py` (mocked Grok forwarder, no network).
