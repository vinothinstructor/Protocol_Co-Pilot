"""
Seed the database with demo protocol and 50-pattern amendment corpus.
Run via: uv run python -m app.db.seed
Idempotent — delete-then-insert for patterns, upsert for protocol.

If app/data/amendment_patterns_embeddings.json exists (pre-computed on office laptop),
embeddings are loaded into the DB in ALL modes so pgvector is genuinely searchable.
"""
import asyncio
import json
import pathlib
from sqlalchemy import select, delete, text
from app.db.session import AsyncSessionLocal, init_db
from app.db.models import AmendmentPattern, ProtocolVersion

DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
EMBEDDINGS_FILE = DATA_DIR / "amendment_patterns_embeddings.json"


async def seed():
    await init_db()

    async with AsyncSessionLocal() as session:
        # ── Load pre-computed embeddings if available ──────────────────────────
        embeddings: dict[str, list[float]] = {}
        if EMBEDDINGS_FILE.exists():
            embeddings = json.loads(EMBEDDINGS_FILE.read_text())
            print(f"  Loaded pre-computed embeddings for {len(embeddings)} patterns")

        # ── Amendment patterns (delete-then-insert for full refresh) ───────────
        await session.execute(delete(AmendmentPattern))

        patterns_raw = json.loads((DATA_DIR / "amendment_patterns.json").read_text())
        for pat in patterns_raw:
            emb = embeddings.get(pat["pattern_id"])
            session.add(
                AmendmentPattern(
                    pattern_id=pat["pattern_id"],
                    category=pat["category"],
                    example_clause=pat["example_clause"],
                    amendment=pat["amendment"],
                    root_cause=pat["root_cause"],
                    therapeutic_areas=pat["therapeutic_areas"],
                    source=pat.get("source", ""),
                    embedding=emb,
                )
            )

        # ── Protocol version (upsert by protocol_id + version) ────────────────
        protocol_raw = json.loads((DATA_DIR / "demo_protocol.json").read_text())
        protocol_id = protocol_raw["protocol_id"]
        version = protocol_raw["version"]

        existing = (
            await session.execute(
                select(ProtocolVersion).where(
                    ProtocolVersion.protocol_id == protocol_id,
                    ProtocolVersion.version == version,
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            session.add(
                ProtocolVersion(
                    protocol_id=protocol_id,
                    version=version,
                    document=protocol_raw,
                    overall_risk=None,
                )
            )

        await session.commit()
        print(f"✓ Seeded {len(patterns_raw)} amendment patterns")
        if embeddings:
            print(f"✓ Embeddings loaded: {sum(1 for pid in embeddings if pid in {p['pattern_id'] for p in patterns_raw})} patterns")
        else:
            print("  (No embeddings file — run scripts/embed_patterns.py to populate)")
        print(f"✓ Protocol {protocol_id} {version} ready")


if __name__ == "__main__":
    asyncio.run(seed())
