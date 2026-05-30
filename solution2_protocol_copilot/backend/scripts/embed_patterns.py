"""
Embed all 50 amendment patterns and save to DB + JSON file.

Embedding text = example_clause + " " + root_cause  (richest signal for matching)

Usage:
    # On office laptop (real Azure embeddings — run once, then commit the JSON):
    LLM_MODE=live uv run python scripts/embed_patterns.py

    # On MacBook (pseudo-embeddings for dev plumbing — does NOT produce semantic matches):
    LLM_MODE=fake uv run python scripts/embed_patterns.py
"""
import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.config import settings
from app.db.session import AsyncSessionLocal, init_db
from sqlalchemy import select
from app.db.models import AmendmentPattern

DATA_DIR = pathlib.Path(__file__).parent.parent / "app" / "data"
OUTPUT_FILE = DATA_DIR / "amendment_patterns_embeddings.json"


async def main():
    from app.utils.llm_client import get_llm_client

    print(f"Mode: {settings.llm_mode.value}")
    await init_db()
    client = get_llm_client()

    async with AsyncSessionLocal() as session:
        patterns = (await session.execute(select(AmendmentPattern))).scalars().all()
        print(f"Embedding {len(patterns)} patterns...")

        embeddings: dict[str, list[float]] = {}
        for i, pat in enumerate(patterns, 1):
            embed_text = pat.example_clause + " " + pat.root_cause
            vec = await client.embed(embed_text)
            pat.embedding = vec
            embeddings[pat.pattern_id] = vec
            print(f"  [{i:02d}/{len(patterns)}] {pat.pattern_id} ✓")

        await session.commit()

    # Write JSON artifact for commit (enables non-live modes to load real embeddings)
    OUTPUT_FILE.write_text(json.dumps(embeddings, indent=2))
    print(f"\n✓ Embeddings written to DB ({len(embeddings)} patterns)")
    print(f"✓ Saved: {OUTPUT_FILE}")
    if settings.llm_mode.value != "live":
        print("\nNOTE: These are pseudo-embeddings (not semantically meaningful).")
        print("Run with LLM_MODE=live on the office laptop to produce real embeddings.")


if __name__ == "__main__":
    asyncio.run(main())
