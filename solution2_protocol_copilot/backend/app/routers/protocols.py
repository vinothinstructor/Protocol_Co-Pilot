from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_session
from app.db.models import ProtocolVersion
from app.schemas import ProtocolResponse

router = APIRouter()


@router.get("/protocols/{protocol_id}", response_model=ProtocolResponse)
async def get_protocol(protocol_id: str, session: AsyncSession = Depends(get_session)):
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

    return ProtocolResponse(
        protocol_id=row.protocol_id,
        version=row.version,
        document=row.document,
    )
