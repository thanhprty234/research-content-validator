"""Helpers for consuming the workflow stream and turning updates into events.

The graph streams with `stream_mode="updates"`, so every chunk looks like
`{"planner": {"research_questions": [...], ...}}` — the key is the node that
just finished. This module exposes helpers to label the step and accumulate a
full state for final rendering.
"""


def node_from_chunk(chunk: dict) -> str:
    """Return the name of the node that produced this chunk."""
    return next(iter(chunk)) if chunk else "start"


def accumulate(state: dict, chunk: dict) -> dict:
    """Merge a node's updates into the running accumulated state."""
    for updates in chunk.values():
        if isinstance(updates, dict):
            state.update(updates)
    return state


def step_message(step: str, state: dict) -> str:
    """A short human-readable message describing the completed step."""
    if step == "planner":
        qs = state.get("research_questions", [])
        return f"{len(qs)} research questions"
    if step == "researcher":
        n = len(state.get("raw_findings", []))
        return f"{n} findings gathered"
    if step == "writer":
        return f"draft ready ({len(state.get('body', ''))} chars)"
    if step == "critic":
        critique = state.get("critique") or {}
        verdict = critique.get("verdict", "?")
        score = critique.get("overall_score", "?")
        return f"{verdict} ({score}/100)"
    return "workflow started"


def consume_stream(stream_iter, state: dict = None, on_step=None, on_error=None):
    """Consume a workflow stream, accumulating the full state.

    Calls ``on_step(step, state)`` after each completed node and returns the
    accumulated state. Exceptions raised inside the stream are passed to
    ``on_error`` (if given) or re-raised.

    Args:
        stream_iter: iterable of ``{node: updates}`` chunks (stream_mode="updates").
        state: optional dict to accumulate into (created if None).
        on_step: optional ``callable(step, state)``.
        on_error: optional ``callable(exc)``; when set, exceptions stop the loop
            and are NOT re-raised.
    Returns:
        dict: accumulated workflow state.
    """
    state = {} if state is None else state
    try:
        for chunk in stream_iter:
            step = node_from_chunk(chunk)
            accumulate(state, chunk)
            if on_step:
                on_step(step, state)
    except Exception as exc:
        if on_error:
            on_error(exc)
        else:
            raise
    return state


STEP_ORDER = ["planner", "researcher", "writer", "critic"]