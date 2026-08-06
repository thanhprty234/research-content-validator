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
    """Run the workflow and push events onto the job queue."""
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
        job = {"queue": queue.Queue(), "done": False, "result": None}
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
            yield f"event: update\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@app.route("/providers")
def providers():
    from models.llm import PROVIDER_ALIASES
    return json.dumps(sorted(PROVIDER_ALIASES))


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser(description="Research & Content Validator UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    print(f"Open the UI at http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)