"""Pydantic structured-output schemas shared across agents."""

from pydantic import BaseModel, Field
from typing import List


class ResearchPlan(BaseModel):
    research_questions: List[str] = Field(default_factory=list)
    outline: List[str] = Field(default_factory=list)


class Note(BaseModel):
    question: str = ""
    findings: str = ""
    sources: List[str] = Field(default_factory=list)


class Citation(BaseModel):
    source: str = ""
    claim_supported: str = ""


class Report(BaseModel):
    title: str = ""
    summary: str = ""
    body: str = ""
    key_claims: List[str] = Field(default_factory=list)
    citations: List[Citation] = Field(default_factory=list)


class DimensionScore(BaseModel):
    score: int = 0
    notes: str = ""


class Critique(BaseModel):
    dimensions: dict[str, DimensionScore] = Field(default_factory=dict)
    overall_score: float = 0.0
    overall_notes: str = ""
    verdict: str = "REVISE"
    issues: List[str] = Field(default_factory=list)
    suggested_revisions: List[str] = Field(default_factory=list)