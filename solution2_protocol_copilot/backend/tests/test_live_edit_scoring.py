"""
Phase 5: live-edit scoring via /score endpoint with clause_texts.
Locks the QoL/Mandarin heuristic — typing the demo punchline returns MEDIUM
with the AMD_021 pattern match.
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
async def test_typed_qol_mandarin_clause_returns_medium():
    """Demo Moment A: typed QoL/Mandarin clause is scored MEDIUM with AMD_021."""
    await _reset()
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        gen_id = "gen_1740000000_a3f2"
        r = await c.post(
            "/protocols/DIABETES-2026-PH3/score",
            json={
                "block_ids": [gen_id],
                "clause_texts": {
                    gen_id: (
                        "Patient must complete the 12-item Quality-of-Life "
                        "questionnaire in their native language at every visit."
                    )
                },
            },
        )

    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["clauses"]) == 1
    clause = data["clauses"][0]
    assert clause["block_id"] == gen_id
    assert clause["risk_level"] == "medium", clause
    assert clause["top_pattern_match"]["pattern_id"] == "AMD_021", clause
    assert clause["factors"]["endpoint_instrument_validation"]["score"] >= 50


@pytest.mark.asyncio
async def test_overall_includes_user_added_clause():
    """A new MEDIUM clause raises overall from 73 (3H/5M/12L) to 76 (3H/6M/12L)."""
    await _reset()
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        gen_id = "gen_1740000001_b5c1"
        r = await c.post(
            "/protocols/DIABETES-2026-PH3/score",
            json={
                "block_ids": [gen_id],
                "clause_texts": {
                    gen_id: (
                        "Quality-of-Life questionnaire administered in the "
                        "patient's native language."
                    )
                },
            },
        )

    assert r.status_code == 200, r.text
    data = r.json()
    # 3 HIGH + 5 MED + 1 new MED + 12 LOW → compute_overall_risk(3,6,12) = 54+18+4 = 76
    assert data["overall_risk"] == 76, data
    assert data["severity_counts"] == {"high": 3, "medium": 6, "low": 12}


@pytest.mark.asyncio
async def test_scoring_revert_restores_original():
    """
    Editing a HIGH clause to a benign rewrite drops it to LOW; reverting the
    text back to the exact original restores the scripted HIGH score and the
    original 73% overall risk. Locks the text-match-first routing in score.py.
    """
    await _reset()
    from httpx import AsyncClient, ASGITransport

    BMI_ORIGINAL = "Have a body mass index (BMI) below 35 kg/m²."
    BMI_EDITED = "Have a body mass index between 25 and 45 kg per square meter with medical clearance."

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:

        # 1. Edit → LOW + 55
        r1 = await c.post(
            "/protocols/DIABETES-2026-PH3/score",
            json={"block_ids": ["blk_4_3"], "clause_texts": {"blk_4_3": BMI_EDITED}},
        )
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["clauses"][0]["risk_level"] == "low", d1["clauses"][0]
        assert d1["overall_risk"] == 55, d1

        # 2. Revert → HIGH + 73 (the bug this test locks)
        r2 = await c.post(
            "/protocols/DIABETES-2026-PH3/score",
            json={"block_ids": ["blk_4_3"], "clause_texts": {"blk_4_3": BMI_ORIGINAL}},
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["clauses"][0]["risk_level"] == "high", d2["clauses"][0]
        assert d2["clauses"][0]["score"] == 82, d2["clauses"][0]  # scripted score from demo_clause_scores
        assert d2["overall_risk"] == 73, d2
        assert d2["severity_counts"] == {"high": 3, "medium": 5, "low": 12}


@pytest.mark.asyncio
async def test_revert_normalizes_whitespace():
    """Live text matching the original after whitespace collapse still counts as revert."""
    await _reset()
    from httpx import AsyncClient, ASGITransport

    # Same as blk_4_3 original, but with extra internal whitespace
    BMI_LOOSE = "Have a  body mass  index (BMI) below 35  kg/m².  "

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/protocols/DIABETES-2026-PH3/score",
            json={"block_ids": ["blk_4_3"], "clause_texts": {"blk_4_3": BMI_LOOSE}},
        )
    assert r.status_code == 200
    d = r.json()
    # Whitespace-collapsed → equals original → scripted HIGH
    assert d["clauses"][0]["risk_level"] == "high"
    assert d["overall_risk"] == 73


@pytest.mark.asyncio
async def test_revert_drug_naive_and_weekly_visits():
    """Same revert behavior for the other two HIGH demo clauses."""
    await _reset()
    from httpx import AsyncClient, ASGITransport

    DRUG_NAIVE_ORIG = "Be drug-naïve at screening, with no prior antidiabetic agents of any kind."
    WEEKLY_ORIG = (
        "Treatment Phase — Weekly Clinic Visits for 24 Weeks: Participants must attend clinic "
        "weekly throughout the 24-week double-blind treatment period (Weeks 1 through 24), at "
        "which time study drug will be dispensed, insulin dose titration will be performed per "
        "protocol algorithm, SMBG diaries will be reviewed, and adverse events and concomitant "
        "medications will be assessed."
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # Edit drug-naïve to benign
        await c.post(
            "/protocols/DIABETES-2026-PH3/score",
            json={"block_ids": ["blk_4_4"],
                  "clause_texts": {"blk_4_4": "Be aged between 18 and 65 years at screening."}},
        )
        # Revert
        r = await c.post(
            "/protocols/DIABETES-2026-PH3/score",
            json={"block_ids": ["blk_4_4"], "clause_texts": {"blk_4_4": DRUG_NAIVE_ORIG}},
        )
        assert r.json()["clauses"][0]["risk_level"] == "high"

        # Edit + revert weekly visits
        await c.post(
            "/protocols/DIABETES-2026-PH3/score",
            json={"block_ids": ["blk_6_2"],
                  "clause_texts": {"blk_6_2": "Treatment Phase: visits monthly after stabilization."}},
        )
        r = await c.post(
            "/protocols/DIABETES-2026-PH3/score",
            json={"block_ids": ["blk_6_2"], "clause_texts": {"blk_6_2": WEEKLY_ORIG}},
        )
        assert r.json()["clauses"][0]["risk_level"] == "high"


@pytest.mark.asyncio
async def test_qol_pattern_suggest_fix():
    """
    Text-pattern matching: a gen_ block_id with QoL+native-language content
    triggers the qol_native_language pattern and returns the 3 scripted candidates.
    """
    await _reset()
    from httpx import AsyncClient, ASGITransport

    QOL_CLAUSE = (
        "Patient must complete the 12-item Quality-of-Life questionnaire "
        "in their native language at every visit."
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # Use any gen_ id — pattern matching keys off the live text, not the id
        gen_id = "gen_8888_zzzz"
        r = await c.post(
            f"/protocols/DIABETES-2026-PH3/clauses/{gen_id}/suggest-fix",
            json={"clause_text": QOL_CLAUSE},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["candidates"]) == 3
        ids = [c["candidate_id"] for c in data["candidates"]]
        assert ids == ["qol_fix_1", "qol_fix_2", "qol_fix_3"], ids
        # Top candidate should be the highest-delta one
        assert data["candidates"][0]["delta_overall"] == -3


@pytest.mark.asyncio
async def test_custom_clause_returns_empty_candidates():
    """Unmatched gen_ clauses get an empty candidates list (UI hides Suggest Fix)."""
    await _reset()
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/protocols/DIABETES-2026-PH3/clauses/gen_7777_yyyy/suggest-fix",
            json={"clause_text": "Subjects must own a smartwatch."},
        )
    assert r.status_code == 200
    assert r.json()["candidates"] == []


@pytest.mark.asyncio
async def test_qol_accept_fix_applies_correctly():
    """Accepting qol_fix_1 on a gen_ block returns the post-fix score + 73 overall."""
    await _reset()
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        gen_id = "gen_6666_xxxx"
        r = await c.post(
            f"/protocols/DIABETES-2026-PH3/clauses/{gen_id}/accept-fix",
            json={"candidate_id": "qol_fix_1"},
        )
    assert r.status_code == 200, r.text
    d = r.json()
    # The applied text is the candidate's new_text (validated-languages version)
    assert "validated translation" in d["new_clause_text"].lower() or "English" in d["new_clause_text"]
    # New clause score is LOW
    assert d["new_clause_score"]["risk_level"] == "low"
    # The seeded protocol is untouched (3H/5M/12L). The new LOW gen_ adds to LOW
    # → 3H/5M/13L → 73 (LOW contribution capped at 12).
    assert d["new_overall_risk"] == 73, d
    assert d["new_severity_counts"] == {"high": 3, "medium": 5, "low": 13}
    # No version bump for gen_ accepts
    assert d["version"] == "v3.2"


@pytest.mark.asyncio
async def test_gen_id_still_uses_heuristic():
    """New (gen_) clauses have no scripted entry — heuristic path unchanged."""
    await _reset()
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        gen_id = "gen_9999_aaaa"
        r = await c.post(
            "/protocols/DIABETES-2026-PH3/score",
            json={"block_ids": [gen_id],
                  "clause_texts": {gen_id: "Patient must complete the 12-item Quality-of-Life questionnaire in their native language at every visit."}},
        )
    assert r.status_code == 200
    d = r.json()
    # Heuristic still detects QoL/Mandarin pattern → MEDIUM with AMD_021
    assert d["clauses"][0]["risk_level"] == "medium"
    assert d["clauses"][0]["top_pattern_match"]["pattern_id"] == "AMD_021"


@pytest.mark.asyncio
async def test_edit_existing_demo_block_overrides_scripted_score():
    """
    Demo Moment B: editing blk_4_3 (BMI HIGH) to a benign rewrite drops the
    overall score. With BMI now LOW: counts (2H/5M/13L) → 55.
    """
    await _reset()
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/protocols/DIABETES-2026-PH3/score",
            json={
                "block_ids": ["blk_4_3"],
                "clause_texts": {
                    "blk_4_3": (
                        "Have a body mass index (BMI) below 40 kg/m² with "
                        "appropriate medical clearance documented at screening."
                    )
                },
            },
        )

    assert r.status_code == 200, r.text
    data = r.json()
    # The edited BMI clause should score LOW via heuristic (no restrictive triggers)
    clause = next(c for c in data["clauses"] if c["block_id"] == "blk_4_3")
    assert clause["risk_level"] == "low", clause
    # Overall drops from 73 to 55 (2H/5M/13L)
    assert data["overall_risk"] == 55, data
