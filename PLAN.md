# Research & Content Validator — Kế Hoạch Sửa Đổi Chi Tiết

## Tổng Quan Dự Án

Pipeline multi-agent dùng LangGraph: **Planner → Researcher → Writer → Critic** (loop revision).
Mục tiêu: tự nghiên cứu chủ đề → viết báo cáo có trích dẫn → phê duyệt tự động.

---

## Phase 1 — Độ Tin Cậy & Chi Phí (Ưu tiên cao, effort thấp)

### 1.1 Cost Tracking — Thống kê chi phí per run

**Vấn đề:** Không biết bao nhiêu token/cost cho mỗi lần chạy, khó kiểm soát khi scale.

**File cần sửa:**

`models/llm.py` — Thêm capture usage_metadata sau mỗi call:
```python
# ponytail: global lock, per-account locks if throughput matters
usage = result.usage_metadata or {}
token_count = {
    "input": usage.get("input_tokens", 0),
    "output": usage.get("output_tokens", 0),
}
call_cost = estimate_cost(provider_family, token_count["input"], token_count["output"])
state["token_log"].append({
    "step": step_name,          # planner, researcher, writer, critic
    "model": MODEL_NAME,
    "tokens": token_count,
    "cost_usd": call_cost,
    "timestamp": datetime.now().isoformat(),
})
state["total_cost_usd"] = round(sum(c["cost_usd"] for c in state["token_log"]), 4)
```

`output.py` — Xuất `cost_summary.json`:
```python
def export_cost_summary(state: dict, output_dir: str):
    cost = {
        "total_cost_usd": state.get("total_cost_usd", 0),
        "total_tokens": sum(c["tokens"]["input"] + c["tokens"]["output"] for c in state.get("token_log", [])),
        "per_step": state.get("token_log", []),
    }
    with open(f"{output_dir}/cost_summary.json", "w") as f:
        json.dump(cost, f, indent=2)
```

`main.py` — Thêm flag `--budget`:
```python
parser.add_argument("--budget", type=float, default=None, help="Maximum USD budget per run")
```
Kiểm tra trước khi bắt đầu workflow.

**Effort:** 2 giờ
**Risk:** Thấp — chỉ thêm metadata, không thay đổi logic hiện tại.

---

### 1.2 Output Validation Gate — Xác thực structured output

**Vấn đề:** LLM đôi khi trả về JSON không đúng schema → crash hoặc dữ liệu hỏng.

**File cần sửa:** `agents/common.py` — Thêm hàm validate sau mỗi `structured_call`:
```python
from pydantic import ValidationError

def validate_structured_output(raw_output: str, schema: type) -> object:
    """Re-parse raw JSON string through Pydantic schema. Raises on invalid shape."""
    try:
        data = json.loads(raw_output)
        return schema(**data)
    except (json.JSONDecodeError, ValidationError) as e:
        raise OutputParserException(f"Schema validation failed: {e}")
```

**File:** `agents/common.py` — Gọi validate trong `structured_call` sau khi parse:
```python
parsed = parse_response(raw)
validated = validate_structured_output(raw, schema)  # ← thêm dòng này
return validated
```

**Effort:** 1 giờ
**Risk:** Thấp — bắt lỗi sớm hơn, giúp retry đúng cách.

---

### 1.3 Graceful Search Fallback — Xử lý khi search không có kết quả

**Vấn đề:** Researcher crash khi Tavily trả về empty results.

**File cần sửa:** `tools/search.py`:
```python
# ponytail: returns placeholder on empty search, loses real citations
results = tavily_search(query)
if not results:
    results = [{
        "title": f"No search results for '{query}'",
        "url": "",
        "content": f"[Fallback] No external sources found for: {query}. Use general knowledge.",
    }]
```

**Effort:** 30 phút
**Risk:** Thấp — đảm bảo pipeline không dừng đột ngột.

---

## Phase 2 — Chất Lượng & Độ Sâu

### 2.1 Parallel Researcher Execution — Tăng tốc research

**Vấn đề:** Researcher gọi search tuần tự (hoặc 3 worker), mỗi câu hỏi chờ nhau.

