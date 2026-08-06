"""Critic agent: validates the writer's report (structured verdict)."""

import json
import os

from .common import load_prompt, structured_call
from .schemas import Critique
from .state import WorkflowState

DEFAULT_APPROVE_THRESHOLD = 85


def approve_threshold() -> int:
    """Approval score threshold; overridable via APPROVE_THRESHOLD in .env."""
    return int(os.getenv("APPROVE_THRESHOLD", str(DEFAULT_APPROVE_THRESHOLD)))


def critic_node(state: WorkflowState, llm=None) -> dict:
    """Graph node: validate the report and produce an APPROVED/REVISE verdict."""
    report = {
        "title": state.get("title", ""),
        "summary": state.get("summary", ""),
        "body": state.get("body", ""),
        "key_claims": state.get("key_claims", []),
        "citations": state.get("citations", []),
    }

    critique: Critique = structured_call(
        llm,
        Critique,
        load_prompt("critic.txt"),
        "Report (JSON):\n" + json.dumps(report, ensure_ascii=False, indent=2),
        max_tokens=2000,
    )

    threshold = approve_threshold()
    if critique.overall_score >= threshold:
        critique.verdict = "APPROVED"

    # Keep the best report/verdict seen so far so a later, worse revision
    # cannot overwrite the best result when revisions run out before approval.
    best_report = state.get("best_report") or {}
    best_score = best_report.get("score", -1.0)
    if critique.overall_score > best_score:
        best_report = {
            "score": critique.overall_score,
            "revision": state.get("revision_count", 0),
            **report,
        }
        best_critique = critique.model_dump()
    else:
        best_critique = state.get("best_critique") or critique.model_dump()

    return {
        "critique": critique.model_dump(),
        "critic_feedback": [
            *state.get("critic_feedback", []),
            _feedback_text(critique),
        ],
        "revision_count": state.get("revision_count", 0),
        "final_report": report if critique.verdict == "APPROVED" else None,
        "best_report": best_report,
        "best_critique": best_critique,
    }


def _feedback_text(critique: Critique) -> str:
    lines = [f"Overall: {critique.overall_notes}"]
    lines += [f"- {i}" for i in critique.issues]
    lines += [f"Suggestion: {r}" for r in critique.suggested_revisions]
    return "\n".join(lines)