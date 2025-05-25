"""
Test configuration and fixtures.
"""

from datetime import datetime

import pytest


@pytest.fixture
def sample_date():
    return datetime(2024, 1, 1)


@pytest.fixture
def sample_date_range():
    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 2)
    return start, end


@pytest.fixture
def sample_hourly_data():
    return {hour: count for hour, count in enumerate(range(1, 25))}


@pytest.fixture
def sample_reaction_data():
    return [
        {"name": "thumbsup", "count": 10},
        {"name": "smile", "count": 5},
        {"name": "heart", "count": 3},
    ]
