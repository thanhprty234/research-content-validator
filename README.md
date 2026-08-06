# Research & Content Validator (Supervisor + Critic)

Hệ thống pipeline dùng **LangGraph** với 4 agent: **Planner → Researcher → Writer → Critic**
để tự nghiên cứu một chủ đề, viết báo cáo, rồi phê duyệt/đánh giá theo vòng lặp.

## Cấu trúc dự án

```
project/
│
├── agents/                  # Các agent (mỗi file = 1 node trong graph)
│   ├── common.py            # Helper dùng chung (load prompt + structured call)
│   ├── planner.py           # Lập kế hoạch nghiên cứu (struct output)
│   ├── researcher.py        # Tìm kiếm & gom dữ liệu (dùng tools/search)
│   ├── writer.py            # Viết báo cáo hoàn chỉnh (struct output)
│   ├── critic.py            # Phê duyệt/đánh giá (struct output)
│   └── schemas.py           # Pydantic models dùng chung
│
├── prompts/                 # System prompts (tách rời khỏi code)
│   ├── planner.txt
│   ├── researcher.txt
│   ├── writer.txt
│   └── critic.txt
│
├── tools/
│   └── search.py            # Search tool + caching (SQLite)
│
├── models/
│   └── llm.py               # Model abstraction (OpenAI/Anthropic/Gemini/Ollama/3rd-party)
│
├── evaluation/
│   ├── criteria.py          # Bộ tiêu chí đánh giá + dataset mẫu
│   └── evaluate.py          # Đo chất lượng báo cáo
│
├── graph.py                 # LangGraph workflow + checkpointer (memory/sqlite)
├── stream_events.py         # Gắn nhãn bước tiến trình (dùng cho UI + CLI)
├── cli_ui.py                # Trình bày terminal (spinner, verdict, safe-unicode)
├── output.py                # Ghi report.md + verdict.json
├── webui.py                 # Web UI (Flask + SSE real-time)
├── templates/               # Trang HTML cho web UI
├── main.py                  # CLI (streaming + spinner, resume, observability)
├── output/                  # Kết quả (report.md, verdict.json, cache, checkpoints)
├── tests/                   # Test offline (fake LLM, không cần API key)
│   ├── __init__.py
│   ├── fakes.py             # FakeLLM dùng chung
│   ├── test_agents.py       # Test từng agent node
│   ├── test_graph.py        # Test logic routing (rewrite/finish)
│   └── test_smoke.py        # Test tích hợp toàn luồng
├── requirements.txt
└── .env.example
```

## Luồng workflow

```
topic
  ▼
Planner ──► research_questions + outline
  ▼
Researcher ──► facts + sources (dùng tools/search, có cache)
  ▼
Writer ──► draft report (Markdown + citations)
  ▼
Critic ──► approve? ──REVISE──► Writer (loop, tối đa MAX_REVISIONS)
  │
 APPROVED
  ▼
report.md + verdict.json
```

## Cài đặt

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> Lưu ý: dùng Python bản chuẩn (Python 3.13 từ python.org), KHÔNG dùng Python của MSYS2
> vì không cài được các gói như `pydantic`/`tiktoken`.

## Chọn model / nơi dán API key

Tạo file `.env` từ `.env.example`, rồi chọn nhà cung cấp bằng `MODEL_PROVIDER`:

```ini
MODEL_PROVIDER=openai      # openai | anthropic | gemini | ollama | openrouter | deepseek | groq | together | opencode | local
MODEL_NAME=gpt-4o-mini
OPENAI_API_KEY=sk-dán-key-thật-của-bạn-vào-đây
```

| Provider | MODEL_PROVIDER | Biến key | MODEL_NAME (ví dụ) |
|----------|----------------|----------|--------------------|
| OpenAI | `openai` | `OPENAI_API_KEY` | `gpt-4o-mini` |
| Anthropec | `anthropic` | `ANTHROPIC_API_KEY` | `claude-3-5-sonnet-20241022` |
| Google Gemini | `gemini` | `GEMINI_API_KEY` | `gemini-1.5-pro` |
| Ollama (local) | `ollama` | (không cần) | `llama3.2` |
| OpenRouter | `openrouter` | `OPENROUTER_API_KEY` | `anthropic/claude-3.5-sonnet` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| Groq | `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| Together | `together` | `TOGETHER_API_KEY` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| OpenCode Zen | `opencode` | `OPENCODE_API_KEY` | model hỗ trợ bởi Zen (vd `deepseek/deepseek-chat`) |
| LM Studio / llama.cpp | `local` | `OPENAI_API_KEY` (bất kỳ) | tên model local |

Các provider **OpenAI-compatible** (`openrouter`, `deepseek`, `groq`, `together`, `mistral`, `opencode`)
tự động dùng base URL đúng, chỉ cần đặt đúng key. Còn `openai`/`azure`/`local`/`custom`
thì thiết lập `OPENAI_BASE_URL` trong `.env`.

API key chỉ được đặt trong file **`.env`** (đã có trong `.gitignore`) — **không bao giờ**
dán trực tiếp vào code.

## Cách dùng

```powershell
# Chạy bình thường
python main.py --topic "Lợi ích và rủi ro của việc nhịn ăn gián đoạn"

