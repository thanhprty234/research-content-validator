# Research & Content Validator — Roadmap

## Phase 0 — Foundation (Already Done ✅)
- [x] Multi-agent pipeline (Planner → Researcher → Writer → Critic)
- [x] Structured output via Pydantic
- [x] Multiple LLM providers (11+)
- [x] Search + Plan caching (SQLite)
- [x] LangGraph checkpointing & resume
- [x] CLI + Web UI (Flask + SSE)
- [x] Offline testing (FakeLLM)
- [x] LangSmith observability

---

## Phase 1 — Reliability & Cost (Quick Wins)

### 1.1 Cost Tracking
**File:** `models/llm.py`, `graph.py`
```python
# After each LLM call, capture usage_metadata
usage = result.usage_metadata
state["token_usage"].append({"model": MODEL_NAME, "input": usage.input_tokens, "output": usage.output_tokens, "step": node_name})
state["estimated_cost"] += calculate_cost(MODEL_PROVIDER, usage.input_tokens, usage.output_tokens)
```
**File:** `output.py` — export `cost_summary.json` alongside report.
**File:** `main.py` — add `--budget` flag, abort if estimated cost exceeds threshold.

→ skipped: full billing integration; add when tracking per-agent cost matters.

### 1.2 Output Validation Gate
**File:** `agents/common.py` — add `validate_output()` that re-parses structured output with Pydantic and raises `ValidationError` on corruption.
Called after every `structured_call` — catches silent model hallucination in JSON shape.

→ skipped: separate validation service; add when multi-model QA pipeline needed.

### 1.3 Graceful Search Fallback
**File:** `tools/search.py` — current code raises on empty results. Add:
```python
if not results:
    return [{"title": f"No results for '{query}'", "url": "", "content": "Fallback to internal knowledge"}]
```
Prevents Researcher crash on niche topics.

---

## Phase 2 — Quality & Depth

### 2.1 Parallel Researcher Execution
**File:** `agents/researcher.py` — replace sequential `ThreadPoolExecutor(max_workers=3)` with asyncio-based parallel execution with rate limiting:
```python
semaphore = asyncio.Semaphore(5)
async def _research_one_async(q):
    async with semaphore:
        await asyncio.gather(*[_research_one(q, llm) for q in questions])
```
**File:** `agents/researcher.py` — add `RESEARCHER_MAX_WORKERS` env var.

→ skipped: full async graph rewrite; add when researcher becomes bottleneck in benchmark.

### 2.2 Fact-Checking Agent
**File:** `agents/fact_checker.py` (new) — receives Report, queries each `key_claim` against cached search results, returns `{claim: {verified, evidence, confidence}}`.
**File:** `graph.py` — insert after Writer, before Critic (or as optional pre-critic step).
**File:** `agents/schemas.py` — add `FactCheckReport` Pydantic model.

→ skipped: independent fact-checking microservice; add when autonomous verification required.

### 2.3 Evaluation Criteria Expansion
**File:** `evaluation/criteria.py` — add:
- `novelty_score`: does the report offer non-obvious insights?
- `actionability_score`: are there concrete next steps?
- `readability_score`: Flesch-Kincaid grade level (use `readabilipy` or manual heuristic).
- `structural_quality`: proper heading hierarchy, logical flow.
**File:** `evaluation/evaluate.py` — update scoring weight defaults.

→ skipped: human-annotated evaluation dataset; add when quantitative benchmarking needed.

### 2.4 Citation Quality Check
**File:** `agents/critic.py` — expand critique dimensions to include `citation_quality`:
- URL validity (dead link detection via HEAD request)
- Source authority (domain reputation heuristic)
- Claim-to-source alignment score

---

## Phase 3 — UX & Workflow

### 3.1 Human-in-the-Loop Checkpoints
**File:** `graph.py` — add `human_review` node after Writer, before Critic:
```python
def human_review_node(state: WorkflowState, llm=None) -> dict:
    user_input = input("[Human Review] Approve draft? (y/n/feedback): ")
    if user_input.strip().lower() == "n":
        return {"manual_feedback": user_input, "draft_rejected": True}
    return {"manual_feedback": "approved"}
```
**File:** `graph.py` — add conditional routing: `draft_rejected=True` → back to Writer with feedback.
**File:** `cli_ui.py`, `webui.py` — stream waiting state.

→ skipped: full async input channel; add when web UI needs non-blocking human review.

### 3.2 Multi-Format Export
**File:** `output.py` — add `export_pdf()` using `weasyprint` or `markdown-to-pdf`:
```python
def export_pdf(report_path: str, output_path: str):
    import markdown
    from weasyprint import HTML
    html = markdown.markdown(open(report_path).read())
    HTML(string=f"<style>...</style>{html}").write_pdf(output_path)
```
**File:** `main.py` — add `--format pdf|docx|html` flag.

