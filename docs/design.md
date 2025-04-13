# Slack メッセージ分析システム プロンプト設計書

## 1. プロジェクト概要

### 目的
Slackの特定のチャンネルのメッセージをElasticsearchに保管し、メッセージデータの分析と可視化を行うシステムを構築する。
これにより、チームのコミュニケーションパターンを分析し、エンゲージメントを向上させる。

### 解決する問題
- チャンネル内のコミュニケーション傾向を時系列で分析したい
- 投稿数やリアクション数などの統計情報を可視化したい
- コミュニケーションのトレンドを自動的に検出し通知したい
- 定期的にチャンネルへ統計情報を自動投稿したい

### 期待される成果物
1. Slackデータ収集スクリプト
2. Elasticsearchデータ保存システム
3. 統計分析・レポート生成機能
4. Slack通知Bot
5. Kibanaダッシュボード定義ファイル

## 2. 技術要件

### 言語・フレームワーク
- プログラミング言語: Python 3.10以上
- パッケージ管理: Poetry 2.1.0以上

### 使用ライブラリ
- slack-sdk
- elasticsearch
- selenium
- python-dotenv
- requests
- pytest
- loguru
- black
- isort
- flake8
- pytz
- matplotlib
- numpy
- jinja2
- pandas
- plotly
- kaleido

### 開発環境
- Docker Compose 構成:
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
      # cron設定を含むDockerfile参照
    
    elasticsearch:
      image: docker.elastic.co/elasticsearch/elasticsearch:latest
      environment:
        - discovery.type=single-node
        - "ES_JAVA_OPTS=-Xms1g -Xmx1g"
        - xpack.security.enabled=false
      volumes:
        - es_data:/usr/share/elasticsearch/data
      ports:
        - "9200:9200"
    
    kibana:
      image: docker.elastic.co/kibana/kibana:latest
      environment:
        - ELASTICSEARCH_HOSTS=http://elasticsearch:9200
      ports:
        - "5601:5601"
      depends_on:
        - elasticsearch
  
  volumes:
    es_data:
  ```

## 3. 機能仕様

### データ取得
- 特定のSlackチャンネルの投稿を指定期間で取得
  ```python
  # 使用するSlack APIメソッド
  conversations.history(channel_id, oldest, latest, limit, inclusive)
  conversations.replies(channel_id, ts, limit)
  ```
- スレッドの返信を含めた全投稿情報を取得
- ページネーション処理による大量データの確実な取得
- 取得対象データ:
  - メッセージ本文
  - 投稿者情報（ID、名前）
  - タイムスタンプ
  - リアクション（種類、数、リアクションした人）
  - スレッド情報（親メッセージID、返信数）
  - メンション情報
  - 添付ファイル情報（種類、サイズ、URL）

### データ保存
- 取得したデータをElasticsearchに保存
- バルクインサートによる効率的なデータ保存
- Slackチャンネルとインデックスを1対1対応させる
- インデックステンプレート:
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

### 統計情報生成と投稿
- 日次レポート:
  - 前日のポスト数とリアクション数の総数
  - 時間帯別の投稿数分布図
  
- 週次レポート: Kibanaで生成したものを投稿する
  - 前週のポスト数推移グラフ（平日のみ/全日）
  - 最もリアクションが多かった投稿Top3
  - タグクラウド（kuromoji解析による名詞抽出）
  - Kibanaで生成したグラフはseleniumのwebdriverで読み込み、pngに変換
  - 生成される画像ファイルは固定の名前を使用（上書き保存）
    - ダッシュボードスクリーンショット: `kibana_weekly_dashboard.png`
    - 週次時間帯別チャート: `hourly_weekly.png`
    - リアクションパイチャート: `reaction_pie_weekly.png`

## 4. データ構造

### Elasticsearchインデックス設計
- インデックス命名規則: `slack-{channel_name}`
- シャード数: 1（小〜中規模データ想定）
- レプリカ数: 0（開発環境）/ 1（本番環境）
- リフレッシュ間隔: 1s（デフォルト）
- タイムスタンプフィールドを主キーとした時系列データ
- kuromoji解析プラグインを使用した日本語テキスト解析

## 5. 実行スケジュール

### データ取得頻度
- 1日1回（平日6:00、休日はスキップ）のデータ取得
  ```
  # crontab設定例
  0 6 * * 1-5 /app/run_data_collector.sh >> /var/log/collector.log 2>&1
  ```
- 過去データ一括取得用のスクリプトを別途用意
  ```python
  # 擬似コード
  def fetch_historical_data(channel_id, start_date, end_date):
      start_ts = convert_to_timestamp(start_date)
      end_ts = convert_to_timestamp(end_date)
      # 日付範囲を1日単位で分割して取得
      current_ts = start_ts
      while current_ts < end_ts:
          next_ts = current_ts + 86400  # 1日=86400秒
          fetch_and_store_messages(channel_id, current_ts, next_ts)
          current_ts = next_ts
  ```

### 統計情報投稿頻度
- 日次: 平日朝8:00に前日の統計情報
- 週次: 月曜朝8:05に前週の統計情報

## 6. エラーハンドリング

### 再試行ポリシー
- リクエスト失敗時はexponentialバックオフで再試行
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
- Slack API レート制限への対応（Tier 3: 50+ per minute）
- 最大5回まで再試行し、それでも失敗した場合はエラー終了・アラート送信
- `get_channel_info`は3回、`conversations_history`と`conversations_replies`は5回の再試行

### 例外処理
- 種類別の例外処理
  - ネットワーク例外: 再試行
  - 認証エラー: 即時終了・アラート
  - データ不整合: ログ記録・スキップ
  - Elasticsearch書き込みエラー: バッファリング・後で再試行
- `is_temporary_error`を使用して一時的なエラーを判定

### ログ出力
- ログレベル: DEBUG, INFO, WARNING, ERROR
- ログフォーマット: `{timestamp} {level} {module}:{line} - {message}`
- ログローテーション: 日次・7日間保持
- 重要エラーはSlackアラートチャンネルにも通知

## 7. セキュリティ要件

### 認証情報管理
- SlackのAPIキーやElasticsearchの認証情報は環境変数(.env)で管理
  ```
  # .env の例
  SLACK_API_TOKEN=xoxb-xxxxxxxxxxxx-xxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxx
  SLACK_CHANNEL_ID=C12345678
  ELASTICSEARCH_HOST=http://elasticsearch:9200
  ELASTICSEARCH_USER=elastic
  ELASTICSEARCH_PASSWORD=changeme
  ```
- .envファイルはgitignoreに追加
- 本番環境ではDocker secretsやKubernetes secretsを使用

### アクセス制御
- Slack APIトークンは必要最小限の権限のみ付与
  - `channels:history`
  - `channels:read`
  - `chat:write`
- Elasticsearch X-Pack Securityを本番環境では有効化

## 8. コード構造

### ファイル構成
```
project/
├── pyproject.toml           # Poetry設定
├── .gitignore               # Git除外設定
├── .env.example             # 環境変数サンプル
├── README.md                # プロジェクト説明
├── Dockerfile               # Dockerビルド定義
├── docker-compose.yml       # Docker Compose設定
├── crontab
├── docker-entrypoint.sh
├── elasticsearch
│   └── Dockerfile
├── docs
│   └── design.md
├── kibana
│   ├── dashboards
│   └── templates
│       ├── dashboard.ndjson.j2
│       ├── index_pattern.ndjson.j2
│       └── lens.ndjson.j2
├── src/
│   ├── main.py              # エントリーポイント
│   ├── slack/
│   │   ├── __init__.py
│   │   ├── client.py        # Slack API操作
│   │   └── message.py       # メッセージデータモデル
│   ├── es_client/
│   │   ├── __init__.py
│   │   ├── client.py        # ES操作
│   │   ├── index.py         # インデックス定義
│   │   └── query.py         # クエリビルダー
│   ├── kibana
│   │   ├── __init__.py
│   │   ├── capture.py
│   │   └── dashboard.py
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── daily.py         # 日次分析
│   │   ├── weekly.py        # 週次分析
│   │   └── visualization.py # 可視化処理
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── alerter.py
│   │   ├── reporter.py      # 定期レポート投稿
│   │   ├── utils.py
│   │   └── formatter.py     # メッセージフォーマット
│   └── utils/
│       ├── __init__.py
│       ├── logger.py        # ログ設定
│       ├── config.py        # 設定読み込み
│       ├── date_utils.py    # 日付操作ユーティリティ
│       └── retry.py
│       
├── scripts/
│   ├── setup_indices.py     # インデックス初期化
│   ├── backfill.py          # 過去データ取得
│   └── import_kibana_objects.py # Kibanaダッシュボード生成
├── kibana/
│   └── dashboards/          # Kibanaダッシュボード定義
└── tests/
    ├── __init__.py
    ├── conftest.py          # テスト設定
    ├── test_slack.py
    ├── test_elasticsearch.py
    └── test_analysis.py
