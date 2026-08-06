"""Offline integration test calling graph nodes directly with a fake LLM.

Run: python -m tests.test_smoke   (or: python tests/test_smoke.py)
Verifies: plan/research/writer/critic nodes work and revision routing terminates.
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
import graph as G


def main():
    os.environ["MAX_REVISIONS"] = "4"
    os.environ["PLAN_CACHE"] = "0"
    fake = FakeLLM(approve_after=2)

    state = {"topic": "Water cycle"}
    state.update(plan_node(state, fake))
    state.update(research_node(state, fake))
    state.update(writer_node(state, fake))
    state.update(critic_node(state, fake))

    # simulate one revise loop (writer already bumped revision_count)
    state.update(writer_node(state, fake))
    state.update(critic_node(state, fake))

    print("Verdict:", (state.get("critique") or {}).get("verdict"))
    print("Revision count:", state.get("revision_count"))
    print("Body present:", bool(state.get("body")))
    print("Routing (REVISE after first):", G._should_revise(state))

    assert (state.get("critique") or {}).get("verdict") == "APPROVED"
    assert state.get("revision_count", 0) >= 1
    print("SMOKE TEST OK")


if __name__ == "__main__":
    main()