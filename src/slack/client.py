"""
Slack API Client
Provides a client for retrieving message data using the Slack API
"""
import os
import time
from datetime import datetime
from typing import Dict, Generator, List, Optional, Tuple, Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from src.slack.message import SlackMessage
from src.utils.config import config
from src.utils.date_utils import convert_to_timestamp
from src.utils.logger import get_logger
from src.utils.retry import retry_with_backoff, is_rate_limit_error, is_temporary_error

logger = get_logger(__name__)


class SlackClient:
    """
    Slack API Client
    
    Retrieves messages from Slack channels using the Slack API.
    Includes handling for pagination and rate limiting.
    """
    
    def __init__(self, token: Optional[str] = None, channel_id: Optional[str] = None):
        """
        Initialize the SlackClient
        
        Args:
            token: Slack API Token (if not specified, retrieved from environment variables)
            channel_id: Channel ID to fetch from (if not specified, retrieved from environment variables)
        """
        self.token = token or (config.slack.api_token if config else None)
        if not self.token:
            raise ValueError("Slack API token is required")
        
        self.channel_id = channel_id or (config.slack.channel_id if config else None)
        if not self.channel_id:
            raise ValueError("Slack channel ID is required")
        
        self.client = WebClient(token=self.token)
        logger.info(f"SlackClient initialized for channel {self.channel_id}")
        
        try:
            channel_info = self.get_channel_info()
            logger.info(f"Successfully validated channel: {channel_info.get('name', 'unknown')} ({self.channel_id})")
        except Exception as e:
            logger.warning(f"Channel validation failed: {e}")
            logger.warning(f"This may cause issues with API calls that require a valid channel ID")
    
    @retry_with_backoff(
        max_retries=3,
        exceptions_to_retry=[SlackApiError],
        should_retry_fn=is_temporary_error,
        on_retry_callback=lambda retries, e, wait_time: logger.warning(
            f"Retrying get_channel_info after error: {e}"
        )
    )
    def get_channel_info(self) -> Dict[str, Any]:
        """
        Get channel information
        
        Returns:
            Dict[str, Any]: Channel information
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
        Get messages for the specified period
        
        Args:
            oldest: Start date/time for fetching (None to fetch from the beginning)
            latest: End date/time for fetching
            limit: Number of messages to fetch per request
            include_threads: Whether to include thread replies
            
        Yields:
            SlackMessage: Retrieved messages
        """
        # Convert to timestamps
        oldest_ts = convert_to_timestamp(oldest) if oldest else None
        latest_ts = convert_to_timestamp(latest) if latest else None
        
        logger.info(
            f"Fetching messages from channel {self.channel_id} "
            f"(oldest: {oldest_ts}, latest: {latest_ts}, include_threads: {include_threads})"
        )
        
        # Parameters for message retrieval
        params = {
            "channel": self.channel_id,
            "limit": limit,
        }
        if oldest_ts:
            params["oldest"] = str(oldest_ts)
        if latest_ts:
            params["latest"] = str(latest_ts)
        
        # Cursor for pagination
        cursor = None
        
        # Message count
        message_count = 0
        thread_message_count = 0
        
        while True:
            try:
                # Add cursor if available
                if cursor:
                    params["cursor"] = cursor
                
                # API request with retry
                response = self._fetch_history_with_retry(params)
                messages = response.get("messages", [])
                
                # Process retrieved messages
                for message in messages:
                    message_count += 1
                    
                    # Convert to SlackMessage object and yield
                    slack_message = SlackMessage.from_slack_data(self.channel_id, message)
                    yield slack_message
                    
                    # Get thread replies
                    if include_threads and message.get("thread_ts") and message.get("reply_count", 0) > 0:
                        thread_messages = self._get_thread_replies(message["thread_ts"])
                        for thread_message in thread_messages:
                            thread_message_count += 1
                            thread_slack_message = SlackMessage.from_slack_data(self.channel_id, thread_message)
                            yield thread_slack_message
                
                # Check if there is a next page
                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
                
                # Wait a bit between requests to be nice to the API
                time.sleep(0.5)
                
            except SlackApiError as e:
                logger.error(f"Failed to fetch messages: {e}")
                raise
        
        logger.info(f"Fetched {message_count} messages and {thread_message_count} thread replies")
    
    @retry_with_backoff(
        max_retries=5,
        initial_backoff=1.0,
        backoff_factor=2.0,
        exceptions_to_retry=[SlackApiError],
        should_retry_fn=is_temporary_error,
        on_retry_callback=lambda retries, e, wait_time: logger.warning(
            f"Retrying conversations_history after error: {e}"
        )
    )
    def _fetch_history_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fetch conversation history with retry
        
        Args:
            params: Parameters for the API call
            
        Returns:
            Dict[str, Any]: API response
        """
        try:
            return self.client.conversations_history(**params)
        except SlackApiError as e:
            # Handle rate limiting explicitly
            if is_rate_limit_error(e):
                retry_after = int(e.response.headers.get("Retry-After", 1))
                logger.warning(f"Rate limited. Waiting for {retry_after} seconds")
                time.sleep(retry_after)
                # This will be retried by the decorator
            raise
    
    def _get_thread_replies(self, thread_ts: str) -> List[Dict[str, Any]]:
        """
        Get thread replies
        
        Args:
            thread_ts: Timestamp of the parent message in the thread
            
        Returns:
            List[Dict[str, Any]]: List of thread reply messages
        """
        all_replies = []
        cursor = None
        
        while True:
            try:
                params = {
                    "channel": self.channel_id,
                    "ts": thread_ts,
                    "limit": 100,
                }
                
                if cursor:
                    params["cursor"] = cursor
                
                # API request with retry
                response = self._fetch_replies_with_retry(params)
                replies = response.get("messages", [])
                
                # Skip the first message as it's the parent message
                if replies and replies[0].get("ts") == thread_ts:
                    replies = replies[1:]
                
                all_replies.extend(replies)
                
                # Check if there is a next page
                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
                
                # Wait a bit between requests to be nice to the API
                time.sleep(0.5)
                
            except SlackApiError as e:
                logger.error(f"Failed to fetch thread replies: {e}")
                # Return what we have so far instead of empty list
                return all_replies
        
        return all_replies
    
    @retry_with_backoff(
        max_retries=5,
        initial_backoff=1.0,
        backoff_factor=2.0,
        exceptions_to_retry=[SlackApiError],
        should_retry_fn=is_temporary_error,
        on_retry_callback=lambda retries, e, wait_time: logger.warning(
            f"Retrying conversations_replies after error: {e}"
        )
    )
    def _fetch_replies_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fetch conversation replies with retry
        
        Args:
            params: Parameters for the API call
            
        Returns:
            Dict[str, Any]: API response
        """
        try:
            return self.client.conversations_replies(**params)
        except SlackApiError as e:
            # Handle rate limiting explicitly
            if is_rate_limit_error(e):
                retry_after = int(e.response.headers.get("Retry-After", 1))
                logger.warning(f"Rate limited. Waiting for {retry_after} seconds")
                time.sleep(retry_after)
                # This will be retried by the decorator
            raise
    
    @retry_with_backoff(
        max_retries=3,
        initial_backoff=1.0,
        backoff_factor=2.0,
        exceptions_to_retry=[SlackApiError],
        should_retry_fn=is_temporary_error,
        on_retry_callback=lambda retries, e, wait_time: logger.warning(
            f"Retrying post_message after error: {e}"
        )
    )
    def post_message(
        self,
        text: str,
        blocks: Optional[List[Dict[str, Any]]] = None,
        thread_ts: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Post a message to the channel
        
        Args:
            text: Message text
            blocks: Message blocks in Block Kit format
            thread_ts: Timestamp of the thread to reply to
            attachments: Attachment information
            
        Returns:
            Dict[str, Any]: Post result
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
            # Handle rate limiting explicitly
            if is_rate_limit_error(e):
                retry_after = int(e.response.headers.get("Retry-After", 1))
                logger.warning(f"Rate limited. Waiting for {retry_after} seconds")
                time.sleep(retry_after)
                # This will be retried by the decorator
            raise
    
    @retry_with_backoff(
        max_retries=3,
        initial_backoff=1.0,
        backoff_factor=2.0,
        exceptions_to_retry=[SlackApiError],
        should_retry_fn=is_temporary_error,
        on_retry_callback=lambda retries, e, wait_time: logger.warning(
            f"Retrying upload_file after error: {e}"
        )
    )
    def upload_file(
        self,
        file_path: str,
        title: Optional[str] = None,
        thread_ts: Optional[str] = None,
        initial_comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload a file to the channel
        
        Args:
            file_path: Path to the file to upload
            title: Title for the file
            thread_ts: Timestamp of the thread to attach the file to
            initial_comment: Initial comment for the file
            
        Returns:
            Dict[str, Any]: Upload result
        """
        if not os.path.exists(file_path):
            error_msg = f"File not found: {file_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        try:
            logger.info(f"Uploading file {file_path} to channel {self.channel_id}")
            
            params = {
                "channels": [self.channel_id],
                "file": file_path,
            }
            
            if title:
                params["title"] = title
            
            if thread_ts:
                params["thread_ts"] = thread_ts
            
            if initial_comment:
                params["initial_comment"] = initial_comment
            
            response = self.client.files_upload_v2(**params)
            logger.info(f"File uploaded to channel {self.channel_id}: {file_path}")
            return response
            
        except SlackApiError as e:
            logger.error(f"Failed to upload file: {e}")
            logger.error(f"Channel ID: {self.channel_id}")
            logger.error(f"File path: {file_path}")
            if hasattr(e, 'response') and 'error' in e.response:
                logger.error(f"Error details: {e.response['error']}")
            # Handle rate limiting explicitly
            if is_rate_limit_error(e):
                retry_after = int(e.response.headers.get("Retry-After", 1))
                logger.warning(f"Rate limited. Waiting for {retry_after} seconds")
                time.sleep(retry_after)
                # This will be retried by the decorator
            raise