**File cần sửa:** `agents/researcher.py`:
```python
import asyncio
from functools import partial

async def _research_one_async(q: str, system: str, llm=None):
    # wrap synchronous research_one in thread pool
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(_research_one, q, system, llm))

async def research_parallel_async(questions, system, llm=None):
    semaphore = asyncio.Semaphore(int(os.getenv("RESEARCHER_MAX_WORKERS", "5")))
    async def bounded(q):
        async with semaphore:
            return await _research_one_async(q, system, llm)
    tasks = [bounded(q) for q in questions]
    return await asyncio.gather(*tasks)

def research_node(state: WorkflowState, llm=None, progress=None) -> dict:
    # ... existing setup ...
    # Replace ThreadPoolExecutor with asyncio
    loop = asyncio.new_event_loop()
    results = loop.run_until_complete(research_parallel_async(questions, system, llm))
    # ... rest same ...
```

**File:** `main.py` — Thêm env var `RESEARCHER_MAX_WORKERS`.

**Effort:** 4 giờ
**Risk:** Trung bình — cần test kỹ với async graph context. LangGraph streaming có thể tương tác.

---

### 2.2 Fact-Checking Agent — Kiểm chứng sự thật

**Vấn đề:** Writer có thể hallucinate claims không có trong sources.

**File mới:** `agents/fact_checker.py`:
```python
from .schemas import FactCheckReport
from .common import load_prompt, structured_call

def fact_check_node(state: WorkflowState, llm=None) -> dict:
    report = state.get("body", "")
    claims = state.get("key_claims", [])
    findings = state.get("raw_findings", {})
    
    # For each claim, verify against findings
    verifications = []
    for claim in claims:
        # Re-query search for this specific claim
        search_results = search(claim, max_results=3)
        # Ask LLM to verify
        verified: dict = structured_call(
            llm, dict,
            load_prompt("fact_checker.txt"),
            f"Claim: {claim}\n\nEvidence: {search_results}"
        )
        verifications.append({
            "claim": claim,
            "verified": verified.get("verdict") == "VERIFIED",
            "confidence": verified.get("confidence", 0),
            "evidence_summary": verified.get("summary", ""),
        })
    
    return {"fact_checks": verifications}
```

**File:** `prompts/fact_checker.txt` (new) — Prompt hướng dẫn LLM xác minh claim.

**File:** `agents/schemas.py` — Thêm `FactCheckReport` model.

**File:** `graph.py` — Thêm node `fact_checker` giữa Writer và Critic (hoặc làm optional step).

**Effort:** 6 giờ
**Risk:** Trung bình — thêm 1 node vào workflow, cần test routing.

---

### 2.3 Evaluation Criteria Expansion — Mở rộng tiêu chí đánh giá

**File:** `evaluation/criteria.py` — Thêm tiêu chí mới:

```python
EVALUATION_DIMENSIONS = {
    # Existing
    "factual_accuracy": {"weight": 0.30, "description": "Claims supported by evidence"},
    "citation_support": {"weight": 0.25, "description": "Each claim has a valid source"},
    "coherence": {"weight": 0.20, "description": "Logical flow and structure"},
    "objectivity_bias": {"weight": 0.10, "description": "Neutral tone, no bias"},
    "completeness": {"weight": 0.15, "description": "All aspects of topic covered"},
    # New
    "novelty_score": {"weight": 0.0, "description": "Non-obvious insights (added but not scored by default)"},
    "actionability_score": {"weight": 0.0, "description": "Practical next steps included"},
    "readability_score": {"weight": 0.0, "description": "Grade level appropriateness"},
}
```

**File:** `agents/critic.py` — Thêm prompt instruction cho các tiêu chí mới (optional toggle).

**Effort:** 3 giờ
**Risk:** Thấp — mở rộng không phá cấu trúc hiện tại.

---

### 2.4 Citation Quality Check — Kiểm tra chất lượng trích dẫn

**File:** `agents/critic.py` — Thêm dimension `citation_quality`:

