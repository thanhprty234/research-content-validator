"""Persist workflow results (report.md + verdict.json) to the output/ directory."""

import json
from datetime import datetime
from pathlib import Path

from cli_ui import _safe_write

OUTPUT_DIR = Path("output")


def write_outputs(state: dict) -> Path:
    """Persist report.md and verdict.json to output/ and return the directory."""
    title = state.get("title") or "Report"
    slug = "".join(c for c in title if c.isalnum() or c in " _-").strip().replace(" ", "_") or "report"
    out_dir = OUTPUT_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{slug}"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "report.md").write_text(_render_markdown(state), encoding="utf-8")

    data = {
        "topic": state.get("topic"),
        "title": title,
        "summary": state.get("summary"),
        "key_claims": state.get("key_claims", []),
        "citations": state.get("citations", []),
        "plan": state.get("plan"),
        "notes": state.get("raw_findings", []),
        "critique": state.get("critique"),
        "revision_count": state.get("revision_count", 0),
    }
    (out_dir / "verdict.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _safe_write(f"\nSaved report  -> {out_dir / 'report.md'}\n")
    _safe_write(f"Saved verdict -> {out_dir / 'verdict.json'}\n")
    return out_dir


def _render_markdown(state: dict) -> str:
    critique = state.get("critique") or {}
    dims = critique.get("dimensions", {})

    lines = [
        f"# {state.get('title', 'Report')}",
        "",
        f"**Verdict:** {critique.get('verdict', 'UNKNOWN')}  "
        f"**Overall:** {critique.get('overall_score', 'N/A')}/100  "
        f"**Revisions:** {state.get('revision_count', 0)}",
        "",
        "## Summary",
        "",
        state.get("summary", ""),
        "",
        "## Report",
        "",
        state.get("body", ""),
        "",
        "## Dimension scores",
        "",
        "| Dimension | Score |",
        "|-----------|-------|",
    ]
    for name, d in dims.items():
        score = d.get("score", "N/A") if isinstance(d, dict) else "N/A"
        lines.append(f"| {name} | {score} |")

    lines += ["", "## Critique", "", critique.get("overall_notes", "")]
    lines += _bullet_section("Issues", critique.get("issues", []))
    lines += _bullet_section("Suggested revisions", critique.get("suggested_revisions", []))

    refs = sorted({c.get("source", "") for c in state.get("citations", []) if isinstance(c, dict) and c.get("source")})
    if refs:
        lines += ["", "## References", ""] + [f"- {r}" for r in refs]

    return "\n".join(lines)


def _bullet_section(title: str, items: list) -> list:
    if not items:
        return []
    return ["", f"### {title}", ""] + [f"- {i}" for i in items]
