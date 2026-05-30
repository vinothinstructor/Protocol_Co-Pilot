"""
Feasibility Simulator tests.
Locks the four-state demo arc to prevent regressions.
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
        await session.execute(
            delete(ClauseHistory).where(ClauseHistory.protocol_id == "DIABETES-2026-PH3")
        )
        await session.execute(
            delete(ProtocolVersion).where(
                ProtocolVersion.protocol_id == "DIABETES-2026-PH3",
                ProtocolVersion.version != "v3.2",
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_mock_mode_returns_placeholder():
    """Mock mode returns a projection with 0-valued placeholder metrics."""
    from app.config import LLMMode
    from app.agents.feasibility_simulator import project_feasibility

    proj = await project_feasibility(
        protocol_id="TEST",
        version="v1.0",
        overall_risk=0,
        accepted_block_ids=set(),
        mode=LLMMode.MOCK,
    )
    assert proj.rationale == "Mock mode — Feasibility Simulator not available."
    assert all(m.current_value == 0.0 for m in proj.metrics)


@pytest.mark.asyncio
async def test_fake_baseline_projection():
    """Fake mode returns the scripted baseline projection when no fixes are accepted."""
    from app.config import LLMMode
    from app.agents.feasibility_simulator import project_feasibility

    proj = await project_feasibility(
        protocol_id="DIABETES-2026-PH3",
        version="v3.2",
        overall_risk=73,
        accepted_block_ids=set(),
        mode=LLMMode.FAKE,
    )
    assert proj.metrics_by_name["screen_failure_rate"] == 70.0
    assert proj.metrics_by_name["sites_required"] == 60.0
    assert proj.metrics_by_name["time_to_lsi_weeks"] == 38.0
    assert proj.metrics_by_name["enrollment_cost_savings_usd_m"] == 0.0
    assert proj.overall_risk == 73
    assert proj.overall_risk_baseline == 73


@pytest.mark.asyncio
async def test_fake_after_all_three_fixes():
    """Fake mode returns the fully-improved projection after all three HIGH fixes."""
    from app.config import LLMMode
    from app.agents.feasibility_simulator import project_feasibility

    proj = await project_feasibility(
        protocol_id="DIABETES-2026-PH3",
        version="v3.3",
        overall_risk=19,
        accepted_block_ids={"blk_4_4", "blk_4_3", "blk_6_2"},
        mode=LLMMode.FAKE,
    )
    assert proj.metrics_by_name["screen_failure_rate"] == 28.0
    assert proj.metrics_by_name["sites_required"] == 55.0
    assert proj.metrics_by_name["time_to_lsi_weeks"] == 33.0
    assert proj.metrics_by_name["enrollment_cost_savings_usd_m"] == 1.4


@pytest.mark.asyncio
async def test_endpoint_contract():
    """POST /protocols/{id}/feasibility returns a valid FeasibilityProjection."""
    await _reset()

    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"X-LLM-Mode": "fake"}) as c:
        r = await c.post("/protocols/DIABETES-2026-PH3/feasibility", json={})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "metrics" in data
        assert "rationale" in data
        assert "overall_risk" in data
        assert "overall_risk_baseline" in data
        assert "generated_at" in data
        assert len(data["metrics"]) == 4

        names = {m["name"] for m in data["metrics"]}
        assert names == {
            "screen_failure_rate", "sites_required",
            "time_to_lsi_weeks", "enrollment_cost_savings_usd_m"
        }

        # Each metric has required fields
        for m in data["metrics"]:
            assert "current_value" in m
            assert "baseline_value" in m
            assert "unit" in m
            assert "delta" in m
            assert "delta_label" in m


@pytest.mark.asyncio
async def test_feasibility_demo_arc():
    """
    Verify the four scripted projections produce the expected sequence
    as the demo's three HIGH fixes are accepted in order.
    """
    await _reset()

    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"X-LLM-Mode": "fake"}) as c:

        async def fetch_projection():
            r = await c.post("/protocols/DIABETES-2026-PH3/feasibility", json={})
            assert r.status_code == 200, r.text
            data = r.json()
            return {m["name"]: m["current_value"] for m in data["metrics"]}

        # baseline
        p0 = await fetch_projection()
        assert p0["screen_failure_rate"] == 70.0
        assert p0["enrollment_cost_savings_usd_m"] == 0.0

        # accept drug-naive fix → after_drug_naive_fix
        r = await c.post("/protocols/DIABETES-2026-PH3/clauses/blk_4_4/accept-fix",
                         json={"candidate_id": "blk_4_4_fix_1"})
        assert r.status_code == 200
        p1 = await fetch_projection()
        assert p1["screen_failure_rate"] == 42.0
        assert p1["time_to_lsi_weeks"] == 35.0

        # accept BMI fix → after_drug_naive_and_bmi_fixes
        r = await c.post("/protocols/DIABETES-2026-PH3/clauses/blk_4_3/accept-fix",
                         json={"candidate_id": "blk_4_3_fix_1"})
        assert r.status_code == 200
        p2 = await fetch_projection()
        assert p2["screen_failure_rate"] == 32.0

        # accept weekly visits fix → after_all_three_fixes
        r = await c.post("/protocols/DIABETES-2026-PH3/clauses/blk_6_2/accept-fix",
                         json={"candidate_id": "blk_6_2_fix_1"})
        assert r.status_code == 200
        p3 = await fetch_projection()
        assert p3["screen_failure_rate"] == 28.0
        assert p3["enrollment_cost_savings_usd_m"] == 1.4


@pytest.mark.asyncio
async def test_heuristic_fallback_for_out_of_order_accepts():
    """Accepting fixes in non-standard order falls back to heuristic (no crash)."""
    await _reset()

    from app.config import LLMMode
    from app.agents.feasibility_simulator import project_feasibility

    # Accept BMI only (out of order — drug-naive not yet accepted)
    proj = await project_feasibility(
        protocol_id="DIABETES-2026-PH3",
        version="v3.2",
        overall_risk=55,
        accepted_block_ids={"blk_4_3"},
        mode=LLMMode.FAKE,
    )
    # Should return a non-zero projection, not crash
    assert proj.metrics_by_name["screen_failure_rate"] > 0
    assert proj.metrics_by_name["screen_failure_rate"] < 70.0


@pytest.mark.asyncio
async def test_mock_mode_endpoint():
    """Mock mode endpoint returns a projection with unavailable rationale (no crash)."""
    await _reset()

    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"X-LLM-Mode": "mock"}) as c:
        r = await c.post("/protocols/DIABETES-2026-PH3/feasibility", json={})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "Mock mode" in data["rationale"]
