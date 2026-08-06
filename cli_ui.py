"""Terminal presentation helpers for the CLI (safe unicode, spinner, verdict)."""

import os
import time

try:
    import rich  # noqa: F401
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False


def _safe_write(text: str):
    """Write to stdout, replacing any character the terminal cannot encode."""
    stream = os.sys.stdout
    try:
        stream.write(text)
    except (UnicodeEncodeError, ValueError):
        enc = stream.encoding or "utf-8"
        stream.write(text.encode(enc, errors="replace").decode(enc))
    stream.flush()


def _log_step(step: str, state: dict):
    from stream_events import step_message

    msg = step_message(step, state)
    _safe_write(f"\u25cf {step.upper()}  {msg}\n")


def print_verdict(state: dict):
    critique = state.get("critique") or {}
    _safe_write("\n" + "=" * 50 + "\n")
    _safe_write(f"VERDICT: {critique.get('verdict', 'UNKNOWN')}  ({critique.get('overall_score', 'N/A')}/100)\n")
    for issue in critique.get("issues", []):
        _safe_write(f"  - {issue}\n")

    best = state.get("best_report") or {}
    if critique.get("verdict") != "APPROVED" and best and (best.get("score") or 0) > (critique.get("overall_score") or 0):
        _safe_write(
            f"[held] Revisions ran out below threshold; best round {best.get('revision')} "
            f"({best.get('score')}/100) will be saved.\n"
        )

    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(title="Dimension scores")
        table.add_column("Dimension")
        table.add_column("Score")
        for name, d in (critique.get("dimensions") or {}).items():
            score = d.get("score", "N/A") if isinstance(d, dict) else "N/A"
            table.add_row(name, str(score))
        Console().print(table)
    except ImportError:
        pass


class _Spinner:
    """Simple terminal spinner (falls back to no-op when rich is unavailable)."""
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    SAFE_FRAMES = "|/-\\"

    def __init__(self):
        self._thread = None
        self._stop = False
        self._rich = _HAS_RICH
        self._label = ""
        self._frames = self.SAFE_FRAMES
        self.running = False
        try:
            os.sys.stdout.write(self.FRAMES[0])
            os.sys.stdout.flush()
            self._frames = self.FRAMES
        except (UnicodeEncodeError, ValueError):
            pass

    def set_label(self, label: str):
        self._label = label

    def start(self, label: str):
        if not self._rich:
            print(label, end="\r", flush=True)
            return
        import threading

        self._stop = False
        self._label = label
        self.running = True

        def spin():
            i = 0
            while not self._stop:
                try:
                    _safe_write(f"\r{self._frames[i % len(self._frames)]} {self._label}")
                except Exception:
                    return
                i += 1
                time.sleep(0.08)

        self._thread = threading.Thread(target=spin, daemon=True)
        self._thread.start()

    def finish(self):
        self._stop = True
        self.running = False
        if self._thread:
            self._thread.join(timeout=0.2)
            self._thread = None
        if self._rich:
            _safe_write("\r\x1b[2K")  # clear the spinner line
            os.sys.stdout.flush()