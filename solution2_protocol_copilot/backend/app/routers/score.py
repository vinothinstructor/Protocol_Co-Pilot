from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_session
from app.db.models import ProtocolVersion
from app.schemas import ScoreRequest, ScoreResponse, ClauseRiskResult, SeverityCounts
from app.agents.amendment_risk import run_amendment_risk
from app.utils.scoring import compute_overall_risk
from app.utils.llm_mode_dependency import resolve_llm_mode
from app.config import LLMMode

router = APIRouter()

# Block IDs in demo_clause_scores.json — used for "score all" in fake mode.
# Order matters for display (high → medium → low).
_DEMO_SCORABLE_BLOCKS = [
    "blk_4_4", "blk_4_3", "blk_6_2",          # HIGH
    "blk_5_6", "blk_6_3", "blk_5_3", "blk_3_4", "blk_5_5",  # MEDIUM
    "blk_4_1", "blk_4_2", "blk_5_1", "blk_5_2", "blk_5_4",  # LOW
    "blk_6_1", "blk_3_3", "blk_7_2", "blk_8_1", "blk_8_3",
    "blk_9_1", "blk_9_3",
]


def _find_block(doc: dict, block_id: str) -> dict | None:
    """Locate a block_id in the nested protocol document."""
    for section in doc.get("sections", []):
        for block in section.get("blocks", []):
            if block["block_id"] == block_id:
                return {**block, "section": section["heading"]}
    return None


def _normalize_clause_text(s: str) -> str:
    """
    Normalize for byte-equivalence matching: strip + collapse internal whitespace
    to single spaces. Case and punctuation are NOT normalized — capitalization or
    punctuation changes are real edits that should NOT match the original.
    """
    return " ".join(s.split())


async def score_protocol_internal(
    protocol_id: str,
    block_ids: list[str] | None,
    session: AsyncSession,
    clause_texts: dict[str, str] | None = None,
    mode_override: LLMMode | None = None,
) -> dict:
    """
    Shared scoring logic. Returns per-clause results for the REQUESTED blocks,
    plus overall_risk + severity_counts computed across the FULL aggregate
    (all 20 demo blocks + any user-added clauses from clause_texts).

    When clause_texts contains a block_id, the live text is used (heuristic in
    fake mode) instead of looking up the persisted protocol document. This is
    Phase 5's mechanism for scoring new typed clauses (gen_…) and un-persisted
    edits to existing clauses.
    """
    row = (
        await session.execute(
            select(ProtocolVersion)
            .where(ProtocolVersion.protocol_id == protocol_id)
            .order_by(ProtocolVersion.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Protocol '{protocol_id}' not found")

    doc: dict = row.document
    ta: str = doc.get("therapeutic_area", "diabetes")
    countries: list[str] = doc.get("target_countries", ["US", "DE", "FR", "JP", "BR", "CN"])
    clause_texts = clause_texts or {}

    # What to return per-clause: the requested subset (or all demo blocks if none specified)
    if block_ids is None:
        target_ids: list[str] = list(_DEMO_SCORABLE_BLOCKS)
    else:
        target_ids = list(block_ids)
    # Always include user-added/edited clauses from clause_texts in the response
    for extra_id in clause_texts:
        if extra_id not in target_ids:
            target_ids.append(extra_id)

    # Full aggregate set: demo blocks + any user-added clauses
    aggregate_ids = list(dict.fromkeys(_DEMO_SCORABLE_BLOCKS + list(clause_texts.keys())))

    async def _score(bid: str) -> ClauseRiskResult | None:
        force_heuristic = False
        blk = _find_block(doc, bid)

        if bid in clause_texts:
            live_text = clause_texts[bid]
            original_text = blk["text"] if blk else None

            # Revert detection: if the live text byte-matches the seeded original
            # (after whitespace normalization), skip the heuristic and use the
            # scripted score. This way "edit BMI → revert BMI" returns to the
            # original HIGH score instead of staying on a heuristic MEDIUM.
            if (
                original_text is not None
                and _normalize_clause_text(live_text) == _normalize_clause_text(original_text)
            ):
                text = original_text
                section = blk.get("section", "")
                # force_heuristic stays False → scripted lookup applies
            else:
                text = live_text
                section = blk.get("section", "") if blk else ""
                force_heuristic = True
        else:
            if blk is None:
                return None
            text = blk["text"]
            section = blk.get("section", "")

        return await run_amendment_risk(
            block_id=bid, text=text, section=section,
            therapeutic_area=ta, target_countries=countries, session=session,
            force_heuristic=force_heuristic,
            mode_override=mode_override,
        )

    # Score the full aggregate so overall_risk is correct
    aggregate_scores: dict[str, ClauseRiskResult] = {}
    for bid in aggregate_ids:
        r = await _score(bid)
        if r is not None:
            aggregate_scores[bid] = r

    n_high = sum(1 for r in aggregate_scores.values() if r.risk_level == "high")
    n_medium = sum(1 for r in aggregate_scores.values() if r.risk_level == "medium")
    n_low = sum(1 for r in aggregate_scores.values() if r.risk_level == "low")
    overall = compute_overall_risk(n_high, n_medium, n_low)

    # Response carries only the requested clauses (target_ids order preserved)
    response_results = [aggregate_scores[bid] for bid in target_ids if bid in aggregate_scores]

    return {
        "clauses": response_results,
        "overall_risk": overall,
        "severity_counts": SeverityCounts(high=n_high, medium=n_medium, low=n_low),
    }


@router.post("/protocols/{protocol_id}/score", response_model=ScoreResponse)
async def score_protocol(
    protocol_id: str,
    body: ScoreRequest = ScoreRequest(),
    session: AsyncSession = Depends(get_session),
    mode: LLMMode = Depends(resolve_llm_mode),
):
    result = await score_protocol_internal(
        protocol_id, body.block_ids, session,
        clause_texts=body.clause_texts,
        mode_override=mode,
    )
    return ScoreResponse(**result)
