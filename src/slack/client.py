"""
Slack APIクライアント
Slack APIを使用してメッセージデータを取得するクライアントを提供します
"""
import time
from datetime import datetime
from typing import Dict, Generator, List, Optional, Tuple, Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from src.slack.message import SlackMessage
from src.utils.config import config
from src.utils.date_utils import convert_to_timestamp
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SlackClient:
    """
    Slack APIクライアント
    
    Slack APIを使用してチャンネルのメッセージを取得します。
    ページネーション処理やレート制限への対応を含みます。
    """
    
    def __init__(self, token: Optional[str] = None, channel_id: Optional[str] = None):
        """
        SlackClientを初期化します
        
        Args:
            token: Slack API Token (指定がない場合は環境変数から取得)
            channel_id: 取得対象のチャンネルID (指定がない場合は環境変数から取得)
        """
        self.token = token or (config.slack.api_token if config else None)
        if not self.token:
            raise ValueError("Slack API token is required")
        
        self.channel_id = channel_id or (config.slack.channel_id if config else None)
        if not self.channel_id:
            raise ValueError("Slack channel ID is required")
        
        self.client = WebClient(token=self.token)
        logger.info(f"SlackClient initialized for channel {self.channel_id}")
    
    def get_channel_info(self) -> Dict[str, Any]:
        """
        チャンネル情報を取得します
        
        Returns:
            Dict[str, Any]: チャンネル情報
        """
        try:
            response = self.client.conversations_info(channel=self.channel_id)
            return response["channel"]
        except SlackApiError as e:
            logger.error(f"Failed to get channel info: {e}")
            raise
    
    def get_messages(
        self,
        oldest: Optional[datetime] = None,
        latest: Optional[datetime] = None,
        limit: int = 100,
        include_threads: bool = True
    ) -> Generator[SlackMessage, None, None]:
        """
        指定した期間のメッセージを取得します
        
        Args:
            oldest: 取得開始日時
            latest: 取得終了日時
            limit: 1回のリクエストで取得するメッセージ数
            include_threads: スレッドの返信も取得するかどうか
            
        Yields:
            SlackMessage: 取得したメッセージ
        """
        # タイムスタンプに変換
        oldest_ts = convert_to_timestamp(oldest) if oldest else None
        latest_ts = convert_to_timestamp(latest) if latest else None
        
        logger.info(
            f"Fetching messages from channel {self.channel_id} "
            f"(oldest: {oldest_ts}, latest: {latest_ts}, include_threads: {include_threads})"
        )
        
        # メッセージ取得のためのパラメータ
        params = {
            "channel": self.channel_id,
            "limit": limit,
        }
        if oldest_ts:
            params["oldest"] = str(oldest_ts)
        if latest_ts:
            params["latest"] = str(latest_ts)
        
        # ページネーション用のカーソル
        cursor = None
        
        # メッセージ数カウント
        message_count = 0
        thread_message_count = 0
        
        while True:
            try:
                # カーソルがある場合は追加
                if cursor:
                    params["cursor"] = cursor
                
                # APIリクエスト
                response = self.client.conversations_history(**params)
                messages = response.get("messages", [])
                
                # 取得したメッセージを処理
                for message in messages:
                    message_count += 1
                    
                    # メッセージオブジェクトに変換して返す
                    slack_message = SlackMessage.from_slack_data(self.channel_id, message)
                    yield slack_message
                    
                    # スレッドの返信を取得
                    if include_threads and message.get("thread_ts") and message.get("reply_count", 0) > 0:
                        thread_messages = self._get_thread_replies(message["thread_ts"])
                        for thread_message in thread_messages:
                            thread_message_count += 1
                            thread_slack_message = SlackMessage.from_slack_data(self.channel_id, thread_message)
                            yield thread_slack_message
                
                # 次のページがあるかチェック
                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
                
                # レート制限に対応するため少し待機
                time.sleep(0.5)
                
            except SlackApiError as e:
                if e.response["error"] == "ratelimited":
                    # レート制限に達した場合は待機して再試行
                    retry_after = int(e.response.headers.get("Retry-After", 1))
                    logger.warning(f"Rate limited. Waiting for {retry_after} seconds")
                    time.sleep(retry_after)
                    continue
                else:
                    logger.error(f"Failed to fetch messages: {e}")
                    raise
        
        logger.info(f"Fetched {message_count} messages and {thread_message_count} thread replies")
    
    def _get_thread_replies(self, thread_ts: str) -> List[Dict[str, Any]]:
        """
        スレッドの返信を取得します
        
        Args:
            thread_ts: スレッドの親メッセージのタイムスタンプ
            
        Returns:
            List[Dict[str, Any]]: スレッドの返信メッセージのリスト
        """
        try:
            all_replies = []
            cursor = None
            
            while True:
                params = {
                    "channel": self.channel_id,
                    "ts": thread_ts,
                    "limit": 100,
                }
                
                if cursor:
                    params["cursor"] = cursor
                
                response = self.client.conversations_replies(**params)
                replies = response.get("messages", [])
                
                # 最初のメッセージは親メッセージなのでスキップ
                if replies and replies[0].get("ts") == thread_ts:
                    replies = replies[1:]
                
                all_replies.extend(replies)
                
                # 次のページがあるかチェック
                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
                
                # レート制限に対応するため少し待機
                time.sleep(0.5)
            
            return all_replies
            
        except SlackApiError as e:
            logger.error(f"Failed to fetch thread replies: {e}")
            if e.response["error"] == "ratelimited":
                # レート制限に達した場合は待機して再試行
                retry_after = int(e.response.headers.get("Retry-After", 1))
                logger.warning(f"Rate limited. Waiting for {retry_after} seconds")
                time.sleep(retry_after)
                return self._get_thread_replies(thread_ts)
            else:
                return []
    
    def post_message(
        self,
        text: str,
        blocks: Optional[List[Dict[str, Any]]] = None,
        thread_ts: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        チャンネルにメッセージを投稿します
        
        Args:
            text: メッセージテキスト
            blocks: Block Kit形式のメッセージブロック
            thread_ts: 返信先のスレッドのタイムスタンプ
            attachments: 添付ファイル情報
            
        Returns:
            Dict[str, Any]: 投稿結果
        """
        try:
            params = {
                "channel": self.channel_id,
                "text": text,
            }
            
            if blocks:
                params["blocks"] = blocks
            
            if thread_ts:
                params["thread_ts"] = thread_ts
            
            if attachments:
                params["attachments"] = attachments
            
            response = self.client.chat_postMessage(**params)
            logger.info(f"Message posted to channel {self.channel_id}")
            return response
            
        except SlackApiError as e:
            logger.error(f"Failed to post message: {e}")
            raise