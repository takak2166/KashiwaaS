"""
Tests for analysis module.
"""

from unittest.mock import Mock

import pytest

from src.analysis.daily import get_daily_stats
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
            "took": 1,
            "timed_out": False,
            "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
            "hits": {"total": {"value": 13, "relation": "eq"}, "max_score": None, "hits": []},
            "aggregations": {
                "reactions_nested": {
                    "doc_count": 3,
                    "total_count": {
                        "value": 3.0,
                    },
                }
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
        assert "hourly_message_counts" in result

        # Verify ES client method calls
        assert mock_es_client.search.call_count >= 1

        # Verify date format
        assert result["date"] == start_date.strftime("%Y-%m-%d")

        # Verify message count
        assert result["message_count"] == 13

        # Verify hourly message counts
        assert len(result["hourly_message_counts"]) == 24
        assert isinstance(result["hourly_message_counts"], list)


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
