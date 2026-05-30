"""
One-time script to pre-cache Drafting Agent responses from Azure OpenAI.
Run this on the office laptop (where Azure credentials are configured) in LIVE mode.

Usage:
    cd backend
    LLM_MODE=live uv run python scripts/precache_drafting.py
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

TOPICS = [
    ("Severe hypoglycemia exclusion",       "Section 5 — Exclusion Criteria"),
    ("HbA1c upper bound exclusion",         "Section 5 — Exclusion Criteria"),
    ("Cardiovascular history exclusion",    "Section 5 — Exclusion Criteria"),
    ("Renal function inclusion criterion",  "Section 4 — Inclusion Criteria"),
    ("Pregnancy/contraception requirement", "Section 4 — Inclusion Criteria"),
]


async def main():
    import os
    from app.config import LLMMode
    from app.agents.drafting import draft_clause, _CACHE_PATH

    if os.environ.get("LLM_MODE", "").lower() != "live":
        print("ERROR: Set LLM_MODE=live before running this script.")
        sys.exit(1)

    print(f"Pre-caching drafting clauses → {_CACHE_PATH}")
    print("This makes 5 Azure calls. Run only on the office laptop.\n")

    for topic, section in TOPICS:
        print(f"  Drafting: {topic}")
        try:
            resp = await draft_clause(topic, "diabetes", section, LLMMode.LIVE)
            print(f"    OK: {resp.clause_text[:80]}...")
        except Exception as e:
            print(f"    ERROR: {e}")

    print("\nDone. drafting_cache.json updated.")


if __name__ == "__main__":
    asyncio.run(main())
