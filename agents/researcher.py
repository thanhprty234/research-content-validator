"""Researcher agent: gather citable facts for each research question via search."""

from concurrent.futures import ThreadPoolExecutor, as_completed

from .common import load_prompt, structured_call
from .schemas import Note
from .state import WorkflowState
from tools.search import search

MAX_WORKERS = 3


def _research_one(q: str, system: str, llm=None) -> tuple:
    """Search + summarize a single research question into a note."""
    results = search(q, max_results=4)
    context = "\n\n".join(
        f"[{r.get('title', '')}] {r.get('url', '')}\n{r.get('content', '')}"
        for r in results
    )
    sources = [r["url"] for r in results if r.get("url")]

    note: Note = structured_call(
        llm,
        Note,
        system,
        f"Research question:\n{q}\n\nSearch results:\n{context}",
        max_tokens=1500,
    )
    note.sources = sources or note.sources
    return q, note


def research_node(state: WorkflowState, llm=None, progress=None) -> dict:
    """Graph node: search and gather notes for each research question (parallel)."""
    system = load_prompt("researcher.txt")
    questions = state.get("research_questions", []) or []
    total = len(questions)

    notes = {}
    findings = {}
    done = 0

    def tick(q, note):
        nonlocal done
        done += 1
        if progress:
            progress(f"Đã nghiên cứu {done}/{total} câu hỏi…")
        notes[q] = note.model_dump()
        findings[q] = {"question": q, "findings": note.findings, "sources": note.sources}

    if not questions:
        return {"notes": [], "raw_findings": []}

    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, total)) as pool:
        futures = {pool.submit(_research_one, q, system, llm): q for q in questions}
        for fut in as_completed(futures):
            q, note = fut.result()
            tick(q, note)

    ordered_notes = [notes[q] for q in questions if q in notes]
    ordered_findings = [findings[q] for q in questions if q in findings]
    return {"notes": ordered_notes, "raw_findings": ordered_findings}