→ skipped: full print-ready layout engine; add when PDF quality matters for publishing.

### 3.3 Template System
**File:** `templates/` — create `report_template.html` with styled citations, TOC, and key claims sidebar.
**File:** `output.py` — render template with Jinja2 instead of raw Markdown copy.
**File:** `prompts/writer.txt` — add template variable injection instructions.

→ skipped: full Theming engine; add when user custom output styling is needed.

---

## Phase 4 — Extensibility

### 4.1 Agent Registry + Config Pipeline ✅
**File:** `agents/registry.py` — `load_registry()`: YAML-backed registry trả `dict[str, AgentConfig]`.
**File:** `config/agents.yaml` — khai báo planner/researcher/writer/critic (module + class).
**File:** `graph.py` — import `load_registry()` (dòng 17) và gọi lúc build (dòng 133) để validate agent config khi startup.
Ghi chú: các node trong graph vẫn bind qua closure tường minh; wiring động từ registry hoãn đến khi có hình thái pipeline thứ hai.

→ skipped: config-driven edge wiring hoàn toàn; thêm khi pipeline cần đổi hình dạng runtime.

### 4.2 RAG Extension
**File:** `tools/search.py` — add `vector_search()` using ChromaDB or FAISS:
```python
from chromadb import Client
client = Client("./output/vector_store")
collection = client.get_or_create_collection("knowledge")
results = collection.query(query_texts=[query], n_results=5)
```
**File:** `main.py` — add `--knowledge-base <path>` flag to load docs into vector store first.
**File:** `tools/search.py` — merge web results with vector results by relevance score.

→ skipped: full embedding model fine-tuning; add when domain-specific accuracy matters.

### 4.3 Supervisor Agent
**File:** `agents/supervisor.py` (new) — observes full workflow state, decides whether to re-plan, re-research, or delegate to sub-agents for deep dives.
**File:** `graph.py` — Supervisor runs at graph start AND after each Critic REVISE cycle.

→ skipped: full ReAct-style supervisor; add when complex multi-topic research is needed.

---

## Phase 5 — Production Readiness

### 5.1 Authentication for Web UI
**File:** `webui.py` — add basic auth or JWT middleware.
**File:** `.env` — add `WEBUI_USERNAME`, `WEBUI_PASSWORD`.

### 5.2 Containerization
**File:** `Dockerfile` — multi-stage build with Python 3.13 slim base.
**File:** `docker-compose.yml` — services: app + SQLite volume + optional Tavily proxy.

### 5.3 CI/CD
**File:** `.github/workflows/test.yml` — run `pytest tests/` on push/PR.
**File:** `requirements.txt` — pin versions with `pip-compile`.

---

## Priority Matrix

| Priority | Item | Effort | Impact | Phase |
|----------|------|--------|--------|-------|
| P0 | Cost tracking + budget guard | 2h | ⭐⭐⭐ | 1 |
| P0 | Output validation gate | 1h | ⭐⭐⭐ | 1 |
| P0 | Graceful search fallback | 30m | ⭐⭐ | 1 |
| P1 | Parallel researcher execution | 4h | ⭐⭐⭐ | 2 |
| P1 | Evaluation criteria expansion | 3h | ⭐⭐ | 2 |
| P1 | Human-in-the-loop checkpoints | 4h | ⭐⭐⭐ | 3 |
| P2 | Fact-checking agent | 6h | ⭐⭐⭐ | 2 |
| P2 | Multi-format export | 4h | ⭐⭐ | 3 |
| P2 | Citation quality check | 3h | ⭐⭐ | 2 |
| P3 | Template system | 3h | ⭐⭐ | 3 |
| P3 | Agent registry + config | 8h | ⭐⭐ | 4 |
| P3 | RAG extension | 6h | ⭐⭐⭐ | 4 |
| P3 | Supervisor agent | 8h | ⭐⭐ | 4 |
| P4 | Auth + Docker + CI/CD | 6h | ⭐ | 5 |

---

## Immediate Next Actions (Sprint 1)

1. **Cost Tracking** — Add token usage capture in `models/llm.py` → `output.py` export.
2. **Output Validation** — Add Pydantic re-parse in `common.py`.
3. **Search Fallback** — One-line fix in `tools/search.py`.
4. **Create `FACT_CHECK.md`** — Document fact-checking agent spec for Phase 2.

Start with cost tracking — it's 1-2 hours, highest ROI, and reveals real spending patterns before any bigger work.