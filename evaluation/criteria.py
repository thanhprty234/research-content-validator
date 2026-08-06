"""Evaluation: measure report quality against a criteria rubric and sample tests.

Run with:  python -m evaluation.evaluate
"""


CRITERIA = [
    {
        "name": "factual_accuracy",
        "question": "Do the claims match known facts without exaggeration or error?",
        "weight": 0.30,
    },
    {
        "name": "citation_support",
        "question": "Are claims backed by cited sources?",
        "weight": 0.25,
    },
    {
        "name": "coherence",
        "question": "Is the structure logical, complete, and readable?",
        "weight": 0.20,
    },
    {
        "name": "objectivity_bias",
        "question": "Is the tone balanced and free of one-sided bias?",
        "weight": 0.15,
    },
    {
        "name": "completeness",
        "question": "Does the report fully address the research plan outline?",
        "weight": 0.10,
    },
]


def weighted_score(dim_scores: dict) -> float:
    """Aggregate per-dimension 0-100 scores into a weighted overall score."""
    total = 0.0
    for c in CRITERIA:
        if c["name"] in dim_scores:
            total += dim_scores[c["name"]] * c["weight"]
    return round(total, 1)


SAMPLE_TESTS = [
    {
        "id": "t1_water_cycle",
        "topic": "Water cycle basics",
        "outline": ["Process", "Drivers"],
        "expect_terms": ["evaporation", "condensation", "sun"],
    },
    {
        "id": "t2_healthy_diet",
        "topic": "Components of a balanced diet",
        "outline": ["Macronutrients", "Micronutrients", "Hydration"],
        "expect_terms": ["protein", "vitamin", "water"],
    },
]
