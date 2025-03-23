"""
Tests for Elasticsearch functionality
"""
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from elasticsearch import Elasticsearch

from src.es_client.client import ElasticsearchClient
from src.es_client.index import SLACK_INDEX_TEMPLATE, get_index_name
from src.es_client.query import (
    bool_query, date_range_query, match_query, term_query, terms_query
)
from src.slack.message import SlackMessage, SlackReaction


class TestElasticsearchClient:
    """Tests for ElasticsearchClient class"""
    
    @pytest.mark.skipif(not os.getenv("ELASTICSEARCH_HOST"), reason="ELASTICSEARCH_HOST not set")
    def test_connection(self):
        """Test connection to Elasticsearch"""
        client = ElasticsearchClient()
        assert client.client.ping() is True
    
    @patch("src.es_client.client.Elasticsearch")
    def test_init_with_auth(self, mock_elasticsearch):
        """Test initialization with authentication"""
        # Setup mock
        mock_es_instance = MagicMock()
        mock_elasticsearch.return_value = mock_es_instance
        mock_es_instance.ping.return_value = True
        
        # Create client with auth
        client = ElasticsearchClient(
            host="http://localhost:9200",
            user="user",
            password="password"
        )
        
        # Verify Elasticsearch was initialized with auth
        mock_elasticsearch.assert_called_once()
        call_args = mock_elasticsearch.call_args[1]
        assert "basic_auth" in call_args
        assert call_args["basic_auth"] == ("user", "password")
    
    @patch("src.es_client.client.Elasticsearch")
    def test_create_index(self, mock_elasticsearch):
        """Test create_index method"""
        # Setup mock
        mock_es_instance = MagicMock()
        mock_elasticsearch.return_value = mock_es_instance
        mock_es_instance.ping.return_value = True
        mock_es_instance.indices.exists.return_value = False
        mock_es_instance.indices.create.return_value = {"acknowledged": True}
        
        # Create client and index
        client = ElasticsearchClient()
        result = client.create_index("test-index")
        
        # Verify
        assert result is True
        mock_es_instance.indices.exists.assert_called_once_with(index="test-index")
        mock_es_instance.indices.create.assert_called_once()
    
    @patch("src.es_client.client.Elasticsearch")
    def test_create_template(self, mock_elasticsearch):
        """Test create_template method"""
        # Setup mock
        mock_es_instance = MagicMock()
        mock_elasticsearch.return_value = mock_es_instance
        mock_es_instance.ping.return_value = True
        mock_es_instance.indices.put_index_template.return_value = {"acknowledged": True}
        
        # Create client and template
        client = ElasticsearchClient()
        result = client.create_template("test-template", SLACK_INDEX_TEMPLATE)
        
        # Verify
        assert result is True
        mock_es_instance.indices.put_index_template.assert_called_once_with(
            name="test-template",
            body=SLACK_INDEX_TEMPLATE
        )
    
    @patch("src.es_client.client.Elasticsearch")
    def test_index_document(self, mock_elasticsearch):
        """Test index_document method"""
        # Setup mock
        mock_es_instance = MagicMock()
        mock_elasticsearch.return_value = mock_es_instance
        mock_es_instance.ping.return_value = True
        mock_es_instance.index.return_value = {"_id": "test-id", "result": "created"}
        
        # Create client and index document
        client = ElasticsearchClient()
        document = {"field1": "value1", "field2": 42}
        result = client.index_document("test-index", document, doc_id="test-id")
        
        # Verify
        assert result is True
        mock_es_instance.index.assert_called_once_with(
            index="test-index",
            document=document,
            id="test-id"
        )
    
    @patch("src.es_client.client.Elasticsearch")
    @patch("src.es_client.client.helpers.bulk")
    def test_bulk_index(self, mock_bulk, mock_elasticsearch):
        """Test bulk_index method"""
        # Setup mocks
        mock_es_instance = MagicMock()
        mock_elasticsearch.return_value = mock_es_instance
        mock_es_instance.ping.return_value = True
        mock_bulk.return_value = (10, 0)  # (success, failed)
        
        # Create client and bulk index
        client = ElasticsearchClient()
        documents = [
            {"id": 1, "field1": "value1"},
            {"id": 2, "field1": "value2"},
            {"id": 3, "field1": "value3"},
        ]
        result = client.bulk_index("test-index", documents, id_field="id")
        
        # Verify
        assert result == {"success": 10, "failed": 0}
        mock_bulk.assert_called_once()
        # Check that actions were created correctly
        actions = mock_bulk.call_args[0][1]
        assert len(actions) == 3
        assert all(action["_index"] == "test-index" for action in actions)
        assert actions[0]["_id"] == 1
        assert actions[1]["_id"] == 2
        assert actions[2]["_id"] == 3
    
    @patch("src.es_client.client.Elasticsearch")
    @patch("src.es_client.client.helpers.bulk")
    def test_index_slack_messages(self, mock_bulk, mock_elasticsearch):
        """Test index_slack_messages method"""
        # Setup mocks
        mock_es_instance = MagicMock()
        mock_elasticsearch.return_value = mock_es_instance
        mock_es_instance.ping.return_value = True
        mock_bulk.return_value = (2, 0)  # (success, failed)
        
        # Create test messages
        messages = [
            SlackMessage(
                channel_id="C12345",
                ts="1609459200.000000",
                user_id="U12345",
                username="user1",
                text="Test message 1",
                timestamp=datetime(2021, 1, 1, 0, 0, 0),
                is_weekend=False,
                hour_of_day=0,
                day_of_week=4,
                reactions=[SlackReaction(name="thumbsup", count=1)]
            ),
            SlackMessage(
                channel_id="C12345",
                ts="1609459300.000000",
                user_id="U67890",
                username="user2",
                text="Test message 2",
                timestamp=datetime(2021, 1, 1, 0, 1, 40),
                is_weekend=False,
                hour_of_day=0,
                day_of_week=4
            )
        ]
        
        # Create client and index messages
        client = ElasticsearchClient()
        result = client.index_slack_messages("general", messages)
        
        # Verify
        assert result == {"success": 2, "failed": 0}
        mock_bulk.assert_called_once()
        # Check that actions were created correctly
        actions = mock_bulk.call_args[0][1]
        assert len(actions) == 2
        assert all(action["_index"] == "slack-general" for action in actions)
        assert all("_source" in action for action in actions)


