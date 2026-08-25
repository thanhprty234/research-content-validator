"""Graceful search fallback — DuckDuckGo → offline when primary search returns nothing."""

import os
from typing import List, Optional

from langchain_community.utilities import DuckDuckGoSearchAPIWrapper


def _ddg_search(query: str, max_results: int = 5) -> list:
    """Search using DuckDuckGo (no API key required)."""
    try:
        ddg = DuckDuckGoSearchAPIWrapper(max_results=max_results)
        results = ddg.run(query)
        if results:
            return [{"title": "DuckDuckGo", "url": "", "content": results}]
    except Exception:
        pass
    return []


def _fallback_search(query: str, max_results: int = 5) -> list:
    """Generate a fallback result so the pipeline continues without crashing."""
    return [
        {
            "title": f"[Fallback] Context on: {query}",
            "url": "",
            "content": (
                f"No external search results for '{query}'. "
                "Proceeding with internal knowledge."
            ),
        }
    ]


def search_with_fallback(
    query: str,
    max_results: int = 5,
    use_primary: bool = True,
    primary_fn=None,
) -> list:
    """Search with graceful fallback chain.

    Strategy:
    1. Try primary search (Tavily, SearXNG, etc.) if configured
    2. If primary returns empty or fails, try DuckDuckGo
    3. If DuckDuckGo also fails, return a friendly fallback note

    This prevents the Researcher from crashing on niche topics.
    """
    # Try primary provider first
    if use_primary and primary_fn is not None:
        try:
            results = primary_fn(query, max_results=max_results)
            if results:
                return results
        except Exception:
            pass

    # Fallback to DuckDuckGo (free, no key needed)
    ddg_results = _ddg_search(query, max_results=max_results)
    if ddg_results:
        return ddg_results

    # Final fallback — keep the pipeline running
    return _fallback_search(query, max_results=max_results)
