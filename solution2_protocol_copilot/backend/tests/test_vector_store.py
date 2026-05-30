"""Tests for pgvector nearest_patterns (requires seeded DB with embeddings)."""
import pytest
from app.utils.vector_store import nearest_patterns, pattern_match_strength
from app.utils.llm_client import _deterministic_pseudo_embedding
from app.config import settings


def test_pattern_match_strength():
    assert pattern_match_strength(1.0) == 100
    assert pattern_match_strength(0.0) == 0
    assert pattern_match_strength(0.75) == 75
    assert pattern_match_strength(-0.1) == 0  # clamped


@pytest.mark.asyncio
async def test_nearest_patterns_returns_empty_without_embeddings():
    """With no embeddings populated, nearest_patterns returns []."""
    from app.db.session import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        # Check if any embeddings exist
        count = (await session.execute(text("SELECT COUNT(*) FROM amendment_patterns WHERE embedding IS NOT NULL"))).scalar()
        if count == 0:
            embedding = _deterministic_pseudo_embedding("test clause", settings.embedding_dim)
            result = await nearest_patterns(session, embedding, k=3)
            assert result == [], f"Expected empty list when no embeddings, got {result}"
            pytest.skip("No embeddings in DB — expected for MacBook dev without embed_patterns.py run")
        else:
            # Embeddings exist — do a real search
            embedding = _deterministic_pseudo_embedding("drug-naïve antidiabetic", settings.embedding_dim)
            result = await nearest_patterns(session, embedding, k=3)
            assert isinstance(result, list)
            assert len(result) <= 3
            if result:
                assert "pattern_id" in result[0]
                assert "similarity" in result[0]
                assert 0.0 <= result[0]["similarity"] <= 1.0
