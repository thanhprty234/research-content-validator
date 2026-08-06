"""Offline tests for each agent node with a fake LLM.

Run: python -m tests.test_agents   (or: python tests/test_agents.py)
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.fakes import FakeLLM
from agents.planner import plan_node
from agents.researcher import research_node
from agents.writer import writer_node
from agents.critic import critic_node


def test_planner():
    fake = FakeLLM()
    out = plan_node({"topic": "Water cycle"}, fake)
    assert out["research_questions"], "planner returned no questions"
    assert out["outline"], "planner returned no outline"
    print("planner OK:", out["research_questions"])


def test_researcher():
    fake = FakeLLM()
    state = {"research_questions": ["q1: water", "q2: sun"]}
    out = research_node(state, fake)
    assert len(out["notes"]) == 2, "expected one note per question"
    assert out["notes"][0]["sources"], "note has no sources"
    print("researcher OK:", len(out["notes"]), "notes")


def test_writer():
    fake = FakeLLM()
    state = {
        "outline": ["Introduction", "Body"],
        "notes": [{"question": "q", "findings": "findings", "sources": ["u"]}],
    }
    out = writer_node(state, fake)
    assert out["body"], "writer produced empty body"
    assert out["citations"], "writer produced no citations"
    assert out["revision_count"] == 1, "revision_count not bumped"
    print("writer OK: body len", len(out["body"]))


def test_critic_approve():
    fake = FakeLLM(approve_after=1)
    state = {
        "title": "t", "summary": "s", "body": "b",
        "key_claims": ["c"], "citations": [{"source": "u", "claim_supported": "c"}],
    }
    out = critic_node(state, fake)
    assert out["critique"]["verdict"] == "APPROVED", "critic should approve after 1"
    assert out["final_report"], "final_report should be set on APPROVED"
    print("critic(approve) OK:", out["critique"]["verdict"])


def test_critic_revise():
    fake = FakeLLM(approve_after=2)
    state = {"body": "b"}
    out = critic_node(state, fake)
    assert out["critique"]["verdict"] == "REVISE", "critic should revise before approving"
    assert out["final_report"] is None, "final_report should be None on REVISE"
    print("critic(revise) OK:", out["critique"]["verdict"])


def main():
    os.environ["MAX_REVISIONS"] = "4"
    test_planner()
    test_researcher()
    test_writer()
    test_critic_approve()
    test_critic_revise()
    print("AGENTS TEST OK")


if __name__ == "__main__":
    main()
