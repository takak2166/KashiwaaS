#!/usr/bin/env python
"""
Setup Elasticsearch Indices

This script sets up the Elasticsearch index templates and indices for Slack messages.
"""
import argparse
import sys
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.es_client.client import ElasticsearchClient
from src.es_client.index import SLACK_INDEX_TEMPLATE, get_index_name
from src.utils.config import config
from src.utils.logger import get_logger

logger = get_logger(__name__)


def setup_template(client: ElasticsearchClient, template_name: str = "slack-messages") -> bool:
    """
    Set up the Slack messages index template
    
    Args:
        client: ElasticsearchClient instance
        template_name: Name for the template
        
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info(f"Setting up index template: {template_name}")
    
    # Create the template
    success = client.create_template(template_name, SLACK_INDEX_TEMPLATE)
    
    if success:
        logger.info(f"Successfully created template: {template_name}")
    else:
        logger.error(f"Failed to create template: {template_name}")
    
    return success


def setup_index(client: ElasticsearchClient, channel_name: str) -> bool:
    """
    Set up an index for a specific channel
    
    Args:
        client: ElasticsearchClient instance
        channel_name: Slack channel name
        
    Returns:
        bool: True if successful, False otherwise
    """
    index_name = get_index_name(channel_name)
    logger.info(f"Setting up index: {index_name}")
    
    # Create the index (will use the template)
    success = client.create_index(index_name)
    
    if success:
        logger.info(f"Successfully created index: {index_name}")
    else:
        logger.error(f"Failed to create index: {index_name}")
    
    return success


def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description="Set up Elasticsearch indices")
    parser.add_argument(
        "--channel", type=str,
        help="Channel name to create index for (default: value from environment variable)"
    )
    parser.add_argument(
        "--template-only", action="store_true",
        help="Only set up the template, not the index"
    )
    
    args = parser.parse_args()
    
    # Get channel name
    channel_name = args.channel
    if not channel_name and config and config.slack.channel_id:
        # Try to get channel name from Slack API
        try:
            from src.slack.client import SlackClient
            slack_client = SlackClient()
            channel_info = slack_client.get_channel_info()
            channel_name = channel_info.get("name")
            logger.info(f"Using channel name from API: {channel_name}")
        except Exception as e:
            logger.error(f"Failed to get channel name from API: {e}")
            logger.info("Please specify a channel name with --channel")
            return 1
    
    # Initialize Elasticsearch client
    try:
        es_client = ElasticsearchClient()
    except Exception as e:
        logger.error(f"Failed to connect to Elasticsearch: {e}")
        return 1
    
    # Set up template
    template_success = setup_template(es_client)
    
    if not template_success:
        logger.error("Failed to set up template, aborting")
        return 1
    
    # Set up index if requested
    if not args.template_only and channel_name:
        index_success = setup_index(es_client, channel_name)
        if not index_success:
            logger.error("Failed to set up index")
            return 1
    
    logger.info("Setup completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())