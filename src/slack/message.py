"""
Slackメッセージデータモデル
Slack APIから取得したメッセージデータを扱うためのデータクラスを提供します
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

from src.utils.date_utils import convert_from_timestamp, get_day_of_week, get_hour_of_day, is_weekend


@dataclass
class SlackReaction:
    """Slackのリアクション情報"""
    name: str
    count: int
    users: List[str] = field(default_factory=list)


@dataclass
class SlackAttachment:
    """Slackの添付ファイル情報"""
    type: str
    size: int = 0
    url: Optional[str] = None


@dataclass
class SlackMessage:
    """Slackのメッセージ情報"""
    # 基本情報
    channel_id: str
    ts: str  # タイムスタンプ（Slackの一意識別子）
    user_id: str
    username: str
    text: str
    
    # 時間情報
    timestamp: datetime  # Python datetime
    is_weekend: bool
    hour_of_day: int
    day_of_week: int
    
    # スレッド情報
    thread_ts: Optional[str] = None
    reply_count: int = 0
    
    # リアクションと添付ファイル
    reactions: List[SlackReaction] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)
    attachments: List[SlackAttachment] = field(default_factory=list)
    
    # 元のSlackデータ
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_slack_data(cls, channel_id: str, message_data: Dict[str, Any]) -> 'SlackMessage':
        """
        Slack APIから取得したメッセージデータからSlackMessageオブジェクトを作成します
        
        Args:
            channel_id: チャンネルID
            message_data: Slack APIから取得したメッセージデータ
            
        Returns:
            SlackMessage: 変換されたメッセージオブジェクト
        """
        # タイムスタンプをPythonのdatetimeに変換
        ts = message_data.get('ts', '0')
        timestamp = convert_from_timestamp(float(ts))
        
        # ユーザー情報
        user_id = message_data.get('user', 'unknown')
        username = message_data.get('username', 'Unknown User')
        
        # スレッド情報
        thread_ts = message_data.get('thread_ts')
        reply_count = message_data.get('reply_count', 0)
        
        # リアクション情報
        reactions = []
        for reaction_data in message_data.get('reactions', []):
            reaction = SlackReaction(
                name=reaction_data.get('name', ''),
                count=reaction_data.get('count', 0),
                users=reaction_data.get('users', [])
            )
            reactions.append(reaction)
        
        # メンション情報を抽出
        mentions = []
        text = message_data.get('text', '')
        # <@U12345> 形式のメンションを抽出
        import re
        mention_pattern = r'<@([A-Z0-9]+)>'
        mentions = re.findall(mention_pattern, text)
        
        # 添付ファイル情報
        attachments = []
        for file_data in message_data.get('files', []):
            attachment = SlackAttachment(
                type=file_data.get('filetype', 'unknown'),
                size=file_data.get('size', 0),
                url=file_data.get('url_private', None)
            )
            attachments.append(attachment)
        
        return cls(
            channel_id=channel_id,
            ts=ts,
            user_id=user_id,
            username=username,
            text=text,
            timestamp=timestamp,
            is_weekend=is_weekend(timestamp),
            hour_of_day=get_hour_of_day(timestamp),
            day_of_week=get_day_of_week(timestamp),
            thread_ts=thread_ts,
            reply_count=reply_count,
            reactions=reactions,
            mentions=mentions,
            attachments=attachments,
            raw_data=message_data
        )
    
    def to_elasticsearch_doc(self) -> Dict[str, Any]:
        """
        ElasticsearchのドキュメントとしてデータをJSON形式に変換します
        
        Returns:
            Dict[str, Any]: Elasticsearchに保存可能なドキュメント
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "channel_id": self.channel_id,
            "user_id": self.user_id,
            "username": self.username,
            "text": self.text,
            "thread_ts": self.thread_ts,
            "reply_count": self.reply_count,
            "reactions": [
                {
                    "name": r.name,
                    "count": r.count,
                    "users": r.users
                } for r in self.reactions
            ],
            "mentions": self.mentions,
            "attachments": [
                {
                    "type": a.type,
                    "size": a.size,
                    "url": a.url
                } for a in self.attachments
            ],
            "is_weekend": self.is_weekend,
            "hour_of_day": self.hour_of_day,
            "day_of_week": self.day_of_week
        }