"""Web UI for the Research & Content Validator.

Runs a Flask app that streams workflow progress to the browser in real time
using Server-Sent Events (SSE).

Usage:
    python webui.py            # http://127.0.0.1:5000
    python webui.py --host 0.0.0.0 --port 8000
"""

import argparse
import json
import os
import queue
import threading

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, Response, render_template, request

from graph import stream
from models.llm import get_model, model_config_from_env
from stream_events import consume_stream, step_message

app = Flask(__name__)

_JOBS = {}  # thread_id -> {"queue": job_queue, "done": bool, "result": dict}


def _tune_env(args):
    os.environ["MAX_REVISIONS"] = str(args.get("max_revisions", 3))
    os.environ["CHECKPOINTER"] = "memory"


def _run_job(args: dict):
    """Run the workflow and push events onto the job queue.

    When the critic still returns REVISE after MAX_REVISIONS, the job emits a
    ``paused`` event (with the best report) so the UI can offer to add more
    revision rounds or keep the best report.
    """
    cfg = model_config_from_env()
    if args.get("provider"):
        cfg.provider = args["provider"]
    if args.get("model"):
        cfg.model = args["model"]

    llm = get_model(cfg)
    job = _JOBS.setdefault(args["thread_id"], {"queue": queue.Queue(), "done": False, "result": None})

    def on_progress(text: str):
        job["queue"].put({"type": "progress", "message": text})

    def on_step(step: str, state: dict):
        job["queue"].put({"type": "step", "step": step, "message": step_message(step, state)})

    def on_error(exc: Exception):
        job["queue"].put({"type": "error", "message": str(exc)})

    try:
        state = consume_stream(
            stream(args["topic"], thread_id=args["thread_id"], llm=llm, on_progress=on_progress),
            on_step=on_step,
            on_error=on_error,
        )
        job["state"] = state
        critique = state.get("critique") or {}
        verdict = critique.get("verdict", "UNKNOWN")
        max_rev = int(os.getenv("MAX_REVISIONS", "3"))
        revision_count = state.get("revision_count", 0)
        if verdict == "REVISE" and revision_count >= max_rev:
            job["paused"] = True
            job["queue"].put({
                "type": "paused",
                "result": _public_result(args["topic"], state),
                "thread_id": args["thread_id"],
                "max_revisions": max_rev,
                "revision_count": revision_count,
            })
        else:
            job["paused"] = False
            job["queue"].put({"type": "done", "result": _public_result(args["topic"], state)})
    except Exception as exc:  # belt-and-braces for errors raised outside the stream
        job["queue"].put({"type": "error", "message": str(exc)})
    finally:
        job["done"] = True


def _public_result(topic: str, state: dict) -> dict:
    state = state or {}
    critique = state.get("critique") or {}
    return {
        "topic": topic,
        "title": state.get("title"),
        "summary": state.get("summary"),
        "body": state.get("body"),
        "key_claims": state.get("key_claims", []),
        "citations": state.get("citations", []),
        "critique": critique,
        "revision_count": state.get("revision_count", 0),
        "best_report": state.get("best_report"),
        "best_critique": state.get("best_critique"),
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/stream")
def event_stream():
    """SSE endpoint. Validates args, spawns job, yields events."""
    topic = request.args.get("topic", "").strip()
    if not topic:
        return Response("bad request", status=400)

    thread_id = request.args.get("thread_id") or "web-ui"
    args = {
        "topic": topic,
        "provider": request.args.get("provider"),
        "model": request.args.get("model"),
        "max_revisions": int(request.args.get("max_revisions") or 3),
        "thread_id": thread_id,
    }
    _tune_env(args)

    job = _JOBS.get(thread_id)
    if not job or job["done"]:
        job = {"queue": queue.Queue(), "done": False, "result": None, "args": args}
        _JOBS[thread_id] = job
        import threading
        threading.Thread(target=_run_job, args=(args,), daemon=True).start()

    def generate():
        while True:
            try:
                event = job["queue"].get(timeout=1)
            except queue.Empty:
                # heartbeat keeps the SSE connection alive during long LLM calls
                yield f"event: ping\ndata: {json.dumps({'type': 'ping'})}\n\n"
                continue
            if event["type"] == "done":
                yield f"event: result\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                yield "event: close\ndata: {}\n\n"
                break
            if event["type"] == "error":
                yield f"event: error\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                yield "event: close\ndata: {}\n\n"
                break
            if event["type"] == "paused":
                yield f"event: paused\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                continue
            yield f"event: update\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@app.route("/continue", methods=["POST"])
def continue_job():
    """Add more revision rounds to a paused job and re-run the workflow."""
    data = request.get_json(silent=True) or request.form
    thread_id = data.get("thread_id") or "web-ui"
    job = _JOBS.get(thread_id)
    if not job:
        return json.dumps({"error": "no such job"}), 404

    try:
        extra = int(data.get("add_rounds") or 0)
    except ValueError:
        extra = 0
    if extra <= 0:
        return json.dumps({"error": "add_rounds must be > 0"}), 400

    max_rev = int(os.getenv("MAX_REVISIONS", "3"))
    prev = job.get("args") or {}
    args = {
        "topic": prev.get("topic") or data.get("topic", ""),
        "provider": prev.get("provider") or data.get("provider"),
        "model": prev.get("model") or data.get("model"),
        "max_revisions": max_rev + extra,
        "thread_id": thread_id,
    }
    _tune_env(args)
    job["args"] = args

    job["done"] = False
    job["paused"] = False
    import threading
    threading.Thread(target=_run_job, args=(args,), daemon=True).start()
    return json.dumps({"ok": True, "max_revisions": args["max_revisions"]})


@app.route("/finalize", methods=["GET"])
def finalize():
    """Persist the best report for a paused job and close its stream."""
    thread_id = request.args.get("thread_id") or "web-ui"
    job = _JOBS.get(thread_id)
    if not job or not job.get("state"):
        return json.dumps({"error": "no such job"}), 404

    from output import write_outputs
    out_dir = write_outputs(job["state"])
    job["paused"] = False
    job["done"] = True
    job["queue"].put({"type": "done", "result": _public_result(request.args.get("topic", ""), job["state"]), "saved": str(out_dir)})
    return json.dumps({"ok": True, "saved": str(out_dir)})


@app.route("/providers")
def providers():
    from models.llm import PROVIDER_ALIASES
    return json.dumps({
        "list": sorted(PROVIDER_ALIASES),
        "default": os.getenv("MODEL_PROVIDER", "openai"),
    })


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser(description="Research & Content Validator UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    print(f"Open the UI at http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)