```python
citation_quality_score = 0
for citation in report.citations:
    url = citation.get("url", "")
    if not url:
        citation_quality_score -= 5  # missing URL
        continue
    # Heuristic: check domain reputation
    domain = urlparse(url).hostname
    if domain in KNOWN_REPUTABLE_DOMAINS:  # e.g., nature.com, arxiv.org, wikipedia.org
        citation_quality_score += 3
    elif domain and ".edu" in domain:
        citation_quality_score += 2
    else:
        citation_quality_score += 1  # neutral
```

**File:** `agents/schemas.py` — Thêm `citation_quality` vào Critique schema.

**Effort:** 2 giờ
**Risk:** Thấp.

---

## Phase 3 — UX & Workflow

### 3.1 Human-in-the-Loop Checkpoints

**Vấn đề:** Không có điểm dừng để người dùng xem xét kết quả trung gian.

**File:** `graph.py` — Thêm node `human_review`:
```python
def human_review_node(state: WorkflowState, llm=None, progress=None) -> dict:
    print("\n=== DRAFT READY FOR REVIEW ===")
    print(f"Title: {state.get('title')}")
    print(f"Summary: {state.get('summary', '')[:200]}...")
    feedback = input("\n[Human] Approve (y), Revise with feedback, or Abort (r/a)? ")
    if feedback.strip().lower() == "y":
        return {"manual_approval": True, "feedback": ""}
    elif feedback.strip().lower() == "r":
        additional_feedback = input("Provide revision feedback: ")
        return {"manual_approval": False, "feedback": additional_feedback, "draft_rejected": True}
    else:
        return {"manual_approval": False, "feedback": "ABORTED", "draft_rejected": True, "aborted": True}
```

**File:** `graph.py` — Add conditional edge từ `human_review` → `writer` (nếu rejected) hoặc → `critic` (nếu approved).

**File:** `cli_ui.py`, `webui.py` — Hiển thị trạng thái chờ user input.

**File:** `main.py` — Thêm flag `--human-review` để bật/tắt.

**Effort:** 4 giờ
**Risk:** Trung bình — cần update graph edges.

---

### 3.2 Multi-Format Export

**Vấn đề:** Chỉ xuất Markdown + JSON, thiếu PDF/DOCX.

**File:** `requirements.txt` — Thêm:
```
markdown>=3.5
weasyprint>=61.0  # or pandoc if preferred
python-docx>=1.1
```

**File:** `output.py` — Thêm functions:
```python
def export_pdf(report_md: str, output_path: str):
    import markdown
    from weasyprint import HTML, CSS
    html_body = markdown.markdown(report_md, extensions=['tables', 'fenced_code'])
    html_content = f"""
    <html><head><style>body {{ font-family: serif; line-height: 1.6; }}</style></head>
    <body>{html_body}</body></html>
    """
    HTML(string=html_content).write_pdf(output_path)

def export_docx(report_md: str, output_path: str):
    from docx import Document
    from docx.shared import Pt
    doc = Document()
    for line in report_md.split('\n'):
        if line.startswith('# '):
            doc.add_heading(line[2:], level=0)
        elif line.startswith('## '):
            doc.add_heading(line[3:], level=1)
        elif line.startswith('### '):
            doc.add_heading(line[4:], level=2)
        else:
            doc.add_paragraph(line)
    doc.save(output_path)
```

**File:** `main.py` — Thêm flag `--format pdf|docx|md` (default: md).

**Effort:** 4 giờ
**Risk:** Thấp — thêm function mới, không ảnh hưởng workflow chính.

---

### 3.3 Template System

**Vấn đề:** Report HTML mặc định đơn giản, không có styling.

**File mới:** `templates/report_template.html` — Jinja2 template với:
- Styled header + metadata
- TOC sidebar
- Citations hover tooltip
- Key claims callout box
- Print-friendly CSS

**File:** `output.py` — Render template:
```python
def render_html_template(report: dict, template_path: str) -> str:
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(os.path.dirname(template_path)))
    template = env.get_template(os.path.basename(template_path))
    return template.render(**report)
```

**Effort:** 3 giờ
**Risk:** Thấp.

