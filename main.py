"""CLI entrypoint: run the Research & Content Validator workflow.

Features:
- LangGraph workflow (planner -> researcher -> writer -> critic).
- Streaming per-step progress (with color/spinner if rich is available).
- Checkpointing (--resume continues a thread).
- LangSmith observability when LANGCHAIN_API_KEY is set.
- Structured output to output/.
"""

import argparse
import json
import os

from dotenv import load_dotenv

load_dotenv()

from models.llm import get_model, model_config_from_env
from graph import run, stream, build_graph
from stream_events import consume_stream
from cli_ui import _Spinner, print_verdict, _log_step
from output import write_outputs


# --------------------------------------------------------------------------- #
# Observability
# --------------------------------------------------------------------------- #
def setup_observability() -> bool:
    """Enable LangSmith tracing only if a key is configured; otherwise disable it."""
    key = (os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY") or "").strip()
    if key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ.setdefault(
            "LANGCHAIN_PROJECT", os.getenv("LANGSMITH_PROJECT", "research-validator")
        )
        from langsmith import Client  # noqa: F401  ensures tracing is initialized
        print("[observability] LangSmith tracing enabled.")
        return True

    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ.pop("LANGCHAIN_TRACING", None)
    os.environ.pop("LANGCHAIN_ENDPOINT", None)
    print("[observability] LangSmith not configured (set LANGCHAIN_API_KEY).")
    return False


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_args():
    parser = argparse.ArgumentParser(description="Research & Content Validator (Supervisor + Critic)")
    parser.add_argument("--topic", help="Research topic")
    parser.add_argument("--provider", help="Model provider (openai, anthropic, gemini, ollama, ...)")
    parser.add_argument("--model", help="Model name")
    parser.add_argument("--stream", action="store_true", help="Stream per-step progress")
    parser.add_argument("--max-revisions", type=int, help="Max writer/critic loops")
    parser.add_argument("--no-plan-cache", action="store_true", help="Ignore cached research plans (refresh data)")
    parser.add_argument("--thread-id", help="Checkpoint thread id (for --resume)")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint for thread")
    parser.add_argument("--list-providers", action="store_true", help="List supported providers")
    parser.add_argument("--print-config", action="store_true", help="Print model config and exit")
    return parser.parse_args()


def main():
    args = parse_args()
    cfg = model_config_from_env()

    if args.list_providers:
        from models.llm import PROVIDER_ALIASES
        print("Supported providers:", ", ".join(sorted(PROVIDER_ALIASES)))
        return

    if args.provider:
        cfg.provider = args.provider
    if args.model:
        cfg.model = args.model

    if args.print_config:
        print(json.dumps(cfg.__dict__, indent=2, default=str))
        return

    if not args.topic:
        raise SystemExit("--topic is required")

    if args.max_revisions:
        os.environ["MAX_REVISIONS"] = str(args.max_revisions)
    if args.no_plan_cache:
        os.environ["PLAN_CACHE"] = "0"

    setup_observability()
    llm = get_model(cfg)

    if args.resume:
        graph = build_graph(llm=llm)
        config = {"configurable": {"thread_id": args.thread_id or "default"}}
        final = graph.invoke(None, config=config)
        print_verdict(final)
        write_outputs(final)
        return

    final_state = _run_with_prompt(args.topic, args.thread_id, llm, stream=args.stream)

    print_verdict(final_state)
    write_outputs(final_state)


def _run_with_prompt(topic: str, thread_id=None, llm=None, stream: bool = False) -> dict:
    """Run the workflow, letting the user add more revision rounds when the
    revisions run out before the critic approves.

    Each loop re-runs the graph; the planner uses its disk cache so re-runs are
    cheap. The critic keeps the best report seen so far.
    """
    while True:
        if stream:
            final_state = _stream_with_spinner(topic, thread_id=thread_id, llm=llm)
        else:
            final_state, _ = run(topic, thread_id=thread_id, llm=llm)

        critique = final_state.get("critique") or {}
        verdict = critique.get("verdict", "UNKNOWN")
        if verdict != "REVISE":
            return final_state

        best = final_state.get("best_report") or {}
        score = critique.get("overall_score", "N/A")
        best_score = best.get("score", score)

        try:
            from cli_ui import _safe_write
            _safe_write("\n")
            _safe_write("=" * 50 + "\n")
            _safe_write(
                f"Revisions ran out ({final_state.get('revision_count', 0)} / "
                f"{os.getenv('MAX_REVISIONS', '3')}) before approval.\n"
            )
            if best:
                _safe_write(
                    f"Best round so far: {best.get('revision')} ({best.get('score')}/100) "
                    f"(current: {score}/100).\n"
                )
            else:
                _safe_write(f"Current score: {score}/100.\n")
            answer = input(
                "Add how many more revision rounds? (0 = keep the best report and stop) > "
            ).strip()
        except EOFError:
            answer = "0"

        extra = 0
        try:
            extra = int(answer)
        except ValueError:
            extra = 0
        if extra <= 0:
            return final_state

        new_max = final_state.get("revision_count", 0) + extra
        os.environ["MAX_REVISIONS"] = str(new_max)


def _stream_with_spinner(topic: str, thread_id=None, llm=None) -> dict:
    """Consume the stream, showing a spinner while each step runs."""
    spinner = _Spinner()

    def on_progress(text: str):
        if spinner.running:
            spinner.set_label(text)

    def on_step(step: str, state: dict):
        spinner.finish()
        _log_step(step, state)
        spinner.start("Đang chạy bước tiếp theo…")

    spinner.start("Đang chạy bước tiếp theo…")
    try:
        return consume_stream(
            stream(topic, thread_id=thread_id, llm=llm, on_progress=on_progress),
            on_step=on_step,
        )
    finally:
        spinner.finish()


if __name__ == "__main__":
    main()