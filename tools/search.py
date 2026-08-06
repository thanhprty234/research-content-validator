"""Search tool with disk-based caching to avoid repeated API calls.

Supports optional live web search via Tavily (or a generic HTTP search) when a
provider key is configured. Falls back to a knowledge-mock / URL fetch otherwise.
"""

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

_CACHE_NAME = "search_cache.sqlite"
_cache_dir = Path(__file__).resolve().parent.parent / "output"


def _conn():
    _cache_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_cache_dir / _CACHE_NAME))
    con.execute(
        "CREATE TABLE IF NOT EXISTS results (query_hash TEXT PRIMARY KEY, query TEXT, data TEXT, created_at TEXT)"
    )
    return con


def _key(query: str, extra: Optional[str] = None) -> str:
    raw = query + "|" + (extra or "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_cache(query: str) -> Optional[list]:
    con = _conn()
    row = con.execute(
        "SELECT data FROM results WHERE query_hash=?", (_key(query),)
    ).fetchone()
    con.close()
    if row:
        return json.loads(row[0])
    return None


def _write_cache(query: str, results: list) -> None:
    from datetime import datetime, timezone

    con = _conn()
    con.execute(
        "INSERT OR REPLACE INTO results (query_hash, query, data, created_at) VALUES (?,?,?,?)",
        (
            _key(query),
            query,
            json.dumps(results, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    con.commit()
    con.close()


def _tavily_search(query: str, tavily_key: str, max_results: int = 5) -> list:
    try:
        from tavily import TavilyClient
    except ImportError:
        return _offline_search(query, max_results)

    client = TavilyClient(api_key=tavily_key)
    resp = client.search(query=query, max_results=max_results)
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
        for r in resp.get("results", [])
    ]


def _offline_search(query: str, max_results: int = 5) -> list:
    """Mock search used when no live provider is configured.

    Returns a deterministic snippet so the pipeline still works locally.
    """
    return [
        {
            "title": f"[offline] Background on: {query}",
            "url": f"https://example.com/search?q={query.replace(' ', '+')}",
            "content": (
                f"Offline search placeholder for query '{query}'. "
                "No live search provider configured. Review results manually."
            ),
        }
    ]


def search(query: str, max_results: int = 5, use_cache: bool = True) -> list:
    """Search for `query`, using disk cache when available."""
    if use_cache:
        cached = _read_cache(query)
        if cached is not None:
            return cached

    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        results = _tavily_search(query, tavily_key, max_results)
    else:
        results = _offline_search(query, max_results)

    if use_cache:
        _write_cache(query, results)
    return results
