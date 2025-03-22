"""
Slack API関連のテスト
"""
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.slack.client import SlackClient
from src.slack.message import SlackMessage
from src.slack.message import SlackReaction



class TestSlackMessage:
    """SlackMessageクラスのテスト"""
    
    def test_from_slack_data(self):
        """from_slack_dataメソッドのテスト"""
        # テスト用のSlackメッセージデータ
        channel_id = "C12345678"
        message_data = {
            "type": "message",
            "user": "U12345",
            "text": "Hello <@U67890>!",
            "ts": "1609459200.000000",  # 2021-01-01 00:00:00
            "reactions": [
                {
                    "name": "thumbsup",
                    "count": 2,
                    "users": ["U11111", "U22222"]
                }
            ],
            "thread_ts": "1609459200.000000",
            "reply_count": 3,
            "files": [
                {
                    "filetype": "png",
                    "size": 12345,
                    "url_private": "https://example.com/file.png"
                }
            ]
        }
        
        # SlackMessageオブジェクトに変換
        message = SlackMessage.from_slack_data(channel_id, message_data)
        
        # 変換結果の検証
        assert message.channel_id == channel_id
        assert message.ts == "1609459200.000000"
        assert message.user_id == "U12345"
        assert message.text == "Hello <@U67890>!"
        assert message.thread_ts == "1609459200.000000"
        assert message.reply_count == 3
        assert len(message.reactions) == 1
        assert message.reactions[0].name == "thumbsup"
        assert message.reactions[0].count == 2
        assert len(message.mentions) == 1
        assert message.mentions[0] == "U67890"
        assert len(message.attachments) == 1
        assert message.attachments[0].type == "png"
        assert message.attachments[0].size == 12345
    
    def test_to_elasticsearch_doc(self):
        """to_elasticsearch_docメソッドのテスト"""
        # テスト用のSlackMessageオブジェクト
        message = SlackMessage(
            channel_id="C12345678",
            ts="1609459200.000000",
            user_id="U12345",
            username="testuser",
            text="Hello!",
            timestamp=datetime(2021, 1, 1, 0, 0, 0),
            is_weekend=False,
            hour_of_day=0,
            day_of_week=4,  # 金曜日
            thread_ts="1609459200.000000",
            reply_count=2,
            reactions=[
                SlackReaction(
                    name="thumbsup",
                    count=1,
                    users=["U11111"]
                )
            ],
            mentions=["U67890"],
            attachments=[]
        )
        
        # Elasticsearchドキュメントに変換
        doc = message.to_elasticsearch_doc()
        
        # 変換結果の検証
        assert doc["channel_id"] == "C12345678"
        assert doc["user_id"] == "U12345"
        assert doc["username"] == "testuser"
        assert doc["text"] == "Hello!"
        assert doc["thread_ts"] == "1609459200.000000"
        assert doc["reply_count"] == 2
        assert len(doc["reactions"]) == 1
        assert doc["reactions"][0]["name"] == "thumbsup"
        assert doc["is_weekend"] is False
        assert doc["hour_of_day"] == 0
        assert doc["day_of_week"] == 4


@pytest.mark.skipif(not os.getenv("SLACK_API_TOKEN"), reason="SLACK_API_TOKEN not set")
class TestSlackClient:
    """SlackClientクラスのテスト"""
    
    def test_get_channel_info(self):
        """get_channel_infoメソッドのテスト"""
        # 実際のAPIを使用するテスト
        client = SlackClient()
        channel_info = client.get_channel_info()
        
        # 結果の検証
        assert "id" in channel_info
        assert "name" in channel_info
    
    def test_get_messages(self):
        """get_messagesメソッドのテスト"""
        # 実際のAPIを使用するテスト
        client = SlackClient()
        
        # 過去1日分のメッセージを取得
        end_date = datetime.now()
        start_date = end_date - timedelta(days=1)
        
        messages = list(client.get_messages(
            oldest=start_date,
            latest=end_date,
            limit=10,
            include_threads=True
        ))
        
        # 結果の検証（メッセージが存在しない場合もあるため、構造のみ確認）
        for message in messages:
            assert isinstance(message, SlackMessage)
            assert message.channel_id == client.channel_id
            assert hasattr(message, "timestamp")
            assert hasattr(message, "text")


class TestSlackClientMock:
    """SlackClientクラスのモックテスト"""
    
    @patch("src.slack.client.WebClient")
    def test_get_messages_mock(self, mock_web_client):
        """get_messagesメソッドのモックテスト"""
        # WebClientのモック設定
        mock_client = MagicMock()
        mock_web_client.return_value = mock_client
        
        # conversations_historyの戻り値を設定
        mock_client.conversations_history.return_value = {
            "messages": [
                {
                    "type": "message",
                    "user": "U12345",
                    "text": "Test message",
                    "ts": "1609459200.000000"
                }
            ],
            "response_metadata": {
                "next_cursor": ""  # 次ページなし
            }
        }
        
        # conversations_repliesの戻り値を設定
        mock_client.conversations_replies.return_value = {
            "messages": [
                {
                    "type": "message",
                    "user": "U12345",
                    "text": "Parent message",
                    "ts": "1609459200.000000"
                },
                {
                    "type": "message",
                    "user": "U67890",
                    "text": "Reply message",
                    "ts": "1609459300.000000",
                    "thread_ts": "1609459200.000000"
                }
            ],
            "response_metadata": {
                "next_cursor": ""  # 次ページなし
            }
        }
        
        # SlackClientのインスタンス化
        client = SlackClient(token="xoxb-test-token", channel_id="C12345678")
        
        # メッセージの取得
        messages = list(client.get_messages(
            oldest=datetime(2021, 1, 1),
            latest=datetime(2021, 1, 2)
        ))
        
        # 結果の検証
        assert len(messages) == 1  # スレッド返信は親メッセージに含まれる
        assert messages[0].user_id == "U12345"
        assert messages[0].text == "Test message"
        
        # APIが正しく呼び出されたことを確認
        mock_client.conversations_history.assert_called_once()
        # スレッド返信の取得は呼び出されていないことを確認（テストデータにスレッドがないため）
        mock_client.conversations_replies.assert_not_called()