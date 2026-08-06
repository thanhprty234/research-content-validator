"""Offline tests for graph routing logic (_should_revise).

Run: python -m tests.test_graph   (or: python tests/test_graph.py)
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import graph as G


def test_revise_below_max():
    os.environ["MAX_REVISIONS"] = "3"
    state = {"critique": {"verdict": "REVISE"}, "revision_count": 1}
    assert G._should_revise(state) == "rewrite"
    print("revise below max OK")


def test_revise_at_max():
    os.environ["MAX_REVISIONS"] = "3"
    state = {"critique": {"verdict": "REVISE"}, "revision_count": 3}
    assert G._should_revise(state) == "finish"
    print("revise at max OK")


def test_approve_finishes():
    os.environ["MAX_REVISIONS"] = "3"
    state = {"critique": {"verdict": "APPROVED"}, "revision_count": 0}
    assert G._should_revise(state) == "finish"
    print("approve finishes OK")


def test_missing_verdict_treated_as_revise():
    os.environ["MAX_REVISIONS"] = "3"
    state = {"revision_count": 0}
    assert G._should_revise(state) == "rewrite"
    print("missing verdict OK")


def main():
    test_revise_below_max()
    test_revise_at_max()
    test_approve_finishes()
    test_missing_verdict_treated_as_revise()
    print("GRAPH TEST OK")


if __name__ == "__main__":
    main()
