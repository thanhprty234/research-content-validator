"""Critic agent: validates the writer's report (structured verdict)."""

import json
import os

from .common import load_prompt, structured_call
from .schemas import Critique
from .state import WorkflowState
from tools import citation_check

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

    # Run deterministic citation quality checks (gated by CITATION_CHECK env)
    audit = {}
    try:
        audit = citation_check.audit_citations(
            state.get("citations", []) or [],
            state.get("key_claims", []) or [],
            raw_findings=state.get("raw_findings"),
        )
    except Exception:
        pass  # fail-open: never crash pipeline

    # Inject audit summary into prompt context
    audit_json = json.dumps(audit, ensure_ascii=False) if audit else "{}"

    prompt = load_prompt("critic.txt").replace("{citation_audit_json}", audit_json)

    critique: Critique = structured_call(
        llm,
        Critique,
        prompt,
        "Report (JSON):\n" + json.dumps(report, ensure_ascii=False, indent=2),
        max_tokens=2000,
    )

    threshold = approve_threshold()
    if critique.overall_score >= threshold:
        critique.verdict = "APPROVED"

    # Append any dead-link / low-authority flags as issues (deterministic, no LLM)
    if audit and audit.get("enabled"):
        for url, status in (audit.get("url_status") or {}).items():
            if not status.get("reachable"):
                issue = f"Dead/unreachable link: {url}"
                if issue not in critique.issues:
                    critique.issues.append(issue)
        low = audit.get("low_authority_count", 0)
        if low:
            note = f"{low} low-authority source(s) detected"
            if note not in critique.issues:
                critique.issues.append(note)

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
        "citation_audit": audit if audit.get("enabled") else {},
    }


def _feedback_text(critique: Critique) -> str:
    lines = [f"Overall: {critique.overall_notes}"]
    lines += [f"- {i}" for i in critique.issues]
    lines += [f"Suggestion: {r}" for r in critique.suggested_revisions]
    return "\n".join(lines)
