"""Shared fake LLM for offline tests (no API key needed)."""

from agents.schemas import ResearchPlan, Note, Report, Critique, Citation


class FakeLLM:
    def __init__(self, approve_after=2):
        self.approve_after = approve_after
        self.critiques = 0

    def with_structured_output(self, schema):
        return LangChainish(schema, self)

    def bind(self, **kwargs):
        return self


class LangChainish:
    """Stand-in for the prompt | llm chain: stores schema, produces on invoke."""

    def __init__(self, schema, llm):
        self.schema = schema
        self.llm = llm

    def __or__(self, other):
        return self  # PromptTemplate | this -> keep this as the runner

    def __call__(self, inputs):
        return self.invoke(inputs)

    def bind(self, **kwargs):
        return self

    def invoke(self, inputs):
        schema = self.schema
        if schema is ResearchPlan:
            return schema(
                research_questions=["q1: water", "q2: sun"],
                outline=["Introduction", "Body", "Conclusion"],
            )
        if schema is Note:
            return schema(
                question="q",
                findings="Water evaporates, condenses and precipitates, driven by the sun.",
                sources=["https://example.com/water"],
            )
        if schema is Report:
            return schema(
                title="Water Cycle Report",
                summary="The water cycle is driven by solar energy.",
                body=(
                    "Evaporation, condensation and precipitation are the main stages. "
                    "A balanced diet includes protein and vitamins and water."
                ),
                key_claims=["The sun drives the water cycle"],
                citations=[Citation(source="https://example.com/water", claim_supported="Water cycle stages")],
            )
        if schema is Critique:
            self.llm.critiques += 1
            if self.llm.critiques >= self.llm.approve_after:
                return schema(
                    overall_score=90, overall_notes="Good", verdict="APPROVED",
                    issues=[], suggested_revisions=[], dimensions={},
                )
            return schema(
                overall_score=55, overall_notes="Needs work", verdict="REVISE",
                issues=["add citations"], suggested_revisions=["cite sources"], dimensions={},
            )
        raise AssertionError(f"unexpected schema {schema}")
