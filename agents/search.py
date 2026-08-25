"""Search orchestration with graceful fallback to DuckDuckGo."""

import asyncio
from typing import List, Dict, Optional

from .searxng import SearXNG


def search_queries_sync(query: str, max_results: int = 5) -> list:
    """Synchronous wrapper for async search_queries."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(search_queries(query, max_results=max_results))
    else:
        return asyncio.run_coroutine_threadsafe(
            search_queries(query, max_results=max_results), loop
        ).result()


async def search_queries(query: str, max_results: int = 5) -> list:
    """Search for query with graceful fallback.

    Strategy:
    1. Try SearXNG first (if configured)
    2. Fallback to DuckDuckGo (free, no key needed)
    3. Return empty list if both fail
    """
    # Try SearXNG first
    try:
        results = await SearXNG.search(query, max_results=max_results)
        if results:
            return results
    except Exception:
        pass

    # Fallback to DuckDuckGo — use .results() to get real URLs
    try:
        from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
        ddg = DuckDuckGoSearchAPIWrapper(max_results=max_results)
        raw = await asyncio.to_thread(ddg.results, query, max_results=max_results)
        if raw:
            out = []
            for r in raw:
                url = r.get("link") or r.get("href") or r.get("url", "")
                if url:
                    out.append({
                        "title": r.get("title", ""),
                        "url": url,
                        "content": r.get("snippet") or r.get("body") or "",
                    })
            if out:
                return out
    except Exception as e:
        print(f"⚠️  DuckDuckGo search failed: {e}")

    return []


async def search_with_fallback(query: str, max_results: int = 5) -> list:
    """Search with explicit fallback chain and logging."""
    results = await search_queries(query, max_results=max_results)
    if not results:
        print(f"⚠️  No search results for: {query}")
        return [{
            "title": f"[Fallback] Context on: {query}",
            "url": "",
            "content": f"No external search results for '{query}'. Proceeding with internal knowledge.",
        }]
    return results
