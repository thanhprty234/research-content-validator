"""Evaluation runner: runs the pipeline over sample topics and scores output vs criteria."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.llm import get_model, model_config_from_env
from graph import run
from evaluation.criteria import CRITERIA, SAMPLE_TESTS, weighted_score


def score_report(state: dict, test: dict) -> dict:
    """Heuristic evaluation of a produced report against a test spec."""
    body = state.get("body", "") or ""
    critique = state.get("critique") or {}
    dims = critique.get("dimensions", {})

    # completeness: do expected terms appear?
    present = [t for t in test["expect_terms"] if t.lower() in body.lower()]
    completeness = round(100 * len(present) / max(1, len(test["expect_terms"])), 1)

    dim_scores = {
        # reuse LLM critic scores when available
        "factual_accuracy": dims.get("factual_accuracy", {}).get("score", 0),
        "citation_support": dims.get("citation_support", {}).get("score", 0),
        "coherence": dims.get("coherence", {}).get("score", 0),
        "objectivity_bias": dims.get("objectivity_bias", {}).get("score", 0),
        "completeness": completeness,
    }
    overall = weighted_score(dim_scores)
    return {
        "test_id": test["id"],
        "overall": overall,
        "dimensions": dim_scores,
        "terms_found": present,
        "terms_missing": [t for t in test["expect_terms"] if t.lower() not in body.lower()],
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate report quality on sample tests")
    parser.add_argument("--tests", default="all", help="test ids or 'all'")
    parser.add_argument("--json", action="store_true", help="Print JSON results")
    args = parser.parse_args()

    tests = SAMPLE_TESTS
    if args.tests != "all":
        wanted = set(args.tests.split(","))
        tests = [t for t in SAMPLE_TESTS if t["id"] in wanted]

    cfg = model_config_from_env()
    llm = get_model(cfg)
    results = []
    for test in tests:
        print(f"\n=== Evaluating '{test['id']}' ===")
        state, _ = run(test["topic"], thread_id=f"eval_{test['id']}", llm=llm)
        r = score_report(state, test)
        results.append(r)
        print(f"  overall: {r['overall']}/100  terms: {r['terms_found']}")
        print(f"  missing terms: {r['terms_missing']}")

    if args.json:
        import json
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        avg = sum(r["overall"] for r in results) / max(1, len(results))
        print(f"\nAverage overall score: {avg:.1f}/100")


if __name__ == "__main__":
    main()
