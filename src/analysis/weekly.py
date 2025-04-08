"""
Weekly Analysis Module
Provides functionality for generating weekly reports
"""
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from src.es_client.client import ElasticsearchClient
from src.utils.logger import get_logger
from src.analysis.daily import get_daily_stats

logger = get_logger(__name__)


def get_weekly_stats(
    channel_name: str,
    end_date: Optional[datetime] = None,
    es_client: Optional[ElasticsearchClient] = None
) -> Dict[str, Any]:
    """
    Get weekly statistics
    
    Args:
        channel_name: Channel name
        end_date: End date (default: yesterday)
        es_client: Elasticsearch client (optional)
        
    Returns:
        Dict[str, Any]: Weekly statistics
    """
    # Initialize Elasticsearch client if not provided
    if es_client is None:
        es_client = ElasticsearchClient()
    
    # Set end_date to yesterday if not specified
    if end_date is None:
        current_time = datetime.now()
        end_date = current_time - timedelta(days=1)
    
    # Calculate start_date (7 days before end_date)
    start_date = end_date - timedelta(days=6)
    
    # Format dates for Elasticsearch
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")
    
    # Get index name
    index_name = f"slack-{channel_name}"
    
    # Get daily stats for each day in the week
    daily_stats = []
    error_dates = []  # Track dates with errors
    current_date = start_date
    
    while current_date <= end_date:
        try:
            stats = get_daily_stats(channel_name, current_date, es_client)
            daily_stats.append(stats)
            logger.info(f"Got daily stats for {current_date.strftime('%Y-%m-%d')}: {stats['message_count']} messages")
        except Exception as e:
            error_msg = f"Failed to get daily stats for {current_date.strftime('%Y-%m-%d')}: {e}"
            logger.error(error_msg)
            # Add to error dates list instead of raising exception
            error_dates.append(current_date.strftime('%Y-%m-%d'))
        
        current_date += timedelta(days=1)
    
    if not daily_stats:
        logger.error("No data available for the specified period")
        return {}
    
    # Calculate weekly totals
    total_messages = sum(stats['message_count'] for stats in daily_stats)
    total_reactions = sum(stats['reaction_count'] for stats in daily_stats)
    
    # Aggregate user stats
    user_stats = {}
    for stats in daily_stats:
        for user in stats['user_stats']:
            username = user['username']
            count = user['message_count']
            if username in user_stats:
                user_stats[username] += count
            else:
                user_stats[username] = count
    
    # Sort users by message count
    top_users = [
        {"username": username, "message_count": count}
        for username, count in sorted(user_stats.items(), key=lambda x: x[1], reverse=True)
    ][:10]  # Top 10
    
    # Get hourly message counts for each day
    hourly_counts = []
    for stats in daily_stats:
        hourly_counts.extend(stats['hourly_message_counts'])
    
    # Get top posts with reactions
    top_posts = get_top_posts_with_reactions(es_client, index_name, start_date_str, end_date_str)
    
    return {
        "start_date": start_date_str,
        "end_date": end_date_str,
        "message_count": total_messages,
        "reaction_count": total_reactions,
        "top_posts": top_posts,
        "user_stats": top_users,
        "hourly_message_counts": hourly_counts,
        "error_dates": error_dates,  # Add error dates to the result
        "daily_stats": daily_stats  # Add daily stats to the result
    }


def get_top_posts_with_reactions(
    es_client: ElasticsearchClient,
    index_name: str,
    start_date: str,
    end_date: str,
    limit: int = 3
) -> List[Dict[str, Any]]:
    """
    Get top posts with most reactions
    
    Args:
        es_client: Elasticsearch client
        index_name: Index name
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        limit: Number of posts to return
        
    Returns:
        List[Dict[str, Any]]: List of top posts with reactions
    """
    # Query to get posts with reactions
    query = {
        "query": {
            "bool": {
                "must": [
                    {
                        "range": {
                            "timestamp": {
                                "gte": start_date,
                                "lte": end_date
                            }
                        }
                    },
                    {
                        "nested": {
                            "path": "reactions",
                            "query": {
                                "exists": {
                                    "field": "reactions"
                                }
                            }
                        }
                    }
                ]
            }
        },
        "aggs": {
            "total_reactions": {
                "nested": {
                    "path": "reactions"
                },
                "aggs": {
                    "sum": {
                        "sum": {
                            "field": "reactions.count"
                        }
                    }
                }
            }
        },
        "size": 100  # 十分な数を取得してからソート
    }
    
    # Execute search
    response = es_client.search(index_name, query)
    
    # Process results
    top_posts = []
    for hit in response.get("hits", {}).get("hits", []):
        source = hit.get("_source", {})
        reactions = source.get("reactions", [])
        total_reactions = sum(reaction.get("count", 0) for reaction in reactions)
        
        # Get text and limit to one line
        text = source.get("text", "")
        if "\n" in text:
            text = text.split("\n")[0] + "..."
        
        # Get Slack link
        channel_id = source.get("channel_id", "")
        thread_ts = source.get("thread_ts", "")
        ts = source.get("ts", "")
        
        # デバッグログを追加
        logger.debug(f"Message source: {source}")
        logger.debug(f"thread_ts: {thread_ts}, ts: {ts}")
        
        # thread_tsが存在する場合はそれを使用、そうでない場合はtsを使用
        message_ts = thread_ts if thread_ts else ts
        
        # どちらも存在しない場合はtimestampから抽出
        if not message_ts:
            timestamp = source.get("timestamp", "")
            if timestamp:
                # ISO 8601形式のタイムスタンプからUnixタイムスタンプを抽出
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    # ミリ秒部分を取得
                    microsecond = dt.microsecond
                    # Unixタイムスタンプ（秒）とミリ秒を結合
                    message_ts = f"{int(dt.timestamp())}{microsecond:06d}"
                except (ValueError, AttributeError):
                    logger.warning(f"Failed to parse timestamp: {timestamp}")
        
        # タイムスタンプの形式を変換（小数点を削除）
        if message_ts:
            message_ts = message_ts.replace(".", "")
        
        slack_link = f"https://slack.com/archives/{channel_id}/p{message_ts}"
        
        top_posts.append({
            "text": text,
            "slack_link": slack_link,
            "user": source.get("user", "unknown"),
            "reaction_count": total_reactions,
            "reactions": reactions
        })
    
    # Sort by total reaction count and limit
    top_posts.sort(key=lambda x: x["reaction_count"], reverse=True)
    return top_posts[:limit]


def get_user_stats(
    es_client: ElasticsearchClient,
    index_name: str,
    start_date: str,
    end_date: str
) -> List[Dict[str, Any]]:
    """
    Get user statistics for the week
    
    Args:
        es_client: Elasticsearch client
        index_name: Index name
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        
    Returns:
        List[Dict[str, Any]]: List of user statistics
    """
    # Query to get user message counts
    query = {
        "size": 0,
        "query": {
            "range": {
                "timestamp": {
                    "gte": start_date,
                    "lte": end_date
                }
            }
        },
        "aggs": {
            "users": {
                "terms": {
                    "field": "user",
                    "size": 10,
                    "order": {
                        "_count": "desc"
                    }
                }
            }
        }
    }
    
    # Execute search
    response = es_client.search(index_name, query)
    
    # Process results
    user_stats = []
    for bucket in response.get("aggregations", {}).get("users", {}).get("buckets", []):
        user_stats.append({
            "username": bucket.get("key", "unknown"),
            "message_count": bucket.get("doc_count", 0)
        })
    
    return user_stats 