class TestElasticsearchIndex:
    """Tests for Elasticsearch index functions"""
    
    def test_get_index_name(self):
        """Test get_index_name function"""
        assert get_index_name("general") == "slack-general"
        assert get_index_name("random-stuff") == "slack-random-stuff"
        assert get_index_name("Team Discussion") == "slack-team-discussion"
        assert get_index_name("project.updates") == "slack-project-updates"


class TestElasticsearchQuery:
    """Tests for Elasticsearch query functions"""
    
    def test_match_query(self):
        """Test match_query function"""
        query = match_query("text", "hello world")
        assert query == {"match": {"text": "hello world"}}
    
    def test_term_query(self):
        """Test term_query function"""
        query = term_query("user_id", "U12345")
        assert query == {"term": {"user_id": "U12345"}}
    
    def test_terms_query(self):
        """Test terms_query function"""
        query = terms_query("day_of_week", [0, 1, 2, 3, 4])
        assert query == {"terms": {"day_of_week": [0, 1, 2, 3, 4]}}
    
    def test_date_range_query(self):
        """Test date_range_query function"""
        start_date = datetime(2021, 1, 1)
        end_date = datetime(2021, 1, 31)
        query = date_range_query("timestamp", start_date, end_date)
        
        assert query["range"]["timestamp"]["gte"] == start_date.isoformat()
        assert query["range"]["timestamp"]["lte"] == end_date.isoformat()
    
    def test_bool_query(self):
        """Test bool_query function"""
        must_queries = [
            match_query("text", "important"),
            term_query("is_weekend", False)
        ]
        should_queries = [
            match_query("text", "urgent"),
            match_query("text", "critical")
        ]
        must_not_queries = [
            term_query("user_id", "U00000")
        ]
        
        query = bool_query(
            must=must_queries,
            should=should_queries,
            must_not=must_not_queries
        )
        
        assert query["bool"]["must"] == must_queries
        assert query["bool"]["should"] == should_queries
        assert query["bool"]["must_not"] == must_not_queries