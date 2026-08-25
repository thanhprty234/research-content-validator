"""SearXNG search wrapper."""

import os
from typing import List, Dict, Optional


class SearXNG:
    """Wrapper around SearXNG search (requires SEARXNG_URL env var)."""

    BASE_URL = os.getenv("SEARXNG_URL", "http://localhost:8080")

    @classmethod
    async def search(cls, query: str, max_results: int = 5) -> list:
        """Search via SearXNG API."""
        try:
            import aiohttp
            url = f"{cls.BASE_URL}/search"
            params = {
                "q": query,
                "format": "json",
                "categories": "general",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get("results", [])
                        return [
                            {
                                "title": r.get("title", ""),
                                "url": r.get("url", ""),
                                "content": r.get("content", ""),
                            }
                            for r in results[:max_results]
                        ]
        except Exception as e:
            print(f"⚠️  SearXNG search failed: {e}")
        return []
