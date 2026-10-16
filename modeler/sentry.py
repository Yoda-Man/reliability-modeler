"""
Sentry Connector — pull raw failure events from Sentry and normalize them
into the shape the analysis pipeline expects:
    (t_hours, cat_list, t0, fault_categories)
where cat_list = [(iso, hours, categories, desc), ...]

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

import email.utils
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .data import load_fault_categories, categorize_description

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://sentry.io/api/0/"
PAGE_SIZE = 100  # Sentry's max page size for the events endpoint
MAX_PAGES = 50   # hard safety cap: 50 pages * 100 = 5000 events
MAX_PROJECT_PAGES = 20  # orgs rarely exceed 2000 projects
DEFAULT_MAX_PROJECTS = 50  # cap for "all projects" aggregation
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3          # retries after the first attempt for 429 / 5xx
BACKOFF_BASE_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_SLUG_RE = re.compile(r'^[a-zA-Z0-9._-]+$')


class SentryError(Exception):
    """Raised when the Sentry API returns an error or auth fails."""


class SentryCancelled(SentryError):
    """Raised when a fetch is abandoned because its cancel event was set."""


def _sleep(seconds: float, cancel_event: Optional[threading.Event]) -> None:
    """Sleep that wakes early (and raises) when the fetch is cancelled."""
    if cancel_event is None:
        time.sleep(seconds)
        return
    if cancel_event.wait(seconds):
        raise SentryCancelled("Sentry fetch cancelled")


def _check_cancelled(cancel_event: Optional[threading.Event]) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise SentryCancelled("Sentry fetch cancelled")


def _base_url(base_url: Optional[str]) -> str:
    return (base_url or os.getenv("SENTRY_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")


def _validate_slug(value: str, name: str) -> str:
    """Validate a Sentry org/project slug (defense in depth against URL injection)."""
    if not value or not _SLUG_RE.match(value):
        raise SentryError(f"Invalid {name} slug: {value!r}")
    return value


def _retry_delay(attempt: int, retry_after: Optional[str]) -> float:
    """Seconds to wait before retry ``attempt`` (1-based), honouring Retry-After."""
    if retry_after:
        retry_after = retry_after.strip()
        try:
            return min(MAX_BACKOFF_SECONDS, max(0.0, float(retry_after)))
        except ValueError:
            try:
                when = email.utils.parsedate_to_datetime(retry_after)
                delta = (when - datetime.now(timezone.utc)).total_seconds()
                return min(MAX_BACKOFF_SECONDS, max(0.0, delta))
            except (TypeError, ValueError):
                pass
    return min(MAX_BACKOFF_SECONDS, BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))


def _http_error_message(code: int, resource: str) -> str:
    if code == 401:
        return "Sentry authentication failed (401). Check SENTRY_AUTH_TOKEN and its scopes."
    if code == 403:
        return "Sentry denied access (403). Check SENTRY_AUTH_TOKEN scopes."
    if code == 404:
        return f"Sentry {resource} not found (404). Check the slug."
    if code == 429:
        return "Sentry rate limit exceeded (429). Retry later or narrow the time window."
    return f"Sentry API error (HTTP {code})"


def _sentry_get_page(
    url: str,
    auth_token: str,
    resource: str = "resource",
    cancel_event: Optional[threading.Event] = None,
) -> Tuple[list, Optional[str]]:
    """
    Perform a GET and return (json_list, next_cursor).

    Uses the Link header for pagination (Sentry's cursor-based pagination).
    Retries up to MAX_RETRIES times on 429 / 5xx and transient network errors,
    honouring Retry-After when present, otherwise exponential backoff.
    """
    attempt = 0
    while True:
        _check_cancelled(cancel_event)
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {auth_token}")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
                try:
                    data = json.loads(resp.read().decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as e:
                    raise SentryError("Sentry returned a malformed (non-JSON) response") from e
                if not isinstance(data, list):
                    raise SentryError("Sentry returned an unexpected response shape (expected a list)")
                return data, _extract_next_cursor(resp.headers.get("Link", ""))
        except urllib.error.HTTPError as e:
            if e.code in _RETRYABLE_STATUS and attempt < MAX_RETRIES:
                attempt += 1
                delay = _retry_delay(attempt, e.headers.get("Retry-After") if e.headers else None)
                logger.warning("Sentry HTTP %d for %s; retry %d/%d in %.1fs",
                               e.code, resource, attempt, MAX_RETRIES, delay)
                _sleep(delay, cancel_event)
                continue
            raise SentryError(_http_error_message(e.code, resource)) from e
        except urllib.error.URLError as e:
            if attempt < MAX_RETRIES:
                attempt += 1
                delay = _retry_delay(attempt, None)
                logger.warning("Sentry network error for %s (%s); retry %d/%d in %.1fs",
                               resource, e.reason, attempt, MAX_RETRIES, delay)
                _sleep(delay, cancel_event)
                continue
            raise SentryError(f"Sentry network error: {e.reason}") from e


def _paginate(
    url: str,
    auth_token: str,
    max_pages: int,
    resource: str,
    cancel_event: Optional[threading.Event] = None,
) -> Tuple[List[dict], bool]:
    """Follow cursor pagination. Returns (items, truncated)."""
    items: List[dict] = []
    next_cursor: Optional[str] = None
    pages = 0
    while pages < max_pages:
        page_url = url
        if next_cursor:
            sep = "&" if "?" in page_url else "?"
            page_url = f"{page_url}{sep}cursor={urllib.parse.quote(next_cursor, safe='')}"
        page, next_cursor = _sentry_get_page(page_url, auth_token, resource, cancel_event)
        if not page:
            return items, False
        items.extend(page)
        pages += 1
        if next_cursor is None:
            return items, False
    return items, next_cursor is not None


def _extract_next_cursor(link_header: str) -> Optional[str]:
    """
    Parse a Link header like:
      <...&cursor=123:0:1>; rel="next"; results="true"; cursor="123:0:1"
    Returns the cursor value, or None if there is no next page.
    Sentry always sends a next link; results="false" marks the end.
    """
    for part in link_header.split(","):
        if 'rel="next"' not in part:
            continue
        if 'results="false"' in part:
            return None
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
    if not isinstance(event, dict):
        return None
    raw = event.get("dateCreated") or event.get("dateReceived")
    if not raw or not isinstance(raw, str):
        return None
    try:
        # Sentry timestamps are like "2025-08-01T12:34:56.789Z"
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
        if values and isinstance(values[0], dict):
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


def _events_to_raw(events: List[dict], source: str, tag: Optional[str] = None) -> List[Tuple[datetime, str]]:
    """Convert Sentry events to (datetime, description) pairs.

    Events without a parseable timestamp are dropped; the number dropped is
    logged so data loss is visible in the logs.
    """
    raw: List[Tuple[datetime, str]] = []
    dropped = 0
    for event in events:
        dt = _parse_event_timestamp(event)
        if dt is None:
            dropped += 1
            continue
        desc = _event_description(event)
        raw.append((dt, f"[project: {tag}] {desc}" if tag else desc))
    if dropped:
        logger.warning("Sentry: dropped %d of %d events from %s with missing/unparseable timestamps",
                       dropped, len(events), source)
    return raw


def list_sentry_projects(
    org: str,
    auth_token: str,
    base_url: Optional[str] = None,
    cancel_event: Optional[threading.Event] = None,
) -> List[dict]:
    """
    List all projects in a Sentry organization.

    Returns a list of dicts with keys like: slug, name, platform, status.
    """
    org = _validate_slug(org, "org")
    url = f"{_base_url(base_url)}/organizations/{urllib.parse.quote(org, safe='')}/projects/"
    projects, truncated = _paginate(url, auth_token, MAX_PROJECT_PAGES, "organization", cancel_event)
    if truncated:
        logger.warning("Sentry: org '%s' project list truncated at %d pages", org, MAX_PROJECT_PAGES)
    logger.info("Sentry: found %d projects in org '%s'", len(projects), org)
    return projects


def _fetch_project_events(
    org: str,
    project: str,
    auth_token: str,
    base_url: str,
    days: int,
    cancel_event: Optional[threading.Event] = None,
) -> Tuple[List[dict], bool]:
    """Fetch raw event dicts for a single project, with pagination.

    Returns (events, truncated); ``truncated`` is True when the MAX_PAGES cap
    was hit, i.e. the oldest events in the window were not fetched (Sentry
    returns newest first).
    """
    org = _validate_slug(org, "org")
    project = _validate_slug(project, "project")
    base = base_url.rstrip("/")
    query_string = urllib.parse.urlencode({
        "full": "false",
        "limit": str(PAGE_SIZE),
        "statsPeriod": f"{int(days)}d",
    })
    url = (f"{base}/projects/{urllib.parse.quote(org, safe='')}/"
           f"{urllib.parse.quote(project, safe='')}/events/?{query_string}")

    events, truncated = _paginate(url, auth_token, MAX_PAGES, "project", cancel_event)
    if truncated:
        logger.warning("Sentry: %s hit MAX_PAGES (%d) — results truncated.", project, MAX_PAGES)
    return events, truncated


def _normalize_raw_events(
    raw_events: List[Tuple[datetime, str]],
    fault_categories: Optional[list],
    multi_label: bool,
) -> Tuple[np.ndarray, List[Tuple], datetime]:
    """Normalize (datetime, desc) pairs into (t_hours, cat_list, t0)."""
    if not raw_events:
        return np.array([]), [], datetime.now(timezone.utc)

    raw_events.sort(key=lambda x: x[0])
    t0 = raw_events[0][0]

    failure_events = []
    for dt, desc in raw_events:
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

    return t_hours, cat_list, t0


def load_sentry_failures(
    org: str,
    project: str,
    auth_token: str,
    config_path: Path,
    days: int = 30,
    multi_label: bool = False,
    base_url: Optional[str] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Tuple[np.ndarray, List[Tuple], datetime, list]:
    """
    Pull failure events from a single Sentry project and return the normalized
    tuple the analysis pipeline expects:
        (t_hours: np.ndarray, cat_list: [(iso, hours, categories, desc)], t0: datetime, fault_categories)

    Raises TaxonomyError if the taxonomy cannot be loaded, SentryError on API
    failures and SentryCancelled if ``cancel_event`` is set mid-fetch.
    """
    fault_categories = load_fault_categories(config_path)
    all_events, _ = _fetch_project_events(org, project, auth_token, _base_url(base_url), days, cancel_event)

    if not all_events:
        logger.warning("Sentry: no events found for %s/%s in last %d days", org, project, days)
        return np.array([]), [], datetime.now(timezone.utc), fault_categories

    raw_events = _events_to_raw(all_events, f"{org}/{project}")
    t_hours, cat_list, t0 = _normalize_raw_events(raw_events, fault_categories, multi_label)
    logger.info("Sentry: processed %d failure events from %s/%s", len(cat_list), org, project)
    return t_hours, cat_list, t0, fault_categories


def load_sentry_failures_all(
    org: str,
    auth_token: str,
    config_path: Path,
    days: int = 30,
    multi_label: bool = False,
    base_url: Optional[str] = None,
    max_projects: Optional[int] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Tuple[np.ndarray, List[Tuple], datetime, list, Dict[str, int], bool]:
    """
    Pull failure events from ALL projects in an org and aggregate them into a
    single system-wide timeline. Returns:
        (t_hours, cat_list, t0, fault_categories, project_counts, truncated)

    project_counts maps project name -> number of failure events, for a
    per-project breakdown. Each event description is tagged with its project.

    Each project is capped at MAX_PAGES * PAGE_SIZE events (newest first). If
    any project hit the cap, its history starts later than the others', which
    would skew the merged timeline; so every project is trimmed to start at
    the latest "oldest kept event" among the truncated projects, and
    ``truncated`` is True.
    """
    fault_categories = load_fault_categories(config_path)
    base = _base_url(base_url)

    projects = list_sentry_projects(org, auth_token, base, cancel_event)
    if max_projects is None:
        max_projects = DEFAULT_MAX_PROJECTS
    if len(projects) > max_projects:
        logger.warning("Sentry: org '%s' has %d projects; only the first %d are analysed",
                       org, len(projects), max_projects)
    projects = projects[:max_projects]

    if not projects:
        logger.warning("Sentry: no projects found in org '%s'", org)
        return np.array([]), [], datetime.now(timezone.utc), fault_categories, {}, False

    per_project: List[Tuple[str, List[Tuple[datetime, str]]]] = []
    cutoff: Optional[datetime] = None

    for p in projects:
        _check_cancelled(cancel_event)
        slug = p.get("slug", "") if isinstance(p, dict) else ""
        if not slug:
            continue
        name = p.get("name") or slug
        try:
            events, project_truncated = _fetch_project_events(org, slug, auth_token, base, days, cancel_event)
        except SentryCancelled:
            raise
        except SentryError as e:
            logger.warning("Sentry: skipping project %s: %s", slug, e)
            continue

        raw = _events_to_raw(events, f"{org}/{slug}", tag=name)
        per_project.append((name, raw))
        if project_truncated and raw:
            oldest = min(dt for dt, _ in raw)
            cutoff = oldest if cutoff is None else max(cutoff, oldest)
        logger.info("Sentry: %s (%s) -> %d events", name, slug, len(raw))

    if cutoff is not None:
        logger.warning("Sentry: event cap hit in org '%s'; trimming every project's events to "
                       "start at %s so the merged timeline is not skewed", org, cutoff.isoformat())
    all_raw: List[Tuple[datetime, str]] = []
    project_counts: Dict[str, int] = {}
    for name, raw in per_project:
        if cutoff is not None:
            raw = [ev for ev in raw if ev[0] >= cutoff]
        all_raw.extend(raw)
        project_counts[name] = len(raw)
    truncated = cutoff is not None

    if not all_raw:
        logger.warning("Sentry: no events across %d projects in %s", len(projects), org)
        return np.array([]), [], datetime.now(timezone.utc), fault_categories, project_counts, truncated

    t_hours, cat_list, t0 = _normalize_raw_events(all_raw, fault_categories, multi_label)
    logger.info("Sentry: aggregated %d events across %d projects in %s",
                len(cat_list), len(project_counts), org)
    return t_hours, cat_list, t0, fault_categories, project_counts, truncated
