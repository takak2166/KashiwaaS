# Slack Events → Grok inbound

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
| `SLACK_GROK_FORWARD_MAX_WORKERS` | no | Max concurrent Grok forwards after Slack ACK (default `4`) |

## Slack app setup (panel / API)

1. Create or use a **dedicated** Slack app for Grok inbound (do not reuse Socket Mode listener on the legacy bot while it runs).
2. Enable **Event Subscriptions**; Request URL: `https://<host>/slack/events`.
3. Subscribe to `app_mention` (and bot membership in target channels).
4. Install app to workspace; set `SLACK_BOT_TOKEN` and `SLACK_SIGNING_SECRET` in the deployment secret store.
5. Bot token OAuth scopes: **`app_mentions:read`**, **`chat:write`**.

## Grok panel (manual)

- Paste the system prompt from Agent Store `internal/grok-routines/system-prompt-milestone1.md`.
- Configure the routine to consume canonical JSON and assemble the leading `[meta]` block per the canonical schema docs.

## Dedup / idempotency

- Inbound: `team_id` + `event_id` (fallback `client_msg_id`, then `channel`+`ts`).
- Outbound visible reply: at most one `chat.postMessage` per trigger event id.

## Delivery reliability (Milestone 1)

Slack Events API treats an HTTP **2xx** response as successful delivery. **Slack does not retry** the same event delivery after a successful response.

This service **ACKs with 200 immediately** after signature verification and inbound dedup reservation, then forwards to Grok on a **bounded thread pool** (`SLACK_GROK_FORWARD_MAX_WORKERS`, default 4). That ordering satisfies Slack’s short response deadline (~3 seconds) but implies a deliberate M1 trade-off:

- If Grok forward fails **after** the ACK (transport error or non-2xx HTTP), the `app_mention` may be **silently lost** from Grok’s perspective. Slack will not redeliver because it already saw success.
- On forward failure the service calls `inbound_dedup.forget` so a **rare** Slack redelivery of the same payload could be processed again; that does **not** cause Slack to retry.

**Out of M1 scope:** durable queues, internal retry workers, blocking until Grok completes before ACK, or synchronous forward in the request thread (would exceed Slack’s deadline).

## Operations (logs)

Logger name: `slack-grok-inbound` (default level INFO via `main`).

| Level | When | What to alert on |
|-------|------|------------------|
| **ERROR** | Grok forward failed after Slack ACK | `grok forward failed after slack ack event_id=…` — correlate with `event_id`, `key`, `transport`, `status`; indicates a mention that Slack will not retry |
| WARNING | `chat.postMessage` failed (or retry failed) | `slack thread reply failed` / `slack thread reply retry failed` — Grok may have succeeded; dedup kept for reply-only retry on duplicate delivery |
| INFO | Happy path / benign skip | `forwarded slack inbound`, `duplicate slack inbound`, `bot-authored slack inbound skipped` |

## Concurrency (Milestone 1)

The service uses Python’s stock **single-thread** `HTTPServer`: one request is handled at a time on the listening port. This is intentional for M1 (no `ThreadingHTTPServer`, no durable work queue).

- **Slow clients:** Inbound POST bodies are read with a **socket read timeout** (default 30s, separate from the Grok forward HTTP client timeout, typically 60s). Clients that stall while sending the body get `408` and release the worker thread.
- **While a request is in flight** on the HTTP thread (signature verification, dedup, and the immediate Slack 200 ACK), **other connections wait**, including `GET /health`. Grok forwards run on a **bounded pool** after ACK; they do not occupy the HTTP thread, but bursts queue in FIFO order until a worker is free (**queue-wait**, not reject+log). If the pool is shut down during deploy, new submits are **rejected** (dedup cleared, ERROR log).
- **Production:** Put a **reverse proxy** in front (TLS termination, request body buffering, and proxy read/send timeouts). `ThreadingHTTPServer` remains out of M1 scope; tune `SLACK_GROK_FORWARD_MAX_WORKERS` for expected mention rate.

## Health

`GET /health` → `ok`

## Tests

`pytest tests/grok/test_slack_inbound.py` (mocked Grok + Slack WebClient).
