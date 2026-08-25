"""Typed workflow state shared between the graph and the agent nodes."""

from typing import Optional, TypedDict


class WorkflowState(TypedDict, total=False):
    # plan / research
    topic: str
    plan: Optional[dict]
    research_questions: list
    outline: list
    notes: list
    raw_findings: list

    # report
    title: str
    summary: str
    body: str
    key_claims: list
    citations: list

    # review loop
    critique: Optional[dict]
    critic_feedback: list
    revision_count: int
    final_report: Optional[dict]

    # best report seen so far (kept when revisions run out before approval)
    best_report: Optional[dict]
    best_critique: Optional[dict]

    # cost tracking
    token_log: list  # ponytail: append-only, no lock — single-threaded workflow; swap to per-step dict if parallel LLM calls matter
    total_cost_usd: float

    # citation quality audit (deterministic, optional)
    citation_audit: Optional[dict]

    # human review (Phase 3.1 — gated by HUMAN_REVIEW env)
    manual_feedback: Optional[str]
    draft_rejected: bool
