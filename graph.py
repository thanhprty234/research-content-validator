"""LangGraph workflow: planner -> researcher -> writer -> critic (revision loop)."""

import os
from contextlib import ExitStack
from typing import Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END

from models.llm import get_model
from agents.state import WorkflowState
from agents.planner import plan_node
from agents.researcher import research_node
from agents.writer import writer_node
from agents.critic import critic_node

# Persistent sqlite saver (kept open across calls via ExitStack).
_sqlite_saver = None
_sqlite_stack = None


def _should_revise(state: WorkflowState) -> str:
    max_revisions = int(os.getenv("MAX_REVISIONS", "3"))
    verdict = (state.get("critique") or {}).get("verdict", "REVISE")
    if verdict == "REVISE" and state.get("revision_count", 0) < max_revisions:
        return "rewrite"
    return "finish"


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


def build_graph(llm=None):
    """Compile the workflow graph with the configured checkpointer."""
    llm = llm or get_model()

    g = StateGraph(WorkflowState)
    g.add_node("planner", lambda s: plan_node(s, llm))
    g.add_node(
        "researcher",
        lambda s, config: research_node(
            s, llm, progress=config.get("configurable", {}).get("on_progress")
        ),
    )
    g.add_node("writer", lambda s: writer_node(s, llm))
    g.add_node("critic", lambda s: critic_node(s, llm))

    g.add_edge(START, "planner")
    g.add_edge("planner", "researcher")
    g.add_edge("researcher", "writer")
    g.add_edge("writer", "critic")
    g.add_conditional_edges(
        "critic",
        _should_revise,
        {"rewrite": "writer", "finish": END},
    )
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