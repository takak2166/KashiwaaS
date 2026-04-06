# KashiwaaS Bot (`@kashiwaas`) and Cursor API

Mentioning `@kashiwaas` in Slack sends the question to the Cursor Cloud Agents API and posts replies in the thread. See `src/bot/kashiwaas.py` and `src/cursor/client.py`.

## Operational notes

- Configuration uses the same `apply_dotenv()` + `load_config()` as the CLI, only in the bot’s `main` (no global config at import time) — [runtime-config.md](runtime-config.md).
- For the full environment variable list, Slack App setup, and troubleshooting, treat [README.md](../README.md) **KashiwaaS Bot** as canonical; this page is an index.

## Related environment variables (see README)

- `SLACK_APP_TOKEN`, `SLACK_BOT_TOKEN`: Socket Mode
- `CURSOR_API_KEY`, `CURSOR_SOURCE_REPOSITORY`, `CURSOR_POLL_INTERVAL`, `CURSOR_POLL_TIMEOUT`, `CURSOR_MODEL`

## Valkey and `ThreadStore` wiring

- Slack thread (`thread_ts`) → Cursor agent id is stored in **Valkey** (Redis protocol): see `src/bot/thread_store.py`.
- `VALKEY_URL` and optional `VALKEY_THREAD_TTL_SECONDS` are loaded into `AppConfig.valkey` via `load_config()` (same pattern as other sub-configs; see [runtime-config.md](runtime-config.md)).
- `create_app(cfg)` in `src/bot/kashiwaas.py` constructs **one** `ThreadStore(cfg.valkey)` per process and passes it into `_handle_mention` (no module-level singleton). Tests inject a `ThreadStore` with `fakeredis` instead of a real Valkey connection.
