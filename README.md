# KashiwaaS
<[English](#English)|[日本語](#日本語)>

## English

## Overview
This system collects messages from a specific Slack channel, stores them in Elasticsearch, and analyzes and visualizes the message data. It helps improve team engagement by analyzing communication patterns.

## Features
- Collects messages from a specific Slack channel
- Stores messages in Elasticsearch
- Generates daily and weekly reports
- Visualizes message data using Kibana
- Posts reports to Slack automatically
- **KashiwaaS Bot**: Answer programming questions via `@kashiwaas` mention using Cursor Cloud Agents API

## Installation
### Prerequisites
- Python 3.12 or higher
- Poetry 2.1.0 or higher
- Docker and Docker Compose

### Setup
1. Clone the repository
   ```bash
   git clone https://github.com/takak2166/KashiwaaS.git
   cd KashiwaaS
   ```

2. Copy `.env.example` to `.env` and edit it
   ```bash
   cp .env.example .env
   ```

3. Start the services using Docker Compose
   ```bash
   docker-compose up -d
   ```

### Development Setup (Optional)
If you want to develop locally without Docker, follow these steps:

1. Install dependencies
   ```bash
   poetry install
   ```

2. Run the application
   ```bash
   poetry run python src/main.py
   ```

## Usage
### Data Collection
The system collects messages from a specific Slack channel every weekday at 6:00 AM (JST).

### Report Generation
- Daily Report: Posted at 8:00 AM (JST) on weekdays
- Weekly Report: Posted at 8:05 AM (JST) on Mondays

### Manual Data Collection
To collect historical data, run the following command:
```bash
# Collect all historical data
docker-compose exec app poetry run python src/main.py fetch --all

# Or collect data for specific days
docker-compose exec app poetry run python src/main.py fetch --days DAYS
```

## Configuration
### Environment Variables
- `SLACK_API_TOKEN`: Slack API token
- `SLACK_CHANNEL_ID`: Channel ID to collect messages from
- `ELASTICSEARCH_HOST`: Elasticsearch host
- `ELASTICSEARCH_USER`: Elasticsearch username
- `ELASTICSEARCH_PASSWORD`: Elasticsearch password

Other variables (Kibana, Selenium/Chrome, logging, alerts, bot/Cursor) are listed in `.env.example`.

### Elasticsearch Indices
To set up Elasticsearch indices, run the following command:
```bash
docker-compose exec app poetry run python scripts/setup_indices.py
```

### Kibana Dashboard
To import Kibana dashboards, run the following command:
```bash
docker-compose exec app poetry run python scripts/import_kibana_objects.py
```

## KashiwaaS Bot
A Slack bot that answers programming and technical questions via Cursor Cloud Agents API.

### How it Works
1. Mention `@kashiwaas` in a Slack channel with your question
2. The bot adds an :eyes: reaction to indicate it's processing
3. The question is sent to Cursor's Cloud Agents API
4. The response is posted as a thread reply
5. Follow-up questions in the same thread maintain conversation context

### Slack App Setup
1. Create a new Slack App at [api.slack.com/apps](https://api.slack.com/apps)
2. Enable **Socket Mode** and generate an App-Level Token (`xapp-`)
3. Under **Event Subscriptions**, subscribe to `app_mention` bot event
4. Add the following **Bot Token Scopes**: `app_mentions:read`, `chat:write`, `reactions:write`
5. Install the app to your workspace and copy the Bot Token (`xoxb-`)
6. Get a Cursor API key from [Cursor Dashboard → Integrations](https://cursor.com/dashboard?tab=integrations)

### Bot Environment Variables
- `SLACK_APP_TOKEN`: Slack App-Level Token for Socket Mode
- `SLACK_BOT_TOKEN`: Slack Bot Token
- `CURSOR_API_KEY`: Cursor Cloud Agents API key
- `CURSOR_SOURCE_REPOSITORY`: GitHub repository URL (default: this repository)
- `CURSOR_POLL_INTERVAL`: Polling interval in seconds (default: 5)
- `CURSOR_POLL_TIMEOUT`: Polling timeout in seconds (default: 300)
- `CURSOR_MODEL`: Model ID (e.g. `composer-2`). If unset, the bot uses `composer-2` by default. To use the API default model instead, explicitly set this to `Auto`, `default`, or an empty string. To see available IDs, call `GET https://api.cursor.com/v0/models` with your API key (Basic Auth).

### Running the Bot
```bash
# Via Docker Compose (starts alongside other services)
docker-compose up -d bot

# Or locally
poetry run python -m src.bot.kashiwaas
```

**Broken pipe errors:** You may see occasional `BrokenPipeError` or "Failed to check the state of sock" in logs. This is a known behavior of Slack Socket Mode when the WebSocket connection drops (e.g. network glitches). The Bolt client automatically reconnects; if the bot continues to respond to mentions, these messages can be ignored. Logging to stderr is also configured to avoid crashing on a closed pipe in Docker.

## Deployment
### Production Environment
1. Set up environment variables
2. Start the services using Docker Compose
3. Configure cron jobs for data collection and report generation

## Contributing
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

---
## 日本語

## 概要
このシステムは、特定のSlackチャンネルのメッセージを収集し、Elasticsearchに保存して、メッセージデータを分析・可視化します。コミュニケーションパターンを分析することで、チームのエンゲージメント向上に役立ちます。

## 機能
- 特定のSlackチャンネルのメッセージを収集
- メッセージをElasticsearchに保存
- 日次・週次のレポートを生成
- Kibanaを使用してメッセージデータを可視化
- レポートをSlackに自動投稿
- **KashiwaaS Bot**: `@kashiwaas` メンションでプログラミングの質問に回答（Cursor Cloud Agents API 連携）

## インストール
### 前提条件
- Python 3.12以上
- Poetry 2.1.0以上
- DockerとDocker Compose

### セットアップ
1. リポジトリをクローン
   ```bash
   git clone https://github.com/takak2166/KashiwaaS.git
   cd KashiwaaS
   ```

2. `.env.example`を`.env`にコピーして編集
   ```bash
   cp .env.example .env
   ```

3. Docker Composeでサービスを起動
   ```bash
   docker-compose up -d
   ```

### 開発環境のセットアップ（オプション）
Dockerを使用せずにローカルで開発する場合は、以下の手順に従ってください：

1. 依存関係をインストール
   ```bash
   poetry install
   ```

2. アプリケーションを実行
   ```bash
   poetry run python src/main.py
   ```

## 使用方法
### データ収集
システムは平日の午前6時（JST）に特定のSlackチャンネルのメッセージを収集します。

### レポート生成
- 日次レポート: 平日の午前8時（JST）に投稿
- 週次レポート: 月曜日の午前8時5分（JST）に投稿

### 手動でのデータ収集
過去のデータを収集するには、以下のコマンドを実行します：
```bash
# すべての過去データを収集
docker-compose exec app poetry run python src/main.py fetch --all

# または特定の日数のデータを収集
docker-compose exec app poetry run python src/main.py fetch --days DAYS
```

## 設定
### 環境変数
- `SLACK_API_TOKEN`: Slack APIトークン
- `SLACK_CHANNEL_ID`: メッセージを収集するチャンネルID
- `ELASTICSEARCH_HOST`: Elasticsearchのホスト
- `ELASTICSEARCH_USER`: Elasticsearchのユーザー名
- `ELASTICSEARCH_PASSWORD`: Elasticsearchのパスワード

Kibana、Selenium/Chrome、ログ、アラート、Bot/Cursor 用など、その他の変数は `.env.example` に記載しています。

### Elasticsearchインデックス
Elasticsearchインデックスを設定するには、以下のコマンドを実行します：
```bash
docker-compose exec app poetry run python scripts/setup_indices.py
```


### Kibanaダッシュボード
Kibanaダッシュボードをインポートするには、以下のコマンドを実行します：
```bash
docker-compose exec app poetry run python scripts/import_kibana_objects.py
```

## KashiwaaS Bot
Cursor Cloud Agents API を利用して、プログラミング・技術的な質問に回答するSlackボットです。

### 使い方
1. Slackチャンネルで `@kashiwaas` をメンションして質問を投稿
2. ボットが :eyes: リアクションを付けて処理中であることを表示
3. 質問がCursor Cloud Agents APIに送信される
4. 回答がスレッドに投稿される
5. 同じスレッド内でフォローアップの質問が可能（会話コンテキストを保持）

### Slack App の設定
1. [api.slack.com/apps](https://api.slack.com/apps) で新しいSlack Appを作成
2. **Socket Mode** を有効化し、App-Level Token (`xapp-`) を生成
3. **Event Subscriptions** で `app_mention` ボットイベントを購読
4. **Bot Token Scopes** に `app_mentions:read`, `chat:write`, `reactions:write` を追加
5. ワークスペースにアプリをインストールし、Bot Token (`xoxb-`) をコピー
6. [Cursor Dashboard → Integrations](https://cursor.com/dashboard?tab=integrations) でCursor APIキーを取得

### Bot用の環境変数
- `SLACK_APP_TOKEN`: Socket Mode用のSlack App-Level Token
- `SLACK_BOT_TOKEN`: Slack Bot Token
- `CURSOR_API_KEY`: Cursor Cloud Agents APIキー
- `CURSOR_SOURCE_REPOSITORY`: GitHubリポジトリURL（デフォルト: 本リポジトリ）
- `CURSOR_POLL_INTERVAL`: ポーリング間隔（秒、デフォルト: 5）
- `CURSOR_POLL_TIMEOUT`: ポーリングタイムアウト（秒、デフォルト: 300）
- `CURSOR_MODEL`: モデルID（例: `composer-2`）。未設定の場合、Botはデフォルトで `composer-2` を使います。APIデフォルトのモデルを使いたい場合は、明示的に `Auto` / `default` または空文字に設定してください。利用可能なIDは `GET https://api.cursor.com/v0/models` をAPIキー（Basic認証）で呼ぶと確認できます。

### Botの起動
```bash
# Docker Compose経由（他のサービスと一緒に起動）
docker-compose up -d bot

# またはローカルで実行
poetry run python -m src.bot.kashiwaas
```

**Broken pipe について:** ログに `BrokenPipeError` や "Failed to check the state of sock" がときどき出ることがあります。Slack Socket Mode で WebSocket が切断されたとき（ネットワークの揺れなど）の既知の挙動です。Bolt は自動で再接続するため、メンションへの応答が続いていれば無視して問題ありません。また、Docker でパイプが閉じた際のクラッシュを避けるため、stderr へのログ出力には catch を入れています。

## デプロイメント
### 本番環境
1. 環境変数を設定
2. Docker Composeでサービスを起動
3. データ収集とレポート生成のためのcronジョブを設定

## 貢献
1. リポジトリをフォーク
2. 機能ブランチを作成
3. 変更をコミット
4. ブランチにプッシュ
5. プルリクエストを作成
