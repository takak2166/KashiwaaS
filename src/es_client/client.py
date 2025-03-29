"""
Elasticsearch Client
Provides a client for interacting with Elasticsearch
"""
import json
import time
from typing import Any, Dict, List, Optional, Union

from elasticsearch import Elasticsearch, helpers
from elasticsearch.exceptions import NotFoundError, ConnectionError, ConnectionTimeout, TransportError

from src.slack.message import SlackMessage
from src.utils.config import config
from src.utils.logger import get_logger
from src.utils.retry import retry_with_backoff, is_temporary_error

logger = get_logger(__name__)


def is_es_temporary_error(exception: Exception) -> bool:
    """
    Check if an Elasticsearch exception is temporary and worth retrying
    
    Args:
        exception: The exception to check
        
    Returns:
        bool: True if the exception is likely temporary
    """
    # Check for connection errors
    if isinstance(exception, (ConnectionError, ConnectionTimeout)):
        return True
    
    # Check for transport errors with 5xx status codes
    if isinstance(exception, TransportError) and hasattr(exception, 'status_code'):
        if 500 <= exception.status_code < 600:
            return True
    
    # Check for error message containing temporary error indicators
    error_str = str(exception).lower()
    temporary_indicators = [
        'timeout', 'connection', 'network', 'too many requests',
        'service unavailable', 'internal server error', 'overloaded'
    ]
    return any(indicator in error_str for indicator in temporary_indicators)


