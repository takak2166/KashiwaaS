# Configuration and security

## Loading configuration (`AppConfig`)

- `.env` is loaded via `apply_dotenv()`; `load_config()` builds settings from the environment in **only** the **CLI** (`python -m src.cli`) and **bot** (`python -m src.bot.kashiwaas`) `main` functions. There is no global `config` singleton at import time.
- `init_alerter(AppConfig)` sets up in-process alerts (optional Slack channel). `ElasticsearchClient`, `SlackClient`, and `KibanaCapture` take the relevant sub-config from `AppConfig` in their constructors.
- Daily and weekly aggregates are represented as `DailyStats` / `WeeklyStats` (`src/analysis/types.py`); report formatting consumes these types.

## Security requirements

### Credential management

- Slack API keys and Elasticsearch credentials live in environment variables (`.env`):
  ```
  # Example .env
  SLACK_API_TOKEN=xoxb-xxxxxxxxxxxx-xxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxx
  SLACK_CHANNEL_ID=C12345678
  ELASTICSEARCH_HOST=http://elasticsearch:9200
  ELASTICSEARCH_USER=elastic
  ELASTICSEARCH_PASSWORD=changeme
  ```
- Add `.env` to `.gitignore`
- In production, prefer Docker secrets or Kubernetes secrets

### Access control

- Grant Slack API tokens only the minimum scopes needed:
  - `channels:history`
  - `channels:read`
  - `chat:write`
- Enable Elasticsearch X-Pack Security in production
