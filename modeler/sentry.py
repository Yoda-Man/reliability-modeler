"""
Sentry Connector — pull raw failure events from Sentry and normalize them
into the exact same shape `load_failure_data()` produces, so the entire
downstream pipeline (models, graphs, dashboard) works unchanged.

Usage:
    from modeler.sentry import load_sentry_failures
    t_hours, cat_list, t0, categories = load_sentry_failures(
        org="my-org", project="my-project",
        auth_token=os.environ["SENTRY_AUTH_TOKEN"],
        config_path=Path("fault_categories.conf"),
        days=30,
        multi_label=False,
    )

Requires:
    - SENTRY_AUTH_TOKEN  (org-level token with `event:read` + `project:read`)
    - SENTRY_BASE_URL    (optional; defaults to https://sentry.io/api/0/ for self-hosted)
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from .data import load_fault_categories, categorize_description

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://sentry.io/api/0/"
PAGE_SIZE = 100  # Sentry's max page size for the events endpoint
MAX_PAGES = 50   # hard safety cap: 50 pages * 100 = 5000 events


class SentryError(Exception):
    """Raised when the Sentry API returns an error or auth fails."""


def _sentry_request(url: str, auth_token: str) -> dict:
    """Perform a single authenticated GET request against the Sentry API."""
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {auth_token}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if e.code == 401:
            raise SentryError("Sentry authentication failed (401). Check SENTRY_AUTH_TOKEN and its scopes.")
        if e.code == 404:
            raise SentryError(f"Sentry resource not found (404): {url}")
        if e.code == 429:
            raise SentryError("Sentry rate limit exceeded (429). Retry later or narrow the time window.")
        raise SentryError(f"Sentry API error {e.code}: {body[:300]}")
    except urllib.error.URLError as e:
        raise SentryError(f"Sentry network error: {e.reason}")


def _sentry_get_page(url: str, auth_token: str) -> Tuple[List[dict], Optional[str]]:
    """
    Perform a GET and return (events, next_cursor).
    Uses the Link header for pagination (Sentry's cursor-based pagination).
    """
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {auth_token}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            events = json.loads(resp.read().decode("utf-8"))
            next_cursor = _extract_next_cursor(resp.headers.get("Link", ""))
            return events, next_cursor
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if e.code == 401:
            raise SentryError("Sentry authentication failed (401). Check SENTRY_AUTH_TOKEN and its scopes.")
        if e.code == 404:
            raise SentryError(f"Sentry resource not found (404): {url}")
        if e.code == 429:
            raise SentryError("Sentry rate limit exceeded (429). Retry later or narrow the time window.")
        raise SentryError(f"Sentry API error {e.code}: {body[:300]}")
    except urllib.error.URLError as e:
        raise SentryError(f"Sentry network error: {e.reason}")


def _extract_next_cursor(link_header: str) -> Optional[str]:
    """
    Parse a Link header like:
      <...&cursor=123:0:1>; rel="next"; results="true"; cursor="123:0:1"
    Returns the cursor value, or None if there is no next page.
    """
    for part in link_header.split(","):
        if 'rel="next"' not in part:
            continue
        # The URL segment contains cursor=...
        start = part.find("<") + 1
        end = part.find(">")
        if start > 0 and end > start:
            url = part[start:end]
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            if "cursor" in qs:
                return qs["cursor"][0]
    return None


def _parse_event_timestamp(event: dict) -> Optional[datetime]:
    """Extract and normalize an event timestamp. Sentry returns ISO-8601 UTC."""
    raw = event.get("dateCreated") or event.get("dateReceived")
    if not raw:
        return None
    try:
        # Sentry timestamps are like "2025-08-01T12:34:56.789Z"
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _event_description(event: dict) -> str:
    """
    Build a human-readable description from a Sentry event.
    Priority: title > message > exception type > "Unknown error".
    Includes release + environment context so the keyword matcher can
    categorize richer data.
    """
    title = event.get("title") or ""
    message = event.get("message") or ""
    desc = title or message or "Unknown error"

    # Enrich with exception metadata if present
    if "exception" in event and isinstance(event["exception"], dict):
        values = event["exception"].get("values") or []
        if values:
            exc_type = values[0].get("type") or ""
            if exc_type:
                desc = f"{exc_type}: {desc}"

    release = event.get("release")
    environment = event.get("environment")
    if release:
        desc += f" [release: {release}]"
    if environment:
        desc += f" [environment: {environment}]"

    return desc


def load_sentry_failures(
    org: str,
    project: str,
    auth_token: str,
    config_path: Path,
    days: int = 30,
    multi_label: bool = False,
    base_url: Optional[str] = None,
) -> Tuple[np.ndarray, List[Tuple], datetime, Optional[list]]:
    """
    Pull failure events from Sentry and return the SAME normalized tuple that
    `load_failure_data()` returns:
        (t_hours: np.ndarray, cat_list: [(iso, hours, categories, desc)], t0: datetime, fault_categories)

    Args:
        org:           Sentry organization slug
        project:       Sentry project slug
        auth_token:    Sentry auth token with event:read scope
        config_path:   path to fault_categories.conf
        days:          look-back window in days
        multi_label:   allow multiple categories per event
        base_url:      override API base URL (for self-hosted Sentry)
    """
    fault_categories = load_fault_categories(config_path)
    base = (base_url or os.getenv("SENTRY_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    until = datetime.now(timezone.utc).isoformat()

    # Build the initial query URL
    params = {
        "full": "false",
        "limit": str(PAGE_SIZE),
    }
    query_string = urllib.parse.urlencode(params)
    url = f"{base}/projects/{urllib.parse.quote(org)}/{urllib.parse.quote(project)}/events/?{query_string}&statsPeriod={days}d"

    all_events: List[dict] = []
    next_cursor: Optional[str] = None
    pages = 0

    # Paginate
    while pages < MAX_PAGES:
        page_url = url
        if next_cursor:
            sep = "&" if "?" in page_url else "?"
            page_url = f"{page_url}{sep}cursor={urllib.parse.quote(next_cursor)}"

        events, next_cursor = _sentry_get_page(page_url, auth_token)
        if not events:
            break
        all_events.extend(events)
        pages += 1
        logger.info(f"Sentry: fetched page {pages} ({len(events)} events, total {len(all_events)})")
        if next_cursor is None:
            break

    if pages >= MAX_PAGES and next_cursor is not None:
        logger.warning(f"Sentry: hit MAX_PAGES ({MAX_PAGES}) cap — results may be truncated.")

    if not all_events:
        logger.warning(f"Sentry: no events found for {org}/{project} in last {days} days")
        return np.array([]), [], datetime.now(timezone.utc), fault_categories

    # Normalize into the same shape as load_failure_data
    full_events: List[Tuple[datetime, str]] = []
    for event in all_events:
        dt = _parse_event_timestamp(event)
        if dt is None:
            continue
        desc = _event_description(event)
        full_events.append((dt, desc))

    full_events.sort(key=lambda x: x[0])

    t0 = full_events[0][0]
    failure_events = []
    for dt, desc in full_events:
        cats = categorize_description(desc, fault_categories, multi_label)
        rel_hours = (dt - t0).total_seconds() / 3600.0
        if rel_hours >= 0:
            failure_events.append((dt, rel_hours, cats, desc))

    failure_events.sort(key=lambda x: x[1])
    t_hours = np.array([ev[1] for ev in failure_events])

    cat_list = []
    for ev in failure_events:
        dt_iso = ev[0].isoformat()
        time_h = round(ev[1], 4)
        cats_str = ", ".join(ev[2]) if isinstance(ev[2], list) else ev[2]
        cat_list.append((dt_iso, time_h, cats_str, ev[3]))

    logger.info(f"Sentry: processed {len(failure_events)} failure events from {org}/{project}")
    return t_hours, cat_list, t0, fault_categories