class ElasticsearchClient:
    """
    Elasticsearch Client
    
    Handles connections to Elasticsearch and provides methods for indexing and querying data.
    """
    
    def __init__(
        self,
        host: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None
    ):
        """
        Initialize the Elasticsearch client
        
        Args:
            host: Elasticsearch host URL (if not specified, retrieved from environment variables)
            user: Elasticsearch username (if not specified, retrieved from environment variables)
            password: Elasticsearch password (if not specified, retrieved from environment variables)
        """
        self.host = host or (config.elasticsearch.host if config else "http://elasticsearch:9200")
        self.user = user or (config.elasticsearch.user if config else None)
        self.password = password or (config.elasticsearch.password if config else None)
        
        # Connection options
        conn_options = {}
        if self.user and self.password:
            conn_options["basic_auth"] = (self.user, self.password)
        
        # Initialize Elasticsearch client
        self.client = Elasticsearch(self.host, **conn_options)
        
        # Check connection
        if self.client.ping():
            logger.info(f"Connected to Elasticsearch at {self.host}")
        else:
            logger.error(f"Failed to connect to Elasticsearch at {self.host}")
            raise ConnectionError(f"Could not connect to Elasticsearch at {self.host}")
    
    @retry_with_backoff(
        max_retries=3,
        initial_backoff=1.0,
        backoff_factor=2.0,
        should_retry_fn=is_es_temporary_error,
        on_retry_callback=lambda retries, e, wait_time: logger.warning(
            f"Retrying create_index after error: {e}"
        )
    )
    def create_index(self, index_name: str, settings: Optional[Dict[str, Any]] = None) -> bool:
        """
        Create an index with optional settings
        
        Args:
            index_name: Name of the index to create
            settings: Index settings and mappings
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if index already exists
            if self.client.indices.exists(index=index_name):
                logger.info(f"Index {index_name} already exists")
                return True
            
            # Create index with settings
            response = self.client.indices.create(
                index=index_name,
                settings=settings
            )
            
            logger.info(f"Created index {index_name}: {response}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create index {index_name}: {e}")
            # Don't retry if the index already exists with a different error
            if "resource_already_exists_exception" in str(e):
                logger.info(f"Index {index_name} already exists (from exception)")
                return True
            return False
    
    @retry_with_backoff(
        max_retries=3,
        initial_backoff=1.0,
        backoff_factor=2.0,
        should_retry_fn=is_es_temporary_error,
        on_retry_callback=lambda retries, e, wait_time: logger.warning(
            f"Retrying delete_index after error: {e}"
        )
    )
    def delete_index(self, index_name: str) -> bool:
        """
        Delete an index
        
        Args:
            index_name: Name of the index to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            response = self.client.indices.delete(index=index_name)
            logger.info(f"Deleted index {index_name}: {response}")
            return True
            
        except NotFoundError:
            logger.warning(f"Index {index_name} not found")
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete index {index_name}: {e}")
            # Don't retry if the index doesn't exist
            if "index_not_found_exception" in str(e):
                logger.warning(f"Index {index_name} not found (from exception)")
                return False
            return False
    
    @retry_with_backoff(
        max_retries=3,
        initial_backoff=1.0,
        backoff_factor=2.0,
        should_retry_fn=is_es_temporary_error,
        on_retry_callback=lambda retries, e, wait_time: logger.warning(
            f"Retrying create_template after error: {e}"
        )
    )
    def create_template(self, name: str, template: Dict[str, Any]) -> bool:
        """
        Create or update an index template
        
        Args:
            name: Template name
            template: Template definition
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            response = self.client.indices.put_index_template(
                name=name,
                body=template
            )
            
            logger.info(f"Created template {name}: {response}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create template {name}: {e}")
            return False
    
    @retry_with_backoff(
        max_retries=3,
        initial_backoff=1.0,
        backoff_factor=2.0,
        should_retry_fn=is_es_temporary_error,
        on_retry_callback=lambda retries, e, wait_time: logger.warning(
            f"Retrying index_document after error: {e}"
        )
    )
    def index_document(
        self,
        index_name: str,
        document: Dict[str, Any],
        doc_id: Optional[str] = None
    ) -> bool:
        """
        Index a single document
        
        Args:
            index_name: Name of the index
            document: Document to index
            doc_id: Document ID (optional)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            response = self.client.index(
                index=index_name,
                document=document,
                id=doc_id
            )
            
            logger.debug(f"Indexed document in {index_name}: {response['_id']}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to index document in {index_name}: {e}")
            return False
    
    @retry_with_backoff(
        max_retries=3,
        initial_backoff=1.0,
        backoff_factor=2.0,
        should_retry_fn=is_es_temporary_error,
        on_retry_callback=lambda retries, e, wait_time: logger.warning(
            f"Retrying bulk_index after error: {e}"
        )
    )
    def bulk_index(
        self,
        index_name: str,
        documents: List[Dict[str, Any]],
        id_field: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Bulk index multiple documents
        
        Args:
            index_name: Name of the index
            documents: List of documents to index
            id_field: Field to use as document ID (optional)
            
        Returns:
            Dict[str, int]: Statistics about the bulk operation
        """
        try:
            # Prepare actions for bulk indexing
            actions = []
            for doc in documents:
                action = {
                    "_index": index_name,
                    "_source": doc
                }
                
                # Use specified field as document ID if provided
                if id_field and id_field in doc:
                    action["_id"] = doc[id_field]
                
                actions.append(action)
            
            # Execute bulk operation
            success, failed = helpers.bulk(
                self.client,
                actions,
                stats_only=True
            )
            
            logger.info(f"Bulk indexed {success} documents in {index_name}, {failed} failed")
            return {"success": success, "failed": failed}
            
        except Exception as e:
            logger.error(f"Failed to bulk index documents in {index_name}: {e}")
            return {"success": 0, "failed": len(documents)}
    
    @retry_with_backoff(
        max_retries=2,  # Lower retry count since individual bulk operations already have retries
        initial_backoff=2.0,
        backoff_factor=2.0,
        should_retry_fn=is_es_temporary_error,
        on_retry_callback=lambda retries, e, wait_time: logger.warning(
            f"Retrying index_slack_messages after error: {e}"
        )
    )
    def index_slack_messages(
        self,
        channel_name: str,
        messages: List[SlackMessage],
        batch_size: int = 500
    ) -> Dict[str, int]:
        """
        Index Slack messages in batches
        
        Args:
            channel_name: Channel name (used for index name)
            messages: List of SlackMessage objects
            batch_size: Number of documents per batch
            
        Returns:
            Dict[str, int]: Statistics about the indexing operation
        """
        # Format index name
        index_name = f"slack-{channel_name.lower()}"
        
        # Convert messages to Elasticsearch documents
        documents = [message.to_elasticsearch_doc() for message in messages]
        
        # Process in batches
        total_success = 0
        total_failed = 0
        
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            try:
                result = self.bulk_index(index_name, batch, id_field="timestamp")
                
                total_success += result.get("success", 0)
                total_failed += result.get("failed", 0)
                
                logger.info(f"Indexed batch {i // batch_size + 1}/{(len(documents) - 1) // batch_size + 1}")
            except Exception as e:
                logger.error(f"Failed to index batch {i // batch_size + 1}: {e}")
                total_failed += len(batch)
                # Re-raise to allow retry decorator to handle it
                raise
        
        return {"success": total_success, "failed": total_failed}
    
    @retry_with_backoff(
        max_retries=3,
        initial_backoff=1.0,
        backoff_factor=2.0,
        should_retry_fn=is_es_temporary_error,
        on_retry_callback=lambda retries, e, wait_time: logger.warning(
            f"Retrying search after error: {e}"
        )
    )
    def search(
        self,
        index_name: str,
        query: Dict[str, Any],
        size: int = 10,
        from_: int = 0
    ) -> Dict[str, Any]:
        """
        Search for documents
        
        Args:
            index_name: Name of the index to search
            query: Elasticsearch query
            size: Number of results to return (ignored if size is in query)
            from_: Starting offset (ignored if from is in query)
            
        Returns:
            Dict[str, Any]: Search results
        """
        try:
            # Check if size or from are already in the query
            params = {"index": index_name}
            
            # Use body parameter instead of directly passing query
            params["body"] = query
            
            # Only add size and from if not already in query
            if "size" not in query:
                params["size"] = size
            
            if "from" not in query:
                params["from_"] = from_
            
            response = self.client.search(**params)
            
            return response
            
        except Exception as e:
            logger.error(f"Search failed in {index_name}: {e}")
            # Don't retry if the index doesn't exist
            if "index_not_found_exception" in str(e):
                logger.warning(f"Index {index_name} not found (from exception)")
                return {"error": f"Index {index_name} not found", "status": "not_found"}
            return {"error": str(e)}