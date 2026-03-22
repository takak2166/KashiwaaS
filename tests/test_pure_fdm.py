"""
Unit tests for pure pipeline helpers (no ES/Slack I/O).
"""

from datetime import datetime, timedelta

from src.analysis.daily_pipeline import (
    parse_hourly_buckets_to_counts,
    parse_search_total_hits,
)
from src.analysis.visualization_prep import (
    aggregate_reaction_totals_from_top_posts,
    build_weekly_two_hour_series,
)
from src.analysis.weekly_pipeline import sort_and_limit_top_posts
from src.bot.report_payloads import build_daily_report_payload
from src.cli.fetch_pipeline import build_dummy_slack_raw_messages, resolve_fetch_window
from src.es_client.query import timestamp_range_query
from src.slack.message import extract_mentions, map_reactions


class TestDailyPipeline:
    def test_parse_search_total_hits(self):
        assert parse_search_total_hits({"hits": {"total": {"value": 42}}}) == 42
        assert parse_search_total_hits({"hits": {"total": 7}}) == 7

    def test_parse_hourly_buckets(self):
        resp = {
            "aggregations": {
                "hourly": {
                    "buckets": [
                        {"key_as_string": "2025-01-01 03:00:00", "doc_count": 5},
                    ]
                }
            }
        }
        counts = parse_hourly_buckets_to_counts(resp)
        assert len(counts) == 24
        assert counts[3] == 5


class TestWeeklyPipeline:
    def test_sort_and_limit_top_posts(self):
        posts = [
            {"reaction_count": 1, "text": "a"},
            {"reaction_count": 9, "text": "b"},
            {"reaction_count": 5, "text": "c"},
        ]
        out = sort_and_limit_top_posts(posts, 2)
        assert [p["reaction_count"] for p in out] == [9, 5]


class TestVisualizationPrep:
    def test_build_weekly_two_hour_series(self):
        start = datetime(2025, 1, 1)
        hourly = [1] * (7 * 24)
        counts, labels = build_weekly_two_hour_series(start, hourly)
        assert len(counts) == 7 * 12
        assert labels[0].startswith("2025-01-01 00:00")

    def test_aggregate_reactions(self):
        posts = [
            {"reactions": [{"name": "a", "count": 2}, {"name": "b", "count": 1}]},
            {"reactions": [{"name": "a", "count": 3}]},
        ]
        agg = aggregate_reaction_totals_from_top_posts(posts, limit=5)
        names = {x["name"]: x["count"] for x in agg}
        assert names["a"] == 5
        assert names["b"] == 1


class TestSlackMappers:
    def test_extract_mentions(self):
        assert extract_mentions("hi <@U123> there <@U999>") == ["U123", "U999"]
        assert extract_mentions("") == []

    def test_map_reactions(self):
        r = map_reactions([{"name": "thumbsup", "count": 2, "users": ["U1"]}])
        assert len(r) == 1
        assert r[0].name == "thumbsup"
        assert r[0].count == 2


class TestReportPayloads:
    def test_build_daily_report_payload(self):
        stats = {"date": "2025-01-01", "message_count": 1, "reaction_count": 0, "hourly_message_counts": [0] * 24}
        p = build_daily_report_payload(stats)
        assert "2025-01-01" in p.formatted_text
        assert p.stats == stats


class TestFetchPipeline:
    def test_resolve_fetch_window(self):
        end = datetime(2025, 1, 10, 12, 0, 0)
        s, e = resolve_fetch_window(end, days=1, fetch_all=False)
        assert s == end - timedelta(days=1)
        assert e == end
        s2, e2 = resolve_fetch_window(end, days=1, fetch_all=True)
        assert s2 is None
        assert e2 == end

    def test_dummy_messages(self):
        name, msgs = build_dummy_slack_raw_messages(10)
        assert name == "dummy-channel"
        assert len(msgs) == 10
        assert "reactions" in msgs[0]


class TestEsQueryHelpers:
    def test_timestamp_range_query(self):
        q = timestamp_range_query("timestamp", gte="2025-01-01", lt="2025-01-02", time_zone="+09:00")
        assert q["range"]["timestamp"]["gte"] == "2025-01-01"
        assert q["range"]["timestamp"]["time_zone"] == "+09:00"
