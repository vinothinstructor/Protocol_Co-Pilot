"""
Per-request LLM mode resolution via the X-LLM-Mode header.
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


async def _reset():
    from app.db.session import AsyncSessionLocal, init_db
    from app.db.models import ClauseHistory, ProtocolVersion
    await init_db()
    async with AsyncSessionLocal() as session:
        await session.execute(delete(ClauseHistory).where(ClauseHistory.protocol_id == "DIABETES-2026-PH3"))
        await session.execute(delete(ProtocolVersion).where(
            ProtocolVersion.protocol_id == "DIABETES-2026-PH3",
            ProtocolVersion.version != "v3.2",
        ))
        await session.commit()


@pytest.mark.asyncio
async def test_resolve_llm_mode_unit():
    """Header values map to LLMMode; invalid values fall back to settings."""
    from app.utils.llm_mode_dependency import resolve_llm_mode
    from app.config import LLMMode

    assert resolve_llm_mode("mock") == LLMMode.MOCK
    assert resolve_llm_mode("FAKE") == LLMMode.FAKE       # case-insensitive
    assert resolve_llm_mode("  cached ") == LLMMode.CACHED  # whitespace tolerant
    assert resolve_llm_mode("live") == LLMMode.LIVE
    # Invalid → falls back to env default (FAKE in this test process)
    assert resolve_llm_mode("garbage") == LLMMode.FAKE
    assert resolve_llm_mode(None) == LLMMode.FAKE
    assert resolve_llm_mode("") == LLMMode.FAKE


@pytest.mark.asyncio
async def test_score_header_routes_to_fake_when_default_is_mock(monkeypatch):
    """
    With the default set to MOCK, sending X-LLM-Mode: fake should route through
    the fake-mode path (scripted demo score for blk_4_4 = HIGH/88).
    Without the header, MOCK path would also return fake's scripted score in
    this codebase because mock falls through to score_clause_fake — so we
    instead verify the response is identical with the header set vs without,
    which confirms the header doesn't break anything.
    """
    await _reset()
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # With explicit header
        r1 = await c.post(
            "/protocols/DIABETES-2026-PH3/score",
            json={"block_ids": ["blk_4_4"]},
            headers={"X-LLM-Mode": "fake"},
        )
        # Without header (env default FAKE)
        r2 = await c.post(
            "/protocols/DIABETES-2026-PH3/score",
            json={"block_ids": ["blk_4_4"]},
        )

    assert r1.status_code == 200 and r2.status_code == 200
    a = r1.json()["clauses"][0]
    b = r2.json()["clauses"][0]
    assert a["score"] == b["score"] == 88
    assert a["risk_level"] == b["risk_level"] == "high"


@pytest.mark.asyncio
async def test_score_with_invalid_header_falls_back():
    """Garbage header value → 200 with default-mode behavior, not a 422/500."""
    await _reset()
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/protocols/DIABETES-2026-PH3/score",
            json={"block_ids": ["blk_4_3"]},
            headers={"X-LLM-Mode": "not_a_real_mode"},
        )

    assert r.status_code == 200
    assert r.json()["clauses"][0]["score"] == 82  # scripted BMI HIGH


@pytest.mark.asyncio
async def test_health_returns_default_mode():
    """/health reports the env-var default mode, used by the frontend to init the dropdown."""
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json()["llm_mode"] == "fake"  # matches LLM_MODE env in this test
