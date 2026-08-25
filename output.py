"""Persist workflow results (report.md + verdict.json + cost_summary.json) to the output/ directory."""

import json
import os
from datetime import datetime
from pathlib import Path

from cli_ui import _safe_write

OUTPUT_DIR = Path("output")


def _best_or_current(state: dict) -> tuple:
    """Return (report, critique) preferring the best report when the last round
    was not approved (revisions may have run out below the threshold)."""
    critique = state.get("critique") or {}
    if critique.get("verdict") == "APPROVED":
        return state, critique
    best = state.get("best_report") or {}
    if best and (best.get("score") or 0) > (critique.get("overall_score") or 0):
        return best, (state.get("best_critique") or critique)
    return state, critique


def write_outputs(state: dict) -> Path:
    """Persist report.md and verdict.json to output/ and return the directory."""
    report, critique = _best_or_current(state)
    title = report.get("title") or "Report"
    slug = "".join(c for c in title if c.isalnum() or c in " _-").strip().replace(" ", "_") or "report"
    out_dir = OUTPUT_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{slug}"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "report.md").write_text(_render_markdown(state, report, critique), encoding="utf-8")

    data = {
        "topic": state.get("topic"),
        "title": report.get("title") or title,
        "summary": report.get("summary"),
        "key_claims": report.get("key_claims", []),
        "citations": report.get("citations", []),
        "plan": state.get("plan"),
        "notes": state.get("raw_findings", []),
        "critique": critique,
        "revision_count": state.get("revision_count", 0),
        "used_best": report is not state,
        "max_revisions": int(os.getenv("MAX_REVISIONS", "3")),
    }
    (out_dir / "verdict.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ponytail: cost summary — skip when token_log is empty (local/offline runs)
    token_log = state.get("token_log") or []
    if token_log:
        cost_summary = {
            "total_cost_usd": round(state.get("total_cost_usd", 0.0), 6),
            "total_tokens": sum(
                e.get("tokens", {}).get("input", 0) + e.get("tokens", {}).get("output", 0)
                for e in token_log
            ),
            "per_step": token_log,
        }
        (out_dir / "cost_summary.json").write_text(
            json.dumps(cost_summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _safe_write(f"Saved cost summary -> {out_dir / 'cost_summary.json'}\n")

    _safe_write(f"\nSaved report  -> {out_dir / 'report.md'}\n")
    _safe_write(f"Saved verdict -> {out_dir / 'verdict.json'}\n")
    return out_dir


def _render_markdown(state: dict, report: dict = None, critique: dict = None) -> str:
    report = report or state
    critique = critique or state.get("critique") or {}
    dims = critique.get("dimensions", {})

    lines = [
        f"# {report.get('title', 'Report')}",
        "",
        f"**Verdict:** {critique.get('verdict', 'UNKNOWN')}  "
        f"**Overall:** {critique.get('overall_score', 'N/A')}/100  "
        f"**Revisions:** {state.get('revision_count', 0)}",
        "",
        "## Summary",
        "",
        report.get("summary", ""),
        "",
        "## Report",
        "",
        report.get("body", ""),
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

    refs = sorted({c.get("source", "") for c in report.get("citations", []) if isinstance(c, dict) and c.get("source")})
    if refs:
        lines += ["", "## References", ""] + [f"- {r}" for r in refs]

    return "\n".join(lines)


def _bullet_section(title: str, items: list) -> list:
    if not items:
        return []
    return ["", f"### {title}", ""] + [f"- {i}" for i in items]
