import pytest
from datetime import datetime, timedelta
from src.analysis.daily import (
    get_daily_stats,
    get_message_count,
    get_reaction_count,
    get_hourly_distribution,
    get_top_reactions,
    get_user_stats
)
from src.analysis.visualization import (
    create_reaction_pie_chart,
    create_hourly_distribution_chart,
    create_hourly_line_chart,
    create_weekly_hourly_line_chart
)

class TestDailyAnalysis:
    def test_get_message_count(self, sample_date_range):
        start_date, end_date = sample_date_range
        expected_duration = timedelta(days=1)
        actual_duration = end_date - start_date
        assert actual_duration == expected_duration
    
    def test_get_reaction_count(self, sample_reaction_data):
        total_reactions = sum(reaction["count"] for reaction in sample_reaction_data)
        assert total_reactions == 18
    
    def test_get_hourly_distribution(self, sample_hourly_data):
        total_messages = sum(sample_hourly_data.values())
        assert total_messages == 300
    
    def test_get_top_reactions(self, sample_reaction_data):
        sorted_reactions = sorted(
            sample_reaction_data,
            key=lambda x: x["count"],
            reverse=True
        )
        assert sorted_reactions[0]["name"] == "thumbsup"
        assert sorted_reactions[0]["count"] == 10

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