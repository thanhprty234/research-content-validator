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
