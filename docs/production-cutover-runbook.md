# Production cutover runbook (TAK-137)

Switch KashiwaaS Bot from legacy **cloud / v0 repo** launches to **ubuntu24 My Machines** (v1 API).

**Chat platform (canonical):** Slack only.

## Production configuration (fixed)

Set these in host `.env` before cutover:

```bash
CURSOR_ENV_TYPE=machine
CURSOR_ENV_NAME=<your-machine-env-name>
CURSOR_LAUNCH_MODE=env_only
CURSOR_AUTO_CREATE_PR=false
```

See [private-worker.md](private-worker.md) for display name mapping and worker verification.

## Pre-cutover checklist

- [ ] [TAK-136 Phase 1](private-worker-e2e.md) curl E2E **PASS**
- [ ] Bot + Valkey running on ubuntu24 ([bot.md](bot.md))
- [ ] `CURSOR_API_KEY` is **user** key ([cursor-secrets.md](cursor-secrets.md))
- [ ] Worker connected ([private-worker.md](private-worker.md) health check)

## Cutover procedure

1. **Update `.env`** on ubuntu24 with the four production values above (plus existing Slack / Valkey vars).
2. **Restart Bot** (systemd or compose):
   ```bash
   sudo systemctl restart kashiwaas-bot
   # or: docker compose restart bot valkey
   ```
3. **Verify Phase 0** — worker still connected (`curl` private-workers).
4. **Slack smoke test** — `@kashiwaas` new thread, then one follow-up in the same thread.
5. **Monitor logs** — confirm log lines show `env_only` / machine worker, v1 run ids.

## Rollback procedure

Rollback if: Phase 1 fails after cutover, Worker unavailable >15 min, or error rate on Slack mentions is unacceptable.

1. **Stop Bot** to prevent new v1 launches:
   ```bash
   sudo systemctl stop kashiwaas-bot
   ```
2. **Restore previous `.env`** from backup (pre-cutover snapshot). Edit the file to remove machine routing:
   ```bash
   # Remove or comment out:
   # CURSOR_ENV_TYPE=machine
   # CURSOR_ENV_NAME=...
   # Set legacy repo mode if rolling back to an older release:
   CURSOR_LAUNCH_MODE=repo
   ```
   Note: v0 API was removed in TAK-134; rollback to cloud requires checking out a pre-migration release tag if still needed.
3. **Clear Valkey thread keys** (optional, if stale agent ids cause confusion):
   ```bash
   docker compose exec -T valkey valkey-cli --scan --pattern 'kashiwaas:thread:*' | \
     xargs -r docker compose exec -T valkey valkey-cli DEL
   ```
4. **Restart Bot** on rollback config and post in Slack that mentions may need fresh threads.

## Legacy cloud / v0 path

| Decision | Detail |
|----------|--------|
| **Bot legacy v0 launch path in code** | Removed (TAK-134). No dual-path in main branch. Manual `GET /v0/private-workers` health checks remain valid. |
| **Cloud VM launches** | Disabled for production Bot once cutover completes. |
| **Emergency cloud use** | Manual via Cursor dashboard only; Bot does not target cloud. |

## Post-cutover

- Archive old cloud-only env vars from runbooks.
- Keep [private-worker-e2e.md](private-worker-e2e.md) as regression checklist after Worker or Bot upgrades.

## Related

- [private-worker.md](private-worker.md)
- [private-worker-e2e.md](private-worker-e2e.md)
- [cursor-secrets.md](cursor-secrets.md)
