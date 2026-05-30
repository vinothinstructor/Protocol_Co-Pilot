"""
One-time script to pre-cache Feasibility Simulator responses from Azure OpenAI.
Run this on the office laptop (where Azure credentials are configured) in LIVE mode.

Usage:
    cd backend
    LLM_MODE=live uv run python scripts/precache_feasibility.py
"""
import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

PROTOCOL_ID = "DIABETES-2026-PH3"

# The four demo states we want to pre-cache
STATES = [
    {"label": "v3.2_baseline",                  "accepted": []},
    {"label": "after_drug_naive_fix",            "accepted": ["blk_4_4"]},
    {"label": "after_drug_naive_and_bmi_fixes",  "accepted": ["blk_4_4", "blk_4_3"]},
    {"label": "after_all_three_fixes",           "accepted": ["blk_4_4", "blk_4_3", "blk_6_2"]},
]

# Risk scores matching the demo arc
RISK_BY_ACCEPTED = {
    frozenset(): 73,
    frozenset(["blk_4_4"]): 55,
    frozenset(["blk_4_4", "blk_4_3"]): 37,
    frozenset(["blk_4_4", "blk_4_3", "blk_6_2"]): 19,
}


async def main():
    import os
    from app.config import LLMMode
    from app.agents.feasibility_simulator import project_feasibility, _CACHE_PATH

    if os.environ.get("LLM_MODE", "").lower() != "live":
        print("ERROR: Set LLM_MODE=live before running this script.")
        sys.exit(1)

    print(f"Pre-caching feasibility projections → {_CACHE_PATH}")
    print("This makes 4 Azure calls. Run only on the office laptop.\n")

    for state in STATES:
        accepted = set(state["accepted"])
        overall_risk = RISK_BY_ACCEPTED.get(frozenset(accepted), 50)
        print(f"  Caching: {state['label']} (risk={overall_risk}%)")
        try:
            proj = await project_feasibility(
                protocol_id=PROTOCOL_ID,
                version="v3.2",
                overall_risk=overall_risk,
                accepted_block_ids=accepted,
                mode=LLMMode.LIVE,
            )
            print(f"    screen_failure_rate={proj.metrics_by_name['screen_failure_rate']}")
        except Exception as e:
            print(f"    ERROR: {e}")

    print("\nDone. feasibility_cache.json updated.")


if __name__ == "__main__":
    asyncio.run(main())
