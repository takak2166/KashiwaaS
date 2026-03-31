# Features, data, schedules, and errors

## 3. Functional specification

### Data ingestion

- Fetch posts from a Slack channel for a given time range:
  ```python
  # Slack API methods used
  conversations.history(channel_id, oldest, latest, limit, inclusive)
  conversations.replies(channel_id, ts, limit)
  ```
- Include thread replies in the full post set
- Paginate to handle large volumes reliably
- Fields captured:
  - Message body
  - Author (ID, name)
  - Timestamps
  - Reactions (type, count, users)
  - Thread metadata (parent ts, reply count)
  - Mentions
  - Attachments (type, size, URL)

### Data storage

- Persist fetched data in Elasticsearch
- Bulk insert for efficiency
- One Slack channel maps to one index
- Index template:
  ```json
  {
    "index_patterns": ["slack-*"],
    "priority": 100,
    "version": 1,
    "_meta": {
      "description": "Template for Slack messages"
    },
    "template": {
      "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
          "analyzer": {
            "kuromoji_analyzer": {
              "type": "custom",
              "tokenizer": "kuromoji_tokenizer",
              "filter": ["kuromoji_baseform", "lowercase", "ja_stop", "kuromoji_part_of_speech"]
            }
          }
        }
      },
      "mappings": {
        "properties": {
          "timestamp": { "type": "date" },
          "channel_id": { "type": "keyword" },
          "user_id": { "type": "keyword" },
          "username": { "type": "keyword" },
          "text": {
            "type": "text",
            "analyzer": "kuromoji_analyzer",
            "fielddata": true,
            "fields": {
              "keyword": { "type": "keyword", "ignore_above": 256 }
            }
          },
          "thread_ts": { "type": "keyword" },
          "reply_count": { "type": "integer" },
          "reactions": {
            "type": "nested",
            "properties": {
              "name": { "type": "keyword" },
              "count": { "type": "integer" },
              "users": { "type": "keyword" }
            }
          },
          "mentions": { "type": "keyword" },
          "attachments": {
            "type": "nested",
            "properties": {
              "type": { "type": "keyword" },
              "size": { "type": "long" },
              "url": { "type": "keyword" }
            }
          },
          "is_weekend": { "type": "boolean" },
          "hour_of_day": { "type": "integer" },
          "day_of_week": { "type": "integer" }
        }
      }
    }
  }
  ```

### Reports and posting

- Daily report:
  - Total posts and reactions for the previous day
  - Hourly post distribution chart

- Weekly report (from Kibana-driven assets):
  - Weekly post trend (weekdays only / all days)
  - Top 3 posts by reactions
  - Tag cloud (nouns via kuromoji)
  - Charts from Kibana loaded with Selenium WebDriver and exported to PNG
  - Fixed output filenames (overwrite each run):
    - Dashboard screenshot: `kibana_weekly_dashboard.png`
    - Weekly hourly chart: `hourly_weekly.png`
    - Reaction pie chart: `reaction_pie_weekly.png`

## 4. Data model

### Elasticsearch index design

- Index naming: `slack-{channel_name}`
- Shards: 1 (small/medium data)
- Replicas: 0 (dev) / 1 (prod)
- Refresh interval: 1s (default)
- Time-series data keyed by timestamp
- Japanese text analysis via kuromoji plugin

## 5. Schedules

### Ingestion frequency

- Once per weekday at 06:00 (skip weekends); example crontab:
  ```
  # Example crontab
  0 6 * * 1-5 /app/run_data_collector.sh >> /var/log/collector.log 2>&1
  ```
- Separate script for bulk historical backfill:
  ```python
  # Pseudocode
  def fetch_historical_data(channel_id, start_date, end_date):
      start_ts = convert_to_timestamp(start_date)
      end_ts = convert_to_timestamp(end_date)
      # Split by day
      current_ts = start_ts
      while current_ts < end_ts:
          next_ts = current_ts + 86400  # one day in seconds
          fetch_and_store_messages(channel_id, current_ts, next_ts)
          current_ts = next_ts
  ```

### Report posting frequency

- Daily: weekdays 08:00 JST for the previous day
- Weekly: Mondays 08:05 JST for the previous week

## 6. Error handling

### Retry policy

- On request failure, retry with exponential backoff:
  ```python
  def retry_with_backoff(func, max_retries=5, initial_backoff=1.0):
      retries = 0
      while retries < max_retries:
          try:
              return func()
          except Exception as e:
              wait_time = initial_backoff * (2 ** retries)
              logger.warning(f"Retry {retries+1}/{max_retries} after {wait_time}s due to {str(e)}")
              time.sleep(wait_time)
              retries += 1
      raise Exception(f"Failed after {max_retries} retries")
  ```
- Respect Slack API rate limits (Tier 3: 50+ per minute)
- Up to 5 retries; then fail and alert
- `get_channel_info`: 3 retries; `conversations_history` / `conversations_replies`: 5 retries

### Exceptions

- Network errors: retry
- Auth errors: exit immediately and alert
- Data inconsistencies: log and skip
- Elasticsearch write errors: buffer and retry later
- Use `is_temporary_error` to classify transient failures

### Logging

- Levels: DEBUG, INFO, WARNING, ERROR
- Format: `{timestamp} {level} {module}:{line} - {message}`
- Rotation: daily, 7-day retention
- Critical errors also go to a Slack alert channel
