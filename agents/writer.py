"""Writer agent: drafts a complete report from plan + notes (structured output)."""

import json

from .common import load_prompt, structured_call
from .schemas import Report
from .state import WorkflowState


def writer_node(state: WorkflowState, llm=None) -> dict:
    """Graph node: write the report from outline and research notes."""
    prior_feedback = state.get("critic_feedback", [])
    context = {
        "outline": state.get("outline", []),
        "notes": state.get("notes", []),
        "prior_feedback": prior_feedback[-1] if prior_feedback else None,
    }

    report: Report = structured_call(
        llm,
        Report,
        load_prompt("writer.txt"),
        "Outline and research notes (JSON):\n"
        + json.dumps(context, ensure_ascii=False, indent=2),
        max_tokens=6000,
    )
    return {
        "title": report.title,
        "summary": report.summary,
        "body": report.body,
        "key_claims": report.key_claims,
        "citations": [c.model_dump() for c in report.citations],
        "revision_count": state.get("revision_count", 0) + 1,
    }