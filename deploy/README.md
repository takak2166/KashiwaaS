# ubuntu24 deployment (systemd)

Host paths assume repo at `/home/ubuntu/ghq/github.com/takak2166/KashiwaaS` and user `ubuntu`. Adjust `WorkingDirectory`, `User`, and `EnvironmentFile` if your layout differs.

## Install

```bash
cd /home/ubuntu/ghq/github.com/takak2166/KashiwaaS
poetry install --no-interaction

# Host .env (never commit) — see docs/cursor-secrets.md
cp .env.example .env
# Edit: SLACK_*, CURSOR_*, VALKEY_URL=redis://127.0.0.1:6379/0

sudo cp deploy/systemd/kashiwaas-valkey.service /etc/systemd/system/
sudo cp deploy/systemd/kashiwaas-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kashiwaas-valkey.service
sudo systemctl enable --now kashiwaas-bot.service
```

## Operations

```bash
sudo systemctl status kashiwaas-bot kashiwaas-valkey
sudo journalctl -u kashiwaas-bot -f
sudo systemctl restart kashiwaas-bot
sudo systemctl stop kashiwaas-bot
```

## Valkey

The `valkey` Compose service binds **`127.0.0.1:6379`** only (not all interfaces). The Bot unit sets `VALKEY_URL=redis://127.0.0.1:6379/0` so a host-run Bot reaches the container.

## Replica count

Run **one** `kashiwaas-bot` instance. See [bot.md](../docs/bot.md) concurrency notes.

## Secrets

Follow [cursor-secrets.md](../docs/cursor-secrets.md). Production Cursor settings: [production-cutover-runbook.md](../docs/production-cutover-runbook.md).
