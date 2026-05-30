"""
Drafting Agent tests.
Locks the scripted-topic behavior, heuristic fallback, and LIVE-mode error surfacing.
"""
import os
import pytest

os.environ["LLM_MODE"] = "fake"

from sqlalchemy.pool import NullPool
import app.db.session as _db
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.config import settings as _cfg

_test_engine = create_async_engine(_cfg.database_url, poolclass=NullPool)
_db.engine = _test_engine
_db.AsyncSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)

from app.main import app  # noqa: E402


@pytest.mark.asyncio
async def test_mock_returns_placeholder():
    """Mock mode returns a placeholder string containing the topic."""
    from app.config import LLMMode
    from app.agents.drafting import draft_clause

    resp = await draft_clause("severe hypoglycemia exclusion", "diabetes", "Section 5", LLMMode.MOCK)
    assert "Mock clause" in resp.clause_text
    assert "severe hypoglycemia exclusion" in resp.clause_text.lower()


@pytest.mark.asyncio
async def test_drafting_scripted_topics():
    """All 5 pre-set chip topics return scripted clauses (no heuristic fallback)."""
    from app.config import LLMMode
    from app.agents.drafting import draft_clause

    topics = [
        "Severe hypoglycemia exclusion",
        "HbA1c upper bound exclusion",
        "Cardiovascular history exclusion",
        "Renal function inclusion criterion",
        "Pregnancy/contraception requirement",
    ]
    for topic in topics:
        resp = await draft_clause(topic, "diabetes", "Section 5", LLMMode.FAKE)
        assert "[criterion to be drafted by Medical Director review]" not in resp.clause_text, \
            f"Topic '{topic}' fell through to heuristic instead of hitting scripted clause"
        assert len(resp.clause_text) > 50, f"Topic '{topic}' returned trivially short clause"


@pytest.mark.asyncio
async def test_drafting_heuristic_fallback():
    """Freeform topics not in the scripted library use the heuristic placeholder."""
    from app.config import LLMMode
    from app.agents.drafting import draft_clause

    resp = await draft_clause(
        "a completely novel topic about cheese", "diabetes", "Section 4", LLMMode.FAKE
    )
    assert "[criterion to be drafted by Medical Director review]" in resp.clause_text


@pytest.mark.asyncio
async def test_endpoint_contract():
    """POST /protocols/{id}/draft-clause returns a valid DraftClauseResponse in fake mode."""
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"X-LLM-Mode": "fake"}) as c:
        r = await c.post(
            "/protocols/DIABETES-2026-PH3/draft-clause",
            json={"topic": "Severe hypoglycemia exclusion", "therapeutic_area": "diabetes"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "clause_text" in data
        assert "topic" in data
        assert "generated_at" in data
        assert len(data["clause_text"]) > 50
        assert "[criterion to be drafted by Medical Director review]" not in data["clause_text"]


@pytest.mark.asyncio
async def test_drafting_live_mode_without_azure_returns_503():
    """Live mode without Azure credentials surfaces a clean 503, no silent fallback."""
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"X-LLM-Mode": "live"}) as c:
        r = await c.post(
            "/protocols/DIABETES-2026-PH3/draft-clause",
            json={"topic": "Test topic"},
        )
        assert r.status_code == 503, f"Expected 503, got {r.status_code}: {r.text}"
        detail = r.json()["detail"].lower()
        assert "missing azure config" in detail, f"Detail missing expected text: {detail}"


@pytest.mark.asyncio
async def test_cached_mode_falls_back_to_scripted():
    """Cached mode with an empty cache falls back to scripted clauses (not heuristic)."""
    from app.config import LLMMode
    from app.agents.drafting import draft_clause

    resp = await draft_clause(
        "Severe hypoglycemia exclusion", "diabetes", "Section 5", LLMMode.CACHED
    )
    assert "[criterion to be drafted by Medical Director review]" not in resp.clause_text
    assert len(resp.clause_text) > 50


# ── Gap Detection tests ────────────────────────────────────────────────────────

def _make_protocol_with_clause(clause_text: str, section_id: str = "sec_5") -> dict:
    """Build a minimal protocol dict with a synthetic clause in the given section."""
    import json, pathlib
    base = json.loads((pathlib.Path(__file__).parent.parent / "app/data/demo_protocol.json").read_text())
    # Add the synthetic clause to the target section
    for section in base["sections"]:
        if section["section_id"] == section_id:
            section["blocks"].append({
                "block_id": "blk_test_synthetic",
                "type": "clause",
                "text": clause_text,
            })
    return base


