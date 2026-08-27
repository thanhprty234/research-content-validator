# Research & Content Validator

A multi-agent research pipeline with LLM-based planning, live web search, drafting, and a built-in critic loop with cost tracking and checkpointing.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![LangGraph](https://img.shields.io/badge/LangGraph-✅-blueviolet)](https://langchain-ai.github.io/langgraph/)

---

## ✨ Features

1. **Multi-agent LangGraph pipeline**: Planner → Researcher → Writer → Critic (configurable revision loop).
2. **Multi-provider model support**: OpenAI, Anthropic, Gemini, Ollama, OpenRouter, DeepSeek, Groq, Together, Mistral, OpenCode Zen, Azure, and any custom OpenAI-compatible endpoint.
3. **Built-in cost tracking & budget guard**: Estimates per-run token cost and aborts when budget is exceeded.
4. **Checkpoint / resume**: Save progress to `memory` (default) or `sqlite` and resume interrupted runs via `--resume`.
5. **Dual search fallback**: Tavily (optional, paid) → DuckDuckGo via `ddgs` (free, no key) → offline CSV placeholders.
6. **Citation quality gate**: Every claim must cite a source; broken links cause revision.
7. **Human-in-the-loop**: HITL checkpoint support for manual review before finalizing.
8. **Agent registry**: YAML-backed provider configuration with cost estimates.
9. **Web UI**: Flask app with real-time SSE streaming of workflow progress.

---

## 🚀 Quick Start

### 1. Clone & install

```bash
git clone https://github.com/thanhprty234/research-content-validator.git
cd research-content-validator
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — set MODEL_PROVIDER, MODEL_NAME, and the matching API key
```

### 3. Run

```bash
# Basic run
python main.py --topic "How does RAG improve search relevance?"

# Stream progress in terminal
python main.py --topic "..." --stream

# Set budget guard
python main.py --topic "..." --budget 2.0

# Resume a previous run
python main.py --resume --thread-id my-thread

# List supported providers / print config
python main.py --list-providers
python main.py --print-config
```

### 4. Web UI (optional)

```bash
python webui.py
# Open http://127.0.0.1:5000
```

---

## ⚙️ Configuration

All settings are managed through `.env` (see [.env.example](.env.example)).

### Required

| Variable | Description |
|----------|-------------|
| `MODEL_PROVIDER` | One of: `openai`, `anthropic`, `gemini`, `ollama`, `openrouter`, `deepseek`, `groq`, `together`, `mistral`, `opencode`, `azure`, `local`, `custom` |
| `MODEL_NAME` | Model identifier, e.g. `gpt-4o-mini`, `claude-3-haiku-20240307`, `gemini-1.5-flash`, `deepseek-chat`, `llama-3.1-70b` |
| Provider API key | e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENCODE_API_KEY` |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_TEMPERATURE` | `0.3` | Sampling temperature |
| `MODEL_MAX_TOKENS` | `4096` | Max output tokens per call |
| `OPENAI_BASE_URL` | *(none)* | Override base URL for OpenAI-compatible providers |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `MAX_REVISIONS` | `3` | Max writer ↔ critic loops |
| `APPROVE_THRESHOLD` | `85` | Min critic score for APPROVED |
| `CHECKPOINTER` | `memory` | `memory` or `sqlite` |
| `SQLITE_PATH` | `output/checkpoints.sqlite` | SQLite checkpoint file path |
| `THREAD_ID` | `default` | Default thread id for checkpointing |
| `TAVILY_API_KEY` | *(none)* | Tavily web search key (optional; DDG fallback works without it) |
| `LANGCHAIN_API_KEY` | *(none)* | LangSmith tracing key (optional) |
| `LANGCHAIN_PROJECT` | `research-validator` | LangSmith project name |
| `BUDGET` | *(none)* | Max USD per run; aborts if exceeded |

### Supported Providers

| Provider | Key Env Var | Base URL | Notes |
|----------|-------------|----------|-------|
| `openai` | `OPENAI_API_KEY` | `https://api.openai.com/v1` | Default |
| `anthropic` | `ANTHROPIC_API_KEY` | *(auto)* | Direct Anthropic SDK |
| `gemini` / `google` | `GEMINI_API_KEY` | *(auto)* | Google AI Studio |
| `ollama` | *(none)* | `http://localhost:11434` | Local LLMs |
| `openrouter` | `OPENROUTER_API_KEY` | *(auto)* | Meta/Llama models |
| `deepseek` | `DEEPSEEK_API_KEY` | *(auto)* | DeepSeek V3/R1 |
| `groq` | `GROQ_API_KEY` | *(auto)* | Fast inference |
| `together` | `TOGETHER_API_KEY` | *(auto)* | Open-source models |
| `mistral` | `MISTRAL_API_KEY` | *(auto)* | Mistral models |
| `opencode` | `OPENCODE_API_KEY` | *(auto)* | OpenCode Zen (free tier available) |
| `azure` | `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` | *(required)* | Azure OpenAI Service |
| `custom` | `CUSTOM_API_KEY` + `CUSTOM_BASE_URL` | *(required)* | Any OpenAI-compatible endpoint |

> **Tip:** Most third-party providers (DeepSeek, Groq, OpenRouter, Together, Mistral, OpenCode) are OpenAI-compatible and share the same `ChatOpenAI` class under the hood. Only set their dedicated API key env var — base URLs are applied automatically.

---

## 🧩 Architecture

```text
 ┌─────────┐   ┌─────────────┐   ┌─────────┐   ┌─────────┐
 │ Planner │→→│  Researcher │→→│  Writer │→→│  Critic │
 │ (plan)  │   │ (web search)│   │ (draft) │   │ (score) │
 └─────────┘   └─────────────┘   └─────────┘   └────┬────┘
                                                     │
                          ┌──────────────────────────┘
                          │ (if REVISE and revision_count < MAX_REVISIONS)
                          ▼
                      ┌─────────┐
                      │  Writer │◀──┘
                      └─────────┘
                          │
                          │ (if APPROVED or max revisions reached)
                          ▼
                      ┌─────────┐
                      │  OUTPUT │
                      │ (report)│
                      └─────────┘
```

Each agent node transforms `WorkflowState`:
- **Planner** produces `ResearchPlan` (outline + evidence strategy).
- **Researcher** performs live web search (`ddgs` fallback when Tavily unavailable).
- **Writer** composes the full report from plan + sources, produces `[1]` citations.
- **Critic** scores against 4 dimensions (completeness, factual accuracy, tone, citation quality) and returns `APPROVE` / `REVISE`.

---

## 📋 CLI Reference

| Flag | Description |
|------|-------------|
| `--topic TEXT` | Research topic (required) |
| `--provider NAME` | Override provider from env |
| `--model NAME` | Override model name from env |
| `--stream` | Stream per-step progress with spinner |
| `--max-revisions N` | Override MAX_REVISIONS |
| `--no-plan-cache` | Ignore cached research plans (force refresh) |
| `--thread-id TEXT` | Checkpoint thread id |
| `--resume` | Resume from last checkpoint for thread |
| `--print-config` | Print resolved model config and exit |
| `--budget FLOAT` | Max USD budget; aborts if exceeded |
| `--list-providers` | List supported providers |

---

## 🔄 Revision Loop Logic

The critic evaluates the draft against four quality dimensions:

| Dimension | Max Score | Criteria |
|-----------|-----------|----------|
| Completeness | 30 | All plan sections covered? |
| Factual Accuracy | 30 | Claims backed by sources? |
| Tone & Readability | 20 | Clear, professional tone? |
| Citation Quality | 20 | Proper `[n]` format, valid URLs? |

If `verdict == "REVISE"` and `revision_count < MAX_REVISIONS`, the graph routes back to **Writer**. Otherwise it terminates at `END`.

---

## 📄 Output Format

Reports are saved to `output/YYYY-MM-DD_<topic_slug>/` with:
- `report.md` — Final Markdown with inline `[n]` citations
- `sources.json` — All fetched URLs + snippets
- `state.json` — Full workflow state snapshot

---

## 🧪 Testing

```bash
python tests/test_graph.py
python tests/test_hitl.py
python tests/test_validation.py
python tests/test_cost.py
python tests/test_registry.py
```

Or run all:
```bash
python -m pytest tests/ -v
```

---

## 🔧 Troubleshooting

| Problem | Fix |
|---------|-----|
| `Unsupported provider: xxx` | Check `MODEL_PROVIDER` in `.env`. See provider table above. |
| `model parameter is required` | Set `MODEL_NAME` in `.env` (e.g. `MODEL_NAME=gpt-4o-mini`). |
| `Rate limit / 429 errors` | Check provider quota. Switch provider or wait for reset. |
| Agent loop stuck revising | Lower `APPROVE_THRESHOLD` or increase `MAX_REVISIONS`. |
| Broken citations | Ensure `TAVILY_API_KEY` or `DDGS_ENABLED=true` is set for live search. |
| `OPENCODE_API_KEY` not found | Set `OPENCODE_API_KEY=your-key` (or use a free-tier provider with no key). |

---

## 📁 Project Structure

```text
.
├── agents/
│   ├── common.py       # Shared types, last_usage tracking
│   ├── critic.py       # Quality scoring + verdict
│   ├── planner.py      # Research plan generation
│   ├── researcher.py   # Live web search + fetch
│   ├── writer.py       # Report writing + citation formatting
│   ├── state.py        # WorkflowState TypedDict
│   ├── schemas.py      # Pydantic models
│   ├── search.py       # Search orchestration (Tavily → DDG → CSV)
│   ├── searxng.py      # SearXNG search backend
│   └── registry.py     # YAML-backed agent/provider registry
├── graph.py            # LangGraph workflow definition
├── main.py             # CLI entrypoint
├── webui.py            # Flask web UI
├── output.py           # Output formatting & file writing
├── stream_events.py    # Stream consumption helpers
├── cli_ui.py           # Terminal spinner / color output
├── tools/
│   ├── citation_check.py
│   └── search_fallback.py
├── models/
│   └── llm.py          # Multi-provider LLM factory
├── evaluation/         # Evaluation harness
├── tests/              # Test suite
├── ROADMAP.md          # Development roadmap
├── PLAN.md             # Current sprint plan
├── requirements.txt
└── .env.example
```

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/amazing-thing`)
3. Commit changes (`git commit -am 'Add amazing thing'`)
4. Push and open a Pull Request

---

## 📜 License

MIT — see [LICENSE](LICENSE) for details.

---

**Built with ❤️ for researchers and AI enthusiasts.**
