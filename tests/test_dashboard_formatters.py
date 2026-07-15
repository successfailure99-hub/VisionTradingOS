"""
Tests for centralized dashboard formatters.
"""

from datetime import UTC, datetime

from dashboard import formatters


def test_missing_numeric_and_timestamp_formatting_is_deterministic():
    assert formatters.text(None) == "-"
    assert formatters.text("") == "-"
    assert formatters.price(None) == "-"
    assert formatters.price(100.125) == "100.12"
    assert formatters.ratio(2) == "2.0000"
    assert formatters.timestamp(datetime(2026, 7, 12, 9, 15, tzinfo=UTC)).startswith("2026-07-12 09:15:00")


def test_semantic_status_kinds_are_stable():
    assert formatters.semantic_kind("Running") == "positive"
    assert formatters.semantic_kind("Not Ready") == "neutral"
    assert formatters.semantic_kind("Starting") == "warning"
    assert formatters.semantic_kind("Rejected") == "negative"
    assert formatters.pnl_kind(10.0) == "positive"
    assert formatters.pnl_kind(-1.0) == "negative"
