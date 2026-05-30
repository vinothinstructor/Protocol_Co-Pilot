"""
Pre-cache scores for all demo protocol clauses in live mode.
Run ONCE on the office laptop after embed_patterns.py.
Commit score_cache.json so demo runs in cached mode deterministically.

Usage:
    LLM_MODE=live uv run python scripts/precache_scores.py
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.config import settings, LLMMode

if settings.llm_mode != LLMMode.LIVE:
    print(f"ERROR: This script requires LLM_MODE=live (current: {settings.llm_mode.value})")
    sys.exit(1)

from app.db.session import AsyncSessionLocal, init_db
from app.routers.score import score_protocol_internal, _DEMO_SCORABLE_BLOCKS


async def main():
    print("Pre-caching scores for DIABETES-2026-PH3 in live mode...")
    await init_db()

    async with AsyncSessionLocal() as session:
        result = await score_protocol_internal(
            "DIABETES-2026-PH3",
            _DEMO_SCORABLE_BLOCKS,
            session,
        )

    print(f"\n✓ Scored {len(result['clauses'])} clauses")
    print(f"✓ Overall risk: {result['overall_risk']}")
    print(f"✓ Severity: {result['severity_counts']}")
    print(f"✓ Cache written to app/cache/score_cache.json")
    print("\nNext: commit score_cache.json and run the demo in LLM_MODE=cached")


if __name__ == "__main__":
    asyncio.run(main())
