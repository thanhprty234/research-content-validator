"""LangGraph workflow: planner -> researcher -> writer -> critic (revision loop)."""

import os
from contextlib import ExitStack
from typing import Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END

from models.llm import get_model, resolve_alias
from agents.state import WorkflowState
from agents.planner import plan_node
from agents.researcher import research_node
from agents.writer import writer_node
from agents.critic import critic_node
from agents.common import last_usage
from agents.registry import load_registry

# Persistent sqlite saver (kept open across calls via ExitStack).
_sqlite_saver = None
_sqlite_stack = None


def _should_revise(state: WorkflowState) -> str:
    max_revisions = int(os.getenv("MAX_REVISIONS", "3"))
    verdict = (state.get("critique") or {}).get("verdict", "REVISE")
    if verdict == "REVISE" and state.get("revision_count", 0) < max_revisions:
        return "rewrite"
    return "finish"


# ponytail: Phase 3.1 — HITL node and routing function are module-level for testability
def _human_review(state: WorkflowState) -> dict:
    """Pause for operator approval before the critic burns tokens.
    Auto-approves on EOFError (web UI / non-TTY path)."""
    draft = state.get("body") or ""
    print("\n--- DRAFT FOR REVIEW ---\n" + draft[:2000] + "\n------------------------")
    try:
        ans = input("Approve draft? [y/N] (reject = type feedback): ").strip().lower()
    except (EOFError, OSError):
        # ponytail: silent auto-approve under servers; add explicit API gate if HITL matters there
        return {"draft_rejected": False}
    if ans in ("y", "yes"):
        return {"draft_rejected": False}
    fb = input("Feedback for writer: ").strip()
    return {"draft_rejected": True, "manual_feedback": fb, "critic_feedback": [fb]}


def _after_review(state: WorkflowState) -> str:
    return "writer" if state.get("draft_rejected") else "critic"


def build_checkpointer():
    """Return a BaseCheckpointSaver based on the CHECKPOINTER env var."""
    global _sqlite_saver, _sqlite_stack

    kind = os.getenv("CHECKPOINTER", "memory").lower()
    if kind != "sqlite":
        return MemorySaver()

    from langgraph.checkpoint.sqlite import SqliteSaver

    path = os.getenv("SQLITE_PATH", "output/checkpoints.sqlite")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    if _sqlite_saver is None:
        # from_conn_string is a context manager; keep the connection open.
        _sqlite_stack = ExitStack()
        _sqlite_saver = _sqlite_stack.enter_context(SqliteSaver.from_conn_string(path))
    return _sqlite_saver


def _track_cost(state: WorkflowState, node_name: str, llm) -> dict:
    """After a node runs, capture usage metadata and append to token_log."""
    usage = last_usage()
    if not usage:
        return {}
    provider = getattr(llm, "model_name", "") or getattr(llm, "model", "") or ""
    from models.llm import estimate_cost
    cost = estimate_cost(resolve_alias(os.getenv("MODEL_PROVIDER", "openai")),
                         usage.get("input_tokens", 0),
                         usage.get("output_tokens", 0),
                         provider)
    token_log = list(state.get("token_log", []))
    token_log.append({
        "step": node_name,
        "model": provider,
        "tokens": {"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)},
        "cost_usd": cost,
    })
    total_cost = round(sum(e["cost_usd"] for e in token_log), 6)

    # ponytail: truncate detection on body — lightweight, no extra LLM call
    body = state.get("body") or ""
    if _is_truncated(body):
        from cli_ui import _safe_write
        _safe_write("[warn] body appears truncated (ends with ...)")
        state["body"] = body.rstrip() + "\n\n*(report may be truncated)*"

    return {"token_log": token_log, "total_cost_usd": total_cost}


def build_graph(llm=None):
    """Compile the workflow graph with the configured checkpointer."""
    llm = llm or get_model()

    def _planner(s):
        out = plan_node(s, llm)
        out.update(_track_cost(s, "planner", llm))
        return out

    def _researcher(s, config=None):
        out = research_node(s, llm, progress=config.get("configurable", {}).get("on_progress") if config else None)
        out.update(_track_cost(s, "researcher", llm))
        return out

    def _writer(s):
        out = writer_node(s, llm)
        out.update(_track_cost(s, "writer", llm))
        return out

    def _critic(s):
        out = critic_node(s, llm)
        out.update(_track_cost(s, "critic", llm))
        return out

    # ponytail: Phase 3.1 — env-gated HITL checkpoint; read env at call-time so tests can toggle
    _hitl_enabled = os.environ.get("HUMAN_REVIEW", "").lower() in ("1", "true", "yes")

    g = StateGraph(WorkflowState)
    # ponytail: Phase 4.1 — registry loaded for future extensibility; current graph
    # uses direct node bindings (closure-safe). Registry lives in config/agents.yaml.
    load_registry()  # side-effect: validates config at startup
    g.add_node("planner", _planner)
    g.add_node("researcher", _researcher)
    g.add_node("writer", _writer)
    g.add_node("critic", _critic)
    g.add_edge(START, "planner")
    g.add_edge("planner", "researcher")
    g.add_edge("researcher", "writer")
    if _hitl_enabled:
        g.add_node("human_review", _human_review)
        g.add_edge("writer", "human_review")
        g.add_conditional_edges("human_review", _after_review, {"writer": "writer", "critic": "critic"})
    else:
        g.add_edge("writer", "critic")
    g.add_conditional_edges("critic", _should_revise, {"rewrite": "writer", "finish": END})
    return g.compile(checkpointer=build_checkpointer())


def _run_config(thread_id: Optional[str]) -> dict:
    return {"configurable": {"thread_id": thread_id or os.getenv("THREAD_ID", "default")}}


def run(topic: str, thread_id: Optional[str] = None, llm=None):
    """Run the full workflow for a topic. Returns (final_state, compiled_graph)."""
    graph = build_graph(llm=llm)
    final_state = graph.invoke({"topic": topic}, config=_run_config(thread_id))
    return final_state, graph


def stream(topic: str, thread_id: Optional[str] = None, llm=None, on_progress=None):
    """Stream the workflow, yielding `{node: updates}` dicts after each node."""
    graph = build_graph(llm=llm)
    config = _run_config(thread_id)
    if on_progress:
        config["configurable"]["on_progress"] = on_progress
    return graph.stream(
        {"topic": topic},
        config=config,
        stream_mode="updates",
    )
