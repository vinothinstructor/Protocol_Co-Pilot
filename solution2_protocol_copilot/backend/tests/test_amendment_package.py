"""
Phase 7: Amendment export package endpoint.
Locks the full demo arc → export shape and markdown quality.
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
async def test_export_no_accepted_returns_400():
    """With no accepted fixes, export should 400."""
    await _reset()
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/protocols/DIABETES-2026-PH3/amendment-package")
    assert r.status_code == 400
    assert "No accepted" in r.json()["detail"]


@pytest.mark.asyncio
async def test_accept_fix_does_not_bump_version():
    """Accept-fix records history but does NOT bump the protocol version."""
    await _reset()
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # Three accepts in a row
        for bid, cid in [
            ("blk_4_4", "blk_4_4_fix_1"),
            ("blk_4_3", "blk_4_3_fix_1"),
            ("blk_6_2", "blk_6_2_fix_1"),
        ]:
            r = await c.post(f"/protocols/DIABETES-2026-PH3/clauses/{bid}/accept-fix",
                             json={"candidate_id": cid})
            assert r.status_code == 200, r.text
            # The response's `version` stays at v3.2 — no bump per Accept
            assert r.json()["version"] == "v3.2", \
                f"Expected version=v3.2 (no bump on accept), got {r.json()['version']}"


@pytest.mark.asyncio
async def test_export_after_three_high_fixes():
    """Full demo arc → export package bumps version exactly once: v3.2 → v3.3."""
    await _reset()
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # Accept the 3 HIGH fixes in order
        for bid, cid in [
            ("blk_4_4", "blk_4_4_fix_1"),
            ("blk_4_3", "blk_4_3_fix_1"),
            ("blk_6_2", "blk_6_2_fix_1"),
        ]:
            r = await c.post(f"/protocols/DIABETES-2026-PH3/clauses/{bid}/accept-fix",
                             json={"candidate_id": cid})
            assert r.status_code == 200, r.text

        # Export — bumps once
        r = await c.get("/protocols/DIABETES-2026-PH3/amendment-package")
        assert r.status_code == 200, r.text
        data = r.json()

    # Shape — exactly one minor bump
    assert data["protocol_id"] == "DIABETES-2026-PH3"
    assert data["from_version"] == "v3.2"
    assert data["to_version"] == "v3.3", f"Expected v3.3, got {data['to_version']}"
    assert data["overall_risk_before"] == 73
    assert data["overall_risk_after"] == 19
    assert len(data["changes"]) == 3

    # Each change has a rationale + label pulled from demo_fix_candidates.json
    for change in data["changes"]:
        assert change["rationale"] != "Rationale not available."
        assert change["label"]
        assert change["section"].startswith("Section ")
        assert change["original_text"]
        assert change["new_text"]
        assert change["risk_before"] > change["risk_after"]

    # Markdown quality checks — must include key structural elements
    md = data["markdown"]
    assert "# Protocol Amendment Package" in md
    assert "v3.2 → " in md
    assert "73% → 19%" in md
    assert "## Change 1 — " in md
    assert "## Change 2 — " in md
    assert "## Change 3 — " in md
    assert "~~" in md  # strikethrough on originals
    assert "## Methodology" in md
    assert "## Sign-off" in md
    assert "- [ ] Medical Director review" in md
    assert "IQVIA Protocol Co-Pilot" in md


@pytest.mark.asyncio
async def test_export_is_idempotent_no_double_bump():
    """Calling export twice without new accepts should NOT bump again."""
    await _reset()
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/protocols/DIABETES-2026-PH3/clauses/blk_4_4/accept-fix",
                     json={"candidate_id": "blk_4_4_fix_1"})

        r1 = await c.get("/protocols/DIABETES-2026-PH3/amendment-package")
        r2 = await c.get("/protocols/DIABETES-2026-PH3/amendment-package")

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["to_version"] == "v3.3"
    assert r2.json()["to_version"] == "v3.3", "Second call should not bump again"
    assert r2.json()["from_version"] == "v3.2"
    # Both calls show the same change
    assert len(r1.json()["changes"]) == len(r2.json()["changes"]) == 1


@pytest.mark.asyncio
async def test_export_second_package_bumps_again():
    """Accept more fixes after a package → next package bumps v3.3 → v3.4
    and includes only the newly-accepted changes."""
    await _reset()
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # First batch: 1 accept, then export → v3.3
        await c.post("/protocols/DIABETES-2026-PH3/clauses/blk_4_4/accept-fix",
                     json={"candidate_id": "blk_4_4_fix_1"})
        r1 = await c.get("/protocols/DIABETES-2026-PH3/amendment-package")
        assert r1.json()["to_version"] == "v3.3"

        # Second batch: accept another fix, then export → v3.4
        await c.post("/protocols/DIABETES-2026-PH3/clauses/blk_4_3/accept-fix",
                     json={"candidate_id": "blk_4_3_fix_1"})
        r2 = await c.get("/protocols/DIABETES-2026-PH3/amendment-package")
        data = r2.json()

    assert data["from_version"] == "v3.3", data
    assert data["to_version"] == "v3.4", data
    # Only the new change (blk_4_3) appears in package 2; blk_4_4 was in package 1
    assert len(data["changes"]) == 1
    assert data["changes"][0]["clause_id"] == "blk_4_3"


@pytest.mark.asyncio
async def test_export_one_fix_returns_one_change():
    """Single accept → package has one Change section."""
    await _reset()
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/protocols/DIABETES-2026-PH3/clauses/blk_4_4/accept-fix",
                     json={"candidate_id": "blk_4_4_fix_1"})
        r = await c.get("/protocols/DIABETES-2026-PH3/amendment-package")

    assert r.status_code == 200
    data = r.json()
    assert len(data["changes"]) == 1
    assert "## Change 1 — Section 4" in data["markdown"]
    assert "## Change 2" not in data["markdown"]
    # The summary line uses singular form for 1 change
    assert "1 accepted clause modification" in data["markdown"]
    assert "1 accepted clause modifications" not in data["markdown"]  # no plural 's'
