from __future__ import annotations
import json
import re
from datetime import datetime
from pydantic import BaseModel
from typing import Any


class HealthResponse(BaseModel):
    status: str
    llm_mode: str


class ProtocolResponse(BaseModel):
    protocol_id: str
    version: str
    document: dict[str, Any]


# ── Scoring schemas ────────────────────────────────────────────────────────────

class FactorScore(BaseModel):
    score: int
    reasoning: str


class PatternMatch(BaseModel):
    pattern_id: str
    match_percent: int
    description: str


class ClauseRiskResult(BaseModel):
    block_id: str
    score: int
    risk_level: str      # low | medium | high
    factors: dict[str, FactorScore]
    top_pattern_match: PatternMatch | None
    summary: str


class ScoreRequest(BaseModel):
    block_ids: list[str] | None = None
    # Live edit override: block_id → current text. When present, the scoring
    # agent uses this text instead of the persisted protocol document. Used by
    # Phase 5's real-time edit pipeline for newly-typed clauses (gen_…) and
    # un-persisted edits to existing demo blocks.
    clause_texts: dict[str, str] | None = None


class SeverityCounts(BaseModel):
    high: int
    medium: int
    low: int


class ScoreResponse(BaseModel):
    clauses: list[ClauseRiskResult]
    overall_risk: int
    severity_counts: SeverityCounts


# ── Fix schemas ────────────────────────────────────────────────────────────────

class FixCandidate(BaseModel):
    candidate_id: str
    label: str
    new_text: str
    delta_overall: int        # negative = risk reduction
    delta_clause_score: int
    new_clause_level: str     # what the clause becomes after accept
    rationale: str


class SuggestFixRequest(BaseModel):
    # Phase 5: live clause text for pattern-matching when block_id has no scripted entry
    # (e.g., gen_ ids from newly-typed clauses).
    clause_text: str | None = None


class SuggestFixResponse(BaseModel):
    block_id: str
    original: str
    candidates: list[FixCandidate]


class AcceptFixRequest(BaseModel):
    candidate_id: str


class AcceptFixResponse(BaseModel):
    block_id: str
    new_clause_text: str
    new_clause_score: ClauseRiskResult
    new_overall_risk: int
    new_severity_counts: SeverityCounts
    version: str


class DismissRequest(BaseModel):
    reason: str = ""


class DismissResponse(BaseModel):
    block_id: str
    action: str
    message: str


# ── Amendment package schemas ─────────────────────────────────────────────────

class AmendmentChange(BaseModel):
    clause_id: str
    section: str              # e.g., "Section 4 — Inclusion Criteria"
    original_text: str
    new_text: str
    risk_before: int
    risk_after: int
    rationale: str
    label: str                # candidate label (e.g., "Allow stable metformin")
    accepted_at: datetime


class AmendmentPackageResponse(BaseModel):
    protocol_id: str
    protocol_title: str
    from_version: str         # e.g., "v3.2"
    to_version: str           # e.g., "v3.3"
    overall_risk_before: int  # 73
    overall_risk_after: int   # 19
    changes: list[AmendmentChange]
    generated_at: datetime
    markdown: str             # rendered amendment document


# ── Gap Detection schemas ─────────────────────────────────────────────────────

class ProtocolGap(BaseModel):
    gap_id: str
    name: str
    category: str
    rationale: str
    suggested_section: str
    suggested_section_id: str
    draft_topic: str
    regulatory_reference: str | None
    severity: str  # "recommended" | "standard" | "optional"


class GapDetectionRequest(BaseModel):
    # Optional override of the persisted document's per-section text. When the
    # frontend has live (unsaved) editor edits, it sends the current section
    # texts here so gap detection reflects what the user actually sees, not the
    # seeded DB document. Keyed by section_id (e.g. "sec_4").
    section_texts: dict[str, str] | None = None


class GapDetectionResponse(BaseModel):
    protocol_id: str
    checklist_version: str
    gaps_detected: list[ProtocolGap]
    detected_at: datetime


# ── Drafting Agent schemas ────────────────────────────────────────────────────

class DraftClauseRequest(BaseModel):
    topic: str
    section_id: str | None = None
    therapeutic_area: str = "diabetes"


class DraftClauseResponse(BaseModel):
    topic: str
    clause_text: str
    generated_at: datetime
    suggested_section: str | None = None
    rationale: str | None = None


# ── Feasibility Simulator schemas ─────────────────────────────────────────────

class FeasibilityMetric(BaseModel):
    name: str                # human-readable key, e.g. "screen_failure_rate"
    current_value: float     # projection for current protocol state
    baseline_value: float    # v3.2 baseline projection
    unit: str                # "%", "weeks", "sites", "$M"
    delta: float             # current_value - baseline_value (signed)
    delta_label: str         # e.g. "-32 pts" or "+$1.4M saved"


class FeasibilityProjection(BaseModel):
    protocol_id: str
    protocol_version: str
    overall_risk: int
    overall_risk_baseline: int
    metrics: list[FeasibilityMetric]
    rationale: str
    generated_at: datetime

    @property
    def metrics_by_name(self) -> dict[str, float]:
        return {m.name: m.current_value for m in self.metrics}


class FeasibilityRequest(BaseModel):
    include_baseline: bool = True  # reserved for future use; always returns baseline


# ── LLM response parsers ───────────────────────────────────────────────────────

def _strip_fences(raw: str) -> str:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    return re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)


def parse_llm_score_response(raw: str) -> dict | None:
    try:
        data = json.loads(_strip_fences(raw))
        return data if "factors" in data else None
    except (json.JSONDecodeError, ValueError):
        return None


def parse_llm_fix_response(raw: str) -> dict | None:
    try:
        data = json.loads(_strip_fences(raw))
        return data if "candidates" in data else None
    except (json.JSONDecodeError, ValueError):
        return None
