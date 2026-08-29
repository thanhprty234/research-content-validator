# Research & Content Validator

> **AI-Powered Multi-Agent Research Pipeline** — Automate research, fact-check, and professional report generation with real-time web search, citation validation, and human-in-the-loop quality control.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![LangGraph](https://img.shields.io/badge/LangGraph-✅-blueviolet?style=flat-square)](https://langchain-ai.github.io/langgraph/)
[![Docker](https://img.shields.io/badge/Docker-Support-blue?style=flat-square&logo=docker)](#-docker)
[![Status](https://img.shields.io/badge/Status-Stable-success?style=flat-square)](#)

---

## ✨ What's Inside

```mermaid
graph LR
    A[🔍 Research Topic] --> B[🧠 Planner]
    B --> C[🌐 Researcher]
    C --> D[✍️ Writer]
    D --> E[🔬 Critic]
    E -->|APPROVE| F[📄 Final Report]
    E -->|REVISE| D
```

**One-liner:** Type a topic → Get a professionally sourced report in minutes.

---

## 🚀 Quick Start

### 1. Install

```bash
# Clone the repo
git clone https://github.com/thanhprty234/research-content-validator.git
cd research-content-validator

# Create virtual environment
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure

```bash
# Copy environment template
cp .env.example .env

# Edit .env — set your model provider and API key
nano .env  # or use your favorite editor
```

### 3. Run

```bash
# CLI mode (text output)
python main.py --topic "How does RAG improve search relevance?"

# Web UI mode (browser interface)
python webui.py
# → Open http://localhost:5000
```

---

## 🎯 Key Features

| Feature | Description | Status |
|---------|-------------|--------|
| 🤖 **Multi-Agent Pipeline** | Planner → Researcher → Writer → Critic loop | ✅ |
| 🔗 **Web Search** | Tavily + DuckDuckGo fallback (no API key needed) | ✅ |
| 💰 **Cost Tracking** | Real-time token usage & budget guard | ✅ |
| 📊 **Citation Quality** | Auto-validates sources & links | ✅ |
| 🧪 **Human-in-the-Loop** | Manual review checkpoints | ✅ |
| 💾 **Checkpoint/Resume** | Save & resume interrupted runs | ✅ |
| 🌐 **Web UI** | Real-time SSE streaming dashboard | ✅ |
| 🐳 **Docker Support** | One-command deployment | ✅ |

---

## 🏗️ Architecture

### Agent Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    RESEARCH PIPELINE                        │
├──────────┬──────────┬──────────┬──────────┬───────────────┤
│ PLANNER  │RESEARCHER│  WRITER  │  CRITIC  │   END         │
├──────────┼──────────┼──────────┼──────────┼───────────────┤
│ Generates │ Searches │ Drafts   │ Evaluates│ Outputs final │
│ research  │ web      │ report   │ quality  │ report        │
│ plan      │ results  │          │ scores   │               │
└──────────┴──────────┴──────────┴──────────┴───────────────┘
                              │
              ┌───────────────┴───────────────┐
              │  REVISE loop (max 3 revisions) │
              └───────────────────────────────┘
```

### Data Flow

```
Input Topic
    │
    ▼
┌─────────┐     ┌─────────────┐     ┌─────────┐
│ Planner │────▶│ Researcher  │────▶│ Writer  │
│ (plan)  │     │ (web search)│     │ (draft) │
└─────────┘     └─────────────┘     └────┬────┘
                                         │
                                         ▼
                                    ┌─────────┐
                                    │  Critic │
                                    │ (score) │
                                    └────┬────┘
                                         │
                          ┌──────────────┼──────────────┐
                          │              │              │
                       APPROVE         REVISE        (loop back)
                          │              │
                          ▼              │
                     Final Report        │
                                          │
                                    ┌─────────┐
                                    │  Writer │ (revision)
                                    └─────────┘
```

---

## ⚙️ Configuration

### Environment Variables

| Variable | Example | Description |
|----------|---------|-------------|
| `MODEL_PROVIDER` | `custom` | LLM provider |
| `MODEL_NAME` | `agnes-2.5-flash` | Model identifier |
| `CUSTOM_API_KEY` | `sk-***` | API key for custom provider |
| `CUSTOM_BASE_URL` | `https://api.example.com/v1` | API endpoint |
| `TAVILY_API_KEY` | `tvly-***` | Tavily search (optional) |
| `LANGCHAIN_TRACING_V2` | `true` | Enable LangSmith tracing |
| `BUDGET` | `5.0` | Max spend per run (USD) |

### Supported Providers

| Provider | Key Required | Base URL |
|----------|--------------|----------|
| `openai` | `OPENAI_API_KEY` | Auto |
| `anthropic` | `ANTHROPIC_API_KEY` | Auto |
| `gemini` | `GEMINI_API_KEY` | Auto |
| `ollama` | None | `http://localhost:11434` |
| `openrouter` | `OPENROUTER_API_KEY` | Auto |
| `deepseek` | `DEEPSEEK_API_KEY` | Auto |
| `groq` | `GROQ_API_KEY` | Auto |
| `together` | `TOGETHER_API_KEY` | Auto |
| `mistral` | `MISTRAL_API_KEY` | Auto |
| `opencode` | `OPENCODE_API_KEY` | Auto |
| `azure` | `AZURE_*` | Required |
| `custom` | `CUSTOM_*` | Required |

---

## 📋 CLI Reference

```bash
python main.py [OPTIONS]

--topic TEXT              Research topic (required)
--provider NAME           Override provider
--model NAME              Override model name
--stream                  Stream progress to terminal
--max-revisions N         Max revision attempts (default: 3)
--no-plan-cache           Disable plan caching
--thread-id TEXT          Checkpoint thread ID
--resume                  Resume from checkpoint
--budget FLOAT            Max cost in USD
--list-providers          Show available providers
--print-config            Print resolved config
```

**Examples:**

```bash
# Basic research
python main.py --topic "Impact of quantum computing on cryptography"

# With budget limit
python main.py --topic "AI regulation in 2024" --budget 2.0

# Resume interrupted run
python main.py --topic "Previous topic" --thread-id abc123 --resume

# Use specific model
python main.py --topic "Topic" --provider openai --model gpt-4o-mini
```

---

## 🌐 Web UI

Start the web interface:

```bash
python webui.py
# → Open http://localhost:5000
```

**Features:**
- Real-time SSE progress streaming
- Provider & model selection dropdown
- Manual input for topic & parameters
- Live output panel with markdown rendering
- Pause/Resume workflow control
- Cost tracking dashboard

---

## 🐳 Docker

### Quick Start

```bash
# Build and run
docker-compose up -d

# Access UI at http://localhost:5000
# SearXNG search at http://localhost:8080
```

### Docker Compose Services

| Service | Port | Purpose |
|---------|------|---------|
| `app` | 5000 | Main web interface |
| `searxng` | 8080 | Search engine (optional) |

### Environment File

```bash
# Required for Docker
cp .env.example .env
# Edit .env with your API keys

docker-compose up -d
```

---

## 📄 Output Format

Reports are saved to `output/YYYY-MM-DD_<topic_slug>/`:

```
output/
└── 2024-08-27_how-rag-improves-search/
    ├── report.md           # Final report with citations
    ├── sources.json        # All fetched URLs & snippets
    └── state.json          # Full workflow snapshot
```

**Report structure:**
- Professional Markdown formatting
- Inline `[n]` citations linked to sources
- Structured sections from research plan
- Cost summary at the end

---

## 🧪 Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test suite
python tests/test_graph.py
python tests/test_hitl.py
python tests/test_validation.py
```

---

## 📚 Prompt Templates

Located in `prompts/` directory:

| File | Purpose |
|------|---------|
| `planner.txt` | Research plan generation |
| `researcher.txt` | Web search & fact gathering |
| `writer.txt` | Draft composition |
| `critic.txt` | Quality evaluation |
| `image_gen.txt` | Visual content generation |

---

## 🎨 Image Generation Prompts

For creating visual assets:

### Repository Banner (Hero Image)

```
prompt: "A futuristic AI research assistant analyzing documents,
        surrounded by floating data visualizations and search results,
        clean tech aesthetic, blue and purple gradient, 
        minimalist style, professional presentation"
```

### Architecture Diagram

```
prompt: "Flowchart showing AI agent pipeline: 
        Planner → Researcher → Writer → Critic, 
        circular feedback loop, modern tech illustration,
        clean lines, flat design, light background"
```

### Feature Icons

```
prompt: "Set of 4 minimalist icons: 
        1) Brain with search magnifying glass, 
        2) Document with citation marks, 
        3) Dollar sign with chart, 
        4) Human hand approving checkmark, 
        consistent style, blue theme, white background"
```

---

## 🔒 Security

- API keys stored in `.env` (never commit)
- No hardcoded credentials
- Cost tracking prevents bill shock
- Checkpoint saves state safely

---

## 📈 Roadmap

| Phase | Features | Status |
|-------|----------|--------|
| 0 | Core pipeline, multi-provider | ✅ Done |
| 1 | Cost tracking, budget guard | ✅ Done |
| 2 | Parallel research, citation quality | 🔄 In Progress |
| 3 | Human review, scheduling | 📋 Planned |
| 4 | Plugin system, extensibility | 📋 Planned |
| 5 | Production deployment | 📋 Planned |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

MIT License — See [LICENSE](LICENSE) for details.

---

## 🙏 Credits

- [LangGraph](https://langchain-ai.github.io/langgraph/) — Agent orchestration
- [DuckDuckGo](https://duckduckgo.com) — Free search fallback
- [SearXNG](https://searxng.github.io/) — Self-hosted search engine
- All LLM provider APIs

---

**Made with ❤️ by [thanhprty234](https://github.com/thanhprty234)**