---

## Phase 4 — Extensibility

### 4.1 Agent Registry + Config Pipeline

**File mới:** `agents/registry.py`:
```python
from .planner import PlannerAgent
from .researcher import ResearcherAgent
from .writer import WriterAgent
from .critic import CriticAgent

AGENT_REGISTRY = {
    "planner": PlannerAgent,
    "researcher": ResearcherAgent,
    "writer": WriterAgent,
    "critic": CriticAgent,
    "fact_checker": None,  # placeholder for Phase 2
    "editor": None,        # placeholder
}
```

**File:** `graph.py` — Xây workflow từ config dict:
```python
def build_workflow(config: dict) -> StateGraph:
    graph = StateGraph(WorkflowState)
    nodes = config.get("nodes", ["planner", "researcher", "writer", "critic"])
    for node_name in nodes:
        agent_cls = AGENT_REGISTRY.get(node_name)
        if agent_cls:
            graph.add_node(node_name, agent_cls.node)
    # ... conditional edges ...
    return graph
```

**File mới:** `config/default.yaml`:
```yaml
pipeline:
  nodes:
    - planner
    - researcher
    - writer
    - critic
  max_revisions: 3
  human_review: false
  evaluation:
    enable_fact_check: true
    criteria:
      - factual_accuracy
      - citation_support
      - coherence
      - objectivity_bias
      - completeness
      - novelty_score  # optional
```

**Effort:** 8 giờ
**Risk:** Trung bình — refactor graph building logic.

---

### 4.2 RAG Extension — Knowledge Base Vector Search

**Vấn đề:** Chỉ search web, không khai thác knowledge base riêng.

**File:** `tools/search.py` — Thêm function `vector_search()`:
```python
from chromadb import Client

class VectorSearchTool:
    def __init__(self, db_path: str = "./output/vector_store"):
        self.client = Client(db_path)
        self.collection = self.client.get_or_create_collection("research_kb")
    
    def add_documents(self, docs: list[dict]):
        """Add documents to vector store."""
        self.collection.add(
            documents=[d["content"] for d in docs],
            metadatas=[{"source": d.get("source", ""), "title": d.get("title", "")} for d in docs],
            ids=[f"doc_{i}" for i in range(len(docs))],
        )
    
    def search(self, query: str, top_k: int = 5) -> list[dict]:
        results = self.collection.query(query_embeddings=[[...]], n_results=top_k)
        return [{"title": m["title"], "url": m["source"], "content": d} 
                for m, d in zip(results["metadatas"][0], results["documents"][0])]
```

**File:** `main.py` — Thêm flag `--knowledge-base <dir>` để load documents trước.

**File:** `tools/search.py` — Merge web + vector results by relevance score.

**Effort:** 6 giờ
**Risk:** Trung bình — cần setup ChromaDB.

---

### 4.3 Supervisor Agent — Quan sát & điều phối

**Vấn đề:** Pipeline cứng nhắc, không tự điều chỉnh khi gặp vấn đề.

**File mới:** `agents/supervisor.py`:
```python
class SupervisorAgent:
    """Observes workflow state, decides if re-plan or deep-dive needed."""
    
    def __init__(self, llm):
        self.llm = llm
    
    def decide(self, state: WorkflowState) -> dict:
        """Return action: PLANNING, RESEARCH, WRITING, DONE, or DEEP_DIVE."""
        prompt = load_prompt("supervisor.txt")
        context = {
            "topic": state.get("topic"),
            "current_phase": state.get("current_phase"),
            "critique": state.get("critique"),
            "revision_count": state.get("revision_count"),
        }
        decision = structured_call(self.llm, dict, prompt, json.dumps(context))
        return decision
```

**File:** `prompts/supervisor.txt` (new) — Prompt hướng dẫn supervisor.

**File:** `graph.py` — Supervisor chạy ở start và sau mỗi critic cycle.

**Effort:** 8 giờ
**Risk:** Cao — kiến trúc thay đổi đáng kể.

---

## Phase 5 — Production Readiness

### 5.1 Authentication cho Web UI

