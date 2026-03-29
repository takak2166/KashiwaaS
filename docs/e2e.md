# Minimal E2E (Docker Compose)

This follows the same flow as the CI `dry-run` job: **bring the stack up**, then run `fetch` and `report` in dry-run mode. Selenium (browser) is used for weekly captures, etc.; this procedure first checks CLI + ES/Kibana health.

## Source of truth in CI

The `dry-run` job in [.github/workflows/ci.yml](../.github/workflows/ci.yml) is authoritative. Locally you can run the same steps via [scripts/e2e_compose_smoke.sh](../scripts/e2e_compose_smoke.sh).

## Local run

From the repository root:

```bash
make e2e-smoke
```

or:

```bash
bash scripts/e2e_compose_smoke.sh
```

Requires Docker and Docker Compose. On exit, Compose is torn down and the generated `.env` is removed.

## Step summary

1. Write a minimal `.env` and `docker compose up --build -d --wait`
2. Copy `.env` into the `app` container
3. Wait until Elasticsearch responds
4. Run `scripts/setup_indices.py` and `import_kibana_objects.py`
5. `python -m src.cli fetch --dummy`
6. `python -m src.cli report` with `--type daily` / `--type weekly` and `--dry-run`
7. Clean up: `docker compose down --rmi all --volumes --remove-orphans` and remove `.env`

## Selenium / Kibana

Kibana screenshots use `src/kibana/capture.py` and the Compose `chrome` service. For a first E2E step, the smoke above is often enough. Add browser-specific steps here if you need more.
