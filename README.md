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

## Installation
### Prerequisites
- Python 3.10 or higher
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

## インストール
### 前提条件
- Python 3.10以上
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