```

### 設計パターン
- 関数型ドメインモデリングを採用
  - 純粋関数を多用し、副作用を分離
  - データ変換パイプラインとして実装
- レイヤー構造:
  - 取得層（Slack API）
  - 保存層（Elasticsearch）
  - 分析層（クエリと集計）
  - 表示層（レポートとBot）

## 9. テスト要件

### 単体テスト
- カバレッジ目標: 80%以上
- pytestを使用したテスト自動化
- テスト対象:
  - データモデル
  - ビジネスロジック
  - ユーティリティ関数
- モックを使用したAPI呼び出しのテスト

### 統合テスト
- Docker Composeを使った環境でのE2Eテスト
- 小規模なサンプルデータを使用した処理の検証

### デバッグと監視
- 詳細なログ出力
  ```python
  from loguru import logger
  
  # ログ設定
  logger.add("logs/app.log", rotation="1 day", retention="7 days", level="INFO")
  
  # 使用例
  logger.info("Processing channel {}", channel_id)
  logger.debug("Raw API response: {}", response)
  logger.error("Failed to connect to Elasticsearch: {}", err)
  ```
- メトリクス収集（処理時間、データ量など）
- 健全性チェックエンドポイント

## 10. デプロイメントと運用

### 初期セットアップ
1. Elasticsearchインデックステンプレートの作成
2. Kuromoji解析プラグインのインストール
3. Kibanaダッシュボードの作成
4. Slack Botの認証設定

### バックアップ戦略
- Elasticsearchスナップショットを日次で取得
- 設定ファイルとコードのGitリポジトリ管理

### モニタリング
- Elasticsearchクラスタ健全性の監視
- クローラー実行ステータスの監視
- エラーアラートのSlack通知

### パフォーマンスチューニング
- バルク操作のサイズ調整（500件単位）
- Elasticsearchキャッシュサイズの最適化
- インデックスのシャード数調整（データ量増加時）

## 11. 拡張性と将来の計画

### 拡張機能の候補
- 複数チャンネルの同時分析
- 感情分析によるチームの雰囲気スコア
- ユーザー間のインタラクションネットワーク分析
- アクティブ時間帯の分析と最適な投稿時間の推奨

### スケーラビリティ対応
- Elasticsearchクラスタ化による大規模データ対応
- 非同期処理によるデータ取得の高速化
- データパーティショニングによる検索性能の最適化