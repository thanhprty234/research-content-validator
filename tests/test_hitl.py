"""Phase 3.1 — Human-in-the-Loop checkpoint tests (env-gated).

Run: python tests/test_hitl.py
"""
import builtins
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph import build_graph, _human_review, _after_review


def _make_fake():
    f = MagicMock()
    f.model_name = "fake"
    return f


def test_graph_without_hitl():
    os.environ.pop("HUMAN_REVIEW", None)
    app = build_graph(llm=_make_fake())
    nodes = {n for n in app.get_graph().nodes.keys() if n not in ("__start__", "__end__")}
    assert "human_review" not in nodes, "human_review should NOT be in default graph"
    assert "critic" in nodes
    print("default graph OK")


def test_graph_with_hitl():
    os.environ["HUMAN_REVIEW"] = "1"
    try:
        app = build_graph(llm=_make_fake())
        nodes = {n for n in app.get_graph().nodes.keys() if n not in ("__start__", "__end__")}
        assert "human_review" in nodes, "human_review should be in HITL graph"
    finally:
        os.environ.pop("HUMAN_REVIEW", None)
    print("hitl graph OK")


def test_review_approve():
    orig = builtins.input
    try:
        builtins.input = lambda *a, **kw: "y"
        result = _human_review({"body": "test draft"})
        assert result == {"draft_rejected": False}, f"approve failed: {result}"
    finally:
        builtins.input = orig
    print("approve OK")


def test_review_reject():
    call_count = [0]
    responses = ["n", "fix the intro"]

    def mock_input(*a, **kw):
        v = responses[call_count[0]]
        call_count[0] += 1
        return v

    orig = builtins.input
    try:
        builtins.input = mock_input
        result = _human_review({"body": "test"})
        assert result == {"draft_rejected": True, "manual_feedback": "fix the intro", "critic_feedback": ["fix the intro"]}, f"reject failed: {result}"
    finally:
        builtins.input = orig
    print("reject OK")


def test_review_eof_auto_approve():
    def boom(*a, **kw):
        raise EOFError("no stdin")

    orig = builtins.input
    try:
        builtins.input = boom
        result = _human_review({"body": "test"})
        assert result == {"draft_rejected": False}, f"EOF auto-approve failed: {result}"
    finally:
        builtins.input = orig
    print("eof auto-approve OK")


def test_after_review_route():
    assert _after_review({"draft_rejected": True}) == "writer"
    assert _after_review({"draft_rejected": False}) == "critic"
    print("after_review routing OK")


def main():
    test_graph_without_hitl()
    test_graph_with_hitl()
    test_review_approve()
    test_review_reject()
    test_review_eof_auto_approve()
    test_after_review_route()
    print("HITL TEST OK")


if __name__ == "__main__":
    main()
