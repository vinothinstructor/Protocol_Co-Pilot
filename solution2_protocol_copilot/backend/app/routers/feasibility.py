"""
Feasibility Simulator endpoint.
POST /protocols/{id}/feasibility → FeasibilityProjection
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_session
from app.db.models import ClauseHistory, ProtocolVersion
from app.schemas import FeasibilityProjection, FeasibilityRequest
from app.utils.llm_mode_dependency import resolve_llm_mode
from app.config import LLMMode
from app.utils.scoring import compute_overall_risk
from app.agents.feasibility_simulator import project_feasibility

router = APIRouter()


@router.post("/protocols/{protocol_id}/feasibility", response_model=FeasibilityProjection)
async def get_feasibility(
    protocol_id: str,
    body: FeasibilityRequest = FeasibilityRequest(),  # noqa: B008
    session: AsyncSession = Depends(get_session),
    mode: LLMMode = Depends(resolve_llm_mode),
):
    _ = body  # include_baseline reserved for future use

    # Load latest protocol version for version string and document
    row = (
        await session.execute(
            select(ProtocolVersion)
            .where(ProtocolVersion.protocol_id == protocol_id)
            .order_by(ProtocolVersion.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(404, f"Protocol {protocol_id} not found")

    # Get all accepted fixes so the agent can determine which scripted state we're in
    accepted_rows = (
        await session.execute(
            select(ClauseHistory).where(
                ClauseHistory.protocol_id == protocol_id,
                ClauseHistory.action == "accept",
            )
        )
    ).scalars().all()
    accepted_block_ids: set[str] = {r.clause_id for r in accepted_rows}

    # Compute current overall risk from accepted fixes
    from app.routers.fixes import _compute_severity_with_fixes
    accepted_texts = {r.clause_id: r.new_text for r in accepted_rows}
    counts = _compute_severity_with_fixes(accepted_texts)
    overall_risk = compute_overall_risk(counts.high, counts.medium, counts.low)

    try:
        return await project_feasibility(
            protocol_id=protocol_id,
            version=row.version,
            overall_risk=overall_risk,
            accepted_block_ids=accepted_block_ids,
            mode=mode,
            protocol_doc=row.document,
        )
    except RuntimeError:
        # LiveLLMClient raises RuntimeError when Azure credentials are missing.
        # Return a 503 with a concise, user-readable message.
        raise HTTPException(
            status_code=503,
            detail="Live mode unavailable: Azure credentials not configured on this machine. Use FAKE or CACHED mode instead.",
        )
