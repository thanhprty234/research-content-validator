"""Planner agent: turns a topic into a research plan (structured output)."""

from .common import load_prompt, structured_call
from .schemas import ResearchPlan
from .state import WorkflowState
from tools import plan_cache


def plan_node(state: WorkflowState, llm=None) -> dict:
    """Graph node: produce a research plan for the topic in state.

    Uses the disk cache for previously-researched topics (same questions and
    outline) so the LLM is only called when there is no cached plan.
    """
    topic = state.get("topic", "")

    cached = plan_cache.get_plan(topic)
    if cached is not None:
        return {
            "plan": cached,
            "research_questions": cached["research_questions"],
            "outline": cached["outline"],
        }

    plan: ResearchPlan = structured_call(
        llm,
        ResearchPlan,
        load_prompt("planner.txt"),
        f"Research topic:\n{topic}",
        max_tokens=2000,
    )
    plan_cache.set_plan(topic, plan.research_questions, plan.outline)
    return {
        "plan": plan.model_dump(),
        "research_questions": plan.research_questions,
        "outline": plan.outline,
    }