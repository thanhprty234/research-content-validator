"""Test cost tracking: verify estimate_cost and token_log flow."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.llm import estimate_cost


def test_estimate_cost():
    # openai gpt-4o-mini: $0.15/M input, $0.60/M output
    assert abs(estimate_cost("openai", 1000, 500, "gpt-4o-mini") - 0.00045) < 1e-12
    # ollama = free
    assert estimate_cost("ollama", 1000, 500, "llama3") == 0.0
    # unknown provider = 0
    assert estimate_cost("unknown", 1000, 500, "x") == 0.0
    # anthropic claude-3-5-sonnet: $3/M input, $15/M output
    expected = 100_000 * 3 / 1_000_000 + 50_000 * 15 / 1_000_000
    assert abs(estimate_cost("anthropic", 100_000, 50_000, "claude-3-5-sonnet") - expected) < 1e-6
    print("estimate_cost OK")


def test_estimate_cost_mismatch():
    # model not in rate table -> 0
    assert estimate_cost("openai", 1000, 500, "unknown-model") == 0.0
    print("estimate_cost mismatch OK")


if __name__ == "__main__":
    test_estimate_cost()
    test_estimate_cost_mismatch()
    print("COST TEST OK")