# Streaming tiến trình theo từng node
python main.py --topic "Biến đổi khí hậu" --stream

# Đổi provider/model nhanh từ CLI
python main.py --topic "AI and jobs" --provider anthropic --model claude-3-5-sonnet-20241022

# Giới hạn số vòng sửa
python main.py --topic "X" --max-revisions 5

# Ngưỡng điểm để critic tự APPROVED (mặc định 85) — có thể đặt trong .env:
# APPROVE_THRESHOLD=90

# In danh sách provider / cấu hình model đang dùng
python main.py --list-providers
python main.py --print-config
```

### Spinner khi chạy CLI

Khi dùng `--stream`, CLI hiện spinner (⠋⠙⠹…) làm "minh họa chờ", kèm log màu
mỗi khi một bước hoàn thành (Planner → Researcher → Writer → Critic):

```powershell
python main.py --topic "Chủ đề" --stream   # hiện spinner + log màu từng bước
```

## Web UI (giao diện trực quan)

Chạy một web app đơn giản để dùng bằng chuột — không cần gõ lệnh:

```powershell
python webui.py                      # mở http://127.0.0.1:5000
python webui.py --host 0.0.0.0 --port 8000
```

Tính năng:
- Form nhập chủ đề, chọn provider, model và số vòng sửa tối đa.
- **Streaming real-time (SSE)**: mỗi bước hiện spinner xoay + đánh dấu ✔ khi xong.
- Khi hoàn thành: hiện verdict (APPROVED/REVISE), điểm, báo cáo Markdown, issues.

Giao diện đọc cấu hình model/key từ file `.env` (giống CLI), nên chỉ cần chọn
provider là chạy được.

### Checkpointing & resume

Nếu bị gián đoạn, workflow lưu trạng thái (thread). Chạy lại với cùng `--thread-id`
và `--resume` để tiếp tục:

```powershell
python main.py --topic "X" --thread-id t1          # lần 1
python main.py --topic "X" --thread-id t1 --resume # tiếp tục (không làm lại từ đầu)
```

Backend checkpointer: mặc định là bộ nhớ (`CHECKPOINTER=memory`); muốn lưu bền qua
các lần chạy dùng `CHECKPOINTER=sqlite` (file `output/checkpoints.sqlite`).

## Structured Output (Pydantic)

Planner, Writer, Critic trả về JSON chuẩn qua Pydantic (xem `agents/schemas.py`):
- `ResearchPlan {research_questions, outline}`
- `Report {title, summary, body, key_claims, citations}`
- `Critique {dimensions, overall_score, verdict, issues, suggested_revisions}`

Dùng `llm.with_structured_output(Schema)` nên output luôn hợp lệ, không cần parse thủ công.

## Caching

`tools/search.py` cache kết quả tìm kiếm vào `output/search_cache.sqlite` để tránh
gọi API web nhiều lần cho cùng câu query. Bật web search thật bằng `TAVILY_API_KEY`
trong `.env`; nếu không có, pipeline dùng placeholder offline để vẫn chạy được.

## Observability (LangSmith)

Thêm vào `.env`:

```ini
LANGCHAIN_API_KEY=lsv2-...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=research-validator
```

Khi có key, mọi lần chạy đều được trace lên LangSmith (prompt, token, latency, lỗi).

## Evaluation

Đo chất lượng báo cáo theo bộ tiêu chí (`factual_accuracy, citation_support,
coherence, objectivity_bias, completeness`) trên dataset mẫu:

```powershell
python -m evaluation.evaluate              # chạy tất cả test mẫu
python -m evaluation.evaluate --json       # xuất JSON
```

## Kiểm thử nhanh (không cần API key)

```powershell
python -m tests.test_smoke     # toàn luồng + vòng lặp sửa
python -m tests.test_agents    # từng agent node
python -m tests.test_graph     # logic routing
```

Dùng fake LLM để chạy các node và kiểm tra vòng lặp sửa có dừng đúng không.
