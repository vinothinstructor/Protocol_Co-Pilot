"""
Locks the 73 → 19 demo arc by automated test.
If anything drifts (formula change, data change, wrong candidate_id), this catches it.
"""
import os
import pytest

os.environ["LLM_MODE"] = "fake"

from sqlalchemy.pool import NullPool
import app.db.session as _db
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.config import settings as _cfg
from sqlalchemy import delete

_test_engine = create_async_engine(_cfg.database_url, poolclass=NullPool)
_db.engine = _test_engine
_db.AsyncSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)

from app.main import app  # noqa: E402


async def _reset_protocol_state():
    """Truncate clause_history + revert protocol_versions to v3.2 only."""
    from app.db.session import AsyncSessionLocal, init_db
    from app.db.models import ClauseHistory, ProtocolVersion

    await init_db()
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(ClauseHistory).where(ClauseHistory.protocol_id == "DIABETES-2026-PH3")
        )
        # Remove any versions beyond v3.2 (created by previous accept-fix calls)
        await session.execute(
            delete(ProtocolVersion).where(
                ProtocolVersion.protocol_id == "DIABETES-2026-PH3",
                ProtocolVersion.version != "v3.2",
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_formula_arc():
    """Unit-level: verify the formula produces the exact sequence."""
    from app.utils.scoring import compute_overall_risk
    assert compute_overall_risk(3, 5, 12) == 73
    assert compute_overall_risk(2, 5, 13) == 55
    assert compute_overall_risk(1, 5, 14) == 37
    assert compute_overall_risk(0, 5, 15) == 19


@pytest.mark.asyncio
async def test_full_demo_arc():
    """
    Full HTTP arc: score → suggest → accept × 3 → 73% → 19%.
    Accepts the top candidate (fix_1) for each HIGH clause in order.
    """
    await _reset_protocol_state()

    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:

        # 1. Score demo protocol → 73
        r = await c.post("/protocols/DIABETES-2026-PH3/score", json={})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["overall_risk"] == 73
        assert data["severity_counts"]["high"] == 3

        # 2. Accept drug-naïve fix → 55
        r = await c.post("/protocols/DIABETES-2026-PH3/clauses/blk_4_4/suggest-fix", json={})
        assert r.status_code == 200, r.text
        assert len(r.json()["candidates"]) == 3

        r = await c.post("/protocols/DIABETES-2026-PH3/clauses/blk_4_4/accept-fix",
                         json={"candidate_id": "blk_4_4_fix_1"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["new_overall_risk"] == 55, f"Expected 55, got {d['new_overall_risk']}"
        assert d["new_severity_counts"]["high"] == 2
        assert d["new_severity_counts"]["low"] == 13

        # 3. Accept BMI fix → 37
        r = await c.post("/protocols/DIABETES-2026-PH3/clauses/blk_4_3/suggest-fix", json={})
        assert r.status_code == 200

        r = await c.post("/protocols/DIABETES-2026-PH3/clauses/blk_4_3/accept-fix",
                         json={"candidate_id": "blk_4_3_fix_1"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["new_overall_risk"] == 37, f"Expected 37, got {d['new_overall_risk']}"
        assert d["new_severity_counts"]["high"] == 1

        # 4. Accept weekly visits fix → 19
        r = await c.post("/protocols/DIABETES-2026-PH3/clauses/blk_6_2/suggest-fix", json={})
        assert r.status_code == 200

        r = await c.post("/protocols/DIABETES-2026-PH3/clauses/blk_6_2/accept-fix",
                         json={"candidate_id": "blk_6_2_fix_1"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["new_overall_risk"] == 19, f"Expected 19, got {d['new_overall_risk']}"
        assert d["new_severity_counts"]["high"] == 0
        assert d["new_severity_counts"]["medium"] == 5
        assert d["new_severity_counts"]["low"] == 15


@pytest.mark.asyncio
async def test_accept_idempotent():
    """Accepting the same candidate twice returns same state without double-applying."""
    await _reset_protocol_state()

    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r1 = await c.post("/protocols/DIABETES-2026-PH3/clauses/blk_5_6/accept-fix",
                          json={"candidate_id": "blk_5_6_fix_1"})
        assert r1.status_code == 200
        r2 = await c.post("/protocols/DIABETES-2026-PH3/clauses/blk_5_6/accept-fix",
                          json={"candidate_id": "blk_5_6_fix_1"})
        assert r2.status_code == 200
        assert r1.json()["new_overall_risk"] == r2.json()["new_overall_risk"]


@pytest.mark.asyncio
async def test_dismiss():
    """Dismiss records in history and returns an ack."""
    await _reset_protocol_state()

    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/protocols/DIABETES-2026-PH3/clauses/blk_6_3/dismiss",
                         json={"reason": "Discuss with medical monitor"})
        assert r.status_code == 200
        data = r.json()
        assert data["action"] == "dismiss"
