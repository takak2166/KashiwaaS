# Testing and verification

## 9. Testing requirements

### Unit tests

- Coverage target: 80%+
- Automated tests with pytest
- Scope:
  - Data models
  - Business logic
  - Utility functions
- API calls tested with mocks

### Integration tests

- E2E-style tests in a Docker Compose environment
- Validation with small sample datasets

### Debugging and monitoring

- Verbose logging
  ```python
  from loguru import logger
  
  # Log setup
  logger.add("logs/app.log", rotation="1 day", retention="7 days", level="INFO")
  
  # Examples
  logger.info("Processing channel {}", channel_id)
  logger.debug("Raw API response: {}", response)
  logger.error("Failed to connect to Elasticsearch: {}", err)
  ```
- Metrics (processing time, volume, etc.)
- Health-check endpoints (where applicable)

## Local and CI

- Local: `make test` (`pytest`), `make lint` (`ruff`) — [Makefile](../Makefile)
- PRs to `main`: GitHub Actions runs `lint_and_test` (`make lint` / `make test`) and `dry-run` (Docker Compose) — [.github/workflows/ci.yml](../.github/workflows/ci.yml)

## Cursor agent hooks

- `.cursor/hooks.json`: `ruff` after edits (`afterFileEdit`), full `pytest` before completion (`stop`, `failClosed`). Hook scripts live under `.claude/hooks/`.

### preToolUse (safety guard)

- `.claude/hooks/pre-tool-use-guard.sh` → `pre_tool_use_guard.py`: blocks dangerous shell commands (e.g. `git push --force`, `rm -rf`, `--no-verify`), writes to `.env` (except `.env.example`), sensitive repository paths, and key material paths. Uses `failClosed: true` so hook failures do not allow the action.

## Stack E2E

See [e2e.md](e2e.md) for bringing Compose up and running the smoke flow.
