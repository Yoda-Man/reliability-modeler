"""
Unit tests for the Sentry connector — no network access required.

Tests the pure helper functions: cursor parsing, timestamp parsing,
and description building.
"""
import pytest
from datetime import datetime, timezone

from modeler.sentry import (
    _extract_next_cursor,
    _parse_event_timestamp,
    _event_description,
)


def test_extract_next_cursor_with_next():
    link = '<https://sentry.io/api/0/projects/org/proj/events/?cursor=123:0:1>; rel="next"; results="true"; cursor="123:0:1"'
    assert _extract_next_cursor(link) == "123:0:1"


def test_extract_next_cursor_none():
    # No rel="next" means no more pages
    link = '<https://sentry.io/api/0/projects/org/proj/events/?cursor=123:0:1>; rel="prev"; results="true"; cursor="123:0:1"'
    assert _extract_next_cursor(link) is None


def test_extract_next_cursor_empty():
    assert _extract_next_cursor("") is None


def test_parse_event_timestamp_zulu():
    event = {"dateCreated": "2025-08-01T12:34:56.789Z"}
    dt = _parse_event_timestamp(event)
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.year == 2025
    assert dt.month == 8
    assert dt.day == 1


def test_parse_event_timestamp_with_offset():
    event = {"dateCreated": "2025-08-01T12:34:56+00:00"}
    dt = _parse_event_timestamp(event)
    assert dt is not None
    assert dt.hour == 12


def test_parse_event_timestamp_missing():
    assert _parse_event_timestamp({}) is None
    assert _parse_event_timestamp({"dateCreated": "not-a-date"}) is None


def test_event_description_title():
    event = {"title": "NullPointerException in auth module"}
    desc = _event_description(event)
    assert "NullPointerException" in desc


def test_event_description_with_context():
    event = {
        "title": "Timeout",
        "release": "v2.4.0",
        "environment": "production",
    }
    desc = _event_description(event)
    assert "Timeout" in desc
    assert "release: v2.4.0" in desc
    assert "environment: production" in desc


def test_event_description_exception_type():
    event = {
        "message": "Connection refused",
        "exception": {"values": [{"type": "DatabaseConnectionError"}]},
    }
    desc = _event_description(event)
    assert "DatabaseConnectionError" in desc
    assert "Connection refused" in desc


def test_normalize_raw_events_sorts_and_offsets():
    """Verify _normalize_raw_events produces sorted relative hours from a common t0."""
    from modeler.sentry import _normalize_raw_events

    t0 = datetime(2025, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
    raw = [
        (t0.replace(hour=2), "first"),      # 2h after t0
        (t0, "origin"),                     # 0h
        (t0.replace(hour=1), "middle"),     # 1h after t0
    ]
    # Simple fake categories: one category matching everything
    categories = [("General", {"first", "origin", "middle"})]

    t_hours, cat_list, _ = _normalize_raw_events(raw, categories, multi_label=False)

    assert len(t_hours) == 3
    # t_hours should be sorted ascending [0, 1, 2]
    assert list(t_hours) == sorted(t_hours)
    assert cat_list[0][1] == 0.0  # earliest event first
    assert cat_list[-1][1] == 2.0  # latest event last


def test_normalize_raw_events_empty():
    from modeler.sentry import _normalize_raw_events
    t_hours, cat_list, t0 = _normalize_raw_events([], None, False)
    assert len(t_hours) == 0
    assert len(cat_list) == 0
    assert t0 is not None


def test_validate_slug_rejects_path_traversal():
    from modeler.sentry import _validate_slug, SentryError
    for bad in ["../etc/passwd", "foo/bar", "org/project", "", None, "..\\..\\x"]:
        try:
            _validate_slug(bad, "org")
            assert False, f"Should have rejected {bad!r}"
        except SentryError:
            pass


def test_validate_slug_accepts_valid():
    from modeler.sentry import _validate_slug
    assert _validate_slug("my-org", "org") == "my-org"
    assert _validate_slug("web_app.v2", "project") == "web_app.v2"
