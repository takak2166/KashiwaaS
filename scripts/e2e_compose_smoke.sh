#!/usr/bin/env bash
# Mirrors .github/workflows/ci.yml dry-run job for local / agent verification.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# If a real .env exists, stash it so the smoke heredoc does not destroy it; restore in cleanup.
_ENV_BACKUP=""
if [[ -f .env ]]; then
  _ENV_BACKUP="$(mktemp)"
  cp .env "$_ENV_BACKUP"
fi

# Pick the same compose file for teardown that exists on disk (v1 name vs Compose v2 `compose.yml`).
_resolve_compose_file() {
  local f
  for f in docker-compose.yml compose.yml compose.yaml docker-compose.yaml; do
    if [[ -f "$f" ]]; then
      printf '%s' "$f"
      return 0
    fi
  done
  return 1
}

cleanup() {
  local compose_file
  if compose_file=$(_resolve_compose_file); then
    docker compose -f "$compose_file" down --rmi all --volumes --remove-orphans 2>/dev/null || true
  fi
  if [[ -n "${_ENV_BACKUP}" ]] && [[ -f "${_ENV_BACKUP}" ]]; then
    mv "$_ENV_BACKUP" .env
  else
    rm -f .env
  fi
}
trap cleanup EXIT

cat << EOF > .env
SLACK_CHANNEL_NAME=dummy-channel
ELASTICSEARCH_HOST=http://elasticsearch:9200
LOG_LEVEL=DEBUG
KIBANA_HOST=http://kibana:5601
SELENIUM_HOST=http://chrome:4444
EOF

docker compose up --build -d --wait
docker compose cp .env app:/app/.env
docker compose ps

ready=0
for i in $(seq 1 30); do
  if docker compose exec -T app curl -fsS http://elasticsearch:9200/ >/dev/null 2>&1; then
    echo "Elasticsearch is available"
    ready=1
    break
  fi
  echo "Elasticsearch is unavailable - sleeping... $i"
  sleep 2
done
if [[ "$ready" -ne 1 ]]; then
  echo "Elasticsearch did not become ready in time"
  docker compose ps
  exit 1
fi

kbn_ready=0
for i in $(seq 1 45); do
  if docker compose exec -T app curl -fsS http://kibana:5601/api/status >/dev/null 2>&1; then
    echo "Kibana is available"
    kbn_ready=1
    break
  fi
  echo "Kibana is unavailable - sleeping... $i"
  sleep 5
done
if [[ "$kbn_ready" -ne 1 ]]; then
  echo "Kibana did not become ready in time"
  docker compose ps
  exit 1
fi

docker compose exec -T app poetry run python scripts/setup_indices.py --channel dummy-channel
docker compose exec -T app poetry run python scripts/import_kibana_objects.py --overwrite

docker compose exec -T app poetry run python -m src.cli fetch --dummy

docker compose exec -T app poetry run python -m src.cli report --type daily --channel dummy-channel --dry-run
docker compose exec -T app poetry run python -m src.cli report --type weekly --channel dummy-channel --dry-run

echo "e2e_compose_smoke: OK"
