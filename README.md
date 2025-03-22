# Slack メッセージ分析システム

Slackの特定のチャンネルのメッセージをElasticsearchに保管し、メッセージデータの分析と可視化を行うシステムです。

## 機能概要

- Slack APIを使用したメッセージデータの取得
- Elasticsearchへのデータ保存
- 日次・週次の統計情報生成
- Slackへのレポート自動投稿
- Kibanaダッシュボードによる可視化

## 必要条件

- Python 3.10以上
- Poetry 2.1.0以上
- Docker & Docker Compose
- Slack APIトークン

## セットアップ

### 1. リポジトリのクローン

```bash
git clone <repository-url>
cd slack-message-analyzer
```

### 2. 環境変数の設定

`.env.example`をコピーして`.env`ファイルを作成し、必要な環境変数を設定します。

```bash
cp .env.example .env
# .envファイルを編集して必要な情報を設定
```

### 3. 依存関係のインストール

```bash
poetry install
```

### 4. Dockerコンテナの起動

```bash
docker-compose up -d
```

### 5. Elasticsearchインデックスの初期化

```bash
poetry run python scripts/setup_indices.py
```

## 使用方法

### メッセージデータの取得

```bash
# 昨日のメッセージを取得
poetry run python src/main.py fetch

# 過去7日間のメッセージを取得
poetry run python src/main.py fetch --days 7

# 特定の日付までのメッセージを取得
poetry run python src/main.py fetch --days 30 --end-date 2023-12-31

# スレッドの返信を含めずに取得
poetry run python src/main.py fetch --no-threads
```

### レポートの生成と投稿

```bash
# 日次レポートの生成と投稿
poetry run python src/main.py report --type daily

# 週次レポートの生成と投稿
poetry run python src/main.py report --type weekly

# 特定の日付のレポート生成（投稿なし）
poetry run python src/main.py report --type daily --date 2023-12-31 --dry-run
```

## 開発

### テストの実行

```bash
poetry run pytest
```

### コードフォーマット

```bash
poetry run black src tests
poetry run isort src tests
```

### リンター

```bash
poetry run flake8 src tests
```

## プロジェクト構成

```
project/
├── pyproject.toml           # Poetry設定
├── .env.example             # 環境変数サンプル
├── README.md                # プロジェクト説明
├── Dockerfile               # Dockerビルド定義
├── docker-compose.yml       # Docker Compose設定
├── .gitignore               # Git除外設定
├── src/
│   ├── main.py              # エントリーポイント
│   ├── slack/               # Slack API関連
│   ├── elasticsearch/       # Elasticsearch関連
│   ├── analysis/            # データ分析関連
│   ├── bot/                 # Slack Bot関連
│   └── utils/               # ユーティリティ
├── scripts/                 # 運用スクリプト
├── kibana/                  # Kibanaダッシュボード定義
└── tests/                   # テストコード
```

## ライセンス

[MIT License](LICENSE)