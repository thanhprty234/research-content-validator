"""Disk-based cache for research plans, keyed by topic.

Lets the planner skip an LLM call when the same topic was researched before,
which also stabilizes the research questions and improves search-cache hits.

Cache is disabled by setting ``PLAN_CACHE=0`` in the environment.
"""

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

_CACHE_NAME = "plan_cache.sqlite"
_cache_dir = Path(__file__).resolve().parent.parent / "output"


def _conn():
    _cache_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_cache_dir / _CACHE_NAME))
    con.execute(
        "CREATE TABLE IF NOT EXISTS plans "
        "(topic_hash TEXT PRIMARY KEY, topic TEXT, questions TEXT, outline TEXT, created_at TEXT)"
    )
    return con


def _key(topic: str) -> str:
    return hashlib.sha256((topic or "").strip().lower().encode("utf-8")).hexdigest()


def enabled() -> bool:
    return os.getenv("PLAN_CACHE", "1").strip().lower() not in ("0", "false", "no")


def get_plan(topic: str) -> Optional[dict]:
    """Return a cached plan dict or None (respects PLAN_CACHE env)."""
    if not enabled():
        return None
    con = _conn()
    row = con.execute(
        "SELECT questions, outline FROM plans WHERE topic_hash=?", (_key(topic),)
    ).fetchone()
    con.close()
    if row:
        return {
            "research_questions": json.loads(row[0]),
            "outline": json.loads(row[1]),
        }
    return None


def set_plan(topic: str, questions: list, outline: list) -> None:
    from datetime import datetime, timezone

    con = _conn()
    con.execute(
        "INSERT OR REPLACE INTO plans (topic_hash, topic, questions, outline, created_at) VALUES (?,?,?,?,?)",
        (
            _key(topic),
            topic,
            json.dumps(questions, ensure_ascii=False),
            json.dumps(outline, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    con.commit()
    con.close()
