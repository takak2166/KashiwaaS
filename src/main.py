"""
メインエントリーポイント
アプリケーションの実行開始点となるモジュールです
"""
import argparse
import sys
from datetime import datetime, timedelta
from typing import Optional

from src.slack.client import SlackClient
from src.utils.config import config
from src.utils.date_utils import convert_from_timestamp, get_current_time
from src.utils.logger import get_logger

logger = get_logger(__name__)


def parse_args():
    """コマンドライン引数をパースします"""
    parser = argparse.ArgumentParser(description="Slack メッセージ分析システム")
    
    # サブコマンドの設定
    subparsers = parser.add_subparsers(dest="command", help="実行するコマンド")
    
    # fetch コマンド
    fetch_parser = subparsers.add_parser("fetch", help="Slackメッセージを取得してElasticsearchに保存")
    fetch_parser.add_argument(
        "--days", type=int, default=1, help="取得する日数 (デフォルト: 1)"
    )
    fetch_parser.add_argument(
        "--channel", type=str, help="取得するチャンネルID (デフォルト: 環境変数の値)"
    )
    fetch_parser.add_argument(
        "--end-date", type=str, help="取得終了日 (YYYY-MM-DD形式, デフォルト: 今日)"
    )
    fetch_parser.add_argument(
        "--no-threads", action="store_true", help="スレッドの返信を取得しない"
    )
    
    # report コマンド
    report_parser = subparsers.add_parser("report", help="レポートを生成してSlackに投稿")
    report_parser.add_argument(
        "--type", type=str, choices=["daily", "weekly"], default="daily",
        help="レポートの種類 (daily または weekly, デフォルト: daily)"
    )
    report_parser.add_argument(
        "--date", type=str, help="レポート対象日 (YYYY-MM-DD形式, デフォルト: 昨日)"
    )
    report_parser.add_argument(
        "--dry-run", action="store_true", help="実際に投稿せずに内容を表示のみ"
    )
    
    return parser.parse_args()


def fetch_messages(
    days: int = 1,
    channel_id: Optional[str] = None,
    end_date: Optional[datetime] = None,
    include_threads: bool = True
):
    """
    指定した期間のSlackメッセージを取得します
    
    Args:
        days: 取得する日数
        channel_id: 取得するチャンネルID
        end_date: 取得終了日
        include_threads: スレッドの返信も取得するかどうか
    """
    # 終了日が指定されていない場合は現在日時
    if end_date is None:
        end_date = get_current_time()
    
    # 開始日を計算
    start_date = end_date - timedelta(days=days)
    
    logger.info(
        f"Fetching messages for {days} days "
        f"(from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})"
    )
    
    # Slackクライアントの初期化
    client = SlackClient(channel_id=channel_id)
    
    # チャンネル情報の取得
    try:
        channel_info = client.get_channel_info()
        channel_name = channel_info.get("name", "unknown")
        logger.info(f"Target channel: {channel_name} ({client.channel_id})")
    except Exception as e:
        logger.error(f"Failed to get channel info: {e}")
        return
    
    # メッセージの取得
    try:
        message_count = 0
        for message in client.get_messages(
            oldest=start_date,
            latest=end_date,
            include_threads=include_threads
        ):
            message_count += 1
            
            # TODO: Elasticsearchへの保存処理を実装
            # 現段階では取得したメッセージの情報をログに出力
            logger.debug(
                f"Message: {message.timestamp.strftime('%Y-%m-%d %H:%M:%S')} "
                f"by {message.username} ({message.user_id})"
            )
            
            # 100件ごとに進捗を表示
            if message_count % 100 == 0:
                logger.info(f"Processed {message_count} messages so far")
        
        logger.info(f"Completed. Total {message_count} messages processed")
        
    except Exception as e:
        logger.error(f"Error during message fetching: {e}")
        raise


def main():
    """メイン実行関数"""
    # 設定の確認
    if not config:
        logger.error("Configuration is not properly loaded. Please check your .env file.")
        sys.exit(1)
    
    # コマンドライン引数のパース
    args = parse_args()
    
    if args.command == "fetch":
        # 終了日の解析
        end_date = None
        if args.end_date:
            try:
                end_date = datetime.strptime(args.end_date, "%Y-%m-%d")
                # タイムゾーン情報を追加
                end_date = end_date.replace(hour=23, minute=59, second=59)
            except ValueError:
                logger.error(f"Invalid date format: {args.end_date}. Use YYYY-MM-DD format.")
                sys.exit(1)
        
        # メッセージ取得の実行
        fetch_messages(
            days=args.days,
            channel_id=args.channel,
            end_date=end_date,
            include_threads=not args.no_threads
        )
    
    elif args.command == "report":
        # TODO: レポート生成と投稿の実装
        logger.info(f"Report command not implemented yet. Type: {args.type}")
    
    else:
        logger.error("No command specified. Use --help for usage information.")
        sys.exit(1)


if __name__ == "__main__":
    main()