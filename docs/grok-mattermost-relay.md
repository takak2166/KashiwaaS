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

## Thread ID derivation

Canonical `thread_id` is derived from the webhook payload only — no Mattermost API lookup is performed:

- `root_id` present → `thread_id = root_id` (reply joins the parent thread context).
- `root_id` absent → `thread_id = post_id` (top-level post starts a new thread context; `post_id` falls back to `id` if missing).

Edge cases — thread context split:

- If MM omits `root_id` on a reply (payload variant / webhook config), that reply opens a new thread context. One MM thread can therefore map to multiple canonical `thread_id`s; no repair fetch is attempted.
- `root_id` may reference a root post the relay never received (e.g. only the reply matched the trigger word). Downstream must handle threads whose root was never ingested.
- If both `root_id` and `post_id`/`id` are missing, `thread_id` is empty and omitted from the canonical JSON.
- Inbound dedup keys on `post_id` (+ optional `trigger_id`), not `thread_id`; webhook retries keep the same thread.

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
