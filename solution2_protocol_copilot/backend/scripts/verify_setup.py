"""
Verify the Phase 1 environment is correctly configured.
Run from the backend directory: python scripts/verify_setup.py
"""
import asyncio
import os
import sys

# Ensure app package is importable from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    from app.config import settings, LLMMode

    print("=" * 55)
    print("  Protocol Co-Pilot — Phase 1 Environment Check")
    print("=" * 55)
    ok = True

    # 1. Postgres reachable
    engine = create_async_engine(settings.database_url, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        print("✓ Postgres reachable")
    except Exception as e:
        print(f"✗ Postgres NOT reachable: {e}")
        ok = False

    # 2. pgvector extension present
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname='vector'")
            )
            row = result.fetchone()
            if row:
                print("✓ pgvector extension present")
            else:
                print("✗ pgvector extension NOT found (run: CREATE EXTENSION IF NOT EXISTS vector)")
                ok = False
    except Exception as e:
        print(f"✗ pgvector check failed: {e}")
        ok = False

    # 3. Tables exist
    try:
        async with engine.connect() as conn:
            tables = []
            for table in ["amendment_patterns", "clause_history", "protocol_versions"]:
                result = await conn.execute(
                    text(f"SELECT to_regclass('public.{table}')")
                )
                val = result.scalar()
                tables.append((table, val is not None))
        all_ok = all(v for _, v in tables)
        for name, exists in tables:
            symbol = "✓" if exists else "✗"
            print(f"  {symbol} Table '{name}' {'exists' if exists else 'MISSING'}")
        if not all_ok:
            print("  → Run: python -m app.db.seed  (creates tables + seeds data)")
            ok = False
        else:
            print("✓ All tables exist")
    except Exception as e:
        print(f"✗ Table check failed: {e}")
        ok = False

    # 4. Seed data loaded
    try:
        async with engine.connect() as conn:
            pat_count = (await conn.execute(text("SELECT COUNT(*) FROM amendment_patterns"))).scalar()
            proto_count = (await conn.execute(text("SELECT COUNT(*) FROM protocol_versions"))).scalar()
        if pat_count >= 5 and proto_count >= 1:
            print(f"✓ Seed data: {pat_count} patterns, {proto_count} protocol(s)")
        else:
            print(f"✗ Seed data incomplete: {pat_count} patterns, {proto_count} protocol(s) — run python -m app.db.seed")
            ok = False
    except Exception as e:
        print(f"✗ Seed data check failed: {e}")
        ok = False

    await engine.dispose()

    # 5. Azure checks (live mode only)
    if settings.llm_mode == LLMMode.LIVE:
        print(f"\nLLM_MODE=live — checking Azure connectivity...")
        try:
            from app.utils.llm_client import LiveLLMClient
            client = LiveLLMClient()
            emb = await client.embed("test")
            assert len(emb) == settings.embedding_dim, f"Expected {settings.embedding_dim} dims"
            print(f"✓ Azure embedding: {len(emb)}-dim vector returned")
        except Exception as e:
            print(f"✗ Azure embedding failed: {e}")
            ok = False

        try:
            reply = await client.complete("Reply with: ok", agent="verify")
            print(f"✓ Azure chat completion: '{reply[:40]}'")
        except Exception as e:
            print(f"✗ Azure chat completion failed: {e}")
            ok = False
    else:
        print(f"\nSkipping Azure checks (LLM_MODE={settings.llm_mode.value}, not 'live')")

    print("=" * 55)
    if ok:
        print("  All checks PASSED — ready for Phase 1 demo")
    else:
        print("  Some checks FAILED — see above")
    print("=" * 55)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
