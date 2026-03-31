# Architecture

Project overview, tech stack, and development environment (Docker Compose excerpt). For **how configuration and secrets are loaded**, see [runtime-config.md](runtime-config.md).

## 1. Project overview

### Goals

Build a system that stores messages from a given Slack channel in Elasticsearch and analyzes and visualizes them, so the team can understand communication patterns and improve engagement.

### Problems addressed

- Analyze channel communication trends over time
- Visualize stats such as post and reaction counts
- Detect and notify on communication trends automatically
- Post statistics to the channel on a schedule

### Expected deliverables

1. Slack data collection
2. Elasticsearch storage
3. Statistical analysis and reporting
4. Slack notification bot
5. Kibana dashboard definitions

## 2. Technical requirements

### Language and tooling

- Language: Python 3.12+ (per `requires-python` in `pyproject.toml`)
- Package manager: Poetry 2.1.0+

### Libraries

- slack-sdk
- slack-bolt
- elasticsearch
- selenium
- python-dotenv
- requests
- pytest
- loguru
- ruff
- pytz
- matplotlib
- numpy
- jinja2
- pandas
- plotly
- kaleido

### Development environment

- Docker Compose layout (must match `docker-compose.yml`; files in the repo are canonical):
  ```yaml
  version: '3.8'
  services:
    app:
      build: .
      volumes:
        - ./:/app
      environment:
        - TZ=Asia/Tokyo
      depends_on:
        - elasticsearch

    elasticsearch:
      build: ./elasticsearch
      environment:
        - discovery.type=single-node
        - "ES_JAVA_OPTS=-Xms1g -Xmx1g"
        - xpack.security.enabled=false
      volumes:
        - es_data:/usr/share/elasticsearch/data
      ports:
        - "9200:9200"

    kibana:
      image: docker.elastic.co/kibana/kibana:8.19.13
      environment:
        - ELASTICSEARCH_HOSTS=http://elasticsearch:9200
      ports:
        - "5601:5601"
      depends_on:
        - elasticsearch

    chrome:
      image: selenium/standalone-chrome:latest
      ports:
        - "4444:4444"
      environment:
        - SE_NODE_MAX_SESSIONS=4
      shm_size: '2g'

    bot:
      build: .
      command: ["poetry", "run", "python", "-m", "src.bot.kashiwaas"]
      environment:
        - TZ=Asia/Tokyo
      env_file:
        - .env
      restart: unless-stopped

  volumes:
    es_data:
  ```

## 8. Code structure

### Layout

```
project/
├── pyproject.toml           # Poetry
├── .gitignore               # Git ignore rules
├── .env.example             # Sample env
├── README.md                # Project overview
├── Dockerfile               # App image
├── docker-compose.yml       # Compose stack
├── crontab
├── docker-entrypoint.sh
├── elasticsearch
│   └── Dockerfile
├── docs
│   ├── README.md            # Design doc index
│   ├── architecture.md
│   ├── runtime-config.md
│   ├── features.md
│   ├── testing.md
│   ├── operations.md
│   ├── bot.md
│   └── e2e.md
├── kibana
│   ├── dashboards
│   └── templates
│       ├── dashboard.ndjson.j2
│       ├── index_pattern.ndjson.j2
│       └── lens.ndjson.j2
├── src/
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── main.py          # Entry: subcommand dispatch
│   │   ├── args.py          # argparse
│   │   ├── fetch_cmd.py     # fetch
│   │   ├── report_cmd.py    # report
│   │   └── fetch_pipeline.py
│   ├── slack/
│   │   ├── __init__.py
│   │   ├── client.py        # Slack API
│   │   └── message.py       # Message models
│   ├── es_client/
│   │   ├── __init__.py
│   │   ├── client.py        # ES client
│   │   ├── index.py         # Index definitions
│   │   └── query.py         # Query builders
│   ├── kibana/
│   │   ├── __init__.py
│   │   ├── capture.py
│   │   └── dashboard.py
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── daily.py         # Daily analysis
│   │   ├── weekly.py        # Weekly analysis
│   │   └── visualization.py # Charts
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── alerter.py
│   │   ├── reporter.py      # Scheduled reports
│   │   ├── kashiwaas.py     # KashiwaaS bot (Socket Mode)
│   │   ├── thread_store.py
│   │   ├── utils.py
│   │   └── formatter.py     # Message formatting
│   ├── cursor/
│   │   └── client.py        # Cursor Cloud Agents API
│   └── utils/
│       ├── __init__.py
│       ├── logger.py        # Logging
│       ├── config.py        # Config loading
│       ├── date_utils.py    # Date helpers
│       └── retry.py
│       
├── scripts/
│   ├── setup_indices.py     # Index bootstrap
│   └── import_kibana_objects.py # Kibana import
├── kibana/
│   └── dashboards/          # Kibana definitions
└── tests/
    ├── conftest.py          # Pytest fixtures
    ├── test_slack.py
    ├── test_es_client.py
    ├── test_analysis.py
    ├── test_cursor_client.py
    └── test_kashiwaas.py
```

### Design patterns

- Functional-style domain modeling: prefer pure functions and isolate side effects; implement as a data transformation pipeline.
- Layers:
  - Ingestion (Slack API)
  - Storage (Elasticsearch)
  - Analysis (queries and aggregates)
  - Presentation (reports and bot)