@pytest.mark.asyncio
async def test_gap_detection_finds_demo_gaps():
    """The seeded diabetes protocol surfaces the 3 featured demo gaps in fake mode."""
    from app.config import LLMMode
    from app.agents.drafting import detect_gaps
    import json, pathlib

    protocol = json.loads(
        (pathlib.Path(__file__).parent.parent / "app/data/demo_protocol.json").read_text()
    )
    resp = await detect_gaps("DIABETES-2026-PH3", protocol, LLMMode.FAKE)
    assert len(resp.gaps_detected) >= 3

    gap_names = {g.name for g in resp.gaps_detected}
    expected_demo_gaps = {
        "Severe hypoglycemia exclusion",
        "HbA1c upper bound exclusion",
        "Bariatric surgery exclusion",
    }
    assert expected_demo_gaps.issubset(gap_names), \
        f"Expected demo gaps not all detected. Missing: {expected_demo_gaps - gap_names}"


@pytest.mark.asyncio
async def test_gap_detection_skips_present_clauses():
    """If the protocol already contains a clause matching GAP_001 keywords, GAP_001 is NOT returned."""
    from app.config import LLMMode
    from app.agents.drafting import detect_gaps

    # Synthetically add a clause matching GAP_001 keywords to sec_5
    protocol = _make_protocol_with_clause(
        "Patient must not have had severe hypoglycemia in the past 6 months.",
        section_id="sec_5",
    )
    resp = await detect_gaps("DIABETES-2026-PH3", protocol, LLMMode.FAKE)
    gap_ids = {g.gap_id for g in resp.gaps_detected}
    assert "GAP_001" not in gap_ids, "GAP_001 should not fire when severe hypoglycemia clause is present"


@pytest.mark.asyncio
async def test_gap_detection_endpoint_contract():
    """POST /protocols/{id}/detect-gaps returns a valid GapDetectionResponse in fake mode."""
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"X-LLM-Mode": "fake"}) as c:
        r = await c.post("/protocols/DIABETES-2026-PH3/detect-gaps", json={})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "gaps_detected" in data
        assert "checklist_version" in data
        assert "detected_at" in data
        assert len(data["gaps_detected"]) >= 3

        gap = data["gaps_detected"][0]
        for field in ("gap_id", "name", "category", "rationale", "suggested_section",
                      "suggested_section_id", "draft_topic", "severity"):
            assert field in gap, f"Missing field: {field}"


@pytest.mark.asyncio
async def test_gap_detection_section_override_clears_present_gap():
    """The live section_texts override is respected: if the override text contains
    a standard gap's keyword (clause added live), that gap clears."""
    from app.config import LLMMode
    from app.agents.drafting import detect_gaps
    import json, pathlib

    base = json.loads(
        (pathlib.Path(__file__).parent.parent / "app/data/demo_protocol.json").read_text()
    )

    # Baseline: GAP_001 (severe hypoglycemia) fires.
    resp_before = await detect_gaps("DIABETES-2026-PH3", base, LLMMode.FAKE)
    assert "GAP_001" in {g.gap_id for g in resp_before.gaps_detected}

    # Override sec_5 to include a severe-hypoglycemia clause → GAP_001 clears.
    override = {
        "sec_5": "Have a documented history of severe hypoglycemia within 6 months prior to screening.",
    }
    resp_after = await detect_gaps(
        "DIABETES-2026-PH3", base, LLMMode.FAKE, section_texts_override=override
    )
    assert "GAP_001" not in {g.gap_id for g in resp_after.gaps_detected}, \
        "GAP_001 should clear when the section override contains its keyword"


@pytest.mark.asyncio
async def test_gap_detection_initial_load_stays_three():
    """Initial load surfaces exactly the 3 featured standard gaps."""
    from app.config import LLMMode
    from app.agents.drafting import detect_gaps
    import json, pathlib

    base = json.loads(
        (pathlib.Path(__file__).parent.parent / "app/data/demo_protocol.json").read_text()
    )
    resp = await detect_gaps("DIABETES-2026-PH3", base, LLMMode.FAKE)
    names = {g.name for g in resp.gaps_detected}
    assert names == {
        "Severe hypoglycemia exclusion",
        "HbA1c upper bound exclusion",
        "Bariatric surgery exclusion",
    }


@pytest.mark.asyncio
async def test_gap_detection_live_mode_without_azure_returns_503():
    """Live mode without Azure credentials surfaces a clean 503."""
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"X-LLM-Mode": "live"}) as c:
        r = await c.post("/protocols/DIABETES-2026-PH3/detect-gaps", json={})
        assert r.status_code == 503, f"Expected 503, got {r.status_code}: {r.text}"
        detail = r.json()["detail"].lower()
        assert "missing azure config" in detail
