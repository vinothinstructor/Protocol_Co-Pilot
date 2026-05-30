"""
Drafting Agent endpoints.
POST /protocols/{id}/draft-clause  → DraftClauseResponse
POST /protocols/{id}/detect-gaps   → GapDetectionResponse
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.schemas import DraftClauseRequest, DraftClauseResponse, GapDetectionResponse, GapDetectionRequest
from app.utils.llm_mode_dependency import resolve_llm_mode
from app.config import LLMMode
from app.agents.drafting import draft_clause, detect_gaps
from app.db.session import get_session
from app.db.models import ProtocolVersion

router = APIRouter()


@router.post("/protocols/{protocol_id}/draft-clause", response_model=DraftClauseResponse)
async def post_draft_clause(
    protocol_id: str,
    body: DraftClauseRequest,
    mode: LLMMode = Depends(resolve_llm_mode),
):
    _ = protocol_id  # future use: protocol-specific style guides

    section = body.section_id or "appropriate protocol section"

    try:
        return await draft_clause(
            topic=body.topic,
            therapeutic_area=body.therapeutic_area,
            section=section,
            mode=mode,
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "missing Azure config" in msg or "LiveLLMClient" in msg:
            raise HTTPException(
                status_code=503,
                detail="Live mode unavailable: missing Azure config on this machine. Use FAKE or CACHED mode instead.",
            )
        raise HTTPException(status_code=500, detail=msg)


@router.post("/protocols/{protocol_id}/detect-gaps", response_model=GapDetectionResponse)
async def post_detect_gaps(
    protocol_id: str,
    body: GapDetectionRequest = GapDetectionRequest(),
    session: AsyncSession = Depends(get_session),
    mode: LLMMode = Depends(resolve_llm_mode),
):
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

    try:
        return await detect_gaps(
            protocol_id=protocol_id,
            protocol=row.document,
            mode=mode,
            section_texts_override=body.section_texts,
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "missing Azure config" in msg or "LiveLLMClient" in msg:
            raise HTTPException(
                status_code=503,
                detail="Live mode unavailable: missing Azure config on this machine. Use FAKE or CACHED mode instead.",
            )
        raise HTTPException(status_code=500, detail=msg)
