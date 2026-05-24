from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

import httpx

log = logging.getLogger(__name__)

_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
_MAX_RETRIES = 3


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    description: str
    published_at: datetime | None


def normalize_url(url: str) -> str:
    """Stable dedupe key: lowercase host, no query/fragment."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def _parse_published(raw: dict) -> datetime | None:
    val = raw.get("age") or raw.get("page_age")
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def search(query: str, *, api_key: str, count: int = 10, freshness: str = "pd") -> list[SearchResult]:
    """Run a single Brave web search.

    freshness: 'pd' = past day, 'pw' = past week, 'pm' = past month.
    """
    headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
    params = {"q": query, "count": count, "freshness": freshness, "result_filter": "web"}

    for attempt in range(_MAX_RETRIES):
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.get(_ENDPOINT, headers=headers, params=params)
            if resp.status_code == 429:
                wait = 2 ** attempt
                log.warning("Brave 429, backing off %ss (attempt %s)", wait, attempt + 1)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return _parse_results(resp.json())
        except httpx.HTTPError as e:
            if attempt == _MAX_RETRIES - 1:
                log.error("Brave search failed for %r after %s attempts: %s", query, _MAX_RETRIES, e)
                return []
            time.sleep(1 + attempt)

    return []


def _parse_results(payload: dict) -> list[SearchResult]:
    web = (payload.get("web") or {}).get("results") or []
    out: list[SearchResult] = []
    for r in web:
        url = r.get("url")
        if not url:
            continue
        out.append(
            SearchResult(
                title=r.get("title", "").strip(),
                url=url,
                description=r.get("description", "").strip(),
                published_at=_parse_published(r),
            )
        )
    return out


def search_many(queries: Iterable[str], *, api_key: str, per_query: int = 5) -> list[SearchResult]:
    """Run multiple queries, dedupe by normalized URL, return flat list."""
    seen: set[str] = set()
    out: list[SearchResult] = []
    for q in queries:
        for result in search(q, api_key=api_key, count=per_query):
            key = normalize_url(result.url)
            if key in seen:
                continue
            seen.add(key)
            out.append(result)
        time.sleep(1.1)  # Brave free tier: 1 req/sec
    return out
