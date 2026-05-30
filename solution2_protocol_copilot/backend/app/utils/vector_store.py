from sqlalchemy import text


async def nearest_patterns(session, embedding: list[float], k: int = 3) -> list[dict]:
    """
    Exact cosine similarity search — no index, deterministic, fast at 50 rows.
    Returns empty list if no embeddings have been populated yet.
    Embedding must be pre-computed (real or pseudo) before calling.
    """
    q = text("""
        SELECT pattern_id, category, example_clause, amendment, root_cause,
               1 - (embedding <=> :emb) AS similarity
        FROM amendment_patterns
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> :emb
        LIMIT :k
    """)
    # pgvector expects bracketed comma-separated string
    emb_str = "[" + ",".join(str(x) for x in embedding) + "]"
    result = await session.execute(q, {"emb": emb_str, "k": k})
    return [dict(row._mapping) for row in result]


def pattern_match_strength(similarity: float) -> int:
    """Convert cosine similarity (0-1) to a 0-100 factor score."""
    return max(0, min(100, round(similarity * 100)))