**File:** `webui.py` — Thêm basic auth hoặc JWT middleware:
```python
from flask import session, redirect, url_for

@app.before_request
def require_login():
    if request.endpoint == 'static':
        return
    if not session.get('authenticated'):
        return redirect(url_for('login'))
```

**File:** `.env` — Thêm `WEBUI_USERNAME`, `WEBUI_PASSWORD`.

**Effort:** 2 giờ

---

### 5.2 Containerization

**File mới:** `Dockerfile`:
```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["python", "webui.py"]
```

**File mới:** `docker-compose.yml`:
```yaml
services:
  validator:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./output:/app/output
    env_file: .env
```

**Effort:** 2 giờ

---

### 5.3 CI/CD Pipeline

**File mới:** `.github/workflows/test.yml`:
```yaml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      - run: pip install -r requirements.txt
      - run: python -m pytest tests/ -v
```

**File:** `requirements.txt` — Pin versions với `pip-compile`.

**Effort:** 1 giờ

---

## Summary — Tổng hợp Effort & Priority

| Phase | Items | Total Effort | Total Impact |
|-------|-------|--------------|-------------|
| Phase 1 | 3 items | ~3.5 giờ | ⭐⭐⭐ |
| Phase 2 | 4 items | ~15 giờ | ⭐⭐⭐ |
| Phase 3 | 3 items | ~11 giờ | ⭐⭐ |
| Phase 4 | 3 items | ~22 giờ | ⭐⭐ |
| Phase 5 | 3 items | ~5 giờ | ⭐ |

**Tổng cộng:** ~56 giờ (khoảng 2-3 sprint, mỗi sprint 2 tuần).

---

## Recommended Sprint Plan

### Sprint 1 (2 tuần) — Phase 1 + Start Phase 2
- [ ] Cost tracking (2h)
- [ ] Output validation gate (1h)
- [ ] Search fallback (30m)
- [ ] Parallel researcher research (4h)
- [ ] **Demo:** Show cost summary + 2x faster research

### Sprint 2 (2 tuần) — Continue Phase 2
- [ ] Fact-checking agent (6h)
- [ ] Evaluation criteria expansion (3h)
- [ ] Citation quality check (2h)
- [ ] Human-in-the-loop checkpoints (4h)
- [ ] **Demo:** Show fact-checked report + human review flow

### Sprint 3 (2 tuần) — Phase 3 + 4
- [ ] Multi-format export (4h)
- [ ] Template system (3h)
- [ ] Agent registry + config (8h)
- [ ] **Demo:** Show PDF export + configurable pipeline

### Sprint 4 (2 tuần) — Phase 4-5
- [ ] RAG extension (6h)
- [ ] Supervisor agent (8h) — optional
- [ ] Auth + Docker + CI/CD (5h)
- [ ] **Demo:** Show RAG-powered research + production deployment

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Parallel researcher breaks LangGraph streaming | Medium | High | Test with fake LLM first; fallback to ThreadPool |
| Fact-checker adds too much latency | High | Medium | Make it optional flag `--no-fact-check` |
| Config-driven pipeline regresses existing behavior | Medium | High | Full test suite before merge; canary deploy |
| Human-in-the-loop blocks automated runs | Low | Medium | Only enable with `--human-review` flag |
| Vector DB increases memory footprint | Medium | Low | Chunk documents; limit collection size |

---

## Success Metrics

| Metric | Current | Target (Phase 2) | Target (Phase 4) |
|--------|---------|------------------|------------------|
| Research speed | ~30s/topic | ~10s/topic | ~5s/topic |
| Cost per run | Unknown | Tracked & logged | < $0.50/topic |
| Report quality score | ~75/100 | ~85/100 | ~90/100 |
| Hallucination rate | Unknown | <5% claims | <2% claims |
| Export formats | 1 (md) | 3 (md/pdf/docx) | 5 (+html,txt) |
| Human intervention needed | Often | Rarely | Never (fully auto) |

---

*Lưu ý: Roadmap này có thể điều chỉnh dựa trên feedback thực tế sau mỗi sprint.*
