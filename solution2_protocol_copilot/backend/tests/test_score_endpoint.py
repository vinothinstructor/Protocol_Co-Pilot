"""
Tests for POST /protocols/{id}/score endpoint.
Critical validation: fake mode must produce overall_risk=73, severity 3/5/12.
"""
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

os.environ["LLM_MODE"] = "fake"

# Patch the engine to use NullPool before app imports so each test gets fresh connections
from sqlalchemy.pool import NullPool
import app.db.session as _db
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.config import settings as _cfg

_test_engine = create_async_engine(_cfg.database_url, poolclass=NullPool)
_db.engine = _test_engine
_db.AsyncSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)

from app.main import app  # noqa: E402 — import after patch


@pytest.mark.asyncio
async def test_score_demo_protocol_full():
    """THE critical test: scoring the full demo protocol in fake mode = 73 / 3H 5M 12L."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/protocols/DIABETES-2026-PH3/score", json={})

    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["overall_risk"] == 73, f"Expected 73, got {data['overall_risk']}"
    assert data["severity_counts"]["high"] == 3, f"Expected 3 HIGH, got {data['severity_counts']['high']}"
    assert data["severity_counts"]["medium"] == 5, f"Expected 5 MED, got {data['severity_counts']['medium']}"
    assert data["severity_counts"]["low"] == 12, f"Expected 12 LOW, got {data['severity_counts']['low']}"


@pytest.mark.asyncio
async def test_score_single_clause_drug_naive():
    """Score just blk_4_4 → returns HIGH score 88."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/protocols/DIABETES-2026-PH3/score",
            json={"block_ids": ["blk_4_4"]},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["clauses"]) == 1
    clause = data["clauses"][0]
    assert clause["block_id"] == "blk_4_4"
    assert clause["score"] == 88
    assert clause["risk_level"] == "high"
    assert clause["top_pattern_match"]["pattern_id"] == "AMD_001"


@pytest.mark.asyncio
async def test_score_response_shape():
    """Validate the full response shape includes all required fields."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/protocols/DIABETES-2026-PH3/score",
            json={"block_ids": ["blk_4_4", "blk_4_3"]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "clauses" in data
    assert "overall_risk" in data
    assert "severity_counts" in data

    clause = data["clauses"][0]
    assert "block_id" in clause
    assert "score" in clause
    assert "risk_level" in clause
    assert "factors" in clause
    assert "summary" in clause

    factor = list(clause["factors"].values())[0]
    assert "score" in factor
    assert "reasoning" in factor


@pytest.mark.asyncio
async def test_score_missing_protocol():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/protocols/NONEXISTENT-PROTOCOL/score", json={})

    assert resp.status_code == 404
