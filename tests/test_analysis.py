"""
Tests for analysis module.
"""

from unittest.mock import Mock

import pytest

from src.analysis.daily import get_daily_stats, get_user_stats
from src.analysis.visualization import (
    create_hourly_distribution_chart,
    create_hourly_line_chart,
    create_reaction_pie_chart,
)


class TestDailyAnalysis:
    @pytest.fixture
    def mock_es_client(self):
        """
        Mock Elasticsearch client fixture that simulates ES responses
        and allows verification of method calls
        """
        mock_client = Mock()
        # Configure mock responses to simulate Elasticsearch behavior
        mock_client.search.return_value = {
            "hits": {"total": {"value": 100}},
            "aggregations": {
                "hourly": {
                    "buckets": [
                        {"key_as_string": "2024-01-01 00:00:00", "doc_count": 10},
                        {"key_as_string": "2024-01-01 01:00:00", "doc_count": 20},
                    ]
                },
                "users": {
                    "buckets": [
                        {"key": "user1", "doc_count": 50},
                        {"key": "user2", "doc_count": 30},
                    ]
                },
            },
        }
        return mock_client

    def test_get_daily_stats(self, mock_es_client, sample_date_range):
        """Test get_daily_stats function with mocked ES client"""
        start_date, end_date = sample_date_range
        channel_name = "test-channel"

        result = get_daily_stats(channel_name, start_date, mock_es_client)

        # Verify basic structure
        assert isinstance(result, dict)
        assert "date" in result
        assert "message_count" in result
        assert "reaction_count" in result
        assert "user_stats" in result
        assert "hourly_message_counts" in result

        # Verify ES client method calls
        assert mock_es_client.search.call_count >= 1

        # Verify date format
        assert result["date"] == start_date.strftime("%Y-%m-%d")

        # Verify message count
        assert result["message_count"] == 100

        # Verify hourly message counts
        assert len(result["hourly_message_counts"]) == 24
        assert isinstance(result["hourly_message_counts"], list)

    def test_get_user_stats(self, mock_es_client, sample_date_range):
        """Test get_user_stats function with mocked ES client"""
        start_date, end_date = sample_date_range
        index_name = "test-index"

        result = get_user_stats(
            mock_es_client,
            index_name,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
        )

        # Verify basic structure
        assert isinstance(result, list)
        assert len(result) == 2

        # Verify user statistics
        assert result[0]["username"] == "user1"
        assert result[0]["message_count"] == 50
        assert result[1]["username"] == "user2"
        assert result[1]["message_count"] == 30

        # Verify ES client method call
        mock_es_client.search.assert_called_once()


class TestVisualization:
    def test_create_reaction_pie_chart(self, sample_reaction_data):
        fig = create_reaction_pie_chart(sample_reaction_data)
        assert fig is not None
        assert len(fig.axes) > 0

    def test_create_hourly_distribution_chart(self, sample_hourly_data):
        fig = create_hourly_distribution_chart(sample_hourly_data)
        assert fig is not None
        assert len(fig.axes) > 0

    def test_create_hourly_line_chart(self, sample_hourly_data):
        fig = create_hourly_line_chart(sample_hourly_data)
        assert fig is not None
        assert len(fig.axes) > 0

    def test_chart_data_validation(self, sample_hourly_data):
        assert all(isinstance(hour, int) for hour in sample_hourly_data.keys())
        assert all(isinstance(count, int) for count in sample_hourly_data.values())
        assert all(0 <= hour < 24 for hour in sample_hourly_data.keys())
