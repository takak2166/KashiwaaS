# KashiwaaS Bot (`@kashiwaas`) and Cursor API

Mentioning `@kashiwaas` in Slack sends the question to the Cursor Cloud Agents API and posts replies in the thread. Bolt wiring lives in `src/bot/adapters/slack/app.py`; process entry is `src/bot/kashiwaas.py`. Cursor client construction is `src/bot/infra/cursor_client_factory.py` and `src/cursor/client.py`.

## Operational notes

- Configuration uses the same `apply_dotenv()` + `load_config()` as the CLI, only in the bot’s `main` (no global config at import time) — [runtime-config.md](runtime-config.md).
- For the full environment variable list, Slack App setup, and troubleshooting, treat [README.md](../README.md) **KashiwaaS Bot** as canonical; this page is an index.
- **Production platform:** Slack only ([production-cutover-runbook.md](production-cutover-runbook.md)).
- **ubuntu24 host deployment:** systemd units in [../deploy/README.md](../deploy/README.md) (`kashiwaas-valkey` + `kashiwaas-bot`). Run **one replica**.

## Start / stop / logs (systemd)

```bash
sudo systemctl start kashiwaas-bot
sudo systemctl stop kashiwaas-bot
sudo journalctl -u kashiwaas-bot -f
```

Valkey must be up first (`kashiwaas-valkey.service` or `docker compose up -d valkey`).

## Related environment variables (see README)

- `SLACK_APP_TOKEN`, `SLACK_BOT_TOKEN`: Socket Mode
- `CURSOR_API_KEY`, `CURSOR_ENV_TYPE`, `CURSOR_ENV_NAME`, `CURSOR_LAUNCH_MODE`, `CURSOR_POLL_*`, `CURSOR_MODEL`
- `VALKEY_URL`: thread → agent mapping (defaults to `redis://localhost:6379/0` if unset; override for Compose vs host systemd — see [deploy/README.md](../deploy/README.md))

## Valkey and `ThreadConversationRepository` wiring

- Slack thread (`thread_ts`) → Cursor agent id and last-assistant metadata are stored in **Valkey** (Redis protocol): see `src/bot/adapters/valkey/thread_conversation_repo.py` and domain aggregate `src/bot/domain/conversation.py`.
- `VALKEY_URL` and optional `VALKEY_THREAD_TTL_SECONDS` are loaded into `AppConfig.valkey` via `load_config()` (same pattern as other sub-configs; see [runtime-config.md](runtime-config.md)).
- `create_app(cfg)` in `src/bot/adapters/slack/app.py` constructs **one** `ValkeyThreadConversationRepository(cfg.valkey)` per process and passes it into `_handle_mention` (no module-level singleton). The Mattermost stack in `src/bot/adapters/mattermost/app.py` uses `ValkeyThreadConversationRepository(cfg.valkey, key_prefix="mm:")` for namespace separation. Tests inject `fakeredis` instead of a real Valkey connection.

## Concurrency and horizontal scaling

- Per-thread serialization uses `ThreadLockRegistry` inside `MentionHandlerService` (`src/bot/application/mention_service.py`). It is **process-local** (per Slack `thread_ts` / Mattermost composite thread key) and serializes handlers within one Python process only.
- Valkey state is shared across processes, but **multiple bot replicas** can still handle the same Slack thread concurrently; there is no distributed lock around the handler. For predictable one-thread-at-a-time behavior end-to-end, run **one bot replica** (or accept rare races if you scale the bot horizontally).
