#!/usr/bin/env bash
# Mirrors .github/workflows/ci.yml dry-run job for local / agent verification.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

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
  rm -f .env
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

for i in $(seq 1 30); do
  if docker compose exec -T app curl -s http://elasticsearch:9200 > /dev/null; then
    echo "Elasticsearch is available"
    break
  fi
  echo "Elasticsearch is unavailable - sleeping... $i"
  sleep 2
done

docker compose exec -T app poetry run python scripts/setup_indices.py --channel dummy-channel
docker compose exec -T app poetry run python scripts/import_kibana_objects.py --overwrite

docker compose exec -T app poetry run python -m src.cli fetch --dummy

docker compose exec -T app poetry run python -m src.cli report --type daily --channel dummy-channel --dry-run
docker compose exec -T app poetry run python -m src.cli report --type weekly --channel dummy-channel --dry-run

echo "e2e_compose_smoke: OK"
