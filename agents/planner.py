"""Planner agent: turns a topic into a research plan (structured output)."""

from .common import load_prompt, structured_call
from .schemas import ResearchPlan
from .state import WorkflowState


def plan_node(state: WorkflowState, llm=None) -> dict:
    """Graph node: produce a research plan for the topic in state."""
    plan: ResearchPlan = structured_call(
        llm,
        ResearchPlan,
        load_prompt("planner.txt"),
        f"Research topic:\n{state.get('topic', '')}",
        max_tokens=2000,
    )
    return {
        "plan": plan.model_dump(),
        "research_questions": plan.research_questions,
        "outline": plan.outline,
    }