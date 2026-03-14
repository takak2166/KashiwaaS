# AGENTS.md

## Cursor Cloud specific instructions

### Overview

KashiwaaS is a Slack message analysis/visualization system using Python 3.12, Poetry 2.1.1, Elasticsearch 8.17.2, Kibana 8.17.2, and Selenium Chrome. See `README.md` for full details.

### Lint / Test / Build

- **Lint**: `make lint` (runs black, isort, flake8 via Poetry)
- **Test**: `make test` (runs pytest via Poetry)
- Tests run outside Docker. One integration test (`test_connection`) requires a live Elasticsearch; it is skipped when `ELASTICSEARCH_HOST` is not set. If `.env` is present with `ELASTICSEARCH_HOST=http://elasticsearch:9200`, that test will fail on the host because `elasticsearch` is only resolvable inside the Docker network.

### Running the full stack (Docker Compose)

Standard commands from `README.md` and `.github/workflows/ci.yml`:

```bash
cp .env.example .env   # edit as needed, or use dummy values for dry-run
sudo docker compose up --build -d
sudo docker compose exec app poetry run python scripts/setup_indices.py --channel dummy-channel
sudo docker compose exec app poetry run python scripts/import_kibana_objects.py --overwrite
```

Dry-run commands (no Slack token needed):

```bash
sudo docker compose exec app poetry run python src/main.py fetch --dummy
sudo docker compose exec app poetry run python src/main.py report --type daily --channel dummy-channel --dry-run
sudo docker compose exec app poetry run python src/main.py report --type weekly --channel dummy-channel --dry-run
```

### Gotchas

- Docker requires `sudo` in the Cloud VM environment.
- Docker daemon must be started manually: `sudo dockerd &>/tmp/dockerd.log &` (wait ~5s before using).
- Docker storage driver is `fuse-overlayfs` and iptables is set to `iptables-legacy` for DinD compatibility.
- The `docker-compose.yml` `version` key triggers a warning; this is harmless.
- Elasticsearch takes a few seconds to become ready after `docker compose up`. Wait for it before running setup scripts.
- Kibana is accessible at `http://localhost:5601`, Elasticsearch at `http://localhost:9200`.
- `poetry` binary is at `~/.local/bin/poetry`; ensure `~/.local/bin` is on `PATH`.
