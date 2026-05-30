"""
Documents how amendment_patterns.json was generated.
The 50 patterns are hand-authored; this script validates and prints statistics.

Usage: uv run python scripts/generate_amendment_patterns.py
"""
import json, pathlib, collections

DATA = pathlib.Path(__file__).parent.parent / "app" / "data" / "amendment_patterns.json"

patterns = json.loads(DATA.read_text())
print(f"Total patterns: {len(patterns)}")

by_cat = collections.Counter(p["category"] for p in patterns)
for cat, count in sorted(by_cat.items()):
    print(f"  {cat}: {count}")

print("\nKey demo-match patterns:")
for pid in ["AMD_001", "AMD_002", "AMD_021", "AMD_031", "AMD_032", "AMD_011"]:
    p = next((x for x in patterns if x["pattern_id"] == pid), None)
    if p:
        print(f"  {pid} ({p['category']}): {p['example_clause'][:80]}...")
    else:
        print(f"  {pid}: MISSING")

assert len(patterns) == 50, f"Expected 50 patterns, got {len(patterns)}"
print("\n✓ Validation passed")
